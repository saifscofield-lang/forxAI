# Phase 11 — Carry Premise Test — RESULTS

Sample: 2022-01-31 .. 2026-03-31  (51 month-ends, 50 monthly returns)

## Portfolio (equal-weight, 6 pairs, monthly)

- Annualized return : +1.61%
- Sharpe (x sqrt12) : +0.27
- % positive months : 50%
- Max drawdown      : -7.35%
- Mean monthly tot  : +0.1519%  (t = +0.56)
- Decompose: spot mean -0.0056% | carry mean +0.1583%

## Per calendar year (portfolio total return)

- 2022: +4.10%  (11 months)
- 2023: -0.55%  (12 months)
- 2024: +8.61%  (12 months)
- 2025: -4.05%  (12 months)
- 2026: -0.91%  (3 months)

## Per-pair full-sample total return

- EURUSD: +1.92%  | flips=0 | carry-leg=('EUR', 'USD')
- GBPUSD: -13.05%  | flips=9 | carry-leg=('GBP', 'USD')
- AUDUSD: -1.63%  | flips=0 | carry-leg=('AUD', 'USD')
- USDCAD: +4.23%  | flips=8 | carry-leg=('USD', 'CAD')
- USDCHF: -2.67%  | flips=0 | carry-leg=('USD', 'CHF')
- USDJPY: +62.85%  | flips=0 | carry-leg=('USD', 'JPY')

## Per-regime mean monthly return

- Hiking era 2022-2024 : +0.3560%  (35 months)
- Easing era 2025-2026 : -0.3244%  (15 months)

## Pre-registered gates

- **C1 Premise** FAIL — mean +0.1519% >0 and t=+0.56 (need >=2.0)
- **C2 Spot** PASS — spot drift t=-0.02 (need >-2.0)
- **C3 Persistence** FAIL — 2/4 years positive (need >=3 of 4)
- **C4 Breadth** FAIL — 3/6 pairs positive (need >=4)
- **C5 Regime** FAIL — hike +0.3560% & ease -0.3244% (both must be >0)

## VERDICT: FAIL — carry premise does not hold robustly

Decision rule -> failed ['C1', 'C3', 'C4', 'C5']. Do NOT tweak the rule post-hoc. Move to the next non-price hypothesis.
