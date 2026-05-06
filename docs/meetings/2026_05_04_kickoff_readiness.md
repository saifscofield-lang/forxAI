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
| 6 — Meta-labeler train MACD | May 18–24 | PENDING — needs α/β/γ + MACD backfill source |
| 7 — Meta-labeler train RSI | May 18–24 | PENDING — same |
| 8 — Refactor ml_filtered + engine | May 25–31 | PENDING — depends on Step 6 design |
| 9 — `kelly_sizer.py` | May 25–31 | ✓ DONE 2026-05-06 (19 days early) |
| 10 — Full backtest 3yr + concentration | Jun 1–7 | PENDING — depends on Steps 6–8 |
| 11 — Ship gate (F1 ≥ 0.55, PF ≥ 1.3 OOS) | Jun 8 | PENDING |

**6 of 11 Phase 7 steps DONE.** All library code (Steps 1, 2, 5, 9) is complete. Step 4 (importance run) used the libraries on real data and produced the curated top-20 feature list.

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
| **Phase 7** (May 4 → Jun 8) | 1 | `AI-017` IN_PROGRESS (parent audit; project-management close call) |
| **Phase 8** (Jun 1 → Jul 20) | 2 | `AI-001` IN_PROGRESS (Path B/D decision needed); `GAP-OPS-01` deferred (internet stability) |
| **Phase 9** (Sep 1 live) | 5 | `GAP-FID-01..05` slippage / commission / news filter / swap / 2k-lot |

**Phase 8 BLOCKING dropped 5 → 2 since 2026-05-01** as today's session shipped AI-003 (schema-drift CI guard), AI-004b (cross-config divergence detection), AI-005 (30% holdout validation), and AI-019 (premise re-examination). Closing rate has front-loaded the technical-debt items; what's left are the project-strategy items that need your input.

### Decisions table (status-tracker)

| # | Decision | Status / Default |
|---|---|---|
| 1 | **Path B optimiser scope** — AUDUSD only? Or all 6? | **PENDING.** Default: AUDUSD only (others in separate audit). |
| 2 | **Training corpus α / β / γ** | **PENDING.** Default: β cap=20 stratified-by-outcome. **2026-05-06 update:** AI-019 re-analysis (today) makes γ more defensible than originally framed because γ sidesteps the thought-blocked cohort by construction. Worth revisiting at next opportunity. |
| 3 | **β cap value** (only if β chosen) | PENDING — default 20 (n=102) |
| 4 | **AI-017b sequencing** | **DONE 2026-05-01.** Phase A + B both shipped. `exit_reason_v2` is clean ground truth on 319 trades. |
| 5 | **MACD/RSI training backfill source** | PENDING. Default: `signal_logs` replay |
| 6 | **AI-004b spec confirmation** | **DONE 2026-05-03.** Cross-config drift detection shipped + activated post engine restart. |
| 7 *(new)* | **AI-001 fix path** — Path B (regime-stratified retraining) vs Path D (Phase 7 meta-labeler replaces ml_direct) | **PENDING.** Today's Path A retrain attempt failed empirically. Diagnostic + report at `docs/research/ai001_zero_buy_root_cause.md` and `ai001_retrain_balanced_report.md`. |

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

The week May 1 → 6 cleared 6 of 11 Phase 7 plan steps and 4 Phase 8 BLOCKING items, leaving the project genuinely well-shaped going into the May 18 meta-labeler training window. The remaining work splits into two camps:

- **Things that need your input** — α/β/γ corpus choice (with γ now more defensible after AI-019), Path B vs D for AI-001, MACD/RSI backfill source. None of these can be done unilaterally.
- **Things blocked on external state** — GAP-OPS-01 (stable internet for Telegram-independent control testing), Phase 9 GAP-FID items (need live broker for slippage/commission validation).

The AI-019 re-analysis is the single most strategically-important finding from this week. It changes the framing from "v3 has a small edge we need to protect" to "v3 has no demonstrated edge yet, and the work to find one is exactly what Phase 7 is for". Vote 2's deferral, Vote 6D's blacklist, and AI-001's urgency all line up under this corrected narrative.

---

### Pointers

- This week's research: `docs/research/phase7_*.md`, `docs/research/ai001_*.md`, `docs/research/ai017_supplemental_findings_2026_05_01.md`, `docs/research/ai019_premise_reexamination.md`
- Decision log: `docs/research/decision_log.md`
- Tracker: `data/improvements.db::action_items` — filter `status IN ('OPEN','IN_PROGRESS')`
- This week's commits: `git log --oneline ebbcc24..HEAD` (~25 commits across May 1–6)
