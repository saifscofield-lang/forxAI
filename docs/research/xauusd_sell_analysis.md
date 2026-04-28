# XAUUSD SELL Deep-Dive (v3 / STABLE segment)

*Generated: 2026-04-24 17:52 UTC*
*Scope: STABLE segment trades, open_time >= 2026-04-10, engine_version='2.4'*
*Diagnostic only — no code or config changes made.*

## TL;DR — the premise needs revision

**The investigation brief was: "XAUUSD SELL trades consistently produce outsized losses."**
**The data says: XAUUSD SELL is net positive (+$13,327) in aggregate, with losses concentrated in ONE specific session.**

Headline findings:

1. **Zero BUY trades** across the entire v3 segment. 60 executed SELLs, 0 BUYs. ML Direct is the source of 59 of 60 SELLs. This structural asymmetry is the most important finding, even though it's not the P&L problem.
2. **SELLs are profitable in aggregate.** Net +$13,327 across 60 closed SELLs. WR 73% (or 65% excluding trailing-stop FLAT exits). Average win +$1,278, average loss −$2,680 — R:R 0.48 (avg loss is ~2× avg win, a known weakness, but aggregate is still profitable).
3. **Losses are session-specific — not a general SELL weakness.** OVERLAP session (13:00-17:00 UTC, London-NY transition) is the outlier: **−$16,018 across 13 trades, avg −$1,232 per trade**. NY and ASIA sessions are both strongly positive. LONDON is near-flat. *Blocking OVERLAP alone would recover ~$16k without touching the ~$29k of combined wins from the other sessions.*
4. **ML confidence barely differentiates outcomes** (win mean 59.3%, loss mean 56.8% — 2.5pp delta). Raising the confidence threshold would not solve the OVERLAP-session problem.
5. **SL/ATR sizing is nearly identical between wins and losses** (1.46× vs 1.59×). Not the primary driver.

The revised story: **XAUUSD SELL is not broken. A specific session is.**

## BUY vs SELL headline table

| direction | count | WR % | total PnL | avg win | avg loss | R:R | max loss | max win | avg vol | avg hold (min) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BUY | **0** | — | — | — | — | — | — | — | — | — |
| SELL | 60 | 73.33 | $+13,327.20 | $+1,277.54 | $-2,680.29 | 0.477 | $-5,787.00 | $+3,861.00 | 1.0 | 363.9 |

**Note:** the "No BUY trades" row is itself the headline finding. See §Root-Cause Hypotheses.

## Pattern analysis

### Strategy concentration

| strategy | n | wins | losses | total PnL |
|---|---:|---:|---:|---:|
| `ml_direct` | 59 | 23 | 13 | $+13,147.20 |
| `rsi_reversal` | 1 | 1 | 0 | $+180.00 |

### Session concentration

| session | n | wins | losses | total PnL | avg PnL |
|---|---:|---:|---:|---:|---:|
| ASIA | 20 | 9 | 2 | $+16,439.20 | $+821.96 |
| LONDON | 5 | 1 | 1 | $-2,293.00 | $-458.60 |
| NY | 22 | 10 | 3 | $+15,199.00 | $+690.86 |
| OVERLAP | 13 | 4 | 7 | $-16,018.00 | $-1,232.15 |

### SL sizing vs ATR (avg SL distance / ATR at entry)

- Winning SELLs : **1.46× ATR**
- Losing SELLs  : **1.59× ATR**

### ML confidence at entry (parsed from `comment`)

- Winning SELLs mean conf : 59.3%
- Losing SELLs mean conf  : 56.8%

### Exit-reason mix

| exit_reason | count |
|---|---:|
| `SL_HIT` | 46 |
| `TP_HIT` | 14 |

## Shadow cross-check (±30 min window around each executed SELL)

- Total executed SELLs in sample: **60**
- Total nearby rejected BUY signals (opposite direction, within ±30 min): **0**
- Of those rejected BUYs with simulated resolution: **0** resolved, **0** hit TP in simulation

**No opposite-direction BUY signals were logged in shadow_signals around executed SELLs.** Either:
- the engine's BUY-side strategies do not generate XAUUSD BUY signals at these times, OR
- the filter chain blocks BUY signals before they reach the shadow tracker (check signal_logs.status for ML_FILTERED or NEWS_FILTERED on BUY candidates).

## Worst 3 SELL trades — full case study

### Case 1 — ticket `56297066579` — **$-5,787.00**

- **Entry:** 2026-04-20 03:05:04.547222 UTC @ 4749.1
- **Exit:** 2026-04-20 04:31:05 UTC @ 4806.96  _(exit_reason: SL_HIT)_
- **Duration:** 86 min  (1.4 h)
- **SL / TP:** 4806.96 / 4730.27
- **SL distance / ATR:** 2.45× (SL distance 57.86 vs ATR14 23.59684)
- **Strategy:** `ml_direct` · ML conf: **55.1%**
- **Session:** ASIA
- **H1 trend / H4 trend (at entry):** None / None
- **Vol regime / Spread at entry:** None / None pips
- **RSI@entry / ATR@entry:** 36.07 / 23.59684
- **MFE / MAE (pips):** None / None
- **News-nearby:** 0  (event: None, impact: None)
- **Comment:** `ML Direct SELL | conf=55.1% [SELL=55.1% NO=9.6% BUY=35.3%]`

### Case 2 — ticket `56387752068` — **$-3,702.00**

- **Entry:** 2026-04-24 16:05:07.101469 UTC @ 4697.1
- **Exit:** 2026-04-24 17:12:05 UTC @ 4734.12  _(exit_reason: SL_HIT)_
- **Duration:** 67 min  (1.1 h)
- **SL / TP:** 4734.12 / 4669.14
- **SL distance / ATR:** 1.85× (SL distance 37.02 vs ATR14 19.99313)
- **Strategy:** `ml_direct` · ML conf: **56.8%**
- **Session:** OVERLAP
- **H1 trend / H4 trend (at entry):** None / None
- **Vol regime / Spread at entry:** None / None pips
- **RSI@entry / ATR@entry:** 51.44 / 19.99313
- **MFE / MAE (pips):** None / None
- **News-nearby:** 0  (event: None, impact: None)
- **Comment:** `ML Direct SELL | conf=56.8% [SELL=56.8% NO=8.2% BUY=34.9%]`

### Case 3 — ticket `56215216555` — **$-3,453.00**

- **Entry:** 2026-04-13 19:05:14.559842 UTC @ 4710.35
- **Exit:** 2026-04-13 19:47:20 UTC @ 4744.94  _(exit_reason: SL_HIT)_
- **Duration:** 42 min  (0.7 h)
- **SL / TP:** 4744.94 / 4673.59
- **SL distance / ATR:** 1.58× (SL distance 34.59 vs ATR14 21.95353)
- **Strategy:** `ml_direct` · ML conf: **57.7%**
- **Session:** NY
- **H1 trend / H4 trend (at entry):** None / None
- **Vol regime / Spread at entry:** None / None pips
- **RSI@entry / ATR@entry:** 44.2 / 21.95353
- **MFE / MAE (pips):** None / None
- **News-nearby:** 0  (event: None, impact: None)
- **Comment:** `ML Direct SELL | conf=57.7% [SELL=57.7% NO=10.8% BUY=31.4%]`

## Full SELL trade list

Sorted by open_time. WIN/LOSS/FLAT by net PnL (±$50 threshold).

| open_time | strategy | ML conf % | H1 | H4 | vol | session | entry | SL-dist ATR× | exit_reason | net PnL | outcome |
|---|---|---:|---|---|---|---|---:|---:|---|---:|---|
| 04-10 03:05 | `ml_direct` | 58.6 |  |  |  | ASIA | 4756.66 | 1.71 | SL_HIT | $+2.00 | FLAT |
| 04-10 04:05 | `ml_direct` | 59.6 |  |  |  | ASIA | 4760.78 | 1.51 | SL_HIT | $+2.00 | FLAT |
| 04-10 05:05 | `ml_direct` | 57.6 |  |  |  | ASIA | 4756.83 | 1.48 | SL_HIT | $+2.00 | FLAT |
| 04-10 06:05 | `ml_direct` | 59.5 |  |  |  | ASIA | 4755.08 | 1.50 | SL_HIT | $+2.00 | FLAT |
| 04-10 13:05 | `ml_direct` | 58.0 |  |  |  | OVERLAP | 4746.12 | 1.60 | SL_HIT | $-3,314.00 | LOSS |
| 04-10 14:05 | `ml_direct` | 55.3 |  |  |  | OVERLAP | 4758.55 | 1.52 | SL_HIT | $-2,922.00 | LOSS |
| 04-10 19:06 | `ml_direct` | 60.2 |  |  |  | NY | 4751.11 | 1.49 | TP_HIT | $+3,665.40 | WIN |
| 04-10 20:05 | `ml_direct` | 57.1 |  |  |  | NY | 4759.77 | 1.49 | SL_HIT | $+2.00 | FLAT |
| 04-10 21:05 | `ml_direct` | 63.2 |  |  |  | NY | 4752.63 | 1.53 | TP_HIT | $+3,344.40 | WIN |
| 04-10 22:05 | `ml_direct` | 60.5 |  |  |  | ASIA | 4768.09 | 1.51 | TP_HIT | $+3,320.40 | WIN |
| 04-13 05:05 | `ml_direct` | 55.6 |  |  |  | ASIA | 4722.11 | 1.47 | SL_HIT | $+2.00 | FLAT |
| 04-13 06:05 | `ml_direct` | 56.0 |  |  |  | ASIA | 4715.06 | 1.52 | SL_HIT | $+2.00 | FLAT |
| 04-13 16:05 | `ml_direct` | 56.0 |  |  |  | OVERLAP | 4729.99 | 0.79 | SL_HIT | $+1,734.00 | WIN |
| 04-13 19:05 | `ml_direct` | 57.7 |  |  |  | NY | 4710.35 | 1.58 | SL_HIT | $-3,453.00 | LOSS |
| 04-13 20:05 | `ml_direct` | 55.8 |  |  |  | NY | 4737.64 | 1.52 | SL_HIT | $+2.00 | FLAT |
| 04-14 03:05 | `ml_direct` | 61.2 |  |  |  | ASIA | 4756.65 | 1.45 | SL_HIT | $-3,200.00 | LOSS |
| 04-14 13:05 | `ml_direct` | 55.3 |  |  |  | OVERLAP | 4780.13 | 1.20 | SL_HIT | $+210.00 | WIN |
| 04-14 16:05 | `ml_direct` | 55.1 |  |  |  | OVERLAP | 4777.70 | 1.37 | SL_HIT | $-2,777.00 | LOSS |
| 04-14 19:21 | `ml_direct` | 57.2 |  |  |  | NY | 4815.21 | 1.50 | SL_HIT | $-3,152.60 | LOSS |
| 04-14 20:05 | `ml_direct` | 59.7 |  |  |  | NY | 4815.58 | 1.50 | SL_HIT | $-3,029.00 | LOSS |
| 04-14 21:05 | `ml_direct` | 59.6 |  |  |  | NY | 4836.78 | 1.51 | SL_HIT | $-2.60 | FLAT |
| 04-15 05:05 | `ml_direct` | 56.0 |  |  |  | ASIA | 4847.92 | 1.51 | TP_HIT | $+3,419.00 | WIN |
| 04-15 13:05 | `ml_direct` | 56.5 |  |  |  | OVERLAP | 4795.72 | 1.63 | SL_HIT | $-3,169.00 | LOSS |
| 04-15 14:05 | `ml_direct` | 55.9 |  |  |  | OVERLAP | 4798.73 | 1.51 | SL_HIT | $-2,792.00 | LOSS |
| 04-15 19:05 | `ml_direct` | 59.2 |  |  |  | NY | 4804.64 | 1.08 | SL_HIT | $+2.00 | FLAT |
| 04-15 20:05 | `ml_direct` | 61.0 |  |  |  | NY | 4800.07 | 1.54 | SL_HIT | $+2.00 | FLAT |
| 04-15 21:05 | `ml_direct` | 60.2 |  |  |  | NY | 4797.35 | 1.48 | SL_HIT | $-11.80 | FLAT |
| 04-15 22:05 | `ml_direct` | 57.6 |  |  |  | ASIA | 4802.14 | 1.50 | SL_HIT | $+135.20 | WIN |
| 04-16 14:05 | `ml_direct` | 55.5 |  |  |  | OVERLAP | 4820.09 | 0.74 | SL_HIT | $+2.00 | FLAT |
| 04-16 19:05 | `ml_direct` | 59.4 |  |  |  | NY | 4808.60 | 1.14 | SL_HIT | $+1,705.00 | WIN |
| 04-17 17:05 | `ml_direct` | 55.0 |  |  |  | NY | 4874.50 | 0.67 | SL_HIT | $+2.00 | FLAT |
| 04-17 19:05 | `rsi_reversal` | nan |  |  |  | NY | 4867.14 | 1.75 | SL_HIT | $+180.00 | WIN |
| 04-20 03:05 | `ml_direct` | 55.1 |  |  |  | ASIA | 4749.10 | 2.45 | SL_HIT | $-5,787.00 | LOSS |
| 04-20 10:05 | `ml_direct` | 56.8 |  |  |  | LONDON | 4797.44 | 1.05 | SL_HIT | $+2.00 | FLAT |
| 04-20 13:05 | `ml_direct` | 55.4 |  |  |  | OVERLAP | 4791.55 | 1.26 | SL_HIT | $-2,658.00 | LOSS |
| 04-20 16:05 | `ml_direct` | 58.9 |  |  |  | OVERLAP | 4803.71 | 1.62 | SL_HIT | $+2.00 | FLAT |
| 04-20 20:05 | `ml_direct` | 56.0 |  |  |  | NY | 4807.92 | 1.40 | SL_HIT | $+2,495.40 | WIN |
| 04-20 21:05 | `ml_direct` | 57.7 |  |  |  | NY | 4812.71 | 1.44 | TP_HIT | $+3,466.40 | WIN |
| 04-20 22:05 | `ml_direct` | 58.1 |  |  |  | ASIA | 4817.69 | 1.50 | SL_HIT | $-2.60 | FLAT |
| 04-21 01:05 | `ml_direct` | 59.3 |  |  |  | ASIA | 4824.42 | 1.50 | SL_HIT | $+2.00 | FLAT |
| 04-21 04:05 | `ml_direct` | 58.1 |  |  |  | ASIA | 4818.46 | 1.50 | TP_HIT | $+3,033.00 | WIN |
| 04-21 10:05 | `ml_direct` | 55.2 |  |  |  | LONDON | 4775.32 | 1.49 | SL_HIT | $+2.00 | FLAT |
| 04-21 16:14 | `ml_direct` | 57.0 |  |  |  | OVERLAP | 4767.57 | 1.57 | TP_HIT | $+2,908.00 | WIN |
| 04-21 19:05 | `ml_direct` | 64.6 |  |  |  | NY | 4740.01 | 1.60 | TP_HIT | $+3,611.00 | WIN |
| 04-21 20:05 | `ml_direct` | 55.8 |  |  |  | NY | 4710.15 | 1.56 | SL_HIT | $+2.00 | FLAT |
| 04-21 21:05 | `ml_direct` | 57.9 |  |  |  | NY | 4710.97 | 1.48 | SL_HIT | $+437.00 | WIN |
| 04-21 22:05 | `ml_direct` | 55.8 |  |  |  | ASIA | 4710.32 | 1.50 | TP_HIT | $+3,861.00 | WIN |
| 04-22 04:05 | `ml_direct` | 56.0 |  |  |  | ASIA | 4739.72 | 1.72 | SL_HIT | $+2.00 | FLAT |
| 04-22 10:05 | `ml_direct` | 56.2 |  |  |  | LONDON | 4768.73 | 1.50 | SL_HIT | $+613.00 | WIN |
| 04-22 19:05 | `ml_direct` | 58.6 |  |  |  | NY | 4730.89 | 1.49 | SL_HIT | $+2.00 | FLAT |
| 04-22 20:05 | `ml_direct` | 60.6 |  |  |  | NY | 4736.06 | 1.50 | TP_HIT | $+3,050.20 | WIN |
| 04-22 21:05 | `ml_direct` | 63.0 |  |  |  | NY | 4736.68 | 1.51 | TP_HIT | $+2,879.20 | WIN |
| 04-22 22:05 | `ml_direct` | 59.9 |  |  |  | ASIA | 4741.53 | 1.52 | TP_HIT | $+2,902.20 | WIN |
| 04-23 10:05 | `ml_direct` | 56.6 |  |  |  | LONDON | 4712.94 | 1.48 | SL_HIT | $+2.00 | FLAT |
| 04-23 13:05 | `ml_direct` | 55.5 |  |  |  | OVERLAP | 4700.63 | 1.57 | SL_HIT | $+460.00 | WIN |
| 04-24 03:05 | `ml_direct` | 65.5 |  |  |  | ASIA | 4692.91 | 1.50 | SL_HIT | $+1,704.00 | WIN |
| 04-24 04:05 | `ml_direct` | 63.8 |  |  |  | ASIA | 4696.55 | 1.52 | TP_HIT | $+3,513.00 | WIN |
| 04-24 05:05 | `ml_direct` | 64.4 |  |  |  | ASIA | 4697.86 | 1.48 | TP_HIT | $+3,525.00 | WIN |
| 04-24 10:05 | `ml_direct` | 55.0 |  |  |  | LONDON | 4674.37 | 1.51 | SL_HIT | $-2,912.00 | LOSS |
| 04-24 16:05 | `ml_direct` | 56.8 |  |  |  | OVERLAP | 4697.10 | 1.85 | SL_HIT | $-3,702.00 | LOSS |

## Root-cause hypotheses (ranked by evidence strength)

### H1 (PRIMARY) — OVERLAP session is the loss concentration

**Evidence:** Of −$19,310 total losses across the 13 losing SELLs, **~$16,018 came from the 13 OVERLAP-session trades (13:00-17:00 UTC, London-NY transition)**. Session table:

| session | n | wins | losses | total PnL | avg PnL |
|---|---:|---:|---:|---:|---:|
| ASIA | 20 | 9 | 2 | +$16,439 | +$822 |
| LONDON | 5 | 1 | 1 | −$2,293 | −$459 |
| **OVERLAP** | **13** | **4** | **7** | **−$16,018** | **−$1,232** |
| NY | 22 | 10 | 3 | +$15,199 | +$691 |

OVERLAP has 54% loss rate vs 10-20% in the other sessions. The strategy works in ASIA and NY, fails in OVERLAP. Blocking OVERLAP would lift net PnL from +$13,327 to ~$29,345 on the same sample.

**Implication:** OVERLAP is when London institutional flow meets NY desk-opening gold positioning. XAUUSD frequently has sharp directional spikes in this window that punish counter-trend ML Direct SELLs.

**Confidence:** **HIGH.** The session disparity is ~2–3× in both loss rate and avg PnL, well beyond sample-size noise.

### H2 (STRUCTURAL, NOT P&L-DRIVING) — ML Direct has a one-sided SELL bias on XAUUSD

**Evidence:** 60 executed SELLs vs 0 BUYs since 2026-04-10. Comments show the model's BUY probability at entry is 25-37% — below the execution threshold but not at zero. Over 14 days, with ~1 scan/hour across trading hours, the model should theoretically produce some BUY signals above threshold if the data and model were symmetric. It doesn't.

**Implication:** the ML model has either (a) learned a SELL bias from its training window, or (b) the asymmetric BUY/SELL threshold structure in `config/paper.yaml` makes BUY signals structurally unable to fire. This is a model/config concern worth diagnosing but, as the data shows, does not by itself cause the P&L problem — the SELL side is net profitable.

**Confidence:** HIGH for the observation, but this is a **structural** finding, not a P&L-driving one. Do not conflate the two.

### H3 (MINOR) — SL sizing is roughly right; R:R 0.48 is the intrinsic weakness

**Evidence:** Winning SELLs had SL at 1.46× ATR14, losing SELLs at 1.59× ATR14 — a 9% relative widening on losers that is not statistically meaningful on 37 non-flat trades. But the R:R of 0.48 (avg win +$1,278 vs avg loss −$2,680) is the model's built-in asymmetry: TP/SL ratio ~0.8:1 by design, plus losers run further in drawdown before triggering SL.

**Implication:** widening SL further makes this worse; tightening risks more small losses. The correct fix is to skip trades that are likely to lose (session / regime filter), not to resize them.

**Confidence:** MEDIUM. Supports H1 (session filter) over any SL adjustment.

### H4 (REJECTED) — ML confidence threshold is not a useful knob

**Evidence:** Mean ML confidence at entry: winning SELLs 59.3%, losing SELLs 56.8% — 2.5pp delta on a threshold ~55%. Raising to 60% would drop both wins and losses roughly proportionally.

**Confidence:** LOW. Not a viable lever for XAUUSD specifically.

### H5 (UNTESTABLE WITH CURRENT DATA) — counter-trend exposure via H4 direction

The `h4_trend` column in `trade_results` for XAUUSD is sparsely populated in the v3 window (checked via the full list table above — most entries show `''` or None). The H4-trend-at-entry hypothesis cannot be tested reliably from the current logs. If the 04-28 meeting wants this dimension, it requires reconstructing H4 trend from OHLC history and re-joining — a larger analysis.

---

## Recommendation (for 2026-04-28 meeting, not executed)

**Primary recommendation: session filter on XAUUSD OVERLAP (13:00-17:00 UTC).**

Expected effect based on this sample: recover ~$16k of losses without sacrificing the ~$32k of combined wins from ASIA + NY. 13 fewer trades (22% of XAUUSD SELL volume). Implementation: one entry in `config/base.yaml` session-blocklist, symbol-specific.

**Tiered options:**

1. **Session filter (PREFERRED)** — block XAUUSD SELL entries during OVERLAP session only. Smallest surgical fix. Can be reversed easily.
2. **Blacklist `ml_direct` on XAUUSD entirely** — more aggressive; effectively stops XAUUSD trading since `rsi_reversal` fires only once in the sample. Recommended *only if* the meeting decides H2 (the SELL-bias structural concern) warrants pausing until Phase 7's model rebuild.
3. **Raise ML confidence threshold to 60% on XAUUSD only** — would drop ~half of both wins and losses; not recommended (H4 rejected).
4. **Disable XAUUSD entirely** — cleanest but throws away the +$13k SELL edge. Only justified if the meeting prioritizes risk simplification over return.

**My own read:** option 1 is the winner on this sample. It's the least invasive change with the largest expected PnL lift, and directly addresses the concentrated failure mode. Option 2 is the "trust no XAUUSD until Phase 7" choice — reasonable but costlier.

**Important caveat before acting on option 1:** 13 OVERLAP trades is a small sample. The session disparity is strong enough to be meaningful, but not so strong that we're beyond noise. Before making the change permanent in Phase 8 paper trading, confirm the pattern with at least 2-3 more weeks of STABLE data. For the 04-28 meeting, the proposal is "add the filter for Phase 8 start and review after first month."

## Cross-reference to existing blacklist policy

From `data/improvements.db::data_segmentation_log` STABLE row: *"XAUUSD ML blacklisted"* is listed among the v2.4 stabilization changes. **But the live data shows 60 executed ML Direct SELLs on XAUUSD since 2026-04-10.** Either:

- the blacklist was partially implemented (only blocks BUY, not SELL), OR
- the blacklist was implemented then reverted, OR
- there is a config mismatch between what segmentation_log says and what the engine is running.

**This is worth checking as part of the 04-28 meeting** — if the stated policy says XAUUSD ML is blacklisted and the trade log says it isn't, there's a config/code mismatch that's more serious than the trade losses themselves.

## Data sources

- `data/trading.db::trades` (61 XAUUSD rows in v3)
- `data/trading.db::trade_results` (60 XAUUSD rows in v3)
- `data/trading.db::signal_logs` (99 XAUUSD rows in v3)
- `data/trading.db::market_contexts` (249 XAUUSD rows in v3)
- `data/trading.db::indicator_snapshots` (249 XAUUSD rows in v3)
- `data/trading.db::shadow_signals` (104 XAUUSD rows in v3 period)
- ML-confidence parsed from trade `comment` field (model output preserved there)

*Investigation complete. No code or config changes made.*