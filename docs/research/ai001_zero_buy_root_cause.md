# AI-001 — Zero-BUY on XAUUSD: Root-Cause Diagnostic

**Date:** 2026-05-06
**Author:** automated investigation (Claude Code)
**Trigger action item:** `AI-001` (BLOCKING, Phase 8) — *"Implement XAUUSD BUY-side capability"*
**Phase 8 gate review:** 2026-06-01 (26 days)
**Status:** Diagnostic phase **complete**. Implementation phase (retraining or replacement) **open** — see "Fix paths" below.

## Executive summary (3 bullets)

- The `ml_direct` model on XAUUSD has produced **94 SELL trades and 0 BUY trades** in v3, despite the training data containing **MORE BUY than SELL examples** (5,311 vs 4,632). The asymmetry is in the trained model's **predicted-class distribution**, not the strategy code, the threshold, or the training-set class balance.
- The model's per-class recall is **77% for SELL but only 11% for BUY**. With `argmax`-based class selection, P(BUY) on actual XAUUSD bars **never crosses 40%** (max 37.3%, mean 32.4%) — well below the 55% threshold and always below P(SELL). No threshold tweak can unlock BUY because the model literally never thinks BUY is the most-likely class on XAUUSD.
- The training script (`ml/market_learner.py:163-178`) does NOT pass `class_weight`, `is_unbalance`, or `scale_pos_weight` to LightGBM. With `multi_logloss` as the objective and the gold regime in the training window favouring clean SELL setups, the model collapsed onto SELL because SELL signals were easier to predict in that window. It's a **regime-induced learned bias**, not a labelling bug.

## Evidence

### Strategy code is symmetric

Inspection of `strategies/ml_direct_strategy.py`:

```python
# Lines 31, 70-141: identical thresholds for BUY and SELL
self.confidence_threshold = 0.55
pred_class = int(proba.argmax())          # symmetric
if confidence < self.confidence_threshold: # symmetric
if action == "BUY":                        # SL/TP construction symmetric
    sl = price - atr * self.atr_sl_multiplier
    tp = price + atr * self.atr_tp_multiplier
else:
    sl = price + atr * self.atr_sl_multiplier
    tp = price - atr * self.atr_tp_multiplier
```

No conditional path that biases against BUY. **Strategy is not the source.**

### Probability distribution on real XAUUSD signals

Across **94 XAUUSD `ml_direct` trades** (every trade ever made on this symbol-strategy pair), parsed from `trades.comment`:

| | min | mean | median | max |
|---|---:|---:|---:|---:|
| P(BUY) | 24.9% | **32.4%** | 33.0% | 37.3% |
| P(SELL) | 55.0% | 58.2% | 57.7% | 65.9% |
| P(NO_TRADE) | 7.4% | 9.4% | 9.6% | 11.8% |

**P(BUY) max = 37.3%.** The model never produced a BUY signal because P(BUY) was never the argmax. Lowering the confidence threshold from 0.55 to 0.40 would not help — argmax still picks SELL every time.

| Threshold | Trades that would have been BUY |
|---|---:|
| 55% | 0 |
| 50% | 0 |
| 40% | 0 |
| 30% | 73 (but argmax still picks SELL) |

### Training-data class balance and per-class metrics

From `models/market_learner/XAUUSD_model.pkl::meta`:

| Class | True samples | Predicted | Recall | Precision |
|---|---:|---:|---:|---:|
| SELL | 4,632 (39%) | 8,274 (70%) | **76.7%** | 42.9% |
| NO_TRADE | 1,865 (16%) | 2,282 (19%) | 55.9% | 45.7% |
| BUY | **5,311 (45%)** | **1,252 (11%)** | **10.9%** | 46.3% |

**Training data favoured BUY by 14% (5,311 BUY vs 4,632 SELL), but the model predicts SELL 6.6× more often than BUY.** Overall accuracy 43.8% (random = 33.3% on three classes) — the model is barely better than random because it collapsed onto a single class.

### Training params

`ml/market_learner.py:163-178`:

```python
params = {
    "objective": "multiclass",
    "num_class": 3,
    "metric": "multi_logloss",
    "learning_rate": 0.05,
    "num_leaves": 63,
    "max_depth": 8,
    "min_child_samples": 50,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
    "n_jobs": -1,
    "verbose": -1,
    "seed": 42,
}
```

**No `class_weight`. No `is_unbalance`. No `scale_pos_weight`.** With `multi_logloss` and balanced-ish data, the model is free to take the easy wins. In the gold training window (model trained 2026-03-26), SELL setups clustered cleanly in feature space (high RSI in downtrend, etc.) while BUY setups were sharper and more irregular. Log-loss penalises confident wrong predictions; the model learned "stay away from BUY because errors are costly" → predict SELL or NO_TRADE → never BUY.

## Why this is a Phase 8 blocker

The Phase 8 paper-trading window (Jun 1 → Jul 20) coincides with the projected **Q3 2026 gold reversal** (institutional consensus: bullish, JPMorgan $5,000 target, Goldman Sachs $5,400-$6,000, Deutsche Bank $6,000). Running a SELL-only system into a rising gold market is **guaranteed drawdown** — the system has no mechanism to participate in upward XAUUSD moves and will repeatedly stop into the trend.

The Vote 6D blacklist (`ml_direct/XAUUSD` blocked in `paper.yaml`/`base.yaml`/`live.yaml`) is the right *interim* response, but it leaves the system without a gold strategy entirely. AI-001 is the implementation work to give the system back a balanced gold capability before Jun 1.

## Fix paths (ranked by effort and risk)

### Path A — Retrain with `class_weight='balanced'` (small change, validate on holdout)

**Effort:** ~1 day. **Risk:** medium.

```python
params["class_weight"] = "balanced"  # one-line change
# OR equivalent: pass `sample_weight` derived from class frequencies to lgb.Dataset
```

LightGBM's `class_weight='balanced'` automatically scales the loss for under-represented classes. With training data already favouring BUY, this would force the model to also penalise BUY mis-predictions more — likely eliminating the collapse onto SELL.

Risk: if the regime issue is genuine (gold was actually unidirectional in the training window), forcing balance may produce a model that's wrong about both directions equally. **Validate on the AI-005 holdout sample** (54 most recent v3 trades, never used to train) before any deployment.

### Path B — Time-stratified retraining (covers both regimes)

**Effort:** 2-3 days. **Risk:** low.

Re-collect training data spanning BOTH a clear gold uptrend (e.g. 2020-2022) and a clear downtrend (2022-2024). Ensure each regime contributes ~half of the training samples. Combined with `class_weight='balanced'`, this directly addresses the regime-induced bias.

This is the **most defensible long-term fix** and is what would survive a methodological audit.

### Path C — Per-class threshold calibration (no retraining)

**Effort:** ~1 day. **Risk:** high.

Replace `argmax` selection with explicit per-class thresholds:

```python
# Instead of: pred_class = proba.argmax()
if proba[2] >= buy_threshold:        # buy_threshold = e.g. 0.30
    action = "BUY"
elif proba[0] >= sell_threshold:     # sell_threshold = e.g. 0.55
    action = "SELL"
else:
    action = None
```

Allows BUY signals to fire even when P(BUY) < P(SELL), so long as P(BUY) ≥ buy_threshold. With buy_threshold=0.30, **73 of 94 historical XAUUSD trades** would have been BUY candidates rather than SELL.

Risk: this fights the model rather than fixing it. We'd be lowering precision on BUY (already only 46%) for a recall gain that's compensating for a deeper bias. The 73 candidates above are the same trades the model already labelled SELL with 55-65% confidence — flipping their direction without any model improvement is gambling on the strategy code's ability to recover.

**Not recommended without retraining.** Useful only as a stop-gap if Phase 8 starts before retraining lands.

### Path D — Replace `ml_direct` with the Phase 7 meta-labeler (long-term fix)

**Effort:** Phase 7 timeline (~5 weeks). **Risk:** lowest.

The Phase 7 meta-labeler (Step 6, May 18-24) trains a separate classifier per signal type (MACD, RSI) and predicts whether each entry signal will be profitable rather than predicting market direction directly. This sidesteps the multi-class direction-prediction problem entirely.

The triple-barrier labels (Phase 7 Step 1, shipped 2026-05-06) and purged K-fold CV (Step 2, shipped 2026-05-06) provide the methodological foundation. By the time Phase 7 ships its first meta-labeled strategy (Jun 8 ship gate), `ml_direct` would be retired in favour of the new architecture.

This is the **architecturally correct fix**, but it doesn't help the Phase 8 paper window starting Jun 1 unless Phase 7 ships ahead of schedule.

## Recommendation

| Window | Recommended path |
|---|---|
| Pre-Jun 1 (Phase 8 start) | **Path A** — `class_weight='balanced'` retraining + AI-005 holdout validation. Lowest-effort, defensible, ships in time. |
| Jun 1 → Jul 20 (Phase 8 paper) | Operate with Path A model under blacklist-lifted conditions OR keep blacklist active and accept missing gold exposure. Project lead's call at the Jun 1 gate. |
| Jul 20+ (Phase 9 lead-up) | **Path B** — full regime-stratified retraining as part of Phase 9 prep. |
| Long term | **Path D** — meta-labeler replaces `ml_direct` per Phase 7 plan. |

## What this diagnostic does NOT close

This document does the diagnostic phase of AI-001. The implementation phase remains open:

- Path A retraining script + validation
- Verifying class balance survives on the AI-005 holdout
- Updating the blacklist + paper.yaml entries when retrained model is approved

I have NOT retrained the model in this commit. The recommendation is for the project lead to approve Path A before any retraining happens.

## Files / data referenced

- `strategies/ml_direct_strategy.py` (lines 31, 70-141) — strategy code
- `ml/market_learner.py` (lines 163-178) — training params
- `models/market_learner/XAUUSD_model.pkl::meta` — trained-model metadata
- `data/trading.db::trades` — 94 v3 XAUUSD ml_direct trades, comments parsed for proba distribution
- `docs/research/ai005_holdout_validation.md` — the OOS holdout that any retrained model must validate against
- `docs/research/external_review_2026_04_28.md` — bias × falling-gold framing that motivated R-EXT-002
- `data/improvements.db::action_items` — AI-001, AI-005 (DONE), R-EXT-002 (HIGH × HIGH risk)
