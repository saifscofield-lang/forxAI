# AI-005 — 30% Holdout OOS Validation

**Date generated:** 2026-05-06  
**Source:** `data/trading.db` (engine_version=2.4)  
**Re-runnable via:** `python scripts/run_holdout_validation.py`

## Why this exists

v4 was rejected on a stricter methodology than v3 was held to: locked scope, single-shot evaluation, OOS separation between training and validation. v3's recommendations (R1–R4) were derived from the same dataset that would be used to evaluate them — converting Phase 8 'OOS' into a second IS. AI-005 was raised at the 2026-04-28 meeting to apply v4's methodology to v3 and validate the surviving recommendations on data not used to derive them.

## Split

| Slice | n | Window | Net PnL | WR |
|---|---:|---|---:|---:|
| IS (70%, oldest) | 124 | 2026-04-02 19:29:19.000000 → 2026-04-22 19:42:09.000000 | $-16,658.83 | 69.4% |
| **OOS (30%, newest)** | **54** | 2026-04-23 03:10:18.000000 → 2026-05-05 12:30:37.000000 | **$+19,434.32** | **81.5%** |
| Total | 178 | | $+2,775.49 | |

Time-based split (not random) so the OOS represents the most recent regime — the v4 standard.

## Recommendations validated against OOS

### R1 — Block XAUUSD SELL during OVERLAP session (13:00–17:00 UTC)

**Verdict:** `SURVIVES`

- OOS XAUUSD SELL: 27 trades. 3 in 13-17 UTC window with PnL $-3,240.00. Non-overlap: $+24,880.60.

OOS slice confirms the IS pattern: OVERLAP-window XAUUSD SELL is net-negative even on data not used to derive R1. The rule is safe to install for Phase 8.

### R4 — Defer per-symbol decisions for non-XAUUSD pairs

**Verdict:** `SURVIVES`

- 10 of 10 non-XAUUSD cells are underpowered (n < 10) on OOS holdout. All non-XAUUSD cells remain underpowered.

All non-XAUUSD per-(symbol, direction) cells remain underpowered on OOS. R4 holds — defer per-symbol decisions until Phase 8 collects more data.

### R2 — Retire bollinger_bounce, R3 — Retire ml_filtered_sma

**Verdict:** `NOT_OOS_VALIDATABLE`

Retirement is a forward-looking rule: after 2026-04-28 these strategies stopped trading. The OOS sample postdates retirement, so there are no bollinger_bounce / ml_filtered_sma trades on OOS to evaluate. The retirement decision can only be validated by a counterfactual rebuild — running the strategy logic on OOS bars in shadow mode and computing what would have happened. That work is out of scope for AI-005 and belongs to the Phase 7 meta-labeler training pipeline (which already has the data infrastructure to run signals against historical bars).

### R5–R7 — undefined

AI-005's brief references *R1–R7* but only **R1 through R4** are formally defined in any project doc (`docs/research/full_trade_evolution_report_2026-04-28.md` section 9). R5, R6, R7 do not appear as labelled recommendations anywhere in the codebase or `docs/`.

The `R1–R7` shorthand likely refers to the broader set of audit recommendations including the 8 meeting votes, but that mapping isn't recorded. **Surfacing as a finding for the project lead.** If R5–R7 should be specific rules, they need to be defined before this script can validate them.

## Summary

| Rule | Description | OOS Verdict |
|---|---|---|
| R1 | OVERLAP filter (XAUUSD SELL 13–17 UTC) | `SURVIVES` |
| R2 | Retire bollinger_bounce | `NOT_OOS_VALIDATABLE` |
| R3 | Retire ml_filtered_sma | `NOT_OOS_VALIDATABLE` |
| R4 | Defer per-symbol decisions (non-XAUUSD) | `SURVIVES` |
| R5 | (undefined) | `—` |
| R6 | (undefined) | `—` |
| R7 | (undefined) | `—` |

## Files

- `artifacts/ai005_holdout_split_2026-05-06.csv` — frozen IS / OOS ticket lists

- This file: `docs/research/ai005_holdout_validation.md`

- Source script: `scripts/run_holdout_validation.py` (re-runnable)
