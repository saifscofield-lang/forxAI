# Phase 5 Step 7 — Feature Importance on Primary Signals

_Re-ran MDI + SFI on signal-conditioned subset (1,017 rows, binary meta-label)_

This ranking matters more than step 6's every-bar ranking — these are the features that distinguish good from bad MACD/RSI signals, not random H1 bars.

## Top 20 features for v3.0 Meta-Labeler

| # | Feature | MDI | SFI (AUC) | Consensus rank |
|---|---|---:|---:|---:|
| 1 | `candle_body_ratio` | 0.0286 | 0.5405 | 1.5 |
| 2 | `price_position_50` | 0.0156 | 0.4717 | 12.5 |
| 3 | `lower_shadow_ratio` | 0.0170 | 0.5237 | 13.0 |
| 4 | `close_vs_sma_200` | 0.0164 | 0.4760 | 13.5 |
| 5 | `macd_hist` | 0.0147 | 0.5343 | 13.5 |
| 6 | `volatility_10` | 0.0185 | 0.5211 | 14.5 |
| 7 | `price_vs_high_20_atr` | 0.0247 | 0.5189 | 15.0 |
| 8 | `rsi_14_lag1` | 0.0139 | 0.4740 | 19.5 |
| 9 | `rsi_14_lag2` | 0.0164 | 0.5167 | 21.5 |
| 10 | `macd_hist_lag1` | 0.0178 | 0.5132 | 22.0 |
| 11 | `volume_ratio` | 0.0144 | 0.5237 | 22.0 |
| 12 | `atr_28_pct` | 0.0134 | 0.5245 | 22.5 |
| 13 | `price_position_10` | 0.0186 | 0.4883 | 23.0 |
| 14 | `volume_change` | 0.0159 | 0.5143 | 24.5 |
| 15 | `body_vs_atr` | 0.0138 | 0.5221 | 25.0 |
| 16 | `atr_ratio_20` | 0.0146 | 0.4810 | 26.0 |
| 17 | `macd_hist_change` | 0.0118 | 0.5266 | 26.0 |
| 18 | `ema_12` | 0.0132 | 0.5227 | 26.5 |
| 19 | `return_5` | 0.0175 | 0.4890 | 26.8 |
| 20 | `dist_from_high_20` | 0.0139 | 0.5205 | 27.0 |

## Comparison to step 6 (every-bar)

Step 6 found all SFI AUCs in [0.49, 0.51] — random. If step-7 SFI AUCs are higher (e.g., several > 0.55), the meta-labeling architecture has measurable signal to work with.

- Features with SFI AUC > 0.55: **0**
- Features with SFI AUC > 0.53: **3**
- Best SFI AUC: **0.5405** (`candle_body_ratio`)

## Verdict

❌ **No measurable signal even at signal-conditioned level**. Reconsider: maybe MACD/RSI primary signals are noise too. Investigate before building meta-labeler.
