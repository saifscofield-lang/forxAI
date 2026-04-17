# Meta-Labeler Prototype — Results

_Run: 2026-04-17T13:51:27_  
_Dataset: 1,017 signals (TP=386, SL=631)_  
_Validation: Purged K-Fold, 5 splits, embargo 1%_  
_Decision threshold: proba ≥ 0.55_  
_Features: 20 from step 7 shortlist_

## Results table

| Architecture | Scope | N | AUC ± std | WR base → filtered | Lift | Verdict |
|---|---|---:|---:|---:|---:|---|
| GLOBAL | `all` | 1,017 | 0.538 ± 0.050 | 38.0% → 39.1% | +1.2pp | ❌ MARGINAL |
| PER_STRATEGY | `macd_crossover` | 710 | 0.517 ± 0.049 | 39.7% → 41.7% | +2.0pp | ❌ MARGINAL |
| PER_STRATEGY | `rsi_reversal` | 307 | 0.581 ± 0.042 | 33.9% → 41.1% | +7.2pp | ✅ STRONG |
| PER_COMBO | `macd_crossover/AUDUSD` | 80 | 0.470 ± 0.120 | 37.5% → 40.0% | +2.5pp | ❌ MARGINAL |
| PER_COMBO | `macd_crossover/EURUSD` | 126 | 0.593 ± 0.154 | 45.2% → 46.0% | +0.8pp | ❌ MARGINAL |
| PER_COMBO | `macd_crossover/GBPUSD` | 117 | 0.387 ± 0.116 | 31.6% → 21.1% | -10.6pp | ❌ NONE |
| PER_COMBO | `macd_crossover/USDCAD` | 118 | 0.396 ± 0.139 | 33.9% → 20.5% | -13.4pp | ❌ NONE |
| PER_COMBO | `macd_crossover/USDCHF` | 101 | 0.536 ± 0.060 | 43.6% → 42.4% | -1.1pp | ❌ MARGINAL |
| PER_COMBO | `macd_crossover/XAUUSD` | 96 | 0.456 ± 0.121 | 42.7% → 32.4% | -10.3pp | ❌ NONE |

## Interpretation

- **AUC ≥ 0.55** is the bar for "this model has real signal".
- **WR lift ≥ 5pp** is the bar for "this is worth the operational complexity".
- **Filtered WR** is the actual metric that matters: of the signals the meta-labeler says to take, what fraction win?

## Recommended architecture for v3.0 Phase 7

**PER_STRATEGY** (rsi_reversal) — ✅ STRONG

- AUC: 0.581 ± 0.042
- Raw WR: 33.9% → Filtered: 41.1% (lift +7.2pp)
- 90 signals taken of 307 primary (29% keep-rate)

## Next action

If any architecture reached ✅ STRONG, that is the v3.0 Phase 7 starting point.
If all are ⚠️ or ❌, investigate: (a) richer feature set, (b) different labels (e.g., triple-barrier with volatility-scaled barriers), (c) admit the edge may not be large enough for meta-labeling to help meaningfully.
