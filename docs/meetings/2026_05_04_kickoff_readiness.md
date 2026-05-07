# May 4 Kickoff — Readiness 1-pager

**Originally prepared:** 2026-05-01 (pre-kickoff)
**Last updated:** 2026-05-06 (post-kickoff aftermath, end-of-session refresh)
**Author:** automated session report (Claude Code)

This doc started as the pre-kickoff briefing and is now the rolling
project-state snapshot. The decisions table has shifted to a
status-tracker as items resolve. The "data quality observations"
section keeps growing as findings emerge.

## Status as of 2026-05-06

### Phase 7 plan progress

| Step | Window | Status |
|---|---|---|
| 1 — `triple_barrier.py` | May 4–10 | ✓ DONE 2026-05-06 |
| 2 — `purged_cv.py` | May 4–10 | ✓ DONE 2026-05-06 |
| 3 — Archive retired strategies | May 4–10 | ✓ DONE 2026-04-30 |
| 4 — Feature importance run | May 11–17 | ✓ DONE 2026-05-06 (5 days early) |
| 5 — `feature_selector.py` | May 11–17 | ✓ DONE 2026-05-06 (5 days early) |
| 6 — Meta-labeler train MACD | May 18–24 | ✓ DONE 2026-05-07 — **DUAL GATE FAIL** (AUC 0.495, R-PF 0.840) |
| 7 — Meta-labeler train RSI | May 18–24 | ✓ DONE 2026-05-07 — **DUAL GATE FAIL** (AUC 0.579, R-PF 0.906) |
| 8 — Refactor ml_filtered + engine | May 25–31 | **ON HOLD** — no validated edge to wire (see Jun 8 brief) |
| 9 — `kelly_sizer.py` | May 25–31 | ✓ DONE 2026-05-06 (19 days early) |
| 10 — Full backtest 3yr + concentration | Jun 1–7 | **DEFERRED** — no Step 8 artifact to backtest |
| 11 — Ship gate | Jun 8 | **RE-SCOPED to path-selection vote** — see `docs/meetings/2026_06_08_phase7_ship_gate.md` |

**8 of 11 Phase 7 steps DONE.** All library code (Steps 1, 2, 5, 9) is complete plus the two meta-labeler training runs (Steps 6–7) and Path B follow-up analysis. Verdict: **the meta-labeler / symbol-whitelist path is exhausted on the H1 corpus**. Recommended Jun 8 outcome = accept v3 as production through Phase 9, defer Phase 7 architecture change.

### Phase 6 plan progress

| Step | Window | Status |
|---|---|---|
| 1 — `tsmom_strategy.py` | May 4–10 | ✓ DONE 2026-05-06 |
| 2 — 10-year backtest, Sharpe ≥ 0.5 | May 11–17 | PENDING |
| 3 — Begin paper trading TSMOM | May 18–24 | PENDING |
| 4 — First-month vol-target validation | May 25–31 | PENDING |
| 5 — Continue parallel with meta-labeler | Jun 1–30 | PENDING |

### BLOCKING items

| Phase | n | Items |
|---|---:|---|
| **Phase 7** (May 4 → Jun 8) | **0** | (AI-017 closed 2026-05-06; all action follow-ups individually tracked) |
| **Phase 8** (Jun 1 → Jul 20) | 2 | `AI-001` IN_PROGRESS (Path D decided 2026-05-06, resolves at Phase 7 ship gate); `GAP-OPS-01` deferred (internet stability) |
| **Phase 9** (Sep 1 live) | 5 | `GAP-FID-01..05` slippage / commission / news filter / swap / 2k-lot |

**Phase 8 BLOCKING dropped 5 → 2 since 2026-05-01** as today's session shipped AI-003 (schema-drift CI guard), AI-004b (cross-config divergence detection), AI-005 (30% holdout validation), and AI-019 (premise re-examination). Closing rate has front-loaded the technical-debt items; what's left are the project-strategy items that need your input.

### Decisions table (status-tracker)

| # | Decision | Status |
|---|---|---|
| 1 | **Path B optimiser scope** — AUDUSD only? Or all 6? | **DECIDED 2026-05-06.** AUDUSD only; others audit separately. (Note: Path B itself is no longer the active path — see #7.) |
| 2 | **Training corpus α / β / γ** | **DECIDED 2026-05-06: γ** (retired strategies only). Sidesteps the thought-blocked cohort by construction per AI-019 re-analysis. Phase 7 Step 6 trains on this corpus when the May 18 window opens. |
| 3 | **β cap value** (only if β chosen) | N/A — γ chosen, not β. |
| 4 | **AI-017b sequencing** | **DONE 2026-05-01.** Phase A + B both shipped. `exit_reason_v2` is clean ground truth on 319 trades. |
| 5 | **MACD/RSI training backfill source** | **DECIDED 2026-05-06: `signal_logs` replay.** Same engine bias as live; cleaner than v1/v2 because no regime contamination from earlier strategy designs. |
| 6 | **AI-004b spec confirmation** | **DONE 2026-05-03.** Cross-config drift detection shipped + activated post engine restart. |
| 7 | **AI-001 fix path** | **DECIDED 2026-05-06: Path D** (Phase 7 meta-labeler replaces `ml_direct`). Path A failed empirically today; Path B rejected as wasted work given the meta-labeler retires `ml_direct` anyway. AI-001's resolution = Phase 7 ship gate (Jun 8). |

### Engine restart decision queue

**No restart pending.** Both 2026-05-02 (AI-020 + AI-017b activation) and 2026-05-03 (AI-004b activation) restarts completed cleanly. New `[CONFIG]` lines verified live for each. All three configs (`base.yaml`, `paper.yaml`, `live.yaml`) in sync.

The `XAUUSD_model_balanced.pkl` file from today's failed Path A retraining sits alongside the deployed model but is **not loaded** by the engine — `strategies/ml_direct_strategy.py:49` still resolves to `XAUUSD_model.pkl`. Switching requires explicit file rename or loader-path config change; not done because Path A failed empirically.

## Data quality observations (running list)

1. **TRAILING_STOP is a major v3 exit category, not a niche** (~30% of closed trades, n=96 of 319). Strategies producing many trailing-stop closes have very different risk dynamics than strategies producing real SL hits. Strategy-retention criteria should not penalise trailing-stop closes as if they were losses.

2. **AI-017b reclassification ground-truth quality is *strengthening over time*.** Today's Phase B classifier uses price-based inference. The `close_comment` column from Phase A captures direct MT5 evidence for every future close. AI-021 (prospective `sl_modifications` log, deferred to Phase 8) closes the remaining inference gap.

3. **`trades.stop_loss` is frozen at order placement** (engine modifies SL via `mt5.position_modify` but never writes back to the DB). Any analysis reading `trades.stop_loss` as "the SL the trade actually closed against" is wrong by an unknown amount. Use `signal_logs.stop_loss` (original) + `exit_reason_v2` (classifier verdict) instead.

4. **AI-001: `ml_direct/XAUUSD` model is structurally SELL-biased.** Across 94 trades the model has produced 0 BUY predictions because P(BUY) never crosses 40% on real bars (max 37.3%, mean 32.4%). The bias is regime-induced from training-window unidirectionality, not class-imbalance — training data favoured BUY (5,311 vs 4,632 SELL) but the model collapsed onto SELL. **Path A (`class_weight='balanced'`) was tried today and failed empirically** — it just over-collapsed onto SELL further. Path B (regime-stratified retraining) or Path D (meta-labeler replacement) is required.

5. **AI-019: the +$2,283 v3 ledger is entirely propped up by 70 trades opened during a window the engine wasn't supposed to be operating.** Excluding the thought-blocked cohort, v3 is **−$27,311 across 107 trades**. Every meaningfully-sampled strategy is net-negative. The dual-gate verdict shifts from "marginal fail" (R-PF 0.916, $-PF 1.035) to "decisive fail" (R-PF 0.429, $-PF 0.280). Implications: Vote 6D blacklist STRONGER (not weaker); Phase 8 deferral STRONGER; AI-001 urgency UP; γ corpus more defensible than originally framed.

6. **Phase 7 Step 4 finding: features are heavily redundant.** PCA shows only 23 of 82 features carry 95% variance. The top-20 list contains 8 SMA-derived features (substitution-effect candidates) and 0 RSI features. Worth flagging when designing the meta-labeler — manually injecting RSI may be appropriate.

## What I read into the project state

**The week May 1 → 6 cleared 6 of 11 Phase 7 plan steps, 4 Phase 8 BLOCKING items, and on 2026-05-06 the project lead resolved the four open project-strategy decisions in one block (Option 1 from the session report).** Phase 7 BLOCKING is now zero. Phase 8 BLOCKING is two: `AI-001` IN_PROGRESS (Path D = Phase 7 ship gate, so its resolution is folded into Phase 7 progress) and `GAP-OPS-01` (deferred until stable internet).

The May 18 meta-labeler training week now has a clean go-state:
- Corpus: γ (retired strategies only, sidesteps the thought-blocked cohort)
- MACD/RSI source: `signal_logs` replay
- `ml_direct` retirement path: Phase 7 ship gate, no separate retraining workstream
- Audit follow-ups: all individually tracked, none gating

The AI-019 re-analysis was the strategically-important finding from this week. It changed the framing from "v3 has a small edge we need to protect" to "v3 has no demonstrated edge yet, and the work to find one is exactly what Phase 7 is for", which is why γ corpus made sense and why Path D over Path B made sense. Vote 2's deferral, Vote 6D's blacklist, and AI-001's resolution all line up under this corrected narrative.

---

### Pointers

- This week's research: `docs/research/phase7_*.md`, `docs/research/ai001_*.md`, `docs/research/ai017_supplemental_findings_2026_05_01.md`, `docs/research/ai019_premise_reexamination.md`
- Decision log: `docs/research/decision_log.md`
- Tracker: `data/improvements.db::action_items` — filter `status IN ('OPEN','IN_PROGRESS')`
- This week's commits: `git log --oneline ebbcc24..HEAD` (~25 commits across May 1–6)
