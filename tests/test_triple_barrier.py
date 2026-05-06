"""Unit tests for features/labels/triple_barrier.py.

Each test builds synthetic OHLC bars where the path is engineered so we
know in advance which barrier should hit first. Tests cover:
- BUY hits TP / SL / vertical barrier
- SELL hits TP / SL / vertical barrier (mirror cases)
- Both barriers hit in the same bar (conservative-loss tie-break)
- Degenerate inputs (empty bars, zero ATR, missing columns)
- Batch labelling via label_events
- Event timestamp before / after the bar series

Runs without pytest (plain assert + a tiny harness at the bottom) so
it executes against the local venv even when pytest install is blocked
by SSL/internet."""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

import pandas as pd

from features.labels.triple_barrier import (
    BarrierResult,
    label_event,
    label_events,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

def make_bars(highs, lows, closes=None, start="2026-05-06 00:00", freq="1h"):
    """Build a bars DataFrame with synthetic OHLC. closes default to highs."""
    n = len(highs)
    if closes is None:
        closes = highs
    idx = pd.date_range(start=start, periods=n, freq=freq)
    return pd.DataFrame(
        {"high": highs, "low": lows, "close": closes}, index=idx
    )


# ── BUY tests ────────────────────────────────────────────────────────────────

def test_buy_hits_tp_first():
    """BUY at 100, ATR=10, tp×2=120, sl×1=90. Path drifts up to 121 in bar 3."""
    bars = make_bars(
        highs=[105, 115, 121, 130],
        lows=[99, 108, 118, 125],
    )
    r = label_event(
        entry_time=pd.Timestamp("2026-05-05 23:00"),
        entry_price=100, side="BUY", atr=10, bars=bars,
    )
    assert r is not None
    assert r.label == +1, r
    assert r.barrier_hit == "TP"
    assert r.exit_price == 120  # TP barrier price
    assert r.bars_held == 3


def test_buy_hits_sl_first():
    """BUY at 100, sl=90. Path: 95, 92, 88 (SL hit in bar 3)."""
    bars = make_bars(
        highs=[102, 99, 95],
        lows=[95, 92, 88],
    )
    r = label_event(
        entry_time=pd.Timestamp("2026-05-05 23:00"),
        entry_price=100, side="BUY", atr=10, bars=bars,
    )
    assert r.label == -1
    assert r.barrier_hit == "SL"
    assert r.exit_price == 90
    assert r.bars_held == 3


def test_buy_vertical_timeout():
    """Path stays in the corridor. Vertical barrier hits → label 0."""
    bars = make_bars(
        highs=[105, 108, 110, 115],
        lows=[99, 100, 102, 105],
        closes=[103, 105, 108, 112],
    )
    r = label_event(
        entry_time=pd.Timestamp("2026-05-05 23:00"),
        entry_price=100, side="BUY", atr=10, bars=bars,
        max_hold_bars=4,
    )
    assert r.label == 0
    assert r.barrier_hit == "TIME"
    assert r.exit_price == 112  # last close


# ── SELL tests ───────────────────────────────────────────────────────────────

def test_sell_hits_tp_first():
    """SELL at 100, sl=110, tp=80. Path drifts DOWN to 79 (TP for SELL)."""
    bars = make_bars(
        highs=[101, 95, 90, 85],
        lows=[97, 90, 85, 79],
    )
    r = label_event(
        entry_time=pd.Timestamp("2026-05-05 23:00"),
        entry_price=100, side="SELL", atr=10, bars=bars,
    )
    assert r.label == +1
    assert r.barrier_hit == "TP"
    assert r.exit_price == 80  # SELL TP barrier (lower price)
    assert r.bars_held == 4


def test_sell_hits_sl_first():
    """SELL at 100, sl=110, tp=80. Path drifts UP to 111 (SL for SELL)."""
    bars = make_bars(
        highs=[103, 108, 111, 115],
        lows=[100, 105, 108, 112],
    )
    r = label_event(
        entry_time=pd.Timestamp("2026-05-05 23:00"),
        entry_price=100, side="SELL", atr=10, bars=bars,
    )
    assert r.label == -1
    assert r.barrier_hit == "SL"
    assert r.exit_price == 110  # SELL SL barrier (upper price)
    assert r.bars_held == 3


def test_sell_vertical_timeout():
    bars = make_bars(
        highs=[105, 108, 109],
        lows=[97, 95, 93],
        closes=[100, 101, 99],
    )
    r = label_event(
        entry_time=pd.Timestamp("2026-05-05 23:00"),
        entry_price=100, side="SELL", atr=10, bars=bars,
        max_hold_bars=3,
    )
    assert r.label == 0
    assert r.barrier_hit == "TIME"
    assert r.exit_price == 99


# ── Tie-break: both barriers hit in same bar ────────────────────────────────

def test_buy_both_barriers_same_bar_prefers_loss():
    """BUY at 100; in bar 1 the high reaches 121 AND low drops to 89.
    Conservative tie-break: prefer the adverse outcome (label -1)."""
    bars = make_bars(
        highs=[121],
        lows=[89],
    )
    r = label_event(
        entry_time=pd.Timestamp("2026-05-05 23:00"),
        entry_price=100, side="BUY", atr=10, bars=bars,
    )
    assert r.label == -1, "tie should resolve to adverse"
    assert r.barrier_hit == "SL"


# ── Degenerate inputs ───────────────────────────────────────────────────────

def test_zero_atr_returns_none():
    bars = make_bars([105], [95])
    r = label_event(pd.Timestamp("2026-05-05 23:00"), 100, "BUY", 0, bars)
    assert r is None


def test_empty_bars_returns_none():
    bars = make_bars([], [])
    r = label_event(pd.Timestamp("2026-05-05 23:00"), 100, "BUY", 10, bars)
    assert r is None


def test_invalid_side_returns_none():
    bars = make_bars([105], [95])
    r = label_event(pd.Timestamp("2026-05-05 23:00"), 100, "HOLD", 10, bars)
    assert r is None


def test_missing_columns_returns_none():
    bars = pd.DataFrame({"open": [100], "close": [101]},
                        index=pd.date_range("2026-05-06", periods=1))
    r = label_event(pd.Timestamp("2026-05-05 23:00"), 100, "BUY", 10, bars)
    assert r is None


def test_event_after_last_bar_returns_none():
    bars = make_bars([105, 110], [95, 100], start="2026-05-06 00:00")
    r = label_event(pd.Timestamp("2026-05-07 00:00"), 100, "BUY", 10, bars)
    assert r is None


def test_event_before_first_bar_uses_all_bars():
    bars = make_bars([105, 121], [95, 110])
    r = label_event(pd.Timestamp("2026-05-01 00:00"), 100, "BUY", 10, bars)
    assert r is not None
    assert r.label == +1
    assert r.bars_held == 2


# ── max_hold_bars ───────────────────────────────────────────────────────────

def test_max_hold_caps_lookforward():
    """Even though TP would be hit in bar 5, max_hold_bars=3 forces a
    vertical-barrier exit at bar 3."""
    bars = make_bars(
        highs=[105, 108, 110, 115, 121],
        lows=[99, 102, 105, 108, 115],
        closes=[103, 106, 108, 113, 119],
    )
    r = label_event(
        entry_time=pd.Timestamp("2026-05-05 23:00"),
        entry_price=100, side="BUY", atr=10, bars=bars,
        max_hold_bars=3,
    )
    assert r.label == 0
    assert r.bars_held == 3
    assert r.exit_price == 108  # close of bar 3


# ── Batch via label_events ──────────────────────────────────────────────────

def test_label_events_batch():
    bars = make_bars(
        highs=[105, 121, 90, 85, 88, 92],
        lows=[99, 110, 80, 79, 82, 87],
    )
    events = pd.DataFrame(
        {
            "side": ["BUY", "SELL"],
            "price": [100.0, 100.0],
            "atr": [10.0, 10.0],
        },
        index=[
            pd.Timestamp("2026-05-05 23:00"),
            pd.Timestamp("2026-05-06 02:00"),
        ],
    )
    out = label_events(events, bars)
    # Original columns preserved
    assert list(out["side"]) == ["BUY", "SELL"]
    # First event hits TP at bar 2 (high=121 >= 120)
    assert out.iloc[0]["label"] == +1
    assert out.iloc[0]["barrier_hit"] == "TP"
    # Second event: SELL at 100, lower-barrier (TP) = 80; bar at 04:00
    # has low=79 → SELL TP hit → label +1
    assert out.iloc[1]["label"] == +1
    assert out.iloc[1]["barrier_hit"] == "TP"


def test_label_events_empty():
    bars = make_bars([105], [95])
    events = pd.DataFrame(columns=["side", "price", "atr"])
    out = label_events(events, bars)
    assert out.empty
    assert "label" in out.columns


# ── Tiny pytest-free runner ─────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    fail = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            fail += 1
            print(f"  FAIL  {t.__name__}: {e!r}")
        except Exception as e:
            fail += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print()
    print(f"{len(tests) - fail}/{len(tests)} pass")
    sys.exit(0 if fail == 0 else 1)
