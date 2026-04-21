Update the dashboard AND the project tracker DB to reflect the new state from
step 4 (v4 OOS results) and prepare for step 5. Do all of this in one pass.

================================================================================
PART 1 — UPDATE improvements.db (project tracker DB)
================================================================================

A) phase_steps table — Phase 10:
   - Step 3 (build TSMOM variant): mark COMPLETE with completion_date=2026-04-21,
     notes="8 in-sample variants run. LO/12m best (Sharpe 1.06). See 
     docs/research/tsmom_crypto_prototype.md"
   - Step 4 (Purged K-Fold + held-out test): mark COMPLETE with completion_date
     =2026-04-21, notes="OOS RED — primary 2/4 gates, secondary 3/4 gates. 
     Strategy fails drift-stability gate due to 2025-2026 bear regime. See 
     docs/research/tsmom_crypto_oos_report.md"
   - Step 5 (correlations with S&P + FX portfolio): mark IN_PROGRESS, started 
     2026-04-21
   - Step 6 (AQR benchmark comparison): keep PENDING
   - Step 7 (formal go/no-go): keep PENDING — add note: "Decision deferred 
     pending step 5 correlation results AND possible Phase 10.5 (regime filter)"
   - Step 8 (document in crypto_momentum_prototype.md): keep PENDING

B) Add new phase: Phase 10.5 — TSMOM Crypto + Regime Filter (CONDITIONAL):
   - status: PENDING (will activate only if step 5 shows low correlation with 
     FX portfolio)
   - phase_number: 10.5
   - title_en: "TSMOM Crypto with Regime Filter (Rescue Attempt)"
   - title_ar: "TSMOM للكريبتو مع فلتر النظام (محاولة إنقاذ)"
   - description: "Add regime overlay (vol-based or correlation-based filter) 
     to TSMOM LO/12w. Re-run OOS validation. Activated only if step 5 confirms 
     diversification value vs FX portfolio."
   - parent_phase: 10
   - estimated_duration_days: 7
   - steps to seed (all PENDING):
     1. Define regime filter spec (realized vol threshold OR correlation spike 
        detector)
     2. Implement filter as overlay on existing TSMOM signal
     3. Re-run full backtest with filter (in-sample)
     4. Re-run OOS validation with filter
     5. Compare gated metrics vs ungated — does filter add or subtract value?
     6. Updated go/no-go decision

C) tsmom_runs table — verify the 4 OOS rows added by step 4 are present 
   (2 variants × {train, oos}). If missing, add them with verdict labels:
   - LO_12m_train: GOOD (Sharpe 1.26)
   - LO_12m_oos: REJECTED (Sharpe 0.03, drift 0.98)
   - LO_12w_train: GOOD (Sharpe 1.27)
   - LO_12w_oos: MARGINAL (Sharpe 0.55, drift 0.57, 3/4 gates)

D) data_segmentation_log: NO changes (segments unchanged).

E) Add a new table if missing — go_no_go_decisions:
   - columns: id, phase_number, decision_date, verdict (GREEN/YELLOW/RED), 
     gates_passed, gates_total, rationale_en, rationale_ar, decided_by, 
     next_action
   - Insert one row for Phase 10:
     * verdict: RED (pending step 5)
     * gates_passed: 2 (primary) / 3 (secondary)
     * gates_total: 4
     * rationale: "OOS Sharpe collapsed from 1.27 to 0.03 (12m) and 0.55 (12w). 
       2025-2026 bear regime exposes regime-dependence. Awaiting step 5 
       correlation analysis before final decision."
     * next_action: "Run step 5; if correlation with FX portfolio < 0.3, 
       initiate Phase 10.5 (regime filter rescue)"

================================================================================
PART 2 — UPDATE THE DASHBOARD
================================================================================

The dashboard is in dashboard/ (Streamlit). Add or update these elements:

A) Project Tracker tab — main view:
   - Reflect the new Phase 10 step statuses (3 and 4 COMPLETE, 5 IN_PROGRESS)
   - Show Phase 10.5 as a conditional sub-phase (greyed out / "PENDING 
     ACTIVATION") under Phase 10
   - Add a verdict badge column showing GREEN/YELLOW/RED for completed phases

B) NEW page: "v4 Crypto Momentum Status" (dashboard/pages/v4_status.py 
   or equivalent):
   Sections:
   1. Pipeline progress bar — Steps 1-8 with status icons
   2. In-sample vs OOS comparison table (8 variants from step 3, 2 from step 4)
   3. Gate scoreboard — 4 gates × 2 variants, with PASS/FAIL coloring
   4. Equity curves chart — load from data/research/tsmom_crypto_oos_equity.png 
      OR re-render from the CSV
   5. Fold stability table from step 4
   6. Current verdict + next action box (read from go_no_go_decisions table)
   7. Decision tree visualization showing the 5 options Claude Code presented, 
      with the chosen path highlighted (Option 4 + step 5 first)

C) UPDATE existing page: "Project Tracker" main page:
   - Add a "Recent Decisions" widget at top — last 3 rows from 
     go_no_go_decisions table
   - Add a "Critical Path" widget — shows what's blocking the next gate

D) UPDATE existing page (if exists): "v3 STABLE Status":
   - No data changes, but add a banner: "v4 entered OOS validation. v3 paper 
     trading continues unchanged through 2026-04-28 go/no-go meeting."

E) Sidebar — add a status pill:
   - "v3: STABLE | v4: RED (awaiting step 5)"
   - Auto-refreshes from DB

================================================================================
PART 3 — DOCUMENTATION SYNC
================================================================================

A) Update docs/v4_framework.md:
   - Add a new section "Status Log" at the bottom
   - Append entry: "2026-04-21: Steps 3-4 complete. OOS RED. Step 5 initiated. 
     Phase 10.5 (regime filter rescue) seeded as conditional phase."

B) Update CLAUDE.md (if it exists in project root):
   - Add to the project state summary: "v4 in step 5 of Phase 10. OOS validation 
     failed gates 1 and 3 of 4. Decision deferred to post-correlation analysis."

C) Create docs/research/decision_log.md (new file):
   - Running log of every go/no-go decision with date, verdict, rationale
   - Seed with the Phase 10 RED entry

================================================================================
RULES
================================================================================

- Make all DB changes in a single transaction. Roll back on any error.
- Before modifying improvements.db, create a backup at 
  data/improvements.db.bak.2026-04-21
- For dashboard changes: don't break existing pages. Test that the existing 
  Project Tracker tab still renders.
- For new pages: follow the existing Streamlit structure (look at any current 
  page in dashboard/pages/ as a template).
- Use Arabic + English bilingually wherever existing UI text is bilingual; 
  English-only where existing UI is English-only. Match the convention.
- After all updates, run the dashboard locally (streamlit run dashboard/app.py 
  or whatever the entry point is) and verify it loads without errors. Report 
  any rendering issues.
- DO NOT run step 5 (correlations) yet — that's a separate task. This task is 
  ONLY tracking infrastructure updates.

OUTPUT:
- Brief summary of what was changed
- List of files modified or created
- Any errors or warnings during dashboard test-run
- Confirmation that improvements.db.bak.2026-04-21 was created

Begin.