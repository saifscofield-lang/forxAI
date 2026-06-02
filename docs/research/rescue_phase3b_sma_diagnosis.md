# Rescue Plan — Phase 3b: SMA Crossover Root-Cause Diagnosis

**Data:** 7 symbols × 60,000 H1 bars. Exits SL=2.0×/TP=3.0×ATR, ordered, horizon=100. SMA is a TREND strategy.

## T1 — Trend-continuation premise test

Forward move over 12 bars (ATR units) after each SMA20/50 cross, pooled. Edge exists only if cross-up move > 0 and cross-down move < 0.

| Cross | n | Mean fwd-move (ATR) | % in trend dir | Edge? |
|---|---:|---:|---:|:--:|
| Bullish (expect +) | 4,665 | +0.014 | 51% | ❌ |
| Bearish (expect −) | 4,664 | +0.045 | 48% | ❌ |

## T2 — Regime split (ADX)

| Regime | Trades | Wins | Losses | **R-PF** |
|---|---:|---:|---:|---:|
| RANGING (ADX<20) | 232 | 89 | 143 | **0.93** |
| TRANSITION (20–25) | 208 | 85 | 123 | **1.04** |
| TRENDING (ADX>25) | 224 | 106 | 118 | **1.35** |

## T3 — Parameter & timeframe sweep: any config with PF>1?

| Config | Trades | Win% | **R-PF** |
|---|---:|---:|---:|
| H1 10/30 | 1364 | 42% | **1.09** |
| H1 20/50 (CURRENT) | 662 | 42% | **1.09** |
| H1 50/100 | 280 | 39% | **0.94** |
| H1 50/200 | 139 | 40% | **1.01** |
| M15 20/50 | 1120 | 38% | **0.91** |
| M15 50/200 | 282 | 41% | **1.03** |

## T4 — Walk-forward (H1 20/50): stable?

| Block | Trades | Win% | **R-PF** |
|---|---:|---:|---:|
| block 1 | 232 | 44% | **1.18** |
| block 2 | 207 | 43% | **1.13** |
| block 3 | 223 | 39% | **0.98** |

## Verdict guidance

- T1: SMA is trend-following, so unlike RSI the premise *should* hold if momentum exists. If cross-up move ≈ 0, the lag has eaten the move (signal too late).
- T3: if any period/timeframe (esp. M15, which rescued MACD) clears PF>1, SMA is fixable by reconfiguration rather than retirement.
- If no config/regime/block clears PF>1, retire like RSI/ml_direct and let MACD-M15 carry the trend edge alone.

## VERDICT — ⚠️ RESCUE, do NOT retire (unlike RSI / ml_direct)

SMA is marginal-but-real, and crucially it behaves like a genuine trend strategy:

- **T2 is the key finding — clean monotonic edge with trend strength:**
  RANGING PF 0.93 → TRANSITION 1.04 → **TRENDING (ADX>25) PF 1.35.** The edge is
  real but lives only in trending regimes; ranging markets bleed it away.
- **T3:** the current H1 20/50 is already **PF 1.09** over 662 trades (and 10/30
  also 1.09) — mildly profitable, NOT the −EV the tiny 9-trade live sample
  suggested. M15 does NOT help SMA (0.91) — opposite of MACD; keep SMA on H1.
- **T4:** 2 of 3 walk-forward blocks profitable (1.18 / 1.13 / 0.98) — mostly
  stable, thin.
- **T1:** the premise is weak (lag eats most of the move) — which is exactly why
  the raw strategy is only marginal and needs the regime gate to be worthwhile.

**Recommended rescue:** add an **ADX>25 (trending) regime gate** to SMA. Evidence
projects PF ~1.35 on ~⅓ of current signals — a real second trend edge alongside
MACD-M15, consistent with the "FX rewards momentum" thesis.

**Caveats before shipping:** (1) this clean sim excludes spread/slippage, which
on a 1.09 raw PF could erode to break-even — the ADX-gated 1.35 version has the
margin to survive it; (2) validate the *gated* config in walk-forward (not just
full-sample T2) before live. So: rescue candidate, pending a gated-config
validation pass.