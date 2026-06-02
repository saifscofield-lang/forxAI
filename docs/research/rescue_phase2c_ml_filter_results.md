# Rescue Plan — Phase 2c: ml_direct Rebuild as Filter — Acceptance Test

**Dataset:** pooled MACD-M15 trades labeled by real ordered TP/SL (TP=3.5× / SL=2.5×ATR). n=2856, base win-rate 40.6%, 64 scale-invariant features.
**Protocol:** 3-fold purged walk-forward; threshold = val R-PF max s.t. pass-rate ≥ 46%. Permutation control per fold.

| Fold | n test | Filter AUC | Perm AUC | Ungated PF | **Gated PF** | Pass% | Gated/sym-yr | Accept? |
|---|---:|---:|---:|---:|---:|---:|---:|:--:|
| 1 | 714 | 0.461 | 0.488 | 0.97 | **0.91** | 80% | 69 | ❌ |
| 2 | 714 | 0.453 | 0.519 | 0.96 | **0.95** | 95% | 82 | ❌ |
| 3 | 714 | 0.490 | 0.498 | 1.03 | **1.00** | 63% | 55 | ❌ |

**Means:** filter AUC 0.468 | permutation AUC 0.501 | ungated PF 0.99 | gated PF 0.95

## Acceptance criteria

- A1 gated PF ≥ ungated + 0.15: mean 0.95 vs 1.14 → FAIL
- A2 gated PF ≥ 1.10: 0.95 → FAIL
- A4 permutation AUC ≈ 0.50: 0.501 → PASS (no leakage)
- A5 ≥2/3 folds pass A1–A3: 0/3 → FAIL

## VERDICT: ❌ DO NOT SHIP — keep ml_direct retired; frequency rests on MACD-M15 alone

A negative result is a valid, honest outcome: it means MACD signals on M15 do not carry a learnable win/loss separation strong enough to beat the bar. The design doc anticipated this — ml_direct stays retired rather than shipping a fake edge. Next options: (a) richer regime features, (b) per-symbol models, (c) accept MACD-M15 ungated and focus elsewhere.