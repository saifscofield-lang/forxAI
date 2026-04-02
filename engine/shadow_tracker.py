"""
Shadow Tracker — logs every signal and simulates what would have happened.

Every signal (executed or rejected) is recorded with full market context.
On each scan cycle, open shadow trades are checked against current price
to see if SL/TP would have been hit.

This produces:
  1. ML training data: signal + context + outcome
  2. Filter effectiveness: how many good signals did we block?
  3. Strategy evaluation: true signal quality regardless of filters

Usage:
    tracker = ShadowTracker()
    tracker.log_signal(signal, executed=True, context={...})
    tracker.log_signal(signal, executed=False, rejection_reason="ATR_FILTER", context={...})
    tracker.resolve_open_shadows(adapter)  # call each scan cycle
"""
from datetime import datetime, timezone
from loguru import logger

from storage.database import SessionLocal, ShadowSignal


# Max bars before timeout (if neither SL nor TP hit)
SHADOW_TIMEOUT_BARS = 100


class ShadowTracker:
    """Track all signals as shadow trades for ML training data."""

    def log_signal(
        self,
        signal: dict,
        executed: bool,
        rejection_reason: str = None,
        rejection_detail: str = None,
        context: dict = None,
    ) -> int | None:
        """
        Log a signal to the shadow_signals table.

        Args:
            signal: dict with action, symbol, price, stop_loss, take_profit, strategy, etc.
            executed: True if the signal was actually traded
            rejection_reason: Why it was rejected (ATR_FILTER, REGIME_MISMATCH, CIRCUIT_BREAKER, NEWS, RISK, etc.)
            rejection_detail: Detailed explanation
            context: Market context dict (regime, adx, atr_ratio, bb_width, h4_trend, etc.)

        Returns:
            shadow signal ID or None on error
        """
        ctx = context or {}

        try:
            session = SessionLocal()
            shadow = ShadowSignal(
                time=datetime.now(timezone.utc),
                symbol=signal.get("symbol", ""),
                strategy=signal.get("strategy", ""),
                strategy_version=signal.get("strategy_version", ""),
                action=signal.get("action", ""),
                entry_price=signal.get("price", 0),
                stop_loss=signal.get("stop_loss"),
                take_profit=signal.get("take_profit"),
                atr=signal.get("atr"),
                rsi=signal.get("rsi"),
                reason=signal.get("reason", ""),
                executed=executed,
                rejection_reason=rejection_reason,
                rejection_detail=rejection_detail,
                regime=ctx.get("regime"),
                adx_value=ctx.get("adx_value"),
                atr_ratio=ctx.get("atr_ratio"),
                bb_width=ctx.get("bb_width"),
                h4_trend=ctx.get("h4_trend"),
                spread=ctx.get("spread"),
                volatility_regime=ctx.get("volatility_regime"),
                sim_status="OPEN",
            )
            session.add(shadow)
            session.commit()
            shadow_id = shadow.id
            session.close()

            status = "EXECUTED" if executed else f"SHADOW ({rejection_reason})"
            logger.debug(
                f"[SHADOW] {signal.get('symbol')} {signal.get('action')} "
                f"{signal.get('strategy')} | {status}"
            )
            return shadow_id

        except Exception as e:
            logger.error(f"Shadow tracker log failed: {e}")
            try:
                session.rollback()
                session.close()
            except Exception:
                pass
            return None

    def resolve_open_shadows(self, adapter, pip_values: dict = None):
        """
        Check all OPEN shadow signals against current price.
        If SL or TP would have been hit, mark them resolved.

        Args:
            adapter: MT5Adapter to get current prices
            pip_values: dict of {symbol: pip_value} for pnl calculation
        """
        pip_values = pip_values or {}

        try:
            session = SessionLocal()
            open_shadows = session.query(ShadowSignal).filter(
                ShadowSignal.sim_status == "OPEN"
            ).all()

            if not open_shadows:
                session.close()
                return

            resolved_count = 0
            for shadow in open_shadows:
                try:
                    result = self._check_shadow(shadow, adapter, pip_values)
                    if result:
                        resolved_count += 1
                except Exception as e:
                    logger.debug(f"Shadow resolve error for {shadow.id}: {e}")

            session.commit()
            session.close()

            if resolved_count > 0:
                logger.info(f"[SHADOW] Resolved {resolved_count}/{len(open_shadows)} shadow trades")

        except Exception as e:
            logger.error(f"Shadow resolve failed: {e}")
            try:
                session.rollback()
                session.close()
            except Exception:
                pass

    def _check_shadow(self, shadow: ShadowSignal, adapter, pip_values: dict) -> bool:
        """
        Check if a shadow trade's SL/TP has been hit.
        Returns True if resolved.
        """
        if not shadow.stop_loss or not shadow.take_profit:
            # No SL/TP — timeout after N bars
            age = (datetime.now(timezone.utc) - shadow.time).total_seconds() / 3600
            if age > SHADOW_TIMEOUT_BARS:
                self._resolve_timeout(shadow, adapter, pip_values)
                return True
            return False

        # Get current price
        tick = adapter.get_tick(shadow.symbol) if hasattr(adapter, 'get_tick') else None
        if tick is None:
            # Fallback: get last close from OHLCV
            df = adapter.get_ohlcv(shadow.symbol, "M15", 1)
            if df.empty:
                return False
            current_price = float(df.iloc[-1]["close"])
        else:
            current_price = float(tick.get("bid", tick.get("last", 0)))

        if current_price <= 0:
            return False

        pip_value = pip_values.get(shadow.symbol, 0.0001)
        if "JPY" in shadow.symbol or "XAU" in shadow.symbol:
            pip_value = 0.01

        entry = shadow.entry_price
        sl = shadow.stop_loss
        tp = shadow.take_profit

        # Track max favorable / adverse excursion
        if shadow.action == "BUY":
            favorable_pips = (current_price - entry) / pip_value
            adverse_pips = (entry - current_price) / pip_value if current_price < entry else 0
        else:
            favorable_pips = (entry - current_price) / pip_value
            adverse_pips = (current_price - entry) / pip_value if current_price > entry else 0

        # Update max excursions
        if shadow.sim_max_favorable is None or favorable_pips > shadow.sim_max_favorable:
            shadow.sim_max_favorable = round(favorable_pips, 1)
        if shadow.sim_max_adverse is None or adverse_pips > shadow.sim_max_adverse:
            shadow.sim_max_adverse = round(adverse_pips, 1)

        # Increment bar count
        shadow.sim_duration_bars = (shadow.sim_duration_bars or 0) + 1

        # Check SL hit
        sl_hit = False
        tp_hit = False
        if shadow.action == "BUY":
            sl_hit = current_price <= sl
            tp_hit = current_price >= tp
        else:  # SELL
            sl_hit = current_price >= sl
            tp_hit = current_price <= tp

        now = datetime.now(timezone.utc)

        if tp_hit:
            pnl_pips = abs(tp - entry) / pip_value
            shadow.sim_status = "TP_HIT"
            shadow.sim_exit_price = tp
            shadow.sim_exit_time = now
            shadow.sim_pnl_pips = round(pnl_pips, 1)
            shadow.sim_pnl = round(pnl_pips * pip_value * 100_000 * 0.01, 2)  # ~0.01 lot equivalent
            shadow.sim_exit_reason = "TP_HIT"
            shadow.label = 1  # profitable
            shadow.filter_correct = shadow.executed  # if executed=True and profitable, filter was correct to allow
            return True

        if sl_hit:
            pnl_pips = -abs(sl - entry) / pip_value
            shadow.sim_status = "SL_HIT"
            shadow.sim_exit_price = sl
            shadow.sim_exit_time = now
            shadow.sim_pnl_pips = round(pnl_pips, 1)
            shadow.sim_pnl = round(pnl_pips * pip_value * 100_000 * 0.01, 2)
            shadow.sim_exit_reason = "SL_HIT"
            shadow.label = 0  # loss
            shadow.filter_correct = not shadow.executed  # if NOT executed and would have lost, filter was correct
            return True

        # Timeout check
        if shadow.sim_duration_bars and shadow.sim_duration_bars >= SHADOW_TIMEOUT_BARS:
            self._resolve_timeout(shadow, adapter, pip_values)
            return True

        return False

    def _resolve_timeout(self, shadow: ShadowSignal, adapter, pip_values: dict):
        """Resolve a shadow trade that timed out — use current price."""
        df = adapter.get_ohlcv(shadow.symbol, "M15", 1)
        if not df.empty:
            current_price = float(df.iloc[-1]["close"])
        else:
            current_price = shadow.entry_price  # fallback

        pip_value = pip_values.get(shadow.symbol, 0.0001)
        if "JPY" in shadow.symbol or "XAU" in shadow.symbol:
            pip_value = 0.01

        if shadow.action == "BUY":
            pnl_pips = (current_price - shadow.entry_price) / pip_value
        else:
            pnl_pips = (shadow.entry_price - current_price) / pip_value

        shadow.sim_status = "TIMEOUT"
        shadow.sim_exit_price = current_price
        shadow.sim_exit_time = datetime.now(timezone.utc)
        shadow.sim_pnl_pips = round(pnl_pips, 1)
        shadow.sim_pnl = round(pnl_pips * pip_value * 100_000 * 0.01, 2)
        shadow.sim_exit_reason = "TIMEOUT"
        shadow.label = 1 if pnl_pips > 0 else 0
        shadow.filter_correct = (shadow.executed == (pnl_pips > 0))

    def get_filter_stats(self) -> dict:
        """
        Get statistics on filter effectiveness.
        Returns dict with counts of correct/incorrect filter decisions.
        """
        try:
            session = SessionLocal()

            total = session.query(ShadowSignal).filter(
                ShadowSignal.sim_status != "OPEN"
            ).count()

            executed_wins = session.query(ShadowSignal).filter(
                ShadowSignal.executed == True,
                ShadowSignal.label == 1,
            ).count()

            executed_losses = session.query(ShadowSignal).filter(
                ShadowSignal.executed == True,
                ShadowSignal.label == 0,
            ).count()

            blocked_would_win = session.query(ShadowSignal).filter(
                ShadowSignal.executed == False,
                ShadowSignal.label == 1,
            ).count()

            blocked_would_lose = session.query(ShadowSignal).filter(
                ShadowSignal.executed == False,
                ShadowSignal.label == 0,
            ).count()

            # Per rejection reason
            from sqlalchemy import func
            reason_stats = session.query(
                ShadowSignal.rejection_reason,
                func.count(ShadowSignal.id),
                func.sum(ShadowSignal.label),
            ).filter(
                ShadowSignal.executed == False,
                ShadowSignal.sim_status != "OPEN",
            ).group_by(ShadowSignal.rejection_reason).all()

            session.close()

            filter_accuracy = 0
            if (blocked_would_lose + blocked_would_win) > 0:
                filter_accuracy = blocked_would_lose / (blocked_would_lose + blocked_would_win) * 100

            return {
                "total_resolved": total,
                "executed_wins": executed_wins,
                "executed_losses": executed_losses,
                "blocked_would_win": blocked_would_win,
                "blocked_would_lose": blocked_would_lose,
                "filter_accuracy": round(filter_accuracy, 1),
                "missed_profit_signals": blocked_would_win,
                "correctly_blocked": blocked_would_lose,
                "per_filter": {
                    r[0]: {"total": r[1], "would_win": r[2] or 0}
                    for r in reason_stats
                },
            }

        except Exception as e:
            logger.error(f"Shadow stats failed: {e}")
            return {}
