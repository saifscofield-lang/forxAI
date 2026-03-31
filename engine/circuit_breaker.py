"""
Circuit Breaker — Auto-freeze strategies that show danger signs.
Triggers:
  1. CONSECUTIVE_LOSSES: 5+ losses in a row
  2. NEGATIVE_EV: Expected value negative on last 20 trades
  3. MAX_DRAWDOWN: Strategy drawdown > configured threshold

Usage:
    cb = CircuitBreaker()
    frozen, reason = cb.check_strategy("sma_crossover", "EURUSD", recent_trades)
    if frozen:
        logger.warning(f"Strategy frozen: {reason}")
"""
import sqlite3
from datetime import datetime, timezone
from loguru import logger


# Default thresholds
DEFAULT_MAX_CONSECUTIVE_LOSSES = 5
DEFAULT_EV_LOOKBACK = 20
DEFAULT_MAX_STRATEGY_DD_PCT = 3.0


class CircuitBreaker:
    """Monitor strategies and auto-freeze when danger thresholds are breached."""

    def __init__(
        self,
        max_consecutive_losses: int = DEFAULT_MAX_CONSECUTIVE_LOSSES,
        ev_lookback: int = DEFAULT_EV_LOOKBACK,
        max_strategy_dd_pct: float = DEFAULT_MAX_STRATEGY_DD_PCT,
        db_path: str = "data/trading.db",
    ):
        self.max_consecutive_losses = max_consecutive_losses
        self.ev_lookback = ev_lookback
        self.max_strategy_dd_pct = max_strategy_dd_pct
        self.db_path = db_path
        self._frozen = {}  # {(strategy, symbol): reason}

    def check_strategy(
        self,
        strategy_name: str,
        symbol: str,
        recent_trades: list = None,
    ) -> tuple:
        """
        Check if a strategy should be frozen.

        Args:
            strategy_name: Strategy name
            symbol: Trading symbol
            recent_trades: List of dicts with at least {pnl: float}
                          If None, reads from database.

        Returns:
            (is_frozen: bool, reason: str or None)
        """
        key = (strategy_name, symbol)

        if recent_trades is None:
            recent_trades = self._load_recent_trades(strategy_name, symbol)

        if not recent_trades:
            return False, None

        # Check 1: Consecutive losses
        frozen, reason = self._check_consecutive_losses(recent_trades)
        if frozen:
            self._freeze(key, "CONSECUTIVE_LOSSES", reason)
            return True, reason

        # Check 2: Negative EV on last N trades
        frozen, reason = self._check_negative_ev(recent_trades)
        if frozen:
            self._freeze(key, "NEGATIVE_EV", reason)
            return True, reason

        # Check 3: Strategy drawdown
        frozen, reason = self._check_drawdown(recent_trades)
        if frozen:
            self._freeze(key, "MAX_DRAWDOWN", reason)
            return True, reason

        # All clear — unfreeze if was previously frozen
        if key in self._frozen:
            self._unfreeze(key)

        return False, None

    def is_frozen(self, strategy_name: str, symbol: str) -> bool:
        """Check if a strategy is currently frozen."""
        return (strategy_name, symbol) in self._frozen

    def get_frozen_strategies(self) -> dict:
        """Return all frozen strategies and their reasons."""
        return dict(self._frozen)

    def force_unfreeze(self, strategy_name: str, symbol: str):
        """Manually unfreeze a strategy."""
        key = (strategy_name, symbol)
        if key in self._frozen:
            self._unfreeze(key)

    def _check_consecutive_losses(self, trades: list) -> tuple:
        """Check for N consecutive losses."""
        consecutive = 0
        for t in reversed(trades):
            pnl = t.get("pnl", t.get("profit", 0))
            if pnl < 0:
                consecutive += 1
            else:
                break

        if consecutive >= self.max_consecutive_losses:
            reason = f"{consecutive} consecutive losses (threshold: {self.max_consecutive_losses})"
            return True, reason
        return False, None

    def _check_negative_ev(self, trades: list) -> tuple:
        """Check if EV is negative on last N trades."""
        recent = trades[-self.ev_lookback:]
        if len(recent) < self.ev_lookback:
            return False, None  # Not enough data

        total_pnl = sum(t.get("pnl", t.get("profit", 0)) for t in recent)
        avg_pnl = total_pnl / len(recent)

        if avg_pnl < 0:
            reason = f"Negative EV on last {len(recent)} trades (avg P&L: ${avg_pnl:.2f})"
            return True, reason
        return False, None

    def _check_drawdown(self, trades: list) -> tuple:
        """Check if strategy drawdown exceeds threshold."""
        if len(trades) < 5:
            return False, None

        cumulative = []
        running = 0
        for t in trades:
            running += t.get("pnl", t.get("profit", 0))
            cumulative.append(running)

        peak = cumulative[0]
        max_dd = 0
        for val in cumulative:
            if val > peak:
                peak = val
            dd = peak - val
            if dd > max_dd:
                max_dd = dd

        # Calculate dd as percentage of peak (or initial balance proxy)
        balance_proxy = max(abs(peak), 1000)  # avoid division by zero
        dd_pct = (max_dd / balance_proxy) * 100

        if dd_pct > self.max_strategy_dd_pct:
            reason = f"Strategy drawdown {dd_pct:.1f}% exceeds {self.max_strategy_dd_pct}% threshold"
            return True, reason
        return False, None

    def _freeze(self, key: tuple, trigger_type: str, reason: str):
        """Freeze a strategy and log it."""
        strategy_name, symbol = key
        self._frozen[key] = reason
        logger.warning(f"CIRCUIT BREAKER: Freezing {strategy_name}/{symbol} — {reason}")
        self._log_event(strategy_name, symbol, trigger_type, reason, "FREEZE")

    def _unfreeze(self, key: tuple):
        """Unfreeze a strategy and log it."""
        strategy_name, symbol = key
        del self._frozen[key]
        logger.info(f"CIRCUIT BREAKER: Unfreezing {strategy_name}/{symbol}")
        self._log_event(strategy_name, symbol, "RECOVERY", "Thresholds cleared", "UNFREEZE")

    def _log_event(self, strategy_name: str, symbol: str, trigger_type: str, trigger_value: str, action: str):
        """Log circuit breaker event to database."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS circuit_breaker_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    trigger_type TEXT,
                    trigger_value TEXT,
                    action TEXT,
                    details TEXT
                )
            """)
            conn.execute(
                "INSERT INTO circuit_breaker_logs (time, strategy_name, symbol, trigger_type, trigger_value, action) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                 strategy_name, symbol, trigger_type, trigger_value, action)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Circuit breaker log failed: {e}")

    def _load_recent_trades(self, strategy_name: str, symbol: str) -> list:
        """Load recent trades from database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "SELECT profit FROM trades WHERE strategy = ? AND symbol = ? AND is_closed = 1 "
                "ORDER BY close_time DESC LIMIT ?",
                (strategy_name, symbol, self.ev_lookback * 2)
            )
            rows = cursor.fetchall()
            conn.close()
            # Reverse to get chronological order
            return [{"pnl": r[0]} for r in reversed(rows)]
        except Exception:
            return []
