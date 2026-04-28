═══════════════════════════════════════════════════════════════════════════════
TASK: External-Review Synthesis & State Persistence
═══════════════════════════════════════════════════════════════════════════════

CONTEXT:
I just received a skeptical external review of the v3 go/no-go meeting prep
(claude.ai web session, conducted 2026-04-28). The reviewer had access to:
- BRIEFING_FOR_EXTERNAL_REVIEW.md (full)
- full_trade_evolution_report_2026-04-28.md (full)
- 2026_04_28_v3_go_nogo.md (full)
- decision_log.md (full)
- engine/trading_engine.py (lines 25-310, including blacklist enforcement
  at L285-291 and config loading at L31-50)
- config/paper.yaml + config/base.yaml (full)
- strategies/ directory listing
- Live web search on XAUUSD price action March-April 2026

The review identified BLOCKING issues that the meeting agenda was about to
miss. I need you to (1) capture the review's substance, (2) persist the
critical findings to the database, and (3) prepare follow-up action items.

═══════════════════════════════════════════════════════════════════════════════
YOUR TASK — execute in this order, do not skip steps:
═══════════════════════════════════════════════════════════════════════════════

────────────────────────────────────────────────────────────────────────────────
STEP 1 — Create the synthesis document
────────────────────────────────────────────────────────────────────────────────

Create file: docs/research/external_review_2026_04_28.md

The document MUST contain these sections, in this order, with these exact
headings. Write in clear professional English. No marketing tone. No
softening. The reviewer was deliberately sharp — preserve that.

## §1. Document purpose
One paragraph. State this is the synthesis of an external skeptical review
held 2026-04-28 before the v3 go/no-go meeting. Note that the review
reframed several "HIGH confidence" recommendations as conditional or
blocking, and identified risks not present in the original briefing.

## §2. Reviewer's understanding of project state
A 5-7 bullet summary, written from the reviewer's perspective, of what
the project actually is — not what the briefing claims it is. Must include:
- v3 PnL decomposition (with-XAUUSD vs without-XAUUSD)
- Single-symbol / single-direction / single-regime concentration
- Connection between XAUUSD profitability and the actual gold market
  trajectory March-April 2026 (gold fell ~17% from January peak)
- The "ml_direct made +$21k" framing is structurally misleading — it
  describes a broken model that happened to align with a falling market

## §3. Verification against codebase
Three subsections. Each verifies a briefing claim against the actual code:

### §3.1 Config loading mechanism (engine/trading_engine.py:31-50)
Quote the resolve_config_path() function. Confirm: TRADING_MODE=paper
(default) → loads config/paper.yaml. Confirms briefing's claim that
base.yaml's strategy_blacklist is dormant.

### §3.2 Blacklist enforcement logic (engine/trading_engine.py:285-291)
Quote the blacklist check loop. Note critical finding: the check uses
`bl.get("strategy") == strategy.name and bl.get("symbol") == symbol`
— there is NO direction (BUY/SELL) check. If the blacklist were active,
it would block both directions equally. This means the "happy accident"
narrative cannot rescue the design: had paper.yaml mirrored base.yaml,
ALL 77 v3 XAUUSD trades would have been blocked, not just SELL.

### §3.3 Config-load-once pattern
Note that __init__ reads YAML once at startup. There is no hot-reload.
Implication: any blacklist change requires engine restart + verification
that the loaded config matches the file on disk.

## §4. Answers to briefing §5 questions (A through F)
For each question, write 3-6 sentences. No bullet points within these
answers — write as proper paragraphs. Preserve the reviewer's edge:

### §4.A Is the project actually progressing?
Conclusion: insufficient data; the +10.6% is dominated by a single-symbol
single-direction window during a confirmed downtrend regime. Without
XAUUSD, v3 is −$2,669 over 60 trades on 6 symbols. The system has not
demonstrated a generalizable edge.

### §4.B XAUUSD concentration
Conclusion: the concentration is FOUR-LAYERED (symbol, direction, regime,
window). Mandate: zero-BUY structural fix is BLOCKING for Phase 8, not
deferrable to Phase 7 audit.

### §4.C OVERLAP filter — overfitting risk
Conclusion: the named hypothesis ("OVERLAP session is bad for XAUUSD") is
likely confounded with volatility (ATR). Required falsification: shadow-
mode for 14+ days, control for ATR, require pattern persistence on n≥20
new OVERLAP trades before paper.yaml installation. p=0.006 on a post-hoc
hypothesis does not carry its nominal power.

### §4.D Blacklist "happy accident"
Conclusion: BOTH framings the briefing offered are post-hoc rationalizations.
The honest reading: an unlogged silent config drift produced an unreviewed
$21k decision. The institutional fix requires a written RFC justifying the
keep-or-block decision based on FORWARD risk in both regimes (rising and
falling gold), not on retrospective P&L. The reviewer's recommended
answer is option (D): block ml_direct/XAUUSD in BOTH configs until zero-BUY
is resolved — and document this as the institutionally correct choice
even if business pressure selects option (C).

### §4.E Phase 8 readiness
Conclusion: NOT READY for Jun 8 OR Jun 14. Five blocking conditions:
zero-BUY unresolved, two strategies retiring during not before, four
schema-drift instances suggest more lurking, 6-day shadow gap unrecoverable,
projected Q3 gold reversal coincides with planned 6-week window. Reviewer's
proposed timeline: Phase 8 gate re-examined June 1, with conditional
GREEN only if zero-BUY fix lands AND shadow filters validate AND no new
schema-drift surfaces.

### §4.F v4 closure
Conclusion: the rejection decision was correct AND the methodology was
clean — preserve that discipline. But there's a deeper observation: v4
was held to a higher methodological bar than v3. v4 had locked scope,
single-shot evaluation, and OOS separation. v3's R1-R7 are being tested
on the same dataset that generated them, and Phase 8 is being treated
as OOS while filters are pre-installed — converting OOS into a second IS.
Required fix: hold out 30% of current v3 trades (~41 trades) before
running R1-R7 validation; treat the holdout as pre-Phase-8 OOS.

## §5. Critical risks the briefing missed
List exactly four risks, each with a short rationale (2-3 sentences):

1. **Gold regime reversal during Phase 8 window**
   Q3 2026 institutional consensus (JPMorgan $5,000, Goldman $5,400-6,000,
   Deutsche Bank $6,000) is bullish. Phase 8 (Jun 8 - Jul 20) coincides with
   the projected reversal. A zero-BUY system in a rising gold market is a
   guaranteed drawdown.

2. **ML_TRAINING_THRESHOLD = 200 will auto-bake current biases**
   At ~63 more closed v3 trades, the system will auto-train ML on a dataset
   featuring zero-BUY on XAUUSD, retired strategies' losing patterns, and
   a single-regime sample. The next model will inherit and amplify these
   biases. Training set composition must be explicitly decided BEFORE the
   threshold is hit, not implicitly by trade count.

3. **No migration system → schema-drift class is not "resolved"**
   Four schema-drift instances surfaced in two weeks. The "RESOLVED" label
   on the 2026-04-22 incident describes one instance, not the class. Without
   Alembic (or equivalent) + a CI guard comparing inspector.get_columns()
   to ORM Model.__table__.columns, the next ALTER TABLE will produce another
   silent failure. Treat this as a P0 infrastructure debt.

4. **Config-load-once + manual restart = silent stale-config window**
   Every config change opens a window where the engine is running an old
   config. Six days of schema-drift demonstrated this class of failure. A
   startup-time config snapshot logger + post-restart self-check is required
   before any further config-driven decisions are made.

## §6. Recommended votes for the 8 meeting decisions
Render as a markdown table with columns: # | Question | Briefing's recommended | Reviewer's recommended | Delta rationale

Vote-by-vote (preserve the reviewer's actual positions, no softening):

1. Phase 5 → Phase 6/7 transition — both YES May 4 — agreed
2. Phase 8 start — briefing says Jun 8 — reviewer says DEFERRED, gate review June 1
3. Block XAUUSD OVERLAP — briefing says install in paper.yaml — reviewer
   says shadow-mode 14d first, then decide
4. Retire bollinger_bounce — both YES — reviewer adds "before Phase 7"
5. Retire ml_filtered_sma — both YES — reviewer adds "before Phase 7"
6. Resolve blacklist mismatch — briefing says option (C) modified —
   reviewer says option (D): block ml_direct/XAUUSD in both configs until
   zero-BUY is resolved; document option (D) as correct answer even if
   business pressure selects (C)
7. Phase 7 includes XAUUSD zero-BUY investigation — briefing says YES —
   reviewer says ELEVATE TO BLOCKING for Phase 8
8. Phase 9 hosting decision — both DEFER — agreed

## §7. Action items (5 categories)

### §7.1 BLOCKING for Phase 8 (no Phase 8 start until all complete)
- AI-001: Implement XAUUSD BUY-side capability (root-cause zero-BUY)
- AI-002: Retire bollinger_bounce + ml_filtered_sma from active rotation
- AI-003: Build Alembic-based migration system OR equivalent CI guard
- AI-004: Implement startup-time config snapshot logger + restart self-check
- AI-005: Hold out 30% of v3 trades; run R1-R7 OOS validation on holdout

### §7.2 SHADOW-MODE validation (run May 4 - June 1)
- AI-006: Install OVERLAP filter for XAUUSD in shadow logging only
- AI-007: Build ATR-controlled OVERLAP analysis (test confound hypothesis)
- AI-008: Daily shadow-staleness alert (max 30 min lag) on dashboard

### §7.3 Documentation & governance
- AI-009: Write RFC for ml_direct/XAUUSD keep-or-block decision (forward-
  looking, not P&L-justified)
- AI-010: Define Phase 8 quantitative success criteria in writing BEFORE
  Phase 8 starts (PnL floor, Sharpe target, min active symbols/directions,
  max drawdown, halt conditions)
- AI-011: Decide ML training set composition explicitly (before
  ML_TRAINING_THRESHOLD = 200 is hit)

### §7.4 Risk monitoring during Phase 5-7
- AI-012: Gold regime monitor — daily check on (5-day SMA > 20-day SMA)
  with alert if SMA crossover triggers
- AI-013: Per-symbol per-direction trade count dashboard (catches
  underpowered cells before they become recommendations)

### §7.5 Post-meeting documentation
- AI-014: Write decision_log.md entries for each YES vote
- AI-015: Update improvements.db::go_no_go_decisions with meeting outcomes
- AI-016: Update improvements.db::phase_steps for any phase transitions

## §8. Things the reviewer flagged as "may be wrong about"
Reproduce exactly these two reviewer self-doubts:
1. Possible over-pessimism on zero-BUY — perhaps the model honestly learned
   "XAUUSD doesn't go BUY above volatility threshold X" as a real signal,
   not a bias. But burden of proof is on the project, not the skeptic.
2. Possibly over-cautious on n=137 sample — but Sharpe 95% CI on n=137 is
   approximately ±1.0, which doesn't answer anything either way.

## §9. Open questions for the meeting
Five questions the meeting MUST answer before voting:
1. If we vote option (D) on R3 (block ml_direct/XAUUSD), what is the cost
   of the next 4 weeks of foregone XAUUSD profit, and is that cost
   acceptable as a hedge against gold reversal?
2. Can zero-BUY be addressed inside Phase 7's 5-week window, or does it
   require a dedicated phase?
3. What is our plan if Phase 8 begins and gold reverses to bullish in
   week 2?
4. Who owns the Alembic/migration migration project (AI-003)?
5. Are we prepared to accept "Phase 8 deferred indefinitely" as a possible
   outcome of the June 1 gate review?

## §10. Final synthesis paragraph
One closing paragraph. Reviewer's bottom line: v3 is not "narrowly
profitable v3" — it is "structurally broken model funded by an incidental
window of bias × falling gold". The meeting's real question is not the
schedule. It is whether the team confronts that framing or celebrates the
+10.6% as accomplishment. The reviewer urges confrontation. The system
is fixable, but not if +10.6% is read as confirmation.

────────────────────────────────────────────────────────────────────────────────
STEP 2 — Persist findings to the database
────────────────────────────────────────────────────────────────────────────────

Use sqlite3 (data/improvements.db). Create the rows below. If the schema
needs new columns, USE str_replace-equivalent edits and propose the column
additions to me before applying — do not silently alter schema.

### 2.1 Insert into go_no_go_decisions
One row, with these field values:
- decision_date: 2026-04-28
- phase: 5
- subject: "External skeptical review of v3 go/no-go briefing"
- verdict: "REVIEW_COMPLETE"  (not GREEN/YELLOW/RED — this is an input
  to the decision, not a decision itself)
- gates_passed: NULL
- gates_total: NULL
- rationale: First 500 chars of §10 Final Synthesis
- artifacts: "docs/research/external_review_2026_04_28.md"
- decided_by: "external_review_claude_web_2026_04_28"

### 2.2 Insert into action_items (or equivalent table)
Verify the table exists. If not, propose schema:
  id INTEGER PRIMARY KEY
  action_id TEXT UNIQUE NOT NULL  (e.g. "AI-001")
  category TEXT NOT NULL  (BLOCKING / SHADOW / DOCS / MONITORING / POST_MEETING)
  title TEXT NOT NULL
  description TEXT
  blocking_phase INTEGER  (e.g. 8 if it blocks Phase 8)
  status TEXT DEFAULT 'OPEN'  (OPEN / IN_PROGRESS / DONE / CANCELLED)
  created_date TEXT
  due_date TEXT
  source TEXT  (e.g. "external_review_2026_04_28")

Insert all 16 action items (AI-001 through AI-016) from §7.

### 2.3 Insert into risks_register (propose if missing)
Schema if missing:
  id INTEGER PRIMARY KEY
  risk_id TEXT UNIQUE
  title TEXT
  description TEXT
  severity TEXT  (CRITICAL / HIGH / MEDIUM / LOW)
  likelihood TEXT  (HIGH / MEDIUM / LOW)
  mitigation TEXT
  status TEXT DEFAULT 'OPEN'
  identified_date TEXT
  source TEXT

Insert four rows, one per risk in §5:
- R-EXT-001: Gold regime reversal during Phase 8 — CRITICAL / HIGH
- R-EXT-002: ML_TRAINING_THRESHOLD auto-bakes biases — HIGH / HIGH
- R-EXT-003: Schema-drift class not resolved without migrations — HIGH / MEDIUM
- R-EXT-004: Config-load-once silent stale window — MEDIUM / MEDIUM

### 2.4 Verify writes
After all inserts, run:
  SELECT COUNT(*) FROM go_no_go_decisions WHERE decision_date='2026-04-28';
  SELECT COUNT(*) FROM action_items WHERE source='external_review_2026_04_28';
  SELECT COUNT(*) FROM risks_register WHERE source='external_review_2026_04_28';

Report the counts to me. Expected: 1, 16, 4.

────────────────────────────────────────────────────────────────────────────────
STEP 3 — Prepare a meeting-ready 1-pager
────────────────────────────────────────────────────────────────────────────────

Create file: docs/meetings/2026_04_28_external_review_summary.md

Maximum 1.5 pages. Format for someone who has 3 minutes before the meeting:

## Executive summary (3 bullets)
- Most important reframing
- Most important risk added
- Most important vote that should change

## Vote changes recommended (table)
Same as §6 of the synthesis, but condensed to one line per vote.

## The single first action
Identify ONE action that must happen in the meeting's opening 5 minutes.
Reviewer's pick: open with R3 reframed as option (D), not (C). State the
$21k as "data we are choosing to set aside" rather than "data validating
our position".

## Three decisions that can wait
List items the meeting can DEFER without cost (so it doesn't get bogged
down in non-blockers).

────────────────────────────────────────────────────────────────────────────────
STEP 4 — Output report
────────────────────────────────────────────────────────────────────────────────

After all of the above, print exactly this report to the terminal:

  ════════════════════════════════════════════════════
  EXTERNAL REVIEW PERSISTENCE — COMPLETE
  ════════════════════════════════════════════════════
  Synthesis doc:     docs/research/external_review_2026_04_28.md (size: XX KB)
  Meeting 1-pager:   docs/meetings/2026_04_28_external_review_summary.md (size: XX KB)
  DB rows inserted:
    - go_no_go_decisions:  1
    - action_items:        16  (AI-001 through AI-016)
    - risks_register:      4   (R-EXT-001 through R-EXT-004)
  Schema changes proposed: <list any, or "none">
  ════════════════════════════════════════════════════
  Next action: review the synthesis doc, then walk into the meeting
  with the 1-pager open.
  ════════════════════════════════════════════════════

═══════════════════════════════════════════════════════════════════════════════
RULES OF EXECUTION
═══════════════════════════════════════════════════════════════════════════════

1. Do NOT soften the reviewer's tone. The user explicitly requested
   skeptical review. Translating "structurally broken" into "needs
   improvement" defeats the purpose.

2. Do NOT add new analysis of your own beyond what's described above.
   Your job is to capture and persist the review, not to mediate it.

3. Do NOT silently alter database schema. If a table is missing, propose
   the schema and ask before applying.

4. If any source file (engine/trading_engine.py, config/*.yaml, the four
   uploaded markdown files) is missing or different from what's described
   in this prompt, STOP and report the discrepancy. Do not fabricate
   content.

5. All file writes go to the actual project directory (D:\forexAI on
   Windows, or wherever the working dir resolves). Do not write to /tmp
   or staging unless explicitly asked.

6. After Step 4, wait for my next instruction. Do not proactively start
   implementing AI-001 through AI-016. The meeting hasn't happened yet.