# AI-001 Path A — XAUUSD `class_weight='balanced'` retraining

**Date:** 2026-05-06  
**Re-runnable:** `python scripts/retrain_xauusd_balanced.py`  
**Outputs:** `models\market_learner\XAUUSD_model_balanced.pkl`, `models\market_learner\XAUUSD_metrics_balanced.json`, this file.

## What this commit does

Reruns the existing XAUUSD training pipeline (`ml/market_learner.py`) with one minimum-impact change: sample weights derived from `sklearn.utils.class_weight.compute_class_weight('balanced', ...)`. All other params, the train/val/test split, and the feature pipeline are unchanged. The new model is saved alongside the old (NOT overwriting); the engine still loads the old model. Deployment is the project lead's decision after reviewing this report.

## Per-class metrics (test set, walk-forward split)

| Class | Old recall | **New recall** | Old precision | **New precision** |
|---|---:|---:|---:|---:|
| SELL | 0.767 | **0.935** | 0.429 | **0.407** |
| NO_TRADE | 0.559 | **0.004** | 0.457 | **0.462** |
| BUY | 0.109 | **0.081** | 0.463 | **0.527** | ← ✗

Overall accuracy: old **0.438**, new **0.415**.

## Prediction-class distribution on recent test bars

On the most recent **200** test bars:

| Metric | Old | **New** |
|---|---:|---:|
| P(BUY) max | 0.483 | **0.407** |
| P(BUY) mean | 0.345 | **0.320** |
| P(SELL) max | 0.653 | **0.535** |
| P(SELL) mean | 0.566 | **0.469** |
| Predicted SELL | 195 | **197** |
| Predicted NO_TRADE | 0 | **0** |
| Predicted BUY | 5 | **3** |

**Verdict: MARGINAL IMPROVEMENT.** The new model produces BUY predictions but at very low frequency. May be acceptable if the precision is high; otherwise consider Path B.

## Top features (new model)

- 1. `atr_28` (importance=38861.9579)
- 2. `hour_cos` (importance=18772.9139)
- 3. `atr_14` (importance=6363.4156)
- 4. `sma_50_200_diff` (importance=4237.1552)
- 5. `session_london` (importance=3393.6020)
- 6. `close_vs_sma_200` (importance=2646.2796)
- 7. `sma_200` (importance=2641.6368)
- 8. `atr_7` (importance=2562.6958)
- 9. `atr_28_pct` (importance=2309.7080)
- 10. `sma_100` (importance=2213.1236)

## Top features (old model, for comparison)

- 1. `atr_28` (importance=114023.3503)
- 2. `hour_cos` (importance=78278.8624)
- 3. `atr_14` (importance=19656.4179)
- 4. `session_london` (importance=9558.7797)
- 5. `sma_50_200_diff` (importance=8861.9621)
- 6. `day_of_week` (importance=8503.1175)
- 7. `close_vs_sma_200` (importance=7944.9509)
- 8. `hour` (importance=7304.9267)
- 9. `atr_7` (importance=6566.9098)
- 10. `sma_200` (importance=6286.4278)

## What this does NOT do

- Deploy the new model. The engine still loads `XAUUSD_model.pkl`. Switching requires the project lead to either rename files, update the loader path, or add a config flag.
- Lift the `ml_direct/XAUUSD` blacklist. That decision is downstream of deployment + AI-005-style holdout validation.
- Address regime balance. Path A treats the issue as a class weighting problem; if the gold regime in the training window is the deeper cause, **Path B** (time-stratified retraining across multiple regimes) is the correct fix.

## Cross-references

- `docs/research/ai001_zero_buy_root_cause.md` — diagnostic phase

- `docs/research/ai005_holdout_validation.md` — OOS holdout for any deployment validation

- `ml/market_learner.py` — original training pipeline

- `models\market_learner\XAUUSD_model.pkl` vs `models\market_learner\XAUUSD_model_balanced.pkl` — side-by-side artefacts
