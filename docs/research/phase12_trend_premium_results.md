# Phase 12 — Cross-Asset Trend Premium — DISCOVERY RESULTS

Per frozen pre-reg (commit 9fa6ee2). Gates fixed before run.

## Data / inclusion

- Included: 26 instruments across 7 classes
- Portfolio window: 2001-02-28 .. 2026-06-30 (305 months)

## Portfolio summary (net of cost)

- Mean monthly net : +0.2200%  (t = +3.36)
- Sharpe (ann)     : +0.67
- Buy&hold Sharpe   : +0.53
- Max drawdown     : -7.9%

## Gates

- **D1 Significance** PASS — mean +0.2200%/mo, t=+3.36 (need >0 & t>=2.0)
- **D2 OOS hold-out** PASS — OOS(2018-11-30..) mean +0.1787%, Sharpe +0.57 (need>0 & >=0.30); drift p(OOS<train)=0.34 (need>0.05) | train Sharpe +0.71
- **D3 Regime** PASS — halves +0.211/+0.229; eras pre2015 +0.239 / 2015+ +0.197 (all must be >0)
- **D4 Breadth** PASS — 6/7 classes net-positive (need >=4)
    ag:-0.051% bonds:+0.058% crypto:+0.851% energy:+0.156% equity:+0.440% fx:+0.054% metals:+0.333%
- **D5 Diversification** FAIL — ENB 12.27 (need>=10.4), PC1 0.17 (need<0.50), max|corr| 0.93 (need<0.70) over 26 instr
- **D6 Cost+passive** PASS — net@1.5x +0.2184%/mo (need>0); trend Sharpe +0.67 vs B&H +0.53 (must beat)

## VERDICT: 5/6 gates — FAIL

Failed: ['D5']. Per §10: no gate relaxation, no re-tuning.
Per §8 matrix (Discovery FAIL): direction-level result — the most-evidenced premise
fails even on the broadest powered universe. Systematic alpha on accessible instruments
under review; pivot the goal rather than add another price hypothesis.

## D5 failure diagnosis (post-run, does NOT change verdict)

The 6 instrument pairs with |corr|>0.70 (of 325 pairs) are ALL benign within-class duplicates:

| corr | pair | class |
|---|---|---|
| 0.93 | ZN=F / ZF=F | bonds (10Y / 5Y) |
| 0.93 | CL=F / BZ=F | energy (WTI / Brent) |
| 0.90 | ZN=F / ZB=F | bonds (10Y / 30Y) |
| 0.84 | ES=F / NQ=F | equity (S&P / Nasdaq) |
| 0.81 | ZB=F / ZF=F | bonds (30Y / 5Y) |
| 0.74 | EURUSD / GBPUSD | fx |

Every offending pair is two instruments of the SAME class measuring nearly the same thing.
D5's companion metrics (ENB 12.27 of 26, PC1 0.17) show the basket IS genuinely ~12
independent bets — within-class duplication is already discounted at the portfolio level.
The max-pairwise-corr<0.70 sub-gate conflicts with the ENB/PC1 sub-gates and would fail
ANY liquid universe holding 2 oils / multiple curve points / 2 equity indices. This is a
gate-SPECIFICATION defect (a universe-construction pruning step mis-encoded as a result
gate), not evidence against the phenomenon. PER §10 THE VERDICT STANDS AS FAIL — the gate
is not relaxed on this data. Remedy belongs in a separately pre-registered re-test.
