# Dashboard Redesign Proposal — 2026-05-01

**Date prepared:** 2026-05-01
**Author:** automated proposal (Claude Code), per `docs/p.md` Phase 2
**Status:** PROPOSAL ONLY — no code or data modified. For Checkpoint 2 review.
**Inherits from:** `dashboard_audit_2026_05_01.md` (Phase 1 discovery).

---

## 1. Design principles (the rules)

| # | Principle | Operational meaning |
|---|---|---|
| 1 | **Single source of truth** | Every concept (action items, risks, decisions, phases) lives in EXACTLY ONE primary tab. Other tabs link, never duplicate. |
| 2 | **Tabs answer questions** | Each tab name IS the question, in plain language. The user should be able to read the tab list and instantly know what's where. |
| 3 | **Status before detail** | Top of every tab: 3–5 numbers summarising the situation. Then drill-down. Never start with a 50-row table. |
| 4 | **Filter, don't fragment** | One "blockers" view with a phase filter — not three separate Phase-7 / Phase-8 / Phase-9 widgets. |
| 5 | **Time-aware** | Every list shows "last updated" timestamp. Stale data is visibly stale. |
| (6) | **Bilingual labels OK, no script-mixing** | Labels can be Arabic OR English, never mixed within one label. Tab titles stay short. |

---

## 2. New tab structure — six tabs

| # | Tab name (Arabic / English) | Question it answers |
|---|---|---|
| 1 | **أين نحن؟ / Where are we?** | "What's the project's current state and what should I be working on right now?" |
| 2 | **بنود التنفيذ / Action Items** | "What's blocking us, and who owns each item?" |
| 3 | **القرارات / Decisions** | "What did we decide and why?" |
| 4 | **المخاطر / Risks** | "What could go wrong, and what are we doing about it?" |
| 5 | **التداول / Trading** | "How is the live engine doing — state, P&L, signals, analytics?" |
| 6 | **الوثائق / Documents** | "Where's the report or research doc on X?" (index, not content) |

If a future need doesn't fit one of these six, it should become a markdown report under `docs/`, not a new tab.

---

## 3. Per-tab wireframe and effort

### Tab 1 — أين نحن؟ / Where are we? (S)

**Purpose:** Single-screen "what state is the project in" answer. Replaces the home page's KPI block + the Project Tracker's Phases inner tab + the Connection page.

**Top status strip (always visible at top of every tab — Principle 5):**
```
ForexAI Project Dashboard · last refreshed: 2026-05-01 15:42 UTC
Current phase: Phase 7 (kickoff May 4) · Days until Jun 1 gate: 31 · Engine: نشط (last scan 15:05)
```

**Section A — Phase status header (5-card row):**
```
┌──────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
│ Phase 6      │ Phase 7      │ Phase 8      │ Phase 9      │ Engine       │
│ TSMOM         │ Meta-Labeler │ Paper trading│ Live trading │ نشط          │
│ IN_PROGRESS  │ KICKOFF May 4│ DEFERRED     │ NOT_STARTED  │ scan #34     │
│ 0/5 steps    │ 0/11 steps   │ Jun 1 gate   │ Sep 1 target │ 12 min ago   │
└──────────────┴──────────────┴──────────────┴──────────────┴──────────────┘
```

**Section B — "What I should be working on right now" (top 5 by blocking_phase ascending):**
```
أهم البنود (by blocking_phase, top 5):
[BLOCKING · Phase 7] AI-017b  Fix SL_HIT exit_reason mislabel
[BLOCKING · Phase 7] AI-020   Remove USDCAD from instruments list
[BLOCKING · Phase 8] AI-001   Implement XAUUSD BUY-side capability
[BLOCKING · Phase 8] AI-003   Build Alembic-based migration system
[BLOCKING · Phase 8] AI-004b  AI-004 enhancement: cross-config drift
                                                    → Open Tab 2 for full list
```

**Section C — Last 3 decisions logged (from `go_no_go_decisions`):**
```
آخر القرارات:
2026-04-28 · Vote 6D · GREEN · ml_direct/XAUUSD blocked until AI-001
2026-04-28 · Vote 5  · RED   · ml_filtered_sma retired (R:R pathology)
2026-04-28 · Vote 4  · RED   · bollinger_bounce retired (R:R pathology)
                                                    → Open Tab 3 for full list
```

**Section D — Engine health (from logs + AI-004 [CONFIG] line):**
```
حالة المحرّك:
MT5: متصل · رصيد $110,444 · 0 صفقات مفتوحة · 7 instruments active
Config: paper.yaml (sha256 0a52718ea4c5...) · 2 blacklist entries
Latest [CONFIG] log: 2026-04-28 21:55:07 (3 days ago) — drift not checked yet?
Telegram: timeout (last error 12 min ago)
```

**Effort:** S. Pure read-only; composes existing queries. No new logic.

---

### Tab 2 — بنود التنفيذ / Action Items (M)

**Purpose:** THE single home for `action_items` (AI-*, GAP-FID-*, GAP-OPS-*) plus the `improvements` legacy table is RETIRED from the surface here. Risks live in Tab 4 (separate concept).

**Top KPI bar:**
```
المعلق: 24    قيد التنفيذ: 1    تم: 6    BLOCKING: 12    DOCS: 6    MONITORING: 6    SHADOW: 2
```

**Filters (sticky, above the table):**
- Phase: ☐ 7  ☐ 8  ☐ 9  ☐ no-phase
- Category: ☐ BLOCKING  ☐ DOCS  ☐ MONITORING  ☐ SHADOW  ☐ POST_MEETING
- Status: ☐ OPEN  ☐ IN_PROGRESS  ☐ DONE
- Search: [____________]

**Default view:** OPEN items, sorted by `blocking_phase` ASC then `created_date` DESC.

**Table columns:**
```
ID         Title                                              Phase  Status     Created    Source              Detail
AI-017b    Fix SL_HIT exit_reason mislabel                    7      OPEN       05-01      phase7_prep         [▶]
AI-020     Remove USDCAD from instruments list                7      OPEN       05-01      phase7_prep         [▶]
AI-017     Audit remaining strategies for R:R pathology       7      IN_PROG    04-28      meeting             [▶]
AI-001     Implement XAUUSD BUY-side capability               8      OPEN       04-28      meeting             [▶]
AI-003     Build Alembic-based migration system               8      OPEN       04-28      meeting             [▶]
AI-004b    AI-004 enhancement: cross-config drift detection   8      OPEN       05-01      phase7_prep         [▶]
...
```

**Detail panel (shown when [▶] clicked):**
- Full description, notes, source
- Linked artefact(s) — auto-detect references to `docs/research/*.md` in description/notes and render as click-through links
- Status timeline (from `status_history` if available)
- "Mark IN_PROGRESS / DONE" controls — read-only for now, edit deferred to a separate task

**The legacy `improvements` table (76 rows, IMP-*) is NOT shown here.** The DB rows remain for history; the dashboard simply stops surfacing them. If the user needs IMP-* lookup, it lives in `docs/IMPROVEMENTS_PORTABLE.md` and the DB.

**Effort:** M. Central concept; needs filter UX + detail panel + a small "open in detail" component. About 200–300 lines.

---

### Tab 3 — القرارات / Decisions (M)

**Purpose:** Single home for `go_no_go_decisions` + `decision_inputs` + (legacy) `decisions_log`. Replaces 6 surfaces of decisions data.

**Top KPI bar:**
```
إجمالي: 11 verdicts    GREEN: 3    YELLOW: 2    RED: 6    آخر قرار: 2026-04-28 (3 days ago)
```

**Filter row:**
- Phase: ☐ 5..9 ☐ 10  ☐ 10.5
- Verdict: ☐ GREEN  ☐ YELLOW  ☐ RED
- Source: ☐ meeting_2026_04_28  ☐ retro_v3  ☐ ...
- Search: [____________]

**Chronological list (newest first):**
```
2026-04-28 · meeting_2026_04_28
  Vote 6D — GREEN — ml_direct/XAUUSD blocked until AI-001 + Jun 1 gate
    Rationale: Zero-BUY structural defect; meeting vote 6D ...
    Next action: AI-001 implementation, June 1 gate review
    Artefacts: docs/meetings/2026_04_28_external_review_summary.md
                                                              [Expand ▼]

2026-04-28 · meeting_2026_04_28
  Vote 5 — RED — ml_filtered_sma retired entirely
    Rationale: WR 68%, R:R 0.11, PF 0.23 — pathology pattern
                                                              [Expand ▼]
...
```

**Bottom section — "Decision inputs / reviews" (from `decision_inputs`, 1 row currently):**
Compact list. Newest first. Same format as decisions but visually distinct (different border colour).

**Legacy `decisions_log` table (40 rows):** rendered in a collapsible expander labelled "Older decisions (pre-2026-04 schema)". Keeps history visible without dominating the live view.

**Effort:** M. Three table sources unified at presentation; chronological merge; expand/collapse on items. ~200 lines.

---

### Tab 4 — المخاطر / Risks (S)

**Purpose:** All `risks_register` rows (currently 4) with severity × likelihood matrix, mitigation linkage to action items.

**Top KPI bar:**
```
إجمالي: 4    CRITICAL: 0    HIGH: 2    MEDIUM: 2    LOW: 0    open mitigations: 4
```

**2×2 risk matrix (severity × likelihood) — visual grid:**
```
                  Likelihood: LOW       MEDIUM        HIGH
Severity: HIGH     ─                    R-EXT-001     R-EXT-002
          MEDIUM   R-EXT-004            R-EXT-003     ─
          LOW      ─                    ─             ─
```

Click a cell → see the risk(s) in that quadrant.

**Risk list (sorted by severity × likelihood descending):**
```
R-EXT-002 — Bias × falling-gold luck-driven profitability     HIGH × HIGH
   Mitigation: Vote 6D blacklist + AI-001 zero-BUY fix
   Linked action: AI-001 (BLOCKING, Phase 8)                 [→ Tab 2]
   Status: mitigation in-flight

R-EXT-001 — Phase 8 paper-trading window data quality        HIGH × MEDIUM
   Mitigation: AI-005 (30% holdout OOS validation)
   Linked action: AI-005 (BLOCKING, Phase 8)                 [→ Tab 2]
   Status: mitigation in-flight
...
```

**Effort:** S. Small dataset, mostly presentation work. ~80 lines.

---

### Tab 5 — التداول / Trading (L)

**Purpose:** All trading-system live state and analytics. Replaces pages 2, 3, 4, 5, 8, 10, 11, 12, plus the Project Tracker's Performance and Regime inner tabs. This is the heaviest tab — splits into 4 inner sections.

**Top status header (from existing home-page sidebar widgets):**
```
MT5: متصل · رصيد $110,444 · إكويتي $110,444 · مفتوحة: 0 · الوضع: ورقي · سوق: مفتوح (London + New York)
```

**Inner section 5A — Live (replaces pages 2, 8, 12 partially):**
- Open positions table (live MT5 query)
- News calendar (next 24h, from `news_events`)
- Connection / engine health log tail (last 50 lines from `paper_trading.log`)
- Active strategies + blacklist (from `[CONFIG]` line)

**Inner section 5B — Analytics (replaces page 5 + Project Tracker's Performance and Regime tabs):**
- Equity curve + drawdown (from `account_snapshots`)
- KPI ribbon: total trades, WR, $-PF, R-PF, expectancy, max DD, **Phase 7 dual-gate verdict** (R-PF≥1.3 AND $-PF≥1.0)
- Per-pair breakdown (from `trade_results`)
- Per-strategy breakdown
- Monthly P&L heatmap
- Regime × strategy matrix (only if `regime_logs` populated; otherwise hidden — Principle 5)

**Inner section 5C — Trade log (replaces pages 3, 10):**
- Filterable list of closed trades (symbol, strategy, date range, exit reason, profitable)
- Click row → expand to show candlestick chart with entry/SL/TP/exit markers (extracted logic from page 10)
- Export CSV

**Inner section 5D — Signals & Shadow (replaces page 4 + Project Tracker's Shadow tab):**
- Signal log with status (executed / ML-filtered / risk-rejected)
- Shadow signal subset (`shadow_signals` table) — separate visual treatment
- ML confidence vs profitability scatter

**Page 11 (Reports) is replaced by:** a "Generate daily report" button at the top of Tab 5 that runs the existing reporting logic and either downloads or shows the result. Telegram-export remains a CLI/script invocation per CLAUDE.md.

**Page 6 (AI/ML model)** content (walk-forward, feature importance, ROC) is moved into a 5th inner section "5E — ML Model" only if it's still actively used. Otherwise → Tab 6 (Documents) as a link to the model report.

**Effort:** L. Largest tab; consolidates ~6 existing pages. Estimate 400–500 lines after deduplication. Inner-section navigation via `st.tabs(...)`.

---

### Tab 6 (optional) — الوثائق / Documents (S)

**Purpose:** Index of `docs/research/` and `docs/meetings/`. Click a row → open in browser/local. Not document content; just an index.

**Layout:**
```
الأبحاث (docs/research/) — 23 files
  2026-05-01  dashboard_audit_2026_05_01.md             (this audit)
  2026-05-01  dashboard_redesign_proposal.md            (this proposal)
  2026-05-01  ai017_supplemental_findings_2026_05_01.md
  2026-05-01  phase7_blocker_2_audusd_usdcad_rr_analysis.md
  2026-05-01  phase7_training_set_proposal.md
  2026-04-30  ai017_rr_audit.md
  2026-04-28  external_review_2026_04_28.md
  ...

الاجتماعات (docs/meetings/) — 3 files
  2026-05-04  2026_05_04_kickoff_readiness.md           (uncommitted)
  2026-04-28  2026_04_28_v3_go_nogo.md
  2026-04-28  2026_04_28_external_review_summary.md
```

Sort newest-first. Filter by date range or filename search.

**Effort:** S. ~50 lines. Filesystem walk + render.

---

## 4. Old → new migration map

### Top-level pages

| Existing surface | Destination | Notes |
|---|---|---|
| `app.py` home — KPI metrics block | Tab 5 (Trading > top header) | 6 KPIs become 1 ribbon |
| `app.py` home — Equity curve + signal pie | Tab 5 (Analytics inner section) | Move as-is |
| `app.py` home — Per-pair table | Tab 5 (Analytics) | Move as-is |
| `app.py` home — Recent signals | Tab 5 (Signals & Shadow) | Move as-is |
| `app.py` home — Next Actions widget | Tab 1 (Where are we? > Section B) | Already designed for this purpose |
| `app.py` home — Quick Navigation grid | DELETE | Tabs replace it |
| `app.py` home — Meeting banner | Tab 1 (Where are we? > Section C) | Last 3 decisions display |
| `app.py` sidebar — MT5 status, market, mode, engine state, news | Tab 1 (top status strip + Section D) + Tab 5 header | Sidebar simplifies to just navigation |
| `app.py` sidebar — v3/v4 status pill | Tab 1 (Phase status header) | Already conveyed by phase cards |
| `1_الماسح.py` (Signal Scanner manual) | DELETE | Engine auto-scans; never used in workflow |
| `2_الصفقات.py` (Open Trades) | Tab 5 (Live inner section) | Open-positions table |
| `3_السجل.py` (Closed Trades log) | Tab 5 (Trade log inner section) | Filterable list |
| `4_الاشارات.py` (Signals log) | Tab 5 (Signals & Shadow inner section) | |
| `5_التحليلات.py` (Performance Analytics) | Tab 5 (Analytics inner section) | Primary content of 5B |
| `6_الذكاء_الاصطناعي.py` (AI/ML model) | Tab 5 (Analytics inner section, optional 5E sub-section) OR Tab 6 link | User decision: keep on dashboard or move to a markdown report? |
| `7_الاختبار.py` (Backtest UI) | DELETE | CLI is canonical (`scripts/run_backtest_all.py`) |
| `8_الأخبار.py` (News calendar) | Tab 5 (Live inner section) | Compact widget version |
| `9_Chat.py` (Trading Chat) | DELETE | No active workflow |
| `10_Trade_Chart.py` (Trade visualisation) | Tab 5 (Trade log > expand row → chart) | Logic moves into expand panel |
| `11_التقارير.py` (Daily Reports) | Tab 5 (Live > "Generate daily report" button) + CLI | Telegram-export stays CLI |
| `12_الاتصال.py` (MT5 Connection / errors) | Tab 1 (Engine health) + Tab 5 (Live > engine log tail) | Compact widgets |
| `13_Project_Tracker.py` Phases tab | Tab 1 (Phase status header + Section D) | Decomposed |
| `13_Project_Tracker.py` System state tab | Tab 1 (Engine health) | |
| `13_Project_Tracker.py` Performance monitor tab | Tab 5 (Analytics) | |
| `13_Project_Tracker.py` Data segmentation tab | DELETE from dashboard, retain DB | Markdown report at `docs/research/data_segmentation.md` if needed |
| `13_Project_Tracker.py` Regime analysis tab | Tab 5 (Analytics, conditional render) | Hide if `regime_logs` empty |
| `13_Project_Tracker.py` Meta-Labeler tab | DELETE from dashboard, retain DB | Surface findings via `docs/research/`; `tsmom_runs` is research data |
| `13_Project_Tracker.py` Decisions tab | Tab 3 (Decisions) | Three-source unification happens here |
| `13_Project_Tracker.py` Improvements tab | Tab 2 (Action items) | `improvements` legacy table dropped from surface |
| `13_Project_Tracker.py` Shadow trading tab | Tab 5 (Signals & Shadow inner section) | Compact view |
| `14_v4_Crypto_Status.py` | DELETE from dashboard | Phase 10 REJECTED 2026-04-22; archive as `docs/research/v4_phase10_summary.md` (already partially documented elsewhere) |
| `15_Meeting_Outcomes.py` | DELETE | Votes → Tab 3, blockers → Tab 2, risks → Tab 4. Page itself was a one-event view that's now expired. |

### Database tables — new surfacing

| Table | Old surface | New surface |
|---|---|---|
| `action_items` | 6 places | Tab 2 only |
| `risks_register` | 2 places | Tab 4 only |
| `go_no_go_decisions` | 6 places | Tab 3 (primary) + Tab 1 last-3 link |
| `decision_inputs` | 1 place | Tab 3 (sub-section) |
| `decisions_log` (legacy) | 1 place | Tab 3 (collapsible expander, marked legacy) |
| `project_phases` | 4 places | Tab 1 (phase status header) only |
| `phase_steps` | 3 places | Tab 1 (phase header drill-down) only |
| `improvements` (legacy) | 1 place | RETIRED from dashboard surface |
| `tsmom_runs` | 3 places | RETIRED from dashboard; surfaced via research docs |
| `meta_labeler_runs` | 1 place | RETIRED from dashboard; surfaced via research docs |
| `expectancy_analysis` | 1 place | Tab 5 (Analytics, optional widget) |
| `system_state` | 1 place | Tab 1 (Engine health) |
| `data_segmentation_log` | 1 place | RETIRED |
| `implementation_log` | 0 places | NEW: collapsible expander on Tab 3 (linked to its decision) |
| `status_history` | 0 places | NEW: timeline component in Tab 2 detail panel |

---

## 5. List of surfaces to DELETE

| Page / Tab | Reason | Replacement |
|---|---|---|
| `1_الماسح.py` | Manual scan unused; engine auto-scans hourly | None needed |
| `7_الاختبار.py` | Duplicates CLI workflow per CLAUDE.md | None needed |
| `9_Chat.py` | Generic chat shell, no active workflow | Project Q&A happens elsewhere |
| `15_Meeting_Outcomes.py` | One-event historical page; content lives in Tabs 2, 3, 4 | Tabs 2 + 3 + 4 |
| `14_v4_Crypto_Status.py` | Phase 10 REJECTED; historical | Archive doc + Tab 6 link |
| Project Tracker → Improvements inner tab `improvements` table | Legacy, separate from `action_items`, confusing | Tab 2 |
| Project Tracker → Data segmentation inner tab | Rarely consulted | Markdown report on demand |
| Project Tracker → Meta-Labeler inner tab | Research artefact | Research docs |
| Project Tracker page itself (`13_Project_Tracker.py`) | After tab decomposition | New tabs cover all live content |
| `app.py` Quick Navigation grid | Replaced by tab structure | Tab list itself is navigation |

---

## 6. Implementation effort summary

| Tab | Effort | Lines (est) | Key risk |
|---|---|---:|---|
| Tab 1 — Where are we? | S | 200 | None — composes existing data |
| Tab 2 — Action items | M | 300 | Filter UX + detail panel |
| Tab 3 — Decisions | M | 250 | Three-table merge at presentation |
| Tab 4 — Risks | S | 100 | None — small dataset |
| Tab 5 — Trading | L | 600 | Largest scope; consolidates 6 pages with deduplication |
| Tab 6 — Documents | S | 80 | None — filesystem walk |
| Shared utilities (`dashboard/utils.py`, status header component) | — | 150 | Affects every tab; build first |
| **Total** | | **~1,680** | vs. current 7,639 → **−5,960 lines (78% reduction)** |

**Estimated wall-clock time:** 2.5–3.5 hours of focused implementation, sequentially per playbook section 3.2 ordering (Tab 1 → 2 → 3 → 4 → 5 → 6, then deletion).

**Code organisation:**
- Keep current `dashboard/pages/` structure; replace files 1:1 with new content (delete old, write new) to make rollback by `git revert` clean.
- Numerical-prefix renaming so the new structure renders in order: `1_أين_نحن.py` (or `01_status.py`), `2_بنود_التنفيذ.py`, etc. Keep Arabic file names per existing convention.
- Move shared widgets to `dashboard/utils.py` (top status strip, KPI ribbon, action item card, risk card).
- `dashboard/app.py` stays as the entry point + sidebar.

---

## 7. Per-playbook checklist for Phase 3 (when Checkpoint 2 clears)

- [ ] Build Tab 1 first (lowest risk, validates the design)
- [ ] Stage as separate commit per tab ("Dashboard: Tab 1 — Where are we?", etc.)
- [ ] After all 6 new tabs ship and verify, delete old pages in **one** commit ("Dashboard: remove deprecated pages (post-redesign)")
- [ ] Update `dashboard/README.md` (or create it — currently absent) explaining the 6-tab structure and how to add a new action item / risk / decision so it appears correctly
- [ ] Capture screenshots → `docs/meetings/2026_05_01_dashboard_v2_screenshots/` (you'll do this; I can't from CLI)
- [ ] Click-through every tab, confirm load times < 3 s, links work

---

## 8. What I want from you before Phase 3

The proposal above is the playbook's defaults applied to the audit's findings. Before I build:

1. **Tab 6 — keep or drop?** The playbook calls it optional. With 23 research docs and 3 meeting docs, an index is useful — but it's also a "nice to have". Defer or include?
2. **Page 6 (`6_الذكاء_الاصطناعي.py`) ML model views**: keep as Tab 5 inner sub-section, or move entirely to a markdown report? It's currently 371 lines and shows walk-forward + feature importance + ROC — research-y data that updates only when ML retrains. My recommendation: **link** from Tab 5 to a research doc; do not embed in dashboard.
3. **Tab 5 inner section count**: the current proposal has 5 inner sections (Live / Analytics / Trade log / Signals & Shadow / optional ML). Five inner tabs inside one outer tab is a lot. Acceptable trade-off vs. a 7th outer tab? My recommendation: yes — outer tab count matters more for navigation (Principle 6 readability); inner sections are fine.
4. **File naming**: keep Arabic filenames (`1_أين_نحن.py`) per existing convention, or switch to ASCII (`1_status.py`) for portability? Current convention is Arabic.
5. **Override anything in the migration map?** Specifically: any of the DELETE candidates you'd rather archive instead of delete?

After your edits / approval, I move to Phase 3 implementation.

---

## Cross-references

- `docs/research/dashboard_audit_2026_05_01.md` — Phase 1 discovery
- `docs/p.md` — playbook
- `dashboard/pages/13_Project_Tracker.py` — largest current consolidation target
- `data/improvements.db` schema — `improvements.db::sqlite_master`
