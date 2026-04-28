"""Phase 10.5 step 2: regime filter overlay for TSMOM crypto LO/12w.

Implements the filter described in docs/research/regime_filter_spec.md:
  - basket_return(t) = equal-weighted mean of active crypto asset returns
  - basket_vol(t)    = 4-week rolling stdev of basket_return, annualized
  - threshold        = 80th percentile of basket_vol over training window
                        (2017-08-17 -> 2024-12-31), LOCKED at train-end snapshot
  - filter rule      = zero all strategy weights when basket_vol(t) > threshold,
                        applied at the same 1-week lag as the base strategy

This module exposes three functions (plus a smoke-test __main__):
  compute_basket_vol(weekly_close, window=4) -> Series
  compute_regime_threshold(basket_vol, train_end, percentile=80) -> float
  apply_regime_filter(weights, basket_vol, threshold) -> DataFrame

No full backtest is run here. That is Phase 10.5 step 3 (blocked on user go-ahead).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from research_tsmom_crypto import (
    WEEKS_PER_YEAR,
    load_weekly_close,
    run_backtest,
)

TRAIN_END = pd.Timestamp("2024-12-31")
DEFAULT_PERCENTILE = 80
DEFAULT_WINDOW = 4


# ───────────────────────────── core functions ─────────────────────────────

def compute_basket_returns(weekly_close: pd.DataFrame) -> pd.Series:
    """Equal-weighted basket of weekly simple returns over *active* assets.

    Active at week t == asset has non-NaN weekly returns at week t.
    Weeks with no active asset return NaN.
    """
    ret = weekly_close.pct_change()
    return ret.mean(axis=1, skipna=True)


def compute_basket_vol(weekly_close: pd.DataFrame, window: int = DEFAULT_WINDOW) -> pd.Series:
    """Rolling annualized vol of the equal-weighted basket.

    vol(t) = stdev(basket_return[t-window+1 .. t], ddof=0) * sqrt(52).
    NaN until `window` observations exist.
    """
    basket = compute_basket_returns(weekly_close)
    return basket.rolling(window, min_periods=window).std(ddof=0) * np.sqrt(WEEKS_PER_YEAR)


def compute_regime_threshold(
    basket_vol: pd.Series,
    train_end: pd.Timestamp = TRAIN_END,
    percentile: float = DEFAULT_PERCENTILE,
    min_obs: int = 50,
) -> float:
    """80th-percentile of training-window basket_vol.

    Training window is `basket_vol.index <= train_end`. NaN rows dropped.
    Raises if fewer than `min_obs` observations in training window.
    """
    train = basket_vol.loc[basket_vol.index <= train_end].dropna()
    if len(train) < min_obs:
        raise RuntimeError(
            f"training window has {len(train)} observations, need >= {min_obs}"
        )
    return float(np.percentile(train, percentile))


def apply_regime_filter(
    weights: pd.DataFrame,
    basket_vol: pd.Series,
    threshold: float,
) -> pd.DataFrame:
    """Zero out strategy weights for weeks where basket_vol > threshold.

    `weights` is the DataFrame of per-asset weights already produced by the
    base strategy (including its 1-week lag). We multiply each row by an
    on/off indicator aligned on the weekly index:
        filter_on(t) = 1 if basket_vol(t) <= threshold else 0
    A NaN basket_vol counts as "on" -- we do not filter on missing data.
    """
    on = (basket_vol <= threshold).reindex(weights.index).fillna(True)
    multiplier = on.astype(float)  # 1.0 when keep, 0.0 when zero-out
    return weights.mul(multiplier, axis=0)


# ───────────────────────────── smoke test ─────────────────────────────

def smoke_test() -> None:
    print("=" * 72)
    print("Phase 10.5 step 2 — regime filter overlay smoke test")
    print("=" * 72)

    # 1. Load weekly data
    weekly = load_weekly_close()
    print(f"[load] weekly frame {weekly.shape} | "
          f"{weekly.index.min().date()} -> {weekly.index.max().date()}")

    # 2. Compute basket vol (4-week rolling)
    vol = compute_basket_vol(weekly, DEFAULT_WINDOW)
    first_valid = vol.first_valid_index()
    print(f"[vol]  4w basket vol: first valid {first_valid.date()}, "
          f"{vol.notna().sum()} non-NaN weeks")

    # 3. Threshold from training data ONLY
    threshold = compute_regime_threshold(vol, TRAIN_END, DEFAULT_PERCENTILE)
    print(f"[thr]  80th percentile (train window <= {TRAIN_END.date()}): "
          f"{threshold:.4f} ann. vol  ({threshold*100:.2f}%)")

    # 4. Determinism check — same input, same output
    threshold_2 = compute_regime_threshold(vol, TRAIN_END, DEFAULT_PERCENTILE)
    assert threshold == threshold_2, "threshold non-deterministic"
    print(f"[det]  determinism OK (identical re-compute)")

    # 5. Lookahead check — adding OOS rows must not change threshold
    train_only = vol.loc[vol.index <= TRAIN_END]
    threshold_train_only = compute_regime_threshold(train_only, TRAIN_END, DEFAULT_PERCENTILE)
    assert abs(threshold - threshold_train_only) < 1e-12, (
        f"lookahead leak: full-data threshold {threshold} "
        f"!= train-only threshold {threshold_train_only}"
    )
    print(f"[loo]  no-lookahead OK (train-only and full-data give same threshold)")

    # 6. Apply filter to LO/12w base strategy (no re-backtest, reuse weights only)
    print(f"[run]  running base LO/12w/10bps backtest to get weights ...")
    res = run_backtest(weekly, direction="LO", lookback_w=12, cost_per_side=0.001)
    base_weights = res["weights"]
    gated_weights = apply_regime_filter(base_weights, vol, threshold)

    # 7. Filter-firing diagnostics
    common = base_weights.index.intersection(vol.index)
    vol_on = vol.reindex(common)
    above = (vol_on > threshold) & vol_on.notna()
    train_mask = common <= TRAIN_END
    oos_mask = common >= pd.Timestamp("2025-01-01")
    train_fires = int((above & train_mask).sum())
    train_weeks = int(train_mask.sum())
    oos_fires = int((above & oos_mask).sum())
    oos_weeks = int(oos_mask.sum())
    train_pct = 100 * train_fires / max(train_weeks, 1)
    oos_pct = 100 * oos_fires / max(oos_weeks, 1)
    print()
    print(f"[fire] filter firing (vol > threshold) by window:")
    print(f"         train (<= 2024-12-31) : {train_fires:3d}/{train_weeks:3d} weeks  ({train_pct:5.1f}%)  [target ~20.0%]")
    print(f"         OOS   (>= 2025-01-01) : {oos_fires:3d}/{oos_weeks:3d} weeks  ({oos_pct:5.1f}%)")
    if oos_pct > 40:
        print(f"[WARN] OOS fire rate is {oos_pct:.1f}% — above 40% threshold flagged in spec §8")

    # 8. Weight-change diagnostics: how many weeks actually get zeroed?
    base_gross = base_weights.abs().sum(axis=1)
    gated_gross = gated_weights.abs().sum(axis=1)
    zeroed = ((base_gross > 1e-9) & (gated_gross < 1e-9))
    print(f"[wt]   weeks where base had exposure AND gated zeroes it: {int(zeroed.sum())}")
    print(f"         base mean gross exposure : {base_gross.mean():.4f}")
    print(f"         gated mean gross exposure: {gated_gross.mean():.4f}")

    # 9. Spot-check a filtered week
    if zeroed.any():
        example = zeroed[zeroed].index[-1]  # most recent filtered week
        print(f"[chk]  sample filtered week {example.date()}:")
        print(f"         basket_vol        = {vol.loc[example]:.4f} (threshold {threshold:.4f})")
        print(f"         base weights      = {base_weights.loc[example].to_dict()}")
        print(f"         gated weights     = {gated_weights.loc[example].to_dict()}")

    print()
    print("[OK]   overlay implementation validated. Run `step 3` to evaluate performance.")


if __name__ == "__main__":
    smoke_test()
