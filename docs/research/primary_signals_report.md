# Phase 5 Step 7 — Primary Signal Dataset (v3.0 Meta-Labeler training set)

_Generated: 2026-04-17T12:54:25_  
_Window: 2020-01-01 → 2026-04-01 · 7 pairs · H1_  
_Strategies: macd_crossover v2.0, rsi_reversal v1.1 (production code)_  
_Triple barrier: TP/SL from each strategy's own ATR multipliers, horizon=48 H1 bars (2 trading days)_

## Result: 1,144 signals (target 1,000 → ✅ MET)

## Signal counts by strategy

| Strategy | Total | TP (+1) | SL (-1) | Timeout (0) | WR (excl timeout) |
|---|---:|---:|---:|---:|---:|
| `macd_crossover` | 815 | 282 | 428 | 105 | 39.7% |
| `rsi_reversal` | 329 | 104 | 203 | 22 | 33.9% |

## Signal counts by pair

| Pair | Total | TP | SL | Timeout | WR |
|---|---:|---:|---:|---:|---:|
| `AUDUSD` | 110 | 38 | 59 | 13 | 39.2% |
| `EURUSD` | 195 | 83 | 92 | 20 | 47.4% |
| `GBPUSD` | 167 | 53 | 99 | 15 | 34.9% |
| `USDCAD` | 193 | 55 | 112 | 26 | 32.9% |
| `USDCHF` | 163 | 57 | 87 | 19 | 39.6% |
| `USDJPY` | 143 | 46 | 84 | 13 | 35.4% |
| `XAUUSD` | 173 | 54 | 98 | 21 | 35.5% |

## Reading the win rate

- A primary signal's WR is **before** the meta-labeler filter. The meta-labeler's job is to push this WR up by rejecting low-quality signals.
- Overall WR is **38.0%**. With TP/SL ratios > 1, even WR ~45% can be profitable — but the v3.0 target is to lift WR closer to 55-60% via meta-filtering.
- **127 timeouts** (11.1%) are signals where neither TP nor SL hit within 48 H1 bars. These are kept in the dataset (label=0) but excluded from the binary trade/skip training set.

## Dataset contents

`data\research\primary_signals.parquet` — 1,144 rows × 97 columns:
- Identification: `time, symbol, strategy, direction, bar_idx`
- Trade params: `entry, sl, tp, atr`
- Outcome: `label, outcome, bars_held, pnl_price, rr_ratio`
- Meta-label: `meta_label` (1 = profitable, 0 = not)
- Features: 82 columns (snapshot at signal time)

## Next step

This dataset is the input for `ml/meta_labeler.py` (v3.0 Phase 7). It also feeds the re-run feature importance below — those rankings, not the every-bar ones from step 6, are what should drive the final feature set.
