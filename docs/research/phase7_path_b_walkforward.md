# Phase 7 Path B — walk-forward validation

**Date:** 2026-05-07  
**Re-runnable:** `python scripts/run_path_b_walkforward.py`

## Why walk-forward

`run_path_b_stratification.py` picked the whitelist by checking R-PF stability in BOTH time halves of the full corpus. The late half was therefore in-sample for the gate selection itself — so the headline 'EURUSD-RSI R-PF=1.85 in late half' is over-fit-tinted by construction. This script fixes that: at each quarterly cutoff, the whitelist is derived from train-only data and applied to the next 6 months of OOS signals. The aggregate of all OOS predictions is the honest validation number.

## Method

- Cutoff grid: ['2024-01-01', '2024-04-01', '2024-07-01', '2024-10-01', '2025-01-01', '2025-04-01', '2025-07-01', '2025-10-01']
- OOS window per cutoff: 6 months
- Skip cutoffs with < 2.0 years of train data
- Gate (re-applied per cutoff): R-PF ≥ 1.3 in BOTH halves of train data AND n ≥ 15 per half
- OOS R-PF: each win contributes +planned_rr (1.4 MACD / 1.5 RSI), each loss contributes -1.0

## Per-cutoff results

| cutoff | strategy | whitelist | OOS n | wins | WR | R-PF |
|---|---|---|---:|---:|---:|---:|
| 2024-01-01 | macd_crossover | — | 0 | 0 | 0.0% | 0.00 |
| 2024-01-01 | rsi_reversal | — | 0 | 0 | 0.0% | 0.00 |
| 2024-04-01 | macd_crossover | — | 0 | 0 | 0.0% | 0.00 |
| 2024-04-01 | rsi_reversal | — | 0 | 0 | 0.0% | 0.00 |
| 2024-07-01 | macd_crossover | — | 0 | 0 | 0.0% | 0.00 |
| 2024-07-01 | rsi_reversal | — | 0 | 0 | 0.0% | 0.00 |
| 2024-10-01 | macd_crossover | — | 0 | 0 | 0.0% | 0.00 |
| 2024-10-01 | rsi_reversal | — | 0 | 0 | 0.0% | 0.00 |
| 2025-01-01 | macd_crossover | — | 0 | 0 | 0.0% | 0.00 |
| 2025-01-01 | rsi_reversal | — | 0 | 0 | 0.0% | 0.00 |
| 2025-04-01 | macd_crossover | — | 0 | 0 | 0.0% | 0.00 |
| 2025-04-01 | rsi_reversal | — | 0 | 0 | 0.0% | 0.00 |
| 2025-07-01 | macd_crossover | — | 0 | 0 | 0.0% | 0.00 |
| 2025-07-01 | rsi_reversal | — | 0 | 0 | 0.0% | 0.00 |
| 2025-10-01 | macd_crossover | — | 0 | 0 | 0.0% | 0.00 |
| 2025-10-01 | rsi_reversal | — | 0 | 0 | 0.0% | 0.00 |

## Aggregate OOS verdict

| strategy | OOS n | wins | losses | WR | R-PF | verdict |
|---|---:|---:|---:|---:|---:|:---:|
| macd_crossover | 0 | 0 | 0 | 0.0% | 0.000 | INSUFFICIENT_N |
| rsi_reversal | 0 | 0 | 0 | 0.0% | 0.000 | INSUFFICIENT_N |

## Honest reading

- **The whitelist was empty at every cutoff for both strategies.** Zero OOS predictions
  isn't because the corpus is thin — it's because the dual-half R-PF gate
  failed when applied to train-only sub-corpora. The single-corpus EURUSD-RSI
  pass (R-PF 1.50 / 1.85 in early/late) was an artifact of *where the median
  split fell* on the full dataset. Diagnostic at the 2025-10-01 cutoff:

  ```
  EURUSD-RSI in train (Jan 2020 – Oct 2025, n=44):
    early half (2020-Jan → 2023-Mar, n=14): WR 42.9% → R-PF 1.13   FAIL
    late  half (2023-Mar → 2025-Oct, n=30): WR 60.0% → R-PF 2.25   PASS
  ```

  When the corpus is sliced earlier, the early half includes 2022's 22% WR
  year for EURUSD-RSI; that one bad year drops early-half WR below the
  46.4% gate-pass threshold. The whole "stable edge" disappears.

- **EURUSD-RSI per-year WR is highly variable**: 100% (n=1) / 67% / 22% /
  77% / 25% / 70% / 40%. With only 49 EURUSD-RSI signals across 6 years,
  any claim of a stable edge is statistically tenuous. Walk-forward
  exposes this honestly; single-corpus selection hid it.

- **MACD:** zero OOS predictions, consistent with the single-corpus
  finding that no symbol consistently clears the gate. No artifact to
  expose — MACD genuinely has no symbol-stratified Path B rescue.

## What this means for Phase 7 Step 8

- The single-corpus whitelist did NOT survive walk-forward validation. Building Step 8 wiring on it would ship an unvalidated edge. Options:
  1. Accept v3 as production through Phase 9 — defer the Phase 7 architecture change.
  2. Look outside the H1 corpus (different timeframe, different signal generators) for a strategy with enough signal cadence to validate cleanly.
  3. Re-design the gate threshold — current R-PF ≥ 1.30 is the documented bar. Lower bars may admit more strategies but undermine the project's edge claim.

## Cross-references

- `docs/research/phase7_path_b_symbol_stratification.md` — single-corpus run
- `docs/research/phase7_step6_meta_labeler_macd.md` — Step 6 FAIL
- `docs/research/phase7_step7_meta_labeler_rsi.md` — Step 7 FAIL
- `data/improvements.db` decisions_log — running record