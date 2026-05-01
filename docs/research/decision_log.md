# Decision Log

Running log of every formal go/no-go and architectural decision. Each entry matches one row in `improvements.db::go_no_go_decisions` where applicable.

Format:
```
## YYYY-MM-DD — Phase N — VERDICT (gates_passed/gates_total)
**Decided by:** ...
**Rationale:** ...
**Next action:** ...
**Artifacts:** ...
```

---

## 2026-04-28 (post-meeting execution, 21:55 UTC) — AI-002 deployed

**Executed:** AI-002a, AI-002b, AI-002c per meeting votes 4, 5, 6.

**Code changes:**
- `scripts/paper_trade.py` L128-134: `bollinger_bounce` registration commented out with retirement annotation referencing Vote 4 (n=25, PF=0.26, R:R=0.12).
- `scripts/paper_trade.py` L163-177: `ml_filtered_sma` registration commented out with retirement annotation referencing Vote 5 (n=22, PF=0.23, R:R=0.11).

**Config changes:**
- `config/paper.yaml`: NEW `strategy_blacklist:` section installed between `risk:` and `session_filter:` — 2 entries (`ml_direct/XAUUSD`, `ml_filtered_sma/XAUUSD`) per Vote 6 Option D.
- `config/base.yaml`: stale "Lost $30K+ shorting gold in uptrend" comment replaced with parity-mandate comment; entry `reason` text updated to match `paper.yaml` exactly.

**Verification:**
- YAML parse: ✅
- Config parity (paper.yaml ↔ base.yaml on (strategy, symbol) AND reason text): ✅
- `paper_trade.py` AST parse: ✅
- Engine graceful restart: ✅ at 21:55:05 UTC. Old PIDs (3316, 3320, 3496, 13324) terminated; new PIDs (3780, 12320, 13012, 13532) auto-spawned by the existing `start.bat` infinite-restart wrapper.
- Scan #1 at 21:55:07: clean, 0 errors in first 60s.
- Active strategies post-restart: `asia_breakout`, `ml_direct`, `sma_crossover`, `rsi_reversal`, `macd_crossover`, `stop_hunt_reversal` (6 strategies × 7 instruments = 42 registrations). `bollinger_bounce` and `ml_filtered_sma` confirmed ABSENT.
- Blacklist enforcement: awaits first ml_direct/XAUUSD signal attempt post-restart (visible in dashboard recent-signals widget within 1-2 hours). Existing 2 open positions (USDCAD SELL, XAUUSD SELL) grandfathered — blacklist gates new entries only.

**Pre-execution backups:**
- `D:/forexAI/backups/trading.db.bak.pre-ai002.20260428-205506` (150 MB)
- `D:/forexAI/backups/paper.yaml.bak.pre-ai002.20260428-205506` (1.8 KB)
- `D:/forexAI/backups/base.yaml.bak.pre-ai002.20260428-205506` (2.7 KB)
- `D:/forexAI/data/improvements.db.bak.2026-04-28-postmeeting` (188 KB)

**Schema patch:** `improvements.db::action_items` extended with two nullable columns (`completed_date TEXT`, `notes TEXT`) to satisfy the spec's UPDATE SQL. Additive change; no existing rows affected.

**Phase 8 blocker progress:** **2 of 5 cleared** — AI-002 (this task) + the implicit retirement of pathological strategies before Phase 7 training-set freeze.

**Remaining Phase 8 blockers:**
- AI-001 — XAUUSD zero-BUY structural fix (engineering, ~4-5 weeks)
- AI-003 — Alembic migration system + CI schema-drift guard (engineering, ~3 hours)
- AI-005 — 30% holdout OOS validation of R1-R7 (analytics, ~1 day)
- AI-006 + AI-007 — OVERLAP filter shadow-mode validation with ATR control (May 4 - May 25)

**Notes for follow-up (per spec rule #8 — references not modified):**
- `scripts/health_check.py` imports `BollingerBounceStrategy`
- `scripts/run_backtest_all.py` imports both retired classes (backtest harness only, not live)
- `engine/trading_engine.py:1159` strategy ID mapping `"bollinger_bounce": 3`
- `scripts/init_improvements_db.py:328` references retired strategy filenames in metadata

These are documentation/tooling references, not active rotation. Will be addressed in AI-017 (R:R audit) or routine cleanup, not in this AI-002 scope.

---

## 2026-04-28 — v3 Go/No-Go Meeting — 8 votes decided (post-external-review)

**Context:** Meeting held after external skeptical review (synthesis at `docs/research/external_review_2026_04_28.md`). Reviewer's framing accepted: project state is "structurally one-sided system funded by an incidental window of bias × falling gold" — methodological discipline applied to v4 now extended to v3.

**Vote outcomes (7 of 8 align with reviewer's recommended position):**

| # | Question | Decision | Direction vs reviewer rec |
|---|---|---|---|
| 6 | Blacklist mismatch resolution | **Option D** — block ml_direct/XAUUSD in BOTH configs until zero-BUY resolved | aligned |
| 1 | Phase 5 → Phase 6/7 transition | **YES, May 4** | aligned |
| 7 | Zero-BUY investigation status | **BLOCKING for Phase 8** | aligned |
| 4 | Retire `bollinger_bounce` | **Retire entirely, before Phase 7** | aligned |
| 5 | Retire `ml_filtered_sma` | **Retire entirely, before Phase 7** | aligned + emergent finding |
| 3 | Block XAUUSD OVERLAP session | **Shadow-mode 14d first** (no paper.yaml install yet) | aligned |
| 2 | Phase 8 paper-trading start | **DEFERRED, June 1 gate review** | aligned |
| 8 | Phase 9 hosting | **Decide local now** + AI-018 watchdog mitigation | DEVIATION (briefing+reviewer said defer) |

**Emergent findings the meeting added:**
- **AI-017** — high-WR / low-R:R pathology pattern across two retired strategies (bollinger_bounce R:R 0.12, ml_filtered_sma R:R 0.11) suggests possible system-wide TP/SL design tendency, not strategy-specific bugs. Audit remaining strategies before Phase 7.
- **AI-018** — snapshot-gap operational issue (9.2h, 6.2h gaps in last 14 days) addressable via boot-on-startup config + auto-restart watchdog rather than VPS migration. Re-evaluation in July (AI-019) conditional on Phase 8 GREEN.

**Phase status post-meeting:**
- Phase 5 → **COMPLETED** 2026-04-28 (transitioning May 4)
- Phase 6 (TSMOM Layer) → **IN_PROGRESS**, started 2026-05-04
- Phase 7 (Meta-Labeler Rebuild) → **IN_PROGRESS**, started 2026-05-04
- Phase 8 (v3.0 Paper Trading) → **DEFERRED**, gate review 2026-06-01 (5 blockers open)
- Phase 9 (Live trading) → unchanged target Sep 1+, hosting locked to local Windows + watchdog
- Phase 10 (v4 research) → CLOSED 2026-04-22 (v4 crypto rejected)

**Five Phase 8 blockers (must all clear at 2026-06-01 gate):**
1. **AI-001** — XAUUSD zero-BUY structural fix (engineering)
2. **AI-002** — three retirements/blocks merged (`bollinger_bounce` + `ml_filtered_sma` retired, `ml_direct/XAUUSD` blocked in both configs)
3. **AI-003** — Alembic migration system + CI schema-drift guard (engineering)
4. **AI-005** — 30% holdout OOS validation of R1-R7 on existing v3 trades (analytics)
5. **AI-006 + AI-007** — OVERLAP filter shadow-validated with ATR control, n≥20 new trades (engineering)

**Institutional discipline established by this meeting:**
- Method standard from v4 now applies to v3 (blocked ml_direct/XAUUSD on principle, set aside +$21k of P&L)
- Capability gates over calendar gates (Phase 8 deferred until five blockers clear; "indefinitely deferred" is acceptable)
- Validation discipline (OVERLAP filter goes shadow-only until n≥20 fresh data + ATR control)

**Artifacts:**
- `docs/research/external_review_2026_04_28.md` — synthesis (~20 KB)
- `docs/meetings/2026_04_28_external_review_summary.md` — 1-pager (~4 KB)
- `improvements.db::go_no_go_decisions` — 8 new rows (`decided_by='meeting_2026_04_28'`)
- `improvements.db::action_items` — 18 total (AI-001 through AI-018)
- `improvements.db::risks_register` — 4 rows (R-EXT-001 through R-EXT-004)
- `improvements.db::decision_inputs` — 1 row (external review)
- `improvements.db::project_phases` — Phase 5 closed, 6/7 started, 8 DEFERRED
- `data/improvements.db.bak.2026-04-28-postmeeting` — DB backup

---

## 2026-04-24 — Comprehensive trade evolution analysis (281 trades / v1+v2+v3)

**Analysis scope:** 281 trades across 3 versions (v1=132, v2=46, v3=103), 10 charts, 8 pivoted CSVs, Wilson-score CIs + binomial/Fisher p-values on every pattern claim. Full report at `docs/research/full_trade_evolution_report.md`. Prepared for 2026-04-28 v3 go/no-go meeting.

**Headline numbers:**
- v1: +$18,637 (oversized lots, context-only)
- v2: −$26,472 (construction zone, not valid for evaluation)
- v3: **+$10,810** (authoritative — driven almost entirely by XAUUSD SELL +$13,327)
- cumulative: +$2,976 from $100k start over 37 days

**Top 3 meeting recommendations (§10 of report):**
1. **R1** — Block XAUUSD SELL in OVERLAP session (13:00-17:00 UTC). Fisher p=0.006. Expected effect: +$16k recovery on same-window sample.
2. **R2** — Retire or restructure `bollinger_bounce` (72% WR but losing due to R:R 0.26).
3. **R3** — Investigate config-vs-reality mismatch: segmentation_log says "XAUUSD ML blacklisted" but 60 ML Direct SELLs ran in v3.

**Top 5 UNEXPECTED findings** (the user requested these — patterns not anticipated before analysis):
1. `bollinger_bounce` wins 13 of 18 trades (72% WR) and still loses money — R:R 0.26 is a structural pathology.
2. **Zero XAUUSD BUY trades across ALL 3 versions** (all 105 XAUUSD trades are SELL). Persistent system-wide asymmetry, not a recent drift.
3. v3 RISK_REJECTED count collapsed to 50 (vs 236 in v1, 74 in v2) — filters are 5× more permissive. Consistent with "demo mode" but concerning.
4. v3 is a **single-symbol system**: without XAUUSD, v3 net PnL would be **−$2,517**. Every FX pair in v3 is net negative.
5. **Worst-10 AND best-10 v3 trades are the SAME**: XAUUSD SELL ml_direct. The strategy owns both tails — highest variance in the portfolio.

**Caveats:** 14 of the non-XAUUSD per-symbol per-direction cells are UNDERPOWERED (n<10) — no per-symbol decisions defensible outside XAUUSD. Additional latent schema-drift bug surfaced: `trade_results.h1_trend/h4_trend/volatility_regime` all NULL since v2.4 — third instance of the same bug family after shadow_signals.data_group and the snapshot-gap investigation's latent finds.

---

## 2026-04-22 — Phase 10 — RED FINAL (v4 crypto momentum REJECTED)

**Decided by:** Phase 10.5 null-result run + user scope-lockdown policy

**Change:** Phase 10.5 rescue attempt ran the approved regime filter (80th-pct 4-week basket vol, training-snapshot threshold, LO/12w only). The filter fired 67/361 training weeks (18.6%, near 20% target — correctly calibrated on training data) but **0/69 OOS weeks**. Gated OOS Sharpe 0.553 is identical to ungated OOS Sharpe 0.553 — the filter never engaged because 2025-2026 was a low-vol downtrend, not the high-vol chop regime the filter was designed to address.

**Gate scoreboard:** 3/5 pass (Sharpe ≥ 0.4, MaxDD ≤ 25%, beats BH BTC) — 2/5 fail (drift stability, gated > ungated).

**Scope lockdown honored:** per `regime_filter_spec.md` §7, no iteration on the filter is permitted. One filter, one knob, one evaluation. Null result means reject.

**v4 crypto momentum: REJECTED.** Phase 10 closed. Phase 10.5 closed.

**Next action:** Pivot Phase 10 to a different research track. Candidates per `v4_framework.md` Shift 2 (Underexploited Niches): commodity futures trend, crypto basis/funding arbitrage, volatility selling (defined risk). Phase 11 (Strategy Expansion) remains NOT_STARTED pending new track selection. User's decision.

**Note for 2026-04-28 meeting:** Do NOT cite "v3 break-even" as a v3.0 signal. v3 PnL swung from −$17,929 to −$615 in 24 hours purely from two TP hits on open positions (tickets 56314551827 +$2,495 and 56315435636 +$3,466). 88 closed trades is small-sample variance, not improvement.

**Artifacts:** `docs/research/regime_filter_results.md`, `docs/research/regime_filter_equity.png`, `data/research/tsmom_crypto_gated_metrics.csv`, `improvements.db::go_no_go_decisions` (id=3, verdict RED).

---

## 2026-04-22 — Shadow-signals pipeline incident (RESOLVED)

**Root cause:** schema drift. Commit `524131e` (2026-04-16 18:44 UTC) added `data_group="STABLE"` kwarg to `ShadowSignal(...)` constructor. The `ShadowSignal` ORM model did not declare `data_group` — that column was added to the SQLite table on 2026-04-14 via raw `ALTER TABLE` in `segment_data.py`, never reflected in the model. Silent TypeError swallowed by try/except at `engine/shadow_tracker.py:119-126`. 73 errors across 6 days. ~200 shadow rows lost (unrecoverable).

**Blast radius:** Phase 7 Meta-Labeler + Phase 8 Paper Trading (both depend on shadow data as v3.0 training oracle). 2026-04-28 go/no-go meeting cannot confirm Phase 5 step 3 GREEN without the fix.

**Resolution:** fix applied to `storage/database.py` (1-line Column declaration), engine restarted 2026-04-22, verification confirmed writes resumed at **2026-04-22 15:52:09 UTC**. Post-restart state: `total=238 rows (+2), stable=111 (+2), last_ts=2026-04-22 15:52:09.810501`. Zero "Shadow tracker log failed" errors in post-restart log. **Shadow pipeline officially restored.**

**Follow-up cleanup applied (Task A):** 3-line latent-drift cleanup on `Trade` and `TradeResult` models (`data_group` + `detected_regime` Column declarations). All 6 ORM models now drift-clean vs live DB — no loaded guns remaining.

**Artifacts:** `docs/research/shadow_signals_incident.md` (with resolution log), `docs/research/snapshot_gaps_incident.md`, `storage/database.py` (modified with 4 new Column lines total), `improvements.db::phase_steps` (Phase 5 step 3 now effectively GREEN after today's restoration).

---

## 2026-04-22 — Snapshot-gaps investigation

**Hypothesis (user-posed):** same schema-drift family as shadow incident. **Result: FALSIFIED.**

Both snapshot gaps (9.2h Thu night 2026-04-16, 6.2h Tue midday 2026-04-21) are clean process exits with delayed restart. Engine was not running during the gaps — the gaps are not write failures. `account_snapshots` is schema-drift-clean (7 DB cols == 7 ORM cols). Trades continued to run correctly on the broker side during the gaps (SL/TP live at MT5).

**Implication:** the demo engine hosting setup (local Windows workstation, manual restart) has operational availability gaps. Not a bug to fix in code, an operational decision for the 04-28 meeting — either accept the gaps, or plan a move to 24/7 hosting (already in v4_framework.md Phase 12).

**Artifacts:** `docs/research/snapshot_gaps_incident.md`.

---

## 2026-04-21 (later same day) — Phase 10 — YELLOW (verdict updated)

**Decided by:** user, after reviewing step 5 correlation results

**Change:** Downgrading earlier RED to YELLOW. The diversification case is decisive: ρ(BTC) in OOS is 0.57 (below the 0.7 proxy threshold), while ρ(FX)=0.13 and ρ(SPY)=0.21 both sit comfortably under the 0.3 diversification bar. The strategy is a crypto-beta harvester with risk management, not a BTC clone — and it meaningfully diversifies the existing FX book. This changes the calculus from "reject" to "rescue attempt".

**Next action:** Activate Phase 10.5 (regime-filter rescue). Phase 10.5 step 1 (define filter spec) in progress — spec drafted at `docs/research/regime_filter_spec.md`, awaiting user sign-off before implementation (step 2).

**Scope of Phase 10.5 (locked):** one filter, one knob (80th-percentile 4-week basket vol), no parameter sweep in the initial run. If the filter fails the 5-gate OOS panel (the 4 original gates + gated > ungated), v4 crypto-momentum is formally rejected — no further iteration permitted (iterating would reintroduce the overfitting risk Phase 10 step 4 is designed to detect).

---

## 2026-04-21 — Phase 10 (v4 Crypto Momentum) — RED (3/4 secondary, 2/4 primary)

**Decided by:** Claude Code audit + user review

**Summary of path:** Phase 10 steps 1–5 complete in a single working session. Step 3 ran 8 in-sample variants (direction × lookback × cost); all cleared the Sharpe-0.4 gate in-sample. Step 4 OOS validation on 2025-01-01 → 2026-04-17 (69 weeks) exposed regime dependence. Step 5 correlation analysis clarified the rescue case.

**Key numbers**

| Metric | Primary (LO/12m) | Secondary (LO/12w) |
|---|---:|---:|
| Train Sharpe | 1.263 | 1.270 |
| OOS Sharpe | **0.030** | **0.553** |
| OOS MaxDD | −8.5% | −4.4% |
| OOS vs BH BTC | strat +0.03 vs BH −0.33 | strat +0.55 vs BH −0.33 |
| Gates passed (of 4) | 2 | 3 |

Fold stability (K=5 on train window): both variants have one deeply negative fold (≈2022 crypto winter), mean fold Sharpe 0.89 (12m) / 1.18 (12w), std ≈ 1.2 — regime-dependent performance.

**Correlations (weekly, full vs OOS)**

| Counterparty | Full ρ | OOS ρ |
|---|---:|---:|
| BH BTC | 0.710 | 0.573 |
| BH ETH | 0.672 | 0.667 |
| BH BNB | 0.613 | 0.671 |
| BH SOL | 0.630 | 0.703 |
| SPY | 0.211 | 0.206 |
| FX TSMOM weekly | 0.122 | 0.127 |

**Rationale:** OOS Sharpe collapsed from train 1.27 to 0.03 (12m) and 0.55 (12w). The 2025-2026 bear regime is a legitimate stress scenario; TSMOM has almost no long signal in a dominant downtrend. However, both variants beat buy-and-hold BTC decisively in OOS (flat/positive vs −18%), confirming the risk-management design works. The BTC-proxy threshold of ρ > 0.7 was not cleanly met in OOS (0.573), and ρ against FX and SPY was well below the 0.3 diversification threshold — v4 genuinely diversifies from the existing FX book. This makes the case for a rescue attempt (Option 4) rather than outright rejection (Option 1).

**Next action:** Activate Phase 10.5 (TSMOM Crypto + Regime Filter, encoded as `phase_number=105` in DB). Six PENDING steps seeded: define filter spec, implement as overlay, re-run full backtest IS, re-run OOS, compare gated vs ungated, updated go/no-go. If Phase 10.5 also fails the 4-gate OOS panel, formal reject and pivot to a different Phase-10 track (commodities, crypto basis, volatility selling).

**Artifacts:**
- `docs/research/tsmom_crypto_prototype.md` — step 3 (in-sample)
- `docs/research/tsmom_crypto_oos_report.md` — step 4 (OOS)
- `docs/research/tsmom_crypto_corr_report.md` — step 5 (correlations)
- `docs/research/tsmom_crypto_equity_curves.png` — step 3 equity
- `docs/research/tsmom_crypto_oos_equity.png` — step 4 train vs OOS
- `docs/research/tsmom_crypto_corr_heatmap.png` — step 5 correlation heatmap
- `data/raw_crypto/*/D1.parquet` — Binance D1 data (BTC/ETH/BNB/SOL USDT)
- `improvements.db::tsmom_runs` — 12 crypto rows (8 IS + 4 OOS/train slices)
- `improvements.db::go_no_go_decisions` — this decision, id=1

---

## 2026-05-01 — USDCAD dropped from live trading (Phase 7 pre-kickoff)

**Decision:** Remove USDCAD from the live trading symbol set. Live instruments list goes from 7 → 6 symbols.

**Decided by:** project lead, 2026-05-01 in response to Phase 2 R:R analysis
**Tracker item:** AI-020 (BLOCKING, Phase 7)
**Source analysis:** `docs/research/phase7_blocker_2_audusd_usdcad_rr_analysis.md`

### Evidence

- Across **40 backtest runs** in `data/backtest_results.db` (7 strategies × 2 timeframes × 3 search rounds), **zero USDCAD configurations achieved a PASS verdict**.
- Best USDCAD result: `stop_hunt_reversal/D1` grade B (PF 1.06, expectancy +$22.52/trade, Sharpe 1.00) — below the 1.15 PF approval threshold.
- Most USDCAD configs are net-negative with significant drawdowns (USDCAD/macd_crossover/H4: MDD 50.7%; USDCAD/ml_direct/H4: MDD 58.8%).
- Live v3 (engine 2.4) USDCAD: **n=11 trades, net PnL −$544.01**. WR 62.5% on bollinger_bounce — exactly on break-even threshold yet $-PF 0.18.

### Rationale

"Try harder with new params" is sunk-cost reasoning when the underlying hypothesis (USDCAD edge exists at the strategies we have) has no data support. Forty backtest runs and one v3 quarter is sufficient evidence to reject.

### Action items

| | |
|---|---|
| (a) | Remove USDCAD entry from `config/paper.yaml::instruments` and `config/base.yaml::instruments`. **Pending engine restart approval** — see AI-020. |
| (b) | Path B re-optimisation (per `phase7_blocker_2_audusd_usdcad_rr_analysis.md`) does NOT run for USDCAD. |
| (c) | This decision logged here as a Phase 7 pre-kickoff finding. |
| (d) | Re-evaluate USDCAD inclusion only if a fundamentally different strategy class (not "tune existing further") is added in the future. |

### Cross-references

- `data/backtest_results.db::backtest_runs` — 40 USDCAD rows
- `data/optimized_params.yaml` — still contains a USDCAD block (atr_sl_mult 2.0 / atr_tp_mult 1.25 → R:R 0.625) which Path B work will leave in place but unused; cleanup deferred to AI-020 implementation
- `docs/research/phase7_blocker_2_audusd_usdcad_rr_analysis.md` — Phase 2 analysis
- AI-020 in `data/improvements.db::action_items`
