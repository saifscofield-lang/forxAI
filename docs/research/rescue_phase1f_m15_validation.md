# Rescue Plan — Phase 1f: M15-Frequency Validation

**Data:** 7 symbols × 30,000 bars per timeframe. Same strategy logic + ATR filter (1.2). One-position-at-a-time, ordered SL/TP, horizon=100.


## MACD Crossover

| Timeframe | Trades | Win% | PF (R) | Net R | Trades/symbol-yr |
|---|---:|---:|---:|---:|---:|
| H1 | 639 | 42% | 1.00 | +4 | 18 |
| M15 | 760 | 42% | 1.03 | +32 | 87 |

## RSI Reversal

| Timeframe | Trades | Win% | PF (R) | Net R | Trades/symbol-yr |
|---|---:|---:|---:|---:|---:|
| H1 | 234 | 37% | 0.89 | -33 | 7 |
| M15 | 195 | 38% | 0.94 | -15 | 22 |

## Verdict

- If M15 keeps **PF (R) ≈ H1's** while raising trades/symbol-yr substantially, M15 is the validated frequency lever → add M15 signal generation (keep all filters).
- If M15 PF degrades materially, lower-timeframe noise hurts these strategies → frequency must come from more symbols or new strategies instead.
- Same caveat as 1e: clean ATR-exit sim, no spread/slippage/downstream filters; PF is a *relative* H1-vs-M15 comparison.