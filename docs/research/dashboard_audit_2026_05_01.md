# Dashboard Audit — 2026-05-01

**Date prepared:** 2026-05-01
**Author:** automated audit (Claude Code), per `docs/p.md` Phase 1
**Scope:** READ-ONLY discovery. No code or data modified.
**Output for:** Checkpoint 1 review before redesign proposal (Phase 2).

## Executive summary (3 bullets)

- **17 navigation surfaces, ~70 widgets, ~7,639 lines** across `dashboard/app.py` + 16 pages. The single page `13_Project_Tracker.py` is **1,734 lines with 9 internal tabs** — a sub-dashboard inside the dashboard.
- **Action items, risks, decisions, and phase progress are duplicated across 4 surfaces each on average**. Same rows of `action_items` appear in the home page's Next Actions widget, the Project Tracker's Improvements tab, the Project Tracker's Phase 8/9 blocker widgets, AND the Meeting Outcomes page's blockers section. The user's complaint ("improvements scattered") is empirically grounded.
- **Three classes of dead surface**: (a) historical event pages whose value expired (Meeting Outcomes for the 2026-04-28 meeting), (b) feature pages duplicating CLI workflows (Backtest UI, Signal Scanner manual mode), (c) legacy table surfaces (the inner Improvements tab reads a `improvements` table that is separate from and effectively replaced by `action_items`).

## 1.1 Tab inventory

### Top-level pages

| # | File | Purpose (1 sentence) | Data source(s) | Widget count |
|---|---|---|---|---|
| Home | `app.py` | Trading KPIs + Next Actions + meeting/version banners | `improvements.db`, `trading.db` | 7 |
| 1 | `1_الماسح.py` | Manual signal scanner with chart | `trading.db.signal_logs` | 3 |
| 2 | `2_الصفقات.py` | Open trades + interactive chart + close calc | `trading.db.trades` | 3 |
| 3 | `3_السجل.py` | Closed trades log + exit reason analysis | `trading.db.trades, trade_results` | 2 |
| 4 | `4_الاشارات.py` | All-signals log + ML filter effect | `trading.db.signal_logs` | 2 |
| 5 | `5_التحليلات.py` | Equity, drawdown, monthly, per-pair, advanced ratios | `trading.db.trade_results, account_snapshots` | 7 |
| 6 | `6_الذكاء_الاصطناعي.py` | LightGBM walk-forward + feature importance + ROC | files (`models/`), `trading.db.trade_results` | 7 |
| 7 | `7_الاختبار.py` | Backtest UI (parameter sweep, results table) | `scripts/run_backtest_all.py` invocation, `data/backtest_results.db` | 4 |
| 8 | `8_الأخبار.py` | Economic calendar + news filter activity + impacted trades | `trading.db.news_events, signal_logs` | 5 |
| 9 | `9_Chat.py` | Generic trading chat assistant | mixed | 1 |
| 10 | `10_Trade_Chart.py` | Single-trade candlestick visualisation | `trading.db.trades, ohlcv_bars` | 4 |
| 11 | `11_التقارير.py` | Daily reports + Telegram export | `trading.db` (multiple) | 7 |
| 12 | `12_الاتصال.py` | MT5 connection status + error log analysis | `data/logs/*` | 5 |
| 13 | `13_Project_Tracker.py` | 9-tab project tracker (see breakdown below) | `improvements.db` + `trading.db` | 9 inner tabs · ~30 sub-widgets |
| 14 | `14_v4_Crypto_Status.py` | v4 Phase 10 crypto research artefacts | `improvements.db.tsmom_runs, project_phases, phase_steps, go_no_go_decisions` | 9 |
| 15 | `15_Meeting_Outcomes.py` | 2026-04-28 v3 go/no-go meeting page (4 widgets) | `improvements.db.go_no_go_decisions, project_phases, action_items, risks_register` | 5 |

### Project Tracker (page 13) — 9 internal tabs

| Inner tab | Purpose | Data source |
|---|---|---|
| 📊 المراحل (Phases) | Phase status with step lists; decisions per phase | `project_phases`, `phase_steps`, `go_no_go_decisions` |
| ⚡ حالة النظام (System state) | Live engine state, account, top strategies | `trading.db.account_snapshots, trade_results`; `improvements.db.system_state` |
| 📈 راقب الأداء (Performance monitor) | Per-version performance, weekly perf, Monte Carlo | `trading.db.trade_results` |
| 📦 تقسيم البيانات (Data segmentation) | v1/v2/v3 segment trade counts, regime distribution | `improvements.db.data_segmentation_log` + `trading.db.trade_results` |
| 🎯 تحليل الأنظمة (Regime analysis) | Regime × strategy matrix, expectancy per regime | `trading.db.regime_logs`, `improvements.db.expectancy_analysis` |
| 🧠 Meta-Labeler | Meta-labeler runs + TSMOM runs | `improvements.db.meta_labeler_runs, tsmom_runs` |
| 📝 سجل القرارات (Decisions) | go_no_go_decisions + decision_inputs + legacy decisions_log | `improvements.db` (3 tables) |
| 🔧 التحسينات (Improvements) | action_items + risks_register + legacy improvements table | `improvements.db.action_items, risks_register, improvements` |
| 👁 التداول الظلي (Shadow) | Shadow signal log + filter activity | `trading.db.shadow_signals` |

## 1.2 Duplication map

| Concept | Appears in tabs | How they differ |
|---|---|---|
| **`action_items` rows** | 1. Home page (`app.py`) Next Actions widget · 2. Project Tracker → Improvements tab (full table) · 3. Project Tracker → Phase 8 blockers countdown widget · 4. Project Tracker → Phase 9 blockers countdown widget · 5. Meeting Outcomes → Phase 8 blockers section · 6. Meeting Outcomes → Meeting-emergent action items section | Same DB rows. Home shows top 6 (BLOCKING-ranked); tracker Improvements tab shows all with category filter; Phase 8/9 widgets count by `blocking_phase`; Meeting Outcomes filters by `source LIKE 'meeting_%'` and by `blocking_phase=8`. **Five different filter views of one table.** |
| **`risks_register` rows** | 1. Project Tracker → Improvements tab (joined render) · 2. Meeting Outcomes → External-review risks widget | Same 4 rows shown twice. Meeting Outcomes filters by `source LIKE '%external_review%'` (which is all 4 rows); tracker shows them ungrouped. |
| **`go_no_go_decisions` rows** | 1. Home page meeting banner (latest meeting count) · 2. Sidebar v3/v4 status pill · 3. Project Tracker → Phases tab (latest 3 decisions) · 4. Project Tracker → Decisions tab (all decisions) · 5. v4 Crypto Status → Phase 10 verdict · 6. Meeting Outcomes → Vote outcomes widget | Six surfaces of 11 DB rows. Same data filtered or aggregated 6 different ways. |
| **`project_phases` status** | 1. Home page sidebar v3/v4 status pill · 2. Project Tracker → Phases tab · 3. v4 Crypto Status (phase 10/10.5 only) · 4. Meeting Outcomes → Phase timeline (phases 5–9 only) | Same 16 rows windowed 4 different ways. |
| **`phase_steps`** | 1. Home page Next Actions widget · 2. Project Tracker → Phases tab · 3. v4 Crypto Status (phase 10/10.5 only) | Three filter views of 87 rows. |
| **`tsmom_runs`** | 1. Project Tracker → Meta-Labeler tab · 2. v4 Crypto Status → IS vs OOS widget · 3. v4 Crypto Status → Equity curves widget | Same 22 rows, 3 different presentations. |
| **`improvements` (legacy IMP-* table)** | 1. Project Tracker → Improvements tab (separate from `action_items` in same tab) | Single surface — but coexists in the same tab with `action_items`, contributing to the user's confusion that "improvements" and "action items" are different concepts. They are different DB tables but represent the same logical idea: things-to-do. |
| **`decisions_log` (legacy)** | 1. Project Tracker → Decisions tab (bottom widget) | Single surface, but coexists with `go_no_go_decisions` (formal verdicts) and `decision_inputs` (review inputs) in the same tab — three "decisions" tables in one screen. |
| **Trade-data views** | 6 separate pages (2, 3, 4, 5, 10, 11) | Different angles on the same `trades` / `trade_results` / `signal_logs` tables. Some redundancy: Trade Chart (10) is a per-trade view of what's already in Open/Closed Trades pages. |

**Bottom line:** the user's claim that "improvements appear in multiple places and there's no clear sense of where am I" is conservative — `action_items` rows specifically appear in **6 places**.

## 1.3 Dead / stale surfaces

| Surface | Status | Reason |
|---|---|---|
| `9_Chat.py` (Trading Chat) | LIKELY DEAD | 316 lines of generic chat shell with no clear DB-tied workflow. Project conversations happen in `claude.ai` per CLAUDE.md, not the dashboard. |
| `7_الاختبار.py` (Backtest UI) | DUPLICATES CLI | Backtests run via `python scripts/run_backtest_all.py` per CLAUDE.md commands. The Streamlit UI wrapping the same operation is unused in production workflow. |
| `1_الماسح.py` (Signal Scanner manual) | LIKELY DEAD | The engine auto-scans hourly. Manual scan is rarely needed; if needed, `scripts/run_engine.py` is the documented path. |
| `15_Meeting_Outcomes.py` | EXPIRED | Built for 2026-04-28 meeting specifically. After meeting closure, content is historical and duplicates Project Tracker (votes, blockers, risks all live in `action_items` / `go_no_go_decisions` / `risks_register` already surfaced elsewhere). |
| `14_v4_Crypto_Status.py` | EXPIRED | v4 Phase 10 was REJECTED on 2026-04-22 per `project_phases.status='COMPLETED'` with REJECTED verdict. Page is now a historical artefact, not active monitoring. |
| Project Tracker → Improvements tab → legacy `improvements` table | LEGACY | 76 rows in a separate table from `action_items`. The user perceives them as one concept; the schema treats them as two. Recommendation: archive the `improvements` table on the dashboard side; keep DB rows for history but stop surfacing. |
| Project Tracker → Decisions tab → legacy `decisions_log` table | LEGACY | 40 rows of an older decision-recording schema. Superseded by `go_no_go_decisions` (11 rows, 2026-04 onwards). |

## 1.4 Database surfaces — what's currently surfaced vs not

### Surfaced

| Table | Rows | Where |
|---|---:|---|
| `action_items` | 34 | 6 surfaces (see duplication map) |
| `risks_register` | 4 | 2 surfaces |
| `go_no_go_decisions` | 11 | 6 surfaces |
| `decision_inputs` | 1 | 1 surface (Project Tracker → Decisions tab) |
| `project_phases` | 16 | 4 surfaces |
| `phase_steps` | 87 | 3 surfaces |
| `decisions_log` (legacy) | 40 | 1 surface |
| `tsmom_runs` | 22 | 3 surfaces |
| `meta_labeler_runs` | 9 | 1 surface |
| `expectancy_analysis` | 62 | 1 surface |
| `system_state` | 31 | 1 surface |
| `data_segmentation_log` | 3 | 1 surface |
| `improvements` (legacy) | 76 | 1 surface (recommend retiring) |

### Not surfaced (data exists in `improvements.db`, no dashboard view)

| Table | Rows | Notes |
|---|---:|---|
| `implementation_log` | 10 | Free-text implementation notes — possibly useful as a "what was actually shipped" log |
| `status_history` | 34 | Historical status transitions of action items / phases — useful for "what changed this week" |

### Conceptual gaps (data exists, but the relevant question isn't asked anywhere)

| Question the dashboard doesn't answer | Why it matters now |
|---|---|
| "What's blocking Phase 7?" (the next phase the project enters May 4) | Dashboard has Phase 8 and Phase 9 blocker widgets — both later phases — but no Phase 7 widget. Yesterday's session added 2 Phase 7 BLOCKING items (AI-017b, AI-020); they're invisible on the home page and Project Tracker overview. |
| "Where is realized_rr / R-PF / $-PF for ml_direct right now?" | Phase 7 ship gate is defined as R-PF ≥ 1.3 AND $-PF ≥ 1.0 (per `phase7_ship_gate_definition.md`). Dashboard's analytics page (5) shows PF but not the dual-gate semantics. |
| "Is the engine config drifting from disk?" | AI-004 (config drift) is deployed and logs at startup + periodically. Dashboard does not surface the most recent `[CONFIG]` line from `paper_trading.log`. |
| "What's the SL_HIT mislabel rate (AI-017b)?" | New finding 2026-05-01. Affects 27% of v3 SL_HIT trades. Visible in the trade log (3) only by manual computation, not as a metric. |
| "What docs/research artefacts exist for current phase?" | 30+ markdown docs under `docs/research/` and `docs/meetings/`. No index from the dashboard; users must browse the filesystem. |

## 1.5 Convolution check (Rule 9)

The dashboard codebase IS convoluted (16 pages + 9 inner tabs, ~7,639 lines, multiple data-source-of-truth violations) but **not so convoluted that incremental refactor is harder than rewrite**:

- Framework is consistent throughout (Streamlit + pandas + sqlite3). No mixed React/Flask/etc. complications.
- Schema has stabilised in the last 6 weeks. ORM models in `storage/database.py` are drift-clean as of AI-002 (2026-04-28).
- The ~30 widgets in Project Tracker are mostly self-contained `st.subheader` blocks; each can be extracted to its own file in a single edit.
- Cached data fetches use `@st.cache_data(ttl=...)` consistently — no shared mutable state to worry about.

**Recommendation: refactor incrementally.** Specifically: (a) replace the 9-tab Project Tracker with a single "Action Items" tab + a single "Decisions" tab + a single "Risks" tab plus moving phase-progress to a Status Overview tab; (b) keep the analytics pages (3, 5, 10, 11) largely as-is — they're per-trade views and the duplication is mostly across project-tracker-style tables, not across analytics; (c) delete or archive `9_Chat`, `7_الاختبار`, `1_الماسح`, `15_Meeting_Outcomes`, `14_v4_Crypto_Status` (or fold the latter two into a "Documents/historical" tab).

If during Phase 3 implementation the Project Tracker breakup turns out to require >2x effort vs the estimate, surface that and reconsider.

## Summary of findings (for Checkpoint 1)

1. **Duplication is the primary cause of confusion.** `action_items` appears in 6 places, `go_no_go_decisions` in 6 places, `project_phases` in 4 places. Single-source-of-truth (Principle 1 in the playbook) is the most impactful change.
2. **The user's perceived overlap between "improvements" / "action items" / "blockers" / "risks" maps to four DB tables** — `improvements` (legacy, 76 rows), `action_items` (live, 34 rows), the BLOCKING-category subset of `action_items` (22 rows), and `risks_register` (4 rows). Three of the four can be unified at the presentation layer; the legacy `improvements` table can be archived from the dashboard.
3. **5 surfaces are dead or expiring** (Chat, Backtest UI, Signal Scanner, Meeting Outcomes, v4 Crypto Status). Removing them drops the surface count from 17 → 12, halves the navigation cost.
4. **Project Tracker (page 13) needs decomposition.** 1,734 lines and 9 inner tabs is the largest single point of duplication and the place users get lost. Each inner tab is a separable concern.
5. **Two Phase-7-relevant gaps:** no Phase 7 blocker widget, no surface for realized_rr / dual-gate PF status. With Phase 7 starting May 4, these are now load-bearing for visibility.

## Cross-references

- Code source: `dashboard/app.py`, `dashboard/pages/*.py`, `dashboard/utils/db.py`, `dashboard/components/*.py`
- Database: `data/improvements.db` (15 tables), `data/trading.db` (18 tables)
- Project context: `CLAUDE.md`, recent `docs/research/*.md`
- For Phase 2 of this redesign: `dashboard_redesign_proposal.md` (to be written after Checkpoint 1 approval)
