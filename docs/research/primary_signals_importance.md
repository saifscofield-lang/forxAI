# Phase 5 Step 7 — Feature Importance on Primary Signals

_Re-ran MDI + SFI on signal-conditioned subset (521 rows, binary meta-label)_

This ranking matters more than step 6's every-bar ranking — these are the features that distinguish good from bad MACD/RSI signals, not random H1 bars.

## Top 20 features for v3.0 Meta-Labeler

| # | Feature | MDI | SFI (AUC) | Consensus rank |
|---|---|---:|---:|---:|
| 1 | `volatility_10` | 0.0408 | 0.5817 | 1.0 |
| 2 | `volatility_20` | 0.0403 | 0.5688 | 3.0 |
| 3 | `atr_28_pct` | 0.0179 | 0.5809 | 7.0 |
| 4 | `macd_signal` | 0.0234 | 0.5519 | 8.5 |
| 5 | `sma_10_50_diff` | 0.0200 | 0.5556 | 9.5 |
| 6 | `macd_hist_lag3` | 0.0205 | 0.5462 | 11.0 |
| 7 | `macd_line` | 0.0209 | 0.5406 | 13.5 |
| 8 | `volume_change` | 0.0225 | 0.5403 | 13.5 |
| 9 | `atr_14_pct` | 0.0140 | 0.5727 | 14.5 |
| 10 | `macd_hist_lag2` | 0.0155 | 0.4478 | 17.0 |
| 11 | `candle_body_ratio` | 0.0202 | 0.5380 | 18.0 |
| 12 | `hour` | 0.0149 | 0.5461 | 20.0 |
| 13 | `close_vs_sma_50` | 0.0134 | 0.5467 | 22.0 |
| 14 | `return_1_lag2` | 0.0121 | 0.5558 | 23.0 |
| 15 | `atr_ratio_20` | 0.0202 | 0.4745 | 25.0 |
| 16 | `atr_7` | 0.0145 | 0.4606 | 25.0 |
| 17 | `upper_shadow_ratio` | 0.0126 | 0.4564 | 27.0 |
| 18 | `return_10` | 0.0113 | 0.5655 | 27.2 |
| 19 | `ema_12_26_diff` | 0.0134 | 0.5368 | 28.5 |
| 20 | `price_position_20` | 0.0164 | 0.5247 | 30.0 |

## Comparison to step 6 (every-bar)

Step 6 found all SFI AUCs in [0.49, 0.51] — random. If step-7 SFI AUCs are higher (e.g., several > 0.55), the meta-labeling architecture has measurable signal to work with.

- Features with SFI AUC > 0.55: **9**
- Features with SFI AUC > 0.53: **27**
- Best SFI AUC: **0.5817** (`volatility_10`)

## Verdict

✅ **Strong meta-labeler signal**. The pivot to filtering primary signals is validated by data — multiple features have measurable predictive power on signal quality.
