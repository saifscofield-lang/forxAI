"""
فلتر الأخبار الاقتصادية — News Filter
يستخدم Forex Factory JSON API (مجاني) لجلب الأحداث الاقتصادية.
يمنع التداول وقت الأخبار عالية التأثير ويخزن الأحداث في قاعدة البيانات لتدريب ML.

المستوى 1: منع التداول 30 دقيقة قبل/بعد أخبار HIGH impact
المستوى 2: إضافة features للـ ML (حدث قريب، مستوى التأثير، المفاجأة)

GAP-FID-03 helper (lookup_news_at_time, 2026-05-07): query the
persisted news_events table for the news context around any
historical trade open time. Used by the engine's close handler to
populate TradeResult.news_nearby + news_event_name + news_impact
(previously these were tagged on the in-flight signal dict but
never written to DB). Enables the meta-labeler to use news
context as a feature.
"""
import json
import hashlib
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from loguru import logger
from storage.database import SessionLocal, NewsEvent


# ── Forex Factory JSON endpoints (free, no auth) ──
FF_THIS_WEEK = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FF_NEXT_WEEK = "https://nfs.faireconomy.media/ff_calendar_nextweek.json"

# ── خريطة العملات → الأزواج المتأثرة ──
CURRENCY_TO_SYMBOLS = {
    "USD": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
    "EUR": ["EURUSD"],
    "GBP": ["GBPUSD"],
    "JPY": ["USDJPY"],
    "XAU": ["XAUUSD"],
    "CHF": ["USDCHF"],
    "AUD": ["AUDUSD"],
    "CAD": ["USDCAD"],
    "NZD": ["NZDUSD"],
}

# ── Map Forex Factory impact strings to our standard levels ──
FF_IMPACT_MAP = {
    "High": "HIGH",
    "Medium": "MEDIUM",
    "Low": "LOW",
    "Holiday": "LOW",
    "Non-Economic": "LOW",
}

# ── Currencies we care about ──
RELEVANT_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD"}


def _parse_ff_number(value_str):
    """Parse a Forex Factory numeric value like '3.5%', '245K', '-1.2B', etc."""
    if value_str is None or value_str == "" or value_str == "N/A":
        return None
    s = str(value_str).strip()
    s = s.replace(",", "").replace("%", "").replace("$", "")
    multiplier = 1.0
    if s.endswith("K"):
        multiplier = 1_000
        s = s[:-1]
    elif s.endswith("M"):
        multiplier = 1_000_000
        s = s[:-1]
    elif s.endswith("B"):
        multiplier = 1_000_000_000
        s = s[:-1]
    elif s.endswith("T"):
        multiplier = 1_000_000_000_000
        s = s[:-1]
    try:
        return float(s) * multiplier
    except (ValueError, TypeError):
        return None


def _generate_event_id(event_name: str, event_time: datetime, currency: str) -> int:
    """Generate a stable integer event_id from event name + time + currency."""
    key = f"{event_name}|{event_time.isoformat()}|{currency}"
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)


class NewsFilter:
    """فلتر الأخبار الاقتصادية باستخدام Forex Factory JSON API."""

    def __init__(
        self,
        block_minutes_before: int = 30,
        block_minutes_after: int = 30,
        min_impact: str = "HIGH",
        symbols: list[str] = None,
    ):
        """
        Parameters
        ----------
        block_minutes_before : minutes to block trading before high-impact news
        block_minutes_after : minutes to block trading after high-impact news
        min_impact : minimum impact level to block ("HIGH" or "MEDIUM")
        symbols : list of trading symbols (to map currencies)
        """
        self.block_before = timedelta(minutes=block_minutes_before)
        self.block_after = timedelta(minutes=block_minutes_after)
        self.min_impact = min_impact
        self.symbols = symbols or ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
        self._cached_events = []
        self._cache_time = None
        self._cache_ttl = timedelta(hours=1)

        # Build reverse map: symbol -> relevant currencies
        self._symbol_currencies = {}
        for symbol in self.symbols:
            currencies = set()
            for currency, syms in CURRENCY_TO_SYMBOLS.items():
                if symbol in syms:
                    currencies.add(currency)
            self._symbol_currencies[symbol] = currencies

    def _fetch_ff_json(self, url: str, timeout: int = 15) -> list[dict]:
        """Fetch and parse JSON from a Forex Factory endpoint."""
        try:
            req = Request(url, headers={"User-Agent": "ForexAI/1.0"})
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except (URLError, HTTPError, json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return []

    def _parse_ff_events(self, raw_events: list[dict]) -> list[dict]:
        """
        Parse Forex Factory JSON events into our standard format.

        FF JSON fields (known structure):
          - title: event name
          - country: currency code (e.g. "USD")
          - date: date+time string (e.g. "2026-03-17T08:30:00-04:00")
          - impact: "High", "Medium", "Low", "Holiday", "Non-Economic"
          - forecast: forecast value string
          - previous: previous value string
          - actual: actual value string (empty if not yet released)
        """
        events = []
        for item in raw_events:
            try:
                currency = item.get("country", "")
                if currency not in RELEVANT_CURRENCIES:
                    continue

                impact = FF_IMPACT_MAP.get(item.get("impact", ""), None)
                if impact is None:
                    continue

                # Parse datetime — FF provides ISO format with timezone offset
                date_str = item.get("date", "")
                if not date_str:
                    continue

                # Parse ISO datetime and convert to UTC-naive
                # FF dates are like "2026-03-17T08:30:00-04:00" (Eastern Time)
                event_time = self._parse_datetime(date_str)
                if event_time is None:
                    continue

                event_name = item.get("title", "Unknown Event")

                actual_val = _parse_ff_number(item.get("actual"))
                forecast_val = _parse_ff_number(item.get("forecast"))
                previous_val = _parse_ff_number(item.get("previous"))

                surprise = None
                if actual_val is not None and forecast_val is not None:
                    surprise = actual_val - forecast_val

                event_id = _generate_event_id(event_name, event_time, currency)

                # Map currency to country code for DB
                country_map = {
                    "USD": "US", "EUR": "EU", "GBP": "GB", "JPY": "JP",
                    "CHF": "CH", "AUD": "AU", "CAD": "CA", "NZD": "NZ",
                }

                events.append({
                    "event_id": event_id,
                    "time": event_time,
                    "country": country_map.get(currency, currency),
                    "currency": currency,
                    "event_name": event_name,
                    "impact": impact,
                    "actual": actual_val,
                    "forecast": forecast_val,
                    "previous": previous_val,
                    "surprise": surprise,
                })

            except Exception as e:
                logger.debug(f"Error parsing FF event: {e}")
                continue

        return events

    @staticmethod
    def _parse_datetime(date_str: str) -> datetime | None:
        """Parse ISO datetime string to UTC-naive datetime."""
        try:
            # Try parsing with timezone info (Python 3.11+ fromisoformat handles offsets)
            dt = datetime.fromisoformat(date_str)
            # Convert to UTC then strip timezone
            if dt.tzinfo is not None:
                from datetime import timezone
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except (ValueError, TypeError):
            pass

        # Fallback: try common formats
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                dt = datetime.strptime(date_str, fmt)
                if dt.tzinfo is not None:
                    from datetime import timezone
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                return dt
            except ValueError:
                continue
        logger.debug(f"Could not parse datetime: {date_str}")
        return None

    def fetch_events(self, hours_ahead: int = 4, hours_behind: int = 1) -> list[dict]:
        """
        Fetch economic calendar events from Forex Factory.

        Parameters
        ----------
        hours_ahead : how many hours ahead to look
        hours_behind : how many hours behind to look

        Returns
        -------
        List of event dicts with: time, currency, event_name, impact, actual, forecast, previous
        """
        now = datetime.utcnow()

        # Use cache if fresh
        if self._cache_time and (now - self._cache_time) < self._cache_ttl:
            return self._filter_by_time(self._cached_events, now, hours_ahead, hours_behind)

        # Fetch this week's events (covers most use cases)
        raw_events = self._fetch_ff_json(FF_THIS_WEEK)

        # If we're near end of week (Friday+), also fetch next week
        if now.weekday() >= 4:  # Friday=4, Saturday=5, Sunday=6
            raw_next = self._fetch_ff_json(FF_NEXT_WEEK)
            raw_events.extend(raw_next)

        events = self._parse_ff_events(raw_events)

        self._cached_events = events
        self._cache_time = now

        high_count = sum(1 for e in events if e["impact"] == "HIGH")
        logger.info(f"Calendar: {len(events)} events fetched ({high_count} HIGH impact)")

        return self._filter_by_time(events, now, hours_ahead, hours_behind)

    @staticmethod
    def _filter_by_time(
        events: list[dict], now: datetime, hours_ahead: int, hours_behind: int
    ) -> list[dict]:
        """Filter events to the requested time window."""
        from_time = now - timedelta(hours=hours_behind)
        to_time = now + timedelta(hours=hours_ahead)
        return [e for e in events if from_time <= e["time"] <= to_time]

    def should_block_trading(self, symbol: str, check_time: datetime = None) -> tuple[bool, str | None]:
        """
        Check if trading should be blocked for a symbol due to upcoming/recent news.

        Parameters
        ----------
        symbol : trading symbol (e.g., "EURUSD")
        check_time : time to check (default: now UTC)

        Returns
        -------
        (should_block, event_name) — True if trading should be blocked, with event name
        """
        if check_time is None:
            check_time = datetime.utcnow()

        events = self.fetch_events()
        relevant_currencies = self._symbol_currencies.get(symbol, set())

        for event in events:
            # Check if this event affects our symbol
            if event["currency"] not in relevant_currencies:
                continue

            # Check impact level
            if self.min_impact == "HIGH" and event["impact"] != "HIGH":
                continue
            if self.min_impact == "MEDIUM" and event["impact"] not in ("HIGH", "MEDIUM"):
                continue

            # Check time window
            event_time = event["time"]
            window_start = event_time - self.block_before
            window_end = event_time + self.block_after

            if window_start <= check_time <= window_end:
                minutes_to_event = (event_time - check_time).total_seconds() / 60
                if minutes_to_event > 0:
                    timing = f"in {abs(minutes_to_event):.0f}min"
                else:
                    timing = f"{abs(minutes_to_event):.0f}min ago"

                reason = f"{event['impact']} impact: {event['event_name']} ({event['currency']}) {timing}"
                logger.warning(f"[{symbol}] BLOCKED by news: {reason}")
                return True, reason

        return False, None

    def get_nearby_events(self, symbol: str, window_hours: float = 1.0) -> list[dict]:
        """Get news events near the current time for a specific symbol."""
        now = datetime.utcnow()
        events = self.fetch_events()
        relevant_currencies = self._symbol_currencies.get(symbol, set())

        nearby = []
        window = timedelta(hours=window_hours)

        for event in events:
            if event["currency"] not in relevant_currencies:
                continue
            if abs((event["time"] - now).total_seconds()) <= window.total_seconds():
                nearby.append(event)

        return nearby

    def get_news_features(self, symbol: str) -> dict:
        """
        Build news-related features for ML model.

        Returns dict with:
        - has_news_1h: bool — any news within +/-1 hour
        - has_high_impact_1h: bool — HIGH impact news within +/-1 hour
        - minutes_to_next_news: float — minutes until next news event (999 if none)
        - nearest_news_impact: str — impact level of nearest event
        - news_surprise: float — actual-forecast of most recent event (0 if none)
        """
        now = datetime.utcnow()
        events = self.fetch_events(hours_ahead=4, hours_behind=2)
        relevant_currencies = self._symbol_currencies.get(symbol, set())

        relevant = [e for e in events if e["currency"] in relevant_currencies]

        features = {
            "has_news_1h": False,
            "has_high_impact_1h": False,
            "minutes_to_next_news": 999.0,
            "nearest_news_impact_high": 0,
            "nearest_news_impact_medium": 0,
            "news_surprise": 0.0,
        }

        if not relevant:
            return features

        for event in relevant:
            delta_minutes = (event["time"] - now).total_seconds() / 60

            # Within +/-60 minutes
            if abs(delta_minutes) <= 60:
                features["has_news_1h"] = True
                if event["impact"] == "HIGH":
                    features["has_high_impact_1h"] = True

            # Next upcoming event
            if delta_minutes > 0 and delta_minutes < features["minutes_to_next_news"]:
                features["minutes_to_next_news"] = round(delta_minutes, 1)
                features["nearest_news_impact_high"] = 1 if event["impact"] == "HIGH" else 0
                features["nearest_news_impact_medium"] = 1 if event["impact"] == "MEDIUM" else 0

            # Most recent surprise
            if delta_minutes < 0 and event["surprise"] is not None:
                features["news_surprise"] = event["surprise"]

        return features

    def save_events_to_db(self, events: list[dict] = None):
        """Save fetched events to database for ML training data."""
        if events is None:
            events = self.fetch_events()

        if not events:
            return

        session = SessionLocal()
        try:
            saved = 0
            for event in events:
                # Check if already saved (by event_id + time)
                existing = session.query(NewsEvent).filter(
                    NewsEvent.event_id == event["event_id"],
                    NewsEvent.time == event["time"],
                ).first()

                if existing:
                    # Update actual/surprise if new data available
                    if event["actual"] is not None and existing.actual is None:
                        existing.actual = event["actual"]
                        existing.surprise = event["surprise"]
                        saved += 1
                    continue

                news = NewsEvent(
                    event_id=event["event_id"],
                    time=event["time"],
                    country=event.get("country"),
                    currency=event["currency"],
                    event_name=event["event_name"],
                    impact=event["impact"],
                    actual=event.get("actual"),
                    forecast=event.get("forecast"),
                    previous=event.get("previous"),
                    surprise=event.get("surprise"),
                )
                session.add(news)
                saved += 1

            session.commit()
            if saved > 0:
                logger.debug(f"Saved {saved} news events to database")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save news events: {e}")
        finally:
            session.close()


# ── GAP-FID-03 helper: post-hoc news-context lookup ────────────────────────

def _symbol_currencies_for(symbol: str) -> set:
    """Return the set of relevant currencies for a trading symbol.

    Uses the same reverse mapping as NewsFilter._symbol_currencies but as a
    standalone function so callers don't need a NewsFilter instance."""
    currencies = set()
    for currency, syms in CURRENCY_TO_SYMBOLS.items():
        if symbol in syms:
            currencies.add(currency)
    return currencies


def lookup_news_at_time(
    session,
    symbol: str,
    when: datetime,
    *,
    window_hours: float = 1.0,
    min_impact: str = "HIGH",
):
    """Query the persisted news_events table for the highest-impact event
    affecting `symbol` within ±window_hours of `when`.

    GAP-FID-03 helper: the engine's news filter blocks new signals
    correctly but never persists the news context onto closed trades.
    This function looks up that context post-hoc (at trade-close time
    OR during a backfill) so trade_results.news_nearby /
    news_event_name / news_impact get populated for the meta-labeler.

    Args:
        session: SQLAlchemy session against trading.db.
        symbol: e.g. "EURUSD" — relevant currencies are derived via
            CURRENCY_TO_SYMBOLS reverse mapping.
        when: datetime to centre the window on. Typically the trade
            open_time. Must be a naive datetime in UTC.
        window_hours: half-window in hours. Default 1.0 (matches the
            engine's get_nearby_events default).
        min_impact: minimum impact level to count. Default "HIGH"
            matches the live filter's threshold.

    Returns:
        Tuple (news_nearby, news_event_name, news_impact):
          - news_nearby: True if any qualifying event found, False otherwise
          - news_event_name: the closest qualifying event's name, or None
          - news_impact: that event's impact level, or None

        When multiple events match, returns the one closest in time to
        `when` so the meta-labeler sees the most-relevant context."""
    relevant = _symbol_currencies_for(symbol)
    if not relevant:
        return False, None, None

    # Build the impact filter
    if min_impact == "HIGH":
        impact_set = {"HIGH"}
    elif min_impact == "MEDIUM":
        impact_set = {"HIGH", "MEDIUM"}
    else:
        impact_set = {"HIGH", "MEDIUM", "LOW"}

    from_time = when - timedelta(hours=window_hours)
    to_time = when + timedelta(hours=window_hours)

    events = (
        session.query(NewsEvent)
        .filter(NewsEvent.time >= from_time)
        .filter(NewsEvent.time <= to_time)
        .filter(NewsEvent.currency.in_(relevant))
        .filter(NewsEvent.impact.in_(impact_set))
        .all()
    )
    if not events:
        return False, None, None

    # Pick the event closest to `when`
    closest = min(events, key=lambda e: abs((e.time - when).total_seconds()))
    return True, closest.event_name, closest.impact
