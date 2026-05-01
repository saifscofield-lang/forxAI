"""Realized risk:reward and profit-factor metrics for closed trades.

This module replaces the inline computation that used to live at
engine/trading_engine.py:1156-1164 and centralises it so analysis
scripts and the live trade-close handler share one definition.

The Phase 7 ship gate uses dual PF gating:

    R-PF >= 1.3  AND  $-PF >= 1.0

R-PF normalises per-trade risk and is the primary academic metric.
$-PF reflects actual capital outcome and protects against scenarios
where R-PF looks fine but capital is shrinking. Both must pass; see
docs/research/phase7_ship_gate_definition.md for the rationale.
"""
from __future__ import annotations

from typing import Iterable, Optional


def realized_rr(
    open_price: float,
    close_price: float,
    stop_loss: float,
    pnl: float,
) -> Optional[float]:
    """Signed realized risk:reward for a closed trade.

    Returns positive when the trade closed in profit, negative when in
    loss, 0.0 when close == open. Magnitude is the price excursion in
    units of the planned SL distance.

    Returns None when SL is missing/zero or when any input is None
    (caller must decide how to surface those — the live engine logs
    None into trade_results.risk_reward_actual)."""
    if open_price is None or close_price is None or stop_loss is None:
        return None
    sl_dist = abs(open_price - stop_loss)
    if sl_dist == 0:
        return None
    actual_dist = abs(close_price - open_price)
    rr = round(actual_dist / sl_dist, 2)
    if pnl is not None and pnl < 0:
        rr = -rr
    return rr


def profit_factor_dollars(pnls: Iterable[float]) -> float:
    """Standard $-based profit factor: sum(wins) / sum(|losses|).

    Returns float('inf') when there are no losses, 0.0 when there are
    no wins. Mirrors the audit's reported PF semantics."""
    wins = sum(p for p in pnls if p is not None and p > 0)
    losses = sum(-p for p in pnls if p is not None and p < 0)
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return wins / losses


def profit_factor_r(rrs: Iterable[float]) -> float:
    """R-unit profit factor: sum(positive realized_rr) / sum(|negative realized_rr|).

    Each loss contributes exactly its own R magnitude (typically 1.0 when
    SL was hit). Independent of position size. Diverges from $-PF when
    volume or SL distance varies across trades."""
    wins_r = sum(r for r in rrs if r is not None and r > 0)
    losses_r = sum(-r for r in rrs if r is not None and r < 0)
    if losses_r == 0:
        return float("inf") if wins_r > 0 else 0.0
    return wins_r / losses_r


def phase7_ship_gate(pnls: Iterable[float], rrs: Iterable[float]) -> dict:
    """Compute the Phase 7 dual-gate ship metric.

    Gate definition (per docs/research/phase7_ship_gate_definition.md):
      R-PF >= 1.3  AND  $-PF >= 1.0

    Returns a dict with both metrics, both individual verdicts, and the
    combined pass/fail verdict so callers can render either."""
    pnls = list(pnls)
    rrs = list(rrs)
    pf_d = profit_factor_dollars(pnls)
    pf_r = profit_factor_r(rrs)
    pass_d = pf_d >= 1.0
    pass_r = pf_r >= 1.3
    return {
        "pf_dollars": pf_d,
        "pf_r": pf_r,
        "passes_dollars_gate": pass_d,
        "passes_r_gate": pass_r,
        "passes_dual_gate": pass_d and pass_r,
        "thresholds": {"r_min": 1.3, "dollars_min": 1.0},
    }
