"""Triple-Barrier Method for ML labelling.

Per Marcos López de Prado, "Advances in Financial Machine Learning"
(2018), Chapter 3. Each event (entry signal) gets a label by walking
the price series forward and seeing which of three barriers is
touched first:

    +1   profit-target barrier hit first  →  the trade was a winner
    −1   stop-loss barrier hit first      →  the trade was a loser
     0   vertical (time) barrier hit first → the trade timed out

The barriers are scaled by ATR (or equivalent volatility proxy) at
the entry bar. The vertical barrier is a fixed number of bars from
entry. Direction-aware: for BUY events, "upper" is the TP barrier
and "lower" is the SL; for SELL events the roles invert.

This module is the foundation for the Phase 7 meta-labeler — it
turns raw entry signals into supervised-learning targets without
look-ahead bias.

Pure function. No DB / engine / file-system dependencies. Inputs are
pandas DataFrames; output is a DataFrame keyed by event index."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


# ── Public API ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BarrierResult:
    """Outcome of a single triple-barrier evaluation."""
    label: int                  # +1 / -1 / 0
    barrier_hit: str            # "TP" | "SL" | "TIME"
    exit_time: pd.Timestamp     # bar at which the barrier was hit
    exit_price: float           # price at exit
    bars_held: int              # number of bars from entry to exit (inclusive)


def label_event(
    entry_time: pd.Timestamp,
    entry_price: float,
    side: str,
    atr: float,
    bars: pd.DataFrame,
    *,
    tp_atr_mult: float = 2.0,
    sl_atr_mult: float = 1.0,
    max_hold_bars: int = 24,
) -> Optional[BarrierResult]:
    """Apply the triple-barrier method to a single event.

    Args:
        entry_time: timestamp of the entry signal. Must be in `bars.index`
            or earlier than the first bar (in which case we use the first
            bar as the entry bar).
        entry_price: price at entry.
        side: "BUY" or "SELL". Determines whether the upper price barrier
            is the TP (BUY) or the SL (SELL).
        atr: volatility proxy at entry; barriers are scaled by this.
        bars: price bars indexed by timestamp with columns "high" and
            "low" (and ideally "close" for time-out exit price). The
            walk-forward starts at the first bar AFTER entry_time.
        tp_atr_mult: TP barrier distance from entry, in ATR units.
        sl_atr_mult: SL barrier distance from entry, in ATR units.
        max_hold_bars: vertical-barrier length. The trade is timed out
            if neither price barrier is hit within this many bars after
            entry.

    Returns:
        BarrierResult if a label can be computed, None if inputs are
        degenerate (no future bars, ATR = 0, missing high/low, etc.)."""
    if not _valid_inputs(entry_price, atr, bars, side):
        return None

    upper, lower = _compute_barriers(entry_price, atr, side, tp_atr_mult, sl_atr_mult)
    upper_label, lower_label = (+1, -1) if side.upper() == "BUY" else (-1, +1)

    future = _bars_after(bars, entry_time, max_hold_bars)
    if future.empty:
        return None

    for i, (ts, row) in enumerate(future.iterrows(), start=1):
        hi, lo = row["high"], row["low"]
        # When both barriers are touched in the same bar, prefer the
        # adverse outcome (label −1) — conservative for ML training.
        upper_hit = hi >= upper
        lower_hit = lo <= lower
        if upper_hit and lower_hit:
            return BarrierResult(
                label=lower_label,
                barrier_hit="SL" if lower_label == -1 else "TP",
                exit_time=ts,
                exit_price=lower if lower_label == -1 else upper,
                bars_held=i,
            )
        if upper_hit:
            return BarrierResult(
                label=upper_label,
                barrier_hit="TP" if upper_label == +1 else "SL",
                exit_time=ts,
                exit_price=upper,
                bars_held=i,
            )
        if lower_hit:
            return BarrierResult(
                label=lower_label,
                barrier_hit="SL" if lower_label == -1 else "TP",
                exit_time=ts,
                exit_price=lower,
                bars_held=i,
            )

    # Vertical barrier hit — neither price barrier touched within
    # max_hold_bars. Exit at the last available bar's close.
    last_ts = future.index[-1]
    last_close = future.iloc[-1].get("close", future.iloc[-1]["high"])
    return BarrierResult(
        label=0,
        barrier_hit="TIME",
        exit_time=last_ts,
        exit_price=float(last_close),
        bars_held=len(future),
    )


def label_events(
    events: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    tp_atr_mult: float = 2.0,
    sl_atr_mult: float = 1.0,
    max_hold_bars: int = 24,
) -> pd.DataFrame:
    """Apply the triple-barrier method to a batch of events.

    Args:
        events: DataFrame indexed by event timestamp (or with a
            'time' column) with columns 'side', 'price', 'atr'. Each
            row is one entry signal.
        bars: OHLC bars indexed by timestamp.
        tp_atr_mult, sl_atr_mult, max_hold_bars: same as `label_event`.

    Returns:
        DataFrame indexed the same as `events`, with columns:
            label, barrier_hit, exit_time, exit_price, bars_held.
        Events where labelling failed (degenerate inputs, no future bars)
        appear with label=NaN. Caller decides whether to drop them."""
    if events.empty:
        return events.assign(
            label=pd.Series(dtype="float64"),
            barrier_hit=pd.Series(dtype="object"),
            exit_time=pd.Series(dtype="datetime64[ns]"),
            exit_price=pd.Series(dtype="float64"),
            bars_held=pd.Series(dtype="Int64"),
        )

    results = []
    for ev_time, row in events.iterrows():
        # Allow event 'time' to come either from the index or a column
        t = row["time"] if "time" in row else ev_time
        result = label_event(
            entry_time=t,
            entry_price=row["price"],
            side=row["side"],
            atr=row["atr"],
            bars=bars,
            tp_atr_mult=tp_atr_mult,
            sl_atr_mult=sl_atr_mult,
            max_hold_bars=max_hold_bars,
        )
        if result is None:
            results.append({"label": pd.NA, "barrier_hit": pd.NA,
                            "exit_time": pd.NaT, "exit_price": pd.NA,
                            "bars_held": pd.NA})
        else:
            results.append({
                "label": result.label,
                "barrier_hit": result.barrier_hit,
                "exit_time": result.exit_time,
                "exit_price": result.exit_price,
                "bars_held": result.bars_held,
            })
    out = events.copy()
    labels_df = pd.DataFrame(results, index=events.index)
    return pd.concat([out, labels_df], axis=1)


# ── Internals ────────────────────────────────────────────────────────────────

def _valid_inputs(entry_price, atr, bars, side) -> bool:
    if entry_price is None or atr is None or bars is None:
        return False
    if side is None or side.upper() not in ("BUY", "SELL"):
        return False
    if atr <= 0:
        return False
    if not isinstance(bars, pd.DataFrame) or bars.empty:
        return False
    if "high" not in bars.columns or "low" not in bars.columns:
        return False
    return True


def _compute_barriers(entry_price, atr, side, tp_mult, sl_mult):
    """Return (upper_price, lower_price). Direction-aware.

    For BUY:
        upper = entry + tp_mult × atr   (profit barrier)
        lower = entry − sl_mult × atr   (stop barrier)
    For SELL:
        upper = entry + sl_mult × atr   (stop barrier)
        lower = entry − tp_mult × atr   (profit barrier)"""
    if side.upper() == "BUY":
        return entry_price + tp_mult * atr, entry_price - sl_mult * atr
    # SELL: barriers swap roles
    return entry_price + sl_mult * atr, entry_price - tp_mult * atr


def _bars_after(bars: pd.DataFrame, entry_time, max_hold_bars: int) -> pd.DataFrame:
    """Return up to `max_hold_bars` bars strictly after `entry_time`.

    If entry_time pre-dates the first bar, all bars are eligible. If
    entry_time exceeds the last bar, returns empty."""
    after = bars[bars.index > entry_time]
    return after.iloc[:max_hold_bars]
