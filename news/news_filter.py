"""
فلتر الأخبار الاقتصادية — News Filter
يستخدم تقويم MT5 الاقتصادي المدمج لمنع التداول وقت الأخبار عالية التأثير.
يخزن الأحداث في قاعدة البيانات لتدريب ML.

المستوى 1: منع التداول 30 دقيقة قبل/بعد أخبار HIGH impact
المستوى 2: إضافة features للـ ML (حدث قريب، مستوى التأثير، المفاجأة)
"""
import MetaTrader5 as mt5
from datetime import datetime, timedelta
from loguru import logger
from storage.database import SessionLocal, NewsEvent


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

# ── خريطة أهمية الحدث من MT5 ──
# MT5 calendar importance: 0=None, 1=Low, 2=Medium, 3=High
IMPORTANCE_MAP = {
    0: "NONE",
    1: "LOW",
    2: "MEDIUM",
    3: "HIGH",
}


class NewsFilter:
    """فلتر الأخبار الاقتصادية باستخدام تقويم MT5."""

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

        # Build reverse map: symbol → relevant currencies
        self._symbol_currencies = {}
        for symbol in self.symbols:
            currencies = set()
            for currency, syms in CURRENCY_TO_SYMBOLS.items():
                if symbol in syms:
                    currencies.add(currency)
            self._symbol_currencies[symbol] = currencies

    def fetch_events(self, hours_ahead: int = 4, hours_behind: int = 1) -> list[dict]:
        """
        Fetch economic calendar events from MT5.

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
            return self._cached_events

        from_time = now - timedelta(hours=hours_behind)
        to_time = now + timedelta(hours=hours_ahead)

        events = []
        try:
            # MT5 calendar_value_history returns upcoming/recent economic events
            cal_values = mt5.calendar_value_history(
                int(from_time.timestamp()),
                int(to_time.timestamp()),
            )

            if cal_values is None or len(cal_values) == 0:
                logger.debug("No calendar events found in range")
                self._cached_events = []
                self._cache_time = now
                return []

            for val in cal_values:
                # Get event details
                try:
                    event_info = mt5.calendar_event_get(val.event_id)
                    if not event_info:
                        continue
                    event = event_info[0] if isinstance(event_info, (list, tuple)) else event_info

                    country_info = mt5.calendar_country_get(event.country_id)
                    if not country_info:
                        continue
                    country = country_info[0] if isinstance(country_info, (list, tuple)) else country_info

                    importance = IMPORTANCE_MAP.get(event.importance, "NONE")
                    if importance == "NONE":
                        continue

                    # actual/forecast/previous: MT5 returns as integers, divide by 10^digits
                    divisor = 10 ** event.digits if event.digits > 0 else 1
                    actual_val = val.actual_value / divisor if val.actual_value != -2147483648 else None
                    forecast_val = val.forecast_value / divisor if val.forecast_value != -2147483648 else None
                    previous_val = val.previous_value / divisor if val.previous_value != -2147483648 else None

                    surprise = None
                    if actual_val is not None and forecast_val is not None:
                        surprise = actual_val - forecast_val

                    event_time = datetime.utcfromtimestamp(val.time)

                    event_dict = {
                        "event_id": val.event_id,
                        "time": event_time,
                        "country": country.code,
                        "currency": country.currency,
                        "event_name": event.name,
                        "impact": importance,
                        "actual": actual_val,
                        "forecast": forecast_val,
                        "previous": previous_val,
                        "surprise": surprise,
                    }
                    events.append(event_dict)

                except Exception as e:
                    logger.debug(f"Error parsing calendar event {val.event_id}: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Failed to fetch calendar events: {e}")
            # Return empty — don't block trading if calendar unavailable
            self._cached_events = []
            self._cache_time = now
            return []

        self._cached_events = events
        self._cache_time = now

        high_count = sum(1 for e in events if e["impact"] == "HIGH")
        logger.info(f"Calendar: {len(events)} events fetched ({high_count} HIGH impact)")

        return events

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
        - has_news_1h: bool — any news within ±1 hour
        - has_high_impact_1h: bool — HIGH impact news within ±1 hour
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

            # Within ±60 minutes
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
