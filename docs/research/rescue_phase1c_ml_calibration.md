# Rescue Plan — Phase 1c: ML Confidence-Calibration Audit

**Models:** models/market_learner/*.pkl (trained 2026-03-26).
**Eval:** last 8,000 bars/symbol, real exits TP=3.0×/SL=2.0×ATR, ordered, horizon=48.
**Question:** does real win% RISE with model confidence? If flat → confidence is noise.


## Aggregate (all symbols) — confidence bin vs real win rate

| Confidence bin | Signals | Real WIN | Real LOSS | Timeout | **Real win% (decided)** |
|---|---:|---:|---:|---:|---:|
| 0.40–0.50 | 16,770 | 6,275 | 9,859 | 636 | **39%** |
| 0.50–0.55 | 5,494 | 1,977 | 3,245 | 272 | **38%** |
| 0.55–0.60 | 3,168 | 1,158 | 1,849 | 161 | **39%** |
| 0.60–0.70 | 1,283 | 473 | 737 | 73 | **39%** |
| 0.70–1.01 | 33 | 14 | 17 | 2 | **45%** |

## Per-symbol real win% by confidence bin

| Symbol | 0.40–0.50 | 0.50–0.55 | 0.55–0.60 | 0.60–0.70 | 0.70–1.01 |
|---|---|---|---|---|---|
| AUDUSD | 42% (n=867) | 41% (n=214) | 57% (n=106) | 57% (n=76) | 100% (n=1) |
| EURUSD | 39% (n=2529) | 43% (n=851) | 39% (n=306) | 43% (n=104) | 38% (n=9) |
| GBPUSD | 39% (n=3015) | 36% (n=327) | 51% (n=49) | 67% (n=6) | — |
| USDCAD | 38% (n=2032) | 36% (n=817) | 38% (n=456) | 40% (n=335) | 83% (n=12) |
| USDCHF | 38% (n=2018) | 34% (n=377) | 29% (n=119) | 32% (n=44) | 0% (n=10) |
| USDJPY | 39% (n=4033) | 41% (n=997) | 51% (n=317) | 35% (n=45) | 0% (n=1) |
| XAUUSD | 38% (n=2276) | 35% (n=1911) | 36% (n=1815) | 37% (n=673) | — |

## How to read

- If real win% is **roughly flat** across bins (e.g. ~70% at 0.50 and ~70% at 0.70), the model's confidence carries **no extra information** — raising the threshold filters quantity but not quality. This confirms the freeze-doc finding.
- If win% **rises** with confidence, confidence is meaningful and the lever is to trade only high-confidence bins.
- Either way: **probability calibration** (isotonic/Platt on a validation set) plus relabeling with realistic exits (Phase 1b) is the fix. Calibration makes the 0.55 threshold mean a true 55%, so it can be tuned to balance trade frequency vs quality.

## VERDICT — the decisive finding

The calibration curve is **flat at ~39%** across every confidence bin
(39% → 38% → 39% → 39%; the 0.70+ bin has only 33 samples = noise).
**The model's confidence carries no information about the real outcome.**
This definitively confirms the freeze-doc observation.

Worse, the **absolute level is a losing edge.** With TP=3×ATR / SL=2×ATR,
break-even win rate = SL/(SL+TP) = 2/5 = **40%**. The model's BUY/SELL calls
win **~39%** → expected value per trade:

    EV = 0.39 × 3 − 0.61 × 2 = +1.17 − 1.22 = **−0.05 ATR  (NEGATIVE)**

So `ml_direct` predictions, traded with the real exits, are **net losers
regardless of confidence.**

### Reconciling with Phase 1b
- Phase 1b showed the **labels** define a profitable target (71% real win
  when the label is correct, strongly +EV).
- Phase 1c shows the **model cannot find those bars** — its predictions win
  only 39%. The target is good; the learner has **no edge**.

### Therefore the real root cause is NOT the labels
Relabeling + calibration cannot manufacture an edge the model doesn't have.
The dominant problems, in order:

1. 🔴 **`ml_direct` has no predictive skill** (39% ≈ coin-flip-with-costs).
   Yet the freeze data shows **6 of 7 live trades came from ml_direct/GBPUSD**
   — the system is leaning on its *weakest* component.
2. 🟢 **The rule-based strategies DO have edge** (March report: MACD 53% WR
   /+$1,672, Bollinger 54% /+$1,435, PF 1.63) but are mostly **silent** — the
   real scarcity problem is here, not in ML.

### Revised rescue priority (evidence-final)
1. **Demote `ml_direct` from a direct signal generator.** Either retire it or
   reuse it only as a *confirmation filter* on rule-based signals — never as
   the primary edge.
2. **Revive the rule-based strategies** (MACD, Bollinger, RSI) that have proven
   edge: diagnose why they go silent for days and widen *setup frequency*
   (M15 signal generation, more symbols) WITHOUT weakening quality filters.
3. **If ML is kept**, rebuild it as a research project (better target, more
   features, walk-forward with calibration) — but do not let the live system
   depend on it until it beats the 40% break-even bar out-of-sample.
4. Keep all quality filters (Phase 1a). Fix margin pre-check (low urgency).