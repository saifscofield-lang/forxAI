# Decision — Retire `ml_direct` (2026-06-02)

**Decision:** Permanently retire the `ml_direct` strategy. Removed from
`scripts/paper_trade.py` registration (commented, with re-enable conditions).
**Status:** RETIRED — not archived; the model files and class remain for
reference, but the live system no longer trades it.

## Why

`ml_direct` was the largest single source of live trades during STABLE_v2
(6 of 7 freeze trades), yet a four-phase evidence chain shows it has **no
predictive edge** — neither in its original form nor in a properly-designed
rebuild.

| Phase | Test | Result |
|---|---|---|
| 1c | Live confidence vs real outcome | Flat ~39% win across ALL confidence bins; EV ≈ −0.05 ATR (break-even 40%). The 0.55 threshold was meaningless. |
| 2a | Direction vs volatility predictability | Direction AUC ≈ **0.51** (coin flip); volatility AUC ≈ 0.80. Features predict *whether* price moves, not *which way*. |
| 2b | Leakage / luck controls | Validated: permutation → 0.50, positive control → 1.00, stable across 3 walk-forward folds and horizons 1/6/24, purged. The 0.51/0.80 split is real and leakage-free. |
| 2c | Rebuild as meta-labeling trade filter | Filter AUC **0.468** (< 0.50), gated PF (0.95) < ungated (0.99) in all 3 folds, permutation 0.50. Failed every acceptance criterion. |

**Root cause:** the available technical features carry volatility/regime
information but essentially **no directional information**. Both uses of ML here
depend on direction — predicting it (old design) or judging whether a
directional trade wins (filter rebuild) — so neither can work. This is a
property of the data, not a tuning bug.

## What replaces it

Nothing needs to. The frequency goal is served by **MACD on M15** (Rescue
Phase 1f, shipped in commit `7ce122e`): ~4.8× more trades than H1 at held PF.
ml_direct was never a positive-edge contributor, so removing it does not cost
expected value — it removes a near-break-even/negative source and concentrates
the system on its rule-based, positive-edge components.

## Re-enable conditions (high bar, deliberately)

Do **not** re-enable by retraining on the same features. Re-enabling requires
BOTH:
1. **Genuinely directional inputs** the current set lacks — e.g. multi-timeframe
   trend structure, order-flow / COT positioning, cross-pair lead-lag, or
   news/sentiment — added and shown to lift direction AUC meaningfully above 0.52
   out-of-sample.
2. **An OOS edge above break-even** meeting the acceptance criteria in
   `docs/research/ml_direct_rebuild_design.md` (gated PF ≥ ungated + 0.15,
   ≥ 1.10 absolute, ≥ 40 trades/symbol-yr, across ≥ 2 of 3 walk-forward folds).

## Operational follow-up (live environment)

- The local checkout DB is stale; record this retirement in the **live tracker
  DB** `decisions_log` (category STRATEGY) and flip ml_direct to RETIRED in any
  strategy-status table.
- After `git pull` + engine restart on the live machine, confirm the scan log no
  longer registers `ml_direct` and that open ml_direct positions (if any) are
  managed to close under the existing monitor logic (no new ml_direct entries).
- XAUUSD ml_direct was already blacklisted (2026-04-10); this retirement makes
  that moot.

## Code change

- `scripts/paper_trade.py`: import + registration block commented with dated
  reason and re-enable conditions (mirrors how bollinger_bounce / ml_filtered
  were retired).
- No engine, risk, or model files changed. Fully reversible by uncommenting.

## Cross-references
- `docs/research/rescue_phase1c_ml_calibration.md`
- `docs/research/rescue_phase2a_ml_diagnosis.md`
- `docs/research/rescue_phase2b_ml_validation.md`
- `docs/research/rescue_phase2c_ml_filter_results.md`
- `docs/research/ml_direct_rebuild_design.md`
