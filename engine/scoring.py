"""
Strategy Scoring Engine — S/A/B/C/F grading system
Based on Strategy Lab v3.0 weighted scoring:
  EV (35%) + PF (25%) + DD (20%) + Trades (10%) + WR (10%)

Usage:
    from engine.scoring import compute_score, grade_from_score
    score = compute_score(report)
    grade = grade_from_score(score)
"""
from dataclasses import dataclass


@dataclass
class ScoreBreakdown:
    """Detailed score breakdown for a strategy."""
    total_score: float       # 0-100
    grade: str               # S/A/B/C/F
    ev_score: float          # Expected Value component (0-35)
    pf_score: float          # Profit Factor component (0-25)
    dd_score: float          # Drawdown component (0-20)
    trades_score: float      # Trade count component (0-10)
    wr_score: float          # Win Rate component (0-10)
    fatal_fail: bool         # True if any fatal criterion failed
    fatal_reasons: list      # List of fatal failure reasons


# -- Scoring weights --
WEIGHTS = {
    "ev": 35,
    "pf": 25,
    "dd": 20,
    "trades": 10,
    "wr": 10,
}

# -- Grade thresholds --
GRADE_THRESHOLDS = [
    ("S", 90),   # 90-100: activate immediately
    ("A", 75),   # 75-89: paper trade 2 weeks then live
    ("B", 60),   # 60-74: optimize then retest
    ("C", 40),   # 40-59: review hypothesis + modify logic
    ("F", 0),    # < 40: reject, archive lesson learned
]

# -- Fatal thresholds (instant fail) --
FATAL = {
    "ev_negative": True,       # EV < 0 = logic is wrong
    "pf_below_one": True,      # PF < 1.0 = guaranteed loss
    "dd_above_15": True,       # DD > 15% = psychological death
    "trades_below_50": True,   # < 50 trades = not statistically significant
}


def _score_ev(avg_win: float, avg_loss: float, win_rate: float) -> tuple:
    """Score Expected Value: (WR * AvgWin) - (LR * AvgLoss). Weight: 35%."""
    lr = 1.0 - (win_rate / 100.0)
    wr = win_rate / 100.0
    ev = (wr * abs(avg_win)) - (lr * abs(avg_loss))

    fatal = ev < 0
    if ev <= 0:
        raw = 0
    elif ev < 5:
        raw = 30 + (ev / 5) * 20  # 30-50
    elif ev < 20:
        raw = 50 + ((ev - 5) / 15) * 30  # 50-80
    elif ev < 50:
        raw = 80 + ((ev - 20) / 30) * 15  # 80-95
    else:
        raw = min(100, 95 + (ev - 50) / 50 * 5)

    return raw * WEIGHTS["ev"] / 100, fatal


def _score_pf(profit_factor: float) -> tuple:
    """Score Profit Factor. Weight: 25%."""
    fatal = profit_factor < 1.0
    if profit_factor < 1.0:
        raw = max(0, profit_factor * 30)  # 0-30
    elif profit_factor < 1.2:
        raw = 30 + (profit_factor - 1.0) / 0.2 * 20  # 30-50
    elif profit_factor < 1.4:
        raw = 50 + (profit_factor - 1.2) / 0.2 * 20  # 50-70
    elif profit_factor < 1.8:
        raw = 70 + (profit_factor - 1.4) / 0.4 * 20  # 70-90
    elif profit_factor < 2.5:
        raw = 90 + (profit_factor - 1.8) / 0.7 * 10  # 90-100
    else:
        raw = 100

    return raw * WEIGHTS["pf"] / 100, fatal


def _score_dd(max_drawdown_pct: float) -> tuple:
    """Score Max Drawdown (lower is better). Weight: 20%."""
    fatal = max_drawdown_pct > 15.0
    if max_drawdown_pct <= 3:
        raw = 100
    elif max_drawdown_pct <= 5:
        raw = 90 + (5 - max_drawdown_pct) / 2 * 10  # 90-100
    elif max_drawdown_pct <= 8:
        raw = 70 + (8 - max_drawdown_pct) / 3 * 20  # 70-90
    elif max_drawdown_pct <= 15:
        raw = 30 + (15 - max_drawdown_pct) / 7 * 40  # 30-70
    elif max_drawdown_pct <= 30:
        raw = (30 - max_drawdown_pct) / 15 * 30  # 0-30
    else:
        raw = 0

    return max(0, raw) * WEIGHTS["dd"] / 100, fatal


def _score_trades(total_trades: int) -> tuple:
    """Score trade count (statistical significance). Weight: 10%."""
    fatal = total_trades < 50
    if total_trades < 15:
        raw = 0
    elif total_trades < 30:
        raw = 20 + (total_trades - 15) / 15 * 20  # 20-40
    elif total_trades < 50:
        raw = 40 + (total_trades - 30) / 20 * 20  # 40-60
    elif total_trades < 100:
        raw = 60 + (total_trades - 50) / 50 * 20  # 60-80
    elif total_trades < 200:
        raw = 80 + (total_trades - 100) / 100 * 15  # 80-95
    else:
        raw = min(100, 95 + (total_trades - 200) / 300 * 5)

    return raw * WEIGHTS["trades"] / 100, fatal


def _score_wr(win_rate: float) -> tuple:
    """Score Win Rate. Weight: 10%. Not fatal on its own."""
    fatal = False  # WR is not fatal — good R:R can compensate
    if win_rate < 25:
        raw = max(0, win_rate * 1.2)  # 0-30
    elif win_rate < 35:
        raw = 30 + (win_rate - 25) / 10 * 20  # 30-50
    elif win_rate < 45:
        raw = 50 + (win_rate - 35) / 10 * 20  # 50-70
    elif win_rate < 55:
        raw = 70 + (win_rate - 45) / 10 * 15  # 70-85
    elif win_rate < 70:
        raw = 85 + (win_rate - 55) / 15 * 10  # 85-95
    else:
        raw = min(100, 95 + (win_rate - 70) / 30 * 5)

    return raw * WEIGHTS["wr"] / 100, fatal


def grade_from_score(score: float) -> str:
    """Convert numeric score (0-100) to letter grade."""
    for grade, threshold in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def compute_score(report) -> ScoreBreakdown:
    """
    Compute weighted score and grade for a backtest report.

    Args:
        report: PerformanceReport with attributes:
            total_trades, win_rate, profit_factor, max_drawdown_pct,
            avg_win, avg_loss, total_pnl, sharpe_ratio

    Returns:
        ScoreBreakdown with total_score, grade, component scores, and fatal info.
    """
    fatal_reasons = []

    ev_score, ev_fatal = _score_ev(report.avg_win, report.avg_loss, report.win_rate)
    pf_score, pf_fatal = _score_pf(report.profit_factor)
    dd_score, dd_fatal = _score_dd(report.max_drawdown_pct)
    trades_score, trades_fatal = _score_trades(report.total_trades)
    wr_score, wr_fatal = _score_wr(report.win_rate)

    if ev_fatal:
        fatal_reasons.append(f"Negative EV (avg_win={report.avg_win:.2f}, avg_loss={report.avg_loss:.2f})")
    if pf_fatal:
        fatal_reasons.append(f"PF < 1.0 ({report.profit_factor:.3f})")
    if dd_fatal:
        fatal_reasons.append(f"Drawdown > 15% ({report.max_drawdown_pct:.1f}%)")
    if trades_fatal:
        fatal_reasons.append(f"< 50 trades ({report.total_trades})")

    total = ev_score + pf_score + dd_score + trades_score + wr_score
    has_fatal = len(fatal_reasons) > 0

    # Fatal failures cap the grade at C (max score 59)
    if has_fatal:
        total = min(total, 59.9)

    grade = grade_from_score(total)

    return ScoreBreakdown(
        total_score=round(total, 1),
        grade=grade,
        ev_score=round(ev_score, 1),
        pf_score=round(pf_score, 1),
        dd_score=round(dd_score, 1),
        trades_score=round(trades_score, 1),
        wr_score=round(wr_score, 1),
        fatal_fail=has_fatal,
        fatal_reasons=fatal_reasons,
    )


def format_score(sb: ScoreBreakdown) -> str:
    """Format score breakdown as a readable string."""
    lines = [
        f"  Grade: [{sb.grade}] Score: {sb.total_score}/100",
        f"  EV: {sb.ev_score}/{WEIGHTS['ev']} | PF: {sb.pf_score}/{WEIGHTS['pf']} | "
        f"DD: {sb.dd_score}/{WEIGHTS['dd']} | Trades: {sb.trades_score}/{WEIGHTS['trades']} | "
        f"WR: {sb.wr_score}/{WEIGHTS['wr']}",
    ]
    if sb.fatal_fail:
        lines.append(f"  FATAL: {'; '.join(sb.fatal_reasons)}")
    return "\n".join(lines)
