"""
Vectorized fast backtester for parameter optimization.
Runs entirely on numpy arrays — no pandas overhead per bar.
"""
import numpy as np
from dataclasses import dataclass


@dataclass
class FastResult:
    """Lightweight backtest result for optimization."""
    total_pnl: float
    total_trades: int
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float
    sharpe_ratio: float
    final_balance: float


def fast_backtest(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    times: np.ndarray,
    sma_fast: np.ndarray,
    sma_slow: np.ndarray,
    rsi: np.ndarray,
    atr: np.ndarray,
    atr_sl_mult: float = 1.5,
    atr_tp_mult: float = 2.0,
    pip_value: float = 0.0001,
    spread_pips: float = 1.0,
    risk_per_trade: float = 0.01,
    initial_balance: float = 100_000.0,
    warmup: int = 60,
) -> FastResult:
    """
    Pure-numpy backtest loop. No pandas, no dataclass per trade.
    Returns aggregated metrics only.
    """
    balance = initial_balance
    n = len(close)

    # Trade state
    in_trade = False
    trade_action = 0   # 1=BUY, -1=SELL
    entry_price = 0.0
    stop_loss = 0.0
    take_profit = 0.0
    lot_size = 0.0

    # Tracking
    pnls = []
    equity_peak = initial_balance
    max_dd = 0.0
    equity_history = []

    pip_value_per_lot = pip_value * 100_000
    spread_cost = spread_pips * pip_value

    for i in range(warmup, n):
        # Check exits
        if in_trade:
            hit_sl = False
            hit_tp = False

            if trade_action == 1:  # BUY
                if low[i] <= stop_loss:
                    hit_sl = True
                if high[i] >= take_profit:
                    hit_tp = True
            else:  # SELL
                if high[i] >= stop_loss:
                    hit_sl = True
                if low[i] <= take_profit:
                    hit_tp = True

            exit_price = 0.0
            if hit_sl:
                exit_price = stop_loss
            elif hit_tp:
                exit_price = take_profit

            if exit_price > 0:
                if trade_action == 1:
                    pnl_pips = (exit_price - entry_price) / pip_value
                else:
                    pnl_pips = (entry_price - exit_price) / pip_value

                pnl = pnl_pips * pip_value_per_lot * lot_size
                balance += pnl
                pnls.append(pnl)
                in_trade = False

        # Check for new signal
        if not in_trade and i >= 1:
            if (np.isnan(sma_fast[i]) or np.isnan(sma_fast[i-1]) or
                np.isnan(sma_slow[i]) or np.isnan(sma_slow[i-1]) or
                np.isnan(rsi[i]) or np.isnan(atr[i]) or atr[i] <= 0):
                pass
            else:
                signal = 0
                # BUY crossover
                if sma_fast[i-1] <= sma_slow[i-1] and sma_fast[i] > sma_slow[i]:
                    if rsi[i] < 70:
                        signal = 1
                # SELL crossover
                elif sma_fast[i-1] >= sma_slow[i-1] and sma_fast[i] < sma_slow[i]:
                    if rsi[i] > 30:
                        signal = -1

                if signal != 0:
                    price = close[i]
                    curr_atr = atr[i]

                    if signal == 1:
                        entry_price = price + spread_cost
                        stop_loss = price - curr_atr * atr_sl_mult
                        take_profit = price + curr_atr * atr_tp_mult
                    else:
                        entry_price = price - spread_cost
                        stop_loss = price + curr_atr * atr_sl_mult
                        take_profit = price - curr_atr * atr_tp_mult

                    sl_pips = abs(entry_price - stop_loss) / pip_value
                    if sl_pips > 0 and balance > 0:
                        risk_amount = balance * risk_per_trade
                        lot_size = risk_amount / (sl_pips * pip_value_per_lot)
                        lot_size = max(0.01, round(lot_size, 2))
                        lot_size = min(lot_size, 10.0)
                        trade_action = signal
                        in_trade = True

        # Track equity
        equity = balance
        if in_trade:
            if trade_action == 1:
                unrealized = (close[i] - entry_price) / pip_value * pip_value_per_lot * lot_size
            else:
                unrealized = (entry_price - close[i]) / pip_value * pip_value_per_lot * lot_size
            equity += unrealized

        equity_history.append(equity)
        if equity > equity_peak:
            equity_peak = equity
        dd = (equity_peak - equity) / equity_peak * 100 if equity_peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    # Close remaining trade at last close
    if in_trade:
        if trade_action == 1:
            pnl_pips = (close[-1] - entry_price) / pip_value
        else:
            pnl_pips = (entry_price - close[-1]) / pip_value
        pnl = pnl_pips * pip_value_per_lot * lot_size
        balance += pnl
        pnls.append(pnl)

    # Compute metrics
    total_trades = len(pnls)
    if total_trades == 0:
        return FastResult(0, 0, 0, 0, 0, 0, initial_balance)

    pnls_arr = np.array(pnls)
    wins = pnls_arr[pnls_arr > 0]
    losses = pnls_arr[pnls_arr <= 0]

    win_rate = len(wins) / total_trades * 100
    gross_profit = wins.sum() if len(wins) > 0 else 0
    gross_loss = abs(losses.sum()) if len(losses) > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    total_pnl = balance - initial_balance

    # Sharpe from equity history
    eq_arr = np.array(equity_history)
    if len(eq_arr) > 1:
        returns = np.diff(eq_arr) / eq_arr[:-1]
        returns = returns[~np.isnan(returns) & ~np.isinf(returns)]
        if len(returns) > 0 and returns.std() > 0:
            sharpe = returns.mean() / returns.std() * np.sqrt(252 * 24)
        else:
            sharpe = 0.0
    else:
        sharpe = 0.0

    return FastResult(
        total_pnl=round(total_pnl, 2),
        total_trades=total_trades,
        win_rate=round(win_rate, 1),
        profit_factor=round(profit_factor, 3),
        max_drawdown_pct=round(max_dd, 2),
        sharpe_ratio=round(sharpe, 3),
        final_balance=round(balance, 2),
    )
