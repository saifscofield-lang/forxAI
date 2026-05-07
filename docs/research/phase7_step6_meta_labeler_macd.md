# Phase 7 Step 6 — MACD Meta-Labeler

**Date:** 2026-05-07  
**Re-runnable:** `python scripts/train_meta_labeler_macd.py`  
**Model artifact:** `models/meta_labeler/macd_v1.pkl`

## Corpus

- Source: `data/research/primary_signals.parquet` filtered to `strategy=macd_crossover`
- After dropping 105 timeout signals: **710 rows** (TP=282, SL=428)
- Time range: 2020-01-17 11:00:00 → 2026-03-31 18:00:00
- Features used: **20** of 20 from Phase 7 Step 4 ranking

## Validation

- Purged K-Fold (5 splits) with 1% embargo
- Decision threshold: probability ≥ 0.55
- LightGBM (n_est=300, lr=0.05, depth=5, leaves=16, class_weight=balanced)

## Cross-validation summary

| Metric | Value |
|---|---:|
| ROC AUC (mean) | 0.495 ± 0.046 |
| F1 | 0.325 |
| Precision | 0.379 |
| Recall | 0.291 |
| Raw WR | 39.7% |
| Filtered WR | 37.5% |
| WR lift | -2.2pp |
| Keep-rate | 30% (216 of 710) |

## Phase 7 ship-gate (projected on OOS taken signals)

| Metric | Value | Threshold | Verdict |
|---|---:|---:|:---:|
| R-PF | 0.840 | ≥ 1.30 | FAIL |
| $-PF | 1.417 | ≥ 1.00 | PASS |
| **Dual-gate** | — | both | **FAIL** |

## Per-fold detail

| Fold | n_train | n_test | AUC | n_taken | n_wins |
|---:|---:|---:|---:|---:|---:|
| 0 | 560 | 142 | 0.421 | 50 | 19 |
| 1 | 560 | 142 | 0.508 | 46 | 14 |
| 2 | 560 | 142 | 0.508 | 34 | 16 |
| 3 | 560 | 142 | 0.562 | 49 | 19 |
| 4 | 568 | 142 | 0.476 | 37 | 13 |

## Honest reading

- AUC ≈ 0.50 on purged OOS folds means **the classifier has no predictive edge** on this corpus with this feature set.
- Filtered WR (37.5%) is **below** raw WR (39.7%) — selection is not just neutral, it's net-negative on hit rate.
- R-PF = 0.840 fails the 1.30 gate. With WR = 37.5% and a fixed planned R:R of 1.4, the upper bound on R-PF for any selector at this WR is 0.84, so no decision threshold can rescue this fold mix.
- $-PF = 1.417 passes — the model happens to pick larger-magnitude wins (higher-ATR conditions) — but that does NOT compensate for the WR drop in R units, which is what the ship gate is intentionally measuring.

**Step 6 verdict: meta-labeling MACD as-configured does not produce a shippable artifact.** Possible recovery paths, in order of seriousness:
  1. **Path B (regime-stratified retrain)** — split corpus by volatility / trend regime and train one meta-labeler per regime. Already on the Phase 9 follow-up list.
  2. **Richer feature set** — Phase 7 Step 4 used 20 features. Add interaction terms, lagged indicators, or context features (news_nearby, time-of-day-of-week interactions).
  3. **Tighten decision threshold** — at proba ≥ 0.55 the recall is 0.29; raising to 0.60+ trades volume for precision but given AUC ≈ 0.50 there's no monotone improvement to exploit.
  4. **Accept the edge isn't there** — MACD's primary signal may be the entire edge, and a secondary classifier on top is just noise. In that case Phase 7 ship gate routes through a different mechanism (e.g., regime filter as a hard rule, not a learned model).

Compare to the Phase 5 prototype (`docs/research/meta_labeler_prototype.md`): this run uses purged_cv with embargo (stricter), Phase 7 Step 4's feature ranking (newer), and projects the dual ship-gate (closer to live truth). The Phase 5 prototype reported a positive lift at 0.55 threshold using non-purged K-fold; that lift did not survive purging — consistent with label leakage being the source of the prototype's apparent edge.

## Calibration notes (2026-05-07 unit-bug fix)

First run reported R-PF = 2.10 (PASS). Investigation found the `realized_r_for_taken` helper used `rr_ratio` from `primary_signals.parquet` directly, but that column is in **ATR units** (WIN ≈ +3.5, LOSS ≈ −2.5 = TP/SL multipliers), not **R units**. Correct conversion is `rr_ratio / SL_ATR_MULTIPLIER`, which gives WIN = +1.4R, LOSS = −1.0R as expected. The fix is in the script header (`SL_ATR_MULTIPLIER = 2.5`). Future strategies with different SL multipliers (e.g., RSI Step 7) need the same treatment with their own multiplier.

## Next

- **Step 7** — same pipeline against the 329 RSI signals.
- **Step 8** — refactor `ml_filtered_strategy` + engine to load this artifact and gate orders on `proba >= decision_threshold`.
- **Step 10** — full 3-year backtest with the meta-labeler in the loop.
- **Step 11** — ship gate (Jun 8).

## Cross-references

- `ml/purged_cv.py` — Phase 7 Step 2
- `docs/research/phase7_step4_feature_importance.md` — feature shortlist
- `analysis/rr_calculator.py::phase7_ship_gate` — gate definition
- `data/improvements.db` table `meta_labeler_runs` — historical runs