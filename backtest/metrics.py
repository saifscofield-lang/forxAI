"""
مقاييس الأداء — Backtest Performance Metrics
Sharpe ratio, max drawdown, profit factor, win rate, trade stats.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass
class PerformanceReport:
    """Summary of backtest performance."""
    # Returns
    total_return_pct: float
    total_pnl: float
    # Risk
    max_drawdown_pct: float
    max_drawdown_dollar: float
    sharpe_ratio: float
    # Trade stats
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    # Averages
    avg_win: float
    avg_loss: float
    avg_pnl_per_trade: float
    avg_win_pips: float
    avg_loss_pips: float
    # Durations (in bars)
    avg_trade_bars: float
    avg_win_bars: float
    avg_loss_bars: float
    # Streaks
    max_consecutive_wins: int
    max_consecutive_losses: int
    # Expectancy
    expectancy: float


def compute_metrics(result) -> PerformanceReport:
    """
    Compute performance metrics from a BacktestResult.

    Args:
        result: BacktestResult with trades and equity_curve.

    Returns:
        PerformanceReport dataclass.
    """
    trades = result.trades
    equity = pd.DataFrame(result.equity_curve)

    if not trades:
        return _empty_report()

    pnls = [t.pnl for t in trades]
    pnl_pips = [t.pnl_pips for t in trades]

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]

    total_pnl = sum(pnls)
    total_return_pct = (total_pnl / result.initial_balance) * 100

    # Win rate
    win_rate = len(wins) / len(trades) * 100 if trades else 0

    # Profit factor
    gross_profit = sum(t.pnl for t in wins) if wins else 0
    gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Averages
    avg_win = np.mean([t.pnl for t in wins]) if wins else 0
    avg_loss = np.mean([t.pnl for t in losses]) if losses else 0
    avg_pnl = np.mean(pnls)
    avg_win_pips = np.mean([t.pnl_pips for t in wins]) if wins else 0
    avg_loss_pips = np.mean([t.pnl_pips for t in losses]) if losses else 0

    # Drawdown from equity curve
    max_dd_pct, max_dd_dollar = _max_drawdown(equity)

    # Sharpe ratio (annualized, using bar returns)
    sharpe = _sharpe_ratio(equity)

    # Trade durations (in bars — approximate from equity curve timestamps)
    avg_bars, avg_win_bars, avg_loss_bars = _trade_durations(trades, result.equity_curve)

    # Streaks
    max_wins, max_losses = _consecutive_streaks(trades)

    # Expectancy: (win_rate * avg_win) + (loss_rate * avg_loss)
    loss_rate = len(losses) / len(trades) if trades else 0
    expectancy = (win_rate / 100 * avg_win) + (loss_rate * avg_loss)

    return PerformanceReport(
        total_return_pct=round(total_return_pct, 2),
        total_pnl=round(total_pnl, 2),
        max_drawdown_pct=round(max_dd_pct, 2),
        max_drawdown_dollar=round(max_dd_dollar, 2),
        sharpe_ratio=round(sharpe, 3),
        total_trades=len(trades),
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate=round(win_rate, 1),
        profit_factor=round(profit_factor, 3),
        avg_win=round(avg_win, 2),
        avg_loss=round(avg_loss, 2),
        avg_pnl_per_trade=round(avg_pnl, 2),
        avg_win_pips=round(avg_win_pips, 1),
        avg_loss_pips=round(avg_loss_pips, 1),
        avg_trade_bars=round(avg_bars, 1),
        avg_win_bars=round(avg_win_bars, 1),
        avg_loss_bars=round(avg_loss_bars, 1),
        max_consecutive_wins=max_wins,
        max_consecutive_losses=max_losses,
        expectancy=round(expectancy, 2),
    )


def _max_drawdown(equity: pd.DataFrame) -> tuple[float, float]:
    """Calculate max drawdown percentage and dollar amount from equity curve."""
    if equity.empty or "equity" not in equity.columns:
        return 0.0, 0.0

    eq = equity["equity"].values
    peak = np.maximum.accumulate(eq)
    drawdown = peak - eq
    max_dd_dollar = np.max(drawdown)

    # Percentage relative to peak
    dd_pct = drawdown / np.where(peak > 0, peak, 1) * 100
    max_dd_pct = np.max(dd_pct)

    return float(max_dd_pct), float(max_dd_dollar)


def _sharpe_ratio(equity: pd.DataFrame, bars_per_year: int = 252 * 24) -> float:
    """
    Annualized Sharpe ratio from equity curve.
    Default: H1 bars → 252 trading days * 24 hours.
    """
    if len(equity) < 2:
        return 0.0

    returns = equity["equity"].pct_change().dropna()
    if returns.std() == 0:
        return 0.0

    return float(returns.mean() / returns.std() * np.sqrt(bars_per_year))


def _trade_durations(trades, equity_curve) -> tuple[float, float, float]:
    """Estimate average trade duration in bars."""
    if not trades or not equity_curve:
        return 0.0, 0.0, 0.0

    durations = []
    win_durations = []
    loss_durations = []

    for t in trades:
        if t.entry_time and t.exit_time:
            # Duration in hours (each H1 bar = 1 hour)
            delta = (t.exit_time - t.entry_time).total_seconds() / 3600
            bars = max(1, delta)
            durations.append(bars)
            if t.pnl > 0:
                win_durations.append(bars)
            else:
                loss_durations.append(bars)

    avg_bars = np.mean(durations) if durations else 0
    avg_win = np.mean(win_durations) if win_durations else 0
    avg_loss = np.mean(loss_durations) if loss_durations else 0

    return float(avg_bars), float(avg_win), float(avg_loss)


def _consecutive_streaks(trades) -> tuple[int, int]:
    """Find max consecutive wins and losses."""
    if not trades:
        return 0, 0

    max_wins = max_losses = 0
    curr_wins = curr_losses = 0

    for t in trades:
        if t.pnl > 0:
            curr_wins += 1
            curr_losses = 0
            max_wins = max(max_wins, curr_wins)
        else:
            curr_losses += 1
            curr_wins = 0
            max_losses = max(max_losses, curr_losses)

    return max_wins, max_losses


def _empty_report() -> PerformanceReport:
    """Return a zeroed-out report for empty backtests."""
    return PerformanceReport(
        total_return_pct=0, total_pnl=0, max_drawdown_pct=0, max_drawdown_dollar=0,
        sharpe_ratio=0, total_trades=0, winning_trades=0, losing_trades=0,
        win_rate=0, profit_factor=0, avg_win=0, avg_loss=0, avg_pnl_per_trade=0,
        avg_win_pips=0, avg_loss_pips=0, avg_trade_bars=0, avg_win_bars=0,
        avg_loss_bars=0, max_consecutive_wins=0, max_consecutive_losses=0, expectancy=0,
    )


def format_report(report: PerformanceReport, result=None) -> str:
    """Format a performance report as a readable string."""
    lines = []
    lines.append("=" * 60)
    lines.append("           BACKTEST PERFORMANCE REPORT")
    lines.append("=" * 60)

    if result:
        lines.append(f"  Symbol:         {result.symbol}")
        lines.append(f"  Timeframe:      {result.timeframe}")
        lines.append(f"  Strategy:       {result.strategy}")
        lines.append(f"  Period:         {result.start_date} -> {result.end_date}")
        lines.append(f"  Initial Balance:${result.initial_balance:,.2f}")
        lines.append(f"  Final Balance:  ${result.final_balance:,.2f}")
        lines.append("-" * 60)

    lines.append(f"  Total Return:   {report.total_return_pct:+.2f}%  (${report.total_pnl:+,.2f})")
    lines.append(f"  Sharpe Ratio:   {report.sharpe_ratio:.3f}")
    lines.append(f"  Max Drawdown:   {report.max_drawdown_pct:.2f}%  (${report.max_drawdown_dollar:,.2f})")
    lines.append("-" * 60)
    lines.append(f"  Total Trades:   {report.total_trades}")
    lines.append(f"  Win Rate:       {report.win_rate:.1f}%  ({report.winning_trades}W / {report.losing_trades}L)")
    lines.append(f"  Profit Factor:  {report.profit_factor:.3f}")
    lines.append(f"  Expectancy:     ${report.expectancy:+.2f} per trade")
    lines.append("-" * 60)
    lines.append(f"  Avg Win:        ${report.avg_win:+,.2f}  ({report.avg_win_pips:+.1f} pips)")
    lines.append(f"  Avg Loss:       ${report.avg_loss:+,.2f}  ({report.avg_loss_pips:+.1f} pips)")
    lines.append(f"  Avg P&L/Trade:  ${report.avg_pnl_per_trade:+,.2f}")
    lines.append("-" * 60)
    lines.append(f"  Avg Trade Dur:  {report.avg_trade_bars:.1f} bars")
    lines.append(f"  Avg Win Dur:    {report.avg_win_bars:.1f} bars")
    lines.append(f"  Avg Loss Dur:   {report.avg_loss_bars:.1f} bars")
    lines.append("-" * 60)
    lines.append(f"  Max Win Streak: {report.max_consecutive_wins}")
    lines.append(f"  Max Loss Streak:{report.max_consecutive_losses}")
    lines.append("=" * 60)

    return "\n".join(lines)
