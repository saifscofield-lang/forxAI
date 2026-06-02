# Design — Rebuild `ml_direct` as a Trade Filter (Meta-Labeling)

**Author:** Rescue Plan, Phase 2 (2026-06-02)
**Status:** DESIGN — not yet implemented. Build behind shadow mode first.
**Supersedes:** the direction-predicting `MLDirectStrategy` (no edge — see evidence).

---

## 1. Why we are rebuilding (evidence, not opinion)

Three independent, validated findings kill the old design and point to the new one:

| Finding | Evidence | Implication |
|---|---|---|
| `ml_direct` confidence is meaningless | Phase 1c: flat ~39% win across all confidence bins; EV ≈ −0.05 ATR | The 0.55 threshold filters quantity, not quality |
| The label was misaligned with execution | Phase 1b: trained on 6-bar min-move, traded on ATR SL/TP; 32% of labels optimistic | Target must match the real exit |
| **The features predict volatility, not direction** | Phase 2a/2b: direction AUC ≈ 0.51 (coin flip), volatility AUC ≈ 0.80, **validated leakage-free** (permutation→0.50, positive control→1.00, stable across folds & horizons) | **Do not predict direction.** Predict tradability and let a rule strategy supply direction. |

**Conclusion:** stop asking the model "which way?" (it cannot know). Ask it
"is this a good trade to take?" — which depends on volatility/regime, exactly
what the features DO predict.

## 2. New role — meta-labeling filter

We adopt **meta-labeling** (López de Prado): a *primary* model decides
direction, a *secondary* model decides whether to act.

```
MACD Crossover (primary)  →  direction (BUY/SELL) + SL/TP   [proven, if thin, edge]
        │
        ▼
ml_filter (secondary)     →  P(this trade hits TP before SL)  [the rebuild]
        │
        ▼
take the trade only if  P(win) ≥ calibrated_threshold
```

The ML never invents a trade. It only **vetoes or passes** trades that MACD
already generated. This plays to the model's real strength (volatility/regime
discrimination) and removes the impossible task (direction).

## 3. Target (label) — aligned with the real trade

For every historical MACD signal, label the **actual outcome** under the real
exits, using the ordered triple-barrier (the correct labeler in
`features/ml/label_engine.py`, NOT the old `market_learner.create_labels`):

- Replay `macd_crossover` over all `data/raw/{SYMBOL}/M15.parquet` history
  (M15 — the timeframe MACD now trades, per Phase 1f).
- For each signal: simulate entry → first touch of `SL = price ∓ 2.5×ATR` or
  `TP = price ± 3.5×ATR` (MACD's real multipliers) within a max horizon.
  - TP first → label **1 (WIN)**
  - SL first → label **0 (LOSS)**
  - neither within horizon → label by sign of final P&L (or drop; decide in build)
- This yields one labeled row **per MACD signal** (thousands across 16y × 7
  symbols), each with features captured at signal time.

This single change fixes the Phase 1b mismatch: the model now learns exactly
the thing we trade.

## 4. Features

Reuse `features/ml/feature_engine.build_features` (66 causal features) — all
verified backward-looking in Phase 2b. **Emphasize / ensure presence of the
features that carry real signal** (volatility & regime):

- Volatility: `atr_14`, `atr_28`, `atr_*_pct`, `atr_ratio_20`, `volatility_*`,
  `bb_position`, `body_vs_atr`.
- Regime/trend context: ADX and trend label from `get_current_regime`,
  `sma_50_200_diff`, `close_vs_sma_200`, H4 trend (the engine already computes
  these — pass them in).
- Timing: `hour_sin/cos`, `session_*`, `day_of_week` (these had high importance).
- **Add MACD's own signal context** as features: `macd_hist`, `macd_hist_vs_atr`,
  histogram momentum, distance of price from EMA50/200 — so the filter can
  judge *this specific* MACD setup, not just generic conditions.

Do NOT add features hoping to predict direction; the meta-label is win/loss of
an already-directional trade, so volatility/regime features are appropriate.

## 5. Model & calibration

- **LightGBM binary** classifier, objective `binary`, early stopping on a
  time-separated validation block.
- **Probability calibration** (isotonic regression) fit on the validation block
  so `P(win)=0.6` means a true 60% — fixes the Phase 1c flat-confidence problem.
- Class imbalance: MACD win rate ≈ 42%, so classes are near-balanced — no heavy
  reweighting needed; monitor anyway.

## 6. Validation protocol (mandatory before any live use)

- **Walk-forward, purged + embargoed** by the trade horizon at every train/test
  boundary (fixes the Phase 1 boundary-leak gap).
- **Permutation control** every run: shuffle labels → AUC must collapse to 0.50.
  If not, stop — leakage.
- Report, per fold: filter AUC, and the **gated vs ungated MACD economics** —
  trades, win%, R-PF, net R.

## 7. Gating threshold

Choose the `P(win)` cutoff on the validation set to **maximise expected value**
subject to a **minimum trade-count floor** (we just bought frequency via M15;
the filter must not throw it all away):

```
EV(thr) = mean over passed trades of [ p·TP_R − (1−p)·SL_R ]
choose thr* = argmax EV(thr)  s.t.  trades_passed(thr) ≥ floor
```

## 8. Acceptance criteria (go/no-go for live)

The rebuilt filter ships ONLY if, out-of-sample (walk-forward):

1. **PF lift:** gated MACD R-PF ≥ ungated MACD R-PF **+ 0.15** (meaningful, not noise).
2. **Edge above break-even:** gated R-PF ≥ 1.10.
3. **Frequency retained:** gated trades/symbol-yr ≥ 40 (keeps the M15 frequency gain meaningful).
4. **Calibration sound:** reliability curve roughly diagonal; permutation AUC ≈ 0.50.
5. **Robustness:** criteria 1–3 hold in ≥ 2 of 3 walk-forward folds (not one lucky window).

If it fails, ml_direct stays **retired** (don't force it) and frequency rests on
MACD-M15 alone. That is an acceptable outcome — better than shipping a fake edge.

## 9. Integration

- New class `strategies/ml_filter.py` (or extend the engine) implementing
  `should_take(signal, features) -> (bool, p_win)`.
- In `trading_engine` scan loop: after a MACD signal passes the existing quality
  filters, call the ML filter; reject with reason `ML_FILTER_LOW_PROB` (logged to
  `signal_logs`/shadow so we can audit it later, exactly like other filters).
- Retire the standalone `MLDirectStrategy` direction signals (remove from
  registration in `scripts/paper_trade.py`).
- Per-symbol models in `models/ml_filter/{SYMBOL}.pkl` with bundled calibrator
  + `feature_cols` + metadata (trained_at, OOS metrics, threshold).

## 10. Rollout — shadow first

1. **Shadow mode:** compute `P(win)` and the would-pass/would-reject decision for
   every live MACD signal, **log it but still take the trade**. After ~30–50
   MACD trades, compare realized win% of would-pass vs would-reject. This
   validates the filter on live data before it can block anything.
2. **Activate** only if shadow confirms separation (would-pass win% materially
   > would-reject).
3. Weekly checkpoint; revert by disabling the filter call (one flag).

## 11. Reversibility & risk

- The filter is a single gate; disable via config flag → system reverts to
  MACD-M15 with all current filters. No data migration.
- **Risk:** the filter may over-restrict and erase the M15 frequency gain — the
  trade-count floor (criterion 3) and shadow mode guard against this.
- **Risk:** meta-label edge may not exist (MACD's base edge is thin). The
  acceptance criteria are designed to catch this and keep ml_direct retired
  rather than ship noise.

## 12. Mistakes this design explicitly avoids

| Old mistake | Fix here |
|---|---|
| Predicting direction from non-directional features | Direction comes from MACD; ML predicts win/loss only |
| Label (6-bar min-move) ≠ traded exit | Meta-label IS the real ordered ATR SL/TP outcome |
| Uncalibrated confidence, arbitrary 0.55 | Isotonic calibration + EV-maximising threshold |
| Judged by classification accuracy (inflated by NO_TRADE) | Judged by gated trade EV / R-PF |
| No purge/embargo, single split | Purged walk-forward + permutation control every run |
| Shipped live on backtest hope | Shadow mode on live signals before it can block |

## 13. Cross-references
- `docs/research/rescue_phase1c_ml_calibration.md` — flat confidence
- `docs/research/rescue_phase1b_label_audit.md` — label/exit mismatch
- `docs/research/rescue_phase2a_ml_diagnosis.md` — direction vs volatility
- `docs/research/rescue_phase2b_ml_validation.md` — leakage controls
- `features/ml/label_engine.py` — the correct ordered triple-barrier labeler
- `scripts/validate_m15_frequency.py` — MACD-M15 baseline to beat
