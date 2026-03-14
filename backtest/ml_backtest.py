"""
ML-Enhanced Backtester.
Uses ML model predictions to filter/replace SMA crossover signals.
Pure-numpy for speed, compatible with walk-forward validation.
"""
import numpy as np
from dataclasses import dataclass


@dataclass
class MLBacktestResult:
    """ML backtest result with extended metrics."""
    total_pnl: float
    total_trades: int
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float
    sharpe_ratio: float
    final_balance: float
    avg_confidence: float
    signals_filtered: int


def ml_backtest(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    times: np.ndarray,
    predictions: np.ndarray,
    probabilities: np.ndarray,
    atr: np.ndarray,
    atr_sl_mult: float = 1.5,
    atr_tp_mult: float = 2.5,
    confidence_threshold: float = 0.40,
    pip_value: float = 0.0001,
    spread_pips: float = 1.0,
    risk_per_trade: float = 0.01,
    initial_balance: float = 100_000.0,
    warmup: int = 0,
) -> MLBacktestResult:
    """
    Backtest using ML model predictions directly.

    Parameters
    ----------
    predictions : array of -1 (SELL), 0 (HOLD), 1 (BUY)
    probabilities : array of max class probability (confidence)
    atr : ATR values for SL/TP calculation
    confidence_threshold : minimum probability to take a trade
    """
    balance = initial_balance
    n = len(close)

    in_trade = False
    trade_action = 0
    entry_price = 0.0
    stop_loss = 0.0
    take_profit = 0.0
    lot_size = 0.0

    pnls = []
    equity_peak = initial_balance
    max_dd = 0.0
    equity_history = []
    confidences = []
    signals_filtered = 0

    pip_value_per_lot = pip_value * 100_000
    spread_cost = spread_pips * pip_value

    for i in range(warmup, n):
        # Check exits
        if in_trade:
            hit_sl = False
            hit_tp = False

            if trade_action == 1:
                if low[i] <= stop_loss:
                    hit_sl = True
                if high[i] >= take_profit:
                    hit_tp = True
            else:
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

        # Check ML signal
        if not in_trade and i < len(predictions):
            signal = int(predictions[i])
            confidence = probabilities[i] if i < len(probabilities) else 0

            if signal != 0 and not np.isnan(atr[i]) and atr[i] > 0:
                if confidence >= confidence_threshold:
                    price = close[i]
                    curr_atr = atr[i]
                    confidences.append(confidence)

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
                else:
                    signals_filtered += 1

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

    # Close remaining trade
    if in_trade:
        if trade_action == 1:
            pnl_pips = (close[-1] - entry_price) / pip_value
        else:
            pnl_pips = (entry_price - close[-1]) / pip_value
        pnl = pnl_pips * pip_value_per_lot * lot_size
        balance += pnl
        pnls.append(pnl)

    # Metrics
    total_trades = len(pnls)
    if total_trades == 0:
        return MLBacktestResult(0, 0, 0, 0, 0, 0, initial_balance, 0, signals_filtered)

    pnls_arr = np.array(pnls)
    wins = pnls_arr[pnls_arr > 0]
    losses = pnls_arr[pnls_arr <= 0]

    win_rate = len(wins) / total_trades * 100
    gross_profit = wins.sum() if len(wins) > 0 else 0
    gross_loss = abs(losses.sum()) if len(losses) > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    total_pnl = balance - initial_balance

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

    avg_conf = np.mean(confidences) if confidences else 0.0

    return MLBacktestResult(
        total_pnl=round(total_pnl, 2),
        total_trades=total_trades,
        win_rate=round(win_rate, 1),
        profit_factor=round(profit_factor, 3),
        max_drawdown_pct=round(max_dd, 2),
        sharpe_ratio=round(sharpe, 3),
        final_balance=round(balance, 2),
        avg_confidence=round(avg_conf, 3),
        signals_filtered=signals_filtered,
    )
