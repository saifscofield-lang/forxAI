# Phase 13 — Volatility Risk Premium — Stage 2 RESULTS

Per frozen pre-reg (commit cec6279). Short VXX (primary). No tuning. Verdict @K=12.

## Data coverage
- VXX: 2018-01-25..2026-06-12 (2107 days)
- SVXY: 2011-10-04..2026-06-12 (3694 days)
- ^VIX: 2004-01-02..2026-06-12 (5648 days)
- ^VIX3M: 2006-07-17..2026-06-12 (5009 days)
- ^GSPC: 2004-01-02..2026-06-12 (5647 days)

## Primary strategy: SHORT VXX (real series starts 2018-01-25)

- DISCLOSURE (pre-reg §2.3): tradable VXX history begins 2018-01-25, later than the
  2010 target. Train window is the earliest clean start .. 2023-12-31 (disclosed, not silently truncated).

## Metrics (train, for VRP-adapted G1-G8)
- train 2018-01-31..2023-12-31 (72 mo)  OOS 30 mo
- mean -0.693%/mo  t=-2.24  Sharpe=-0.92
- OOS mean -0.366%  Sharpe=-0.59  drift_p=1.00
- regimes: {'vix_low': -0.008886001495740162, 'vix_mid': -0.004311521955488024, 'vix_high': -0.0044695893260935145}
- months_positive=24%  net@1.5x=-0.728%/mo  PF=0.46
- tail MDD=42.3%  beats_passive=False (B&H Sharpe +0.45)

## GUARDIAN VERDICT (declared VRP gates, K=12)

**VERDICT: FAIL**
- passed: ['G1', 'G8']
- failed: ['G2', 'G3', 'G4', 'G5', 'G6', 'G7']
- DSR: 0.000 (SR=-0.264 SR0=0.207 K=12)
  - G1 [PASS] economic_rationale_present=True == True -> True
  - G2 [FAIL] mean_period=-0.006927>0.0:N & t_stat=-2.242>=2.0:N
  - G3 [FAIL] DSR=0.000 (need>=0.95) | SR=-0.264 SR0=0.207 K=12
  - G4 [FAIL] oos.mean=-0.003663>0.0:N & oos.sharpe=-0.5929>=0.3:N & oos.drift_p=1>0.05:Y
  - G5 [FAIL] all>0? False [vix_low:-0.008886, vix_mid:-0.004312, vix_high:-0.00447]
  - G6 [FAIL] months_positive_pct=0.2361 >= 0.55 -> False
  - G7 [FAIL] cost.net_mean_1_5x=-0.007276>0.0:N & tail.mdd=0.423<0.3:N & beats_passive=False==True:N
  - G8 [PASS] no_leverage=True == True -> True
  - FLAG [info] DEF-3-cost-cliff: Edge does not survive costs (net_mean_1x=None, pf_net=0.46021227930966363). Pre-cost performance is an illusion.

## Robustness (SVXY long, report only): Sharpe +0.48 over 147 mo (note SVXY -0.5x post-2018 artifact)

---
Per §6 step 4: FAIL recorded. No relaxation, no re-tune, OOS holdout NOT opened.
