# Rescue Plan — Phase 4a: Breakout T1 Premise Diagnosis

**Data:** 7 symbols × 60,000 H1 bars, pooled. Fresh Donchian breakouts, forward move over 12 bars in ATR units. ADX via project compute_adx.

Edge exists only if **upside break fwd-move > 0** and **downside < 0**, clearly above the noise baseline.

Noise baseline: mean |forward move| ≈ **1.903 ATR**.

## Channel N=20

| Condition | Regime | n | Mean fwd-move (ATR) | % in trend dir | Edge? |
|---|---|---:|---:|---:|:--:|
| UP break (expect +) | ALL | 16,357 | -0.016 | 49% | ❌ |
| UP break (expect +) | TRENDING ADX≥25 | 7,413 | -0.082 | 48% | ❌ |
| UP break (expect +) | RANGING ADX<20 | 5,442 | +0.038 | 50% | ~ |
| DN break (expect −) | ALL | 14,710 | +0.045 | 48% | ❌ |
| DN break (expect −) | TRENDING ADX≥25 | 7,376 | +0.040 | 48% | ❌ |
| DN break (expect −) | RANGING ADX<20 | 4,351 | +0.019 | 49% | ❌ |
## Channel N=55

| Condition | Regime | n | Mean fwd-move (ATR) | % in trend dir | Edge? |
|---|---|---:|---:|---:|:--:|
| UP break (expect +) | ALL | 9,729 | -0.034 | 49% | ❌ |
| UP break (expect +) | TRENDING ADX≥25 | 5,389 | -0.077 | 48% | ❌ |
| UP break (expect +) | RANGING ADX<20 | 2,419 | -0.012 | 51% | ❌ |
| DN break (expect −) | ALL | 8,424 | +0.074 | 48% | ❌ |
| DN break (expect −) | TRENDING ADX≥25 | 5,489 | +0.063 | 47% | ❌ |
| DN break (expect −) | RANGING ADX<20 | 1,468 | -0.018 | 50% | ❌ |

## How to read / next step

- **Make-or-break:** in the TRENDING bucket, upside breaks should show a clearly positive forward move and downside clearly negative — that is the continuation edge the strategy will harvest.
- If TRENDING shows edge but ALL/RANGING do not, the regime gate (ADX≥25) is justified and becomes a core part of the design (as in SMA Phase 3b).
- If even the TRENDING bucket is ≈0, breakouts do not predict continuation on this data → stop and reconsider (do not proceed to T2–T4), exactly as we would have for a failed RSI premise.
- Caveat: fwd move ≠ tradable P&L (no SL/TP/spread). T1 only checks the premise; economics come in T2–T4.

## VERDICT — ❌ PREMISE FAILS. Do NOT build the breakout strategy.

The continuation premise is not merely absent — it is **mildly inverted**:
- Upside breaks (N=20) drift **−0.016 ATR** overall and **−0.082 ATR in the
  TRENDING bucket** (expected positive). Downside breaks drift **+0.045 ATR**
  (expected negative). N=55 is the same picture.
- All buckets are 47–51% in the trend direction ≈ coin flip.

So on these H1 FX pairs, channel breakouts get **FADED** (the classic FX
false-breakout): upside breaks tend to get sold, downside breaks bought. The
regime gate does NOT rescue it — TRENDING is the WORST bucket for continuation.
Per protocol (as with a failed RSI premise) we STOP here and do not proceed to
T2–T4.

## Bigger picture (the honest meta-finding of the whole rescue)

Tally of premise/edge across everything tested on price-only H1/M15 technicals:
- MACD (filtered momentum): thin edge, PF ~1.0–1.09
- SMA cross (trend): thin edge, PF ~1.10 (lag-limited)
- RSI reversal (mean-reversion): no edge — premise false
- Donchian breakout (momentum): no edge — premise inverted (fade)
- ml_direct (ML direction): no edge — features predict volatility not direction

**The consistent signal is that price-only technical alpha on H1 FX is
thin-to-absent.** MACD-M15 (~1.03) is the best available and it is thin. The
faint breakout-fade tendency (−0.08 ATR, 48%) is too weak/noisy to pivot into a
tradable fade strategy with confidence (it would be eaten by spread).

**Strategic implication:** stop hunting for a strong price-only H1 signal — the
evidence says it is not there. Realistic paths: (a) accept MACD-M15 as a thin
engine and compete on execution/risk/sizing; (b) look beyond price-only H1
technicals — higher timeframe (D1) trend, carry/fundamentals, cross-asset, or
session/seasonality — which are different information, not more TA on the same
bars.