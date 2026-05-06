"""Unit tests for ml/purged_cv.py.

Each test builds a small synthetic event series with explicit entry /
exit times, runs purged_kfold_indices, and asserts the resulting train
/ test sets satisfy the no-overlap and no-leak invariants.

Pytest-free runner at the bottom (matches tests/test_triple_barrier.py)."""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from ml.purged_cv import purged_kfold_indices, purged_kfold_summary


# ── Fixtures ─────────────────────────────────────────────────────────────────

def make_events(n: int, entry_freq: str = "1h", hold_bars: int = 1):
    """Build n events with entry times spaced `entry_freq` apart, each
    held `hold_bars` * entry_freq bars before exit."""
    entries = pd.date_range("2026-05-01 00:00", periods=n, freq=entry_freq)
    exits = entries + pd.Timedelta(entry_freq) * hold_bars
    return pd.DataFrame({"exit_time": exits, "label": np.zeros(n)}, index=entries)


# ── Basic invariants ────────────────────────────────────────────────────────

def test_returns_n_splits_folds():
    events = make_events(50, hold_bars=1)
    folds = list(purged_kfold_indices(events, n_splits=5))
    assert len(folds) == 5


def test_test_indices_cover_all_samples_exactly_once():
    """Across all folds, every sample appears in exactly one test set."""
    events = make_events(50, hold_bars=1)
    seen = []
    for _, test_idx in purged_kfold_indices(events, n_splits=5):
        seen.extend(test_idx.tolist())
    assert sorted(seen) == list(range(50))


def test_train_and_test_disjoint_per_fold():
    events = make_events(50, hold_bars=1)
    for train_idx, test_idx in purged_kfold_indices(events, n_splits=5):
        assert len(set(train_idx) & set(test_idx)) == 0


# ── Purging: overlapping events get removed ────────────────────────────────

def test_purges_train_event_whose_exit_overlaps_test_window():
    """Set hold_bars high enough that early train events' exit_times
    fall inside later test folds' entry windows. Those train events
    must be purged."""
    events = make_events(20, hold_bars=10)  # heavy overlap
    folds = list(purged_kfold_indices(events, n_splits=4))
    # Take the middle fold (test fold 2: indices 10-14). Any train
    # event with exit_time >= events.index[10] would overlap and
    # should be purged.
    train_idx, test_idx = folds[2]
    test_start_time = events.index[test_idx[0]]
    test_end_time = events["exit_time"].iloc[test_idx].max()
    for i in train_idx:
        ev_entry = events.index[i]
        ev_exit = events["exit_time"].iloc[i]
        # Should NOT overlap [test_start_time, test_end_time]
        assert ev_exit < test_start_time or ev_entry > test_end_time, (
            f"train event {i} overlaps test fold: "
            f"{ev_entry}-{ev_exit} vs {test_start_time}-{test_end_time}"
        )


def test_no_overlap_when_holds_are_short():
    """Short hold_bars with non-overlapping windows → minimal purging.
    Train set should be (n − fold_size − some boundary purge) ~ size."""
    events = make_events(50, hold_bars=1)  # exit equals next entry
    folds = list(purged_kfold_indices(events, n_splits=5))
    for train_idx, test_idx in folds:
        # Even with hold_bars=1 the boundary event right before the
        # test fold has exit == test_t0 → counts as overlap → purged.
        # So train_size ∈ [n - fold_size - 2, n - fold_size).
        n = len(events)
        fold_size = n // 5
        assert n - fold_size - 2 <= len(train_idx) < n - fold_size


# ── Embargo ────────────────────────────────────────────────────────────────

def test_embargo_drops_samples_after_test_fold():
    events = make_events(100, hold_bars=1)
    n = len(events)
    embargo_pct = 0.05  # 5% = 5 samples
    folds = list(purged_kfold_indices(events, n_splits=5, embargo_pct=embargo_pct))
    # First fold's test = [0, 20). Embargo drops [20, 25). So train
    # indices should NOT contain any of [20, 25).
    train_idx, test_idx = folds[0]
    embargoed = set(range(20, 25))
    assert not (set(train_idx) & embargoed), (
        f"train contains embargoed indices: {set(train_idx) & embargoed}"
    )


def test_embargo_zero_does_nothing():
    events = make_events(50, hold_bars=1)
    no_embargo = list(purged_kfold_indices(events, n_splits=5, embargo_pct=0.0))
    with_embargo = list(purged_kfold_indices(events, n_splits=5, embargo_pct=0.05))
    # First fold's test = [0, 10). With non-zero embargo, train_size
    # should be smaller than without (since some valid candidates were
    # embargoed-out).
    assert len(with_embargo[0][0]) <= len(no_embargo[0][0])


# ── Edge cases ─────────────────────────────────────────────────────────────

def test_empty_events_yields_nothing():
    events = pd.DataFrame(columns=["exit_time"])
    folds = list(purged_kfold_indices(events, n_splits=5))
    assert folds == []


def test_n_splits_too_large_raises():
    events = make_events(3)
    try:
        list(purged_kfold_indices(events, n_splits=5))
        assert False, "expected ValueError"
    except ValueError as e:
        assert "at least n_splits" in str(e)


def test_n_splits_below_two_raises():
    events = make_events(10)
    try:
        list(purged_kfold_indices(events, n_splits=1))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_missing_exit_time_column_raises():
    events = pd.DataFrame({"label": [0, 1]}, index=pd.date_range("2026-05-01", periods=2))
    try:
        list(purged_kfold_indices(events, n_splits=2))
        assert False, "expected ValueError"
    except ValueError as e:
        assert "exit_time" in str(e)


def test_unsorted_index_raises():
    df = make_events(10)
    df = df.iloc[::-1]  # reverse → not monotonic increasing
    try:
        list(purged_kfold_indices(df, n_splits=5))
        assert False, "expected ValueError"
    except ValueError as e:
        assert "monotonic" in str(e) or "sorted" in str(e)


def test_invalid_embargo_raises():
    events = make_events(10)
    try:
        list(purged_kfold_indices(events, n_splits=2, embargo_pct=1.5))
        assert False, "expected ValueError"
    except ValueError:
        pass
    try:
        list(purged_kfold_indices(events, n_splits=2, embargo_pct=-0.1))
        assert False, "expected ValueError"
    except ValueError:
        pass


# ── NaT exit_time ──────────────────────────────────────────────────────────

def test_nat_exit_time_treated_as_entry_only():
    """A NaT exit_time means we couldn't label the event (e.g. event
    fell at the end of the bar series). Such events should not break
    purging — their evaluation window collapses to [entry, entry]."""
    events = make_events(10, hold_bars=1)
    events.loc[events.index[2], "exit_time"] = pd.NaT
    # Should not raise
    folds = list(purged_kfold_indices(events, n_splits=5))
    assert len(folds) == 5


# ── Summary helper ─────────────────────────────────────────────────────────

def test_summary_columns():
    events = make_events(50, hold_bars=2)
    summary = purged_kfold_summary(events, n_splits=5, embargo_pct=0.02)
    expected = {
        "fold", "test_size", "train_size", "purged_size",
        "embargoed_size", "test_window_start", "test_window_end",
    }
    assert set(summary.columns) == expected
    assert len(summary) == 5
    assert summary["test_size"].sum() == 50  # all samples covered


# ── Combined sanity: realistic scale ───────────────────────────────────────

def test_realistic_v3_scale():
    """Closer-to-real scale — 200 events with 8-bar hold (3% overlap).
    Confirm the splitter runs without error and produces reasonable
    train/test sizes."""
    events = make_events(200, hold_bars=8)
    folds = list(purged_kfold_indices(events, n_splits=5, embargo_pct=0.01))
    assert len(folds) == 5
    n_test_total = sum(len(t[1]) for t in folds)
    assert n_test_total == 200
    # Each train fold should have at least n - fold_size - some-overlap
    # samples; expect train size to be in a reasonable band.
    for train_idx, test_idx in folds:
        assert 100 < len(train_idx) <= 180


# ── Pytest-free runner ─────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    fail = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            fail += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            fail += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print()
    print(f"{len(tests) - fail}/{len(tests)} pass")
    sys.exit(0 if fail == 0 else 1)
