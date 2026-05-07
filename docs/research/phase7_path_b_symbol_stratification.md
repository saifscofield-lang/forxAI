# Phase 7 Path B — symbol-stratification analysis

**Date:** 2026-05-07  
**Re-runnable:** `python scripts/run_path_b_stratification.py`  
**Whitelist artifact:** `config/strategy_symbol_whitelist.yaml`

## Why this analysis

Phase 7 Step 6 trained an MACD meta-labeler — DUAL GATE FAIL (AUC=0.495, R-PF=0.840). Step 7 trained an RSI meta-labeler — DUAL GATE FAIL (AUC=0.579, R-PF=0.906) but with real predictive signal. The per-symbol breakdown in Step 7 showed the RSI edge is concentrated in a few pairs while others drag the corpus average down. This script formalises that finding and outputs an actionable whitelist, plus checks each per-symbol edge for cross-time stability.

## Method

1. Split each strategy's signal corpus at the median signal timestamp into `early` and `late` halves.
2. Compute per-symbol WR and projected R-PF (= WR/(1-WR) × planned R:R) in both halves.
3. A symbol enters the whitelist only if R-PF ≥ 1.3 in BOTH halves AND n ≥ 15 per half. The dual-half gate guards against temporal overfitting; the n gate guards against tiny-sample noise.
4. Planned R:R: macd=1.4 (TP=3.5×ATR / SL=2.5×ATR), rsi=1.5 (TP=3.0×ATR / SL=2.0×ATR).

## macd_crossover

Baseline (full corpus, all symbols): n = 710, WR = 39.7%, projected R-PF = 0.922 (FAIL)

| symbol | n | WR | R-PF | n_early | WR_early | R-PF_early | n_late | WR_late | R-PF_late | stable? |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| AUDUSD | 80 | 37.5% | 0.84 | 36 | 41.7% | 1.00 | 44 | 34.1% | 0.72 | no |
| EURUSD | 126 | 45.2% | 1.16 | 62 | 43.5% | 1.08 | 64 | 46.9% | 1.24 | no |
| GBPUSD | 117 | 31.6% | 0.65 | 63 | 30.2% | 0.60 | 54 | 33.3% | 0.70 | no |
| USDCAD | 118 | 33.9% | 0.72 | 57 | 42.1% | 1.02 | 61 | 26.2% | 0.50 | no |
| USDCHF | 101 | 43.6% | 1.08 | 52 | 42.3% | 1.03 | 49 | 44.9% | 1.14 | no |
| USDJPY | 72 | 45.8% | 1.19 | 36 | 55.6% | 1.75 | 36 | 36.1% | 0.79 | no |
| XAUUSD | 96 | 42.7% | 1.04 | 48 | 39.6% | 0.92 | 48 | 45.8% | 1.19 | no |

**Whitelist for macd_crossover:** (none — no symbol passes the dual-half gate)

## rsi_reversal

Baseline (full corpus, all symbols): n = 307, WR = 33.9%, projected R-PF = 0.768 (FAIL)

| symbol | n | WR | R-PF | n_early | WR_early | R-PF_early | n_late | WR_late | R-PF_late | stable? |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| AUDUSD | 17 | 47.1% | 1.33 | 9 | 55.6% | 1.88 | 8 | 37.5% | 0.90 | no |
| EURUSD | 49 | 53.1% | 1.70 | 20 | 50.0% | 1.50 | 29 | 55.2% | 1.85 | YES |
| GBPUSD | 35 | 45.7% | 1.26 | 18 | 50.0% | 1.50 | 17 | 41.2% | 1.05 | no |
| USDCAD | 49 | 30.6% | 0.66 | 23 | 26.1% | 0.53 | 26 | 34.6% | 0.79 | no |
| USDCHF | 43 | 30.2% | 0.65 | 19 | 26.3% | 0.54 | 24 | 33.3% | 0.75 | no |
| USDJPY | 58 | 22.4% | 0.43 | 33 | 27.3% | 0.56 | 25 | 16.0% | 0.29 | no |
| XAUUSD | 56 | 23.2% | 0.45 | 31 | 9.7% | 0.16 | 25 | 40.0% | 1.00 | no |

**Whitelist for rsi_reversal:** `EURUSD`

## Recommendation

- **RSI:** restrict the strategy in `ml_filtered_strategy` (Step 8) to ['EURUSD']. Skip the meta-labeler on top — at this corpus size, a per-symbol whitelist captures the edge more cleanly than a sample-starved per-symbol model.
- **MACD:** no symbol clears the dual-half R-PF gate. Best candidates (USDJPY, EURUSD) decay materially in the late half — temporal regime change rather than recoverable edge. Path B does not rescue MACD.
- **Step 8 design impact:** `ml_filtered_strategy` reads the YAML whitelist before any model logic. Symbols not on the list are silently skipped. No model artifact required for the gated strategies, simplifying deployment.
- **Step 11 ship gate:** projecting R-PF on EURUSD-only RSI from the historical corpus is approximate — Step 10's full backtest must validate on a hold-out window before the Jun 8 ship vote.

## Cross-references

- `docs/research/phase7_step6_meta_labeler_macd.md` — MACD meta-labeler FAIL
- `docs/research/phase7_step7_meta_labeler_rsi.md` — RSI meta-labeler FAIL
- `config/strategy_symbol_whitelist.yaml` — generated artifact consumed by `ml_filtered_strategy` (Step 8)
- `data/improvements.db` decisions_log — running record