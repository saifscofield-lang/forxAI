# Freeze Window Status — Day 24 of STABLE_v2

**Date:** 2026-06-02
**Freeze start:** 2026-05-09
**Days in freeze:** 24
**Original gate target:** 2026-06-20 (Day 42)
**Engine status:** ✅ Healthy, scan #406 completed at 22:05 UTC today

> The 6-week freeze window is roughly halfway through. The honest read:
> trade cadence is far below what's needed for the 30-trade H4 gate
> by June 20. The gate will need to extend.

## Trades during STABLE_v2

**Total:** 7 v3 trades closed (TSMOM tracked separately — see TSMOM section).

| # | Date (UTC) | Symbol | Strategy | Direction | PnL ($) | Result |
|---|---|---|---|---|---:|---|
| 1 | 2026-05-15 06:05 | GBPUSD | ml_direct | SELL | +196.00 | ✅ |
| 2 | 2026-05-15 07:05 | GBPUSD | ml_direct | SELL | +164.00 | ✅ |
| 3 | 2026-05-15 08:05 | GBPUSD | ml_direct | SELL | +60.00 | ✅ |
| 4 | 2026-05-15 10:05 | GBPUSD | ml_direct | SELL | +20.00 | ✅ |
| 5 | 2026-05-15 16:05 | USDCHF | macd_crossover | BUY | +25.42 | ✅ |
| 6 | 2026-05-19 10:05 | GBPUSD | ml_direct | SELL | -254.00 | ❌ |
| 7 | 2026-05-19 12:05 | GBPUSD | ml_direct | SELL | -243.00 | ❌ |

**Per-strategy concentration:** 6 of 7 trades from `ml_direct` on GBPUSD.
Only one other strategy fired (`macd_crossover` on USDCHF). The other
20 strategy×symbol combinations were silent across 24 days.

## Phase 8 gate progress

| Gate | Threshold | Current | Status |
|---|---|---|---|
| H1 R-PF | ≥ 1.30 | n/a (under-sampled) | — |
| H2 $-PF | ≥ 1.00 | **0.936** | ❌ MARGINAL FAIL |
| H3 Max drawdown | < 10% peak | small (~0.02% net) | ✅ |
| H4 Total trades | ≥ 30 | **7** | ❌ SHORT |
| H5 Active symbols | ≥ 3 | **2** (GBPUSD, USDCHF) | ❌ SHORT |
| H6 Both directions on ≥2 symbols | both BUY and SELL | **only SELL** (GBPUSD), **only BUY** (USDCHF) | ❌ SHORT |
| H7 Code freeze final 14 days | zero engine commits | ✅ holding | ✅ |
| H8 Slippage budget | ≤ 1.5 pips FX | needs analysis | (pending) |

**Two hard gates are insufficient-data fails** (H4, H5, H6) — the
sample simply isn't there. The other key metric ($-PF) sits at 0.936,
just below the 1.00 break-even gate. With only 7 trades, this number
is **not statistically meaningful** — one more winning or losing trade
moves it ±0.05.

## Account state

| | Value |
|---|---|
| Balance at freeze start (2026-05-10 22:05) | $111,002.45 |
| Balance now (2026-06-02 19:05) | $110,978.91 |
| Net change | **−$23.54** (−0.02%) |
| TSMOM unrealized (from May 8 positions) | shifting daily; still net positive |

The −$31.58 net from the 7 closed v3 trades is mostly offset by
TSMOM unrealized gain — net account is essentially flat.

## Why so few trades

The 4 active v3 strategies each require **multiple filter
conditions to align simultaneously:**

- **rsi_reversal:** RSI < 30 or > 70 + 2-bar confirmation +
  price-direction match
- **macd_crossover:** MACD line cross + EMA50/200 trend confirm +
  histogram momentum + ATR ≥ 1.2× threshold
- **sma_crossover:** SMA20/50 cross + RSI filter
- **ml_direct:** ML model confidence ≥ 55% (only XAUUSD blacklisted)

Reading the engine log, the typical scan reports `NO SIGNAL` for
5 of 6 symbols every hour. RSI values during the freeze period
have mostly sat in the 30-70 "no man's land" zone. The one
strategy that has fired consistently — `ml_direct` on GBPUSD —
appears to bunch trades around the same setup conditions (the
4 wins were all on 2026-05-15 in consecutive hours; the 2 losses
were on 2026-05-19 in close succession).

**The strategies are working as designed.** They're not firing on
noise. They're waiting for setup conditions that simply haven't
appeared often in the May 9 → Jun 2 window.

## TSMOM (parallel layer)

4 BUY positions opened 2026-05-08 21:12 (one day before STABLE_v2
formal start). Still open. Per `phase8_success_criteria.md`
caveat 3, these do NOT count toward Phase 8 H4 — TSMOM is a
parallel evaluation track, not the v3 strategy stack under test.

Next TSMOM rebalance evaluation: first day of June (passed —
no flip occurred because direction unchanged on all 4 symbols).
The monthly rebalance triggers on the first calendar day of a
new month, which means June 1 was a check day. The rebalance
script was not manually run on June 1; if it had been, the
existing positions would have been HELD (same direction) and no
new orders placed.

## Engine health

- ✅ 1 forexAI venv python process running
- ✅ MT5 connection active (account 5047751974)
- ✅ Scan cadence on time (`Scan #406` at 22:05 UTC today)
- ✅ News filter active (correctly blocked all symbols around CPI on 2026-05-12)
- ✅ Shadow tracker writing rows (207 shadow rows since freeze)
- ✅ Position monitor active (SL adjustments logged)
- ✅ No errors in log
- ✅ Daily TSMOM scanner firing on schedule (Task Scheduler)

The shadow-write silence concern from 2026-05-09 (AI-022) appears
resolved: shadow rows have been written consistently every hour
since market reopened on Sunday 2026-05-10 22:00 UTC. The May 8
night silence (3 missed rows) self-resolved and never recurred.
**AI-022 can be closed at the next tracker review.**

## Projected gate timeline

Current trade pace: 7 trades / 24 days = **0.29 trades/day**.

To reach 30 closed v3 trades at this pace: **103 more days**
from today = approximately **2026-09-13**.

The original 2026-06-20 target is unreachable without a regime
shift that produces more setups. Honest options:

1. **Extend the freeze gate.** Wait until 30 closed trades
   accumulate even if it pushes Phase 8 review into late August
   or September. Most disciplined; respects the H4 evidence bar.

2. **Lower H4 threshold to 15-20 trades.** Faster, but weakens
   the already-thin statistical bar. Discussed and rejected
   2026-05-09 — 30 was already a sufficiency check, not a
   confidence check.

3. **Reconsider strategy mix at the gate review.** Some
   strategies are genuinely silent (sma_crossover, rsi_reversal
   have not fired once during the freeze). The gate review can
   decide whether silent strategies stay in rotation.

**My recommendation: Option 1 — extend the gate.** Don't
compromise the discipline that the freeze is designed to enforce.

## What the data already tells us

Even with only 7 trades, some patterns warrant attention as
diagnostics (NOT performance verdicts):

- **`ml_direct` on GBPUSD is the most active strategy.** 6 of 7
  trades. If the gate review focuses on the working strategies,
  this is the one to study most carefully.
- **The 4 GBPUSD wins on 2026-05-15 (06:00-10:00 UTC)** and
  **2 losses on 2026-05-19 (10:00-12:00 UTC)** suggest setup
  clustering — the model is producing signals during specific
  market conditions, then going silent for days. This is
  consistent with the broader project pattern of low-frequency
  high-conviction setups.
- **The 2 losses both had similar ML confidence (56.1%, 56.3%)
  to the 4 wins (55.9%-59.6%).** The ML model is not
  differentiating winning from losing setups at the 0.55
  threshold level. This is the exact problem Phase 7 was
  supposed to fix and could not — see Phase 7 verdict.
- **3 strategies (rsi_reversal, sma_crossover, plus ml_direct on
  5 of 6 symbols) produced zero trades in 24 days.** These need
  Phase 8 post-mortem.

## What's been done during the freeze (none touched trading code)

| Date | Commit | Type |
|---|---|---|
| 2026-05-09 | `f169bef` | Freeze policy + STABLE_v2 segmentation row + post-freeze backlog |
| 2026-05-09 | `5c673f5` | Dashboard freeze-progress widget |
| 2026-05-09 | `89cf33c` | Phase 9 graduation gates (100 / 200 trade bars) |
| 2026-06-02 | THIS | Status snapshot doc + tracker DB update |

No commits to `engine/`, `strategies/`, `risk/`, `execution/`,
`news/`, `features/regime_detector.py`, or trade-affecting
`config/paper.yaml` keys. **The freeze is intact.**

## Next checkpoint

Mid-June (around 2026-06-15): another status snapshot. By that
point we'll be ~37 days into the freeze. If trade pace remains
near 0.3/day, the H4 gate (30 trades) will be projected for
late August / early September.

The Phase 7 path-selection vote (originally scheduled 2026-06-08)
is independent of trade accumulation and can still happen on
schedule — see `docs/meetings/2026_06_08_phase7_ship_gate.md`.

## Cross-references

- `docs/research/code_freeze_policy.md` — freeze rules
- `docs/research/phase8_success_criteria.md` — gate definitions
- `docs/research/post_freeze_backlog.md` — deferred work
- `docs/meetings/2026_06_08_phase7_ship_gate.md` — next decision meeting
- `data/improvements.db` `data_segmentation_log` row 4 — STABLE_v2 definition
- `data/improvements.db` `decisions_log` rows 41-48 — full decision chain
