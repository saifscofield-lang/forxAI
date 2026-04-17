# Phase 5 Step 6 — Feature Importance Analysis

_Generated: 2026-04-17T11:08:08_  
_Data: 40,000 labeled rows · 5 pairs · H1 · 2020-01-01 → 2026-04-01_  
_Label: triple-barrier · horizon=24 bars · SL/TP=1.5/2.5 ATR_

## Summary

- **Original features:** 82
- **Redundant (Spearman > 0.85) clusters dropped:** 42 features
- **Final shortlist:** 20 features
- **PCA:** 17 components explain 90% variance (suggests 17–22 effective dimensions)

## Recommended shortlist for v3.0 Meta-Labeler

| # | Feature | MDI | SFI (AUC) | Consensus rank |
|---|---------|-----|-----------|----------------|
| 1 | `sma_20_100_diff` | 0.0331 | 0.5112 | 4.0 |
| 2 | `sma_50_200_diff` | 0.0622 | 0.5060 | 5.5 |
| 3 | `ema_26` | 0.0300 | 0.4923 | 7.0 |
| 4 | `atr_14_pct` | 0.0156 | 0.5098 | 10.5 |
| 5 | `spread_vs_atr` | 0.0183 | 0.5077 | 10.5 |
| 6 | `close_vs_sma_100` | 0.0283 | 0.5056 | 11.5 |
| 7 | `volatility_20` | 0.0251 | 0.5033 | 21.0 |
| 8 | `roc_20` | 0.0104 | 0.4946 | 21.0 |
| 9 | `dist_from_low_20` | 0.0091 | 0.4937 | 21.5 |
| 10 | `macd_hist_lag1` | 0.0095 | 0.5043 | 27.5 |
| 11 | `rsi_14_lag3` | 0.0067 | 0.4937 | 27.5 |
| 12 | `dow_cos` | 0.0071 | 0.5031 | 36.0 |
| 13 | `atr_14` | 0.0126 | 0.5016 | 38.5 |
| 14 | `close_vs_sma_10` | 0.0056 | 0.4961 | 39.0 |
| 15 | `return_1_lag3` | 0.0028 | 0.4932 | 39.5 |
| 16 | `close_vs_sma_20` | 0.0059 | 0.4969 | 40.0 |
| 17 | `upper_shadow_ratio` | 0.0044 | 0.5041 | 42.5 |
| 18 | `session_london` | 0.0004 | 0.5063 | 43.0 |
| 19 | `hour_cos` | 0.0055 | 0.5028 | 45.0 |
| 20 | `consecutive_direction` | 0.0015 | 0.5047 | 48.0 |

## Top 10 by MDI (raw, no redundancy filter)

| Feature | MDI |
|---------|-----|
| `sma_50_200_diff` | 0.0622 |
| `sma_200` | 0.0468 |
| `ema_50` | 0.0378 |
| `close_vs_sma_200` | 0.0364 |
| `macd_signal` | 0.0346 |
| `sma_100` | 0.0334 |
| `sma_20_100_diff` | 0.0331 |
| `ema_12` | 0.0329 |
| `sma_50` | 0.0320 |
| `atr_28_pct` | 0.0310 |

## Top 10 by SFI (single-feature AUC)

Closer to 0.5 = no signal. Above 0.55 = real signal. Above 0.60 = strong.

| Feature | AUC |
|---------|-----|
| `sma_20_100_diff` | 0.5112 |
| `atr_14_pct` | 0.5098 |
| `spread_vs_atr` | 0.5077 |
| `session_london` | 0.5063 |
| `sma_50_200_diff` | 0.5060 |
| `close_vs_sma_100` | 0.5056 |
| `consecutive_direction` | 0.5047 |
| `atr_28_pct` | 0.5044 |
| `macd_hist_lag1` | 0.5043 |
| `upper_shadow_ratio` | 0.5041 |

## Redundant feature clusters (kept the highest-ranked from each)

- `return_1` ⇄ `candle_direction`, `rsi_14_change`
- `return_5` ⇄ `close_vs_sma_10`, `roc_5`
- `return_10` ⇄ `close_vs_sma_20`, `rsi_7`, `roc_10`, `bb_position`, `rsi_7_dist_50`
- `return_20` ⇄ `ema_12_26_diff`, `rsi_14`, `rsi_21`, `macd_line`, `roc_20`, `rsi_14_dist_50`
- `sma_10` ⇄ `sma_20`, `sma_50`, `sma_100`, `sma_200`, `ema_12`, `ema_26`, `ema_50`
- `close_vs_sma_50` ⇄ `close_vs_sma_100`, `sma_10_50_diff`, `macd_signal`, `price_position_50`, `rsi_14_lag1`, `rsi_14_lag2`
- `close_vs_sma_200` ⇄ `sma_50_200_diff`
- `macd_hist` ⇄ `macd_hist_lag1`, `macd_hist_lag2`, `macd_hist_vs_atr`
- `atr_7` ⇄ `atr_14`, `atr_28`
- `atr_7_pct` ⇄ `atr_14_pct`, `atr_28_pct`, `volatility_10`
- `candle_body_ratio` ⇄ `body_vs_atr`
- `price_position_20` ⇄ `dist_from_high_20`, `dist_from_low_20`, `price_vs_high_20_atr`, `price_vs_low_20_atr`

## How to read this

- **MDI** is fast but biased toward features with many split points. Trust it for ranking but not for absolute magnitude.
- **SFI** is the unbiased per-feature predictive power. AUC < 0.52 means the feature alone has near-zero edge.
- **Consensus rank** combines both. Lower = better.
- **Correlation clusters** identify near-duplicate features. v3.0 should use only one representative per cluster to reduce noise and improve interpretability.

## Next action

Use this shortlist as the FEATURES list when implementing `ml/meta_labeler.py` (Phase 7, days 6-7). Re-run this analysis after Triple Barrier labeling on actual primary signals (not on every bar) — the ranking may shift when labels come from MACD/RSI signals instead of every H1 bar.
