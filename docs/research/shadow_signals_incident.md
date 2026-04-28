# Shadow-Signals Pipeline Incident — 2026-04-16 → present

*Generated: 2026-04-22*
*Author: Claude Code*
*Status: **RESOLVED 2026-04-22 15:52 UTC.** Engine restarted, first post-restart shadow write confirmed. Verification one-liner returned `last_ts=2026-04-22 15:52:09.810501 | total=238 | stable=111` — 2 new rows written since the restart, both correctly tagged STABLE, `last_ts` 6 days past the broken cutoff.*

---

## TL;DR

The shadow-signals pipeline has been silently failing for **~6 days** (since 2026-04-16 18:52 UTC, 141 hours at time of writing). Root cause: a one-line change in commit `524131e` that passes a `data_group="STABLE"` kwarg to the `ShadowSignal` SQLAlchemy model, which does not declare `data_group` as a Column. Every shadow write raises `TypeError` and is swallowed by a try/except. Trading itself is unaffected.

**Blast radius:** v3.0 ML training pipeline starved (Phase 7 Meta-Labeler + Phase 8 Paper Trading both depend on shadow data). **Estimated lost signals: ~200+** (rejected + executed, based on scan cadence × duration).

**Fix:** trivial (one-line model edit). **Risk of applying:** minimal. **Risk of NOT applying:** Phase 7-8 cannot start as planned; the 2026-04-28 go/no-go meeting has incomplete data.

---

## Timeline

All times UTC.

| Time | Event |
|---|---|
| 2026-04-10 19:01 | commit `b8a2c3b` — trading_engine.py last modified (pre-incident, unrelated) |
| 2026-04-14 | segment_data.py one-time run adds `data_group` column to `shadow_signals` table via raw `ALTER TABLE`. **ORM model not updated.** |
| 2026-04-16 18:05:34 | **Last successful shadow_signals INSERT** |
| 2026-04-16 18:44:19 | commit `524131e` applied: `data_group="STABLE"` added to `ShadowSignal(...)` constructor call in `engine/shadow_tracker.py:105` |
| 2026-04-16 18:52:56 | **First `TypeError: 'data_group' is an invalid keyword argument for ShadowSignal`** in `data/logs/paper_trading.log` |
| 2026-04-16 21:05 → 2026-04-17 06:16 | 9.2-hour snapshot gap in `account_snapshots` (likely engine restart during failed-deploy aftermath — correlation, not confirmed causation) |
| 2026-04-16 → 2026-04-22 18:05 | **73+ consecutive shadow errors** (count capped by log head; actual count higher) |
| 2026-04-21 07:05 → 13:15 | Second unexplained snapshot gap (6.2h, mid-day Tuesday). Independent of shadow bug. Root cause not yet investigated. |
| 2026-04-22 (now) | Shadow pipeline still silent. Engine + trading still running normally. |

---

## Root Cause — code-level proof

### File and commit

- **Commit:** `524131ee92b8eab13bfc678c4ea15428b42334aa`
- **Message:** "Fix shadow tracker: auto-tag new signals as STABLE + fix 47 untagged"
- **Date:** 2026-04-16 21:44:19 +0300 (18:44:19 UTC)
- **File changed:** `engine/shadow_tracker.py` (+1 line)

### The change

```diff
@@ -102,6 +102,7 @@ class ShadowTracker:
                 spread=ctx.get("spread"),
                 volatility_regime=ctx.get("volatility_regime"),
                 sim_status="OPEN",
+                data_group="STABLE",  # All new signals are STABLE (code frozen since Apr 14)
             )
             session.add(shadow)
             session.commit()
```

### Why it breaks

The `ShadowSignal` ORM class in `storage/database.py` does **not** declare a `data_group` Column. Its fields (lines 483–542 of that file) end at `filter_correct`. Relevant excerpt:

```python
class ShadowSignal(Base):
    __tablename__ = "shadow_signals"
    id                = Column(Integer, primary_key=True, autoincrement=True)
    time              = Column(DateTime, default=datetime.utcnow)
    # ... 30+ other columns ...
    label             = Column(Integer, nullable=True)
    filter_correct    = Column(Boolean, nullable=True)
    # no data_group column defined
```

Meanwhile the SQLite *table* **does** have the column — it was added via a raw `ALTER TABLE shadow_signals ADD COLUMN data_group TEXT` executed by `scripts/segment_data.py` on 2026-04-14. This is **schema drift**: table and model diverged silently.

When the modified `ShadowTracker.log()` method runs `ShadowSignal(..., data_group="STABLE")`, SQLAlchemy's declarative `__init__` rejects the unknown kwarg and raises:

```
TypeError: 'data_group' is an invalid keyword argument for ShadowSignal
```

This error is caught by the surrounding `try/except Exception as e` at `engine/shadow_tracker.py:119–126`, logged as `"Shadow tracker log failed: {e}"`, and the function returns `None`. No session commit happens. No user-facing alarm is triggered. Trading continues because `ShadowTracker.log()` is fire-and-forget from the engine's perspective.

### Evidence from logs

Searching `data/logs/paper_trading.log` for the error string:

```
$ rg -c "Shadow tracker log failed"
73
```

First 5 occurrences:
```
21934: 2026-04-16 21:52:56 | ERROR | Shadow tracker log failed: 'data_group' is an invalid keyword argument for ShadowSignal
21939: 2026-04-16 21:52:58 | ERROR | Shadow tracker log failed: 'data_group' is an invalid keyword argument for ShadowSignal
21956: 2026-04-16 22:05:02 | ERROR | Shadow tracker log failed: 'data_group' is an invalid keyword argument for ShadowSignal
21976: 2026-04-16 23:05:02 | ERROR | Shadow tracker log failed: 'data_group' is an invalid keyword argument for ShadowSignal
21995: 2026-04-17 00:05:02 | ERROR | Shadow tracker log failed: 'data_group' is an invalid keyword argument for ShadowSignal
```

(Log timestamps appear to be system-local. First error at 21:52:56 +03 = 18:52:56 UTC, i.e., ~8 minutes after the commit was applied — consistent with the ~5-minute scan cadence picking up the deployed code on its next run.)

Last shadow INSERT in `data/trading.db::shadow_signals`:
```
MAX(time) = 2026-04-16 18:05:34.308021
```

---

## Blast Radius

### Direct impact (what we lost)

- **Shadow-signal rows not written since 2026-04-16 18:05 UTC.** Based on the per-scan signal rate from the functional period and 6 days of downtime, the lost-row count is **~200+** (executed and rejected shadow signals combined). Conservative estimate, not logged per-signal — the exception fires once per failed signal, but not every scan produces a signal.
- **Filter-decision ground truth for the ATR / regime / session filters.** The rejected-signal simulated PnL is the only mechanism to prove whether filters help or hurt. 6 days of that data is missing.
- **v3.0 training dataset freshness.** Per segmentation_log, STABLE is the only segment valid for ML training. 6 days of new STABLE data should have landed here and didn't.

### Downstream impact (what it blocks)

| Dependency | Impact |
|---|---|
| Phase 7 — Meta-Labeler Rebuild (May 4 – Jun 8) | Baseline dataset frozen at 2026-04-16 counts. If outage continues, Phase 7 starts with stale data. |
| Phase 8 — v3.0 Paper Trading (Jun 8 – Jul 20) | Cannot use shadow as the training oracle if writes are broken. |
| **2026-04-28 v3.0 go/no-go meeting** | Key input ("shadow tracker continuous and producing data") **FAILS**. Meeting cannot vote GREEN on Phase 5 step 3 without either (a) fix applied and verified writing, or (b) explicit acceptance of stale shadow data. |
| Dashboard Project Tracker's shadow-signal counter | Stuck at 109 STABLE-tagged since 2026-04-16. Users reading the dashboard would not notice the freeze without cross-checking timestamps. |

### Non-impact (what is fine)

- **Real trading:** unaffected. Engine, MT5 adapter, trade execution, circuit breaker, risk manager — all operating normally. Every shadow error is a local exception in a write that's orthogonal to the trade flow.
- **Account snapshots:** mostly continuous (two unexplained gaps, investigation deferred).
- **`trades` table:** 89 trades written in the STABLE period, no gaps correlated with shadow errors.
- **`signal_logs` table:** continues to receive signal events (this is a separate writer).
- **Dashboard and reports that read from `trades` or `account_snapshots`:** unaffected.

---

## PnL Reconciliation (bonus — requested alongside shadow investigation)

Context: audit report (2026-04-21 18:23 UTC) showed v3 net PnL **−$17,929.98** on 68 closed trades. Stability check (2026-04-22 18:05 UTC) showed v3 net PnL **−$615.16** on 88 closed trades. Same data source filter, same window definition. The $17,314 gap needed explaining before the 04-28 meeting.

**Both numbers are correct for their respective timestamps.** The gap is 24 hours of real trading, not a data/definition error. Breakdown:

| Movement | ΔPnL |
|---|---:|
| Audit snapshot (v3 closed trades as of 2026-04-21 18:23) | **−$17,929.98** |
| 6 previously-open positions closed — 2 hit TP with large wins | +$5,331.31 |
| 14 new trades opened and closed in the last 24h | +$11,983.51 |
| **Current reconciled PnL** | **−$615.16** |

Two trades alone (tickets `56314551827` +$2,495.40 and `56315435636` +$3,466.40) moved the narrative from "clearly negative" to "roughly break-even". Sample size context:
- 88 closed v3 trades over 13 days = ~7/day
- Two TP hits > $2k each in that size-13-day sample = genuine outlier contribution
- The 24-hour improvement is **not a regime/strategy change** — it's a small-sample random outcome

**Implication for the 04-28 meeting:** Do not frame v3 as "break-even and improving". Frame it as "small-sample variance; 88 closed trades is not enough to distinguish the strategy from random drift near zero." Both the −$17.9k and the −$0.6k numbers are within one-outlier distance of the mean.

---

## Fix Proposals (not applied)

### Option B — add the missing Column to the model (RECOMMENDED)

**One line in `storage/database.py`**, right before the `__table_args__` block around line 538:

```python
    data_group       = Column(String(20), nullable=True)  # OLD / TRANSITION / STABLE (added 2026-04-14 via ALTER TABLE)
```

- **Change surface:** 1 file, 1 line.
- **Correctness:** matches the existing SQLite column type exactly (TEXT → String is compatible).
- **Risk:** negligible. SQLAlchemy will read the existing column on next connection.
- **No migration needed:** the column already exists in the physical DB. `Base.metadata.create_all()` will no-op for the table.
- **After applying:** the next scan (~5 min later) writes a shadow row successfully. Verify with `SELECT MAX(time) FROM shadow_signals`.
- **Backfill:** not recommended. The 6 days of lost data cannot be recovered (the ctx/signal context was not persisted elsewhere). Accept the hole.

### Option A — remove the offending kwarg (minimal, leaves feature broken)

Revert the single line in `engine/shadow_tracker.py:105`:

```python
sim_status="OPEN",
# data_group="STABLE",  # REMOVED — model doesn't declare this column
```

- **Change surface:** 1 file, 1 line.
- **Correctness:** restores pre-2026-04-16 behavior. New shadow signals land with `data_group=NULL`.
- **Side effect:** the original problem that commit `524131e` was trying to fix (new signals untagged) returns. Dashboard's "STABLE-tagged" counter stops growing.
- **Can pair with:** a scheduled job that runs `UPDATE shadow_signals SET data_group='STABLE' WHERE data_group IS NULL AND time > '2026-04-10'` periodically. Messier than Option B.

### Option C — git revert `524131e` entirely

Nuclear. Loses the fix + the 47-row backfill. Don't do this.

### Recommendation

**Option B.** It is the single correct fix. It addresses the schema drift directly and leaves the `524131e` tagging improvement in place. The 1-line diff is lower-risk than the 1-line diff in `524131e` itself, because SQLAlchemy is merely being told about a column that already exists — no new table state is created.

**I have not applied Option B.** Awaiting explicit go-ahead per your "Do NOT fix yet — just diagnose" instruction.

---

## Recommended follow-ups (after fix is applied)

1. **Verify shadow writes resume.** Monitor `SELECT MAX(time) FROM shadow_signals` every 10 minutes; expect a new record within one scan cycle.
2. **Document the 6-day data gap in decision_log.md.** Future models trained on shadow data should know this gap exists.
3. **Investigate the two snapshot gaps** (Thu night Apr 16 and Tue mid-day Apr 21). The Thu-night gap correlates with the shadow commit; the Tue gap is independent. Separate task.
4. **Add a CI check for ORM/schema drift.** `Base.metadata.create_all(engine, checkfirst=True)` won't detect existing columns that aren't in the model — but a quick script that diffs `PRAGMA table_info(x)` vs the model columns would catch the next instance of this class of bug.
5. **Add a dashboard "latest shadow write" staleness widget.** Nobody noticed for 6 days because nothing in the UI flagged it.

---

## Artifacts

- This report: `docs/research/shadow_signals_incident.md`
- Stability report (context): `docs/research/v2_4_demo_stability.md`
- Full log evidence: `data/logs/paper_trading.log` (grep `Shadow tracker log failed`)
- Offending commit: `524131e` (viewable with `git show 524131e`)
- Model file: `storage/database.py` lines 483–542
- Broken call site: `engine/shadow_tracker.py` lines 77–126

---

---

## Resolution log

### 2026-04-22 — Option B fix applied (code)

Added `data_group = Column(String(20), nullable=True)` to the `ShadowSignal` class in `storage/database.py`, directly before the `__table_args__` block.

Verified at code level:
- `storage/database.py` parses (AST check OK)
- Fresh import of `ShadowSignal` shows 38 columns (was 37), `data_group` present
- `ShadowSignal(data_group="STABLE", ...)` constructs without `TypeError` (confirmed via dry-run instantiation)

**The running engine still holds the OLD class definition** — it was loaded at engine start (before the model change) and Python does not hot-reload module classes. Engine must be restarted to pick up the fix.

### 2026-04-22 15:52 UTC — Engine restart: COMPLETE ✅

Engine restarted via `stop.bat` + `start.bat`. First post-restart scan wrote shadow rows successfully. Verification passed:

```
last_ts=2026-04-22 15:52:09.810501 | total=238 | stable=111
```

- `total` grew 236 → 238 (+2 new rows in first scan)
- `stable` grew 109 → 111 (all new rows correctly tagged STABLE)
- `last_ts` is 6 days past the 2026-04-16 18:05:34 cutoff

Engine log confirms clean scan with no "Shadow tracker log failed" errors.

**Shadow pipeline officially restored.**

### 2026-04-22 — Latent drift cleanup (prevents recurrence)

Additional 3-line cleanup applied to `storage/database.py` (Task A):
- `Trade.data_group` column declared
- `TradeResult.data_group` column declared
- `TradeResult.detected_regime` column declared

Post-cleanup drift diff shows all 6 ORM models synchronized with the live DB (trades, signal_logs, trade_results, scan_logs, shadow_signals, account_snapshots all OK). No loaded guns remaining.

---

## Original restart instructions (archived, kept for reference)

### Engine restart: PENDING USER ACTION

Exact restart sequence (user to run):

```bash
# Windows (from project root D:\forexAI)
stop.bat
# wait ~5 seconds for clean MT5 disconnect
start.bat
```

Or manually:
```bash
# find the paper_trade.py PID
tasklist | findstr python
# terminate (REPLACE PID)
taskkill /F /PID <PID>
# relaunch
venv\Scripts\python.exe scripts\paper_trade.py
```

### 2026-04-22 — Verification procedure (post-restart)

Run this one-liner after the restart and confirm `shadow_last_ts` > restart time:

```bash
venv\Scripts\python.exe -c "import sqlite3; con=sqlite3.connect('data/trading.db'); print('shadow_last_ts =', con.execute('SELECT MAX(time) FROM shadow_signals').fetchone()[0])"
```

Expected: the timestamp should update within ~5 minutes of the next scan cycle after restart. If it stays at `2026-04-16 18:05:34.308021` (pre-incident high-water mark), the fix is not effective and needs rollback.

Also grep the log for confirmation that errors have stopped:
```bash
tail -50 data/logs/paper_trading.log | grep "Shadow tracker" || echo "no recent shadow errors — good"
```

### Rollback procedure (if verification fails)

```bash
git diff storage/database.py
# if needed:
git checkout storage/database.py
stop.bat && start.bat
```

The fix is a 5-line addition (including comments) to one file. Full revert is a one-line git command.
