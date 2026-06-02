# Rescue Plan — Phase 1d: Strategy-Silence Funnel Audit

**Data:** 7 symbols × last 30,000 H1 bars = 209,776 bars (~3.4y/symbol).
**Goal:** identify the condition that blocks the most signals, and quantify the trade-frequency gain from relaxing each lever.

## MACD Crossover — funnel

| Stage (cumulative) | Bars passing | per 1k bars | per symbol-yr |
|---|---:|---:|---:|
| 1. ATR filter ≥1.2×avg | 19,126 | 91.17 | 547 |
| 2. + MACD cross | 1,601 | 7.63 | 46 |
| 3. + trend & histogram = FIRE | 681 | 3.25 | 19 |

**What-if levers (relax one at a time):**

| Lever | Signals | per 1k | per symbol-yr | vs current |
|---|---:|---:|---:|---:|
| CURRENT | 681 | 3.25 | 19 | 1.0× |
| ATR thr 1.2→1.0 | 2,843 | 13.55 | 81 | 4.2× |
| ATR filter OFF | 5,762 | 27.47 | 165 | 8.5× |
| histogram momentum OFF | 681 | 3.25 | 19 | 1.0× |
| ATR 1.0 + hist OFF | 2,843 | 13.55 | 81 | 4.2× |

## RSI Reversal — funnel

| Stage (cumulative) | Bars passing | per 1k bars | per symbol-yr |
|---|---:|---:|---:|
| 1. ATR filter ≥1.2×avg | 19,126 | 91.17 | 547 |
| 2. + RSI extreme +2bar +price = FIRE | 279 | 1.33 | 8 |

**What-if levers:**

| Lever | Signals | per 1k | per symbol-yr | vs current |
|---|---:|---:|---:|---:|
| CURRENT (30/70, 2bar, price) | 279 | 1.33 | 8 | 1.0× |
| bands 30/70→35/65 | 569 | 2.71 | 16 | 2.0× |
| drop 2-bar confirm | 1,353 | 6.45 | 39 | 4.8× |
| drop price confirm | 279 | 1.33 | 8 | 1.0× |
| ATR thr 1.2→1.0 | 918 | 4.38 | 26 | 3.3× |
| 35/65 + no 2-bar + ATR1.0 | 8,579 | 40.90 | 245 | 30.7× |

## Bollinger Bounce — funnel

| Stage (cumulative) | Bars passing | per 1k bars | per symbol-yr |
|---|---:|---:|---:|
| 1. ATR filter ≥1.0×avg | 92,175 | 439.40 | 2636 |
| 2. + BB width ≤3% | 90,456 | 431.20 | 2587 |
| 3. + bounce confirm | 8,539 | 40.71 | 244 |
| 4. + RSI 40/60 & width = FIRE | 4,423 | 21.08 | 127 |

**What-if levers:**

| Lever | Signals | per 1k | per symbol-yr | vs current |
|---|---:|---:|---:|---:|
| CURRENT | 4,423 | 21.08 | 127 | 1.0× |
| RSI 40/60→45/55 | 6,083 | 29.00 | 174 | 1.4× |
| RSI confirm OFF (50/50) | 6,971 | 33.23 | 199 | 1.6× |
| BB width cap 3%→5% | 4,471 | 21.31 | 128 | 1.0× |

## How to use this

- The funnel shows WHERE signals die. The **what-if** table shows the trade-count multiplier from each single relaxation.
- Pick levers with the best frequency gain **and** that Phase 1a/evidence says are safe. The ATR filter is evidence-backed (STAT-003: winners ATR 3.59 vs losers 1.18) so prefer tuning its threshold over removing it.
- **Next step after choosing levers:** backtest the relaxed config on `data/backtest_results.db` tooling to confirm profit factor holds BEFORE going live (per the balanced approach). Adding M15 timeframe is a separate ~4× frequency lever not modelled here (it multiplies bar count).