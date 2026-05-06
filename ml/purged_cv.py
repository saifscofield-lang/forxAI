"""Purged K-Fold cross-validation for time-series ML labels.

Per Marcos López de Prado, "Advances in Financial Machine Learning"
(2018), Chapter 7. Standard K-fold CV leaks information when used on
time-series ML labels because:

  - Each event's label is determined by price action over a future
    window (entry_time → exit_time). The triple-barrier method
    (features/labels/triple_barrier.py) produces exactly this kind
    of label.
  - Two events whose evaluation windows overlap share information.
    If event A is in the train set and event B in the test set, but
    their windows overlap, the model effectively learns from
    information that should be unavailable at A's prediction time —
    inflating CV scores.

Two corrections this module implements:

  1. **Purging.** For each test fold, remove from the training set
     any event whose evaluation window [entry, exit] overlaps with
     the test fold's union evaluation window. Eliminates direct
     label leakage.

  2. **Embargo.** Optionally, drop training events that fall in a
     small buffer just after the test fold ends. Mitigates serial
     correlation that purging alone misses (e.g., autocorrelation
     in features that survives the label-window separation).

This module returns plain `(train_idx, test_idx)` numpy arrays per
fold so it composes with any model-training loop. A thin sklearn
adapter (subclass of BaseCrossValidator) is intentionally not
included here — Phase 7 plan can add it as a one-liner wrapper if
the meta-labeler training pipeline ends up using sklearn's
GridSearchCV / cross_val_score.

Inputs are a DataFrame from `features.labels.triple_barrier.label_events`
or any DataFrame with an `exit_time` column whose index holds entry
timestamps."""
from __future__ import annotations

from typing import Iterator, Tuple

import numpy as np
import pandas as pd


def purged_kfold_indices(
    events: pd.DataFrame,
    n_splits: int = 5,
    embargo_pct: float = 0.0,
) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
    """Generate (train_idx, test_idx) for each fold of purged K-fold CV.

    Args:
        events: DataFrame indexed by entry timestamp, with an
            `exit_time` column giving each event's evaluation-window
            end. Must be sorted by index ascending. Output of
            `features.labels.triple_barrier.label_events` is the
            canonical input shape.
        n_splits: number of folds. Must be ≥ 2.
        embargo_pct: fraction of total samples to drop after each
            test fold's end as a serial-correlation buffer. 0.0
            disables embargo. Typical values 0.01–0.05 (1%–5%).

    Yields:
        (train_idx, test_idx) pairs of numpy int arrays. Indices are
        positional (0..n-1), not labels. Caller can use
        `events.iloc[train_idx]` to materialise rows.

    Raises:
        ValueError if events is missing the exit_time column, the
        index is not monotonic, n_splits < 2, or embargo_pct is out
        of [0, 1)."""
    if "exit_time" not in events.columns:
        raise ValueError("events must have an 'exit_time' column")
    if n_splits < 2:
        raise ValueError(f"n_splits must be >= 2, got {n_splits}")
    if not 0.0 <= embargo_pct < 1.0:
        raise ValueError(f"embargo_pct must be in [0, 1), got {embargo_pct}")

    n = len(events)
    if n == 0:
        return
    if n < n_splits:
        raise ValueError(
            f"need at least n_splits={n_splits} events, got {n}"
        )
    if not events.index.is_monotonic_increasing:
        raise ValueError("events must be sorted by index (entry time) ascending")

    # Build fold boundaries by integer position. Last fold absorbs
    # the remainder so total coverage equals n exactly.
    fold_size = n // n_splits
    fold_bounds = []
    for i in range(n_splits):
        start = i * fold_size
        end = (i + 1) * fold_size if i < n_splits - 1 else n
        fold_bounds.append((start, end))

    embargo_n = int(np.ceil(n * embargo_pct)) if embargo_pct > 0 else 0

    # Pre-extract entry times (from index) and exit times for fast lookup.
    entry_times = events.index.to_numpy()
    exit_times = events["exit_time"].to_numpy()

    for test_start, test_end in fold_bounds:
        test_idx = np.arange(test_start, test_end)

        # Union evaluation window for this test fold: from the earliest
        # entry to the latest exit. We use vectorised min/max over the
        # slice for speed and to handle NaT exit times defensively.
        test_t0 = entry_times[test_start]
        test_exits = exit_times[test_start:test_end]
        # Treat NaT-exit events as if their window extends through their entry only
        test_t1 = (
            np.nanmax(test_exits)
            if np.any(~pd.isna(test_exits))
            else entry_times[test_end - 1]
        )

        # Candidate train indices: everything except the test fold,
        # plus the embargo gap immediately after the test fold.
        embargo_end = min(test_end + embargo_n, n)
        candidates = np.concatenate(
            [np.arange(0, test_start), np.arange(embargo_end, n)]
        )

        # Purge: keep only train candidates whose evaluation window
        # does NOT overlap [test_t0, test_t1]. Window overlap rule:
        # two intervals [a, b] and [c, d] overlap iff a <= d AND c <= b.
        train_idx_list = []
        for i in candidates:
            ev_t0 = entry_times[i]
            ev_t1 = exit_times[i]
            if pd.isna(ev_t1):
                ev_t1 = ev_t0  # NaT exit defaults to entry-only window
            # Overlap test
            overlaps = (ev_t0 <= test_t1) and (test_t0 <= ev_t1)
            if not overlaps:
                train_idx_list.append(i)

        yield np.asarray(train_idx_list, dtype=np.int64), test_idx


def purged_kfold_summary(
    events: pd.DataFrame,
    n_splits: int = 5,
    embargo_pct: float = 0.0,
) -> pd.DataFrame:
    """Diagnostic summary of a purged K-fold split.

    Returns one row per fold with: test_size, train_size, purged_size,
    embargoed_size, test_window_start, test_window_end. Useful for
    spot-checking that purging actually removed overlapping samples
    rather than failing silently."""
    n = len(events)
    if n == 0:
        return pd.DataFrame(columns=[
            "fold", "test_size", "train_size", "purged_size",
            "embargoed_size", "test_window_start", "test_window_end",
        ])

    fold_size = n // n_splits
    rows = []
    for fold_idx, (train_idx, test_idx) in enumerate(
        purged_kfold_indices(events, n_splits=n_splits, embargo_pct=embargo_pct)
    ):
        test_start, test_end = test_idx[0], test_idx[-1] + 1
        # Pre-purge candidate train pool (everything outside test fold + embargo)
        embargo_n = int(np.ceil(n * embargo_pct)) if embargo_pct > 0 else 0
        embargo_end = min(test_end + embargo_n, n)
        n_candidates = test_start + (n - embargo_end)
        purged_n = n_candidates - len(train_idx)
        rows.append({
            "fold": fold_idx,
            "test_size": len(test_idx),
            "train_size": len(train_idx),
            "purged_size": purged_n,
            "embargoed_size": embargo_end - test_end,
            "test_window_start": events.index[test_idx[0]],
            "test_window_end": events["exit_time"].iloc[test_idx].max(),
        })
    return pd.DataFrame(rows)
