═══════════════════════════════════════════════════════════════════════════════
TASK: Execute meeting outcomes from 2026-04-28 v3 go/no-go meeting
═══════════════════════════════════════════════════════════════════════════════

CONTEXT:
The 2026-04-28 meeting concluded with 8 votes. The decisions are documented
in improvements.db, decision_log.md, and external_review_2026_04_28.md, but
the CODE has not yet been changed. The engine is currently running with
configurations the meeting explicitly rejected. This prompt executes the
immediate-action items required to bring the running system into alignment
with the meeting's decisions.

Scope of THIS prompt:
- AI-002a: retire bollinger_bounce
- AI-002b: retire ml_filtered_sma
- AI-002c: install strategy_blacklist in paper.yaml (Vote 6 Option D)
- Engine restart + verification
- Post-restart monitoring window

OUT OF SCOPE for this prompt (separate work later):
- AI-001 (zero-BUY fix) — 4-5 weeks of structural work
- AI-003 (Alembic migrations) — separate prompt tomorrow
- AI-004 (config snapshot logger) — separate prompt tomorrow
- AI-005 (30% holdout) — separate prompt next week
- AI-006/007 (OVERLAP shadow) — starts May 4
- AI-018 (watchdog) — separate prompt tomorrow

═══════════════════════════════════════════════════════════════════════════════
EXECUTE in this order. Pause at each CHECKPOINT. Do not skip verification.
═══════════════════════════════════════════════════════════════════════════════

────────────────────────────────────────────────────────────────────────────────
PHASE 0 — Pre-flight safety
────────────────────────────────────────────────────────────────────────────────

### 0.1 Backup current state
- Copy data/trading.db → data/trading.db.bak.pre-ai002.YYYYMMDD-HHMMSS
- Copy config/paper.yaml → config/paper.yaml.bak.pre-ai002.YYYYMMDD-HHMMSS
- Copy config/base.yaml → config/base.yaml.bak.pre-ai002.YYYYMMDD-HHMMSS
- Verify backups exist + nonzero size

### 0.2 Snapshot pre-change state
Run and save to /tmp/ai002_pre_state.txt:
  - List of currently registered strategies (grep strategy registration in
    scripts/run_engine.py or equivalent entry point)
  - Current paper.yaml content (full)
  - Current base.yaml content (full)
  - Last 5 trades from trade_results table with strategy column
  - Engine PID if running (Get-Process python | Where CommandLine matches engine)

### 0.3 Detect engine running state
- Is the engine currently running? Find the python process running run_engine.py
  or trading_engine.py
- Note: do NOT kill the engine yet. Note PID for later graceful shutdown.

Report all findings, then proceed.

────────────────────────────────────────────────────────────────────────────────
CHECKPOINT 0 — pause; share pre-flight report; await my "continue"
────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────
PHASE 1 — AI-002a: Retire bollinger_bounce
────────────────────────────────────────────────────────────────────────────────

### 1.1 Find the strategy registration point
Search for where bollinger_bounce is registered into the engine:
  grep -rn "bollinger_bounce\|BollingerBounce" scripts/ engine/ strategies/

Identify the exact file + line where the strategy is added to the active
rotation. Common patterns:
  - strategies = [..., BollingerBounce(...), ...]
  - register_strategy(BollingerBounce)
  - active_strategies.yaml entries
  - factory dict {"bollinger_bounce": BollingerBounce}

### 1.2 Disable, don't delete
DO NOT delete strategies/bollinger_bounce.py — historical reference matters.

Two acceptable disable methods, pick whichever matches existing convention:

Method A (preferred if there's a registration list):
  Comment out the registration line with comment:
  # RETIRED 2026-04-28 per Vote 4 (high-WR/low-R:R pathology, n=25, PF=0.26)
  # See: docs/research/decision_log.md 2026-04-28 entry
  # Re-enabling requires: fresh n≥25 OOS sample + R:R ≥ 1.0 design

Method B (if registration is automatic via class discovery):
  Add a class-level attribute:
    DISABLED = True
    DISABLED_REASON = "Retired 2026-04-28 — see decision_log.md"
  AND modify the discovery logic to skip DISABLED strategies.

If Method B, also add a unit test: test_disabled_strategies_not_loaded

### 1.3 Verify
Run a dry-import:
  python -c "from scripts.run_engine import get_active_strategies; \
             names = [s.name for s in get_active_strategies()]; \
             print('Active:', names); \
             assert 'bollinger_bounce' not in names, 'STILL ACTIVE'"

Should print active strategies list WITHOUT bollinger_bounce. If it appears,
STOP and report.

────────────────────────────────────────────────────────────────────────────────
PHASE 2 — AI-002b: Retire ml_filtered_sma
────────────────────────────────────────────────────────────────────────────────

Repeat Phase 1 logic for ml_filtered_sma (file: strategies/ml_filtered_strategy.py
based on directory listing — verify the actual class/registration name).

Comment text:
  # RETIRED 2026-04-28 per Vote 5 (high-WR/low-R:R pathology, n=22, PF=0.23,
  # R:R=0.11, same pattern as bollinger_bounce — see AI-017 audit pending)
  # See: docs/research/decision_log.md 2026-04-28 entry
  # Re-enabling requires: fresh n≥22 OOS sample + R:R ≥ 1.0 design

Verify same way.

────────────────────────────────────────────────────────────────────────────────
PHASE 3 — AI-002c: Install strategy_blacklist in paper.yaml (Vote 6 Option D)
────────────────────────────────────────────────────────────────────────────────

### 3.1 Add strategy_blacklist section to paper.yaml

Append the following block to config/paper.yaml. Place it AFTER the existing
`risk:` section and BEFORE `session_filter:` to match base.yaml's ordering:

# ============================================================
# Strategy Blacklist (Installed 2026-04-28 per Meeting Vote 6, Option D)
# ============================================================
# Decision: block ml_direct on XAUUSD in BOTH configs until zero-BUY is
# resolved (AI-001). The +$21k v3 ml_direct/XAUUSD profit was made during
# a confirmed gold downtrend; the strategy has zero BUY capability across
# 105 trades in 3 versions. Continuing to run it into a projected reversal
# regime (Q3 2026 institutional consensus: bullish $5k-$6k) would convert
# accumulated profit into mirror-image loss with no defensive capability.
#
# Lift conditions (ALL required):
#   1. AI-001 (zero-BUY fix) shipped + validated on holdout
#   2. June 1 Phase 8 gate review GREEN
#   3. RFC documenting forward-looking justification (not P&L-justified)
#
# Per Vote 6 Option D: this entry mirrors base.yaml::strategy_blacklist.
# ============================================================
strategy_blacklist:
  - strategy: "ml_direct"
    symbol: "XAUUSD"
    reason: "Zero-BUY structural defect; meeting vote 6D 2026-04-28; lift requires AI-001 + June 1 gate"

  - strategy: "ml_filtered_sma"
    symbol: "XAUUSD"
    reason: "Mirrored from base.yaml; strategy retired entirely 2026-04-28 (vote 5)"

### 3.2 Verify YAML parses
  python -c "import yaml; \
             c = yaml.safe_load(open('config/paper.yaml', encoding='utf-8')); \
             bl = c.get('strategy_blacklist', []); \
             print('blacklist entries:', len(bl)); \
             assert any(b['strategy']=='ml_direct' and b['symbol']=='XAUUSD' for b in bl), \
                'ml_direct/XAUUSD missing from blacklist'; \
             print('OK')"

### 3.3 Update base.yaml comment

The existing base.yaml::strategy_blacklist comment says:
  "Lost $30K+ shorting gold in uptrend"

This is stale (v2 reality, not v3). Update to:
  # Strategy blacklist — kept identical to paper.yaml after 2026-04-28 meeting (Vote 6 D).
  # Both configs MUST stay synchronized until config-parity CI guard (AI-004) lands.
  # Original v2 rationale ("Lost $30K+ shorting gold in uptrend"): superseded by
  # forward-looking rationale in paper.yaml.

Replace the old comment in base.yaml. Do NOT change the entries themselves.

### 3.4 Verify config parity
  python -c "import yaml; \
             p = yaml.safe_load(open('config/paper.yaml', encoding='utf-8')); \
             b = yaml.safe_load(open('config/base.yaml', encoding='utf-8')); \
             pbl = sorted([(x['strategy'], x['symbol']) for x in p.get('strategy_blacklist', [])]); \
             bbl = sorted([(x['strategy'], x['symbol']) for x in b.get('strategy_blacklist', [])]); \
             print('paper:', pbl); \
             print('base: ', bbl); \
             assert pbl == bbl, 'CONFIG DRIFT — blacklists do not match'; \
             print('PARITY OK')"

If parity fails, STOP and report which entries differ.

────────────────────────────────────────────────────────────────────────────────
CHECKPOINT 1 — pause; report all 3 changes; await my "continue"
────────────────────────────────────────────────────────────────────────────────

Show:
- Diff of paper.yaml (added blacklist block)
- Diff of base.yaml (updated comment)
- File(s) modified to disable the two strategies
- Output of dry-import verification (active strategies list)
- Output of config parity check

Wait for "continue" before any engine restart.

────────────────────────────────────────────────────────────────────────────────
PHASE 4 — Engine restart with verification
────────────────────────────────────────────────────────────────────────────────

### 4.1 Graceful shutdown
If engine is currently running:
- Send SIGTERM to the noted PID
- Wait up to 30 seconds for graceful exit
- If still running, report and ask before SIGKILL

### 4.2 Pre-start sanity check
Confirm:
- TRADING_MODE env var (should be "paper" for paper.yaml load)
- Database connection reachable
- MT5 connection alive (run a quick ping if there's a healthcheck script)

### 4.3 Start engine
- Use whatever startup command exists (start.bat or python scripts/run_engine.py)
- Capture first 60 seconds of log output

### 4.4 Verify post-start state
Wait 60 seconds, then check engine logs for:

  ✓ Config loaded from: config/paper.yaml
  ✓ Active strategies list (must NOT contain bollinger_bounce or ml_filtered_sma)
  ✓ Strategy blacklist loaded: 2 entries
  ✓ No "ImportError" or "AttributeError" or "TypeError" in startup
  ✓ At least one heartbeat / market scan logged

If any check fails, STOP. Show last 50 log lines + ask before further action.

### 4.5 Targeted XAUUSD ml_direct test
The next time the engine attempts an ml_direct signal on XAUUSD, the log
should show:
  REJECTED [BLACKLISTED]: ml_direct/XAUUSD blocked per strategy_blacklist

This won't fire immediately; it triggers only when ml_direct generates an
XAUUSD signal. Set a 20-minute watch on the log for either:
  (a) The expected REJECTED line, OR
  (b) A 20-minute heartbeat with no signal attempts (which is also valid —
      ml_direct may not signal during off-hours)

Report which outcome occurred.

────────────────────────────────────────────────────────────────────────────────
PHASE 5 — Persist execution to action_items
────────────────────────────────────────────────────────────────────────────────

Update improvements.db::action_items:

  UPDATE action_items
  SET status = 'DONE',
      completed_date = datetime('now'),
      notes = 'Executed 2026-04-28. Engine restarted at HH:MM:SS.
              Config parity verified. bollinger_bounce + ml_filtered_sma
              removed from rotation. ml_direct/XAUUSD blacklist active in
              both configs. See decision_log.md 2026-04-28.'
  WHERE action_id IN ('AI-002', 'AI-002a', 'AI-002b', 'AI-002c');

If AI-002 is stored as one row instead of three subrows, update the single
row with combined notes. If three subrows exist, update each.

Verify:
  SELECT action_id, status, completed_date FROM action_items
  WHERE action_id LIKE 'AI-002%';

────────────────────────────────────────────────────────────────────────────────
PHASE 6 — Append execution note to decision_log.md
────────────────────────────────────────────────────────────────────────────────

Append to docs/research/decision_log.md:

## 2026-04-28 (post-meeting execution) — AI-002 deployed

**Executed:** AI-002a, AI-002b, AI-002c per meeting votes 4, 5, 6.

**Changes:**
- bollinger_bounce: disabled in [registration file], comment annotated
- ml_filtered_sma: disabled in [registration file], comment annotated
- paper.yaml: strategy_blacklist installed (ml_direct + ml_filtered_sma on XAUUSD)
- base.yaml: blacklist comment updated to reference 2026-04-28 vote

**Verification:**
- YAML parse: OK
- Config parity (paper.yaml ↔ base.yaml): OK
- Engine restart: clean (no errors in first 60s)
- Active strategies post-restart: [list]
- Blacklist enforcement: [observed at HH:MM:SS / not yet triggered in 20-min window]

**Pre-execution backups:**
- data/trading.db.bak.pre-ai002.<timestamp>
- config/paper.yaml.bak.pre-ai002.<timestamp>
- config/base.yaml.bak.pre-ai002.<timestamp>

**Phase 8 blocker progress:** 1 of 5 cleared (AI-002).
**Remaining blockers:** AI-001, AI-003, AI-005, AI-006+007.

────────────────────────────────────────────────────────────────────────────────
PHASE 7 — Final completion report
────────────────────────────────────────────────────────────────────────────────

Print to terminal:

  ════════════════════════════════════════════════════════════════
  AI-002 EXECUTION — COMPLETE
  ════════════════════════════════════════════════════════════════
  Strategies retired:
    ✓ bollinger_bounce  (file: <path>, method: <comment-out|DISABLED-flag>)
    ✓ ml_filtered_sma   (file: <path>, method: <comment-out|DISABLED-flag>)
  Blacklist installed:
    ✓ paper.yaml  — 2 entries (ml_direct/XAUUSD, ml_filtered_sma/XAUUSD)
    ✓ base.yaml   — same 2 entries (parity verified)
  Engine state:
    ✓ Restarted at <HH:MM:SS>
    ✓ Active strategies: <list, count N> — neither retired strategy present
    ✓ Blacklist enforcement: <observed / awaiting first trigger>
  Backups:
    ✓ data/trading.db.bak.pre-ai002.<ts>
    ✓ config/paper.yaml.bak.pre-ai002.<ts>
    ✓ config/base.yaml.bak.pre-ai002.<ts>
  Database updates:
    ✓ action_items: AI-002* marked DONE
    ✓ decision_log.md: execution note appended
  Phase 8 gate progress:
    1 of 5 blockers cleared (AI-002)
    Remaining: AI-001, AI-003, AI-005, AI-006/007
    Next gate review: 2026-06-01 (34 days)
  Git state:
    Modified: <list of files>
    Status:   staged, NOT committed (per project convention)
  ════════════════════════════════════════════════════════════════
  Next strategic action options:
    A. AI-003 (Alembic + CI schema guard) — tomorrow, ~3 hours
    B. AI-018 (watchdog + boot config)    — tomorrow, ~1 hour
    C. AI-001 (zero-BUY fix) discovery    — next 4-5 weeks of work
  ════════════════════════════════════════════════════════════════

────────────────────────────────────────────────────────────────────────────────
RULES OF EXECUTION
────────────────────────────────────────────────────────────────────────────────

1. Two checkpoints (0 and 1). Pause at each. Show evidence. Wait for "continue".

2. NEVER delete files. Disable via comment or DISABLED flag only.

3. NEVER skip backup phase 0.1. If backups fail, halt entirely.

4. Engine restart in Phase 4 ONLY happens after Checkpoint 1 approval.

5. If config parity check fails, do not restart engine. Report the diff.

6. If post-restart logs show ANY error in first 60s, do not proceed to
   Phase 5. Report logs. Restoration path: stop engine, restore from
   *.bak.pre-ai002.* files, restart, report for manual debugging.

7. Stage all modified files in git (git add) but do NOT git commit.

8. If you find that bollinger_bounce or ml_filtered_sma is referenced
   somewhere unexpected (e.g., a unit test, a documentation example,
   the meta-labeler training set spec), list those references in the
   completion report under "Notes for follow-up" — do NOT modify them.

9. If TRADING_MODE is currently set to anything other than "paper",
   STOP and ask before proceeding. This prompt is calibrated for
   paper-mode execution only.

10. The bottom-line goal: by the time this prompt finishes, the live
    engine must reflect the meeting's decisions. No retired strategy
    in rotation. No ml_direct/XAUUSD trades. Both configs in parity.