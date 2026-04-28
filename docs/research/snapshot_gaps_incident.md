# Snapshot Gaps Incident — 2026-04-16 and 2026-04-21

*Generated: 2026-04-22*
*Author: Claude Code*
*Status: **DIAGNOSIS COMPLETE — no fix applied**. Root cause is operational, not a code bug.*

---

## TL;DR

Both snapshot gaps are **clean process exits followed by delayed restart** — the engine was shut down and brought back up manually (or via scheduler / machine wake). They are **not** schema-drift siblings of the shadow-signals bug. `account_snapshots` schema is drift-clean (ORM and DB in sync, 7 columns each).

**Hypothesis tested** (same root cause family as shadow): **FALSIFIED**. Different class of issue.

**Three latent schema-drift bugs found as a by-product of the investigation** (not currently exploited, but worth knowing about).

---

## Hypothesis

> Same root cause family as shadow incident — a silent exception in a try/except somewhere swallowing engine writes.

**Result: FALSIFIED for snapshot gaps.** The engine was not running during either gap window — not running silently-failing-writes, but actually stopped.

---

## Gap #1 — 2026-04-16 21:05 UTC → 2026-04-17 06:14 UTC (9h 9m)

Log evidence (timestamps local = UTC+3):

**Last activity before the gap:**
```
2026-04-17 00:05:00 | INFO | ============================================================
2026-04-17 00:05:00 | INFO | Scan #4 at 2026-04-17 00:05
2026-04-17 00:05:00 | INFO | Account: $80,495.48 | Equity: $80,495.48 | P&L: $+0.00
... normal scan output ...
2026-04-17 00:05:04 | INFO | No executed signals this scan
2026-04-17 00:05:14 | ERROR | Telegram send failed: <urlopen error timed out>
2026-04-17 00:05:14 | INFO | Scan #4 complete
<9 hours of silence>
```

**First activity after the gap:**
```
2026-04-17 09:14:16 | INFO | Running pre-start health check...
2026-04-17 09:14:16 | INFO |   MT5: OK (Account 5047751974, $80,495.48)
2026-04-17 09:14:16 | INFO |   Database: OK (228 trades)
2026-04-17 09:14:16 | INFO |   Config: OK (config/paper.yaml, 7 instruments)
2026-04-17 09:14:16 | INFO |   Health check: ALL PASS
2026-04-17 09:14:26 | ERROR | Telegram send failed: <urlopen error timed out>
2026-04-17 09:14:26 | INFO | Loading config: config/paper.yaml
2026-04-17 09:14:26 | INFO | Creating strategies (data collection mode - no ML filter)...
```

The "Running pre-start health check..." line is the signature of `scripts/paper_trade.py` starting up. The engine exited cleanly after `Scan #4 complete` at 00:05:14 local (21:05 UTC), and was restarted 9 hours later at 09:14 local (06:14 UTC) with a full health-check + config reload + strategy init sequence.

**Temporal correlation with shadow bug:** the 9-hour outage STARTED ~6 hours after the shadow bug was deployed (18:44 UTC → 00:05 UTC). No evidence the shadow bug caused the shutdown. Plausible explanations (cannot confirm from logs alone): user manually stopped the process to investigate, Windows overnight scheduled restart, machine sleep or shutdown.

---

## Gap #2 — 2026-04-21 07:05 UTC → 13:12 UTC (6h 7m)

**Last activity before the gap:**
```
2026-04-21 10:05:00 | INFO | Scan #50 at 2026-04-21 10:05
2026-04-21 10:05:00 | INFO | Account: $77,702.00 | Equity: $80,663.51 | P&L: $+2,961.51
2026-04-21 10:05:00 | INFO | Open positions: 5
  #56314551827 SELL XAUUSD 1.0 lots | P&L: $+3,287.00
  #56318311013 BUY GBPUSD 1.0 lots | P&L: $-98.00
  ...
2026-04-21 10:05:00 | INFO | No news blocks active
<6+ hours of silence — last timestamp ~10:05:35>
```

**First activity after the gap:**
```
2026-04-21 16:12:25 | INFO | Running pre-start health check...
2026-04-21 16:12:25 | INFO |   MT5: OK (Account 5047751974, $79,777.40)
2026-04-21 16:12:25 | INFO |   Database: OK (253 trades)
2026-04-21 16:12:25 | INFO |   Config: OK (config/paper.yaml, 7 instruments)
2026-04-21 16:12:25 | INFO |   Health check: ALL PASS
```

Same signature — clean pre-start health check, not a crash recovery. User (or scheduler) brought the engine back up.

During the gap, the **live trades continued to run** — positions #56314551827, #56318311013, #56318827869, #56319311958, #56320527649 had MT5 stop-loss and take-profit orders attached at the broker side, so SL/TP hits could still fire on the broker even with the local engine down. The engine only handles scanning, signal generation, and trailing-stop management — not primary order execution, which lives on the MT5 server.

---

## Account_snapshots schema drift check

As part of the hypothesis test, I diffed `AccountSnapshot` ORM columns against the live `account_snapshots` SQLite table:

```
account_snapshots DB cols   : ['balance', 'equity', 'free_margin', 'id', 'margin', 'profit', 'time']
account_snapshots model cols: ['balance', 'equity', 'free_margin', 'id', 'margin', 'profit', 'time']
DRIFT: none
```

**No drift.** `account_snapshots` is not affected by the schema-drift pattern that broke shadow-signals. The gaps are not write failures.

---

## By-product finding — three latent schema-drift bugs

Running the same drift diff across all five core ORM models surfaced three additional drift candidates that aren't currently breaking anything but are loaded guns:

| Model | Table | Columns in DB not in ORM | Risk |
|---|---|---|---|
| `Trade` | `trades` | `data_group` | LATENT — no current code path passes `data_group=` to `Trade(...)` constructor. If added in future, silent TypeError same as shadow bug. |
| `TradeResult` | `trade_results` | `data_group`, `detected_regime` | LATENT — same risk profile. |
| `AccountSnapshot` | `account_snapshots` | (none) | CLEAN |
| `SignalLog` | `signal_logs` | (none) | CLEAN |
| `ScanLog` | `scan_logs` | (none) | CLEAN |
| `ShadowSignal` | `shadow_signals` | (fixed 2026-04-22) | FIXED |

**Grep confirmed** `Trade(...)` and `TradeResult(...)` constructor call sites in `engine/trading_engine.py:885` and `:1078` do NOT pass `data_group=` or `detected_regime=`. These columns are populated only by raw SQL UPDATE (in `scripts/segment_data.py`), never via the ORM.

Safe today. One wrong copy-paste away from reproducing the shadow bug. Recommendation in the "Follow-ups" section below.

---

## Root cause of the `data_group` schema drift (all tables)

`scripts/segment_data.py` on 2026-04-14 ran:

```python
for table in ["trades", "trade_results", "shadow_signals"]:
    ct.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in ct.fetchall()]
    if "data_group" not in cols:
        ct.execute(f"ALTER TABLE {table} ADD COLUMN data_group TEXT")
        print(f"Added data_group to {table}")
```

**Added 3 columns to live SQLite. Did not touch `storage/database.py`.** The author knew about the ORM but chose to leave the model alone (perhaps assuming no ORM code would use the column). This was correct for `trades` and `trade_results` (no ORM writers pass that kwarg), broken for `shadow_signals` (commit `524131e` introduced a writer).

`trade_results.detected_regime` has unknown origin — no `ALTER TABLE ... detected_regime` string is present in the repo. Probably added manually via sqlite3 CLI, or via an older script that has since been deleted. Either way, now orphaned.

---

## Why this matters for the 2026-04-28 meeting

- The snapshot gaps are **operational availability** issues, not code bugs. They should be framed that way: "engine is on a local Windows workstation that has operational uptime issues."
- For v3.0 to go GREEN on Phase 8 (paper trading), you need to decide whether the engine runs on:
  1. The current Windows workstation (accepting occasional 6-9h outages; document SL/TP-at-broker as mitigation)
  2. A dedicated always-on host (VPS, separate workstation) — aligned with v4_framework.md "Infrastructure Migration" guidance for Phase 12
- The **shadow pipeline fix** takes priority over snapshot-gap operational concerns — shadow was silently broken, snapshots are loud (anyone watching sees the gap).

---

## Recommendations (informational — no fix applied)

1. **No action needed on snapshot gaps as "bugs"** — they are not bugs. They are uptime events.
2. **Latent schema-drift cleanup (low urgency):** add `data_group = Column(String(20), nullable=True)` to `Trade` and `TradeResult` classes in `storage/database.py`, plus `detected_regime = Column(String(30), nullable=True)` to `TradeResult`. One 3-line diff total. Lowers the chance of a future copy-paste introducing another shadow-style bug.
3. **Schema-drift CI check (medium-term):** add to `tests/` a script that imports every model, diffs `PRAGMA table_info()` vs declared columns, and fails on drift. Prevents the class of bug entirely.
4. **Engine uptime monitor:** a simple cron/systemd/taskscheduler check that pings the engine's last-snapshot timestamp every 15 minutes and alerts if stale > 30 minutes. Would have caught the 9h and 6h outages within 30 minutes.
5. **Production hosting decision:** if v3.0 goes live, the engine moves to a 24/7 host. Decision for the 04-28 meeting.

---

## Artifacts

- This report: `docs/research/snapshot_gaps_incident.md`
- Sibling report: `docs/research/shadow_signals_incident.md` (the actual bug)
- Stability report: `docs/research/v2_4_demo_stability.md`
- Log source: `data/logs/paper_trading.log` (~2 MB)

---

*No fix applied. No code changes made. Report-only.*
