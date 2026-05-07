# Jun 8 — Phase 7 Ship-Gate Meeting Brief

**Prepared:** 2026-05-07
**Status:** RE-SCOPED FROM SHIP VOTE TO PATH-SELECTION VOTE
**Author:** automated session report (Claude Code)

> The original Phase 7 plan called for a Jun 8 ship-gate vote on a
> trained meta-labeler (F1 ≥ 0.55, PF ≥ 1.3 OOS). Today's research
> shipped Steps 6, 7, and Path B (single-corpus + walk-forward).
> All four runs failed the ship gate. The Jun 8 meeting can no
> longer be a "ship vs. don't ship" vote on a meta-labeler — that
> path is exhausted on the H1 corpus. Instead, it is a path-selection
> vote on what Phase 7 becomes from here.

## TL;DR

- Phase 7's intended Step 8 wiring (meta-labeler / symbol whitelist
  in `ml_filtered_strategy`) **cannot proceed** — no validated edge
  exists in the current H1 corpus to wire up.
- v3 (engine v2.4) continues as the production segment.
- Recommendation: **Option 1 — accept v3 as production through Phase 9,
  defer Phase 7 architecture change indefinitely.** Restart Phase 7
  scoping at a future date with a wider corpus (different timeframe
  or signal generators), as a Phase 8 reset.

## What we tried, what we found

| Run | Approach | Result | Doc |
|---|---|---|---|
| Step 6 | LightGBM meta-labeler on 710 MACD signals, purged 5-fold + 1% embargo | DUAL GATE FAIL — AUC 0.495 (random), R-PF 0.840 | `docs/research/phase7_step6_meta_labeler_macd.md` |
| Step 7 | Same on 307 RSI signals | DUAL GATE FAIL — AUC 0.579 (real but weak signal), R-PF 0.906 capped by R:R math | `docs/research/phase7_step7_meta_labeler_rsi.md` |
| Path B (single-corpus) | Per-symbol R-PF projection, dual-half stability check | RSI={EURUSD} (R-PF 1.50/1.85), MACD={} | `docs/research/phase7_path_b_symbol_stratification.md` |
| Path B (walk-forward) | Quarterly cutoffs through 2024-2025, whitelist re-derived per cutoff, OOS aggregate | EMPTY whitelist at every cutoff. Single-corpus EURUSD result was an artifact of the median split point. | `docs/research/phase7_path_b_walkforward.md` |

### Why the EURUSD-RSI result didn't survive walk-forward

EURUSD-RSI per-year WR is **100/67/22/77/25/70/40** across 2020-2026.
With only 49 signals total for that combo across 6 years, the corpus
is too thin for any selector to validate to the project's R-PF ≥ 1.30
gate. The single-corpus dual-half check happened to land its median
at 2023-06-23, which by coincidence put both halves above the gate.
Walk-forward exposed this honestly — at the 2025-10-01 cutoff, the
early half (Jan 2020 → Mar 2023, n=14) has WR 42.9% / R-PF 1.13 (FAIL).

## The three options

### Option 1 — Accept v3 as production through Phase 9 *(recommended)*

- v3 (engine v2.4) is the running STABLE segment on MT5 demo per CLAUDE.md.
- Phase 7 architecture change deferred indefinitely.
- Jun 8 closes Phase 7 cleanly without shipping unvalidated work.
- Phase 8 work (different timeframe, different signal generators) starts
  with a clean mandate rather than a forced architecture change.
- **Cost:** the Phase 7 plan's effort — meta-labeler infrastructure,
  Path B analysis, walk-forward validation — produced no production
  artifact, only research conclusions and reusable libraries
  (`features/labels/triple_barrier.py`, `ml/purged_cv.py`,
  `features/importance/feature_selector.py`, `risk/kelly_sizer.py`,
  `analysis/rr_calculator.py`). All five remain useful for Phase 8+.
- **Confidence:** high. v3 is documented stable; deferring is a known-good
  state.

### Option 2 — Widen the corpus

- Re-generate the primary signal corpus on M15 or H4 timeframes (more
  signals per year, possibly enough cadence to validate per-symbol
  edges OOS).
- Or add new signal generators (TSMOM crypto, donchian breakout,
  etc.) that have different statistical properties.
- This is a **Phase 8 reset**, not a Phase 7 ship. The Jun 8 vote
  becomes "approve a Phase 8 corpus-widening initiative".
- **Cost:** 4-8 weeks before another ship-gate attempt is meaningful.
- **Risk:** there is no a-priori reason to believe wider data will
  produce a stable edge — the H1 result may not be a corpus-thin issue
  but a genuine "no edge to find" issue. Could repeat the same loop.

### Option 3 — Lower the R-PF gate

- Change the documented bar from R-PF ≥ 1.30 to e.g. R-PF ≥ 1.05.
- Allows Phase 7 to ship something on top of v3.
- **Cost:** undermines the project's stated edge claim. Future
  internal review (or external review like the 2026-04-28 report)
  will likely call this out as moving the goalposts to fit a
  disappointing result.
- **Not recommended.** A 1.05 gate would have passed the EURUSD-RSI
  whitelist on full corpus (R-PF 1.70) but the walk-forward shows
  even that fails on truly OOS data. Lowering the gate doesn't make
  the underlying edge real.

## Decision matrix

| Criterion | Option 1 | Option 2 | Option 3 |
|---|:---:|:---:|:---:|
| Ships a production change Jun 8? | no | no | yes (caveat) |
| Survives external review? | yes | yes (it's a plan) | no |
| Preserves project credibility | yes | yes | no |
| Time to next decision point | Jun 8 closes Phase 7 | 4-8 weeks | immediate |
| Throws away today's work? | no — libs reused | no — libs reused | uses the failed artifact |

## What changes after the meeting

### If Option 1 (recommended)

- Mark phase_steps 7.6, 7.7, 7.8, 7.10, 7.11 as `DEFERRED` (not FAILED
  — the work was done correctly, the corpus didn't support it).
- `phase_steps` 7.6 and 7.7 stay `COMPLETED` with the FAIL verdicts
  in their notes.
- v3 continues paper trading. Live-broker switch (Phase 9) timeline
  unchanged — GAP-FID-01/-02/-04 already shipped 2026-05-07,
  GAP-FID-05 still pending live broker, GAP-OPS-01 still deferred.
- Phase 8 scoping document opens with "Phase 7 deferred. New corpus
  generation is the gating prerequisite for any future architecture
  change."

### If Option 2

- Approve a Phase 8 sub-plan: regenerate `primary_signals.parquet`
  on M15 timeframe (or add 2 more signal generators), then re-run
  Steps 4 → 7 → Path B → walk-forward. Estimated 4-6 weeks.
- v3 continues unchanged in the meantime.

### If Option 3 (NOT recommended)

- Update `analysis/rr_calculator.py::phase7_ship_gate` thresholds.
- Re-run Path B with relaxed gate, get a new whitelist.
- Wire Step 8 against the new whitelist.
- Document the gate change with a clear "we lowered the bar to ship
  this" footnote in `docs/research/phase7_ship_gate_definition.md`.
- Live-trade the new architecture with extra monitoring.

## Cross-references

- All four research docs above (`docs/research/phase7_*`).
- `data/improvements.db` `decisions_log` rows 41–45 (today's chain).
- `data/improvements.db` `phase_steps` 7.6/7.7 — already marked
  COMPLETED with FAIL verdicts in notes.
- `CLAUDE.md` — current state ("v3 is the running STABLE segment").
- `docs/meetings/2026_05_04_kickoff_readiness.md` — pre-kickoff brief
  (this Jun 8 brief supersedes its Phase 7 section).
