# Unfreeze Decision — End of STABLE_v2 Freeze

**Date:** 2026-06-02
**Freeze duration:** 2026-05-09 → 2026-06-02 (24 days of a planned 42)
**Decision:** END the freeze early and ship one validated change to raise trade
frequency, then resume collection toward the Phase 8 gate.

## Why end the freeze early

The freeze's purpose was to accumulate ≥30 clean v3 trades for the Phase 8 H4
gate. At the observed pace (0.29 trades/day, 7 trades in 24 days) the gate was
projected for ~2026-09-13 — unreachable on any reasonable calendar. The freeze
was succeeding at discipline but failing at its actual goal: producing an
evaluable sample. Owner priority: **increase tradeable, evaluable trades.**

Rather than passively wait, we ran a read-only evidence phase (no engine code
touched) to find the highest-leverage, lowest-risk way to raise frequency.

## Evidence base (all read-only, freeze-respecting)

Six audits, scripts in `scripts/audit_*.py` + `validate_*.py`, reports in
`docs/research/rescue_phase1*.md`:

- **1a Rejected-signal audit** — quality filters (H4 trend, session, news,
  max-pos, dedup-same) block trades that win FAR below the executed baseline →
  they protect us. **Do not loosen filters.** (DEDUP_CONFLICT 73% → redesign later.)
- **1b Label-optimism audit** — current ML labels are ~32% optimistic; the
  ordering bug flips ~48% of ambiguous labels but those are only ~1.7% of data.
- **1c ML calibration audit** — DECISIVE: `ml_direct` confidence is flat at ~39%
  win across all bins (break-even = 40%), EV ≈ −0.05 ATR. **ml_direct has no
  predictive edge** yet 6 of 7 freeze trades came from it. Demote it.
- **1d Strategy-silence funnel** — the ATR regime filter (≥1.2×avg) is the
  dominant throttle (passes ~9% of bars); relaxing it 1.2→1.0 gives ~4× MACD.
- **1e ATR-lever validation** — relaxing ATR FAILS: MACD PF 1.00→0.97 (net −88R);
  RSI has no edge either timeframe. **The filter carries MACD's thin edge.**
- **1f M15 validation** — MACD on M15 (same logic, all filters) = **~4.8× trades
  (18→87/symbol-yr) with PF HELD (1.03 vs 1.00), identical 42% WR.** The one
  validated frequency lever.

## The change shipped (this commit)

**MACD Crossover now generates signals on M15 instead of H1**, all filters kept.
- `strategies/macd_crossover.py`: added `timeframe="M15"` attribute.
- `engine/trading_engine.py`: fetch signal-grade M15 bars per symbol; route each
  strategy's `generate_signal()` to its declared timeframe (default H1).

RSI / SMA / ml_direct remain on H1. No filters loosened. No risk controls changed.

## What we expect

- **Frequency:** MACD signal rate ~4.8× at strategy level; net live ~2–3× after
  downstream filters. Phase 8 30-trade gate reachable in ~4–8 weeks (~mid-July)
  instead of September.
- **Quality:** PF held in clean sim (1.03). With the full filter stack + optimized
  params + trade management, expect break-even to modestly positive. MACD's edge
  is thin — the primary value is reaching an EVALUABLE sample fast.
- **Risk to watch:** M15 is noisier and spread is a larger % of smaller moves
  (excluded from the sim) — could erode the thin edge. Weekly checkpoint to
  confirm live PF tracks the sim; revert MACD to H1 (`timeframe="H1"`) if it
  degrades.

## New segment

This opens a fresh data segment (call it **STABLE_v3-M15**) — trade accounting
for the gate restarts from this commit. Record in `data_segmentation_log` and
`decisions_log` on the live tracker DB (local checkout DB is stale; live DB is
authoritative).

## Reversibility

Single-line revert: set MACD `timeframe="H1"`. The engine routing falls back to
H1 for any strategy without a `timeframe` attribute.
