# Rescue Plan — Phase 3a: RSI Reversal Root-Cause Diagnosis

**Data:** 7 symbols × 60,000 H1 bars. RSI exits SL=2.0×/TP=3.0×ATR, ordered, horizon=100.

## T1 — Mean-reversion premise test

Forward move over 6 bars (in ATR units) after each RSI extreme, pooled. Reversion is real only if oversold fwd-move > 0 and overbought fwd-move < 0.

| Condition | n | Mean fwd-move (ATR) | % in reversion dir | Reversion edge? |
|---|---:|---:|---:|:--:|
| Oversold RSI<30 (expect +) | 23,138 | -0.027 | 52% | ❌ |
| Overbought RSI>70 (expect −) | 25,414 | +0.029 | 51% | ❌ |

Interpretation: a mean |fwd-move| baseline is ~1.291 ATR; reversion 'edge' must be a clear non-zero move in the bounce direction.

## T2 — Regime split (ADX): does RSI win when ranging?

| Regime | Trades | Wins | Losses | **R-PF** |
|---|---:|---:|---:|---:|
| RANGING (ADX<20) | 1 | 1 | 0 | **inf** |
| TRANSITION (20–25) | 29 | 7 | 22 | **0.48** |
| TRENDING (ADX>25) | 418 | 142 | 276 | **0.77** |

## T3 — Parameter sweep: is ANY config profitable?

| Config | Trades | Win% | **R-PF** |
|---|---:|---:|---:|
| CURRENT 30/70, 2bar, price | 445 | 33% | **0.76** |
| 25/75, 2bar, price | 182 | 32% | **0.70** |
| 20/80, 2bar, price | 54 | 31% | **0.69** |
| 30/70, no 2bar | 1655 | 36% | **0.84** |
| 30/70, no price confirm | 445 | 33% | **0.76** |
| 20/80, no filters (raw extremes) | 549 | 33% | **0.74** |

## T4 — Walk-forward (current config): is any edge stable?

| Block | Trades | Win% | **R-PF** |
|---|---:|---:|---:|
| block 1 | 155 | 29% | **0.61** |
| block 2 | 133 | 34% | **0.77** |
| block 3 | 157 | 38% | **0.90** |

## Verdict guidance

- **T1** is the make-or-break: if RSI extremes do not produce a reversion move, the strategy's premise is invalid and no parameter tuning will save it.
- **T2**: if PF > 1 in RANGING only, a regime filter (trade RSI only when ADX<20) is a candidate rescue — otherwise retire.
- **T3/T4**: if no config clears PF>1 and no block is positive, RSI reversal has no recoverable edge on this data → retire like ml_direct.

## VERDICT — ❌ RETIRE RSI Reversal

Every test fails:
- **T1 (premise):** FALSE. After oversold, price drifts −0.027 ATR (expected
  +bounce); after overbought, +0.029 ATR (expected −fall). 51–52% ≈ coin flip.
  There is actually a faint **continuation/momentum** bias — the OPPOSITE of the
  mean-reversion this strategy assumes. The premise is empirically invalid.
- **T2:** no regime is profitable (trending PF 0.77; the ATR≥1.2 filter starves
  the ranging bucket where reversion might work).
- **T3:** NO parameter config clears PF 1.0 (best 0.84, still losing).
- **T4:** all 3 walk-forward blocks PF < 1.0 — consistently losing, not unlucky.

No tuning, regime filter, or threshold rescues a strategy whose core premise the
data rejects. Retire it as we retired ml_direct.

## Strategic insight (why this matters beyond RSI)

The continuation bias in T1 is the key: at H1/M15 these FX pairs reward
**momentum/trend-following**, not mean-reversion. This coherently explains the
whole strategy ledger —
- MACD (trend/momentum) = the one survivor with a (thin) edge;
- RSI reversal & Bollinger bounce (both mean-reversion) = both failed/retired.

Implication for the rescue: stop trying to fix mean-reversion strategies. Future
effort should go to **trend/momentum** approaches (strengthen MACD, add a
breakout/trend-continuation strategy), where the data says the edge lives.