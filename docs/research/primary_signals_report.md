# Phase 5 Step 7 — Primary Signal Dataset (v3.0 Meta-Labeler training set)

_Generated: 2026-04-17T11:36:46_  
_Window: 2022-04-17 → 2026-04-01 · 5 pairs · H1_  
_Strategies: macd_crossover v2.0, rsi_reversal v1.1 (production code)_  
_Triple barrier: TP/SL from each strategy's own ATR multipliers, horizon=48 H1 bars (2 trading days)_

## Result: 586 signals (target 3,000 → ❌ BELOW)

## Signal counts by strategy

| Strategy | Total | TP (+1) | SL (-1) | Timeout (0) | WR (excl timeout) |
|---|---:|---:|---:|---:|---:|
| `macd_crossover` | 424 | 136 | 234 | 54 | 36.8% |
| `rsi_reversal` | 162 | 66 | 85 | 11 | 43.7% |

## Signal counts by pair

| Pair | Total | TP | SL | Timeout | WR |
|---|---:|---:|---:|---:|---:|
| `AUDUSD` | 87 | 27 | 48 | 12 | 36.0% |
| `EURUSD` | 136 | 58 | 64 | 14 | 47.5% |
| `GBPUSD` | 117 | 38 | 69 | 10 | 35.5% |
| `USDCAD` | 132 | 37 | 78 | 17 | 32.2% |
| `USDCHF` | 114 | 42 | 60 | 12 | 41.2% |

## Reading the win rate

- A primary signal's WR is **before** the meta-labeler filter. The meta-labeler's job is to push this WR up by rejecting low-quality signals.
- Overall WR is **38.8%**. With TP/SL ratios > 1, even WR ~45% can be profitable — but the v3.0 target is to lift WR closer to 55-60% via meta-filtering.
- **65 timeouts** (11.1%) are signals where neither TP nor SL hit within 48 H1 bars. These are kept in the dataset (label=0) but excluded from the binary trade/skip training set.

## Dataset contents

`data\research\primary_signals.parquet` — 586 rows × 97 columns:
- Identification: `time, symbol, strategy, direction, bar_idx`
- Trade params: `entry, sl, tp, atr`
- Outcome: `label, outcome, bars_held, pnl_price, rr_ratio`
- Meta-label: `meta_label` (1 = profitable, 0 = not)
- Features: 82 columns (snapshot at signal time)

## Next step

This dataset is the input for `ml/meta_labeler.py` (v3.0 Phase 7). It also feeds the re-run feature importance below — those rankings, not the every-bar ones from step 6, are what should drive the final feature set.
