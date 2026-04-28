═══════════════════════════════════════════════════════════════════════════════
TASK: Post-meeting persistence + dashboard update with timeline visibility
═══════════════════════════════════════════════════════════════════════════════

CONTEXT:
The 2026-04-28 v3 go/no-go meeting concluded with 8 votes (7 aligned with
external reviewer, 1 deviation on Vote 8 with mitigation). Action items
AI-014, AI-015, AI-016 must now run, PLUS the dashboard needs to surface
meeting outcomes, current state, and upcoming dates.

═══════════════════════════════════════════════════════════════════════════════
EXECUTE in this order. Pause only at marked checkpoints.
═══════════════════════════════════════════════════════════════════════════════

────────────────────────────────────────────────────────────────────────────────
PHASE 1 — Database persistence (AI-015, AI-016)
────────────────────────────────────────────────────────────────────────────────

### 1.1 Insert 8 rows into improvements.db::go_no_go_decisions

For each vote, insert one row with these fields:
- decision_date: 2026-04-28
- phase_number: per-vote (see table below)
- verdict: per-vote (GREEN / YELLOW / RED)
- gates_passed / gates_total: per-vote
- rationale_en: 2-3 sentences in English
- rationale_ar: same content in Arabic (this is a bilingual project)
- next_action: concrete action item ID (e.g. "AI-001 owner: engineering, due 2026-06-01")
- decided_by: "meeting_2026_04_28"
- created_at: datetime('now')

Vote-by-vote field values:

| Vote | phase | verdict | gates_passed | gates_total | next_action |
|------|-------|---------|--------------|-------------|-------------|
| 1    | 5     | GREEN   | 6            | 8           | AI-014, transition_date 2026-05-04 |
| 2    | 8     | YELLOW  | 0            | 5           | June 1 gate review; 5 blockers OPEN |
| 3    | 5     | YELLOW  | NULL         | NULL        | AI-006 + AI-007 shadow-mode May 4 - May 25 |
| 4    | 5     | GREEN   | NULL         | NULL        | AI-002a retire bollinger_bounce before May 4 |
| 5    | 5     | GREEN   | NULL         | NULL        | AI-002b retire ml_filtered_sma before May 4 |
| 6    | 5     | GREEN   | NULL         | NULL        | AI-002c block ml_direct/XAUUSD in both configs |
| 7    | 8     | RED     | 0            | 1           | AI-001 BLOCKING; June 1 gate cannot GREEN without it |
| 8    | 9     | YELLOW  | NULL         | NULL        | AI-018 watchdog implementation; AI-019 July re-eval |

Use rationale text that captures the consistency principle: methodological
discipline applied to v3 same as v4, capability gates not calendar gates,
validation before installation.

### 1.2 Update improvements.db::phase_steps

For Phase 5: mark step "v3.0 Pre-Build" as completed_at = 2026-04-28
For Phase 6: insert step "TSMOM Layer build" with started_at = 2026-05-04
For Phase 7: insert step "Meta-Labeler Rebuild" with started_at = 2026-05-04
For Phase 8: ensure status reflects DEFERRED with gate_date = 2026-06-01

### 1.3 Verify all writes

Run:
  SELECT COUNT(*) FROM go_no_go_decisions WHERE decided_by='meeting_2026_04_28';
  -- expected: 8

  SELECT phase_number, verdict, COUNT(*) FROM go_no_go_decisions
  WHERE decided_by='meeting_2026_04_28' GROUP BY phase_number, verdict;

  SELECT * FROM phase_steps WHERE started_at >= '2026-04-28' OR completed_at >= '2026-04-28';

Report counts and a 1-line summary.

────────────────────────────────────────────────────────────────────────────────
PHASE 2 — Decision log entry (AI-014)
────────────────────────────────────────────────────────────────────────────────

Append to docs/research/decision_log.md a single block:

## 2026-04-28 — v3 Go/No-Go Meeting — 8 votes decided (post-external-review)

**Context:** Meeting held after external skeptical review (synthesis at
docs/research/external_review_2026_04_28.md). Reviewer's framing accepted:
project state is "structurally one-sided system funded by an incidental
window of bias × falling gold" — methodological discipline applied to v4
now extended to v3.

**Vote outcomes (7 of 8 align with reviewer's recommended position):**

[Reproduce the 8-vote table from meeting summary verbatim]

**Emergent findings the meeting added:**
- AI-017: high-WR / low-R:R pathology pattern across two retired strategies
  suggests possible system-wide TP/SL design issue. Audit remaining
  strategies before Phase 7.
- AI-018: snapshot-gap operational issue addressable via watchdog +
  Task Scheduler boot config rather than VPS migration. AI-019 re-evals
  hosting in July.

**Phase status post-meeting:**
- Phase 5 → COMPLETE (transitioning May 4)
- Phase 6 + Phase 7 → STARTING May 4
- Phase 8 → DEFERRED, gate review 2026-06-01 (5 blockers open)
- Phase 9 → unchanged target Sep 1+, hosting decision deferred to July
- Phase 10 → CLOSED 2026-04-22 (v4 crypto rejected)

**Five Phase 8 blockers (must all clear at 2026-06-01 gate):**
1. AI-001 — XAUUSD zero-BUY structural fix
2. AI-002 — three retirements/blocks merged (bollinger_bounce, ml_filtered_sma, ml_direct/XAUUSD)
3. AI-003 — Alembic migration system + CI schema-drift guard
4. AI-005 — 30% holdout OOS validation of R1-R7 on existing v3 trades
5. AI-006 + AI-007 — OVERLAP filter shadow-validated with ATR control, n≥20 new trades

**Artifacts:**
- docs/research/external_review_2026_04_28.md (synthesis)
- docs/meetings/2026_04_28_external_review_summary.md (1-pager)
- improvements.db::go_no_go_decisions (8 new rows)
- improvements.db::action_items (18 total: AI-001 through AI-018)
- improvements.db::risks_register (4 rows: R-EXT-001 through R-EXT-004)
- improvements.db::decision_inputs (1 row: external review)

────────────────────────────────────────────────────────────────────────────────
CHECKPOINT 1 — pause here, report Phase 1+2 status, await my "continue"
────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────
PHASE 3 — Dashboard discovery
────────────────────────────────────────────────────────────────────────────────

The project has dashboard/ at the top level. Before modifying anything:

### 3.1 Map the dashboard
Run:
  ls dashboard/
  find dashboard/ -name "*.py" -o -name "*.html" -o -name "*.jsx" -o -name "*.tsx" | head -30
  cat dashboard/README.md 2>/dev/null || echo "no README"

Identify:
- Framework (Streamlit / Flask / FastAPI / React / static HTML)
- Entry point (e.g., app.py, dashboard.py, main.py)
- How it currently reads from improvements.db
- Existing widgets/pages

### 3.2 Report the dashboard structure to me

Print:
- Framework detected
- Entry point file
- List of existing pages/widgets
- Sample of how DB is queried (1 code snippet)

Do NOT modify dashboard yet. Wait for my approval after CHECKPOINT 2.

────────────────────────────────────────────────────────────────────────────────
CHECKPOINT 2 — pause, share dashboard structure, await "continue"
────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────
PHASE 4 — Dashboard updates (4 new widgets)
────────────────────────────────────────────────────────────────────────────────

Add these four widgets to the dashboard. Match the existing framework's
patterns — don't introduce a new framework.

### Widget 1: "Meeting Outcomes — 2026-04-28"

A status banner card at the top of the main page. Shows:
- Meeting date
- 8 vote outcomes as a colored table:
  - GREEN votes (1, 4, 5, 6) — green dot
  - YELLOW votes (2, 3, 8) — amber dot
  - RED votes (7) — red dot
- Single-line summary: "7 of 8 aligned with external review"
- Link/expandable section: "View synthesis" → renders external_review_2026_04_28.md

Source: SELECT * FROM go_no_go_decisions WHERE decided_by='meeting_2026_04_28'
ORDER BY phase_number, decision_date

### Widget 2: "Phase Timeline" (Gantt-style or vertical timeline)

Visual showing:
- Phase 5: COMPLETE (gray) — ending 2026-04-28
- Phase 6 (TSMOM Layer): STARTING 2026-05-04 → ~2026-06-08 (blue)
- Phase 7 (Meta-Labeler Rebuild): STARTING 2026-05-04 → ~2026-06-01 (blue)
- Phase 8 Gate Review: MILESTONE 2026-06-01 (amber diamond)
- Phase 8 (Paper Trading): CONDITIONAL — earliest start 2026-06-01,
  6 weeks duration (gray-dashed if blockers OPEN, blue-solid if all clear)
- Phase 9 (Live trading): TARGET 2026-09-01 (gray, far future)
- July 2026 Hosting Re-eval: MILESTONE (amber diamond, AI-019)

Today's date marker: vertical line at current date.

Source: improvements.db::phase_steps + hardcoded milestone dates from the
decision log.

### Widget 3: "Phase 8 Blockers" — countdown to June 1 gate

Card showing:
- Days until June 1 gate: 34 days (count from today)
- 5 blocker rows with checkboxes (live-bound to action_items.status):
  ☐ AI-001  XAUUSD zero-BUY fix          [OPEN]      engineering
  ☐ AI-002  3 retirements/blocks merged  [OPEN]      engineering
  ☐ AI-003  Migration system + CI guard  [OPEN]      engineering
  ☐ AI-005  30% holdout OOS validation   [OPEN]      analytics
  ☐ AI-006/007  OVERLAP shadow validated [OPEN]      engineering

Each row links to the full action_item description.

Source: SELECT * FROM action_items WHERE blocking_phase = 8

Color the card border: red if any RED, amber if any IN_PROGRESS, green
if all DONE.

### Widget 4: "Risks Register" — top 4 risks from the review

Compact card listing:
- R-EXT-001  Gold regime reversal during Phase 8     CRITICAL / HIGH
- R-EXT-002  ML auto-bake of current biases          MEDIUM / HIGH
                                                     (manual trigger, downgraded)
- R-EXT-003  Schema-drift class not resolved         HIGH / MEDIUM
- R-EXT-004  Config-load-once silent stale window    MEDIUM / MEDIUM

Source: SELECT * FROM risks_register WHERE source LIKE '%external_review%'
ORDER BY severity DESC, likelihood DESC

### Layout

Place widgets in this order on the main dashboard page:
1. Meeting Outcomes banner (full width, top)
2. Phase Timeline (full width, below banner)
3. Phase 8 Blockers (left half, below timeline)
4. Risks Register (right half, below timeline)

If the dashboard already has a homepage, add these as a new section
"Meeting 2026-04-28" rather than replacing existing content.

────────────────────────────────────────────────────────────────────────────────
PHASE 5 — Verification & screenshot
────────────────────────────────────────────────────────────────────────────────

After widgets are added:
1. Start the dashboard locally (e.g., streamlit run, flask run, etc.)
2. Verify all 4 widgets render without errors
3. If headless screenshot capability exists, capture the homepage as
   docs/meetings/2026_04_28_dashboard_screenshot.png
4. Report URL where dashboard is accessible

────────────────────────────────────────────────────────────────────────────────
PHASE 6 — Final completion report
────────────────────────────────────────────────────────────────────────────────

Print to terminal:

  ═══════════════════════════════════════════════════════════════
  POST-MEETING PERSISTENCE + DASHBOARD UPDATE — COMPLETE
  ═══════════════════════════════════════════════════════════════
  Phase 1 — DB persistence:
    - go_no_go_decisions:  +8 rows (Vote 1-8)
    - phase_steps:         updated (Phase 5 done, 6/7 started)
    - action_items:        unchanged (18 total)
    - risks_register:      unchanged (4 total)
  Phase 2 — Decision log:
    - decision_log.md:     +1 entry (~80 lines)
  Phase 3-4 — Dashboard:
    - Framework:           <Streamlit/Flask/etc>
    - Widgets added:       4 (Meeting / Timeline / Blockers / Risks)
    - Modified files:      <list>
    - Screenshot:          <path or "skipped">
  Phase 5 — Dashboard live:
    - URL:                 <e.g. http://localhost:8501>
    - Status:              all widgets rendering
  Git state:
    Modified (staged):     <list>
    NOT committed (per project convention)
  ═══════════════════════════════════════════════════════════════
  Next strategic action: Begin AI-002 (3 retirements/blocks).
  Lowest-effort, highest-confidence — clears Blocker #2 of 5.
  Estimated time: 30-45 minutes.
  ═══════════════════════════════════════════════════════════════

────────────────────────────────────────────────────────────────────────────────
RULES OF EXECUTION
────────────────────────────────────────────────────────────────────────────────

1. Two checkpoints — pause for my "continue" before proceeding past each.
2. Bilingual rationale (Arabic + English) for go_no_go_decisions rows.
3. Don't introduce a new dashboard framework. Match what exists.
4. If improvements.db schema for go_no_go_decisions doesn't have rationale_ar
   column, propose ALTER TABLE before applying.
5. If dashboard/ directory is empty or doesn't have a runnable entry point,
   STOP and report — don't fabricate a dashboard from scratch.
6. Stage modified files in git but don't commit.
7. The bottom-line goal of the dashboard update: when I open the dashboard
   tomorrow morning, the first thing I see should answer "what was decided
   yesterday, what am I working on now, when is the next gate".