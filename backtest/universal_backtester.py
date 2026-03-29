"""
Universal Backtester — يعمل مع أي استراتيجية تملك generate_signal()
لا يعتمد على SMA أو أي مؤشر معين — يمرر DataFrame للاستراتيجية وتقرر هي.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger


@dataclass
class BacktestTrade:
    id: int
    symbol: str
    action: str
    entry_price: float
    entry_time: datetime
    stop_loss: float
    take_profit: float
    lot_size: float
    strategy: str
    strategy_version: str = ""
    exit_price: float = 0.0
    exit_time: datetime = None
    exit_reason: str = ""
    pnl: float = 0.0
    pnl_pips: float = 0.0
    rr_planned: float = 0.0
    rr_actual: float = 0.0
    duration_minutes: int = 0


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    strategy: str
    strategy_version: str
    start_date: datetime
    end_date: datetime
    initial_balance: float
    final_balance: float
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)


class UniversalBacktester:
    """
    Bar-by-bar backtester that calls strategy.generate_signal(df_slice)
    exactly like the live engine does. Works with ANY strategy.
    """

    def __init__(
        self,
        strategy,
        initial_balance: float = 100_000.0,
        risk_per_trade: float = 0.01,
        max_open_positions: int = 1,
        pip_value: float = 0.0001,
        spread_pips: float = 1.5,
    ):
        self.strategy = strategy
        self.initial_balance = initial_balance
        self.risk_per_trade = risk_per_trade
        self.max_open_positions = max_open_positions
        self.pip_value = pip_value
        self.spread_pips = spread_pips

    def run(self, df: pd.DataFrame, warmup: int = 250) -> BacktestResult:
        """
        Run backtest bar-by-bar.
        At each bar i, passes df[0:i+1] to strategy.generate_signal().
        """
        df = df.reset_index(drop=True)
        symbol = getattr(self.strategy, 'symbol', 'UNKNOWN')
        strategy_name = getattr(self.strategy, 'name', 'unknown')
        strategy_version = getattr(self.strategy, 'VERSION', '?')
        timeframe = df["timeframe"].iloc[0] if "timeframe" in df.columns else "H1"

        logger.info(
            f"Backtest | {symbol} {timeframe} | {strategy_name} v{strategy_version} | "
            f"{len(df)} bars | warmup={warmup}"
        )

        # State
        balance = self.initial_balance
        open_trades: list[BacktestTrade] = []
        closed_trades: list[BacktestTrade] = []
        equity_curve = []
        trade_counter = 0

        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        times = df["time"].values

        for i in range(warmup, len(df)):
            # 1. Check SL/TP exits
            for trade in list(open_trades):
                hit_sl = hit_tp = False
                if trade.action == "BUY":
                    if lows[i] <= trade.stop_loss:
                        hit_sl = True
                    if highs[i] >= trade.take_profit:
                        hit_tp = True
                else:
                    if highs[i] >= trade.stop_loss:
                        hit_sl = True
                    if lows[i] <= trade.take_profit:
                        hit_tp = True

                if hit_sl:
                    trade.exit_price = trade.stop_loss
                    trade.exit_time = pd.Timestamp(times[i])
                    trade.exit_reason = "SL_HIT"
                    self._calc_pnl(trade)
                    balance += trade.pnl
                    open_trades.remove(trade)
                    closed_trades.append(trade)
                elif hit_tp:
                    trade.exit_price = trade.take_profit
                    trade.exit_time = pd.Timestamp(times[i])
                    trade.exit_reason = "TP_HIT"
                    self._calc_pnl(trade)
                    balance += trade.pnl
                    open_trades.remove(trade)
                    closed_trades.append(trade)

            # 2. Generate signal (pass slice like live engine)
            if len(open_trades) < self.max_open_positions:
                df_slice = df.iloc[:i + 1].copy()
                try:
                    signal = self.strategy.generate_signal(df_slice)
                except Exception:
                    signal = None

                if signal and signal.get("action") in ("BUY", "SELL"):
                    price = signal["price"]
                    sl = signal["stop_loss"]
                    tp = signal["take_profit"]

                    # Spread
                    if signal["action"] == "BUY":
                        price += self.spread_pips * self.pip_value
                    else:
                        price -= self.spread_pips * self.pip_value

                    # Position sizing
                    sl_distance = abs(price - sl)
                    if sl_distance <= 0:
                        continue
                    sl_pips = sl_distance / self.pip_value
                    risk_amount = balance * self.risk_per_trade
                    pip_value_per_lot = self.pip_value * 100_000
                    lot_size = risk_amount / (sl_pips * pip_value_per_lot)
                    lot_size = max(0.01, min(round(lot_size, 2), 10.0))

                    # R:R
                    risk = abs(price - sl)
                    reward = abs(tp - price)
                    rr_planned = round(reward / risk, 2) if risk > 0 else 0

                    trade_counter += 1
                    trade = BacktestTrade(
                        id=trade_counter,
                        symbol=symbol,
                        action=signal["action"],
                        entry_price=round(price, 5),
                        entry_time=pd.Timestamp(times[i]),
                        stop_loss=sl,
                        take_profit=tp,
                        lot_size=lot_size,
                        strategy=strategy_name,
                        strategy_version=strategy_version,
                        rr_planned=rr_planned,
                    )
                    open_trades.append(trade)

            # 3. Equity curve (sample every 5 bars)
            if i % 5 == 0 or i == len(df) - 1:
                unrealized = sum(
                    ((closes[i] - t.entry_price) if t.action == "BUY" else (t.entry_price - closes[i]))
                    / self.pip_value * self.pip_value * 100_000 * t.lot_size
                    for t in open_trades
                )
                equity_curve.append({
                    "time": times[i],
                    "balance": balance,
                    "equity": balance + unrealized,
                    "open_trades": len(open_trades),
                })

        # Close remaining at last price
        for trade in list(open_trades):
            trade.exit_price = closes[-1]
            trade.exit_time = pd.Timestamp(times[-1])
            trade.exit_reason = "END"
            self._calc_pnl(trade)
            balance += trade.pnl
            closed_trades.append(trade)

        logger.info(
            f"Done | {len(closed_trades)} trades | "
            f"P&L: ${balance - self.initial_balance:+,.2f}"
        )

        return BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            strategy=strategy_name,
            strategy_version=strategy_version,
            start_date=pd.Timestamp(times[warmup]),
            end_date=pd.Timestamp(times[-1]),
            initial_balance=self.initial_balance,
            final_balance=balance,
            trades=closed_trades,
            equity_curve=equity_curve,
        )

    def _calc_pnl(self, trade: BacktestTrade):
        if trade.action == "BUY":
            pnl_pips = (trade.exit_price - trade.entry_price) / self.pip_value
        else:
            pnl_pips = (trade.entry_price - trade.exit_price) / self.pip_value

        trade.pnl_pips = round(pnl_pips, 1)
        trade.pnl = round(pnl_pips * self.pip_value * 100_000 * trade.lot_size, 2)

        # Duration
        if trade.entry_time and trade.exit_time:
            trade.duration_minutes = int((trade.exit_time - trade.entry_time).total_seconds() / 60)

        # Actual R:R
        risk = abs(trade.entry_price - trade.stop_loss)
        if risk > 0:
            if trade.action == "BUY":
                actual_move = trade.exit_price - trade.entry_price
            else:
                actual_move = trade.entry_price - trade.exit_price
            trade.rr_actual = round(actual_move / risk, 2)
