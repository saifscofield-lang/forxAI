# Decision — Retire `rsi_reversal` (2026-06-03)

**Decision:** Permanently retire the RSI Reversal strategy. Removed from
`scripts/paper_trade.py` registration (import + block commented, with re-enable
conditions).
**Status:** RETIRED — class and file remain for reference; the live system no
longer trades it.

## Why

A four-test diagnosis (Phase 3a, `docs/research/rescue_phase3a_rsi_diagnosis.md`)
shows the strategy's core premise is empirically false and no configuration
recovers an edge.

| Test | What it checked | Result |
|---|---|---|
| T1 Premise | Does an RSI extreme actually precede a reversion move? | **FALSE.** Oversold (RSI<30) → +mean fwd-move of **−0.027 ATR** (expected positive bounce); overbought (RSI>70) → **+0.029 ATR**. 51–52% ≈ coin flip, with a faint **continuation** bias — the opposite of mean-reversion. |
| T2 Regime | Does it win when ranging (ADX<20)? | No. Trending PF 0.77; ATR≥1.2 filter starves the ranging bucket. No profitable regime. |
| T3 Params | Any oversold/overbought / confirmation config with PF>1? | No. Best 0.84 (still losing); tighter thresholds worse. |
| T4 Walk-forward | Is any edge stable across time? | No. All 3 blocks PF < 1.0 (0.61 / 0.77 / 0.90). |

Baseline economics (Phase 1e/1f): RSI R-PF 0.89 (H1) / 0.94 (M15) — losing on
both timeframes.

**Root cause:** mean-reversion at RSI extremes does not exist at H1/M15 on these
pairs; if anything there is weak momentum continuation. The premise is invalid,
so no tuning can save it.

## Strategic context (the bigger pattern)

This is the second mean-reversion strategy to fail (Bollinger bounce was retired
2026-04-28). Together with MACD (trend/momentum) being the lone survivor, the
evidence says **H1/M15 FX rewards momentum/trend, not mean-reversion.** Future
strategy work should target trend/breakout/continuation, not reversion.

## Active strategies after this retirement

| Strategy | Status |
|---|---|
| macd_crossover | ACTIVE — on M15 (Rescue Phase 1f) |
| sma_crossover | still registered; weak historically — diagnosis pending |
| rsi_reversal | **RETIRED (this doc)** |
| ml_direct | RETIRED 2026-06-02 |
| bollinger_bounce, ml_filtered, stop_hunt, asia | retired/archived earlier |

So the live directional edge now rests on MACD-M15 (plus SMA pending review).
This concentration is intentional: better one thin-but-real edge than several
negative-EV strategies diluting the book and the evaluation sample.

## Re-enable conditions

Re-enable only with a configuration demonstrating **OOS PF > 1.0 across all
walk-forward blocks** — which this diagnosis could not find. A regime-gated
variant (RSI only in confirmed ranging regimes) could be re-tested IF the ATR
filter is relaxed for it so ranging signals are not starved; but T1 suggests
even that is unlikely to clear the bar.

## Operational follow-up (live)

- Record in the **live tracker DB** `decisions_log` (category STRATEGY); local
  checkout DB is stale.
- After `git pull` + engine restart, confirm the scan log no longer registers
  `rsi_reversal`; manage any open RSI positions to close under existing monitor
  logic (no new RSI entries).

## Code change

- `scripts/paper_trade.py`: import + registration commented with dated reason
  and re-enable conditions (same pattern as ml_direct / bollinger / ml_filtered).
- No engine/risk/model changes. Reversible by uncommenting.

## Cross-references
- `docs/research/rescue_phase3a_rsi_diagnosis.md` — the diagnosis
- `docs/research/rescue_phase1f_m15_validation.md` — RSI/MACD M15 economics
- `docs/research/ml_direct_retirement_2026_06_02.md` — prior retirement (same rigor)
