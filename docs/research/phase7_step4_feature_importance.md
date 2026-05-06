# Phase 7 Step 4 — Feature Importance Run

**Date:** 2026-05-06  
**Re-runnable:** `python scripts/run_feature_importance.py`  
**Output:** the **20 final features** below + `artifacts/phase7_step4_feature_ranking_2026-05-06.csv`

## Pipeline

- Symbols: EURUSD, GBPUSD, USDJPY, XAUUSD, AUDUSD, USDCHF (6 of 6 v3 instruments)
- Timeframe: H1  ·  bars per symbol: 5,000
- Triple-barrier labels: TP=2.0×ATR, SL=1.0×ATR, hold=24 bars
- Total labelled rows after dropna: **28,803**
- Positive class share: 31.7%
- Total features evaluated: **82**
- Wall time: 58.3s

## MDI top 20 (LightGBM gain)

| Rank | Feature | MDI |
|---:|---|---:|
| 1 | `sma_200` | 0.0878 |
| 2 | `sma_50_200_diff` | 0.0835 |
| 3 | `atr_28` | 0.0828 |
| 4 | `close_vs_sma_100` | 0.0576 |
| 5 | `sma_20_100_diff` | 0.0542 |
| 6 | `sma_100` | 0.0496 |
| 7 | `day_of_week` | 0.0479 |
| 8 | `close_vs_sma_200` | 0.0429 |
| 9 | `hour` | 0.0349 |
| 10 | `sma_10_50_diff` | 0.0299 |
| 11 | `dist_from_low_20` | 0.0280 |
| 12 | `ema_12` | 0.0231 |
| 13 | `sma_50` | 0.0218 |
| 14 | `atr_14_pct` | 0.0203 |
| 15 | `bb_width` | 0.0202 |
| 16 | `sma_20` | 0.0190 |
| 17 | `atr_ratio_20` | 0.0187 |
| 18 | `return_20` | 0.0182 |
| 19 | `ema_50` | 0.0175 |
| 20 | `volatility_20` | 0.0165 |

## SFI on top 30 MDI candidates (3-fold CV accuracy)

SFI evaluates each feature in isolation — cross-checks MDI's susceptibility to the substitution effect. Mean accuracy across 30 features: **0.680** (range 0.660–0.683).

Top 10 by SFI:

| Rank | Feature | Mean accuracy | Std |
|---:|---|---:|---:|
| 1 | `sma_200` | 0.6833 | ±0.0000 |
| 2 | `day_of_week` | 0.6833 | ±0.0000 |
| 3 | `hour` | 0.6833 | ±0.0000 |
| 4 | `dow_sin` | 0.6833 | ±0.0000 |
| 5 | `volatility_10` | 0.6830 | ±0.0001 |
| 6 | `macd_hist` | 0.6828 | ±0.0006 |
| 7 | `close_vs_sma_100` | 0.6827 | ±0.0011 |
| 8 | `volume_ratio` | 0.6826 | ±0.0004 |
| 9 | `atr_ratio_20` | 0.6825 | ±0.0008 |
| 10 | `sma_20_100_diff` | 0.6824 | ±0.0025 |

## PCA dimensionality

With standardised features and 95% explained-variance threshold, **23** principal components capture 95% of the variance out of 82 original features. Effective dimensionality ≈ 28% of the raw feature count — some features carry redundant information.

## Final 20 features (combined MDI + SFI rank)

Combined rank: each feature's MDI rank and SFI rank are averaged (equal weights), and the smallest combined rank wins. Features in both rankings.

| Rank | Feature |
|---:|---|
| 1 | `sma_200` |
| 2 | `day_of_week` |
| 3 | `close_vs_sma_100` |
| 4 | `hour` |
| 5 | `sma_20_100_diff` |
| 6 | `dist_from_low_20` |
| 7 | `dow_sin` |
| 8 | `sma_100` |
| 9 | `sma_10_50_diff` |
| 10 | `sma_50_200_diff` |
| 11 | `atr_ratio_20` |
| 12 | `atr_28` |
| 13 | `close_vs_sma_200` |
| 14 | `volatility_10` |
| 15 | `bb_width` |
| 16 | `volatility_20` |
| 17 | `volume_ratio` |
| 18 | `return_20` |
| 19 | `sma_50` |
| 20 | `macd_hist` |

## Methodology notes

- **Single direction (BUY) for ranking.** The triple-barrier labels are
  computed for BUY events. Tree-based models extract the same
  feature-importance information regardless of direction; SELL would
  produce a mirrored ranking. The Phase 7 meta-labeler (Step 6) will
  use this feature set for both directions.
- **Multi-symbol unified training.** Features are computed per symbol
  (so e.g. RSI is symbol-agnostic in interpretation) and the model
  learns which features generalise. A symbol-stratified version would
  produce per-symbol rankings; that's a separate analysis.
- **Walk-forward 80/20 split** for the LightGBM training validation.
  No purging applied here because we're ranking, not evaluating
  generalisation. Phase 7 Step 2's purged_cv would apply for any
  outcome prediction we run on this feature set later.
- **MDI uses gain, not split-count.** Per LightGBM convention; gain
  is more interpretable as 'feature contribution to loss reduction'.

## What this does NOT decide

- Whether the meta-labeler should use these 20 features verbatim or
  add interaction terms / regime indicators.
- Whether the same feature set works for both BUY and SELL
  directions in the meta-labeler.
- The α / β / γ training-corpus choice (separate kickoff decision).

## Cross-references

- `features/labels/triple_barrier.py` — Phase 7 Step 1

- `ml/purged_cv.py` — Phase 7 Step 2

- `features/importance/feature_selector.py` — Phase 7 Step 5

- `artifacts/phase7_step4_feature_ranking_2026-05-06.csv` — full per-feature ranking
