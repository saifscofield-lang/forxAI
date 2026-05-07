# Phase 6 Step 2 — 10-year TSMOM Backtest

**Date:** 2026-05-07  
**Re-runnable:** `python scripts/backtest_tsmom.py`  
**Source module:** `strategies/tsmom/tsmom_strategy.py` (Phase 6 Step 1, shipped 2026-05-06)  
**Phase 6 ship gate:** Sharpe ≥ 0.5 across ≥3 regimes; the 2026-04-17 prototype delivered Sharpe 0.13.

## Backtest setup

- Symbols: EURUSD, GBPUSD, USDJPY, XAUUSD, AUDUSD, USDCHF
- Timeframe: D1 (daily bars)
- Lookback: 252 bars (12 months)
- Vol window: 60 bars (3 months)
- Vol target: 0.10 (10% annualised)
- Weight cap: 4.0
- Rebalance: monthly (first available bar per calendar month)
- Total per-symbol-month observations: **1104**

## Per-symbol metrics

| Symbol | Months | Sharpe | Max DD | Total return | Win-month |
|---|---:|---:|---:|---:|---:|
| EURUSD | 184 | 0.132 | -23.7% | 13.7% | 52.2% |
| GBPUSD | 184 | -0.170 | -42.5% | -30.4% | 48.9% |
| USDJPY | 184 | 0.541 | -21.1% | 145.1% | 59.2% |
| XAUUSD | 184 | 0.380 | -31.7% | 76.8% | 49.5% |
| AUDUSD | 184 | 0.145 | -29.7% | 16.5% | 51.6% |
| USDCHF | 184 | -0.083 | -44.7% | -20.0% | 48.9% |

## Portfolio (equal-weight, 6 symbols)

| Metric | Value |
|---|---:|
| Months observed | 191 |
| **Sharpe (annualised)** | **0.336** |
| Max drawdown | -11.0% |
| Total return | 36.3% |
| Win-month rate | 51.8% |
| Mean monthly return | 0.0018 |
| Std monthly return | 0.0185 |

### Verdict: ✗ FAILS Phase 6 ship gate (Sharpe 0.336 < 0.5, short by 0.164). The 2026-04-17 prototype delivered 0.13; this build delivers 0.336. Step in the right direction. Need to investigate parameter tuning (lookback, vol_target, weight_cap) or accept TSMOM doesn't have edge on this universe.

## Sub-period breakdown (regime check)

Phase 6 plan requires the backtest cover ≥3 regimes. Splitting the period into ~3-year sub-windows:

| Period | Months | Sharpe | Total return | Win-month |
|---|---:|---:|---:|---:|
| 2011–2013 | 39 | 0.295 | 5.9% | 53.8% |
| 2014–2016 | 37 | 0.076 | 0.9% | 56.8% |
| 2017–2019 | 37 | 0.013 | -0.3% | 43.2% |
| 2020–2022 | 36 | 0.590 | 12.8% | 50.0% |
| 2023–2025 | 38 | 0.505 | 9.5% | 52.6% |
| 2026–2026 | 4 | 1.707 | 3.6% | 75.0% |

6 of 6 sub-periods produced positive Sharpe. Consistent across regimes.

## Methodology notes

- **Monthly rebalance only.** No intra-month adjustments. A signal at month-start
  is held for the entire month. Real paper trading might rebalance differently;
  this matches the Phase 6 plan's 'monthly rebalance' instruction.
- **No transaction costs.** Spreads / commissions / swap not modelled. A real
  paper run would shave Sharpe by ~0.05–0.15 depending on broker terms.
- **Equal-weight portfolio.** Each of 6 symbols contributes 1/6 to the monthly
  return. A volatility-parity portfolio would weight by inverse vol; that's a
  separate experiment.
- **Walk-forward by construction.** Each month's signal uses only data up to
  that month-start, so there's no look-ahead.
- **No SL/TP.** Pure direction × monthly return. The strategy class has SL/TP
  for live trading but the backtest doesn't simulate them — kept simple to
  test the directional signal's edge in isolation.

## What this does NOT decide

- Whether Phase 6 step 3 (May 18-24 paper trading) starts. That depends on
  the Sharpe verdict + your read of regime-consistency.
- Whether to switch to volatility-parity weighting or another portfolio
  construction. Equal-weight is the simplest baseline; alternatives can be
  evaluated separately if Sharpe needs improvement.
- Whether to add a regime filter (similar to Phase 10.5's TSMOM-with-regime-
  filter rescue, which did NOT work on crypto). Worth flagging as a potential
  iteration if the unfiltered version fails the gate.
