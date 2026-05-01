# ForexAI Dashboard

Streamlit dashboard for project status, action items, decisions, risks, and trading state.

## Run locally

```bash
cd d:/forexAI
venv/Scripts/activate
streamlit run dashboard/app.py
```

Default URL: `http://localhost:8501`.

## Structure (6 surfaces)

The dashboard has six top-level tabs. Each answers exactly one question. Project policy: **filesystem English-only, UI Arabic**.

| # | Surface | File | Question it answers |
|---|---|---|---|
| 1 | Where are we? / أين نحن؟ | `app.py` (home) | What's the project's current state and what should I be working on right now? |
| 2 | Action Items / بنود التنفيذ | `pages/1_action_items.py` | What's blocking us, and who owns each item? |
| 3 | Decisions / القرارات | `pages/2_decisions.py` | What did we decide and why? |
| 4 | Risks / المخاطر | `pages/3_risks.py` | What could go wrong, and what are we doing about it? |
| 5 | Trading / التداول | `pages/4_trading.py` | How is the live engine doing — state, P&L, signals, analytics? |
| 6 | Documents / الوثائق | `pages/5_documents.py` | Where's the report or research doc on X? |

## Single source of truth

Every concept lives in exactly one tab. Other tabs may **link** but never **duplicate**:

| Concept | Primary tab | Other appearances |
|---|---|---|
| `action_items` rows | Tab 2 | Tab 1 shows top 5 with link to Tab 2 |
| `go_no_go_decisions` | Tab 3 | Tab 1 shows last 3 with link to Tab 3 |
| `project_phases` | Tab 1 | — |
| `risks_register` | Tab 4 | — |
| Trading data (`trades`, `trade_results`, `signal_logs`) | Tab 5 | — |

## Data sources

| File | Source |
|---|---|
| `app.py` (Tab 1) | `improvements.db` (project_phases, action_items, go_no_go_decisions); `data/logs/paper_trading.log` (engine state); MT5 connection |
| `pages/1_action_items.py` | `improvements.db.action_items`, `status_history` |
| `pages/2_decisions.py` | `improvements.db.go_no_go_decisions, decision_inputs, decisions_log` (legacy) |
| `pages/3_risks.py` | `improvements.db.risks_register, action_items` (status linkage) |
| `pages/4_trading.py` | `trading.db` (trades, trade_results, signal_logs, account_snapshots, news_events, ohlcv_bars, shadow_signals); `analysis.rr_calculator.phase7_ship_gate` for the dual-gate metric |
| `pages/5_documents.py` | Filesystem walk of `docs/research/` and `docs/meetings/` |

## Shared utilities

| Module | Purpose |
|---|---|
| `dashboard/utils/layout.py` | `status_header()` (top strip on every page) + `page_intro()` |
| `dashboard/utils/db.py` | DB query helpers (equity curve, signal log, trade results, etc.) |
| `dashboard/utils/mt5_helper.py` | Live MT5 connection state |
| `dashboard/components/charts.py` | Plotly chart builders (equity curve, drawdown, candlestick, etc.) |
| `dashboard/components/metrics.py` | Metric formatters |

## How to add data so it appears in the dashboard

### Adding a new action item

```sql
-- Connect to data/improvements.db
INSERT INTO action_items
  (action_id, category, title, description, blocking_phase, status, created_date, source)
VALUES
  ('AI-021', 'BLOCKING', 'Short title', 'Full description ...', 7, 'OPEN',
   '2026-05-01', 'meeting_or_doc_reference');
```

Categories: `BLOCKING`, `DOCS`, `MONITORING`, `SHADOW`, `POST_MEETING`.
Statuses: `OPEN`, `IN_PROGRESS`, `DONE`.
Phase: integer matching `project_phases.phase_number`, or NULL.

The new item appears in Tab 2 immediately on cache refresh (TTL 60s) or click of "تحديث البيانات" button. If `category='BLOCKING'` and `status` is OPEN/IN_PROGRESS, it may appear in Tab 1's top-5 panel ranked by `blocking_phase ASC` then `created_date DESC`.

### Adding a new risk

```sql
INSERT INTO risks_register
  (risk_id, title, description, severity, likelihood, mitigation, status,
   identified_date, source)
VALUES
  ('R-EXT-005', 'Title', 'Full description ...',
   'HIGH', 'MEDIUM',
   'Mitigation text — reference action items by ID like AI-021 to enable status colouring',
   'OPEN', '2026-05-01', 'source_doc');
```

Severities: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`.
Likelihoods: `HIGH`, `MEDIUM`, `LOW`.
The mitigation text is parsed for `AI-*`, `GAP-*`, `R-EXT-*` tokens and the matching action item's status colour is rendered automatically.

### Adding a new decision

```sql
INSERT INTO go_no_go_decisions
  (phase_number, decision_date, verdict, gates_passed, gates_total,
   rationale_en, rationale_ar, decided_by, next_action)
VALUES
  (8, '2026-06-01', 'GREEN', 5, 5,
   'English rationale ...', 'سبب القرار ...',
   'gate_review_2026_06_01',
   'Begin Phase 8 paper trading window');
```

Verdicts: `GREEN`, `YELLOW`, `RED`.

## Design principles

1. **Single source of truth.** Every concept lives in exactly one tab.
2. **Tabs answer questions.** The tab name is the question in plain language.
3. **Status before detail.** Every tab opens with a 3–7 number summary, then drill-down. Never start with a 50-row table.
4. **Filter, don't fragment.** One "blockers" view with a phase filter — not three Phase-7/Phase-8/Phase-9 widgets.
5. **Time-aware.** Top status strip shows current phase, days to gate, engine state with last-activity age.
6. **Filesystem English, UI Arabic.** No script-mixing within a single label.

## History

| Date | Change |
|---|---|
| 2026-05-01 | Major redesign: 17 surfaces (~7,639 lines) reduced to 6 surfaces (~1,933 lines). See `docs/research/dashboard_audit_2026_05_01.md` and `docs/research/dashboard_redesign_proposal.md`. |
