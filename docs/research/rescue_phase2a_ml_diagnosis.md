# Rescue Plan — Phase 2a: ml_direct Root-Cause Diagnosis

**Question:** can the feature set predict DIRECTION, or only VOLATILITY?
Two fresh LightGBM models, same features, 80/20 time split (OOS).

- **AUC 0.50 = no skill (coin flip). >0.55 = real signal.**
- Accuracy compared to the majority-class baseline.

| Symbol | Dir acc | Dir AUC | (base) | Vol acc | Vol AUC | (base) |
|---|---:|---:|---:|---:|---:|---:|
| EURUSD | 0.520 | **0.521** | 0.507 | 0.747 | **0.824** | 0.558 |
| GBPUSD | 0.504 | **0.502** | 0.514 | 0.736 | **0.799** | 0.549 |
| USDJPY | 0.524 | **0.513** | 0.524 | 0.828 | **0.806** | 0.821 |

**Mean direction AUC = 0.512 | Mean volatility AUC = 0.810**

## Verdict & rebuild guidance

- If **direction AUC ≈ 0.50** and **volatility AUC > 0.55**: confirmed — the features (ATR, hour, session) predict WHETHER price moves, not WHICH WAY. `ml_direct` was built to predict direction from non-directional features, so it is structurally incapable of an edge. This is why calibration was flat (Phase 1c).

### How to rebuild WITHOUT repeating the mistake

1. **Stop predicting direction from TA features.** The data says it isn't there. Either (a) repurpose the model as a **tradability/volatility filter** on the rule-based directional strategies (MACD etc.) — play to what it CAN predict; or (b) bring genuinely directional inputs (multi-TF trend structure, momentum persistence, order-flow/COT, cross-pair lead-lag) before attempting direction again.
2. **Align target with execution** (ordered triple-barrier at the real ATR SL/TP, Phase 1b) — never the 6-bar min-move proxy.
3. **Calibrate probabilities** (isotonic on validation) so a threshold means a true probability; gate live only above a proven OOS edge.
4. **Judge on trade EV, not classification accuracy** — accuracy here was inflated by the majority NO_TRADE class while directional precision stayed < 0.50.
- If instead direction AUC > 0.55 somewhere, that symbol/feature is worth a focused rebuild; pursue it rather than a blanket model.