"""
محرك الباك تست — Backtesting Engine
Replay historical bars through a strategy and simulate trade execution.
Optimized: indicators computed once upfront, crossover detection vectorized.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger


@dataclass
class BacktestTrade:
    """A single backtest trade record."""
    id: int
    symbol: str
    action: str            # BUY or SELL
    entry_price: float
    entry_time: datetime
    stop_loss: float
    take_profit: float
    lot_size: float
    strategy: str
    exit_price: float = 0.0
    exit_time: datetime = None
    exit_reason: str = ""  # sl, tp, signal, end
    pnl: float = 0.0
    pnl_pips: float = 0.0


@dataclass
class BacktestResult:
    """Container for backtest output."""
    symbol: str
    timeframe: str
    strategy: str
    start_date: datetime
    end_date: datetime
    initial_balance: float
    final_balance: float
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)


class Backtester:
    """
    Bar-by-bar backtesting engine.

    Computes indicators once upfront, then scans for signals bar-by-bar.
    Simulates entries/exits with SL/TP, and tracks equity over time.
    """

    def __init__(
        self,
        strategy,
        initial_balance: float = 100_000.0,
        risk_per_trade: float = 0.01,
        max_open_positions: int = 5,
        commission_per_lot: float = 0.0,
        pip_value: float = 0.0001,
        spread_pips: float = 1.0,
    ):
        self.strategy = strategy
        self.initial_balance = initial_balance
        self.risk_per_trade = risk_per_trade
        self.max_open_positions = max_open_positions
        self.commission_per_lot = commission_per_lot
        self.pip_value = pip_value
        self.spread_pips = spread_pips

        # State
        self.balance = initial_balance
        self.open_trades: list[BacktestTrade] = []
        self.closed_trades: list[BacktestTrade] = []
        self.equity_curve: list[dict] = []
        self._trade_counter = 0

    def run(
        self,
        df: pd.DataFrame,
        warmup: int = 60,
    ) -> BacktestResult:
        """
        Run backtest on a DataFrame of OHLCV bars.

        Args:
            df: DataFrame with columns [time, open, high, low, close, volume].
                Must be sorted by time ascending.
            warmup: Minimum bars before generating signals (for indicators).

        Returns:
            BacktestResult with trades and equity curve.
        """
        df = df.reset_index(drop=True)
        symbol = df["symbol"].iloc[0] if "symbol" in df.columns else "UNKNOWN"
        timeframe = df["timeframe"].iloc[0] if "timeframe" in df.columns else "H1"

        logger.info(
            f"Backtest starting | {symbol} {timeframe} | "
            f"{len(df)} bars | {df['time'].iloc[0]} -> {df['time'].iloc[-1]}"
        )

        # Reset state
        self.balance = self.initial_balance
        self.open_trades = []
        self.closed_trades = []
        self.equity_curve = []
        self._trade_counter = 0

        # Compute indicators ONCE upfront
        prepared = self.strategy.prepare(df.copy())

        # Pre-extract numpy arrays for fast access
        times = prepared["time"].values
        opens = prepared["open"].values
        highs = prepared["high"].values
        lows = prepared["low"].values
        closes = prepared["close"].values

        # Get indicator column names from strategy
        fast_col = f"sma_{self.strategy.fast_period}"
        slow_col = f"sma_{self.strategy.slow_period}"
        rsi_col = f"rsi_{self.strategy.rsi_period}"
        atr_col = f"atr_{self.strategy.atr_period}"

        sma_fast = prepared[fast_col].values
        sma_slow = prepared[slow_col].values
        rsi = prepared[rsi_col].values
        atr = prepared[atr_col].values

        # Bar-by-bar simulation
        for i in range(warmup, len(df)):
            # 1. Check SL/TP hits on current bar
            self._check_exits_fast(highs[i], lows[i], times[i])

            # 2. Generate signal (vectorized crossover check)
            if len(self.open_trades) < self.max_open_positions:
                if not np.isnan(sma_fast[i]) and not np.isnan(sma_fast[i - 1]):
                    signal = self._check_crossover(
                        sma_fast[i - 1], sma_slow[i - 1],
                        sma_fast[i], sma_slow[i],
                        rsi[i], atr[i], closes[i], symbol,
                    )
                    if signal:
                        self._open_trade(signal, times[i])

            # 3. Record equity (sample every 10 bars to reduce memory)
            if i % 10 == 0 or i == len(df) - 1:
                unrealized = self._calc_unrealized_fast(closes[i])
                self.equity_curve.append({
                    "time": times[i],
                    "balance": self.balance,
                    "equity": self.balance + unrealized,
                    "open_trades": len(self.open_trades),
                    "closed_trades": len(self.closed_trades),
                })

        # Close remaining open trades at last bar's close
        if self.open_trades:
            for trade in list(self.open_trades):
                self._close_trade(trade, closes[-1], times[-1], "end")

        result = BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            strategy=self.strategy.name,
            start_date=pd.Timestamp(times[warmup]),
            end_date=pd.Timestamp(times[-1]),
            initial_balance=self.initial_balance,
            final_balance=self.balance,
            trades=self.closed_trades,
            equity_curve=self.equity_curve,
        )

        logger.info(
            f"Backtest complete | {len(self.closed_trades)} trades | "
            f"P&L: ${self.balance - self.initial_balance:+,.2f}"
        )
        return result

    def _check_crossover(
        self,
        prev_fast: float, prev_slow: float,
        curr_fast: float, curr_slow: float,
        curr_rsi: float, curr_atr: float,
        price: float, symbol: str,
    ) -> dict | None:
        """Check for SMA crossover signal using pre-computed indicators."""
        if np.isnan(curr_rsi) or np.isnan(curr_atr) or curr_atr <= 0:
            return None

        # BUY: fast crosses above slow
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            if curr_rsi < 70:
                sl = price - curr_atr * self.strategy.atr_sl_multiplier
                tp = price + curr_atr * self.strategy.atr_tp_multiplier
                return {
                    "action": "BUY",
                    "symbol": symbol,
                    "price": price,
                    "stop_loss": round(sl, 5),
                    "take_profit": round(tp, 5),
                    "strategy": self.strategy.name,
                }

        # SELL: fast crosses below slow
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            if curr_rsi > 30:
                sl = price + curr_atr * self.strategy.atr_sl_multiplier
                tp = price - curr_atr * self.strategy.atr_tp_multiplier
                return {
                    "action": "SELL",
                    "symbol": symbol,
                    "price": price,
                    "stop_loss": round(sl, 5),
                    "take_profit": round(tp, 5),
                    "strategy": self.strategy.name,
                }

        return None

    def _open_trade(self, signal: dict, time):
        """Open a new trade from a signal."""
        entry_price = signal["price"]
        sl = signal["stop_loss"]
        tp = signal["take_profit"]
        action = signal["action"]

        # Apply spread cost
        if action == "BUY":
            entry_price += self.spread_pips * self.pip_value
        else:
            entry_price -= self.spread_pips * self.pip_value

        # Position sizing: risk-based
        sl_pips = abs(entry_price - sl) / self.pip_value
        if sl_pips <= 0:
            return

        risk_amount = self.balance * self.risk_per_trade
        pip_value_per_lot = self.pip_value * 100_000
        lot_size = risk_amount / (sl_pips * pip_value_per_lot)
        lot_size = max(0.01, round(lot_size, 2))
        lot_size = min(lot_size, 10.0)

        # Commission
        self.balance -= self.commission_per_lot * lot_size

        self._trade_counter += 1
        trade = BacktestTrade(
            id=self._trade_counter,
            symbol=signal["symbol"],
            action=action,
            entry_price=round(entry_price, 5),
            entry_time=pd.Timestamp(time),
            stop_loss=sl,
            take_profit=tp,
            lot_size=lot_size,
            strategy=signal["strategy"],
        )
        self.open_trades.append(trade)

    def _check_exits_fast(self, high: float, low: float, time):
        """Check if current bar's high/low triggers SL or TP."""
        for trade in list(self.open_trades):
            hit_sl = False
            hit_tp = False

            if trade.action == "BUY":
                if low <= trade.stop_loss:
                    hit_sl = True
                if high >= trade.take_profit:
                    hit_tp = True
            else:
                if high >= trade.stop_loss:
                    hit_sl = True
                if low <= trade.take_profit:
                    hit_tp = True

            # If both hit on same bar, assume SL first (conservative)
            if hit_sl:
                self._close_trade(trade, trade.stop_loss, time, "sl")
            elif hit_tp:
                self._close_trade(trade, trade.take_profit, time, "tp")

    def _close_trade(self, trade: BacktestTrade, exit_price: float, exit_time, reason: str):
        """Close a trade and update balance."""
        trade.exit_price = round(exit_price, 5)
        trade.exit_time = pd.Timestamp(exit_time)
        trade.exit_reason = reason

        if trade.action == "BUY":
            pnl_pips = (exit_price - trade.entry_price) / self.pip_value
        else:
            pnl_pips = (trade.entry_price - exit_price) / self.pip_value

        trade.pnl_pips = round(pnl_pips, 1)
        trade.pnl = round(pnl_pips * self.pip_value * 100_000 * trade.lot_size, 2)

        self.balance += trade.pnl
        self.open_trades.remove(trade)
        self.closed_trades.append(trade)

    def _calc_unrealized_fast(self, price: float) -> float:
        """Calculate unrealized P&L for open trades."""
        total = 0.0
        for trade in self.open_trades:
            if trade.action == "BUY":
                pips = (price - trade.entry_price) / self.pip_value
            else:
                pips = (trade.entry_price - price) / self.pip_value
            total += pips * self.pip_value * 100_000 * trade.lot_size
        return total
