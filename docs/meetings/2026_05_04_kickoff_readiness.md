# May 4 Kickoff — Readiness 1-pager

**Date prepared:** 2026-05-01 · **Meeting:** Phase 7 kickoff, 2026-05-04 · **Author:** automated session report (Claude Code)

## Today's deliverables (commits `7384629` → `80f734e`)

- **`Phase 1`** — realized_rr instrumentation. CSV exporter fix; calculator factored to `analysis/rr_calculator.py`; dual-gate PF helpers; 13 unit tests; ship-gate definition (`docs/research/phase7_ship_gate_definition.md`).
- **`Phase 1 narrative`** — `docs/research/ai017_supplemental_findings_2026_05_01.md`. Three findings: (1) yesterday's "realized_rr is NaN" was wrong, (2) **AI-017b** SL_HIT mislabel (27% v3 / 50% ml_direct), (3) **AI-019** Apr-10 blacklist was no-op for 18 days.
- **`Phase 2`** — AUDUSD/USDCAD R:R analysis + AI-004 backward audit. Path B confirmed; **USDCAD dropped** from live trading; AI-004b raised. Doc: `docs/research/phase7_blocker_2_audusd_usdcad_rr_analysis.md`. Decision logged: `decision_log.md` 2026-05-01 entry.
- **`Phase 3`** — meta-labeler training-set proposal. α/β/γ with AI-017b interaction column. Doc: `docs/research/phase7_training_set_proposal.md`.
- **`Tracker`** — `data/improvements.db` updated. Five action items added or modified.
- **`Backup`** — `data/trading.db.bak.pre-phase7-prep.20260501T095425Z` (151 MB; gitignored).

## Six decisions inheriting to this meeting

| # | Decision | Default if not chosen | Owner |
|---|---|---|---|
| 1 | **Path B optimiser scope** — AUDUSD only? Or all 6 remaining symbols? | AUDUSD only; others in separate audit | strategy |
| 2 | **Training corpus α / β / γ** | β with cap=20, stratified-by-outcome — most balanced | strategy |
| 3 | **β cap value** (only if β chosen) | 20 (n=102) | strategy |
| 4 | **AI-017b sequencing** — fix before May 18 (Step 6) so α/β can use `exit_reason`, or exclude that feature class? | **STATUS UPDATE 2026-05-01:** Phase A shipped (classifier + `close_comment` storage; engine fix dormant until restart). Phase B backfill pending engine restart + validation gate. Once Phase B clears, α/β can use `exit_reason_v2` cleanly for training. Decision is now sequencing of Phase B vs the May 18 train date, not whether to fix at all. | engineering |
| 5 | **MACD/RSI training backfill source** — v1/v2 trades, `signal_logs` replay, or reorder Phase 7 plan? | `signal_logs` replay (cleanest; same engine bias) | engineering |
| 6 | **AI-004b spec confirmation** — multi-file hash + cross-config consistency check on `strategy_blacklist`? | Per spec at end of `phase7_blocker_2_*.md`; ship before Jun 1 | engineering |

## Open BLOCKING items by phase

| Phase | n | Items |
|---|---:|---|
| **Phase 7** (May 4 → Jun 8) | 2 | `AI-017b` SL_HIT mislabel · `AI-020` USDCAD removal (yaml edits pending engine restart) |
| Plus 1 IN_PROGRESS | 1 | `AI-017` R:R pathology audit (today's Phase 1 + Phase 2 work continues to close it) |
| **Phase 8** (Jun 1 → Jul 20) | 5 | `AI-001` XAUUSD BUY · `AI-003` Alembic migrations · `AI-004b` cross-config drift · `AI-005` 30% holdout OOS · `GAP-OPS-01` Telegram-independent control |
| **Phase 9** (Sep 1 live) | 5 | `GAP-FID-01..05` slippage / commission / news filter / swap / 2k-lot validation |

`AI-019` (DOCS, no phase): premise re-examination of past ml_direct/XAUUSD decisions. Kickoff agenda item — 5 min.

## Engine restart decision queue

Restart still **deferred**. End-of-session restart preferred so the project lead can review the full diff (4 commits today) in one read. When the restart happens, these effects activate:

1. `engine/trading_engine.py` switches to the factored `analysis.rr_calculator.realized_rr` import path. Behaviour-preserving — same formula, same outputs.
2. Once restart is approved, the AI-020 yaml edits (remove USDCAD from `paper.yaml::instruments` and `base.yaml::instruments`) can ship. **Do not edit yaml without restart in the same window** — otherwise on-disk drift between memory and file violates the operational invariant AI-004 was meant to detect.
3. `[CONFIG]` log line at startup will then show 6 instruments (was 7) and the existing blacklist (2 entries: ml_direct/XAUUSD, ml_filtered_sma/XAUUSD).

## What I read into the meeting

The session shifted yesterday's "Phase 7 has 3 blockers" picture to "Phase 7 is mostly already-cleared, but two structural data-quality issues (AI-017b and AI-019) plus one infrastructure gap (AI-004b) materially change the May 4 → Jun 8 risk profile". The training-corpus choice (α/β/γ) is the single decision with the largest downstream impact — it determines whether the meta-labeler trains on a 26%-corrupted dominant-cell-overfit corpus, a half-cleaned middle path, or a small clean retired-strategy corpus. None of the three options is obviously right — the decision is genuinely a trade-off between data volume, contamination, and corpus representativeness.

---

### Pointers

- All today's research: `docs/research/phase7_*.md` and `docs/research/ai017_supplemental_findings_2026_05_01.md`
- Decision log: `docs/research/decision_log.md` (2026-05-01 USDCAD entry appended)
- Tracker: `data/improvements.db::action_items` — filter status='OPEN' AND blocking_phase IN (7,8,9)
- Recent commits: `git log --oneline ebbcc24..HEAD` (5 commits across 2 sessions)
