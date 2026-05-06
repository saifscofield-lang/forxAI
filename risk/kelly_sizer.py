"""Kelly-criterion position sizing for the Phase 7 meta-labeler.

Per the Kelly criterion (1956), the fraction of bankroll that
maximises the expected geometric growth rate is:

    f* = (p × b − q) / b

where:
    p = probability of a winning trade
    q = 1 − p, probability of a losing trade
    b = ratio of average win size to average loss size (in same units)

The Phase 7 plan calls for "ml/kelly_sizer.py" but it sits more
naturally in risk/ next to risk_manager.py — Kelly is a sizing
rule, not an ML technique. This module pairs with the meta-labeler
output: the labeler produces P(profitable) per signal, the
historical PF-equivalent (avg_win / avg_loss) is known per
strategy, and Kelly turns those into a per-trade position fraction.

Three layers:

  kelly_fraction()      pure formula. Returns the unconstrained
                        Kelly fraction. Negative when edge is
                        negative; the caller decides whether to
                        clamp at zero or skip the trade.

  fractional_kelly()    full Kelly with a multiplier (0.25–0.5
                        typical) and an absolute cap. Standard
                        practical-use wrapper that handles edge
                        cases (negative edge → 0, infinite edge
                        → cap, etc.).

  kelly_position_size() turns fractional_kelly's output into a
                        dollar size given current balance and risk
                        per trade. Composes with the existing
                        risk_manager.calculate_position_size() —
                        Kelly here picks the *fraction*, the risk
                        manager picks the *lot size from fraction*.

Pure functions over scalar inputs. No DB, no engine, no
filesystem dependencies. All callers can pass in p, b, balance,
risk_per_trade as numpy floats."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ── Pure formula ────────────────────────────────────────────────────────────

def kelly_fraction(win_prob: float, win_loss_ratio: float) -> float:
    """Unconstrained Kelly fraction.

    Returns f* = (p × b − q) / b. Output range:
      - Negative when win_prob × win_loss_ratio < (1 − win_prob).
        Callers should clamp to 0 (no trade) or skip the signal.
      - Positive when there's positive expected value.
      - Can exceed 1.0 in theory; full-Kelly fractions above ~0.25
        are usually capped in practice (see fractional_kelly).

    Args:
        win_prob: probability of winning, in [0, 1].
        win_loss_ratio: average win / average loss (b in Kelly
            literature). Must be > 0. For a 2:1 R:R strategy that
            wins on average, b ≈ 2.0.

    Raises:
        ValueError if win_prob is outside [0, 1] or
        win_loss_ratio <= 0."""
    if not 0.0 <= win_prob <= 1.0:
        raise ValueError(f"win_prob must be in [0, 1], got {win_prob}")
    if win_loss_ratio <= 0:
        raise ValueError(f"win_loss_ratio must be > 0, got {win_loss_ratio}")
    q = 1.0 - win_prob
    return (win_prob * win_loss_ratio - q) / win_loss_ratio


# ── Practical wrapper ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class KellyResult:
    """Output of fractional_kelly()."""
    full_kelly: float           # raw f* from kelly_fraction()
    fractional_kelly: float     # full_kelly × multiplier
    capped: float               # final fraction after cap and clamp
    skip_trade: bool            # True if edge is non-positive


def fractional_kelly(
    win_prob: float,
    win_loss_ratio: float,
    *,
    multiplier: float = 0.25,
    max_fraction: float = 0.25,
) -> KellyResult:
    """Full Kelly with a multiplier and absolute cap.

    Most practitioners use FRACTIONAL Kelly (typically 0.25–0.5 ×
    full Kelly) because:
      - Full Kelly maximises geometric growth in expectation but
        produces extreme drawdowns under bad runs.
      - Half Kelly halves growth but cuts drawdown variance ~75%.
      - Quarter Kelly is the conservative practitioner default.

    On top of the multiplier, an absolute cap (default 0.25 = 25% of
    bankroll) bounds the worst-case position size for safety. This
    handles edge cases like extremely high reported win_prob from a
    small sample, where the Kelly formula would suggest betting most
    of the bankroll on a single trade.

    Returns a KellyResult dict-like with the full Kelly, fractional
    Kelly, and the capped final fraction. skip_trade is True when
    full_kelly ≤ 0 (negative or zero edge — don't trade)."""
    if not 0.0 < multiplier <= 2.0:
        raise ValueError(f"multiplier must be in (0, 2], got {multiplier}")
    if not 0.0 < max_fraction <= 1.0:
        raise ValueError(f"max_fraction must be in (0, 1], got {max_fraction}")
    full = kelly_fraction(win_prob, win_loss_ratio)
    if full <= 0:
        return KellyResult(
            full_kelly=full, fractional_kelly=0.0,
            capped=0.0, skip_trade=True,
        )
    frac = full * multiplier
    capped = min(frac, max_fraction)
    return KellyResult(
        full_kelly=full, fractional_kelly=frac,
        capped=capped, skip_trade=False,
    )


# ── Dollar-size composer ────────────────────────────────────────────────────

def kelly_position_size(
    balance: float,
    win_prob: float,
    win_loss_ratio: float,
    *,
    multiplier: float = 0.25,
    max_fraction: float = 0.25,
    min_size: float = 0.0,
) -> float:
    """Compose Kelly fraction with bankroll into a dollar position size.

    Returns balance × capped Kelly fraction. Returns 0.0 (i.e.
    skip the trade) when edge is non-positive.

    `min_size` is a floor: if the computed size is below it, return 0
    rather than a tiny meaningless trade. Default 0 disables the floor.

    Note: this is NOT lot-size aware. For MT5 lot rounding, pipe the
    output through risk.risk_manager.calculate_position_size() with the
    appropriate pip_value and stop-loss distance — Kelly here picks the
    fraction, the risk_manager picks the lot."""
    if balance <= 0:
        return 0.0
    result = fractional_kelly(
        win_prob, win_loss_ratio,
        multiplier=multiplier, max_fraction=max_fraction,
    )
    if result.skip_trade:
        return 0.0
    size = balance * result.capped
    if size < min_size:
        return 0.0
    return float(size)


# ── Convenience: derive ratio from historical avg_win/avg_loss ─────────────

def win_loss_ratio_from_pnl(avg_win: float, avg_loss: float) -> Optional[float]:
    """Convert average-win / average-loss dollar amounts into Kelly's b.

    avg_loss is expected as a POSITIVE number (the magnitude of the
    average loss). If you have signed losses (negative), pass abs(loss).

    Returns None if either input is non-positive (degenerate
    inputs — caller should treat as "no edge data, skip Kelly")."""
    if avg_win is None or avg_loss is None:
        return None
    if avg_win <= 0 or avg_loss <= 0:
        return None
    return float(avg_win / avg_loss)
