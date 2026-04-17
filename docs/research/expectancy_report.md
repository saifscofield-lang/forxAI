# Expectancy Analysis — v3.0 Phase 5

_Run: 2026-04-17T13:59:11_

Expectancy = (WR × avg_win) − ((1−WR) × avg_loss). 
Positive = strategy makes money on average. Negative = loses money.

## Backtest expectancy (triple-barrier signals)

| Strategy | Pair | N | WR | RR | Exp (pips/signal) |
|---|---|---:|---:|---:|---:|
| `macd_crossover` | `AUDUSD` | 89 | 37.5% | 1.40 | -3.5 |
| `macd_crossover` | `EURUSD` | 144 | 45.2% | 1.40 | +3.2 |
| `macd_crossover` | `GBPUSD` | 131 | 31.6% | 1.40 | -12.7 |
| `macd_crossover` | `USDCAD` | 141 | 33.9% | 1.40 | -7.9 |
| `macd_crossover` | `USDCHF` | 118 | 43.6% | 1.40 | +1.5 |
| `macd_crossover` | `USDJPY` | 82 | 45.8% | 1.40 | +5.2 |
| `macd_crossover` | `XAUUSD` | 110 | 42.7% | 1.40 | +3.8 |
| `rsi_reversal` | `AUDUSD` | 21 | 47.1% | 1.50 | +6.1 |
| `rsi_reversal` | `EURUSD` | 51 | 53.1% | 1.50 | +12.5 |
| `rsi_reversal` | `GBPUSD` | 36 | 45.7% | 1.50 | +7.0 |
| `rsi_reversal` | `USDCAD` | 52 | 30.6% | 1.50 | -8.4 |
| `rsi_reversal` | `USDCHF` | 45 | 30.2% | 1.50 | -8.3 |
| `rsi_reversal` | `USDJPY` | 61 | 22.4% | 1.50 | -25.3 |
| `rsi_reversal` | `XAUUSD` | 63 | 23.2% | 1.50 | -81.3 |

## Live trade expectancy (211 closed trades)

| Strategy | Pair | N | WR | AvgWin$ | AvgLoss$ | Exp/trade | Total PnL |
|---|---|---:|---:|---:|---:|---:|---:|
| `macd_crossover` | `XAUUSD` | 7 | 71.4% | $2394 | $8 | $+1708 | $+11954 |
| `rsi_reversal` | `AUDUSD` | 3 | 100.0% | $1283 | $0 | $+1283 | $+3850 |
| `sma_crossover` | `AUDUSD` | 2 | 100.0% | $1250 | $0 | $+1250 | $+2500 |
| `macd_crossover` | `EURUSD` | 4 | 100.0% | $597 | $0 | $+597 | $+2388 |
| `ml_direct` | `GBPUSD` | 1 | 100.0% | $596 | $0 | $+596 | $+596 |
| `rsi_reversal` | `NZDUSD` | 1 | 100.0% | $540 | $0 | $+540 | $+540 |
| `macd_crossover` | `AUDUSD` | 5 | 100.0% | $379 | $0 | $+379 | $+1893 |
| `macd_crossover` | `GBPUSD` | 4 | 75.0% | $773 | $840 | $+370 | $+1480 |
| `rsi_reversal` | `USDCHF` | 2 | 100.0% | $343 | $0 | $+343 | $+686 |
| `rsi_reversal` | `EURUSD` | 2 | 50.0% | $770 | $450 | $+160 | $+320 |
| `bollinger_bounce` | `GBPUSD` | 8 | 37.5% | $1027 | $387 | $+143 | $+1146 |
| `sma_crossover` | `NZDUSD` | 6 | 50.0% | $840 | $601 | $+119 | $+716 |
| `macd_crossover` | `USDCHF` | 6 | 66.7% | $558 | $765 | $+117 | $+701 |
| `ml_direct` | `USDCHF` | 1 | 100.0% | $109 | $0 | $+109 | $+109 |
| `ml_direct` | `USDCAD` | 3 | 100.0% | $95 | $0 | $+95 | $+284 |
| `ml_direct` | `EURUSD` | 6 | 100.0% | $89 | $0 | $+89 | $+535 |
| `sma_crossover` | `USDJPY` | 1 | 100.0% | $68 | $0 | $+68 | $+68 |
| `ml_direct` | `AUDUSD` | 9 | 88.9% | $120 | $450 | $+57 | $+513 |
| `macd_crossover` | `USDJPY` | 2 | 100.0% | $23 | $0 | $+23 | $+45 |
| `ml_filtered_sma` | `EURUSD` | 1 | 100.0% | $20 | $0 | $+20 | $+20 |
| `ml_filtered_sma` | `GBPUSD` | 2 | 100.0% | $20 | $0 | $+20 | $+40 |
| `asia_breakout` | `AUDUSD` | 1 | 100.0% | $20 | $0 | $+20 | $+20 |
| `ml_filtered_sma` | `AUDUSD` | 2 | 100.0% | $20 | $0 | $+20 | $+40 |
| `stop_hunt_reversal` | `AUDUSD` | 1 | 100.0% | $20 | $0 | $+20 | $+20 |
| `ml_filtered_sma` | `USDCAD` | 1 | 100.0% | $14 | $0 | $+14 | $+14 |
| `rsi_reversal` | `USDJPY` | 6 | 66.7% | $20 | $13 | $+9 | $+55 |
| `bollinger_bounce` | `XAUUSD` | 5 | 60.0% | $15 | $13 | $+4 | $+19 |
| `sma_crossover` | `XAUUSD` | 4 | 0.0% | $0 | $8 | $-8 | $-30 |
| `macd_crossover` | `USDCAD` | 7 | 57.1% | $232 | $344 | $-15 | $-102 |
| `rsi_reversal` | `XAUUSD` | 7 | 0.0% | $0 | $37 | $-37 | $-256 |
| `bollinger_bounce` | `USDCHF` | 7 | 57.1% | $178 | $335 | $-42 | $-293 |
| `bollinger_bounce` | `USDCAD` | 7 | 57.1% | $109 | $296 | $-64 | $-450 |
| `ml_filtered_sma` | `USDCHF` | 4 | 75.0% | $25 | $354 | $-70 | $-278 |
| `bollinger_bounce` | `AUDUSD` | 11 | 54.5% | $469 | $747 | $-84 | $-920 |
| `bollinger_bounce` | `USDJPY` | 9 | 44.4% | $54 | $200 | $-87 | $-784 |
| `ml_filtered_sma` | `USDJPY` | 4 | 25.0% | $13 | $129 | $-93 | $-374 |
| `asia_breakout` | `USDJPY` | 1 | 0.0% | $0 | $135 | $-135 | $-135 |
| `bollinger_bounce` | `EURUSD` | 7 | 42.9% | $763 | $834 | $-149 | $-1044 |
| `rsi_reversal` | `GBPUSD` | 3 | 33.3% | $660 | $653 | $-215 | $-646 |
| `bollinger_bounce` | `NZDUSD` | 6 | 16.7% | $600 | $632 | $-427 | $-2562 |
| `macd_crossover` | `NZDUSD` | 4 | 0.0% | $0 | $508 | $-508 | $-2030 |
| `sma_crossover` | `GBPUSD` | 2 | 0.0% | $0 | $551 | $-551 | $-1102 |
| `ml_direct` | `XAUUSD` | 48 | 60.4% | $855 | $3090 | $-706 | $-33907 |
| `sma_crossover` | `USDCAD` | 2 | 0.0% | $0 | $766 | $-766 | $-1532 |
| `ml_filtered_sma` | `XAUUSD` | 4 | 0.0% | $0 | $898 | $-898 | $-3591 |

## Meta-filter impact on RSI

- **Raw RSI** (all 307 signals): WR 33.9%, Exp -65.9 pips/signal
- **Filtered RSI** (proba ≥ 0.55): WR 43.2%, Exp +5.1 pips/signal
- **Keep-rate**: 29% of signals taken
- **Lift**: +71.0 pips per signal


## How to read this

- **RR < 1.0** means losses are bigger than wins. Need high WR to survive.
- **Exp/signal negative** → strategy is a money-loser regardless of win rate.
- **Live vs backtest gap** shows execution reality (slippage, spreads, psychology).
- Meta-filtered columns show the expected lift IF the meta-labeler generalizes out of sample — always expect some degradation in production.
