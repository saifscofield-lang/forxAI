# Rescue Plan — Phase 1b: Label-Optimism Audit

**Data:** data/raw/*/H1.parquet, last 30,000 bars/symbol (~3.4y).
**Current labeler:** market_learner.create_labels (unordered, 6-bar window).
**Realistic exits:** TP=3.0×ATR, SL=2.0×ATR, ordered first-touch, horizon=48 bars.

## TEST A — Realism gap: do the labels survive real ordered exits?

For every bar the current labeler calls BUY/SELL, we simulate the real ml_direct trade (3×/2× ATR, ordered). A 'WIN' actually reached TP before SL.

| Symbol | Dir labels | Real WIN | Real LOSS | Timeout | **Real win% (decided)** | **Optimism\*** |
|---|---:|---:|---:|---:|---:|---:|
| AUDUSD | 16,221 | 11,379 | 4,328 | 508 | **72%** | **30%** |
| EURUSD | 17,424 | 12,056 | 4,679 | 681 | **72%** | **31%** |
| GBPUSD | 18,053 | 12,357 | 4,979 | 710 | **71%** | **32%** |
| USDCAD | 18,804 | 12,712 | 5,396 | 690 | **70%** | **32%** |
| USDCHF | 15,676 | 10,994 | 3,980 | 696 | **73%** | **30%** |
| USDJPY | 21,409 | 13,840 | 6,534 | 1,030 | **68%** | **35%** |
| XAUUSD | 17,903 | 12,355 | 4,850 | 694 | **72%** | **31%** |
| **ALL** | 125,490 | 85,693 | 34,746 | 5,009 | **71%** | **32%** |

\*Optimism = share of BUY/SELL labels that do NOT reach TP first as a real trade (LOSS + never-reached). These are training targets the model learns as 'good' but that lose money in reality — the direct cause of meaningless confidence.

## TEST B — Pure ordering flip (isolates the create_labels bug)

On the ambiguous bars where BOTH barriers (±min_move, 6-bar) are touched, how often does the ordered first-touch label DISAGREE with the current magnitude-tiebreak label?

| Symbol | Ambiguous dir-labels | Flipped by ordering | **Flip%** |
|---|---:|---:|---:|
| AUDUSD | 153 | 84 | **55%** |
| EURUSD | 232 | 122 | **53%** |
| GBPUSD | 216 | 95 | **44%** |
| USDCAD | 203 | 107 | **53%** |
| USDCHF | 111 | 50 | **45%** |
| USDJPY | 492 | 225 | **46%** |
| XAUUSD | 679 | 326 | **48%** |
| **ALL** | 2,086 | 1,009 | **48%** |

## Conclusion

- **TEST A** measures the headline harm: how many 'good' training labels are actually losing trades under the exits we really use.
- **TEST B** confirms the mechanism: the higher the flip%, the more the magnitude-tiebreak (ignoring order) corrupts the label vs. a first-touch rule.
- **Fix:** relabel with the ordered triple-barrier already in `features/ml/label_engine.py` using the SAME 3×/2× ATR exits, then retrain. This aligns training target with live trading and should restore meaningful confidence (so we can lower the 0.55 threshold to fire more trades safely).