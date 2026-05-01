"""Exit-reason classifier for closed trades (AI-017b).

Refines the MT5 close-deal tag using price-proximity heuristics so the
trade record carries information the meta-labeler can train on.

The MT5 close-deal comment carries one of four shapes:
- "[sl <price>]" — SL price was hit (could be original adverse SL OR a
  modified break-even / trailing SL that ended up near entry / in profit)
- "[tp <price>]" — TP was hit
- "[so] / margin" — stop-out
- empty / opaque — manual or unknown

The bug AI-017b targets: when SL was modified (trailing-stop or break-even
move), the close still carries an "[sl ...]" tag, but the trade is NOT a
real adverse stop. The original engine treated all SL tags as `SL_HIT`,
producing the empirical pattern (50% of v3 ml_direct SL_HIT trades have
close ≈ open with pnl ≈ +$2 — break-even closes mislabelled as adverse
losses).

Note: the original audit (ai017_supplemental_findings_2026_05_01.md) said
the substring `"SL"` matched `"SELL"` in ML signal comments. That claim
was verified WRONG on 2026-05-01: `"SL" in "SELL"` is False (the
characters are S-E-L-L, no S-immediately-L pair). The actual mechanism
is modified-SL hits as described above. Documented in the supplemental
doc's correction section.

This module's classify_exit() takes the MT5-derived initial tag and
refines it using price-proximity rules. It uses ONLY data available at
close time + entry-time ATR — no SL-modification log required.

Output enum (5 values):
    TP_HIT          — TP was hit (passed through from MT5 tag, unchanged)
    SL_HIT          — adverse stop, close in adverse direction by > threshold
    BE_HIT          — close ≈ open within threshold; SL was at break-even
    TRAILING_STOP   — close in favorable direction by > threshold despite
                      MT5 reporting SL hit; SL was trailed into profit
    MANUAL          — neither SL nor TP tag from MT5
"""
from __future__ import annotations

from typing import Optional


# Per-symbol fallback threshold when atr_at_entry is missing. These are
# rough "how big is a typical bar move" estimates — only used when ATR
# is unavailable. ATR-based threshold is preferred.
_FALLBACK_THRESHOLDS = {
    "XAUUSD": 5.0,        # 5 points on gold
    "USDJPY": 0.05,       # 5 pips × 0.01 pip_value
    "AUDJPY": 0.05,
    "EURJPY": 0.05,
    "GBPJPY": 0.05,
}
_DEFAULT_FALLBACK = 0.0005  # 5 pips × 0.0001 pip_value (most forex)


def _resolve_threshold(symbol: str, atr_at_entry: Optional[float]) -> float:
    """Return the price-distance threshold for break-even classification.

    Preference: 0.10 × ATR at entry (auto-scales per symbol). Falls back to
    a hand-picked per-symbol value if ATR is missing.

    The 0.10 × ATR multiplier is calibrated against the empirical
    break-even cohort in v3 paper trading: those trades had close-to-open
    distance < 0.50 (XAUUSD with ATR ≈ 16; 0.10 × 16 = 1.6 → catches
    the 0.02–0.10 distances cleanly, with margin for noise)."""
    if atr_at_entry and atr_at_entry > 0:
        return 0.10 * atr_at_entry
    return _FALLBACK_THRESHOLDS.get(symbol, _DEFAULT_FALLBACK)


def classify_exit(
    open_price: Optional[float],
    close_price: Optional[float],
    stop_loss: Optional[float],
    take_profit: Optional[float],
    order_type: Optional[str],
    atr_at_entry: Optional[float],
    mt5_exit_tag: str,
    symbol: str = "",
) -> str:
    """Classify a closed trade's exit reason using price proximity.

    Args:
        open_price, close_price: actual entry / exit prices.
        stop_loss, take_profit: SL/TP at close time (may have been modified
            since order placement). Currently not load-bearing for the
            classifier — kept in the signature for future extensions.
        order_type: "BUY" or "SELL".
        atr_at_entry: ATR at trade entry (from signal_log). Used to scale
            the break-even threshold. None falls back to per-symbol value.
        mt5_exit_tag: initial classification from MT5 close-deal comment —
            one of "SL_HIT", "TP_HIT", "MANUAL", "UNKNOWN".
        symbol: trade symbol, used for fallback threshold when ATR missing.

    Returns one of: "SL_HIT", "TP_HIT", "BE_HIT", "TRAILING_STOP",
    "MANUAL", "UNKNOWN".

    Refinement logic:
        - TP_HIT, MANUAL, UNKNOWN: pass through (MT5 was unambiguous).
        - SL_HIT: refine using close-to-open distance and direction:
            * |close - open| < threshold → BE_HIT
            * close in favorable direction by > threshold → TRAILING_STOP
            * close in adverse direction by > threshold → SL_HIT (real)

    Determinism: pure function of inputs. No DB calls, no clock reads."""
    # Pass-through cases — no refinement
    if mt5_exit_tag != "SL_HIT":
        return mt5_exit_tag

    # Need open + close + side to refine
    if open_price is None or close_price is None or order_type is None:
        return "SL_HIT"

    threshold = _resolve_threshold(symbol, atr_at_entry)
    move = close_price - open_price  # signed

    if abs(move) < threshold:
        return "BE_HIT"

    # Direction-aware: favorable means in profit
    if order_type.upper() == "BUY":
        favorable = move
    elif order_type.upper() == "SELL":
        favorable = -move
    else:
        # Unknown direction — can't refine, keep original
        return "SL_HIT"

    if favorable > threshold:
        return "TRAILING_STOP"
    # Adverse direction by more than threshold → real SL hit
    return "SL_HIT"
