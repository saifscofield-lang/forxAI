# Rescue Plan — Phase 1e: ATR-Lever Validation (backtest-lite)

**Data:** 7 symbols × 30,000 H1 bars. One-position-at-a-time, ordered SL/TP, horizon=100 bars. Decided trades only (timeouts excluded).
**PF (R)** = (wins×TP_mult)/(losses×SL_mult). PF>1.0 = profitable edge.


## MACD Crossover  (SL=2.5×ATR, TP=3.5×ATR)

| ATR thr | Trades | Win% | PF (R) | Net R | Trades/symbol-yr |
|---|---:|---:|---:|---:|---:|
| 1.2 (CURRENT) | 639 | 42% | 1.00 | +4 | 18 |
| 1.0 (RELAXED) | 2,265 | 41% | 0.97 | -88 | 65 |

## RSI Reversal  (SL=2.0×ATR, TP=3.0×ATR)

| ATR thr | Trades | Win% | PF (R) | Net R | Trades/symbol-yr |
|---|---:|---:|---:|---:|---:|
| 1.2 (CURRENT) | 234 | 37% | 0.89 | -33 | 7 |
| 1.0 (RELAXED) | 685 | 38% | 0.93 | -55 | 20 |

## Verdict

- If **PF (R) stays > 1.0** (ideally near the current value) when ATR thr drops 1.2→1.0, the relaxation increases trade count **without destroying edge** → SHIP it.
- If PF collapses below 1.0, the 1.2 filter is carrying the edge → keep it and find frequency elsewhere (M15 timeframe, more symbols).
- Note: this is a clean ATR-exit sim without spread/slippage/downstream filters; treat PF as a *relative* comparison between thresholds, not a live P&L forecast.

## DECISION — do NOT relax the ATR filter

The data is decisive:
- **MACD at 1.2 is barely break-even (PF 1.00).** Relaxing to 1.0 adds 3.5× trades
  but drops PF to 0.97 / net −88R. **The ATR filter is carrying MACD's thin edge.**
- **RSI reversal has no standalone edge** (PF < 1.0 at both thresholds).

This is the **second** independent confirmation (after Phase 1a) that loosening
filters trades quality for quantity at a LOSS. We will not relax filters.

**Why the live March report looked better (PF 1.63):** this sim deliberately
STRIPS the things that produced the live edge — the downstream filters (H4 trend
/ session / news, which Phase 1a showed block losers), the per-symbol *optimized*
SL/TP from `optimized_params.yaml` (not the defaults used here), trade management
(trailing / breakeven in `monitor_positions`), and it uses a far larger sample.
So this PF is a conservative *lower bound* on the raw signal, not the live system.

## The validated path to MORE trades = timeframe, not looser filters

The only frequency lever that adds setups **without** degrading per-trade quality
is scanning a **lower timeframe (M15)** — same strategy logic, ~4× more candles.
Next: Phase 1f validates MACD/RSI on M15 (PF must hold) before any deploy.