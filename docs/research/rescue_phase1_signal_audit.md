# Rescue Plan — Phase 1: Rejected-Signal Evidence Audit

**Data window:** trading.db (2026-03-17 → 2026-03-27, pre-freeze)
**Method:** forward h1_close path, horizon=24 bars, signal's own SL/TP as barriers (close-cross proxy).

> Win% = of signals with a decided outcome (WIN+LOSS), how many hit TP first.

| Bucket | Signals | Decided | WIN | LOSS | Timeout | NoData | **Win% (decided)** |
|---|---:|---:|---:|---:|---:|---:|---:|
| EXECUTED | 132 | 112 | 47 | 65 | 20 | 0 | **42%** |
| H4_TREND | 79 | 46 | 11 | 35 | 33 | 0 | **24%** |
| SESSION | 27 | 9 | 1 | 8 | 17 | 1 | **11%** |
| DEDUP_SAME | 27 | 20 | 0 | 20 | 7 | 0 | **0%** |
| DEDUP_CONFLICT | 13 | 11 | 8 | 3 | 2 | 0 | **73%** |
| MAX_POS_DD | 32 | 14 | 3 | 11 | 18 | 0 | **21%** |
| NEWS | 19 | 17 | 4 | 13 | 2 | 0 | **24%** |
| EXEC_ERROR | 55 | 36 | 21 | 15 | 19 | 0 | **58%** |
| OTHER | 3 | 2 | 0 | 2 | 1 | 0 | **0%** |

## Reading this table

- **EXECUTED** is the baseline: the win-rate of trades we actually took (by this close-proxy measure). Compare every filtered bucket against it.
- A filtered bucket with **Win% >= EXECUTED** means that filter is **blocking trades as good as the ones we keep** → candidate to LOOSEN.
- A filtered bucket with **Win% well below EXECUTED** means the filter is **protecting us** → KEEP.
- **EXEC_ERROR** are NOT strategy decisions — they are broker/config failures (filling mode, AutoTrading off, No money). Any win% here is lost P&L from bugs, not risk policy → FIX regardless of win%.

## Verdict per bucket (baseline EXECUTED = 42%)

| Bucket | Win% | Verdict | Action |
|---|---:|---|---|
| **EXEC_ERROR** | 58% | NOT a filter — bugs killing our best signals | 🔴 **FIX FIRST** (55 lost signals) |
| **DEDUP_CONFLICT** | 73% | Blocked signal usually the RIGHT direction; open position was wrong | 🟡 **REDESIGN** (close/reverse instead of block) |
| H4_TREND | 24% | Protecting us — blocks mostly losers | ✅ KEEP |
| SESSION | 11% | Strongly protecting | ✅ KEEP |
| NEWS | 24% | Protecting | ✅ KEEP |
| MAX_POS_DD | 21% | Protecting during drawdown | ✅ KEEP |
| DEDUP_SAME | 0% | Second signal on open position always lost | ✅ KEEP |

## Headline conclusion

**The path to more trades is NOT loosening quality filters — they are working
(all block mostly losers).** The evidence-based levers are:

1. **Fix the execution bugs (EXEC_ERROR, 55 signals, 58% win).** Pure lost
   profit from `Unsupported filling mode` (24), `AutoTrading disabled` (21),
   `No money` (10). Fixing this recovers ~55 signals over a 10-day window
   with zero quality loss.
2. **Redesign conflict handling (DEDUP_CONFLICT, 73% win).** When a new signal
   opposes an open position, the new one was usually right — consider
   reverse-on-conflict logic instead of a hard block.
3. **Raise setup frequency upstream** via the ML re-label/retrain fix and
   M15 / wider symbol coverage (Phase 2-3) — NOT by weakening filters.

## Caveats

- Window is **pre-freeze March data**; the live freeze-window DB (May–Jun)
  is not in this checkout. Re-run this script on the synced live DB to confirm.
- Close-cross proxy understates barrier touches uniformly across buckets;
  relative comparison is valid, absolute win% is conservative.

## EXEC_ERROR root-cause diagnosis (corrects the headline)

Drilling into the 55 EXEC_ERROR signals against the fix timeline shows they
are **mostly already-solved historical artifacts, NOT ongoing lost profit:**

| Sub-error | Count | Before IMP-50 fix (3-25) | After fix | Status |
|---|---:|---:|---:|---|
| Unsupported filling mode | 24 | 21 | 3 | ✅ **FIXED** by IMP-50 (FOK→IOC→RETURN fallback). 3 minor leaks remain. |
| AutoTrading disabled | 21 | 21 | 0 | ⚠️ **Operational** — terminal "Algo Trading" toggle was OFF. Not code. IMP-53 alert added; keep button ON. |
| No money (margin) | 10 | 10 | 0 | 🔴 **No code fix exists.** No pre-trade margin check. Low frequency but unguarded. |

**Revised verdict:** EXEC_ERROR is largely behind us. Filling mode is fixed,
AutoTrading is an operational discipline (keep the terminal toggle on), and
only the **margin pre-check (No money)** is a genuine open code item — and
it is low-frequency. The big "55 lost signals" number is dominated by the
pre-3-25 period before IMP-50 shipped.

## Final revised priority (post-diagnosis)

1. 🔴 **ML root-cause fix** (re-label with ordered triple-barrier matching real
   exits + refresh data + retrain + calibrate). This is now the #1 lever — it
   makes `ml_direct` trustworthy AND lets us safely lower the confidence
   threshold to fire more trades. Addresses both quality and frequency.
2. 🟡 **DEDUP_CONFLICT redesign** (73% win, 13 signals) — reverse-on-conflict
   instead of hard block. Still valid and high-win.
3. 🟢 **Frequency expansion** — add M15 signal generation + wider symbol
   coverage on confirmed strategies (backtest each before live).
4. 🟢 **Margin pre-check** — add a free-margin guard before `place_order`
   (closes the only open EXEC_ERROR item; low urgency).
5. ✅ **Keep all quality filters** (H4_TREND, SESSION, NEWS, MAX_POS_DD,
   DEDUP_SAME) — evidence shows they block losers.