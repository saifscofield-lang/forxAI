# Phase 7 Step 7 — RSI Meta-Labeler

**Date:** 2026-05-07  
**Re-runnable:** `python scripts/train_meta_labeler_rsi.py`  
**Model artifact:** `models/meta_labeler/rsi_v1.pkl`

## Corpus

- Source: `data/research/primary_signals.parquet` filtered to `strategy=rsi_reversal`
- After dropping 22 timeout signals: **307 rows** (TP=104, SL=203)
- Time range: 2020-01-22 19:00:00 → 2026-03-23 12:00:00
- Features used: **20** of 20 from Phase 7 Step 4 ranking
- Strategy params: SL = 2.0×ATR, TP = 3.0×ATR, planned R:R = 1.5

## Validation

- Purged K-Fold (5 splits) with 1% embargo
- Decision threshold: probability ≥ 0.55
- LightGBM (n_est=300, lr=0.05, depth=5, leaves=16, class_weight=balanced)

## Cross-validation summary

| Metric | Value |
|---|---:|
| ROC AUC (mean) | 0.579 ± 0.092 |
| F1 | 0.326 |
| Precision | 0.362 |
| Recall | 0.305 |
| Raw WR | 33.9% |
| Filtered WR | 37.6% |
| WR lift | +3.8pp |
| Keep-rate | 28% (85 of 307) |

## Phase 7 ship-gate (projected on OOS taken signals)

| Metric | Value | Threshold | Verdict |
|---|---:|---:|:---:|
| R-PF | 0.906 | ≥ 1.30 | FAIL |
| $-PF | 0.018 | ≥ 1.00 | FAIL |
| **Dual-gate** | — | both | **FAIL** |

## Per-fold detail

| Fold | n_train | n_test | AUC | n_taken | n_wins |
|---:|---:|---:|---:|---:|---:|
| 0 | 242 | 61 | 0.623 | 15 | 4 |
| 1 | 242 | 61 | 0.617 | 20 | 9 |
| 2 | 241 | 61 | 0.702 | 20 | 9 |
| 3 | 242 | 61 | 0.437 | 14 | 2 |
| 4 | 243 | 63 | 0.518 | 16 | 8 |

## Honest reading

- AUC = 0.579 on purged OOS folds — meaningful predictive signal vs random.
- Filtered WR (37.6%) vs raw WR (33.9%): +3.8pp lift.
- R-PF = 0.906 fails the 1.30 gate. With WR = 37.6% and a fixed planned R:R of 1.5, the upper bound on R-PF for any selector at this WR is 0.91 — no decision threshold can rescue this fold mix.
- $-PF = 0.018 (fails the 1.00 gate).

**Step 7 verdict: meta-labeling RSI as-configured does not produce a shippable artifact.** Same recovery options as Step 6 (Path B regime-stratified retrain, richer feature set, threshold tuning, or accept no second-layer edge).

## Comparison to Step 6 (MACD)

| | MACD (Step 6) | RSI (Step 7) |
|---|---:|---:|
| Corpus size | 710 | 307 |
| Raw WR | 39.7% | 33.9% |
| AUC | 0.495 ± 0.046 | 0.579 ± 0.092 |
| WR lift | -2.2pp | +3.8pp |
| R-PF | 0.840 (FAIL) | 0.906 (FAIL) |
| $-PF | 1.417 (PASS) | 0.018 (FAIL) |
| Dual gate | FAIL | **FAIL** |

## Calibration notes

- `rr_ratio` in `primary_signals.parquet` is in **ATR units**. RSI strategy uses SL = 2.0×ATR / TP = 3.0×ATR, so WIN rr_ratio ≈ +3.0 and LOSS ≈ -2.0. Verified empirically 2026-05-07. R-unit conversion divides by SL multiplier (2.0), giving WIN = +1.5R / LOSS = -1.0R.
- Same unit-conversion bug pattern hit Step 6 first; this script applies the fix from the start (see `realized_r_for_taken`).
- **$-PF caveat (uncovered 2026-05-07):** `pnl_price` in the corpus is *raw price* PnL, not dollar PnL. Across heterogeneous symbols this varies 4 orders of magnitude — EURUSD wins ≈ 0.008 (= 80 pips), USDJPY wins ≈ 0.78, XAUUSD wins ≈ 71. So `sum(wins) / sum(|losses|)` on raw `pnl_price` is dominated by whichever symbol the selector happens to pick, not by actual $-outcome. **R-PF is the trustworthy projection** from this corpus; $-PF should be recomputed from live trade ledger or with explicit pip_value × volume normalization. Step 6's $-PF=1.42 PASS and Step 7's $-PF=0.018 FAIL are both unreliable for the same reason. Filed as a follow-up note for Step 10's full-backtest reporting.

## Next

- **Step 8** — refactor `ml_filtered_strategy` + engine to load whichever of (macd_v1, rsi_v1) actually clears the ship gate. If neither does, Step 8 needs a different design (e.g., regime filter as a hard rule).
- **Step 10** — full 3-year backtest with the meta-labeler in the loop.
- **Step 11** — ship gate (Jun 8).

## Cross-references

- `ml/purged_cv.py` — Phase 7 Step 2
- `docs/research/phase7_step4_feature_importance.md` — feature shortlist
- `docs/research/phase7_step6_meta_labeler_macd.md` — MACD parallel
- `analysis/rr_calculator.py::phase7_ship_gate` — gate definition
- `data/improvements.db` table `meta_labeler_runs` — historical runs