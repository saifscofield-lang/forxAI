# Phase 12b — Cross-Asset Trend Premium (CORRECTED re-test) — RESULTS

Per frozen pre-reg (commit d7b2910). Pruned 21-instrument universe, canonical G1-G8.
Verdict computed separately by scripts/guardian_assess.py (deterministic engine).

## Universe
- Included: 21 instruments / 7 classes
- Train: 2001-02-28..2024-06-30 (281 mo)
- OOS  : 2024-07-31..2026-06-30 (24 mo)

## Metrics (train window, for canonical G1-G8)

- mean +0.2095%/mo  t=+3.02  Sharpe=+0.62  n=281
- OOS  mean +0.2607%  Sharpe=+0.90  drift_p=1.00
- regimes: half1:+0.206% half2:+0.213% era_pre2015:+0.243% era_2015plus:+0.160%
- breadth: 6/7 classes positive  [ag:-0.057 bonds:+0.081 crypto:+1.017 energy:+0.146 equity:+0.359 fx:+0.098 metals:+0.251]
- cost: net@1.5x +0.2079%/mo  PF=1.60  beats_passive=True (B&H Sharpe +0.50)
- diversification: ENB 12.05/21  PC1 0.15  max|corr| 0.70 (diagnostic only)

