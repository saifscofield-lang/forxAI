# AI-017 Supplemental Findings — 2026-05-01

**Date:** 2026-05-01
**Author:** automated investigation (Claude Code), per `docs/p.md` instructions
**Trigger:** Phase 7 prep work (per yesterday's audit) found three new issues that change yesterday's conclusions.

This document supplements `ai017_rr_audit.md` (2026-04-30). Three findings, each consequential for Phase 7 and at least two consequential for v3 paper-trading interpretation.

---

## Finding 1 — Yesterday's "realized_rr is NaN" claim was wrong

### What yesterday's audit said
> Key finding 3 — `realized_rr` column is NaN across all v3 trades. The pipeline computes `planned_rr` at order time but never backfills realized R:R from `open_price`/`close_price`/`stop_loss`/`take_profit` after the trade closes.

### What is actually true
The live engine's trade-close handler (`engine/trading_engine.py:1156-1164` at the time of yesterday's audit) **already implements** the realized-R:R formula and writes the value to `trade_results.risk_reward_actual`. The DB column is **100% populated** (318 of 318 closed trades). Recompute from raw fields matches stored on **76 of 76 audit tickets, zero formula bugs**.

The audit was misled by `artifacts/all_trades_enriched.csv`. That CSV has both a `realized_rr` column (placeholder, all NaN) and a `risk_reward_actual` column (real values from DB). Yesterday's audit read the placeholder, not the data.

### Root cause
`scripts/analyze_all_trades.py:250` set `df["realized_rr"] = np.nan  # will require risk amount per trade; leave for now` — a TODO never closed. The merge of `risk_reward_actual` from `trade_results` overwrote nothing because the placeholder column was already named differently.

### Fix shipped
- `scripts/analyze_all_trades.py` now fills `realized_rr` from `risk_reward_actual` after the trade_results merge. The CSV will roundtrip the metric on the next run.
- `tests/test_rr_calculator.py::TestCSVRoundtrip` enforces this going forward.

### Implication
Yesterday's Phase 7 Blocker #1 ("populate realized_rr") is **not** a build job. The data exists. The work is to surface it correctly in the analytics layer and to factor the calculator into a shared module. Both shipped this session — see Blocker #1 status block at the end of this doc.

---

## Finding 2 — `exit_reason` is corrupted on ~27% of v3 SL_HIT trades (mislabelling bug)

### Pattern
- 247 trades in the live DB carry `exit_reason='SL_HIT'`. Of those, **52 of 98 ml_direct/v3 trades** are tagged SL_HIT but `profitable=1` with tiny price moves (close ≈ open within 0.10 on XAUUSD) and `pnl ≈ +$2.00`. SL was set 30–40 points away — nowhere near where the trade actually closed.
- Quantified across full v3: **40 of 149 SL_HIT trades (27%)** are mislabelled. Strategy breakdown (v3): ml_direct **38/76 (50%)**, rsi_reversal 1/3, all others 0.
- Engine-version trend: 0% (v2.0–v2.2) → 5% (v2.1) → **50% (v2.3)** → **27% (v2.4)**. The bug has always been latent; its surface area exploded in v2.3 with the introduction of trailing/break-even close paths.

### Root cause

> **Correction (2026-05-01 Phase A):** The original entry below claimed the substring `"SL"` matched `"SELL"` and that ML signal comments returned by MT5 on close were the source of the mislabel. This is **wrong**. Verified empirically: `'SL' in 'SELL'` is `False` (the characters are S-E-L-L, no S-immediately-L pair). The actual mechanism is **modified-SL hits**, described below. The original analysis is preserved here for audit-trail purposes — strikethrough indicates the corrected text.

**Original (wrong) claim — superseded:**

> ~~`engine/trading_engine.py:1109-1116`:~~
>
> ~~```python~~
> ~~comment = (close_deal.comment or "").upper()~~
> ~~if "SL" in comment or "STOP LOSS" in comment:~~
> ~~    exit_reason = "SL_HIT"~~
> ~~elif "TP" in comment or "TAKE PROFIT" in comment:~~
> ~~    exit_reason = "TP_HIT"~~
> ~~else:~~
> ~~    exit_reason = "MANUAL"~~
> ~~```~~
>
> ~~The substring match `"SL" in comment` matches `"SELL"`. When MT5 returns the original signal comment on a close (e.g., trailing-stop or break-even close paths), the comment contains text like `"ML Direct SELL | conf=56.6%"` — uppercase `"SELL"` contains `"SL"` — the trade is labelled `SL_HIT` regardless of how it actually exited.~~

**Actual mechanism (corrected):**

The substring check works as designed: it catches the `"sl"` token in close comments like `"[sl 4756.64]"` that MT5 returns when an SL price is hit. The problem is upstream: the engine had no way to distinguish between two scenarios that both produce `[sl ...]` close comments:

1. **Original-SL hit** (real adverse stop): price moved against the position by the full planned SL distance and triggered the SL.
2. **Modified-SL hit** (break-even or trailing stop): the engine's strategy moved the SL from its original adverse price to break-even (≈ entry) or further into profit; price then ticked back to the modified SL and triggered it. The trade closes at a small profit / break-even, not an adverse loss — but MT5 still reports it as `[sl ...]` because the SL price *was* hit (just a different SL than the original one).

The empirical pattern (close ≈ open, pnl ≈ +$2, exit_reason = SL_HIT) is mostly scenario 2: trailing-stop break-even closes that the old engine code labelled identically to scenario 1.

### Evidence gap that motivated Phase A's `close_comment` storage

Yesterday's investigation could not directly verify scenario 2 from the database alone — the engine never persisted the MT5 close-deal comment. Phase A (committed 2026-05-01) adds `trade_results.close_comment` (TEXT, nullable) to capture the raw comment going forward. Future investigations into exit-reason mechanics now have direct evidence rather than inferring from price fields. This is the load-bearing infrastructure addition; the classifier below would have been ad-hoc without it.

### Impact

| Layer | Affected |
|---|---|
| `pnl`, `profit`, `risk_reward_actual`, prices | NOT affected (computed from price fields, not text) |
| `exit_reason`, anything that filters/aggregates by it | corrupted on ~27% of v3 SL_HIT |
| Yesterday's audit's exit-reason narrative for ml_direct (PF 1.49 vs PF 0.46 R:R interpretation) | unaffected for the headline numbers; affected for any "SL_HIT outcomes" narrative |
| Phase 7 meta-labeler training data if it uses `exit_reason` as a label or feature | **CRITICAL** — would learn from corrupted ground truth |
| Direct $ impact of the mislabels (treated-as-loss but actually small profit) | **+$635.80** total — small, but the *count* corruption is the real damage |

### Phase A — code fix (shipped 2026-05-01)

1. **Capture `close_comment`** — store MT5's raw close-deal comment in `trade_results.close_comment`. Closes the evidence gap permanently. Done via plain ALTER TABLE; an Alembic migration will replace this when AI-003 lands.

2. **Price-proximity classifier** at `analysis/exit_classifier.py::classify_exit()`. Refines the MT5 tag using close-to-open distance and direction:
   - `|close - open| < 0.10 × atr_at_entry` → **BE_HIT** (no meaningful move; SL was at break-even)
   - close in favorable direction by > threshold → **TRAILING_STOP** (SL was trailed into profit, position closed in green)
   - close in adverse direction by > threshold → **SL_HIT** (real adverse stop)
   - `TP_HIT` / `MANUAL` / `UNKNOWN` pass through unchanged

   **Threshold rationale:** 0.10 × ATR scales naturally per symbol. For XAUUSD with ATR ≈ 16 the threshold is ~1.6 points — well above the empirical break-even cohort (close-to-open distance 0.02–0.10) and well below real SL hits (15+ points). For EURUSD with ATR ≈ 0.0012 the threshold is ~0.00012 (~1.2 pips), matching the same proportion. Per-symbol fallback values used if `atr_at_entry` is NULL: 5.0 for XAUUSD, 0.05 for JPY pairs, 0.0005 for other forex.

3. **Engine wiring** at `engine/trading_engine.py::_record_trade_result()`: SignalLog lookup moved up so `atr_at_entry` is available for the classifier; classifier called after MT5-tag determination; `close_comment` written into the new column.

4. **New `exit_reason` enum values** added at the model docstring level (`storage/database.py:131`). Downstream consumers must accept `BE_HIT` and `TRAILING_STOP` in addition to the existing `SL_HIT / TP_HIT / MANUAL / UNKNOWN`. Phase B will introduce `exit_reason_v2` for the retroactive backfill.

5. **Regex word-boundary change considered but rejected.** The original spec proposed `\b(sl|stop\s*loss)\b` to avoid the (claimed) `"SELL"` collision. Once the substring claim was disproved on 2026-05-01, the regex change had no functional value — the substring check wasn't matching what we thought. Defensive value did not justify additional code surface; skipped per project lead instruction (`docs/p.md` 2026-05-01).

### Phase B — retroactive relabel (pending)

Same as before:
1. Add column `trade_results.exit_reason_v2` (additive, preserves existing `exit_reason`).
2. Run classifier on all 314 closed trades; write to `exit_reason_v2`.
3. Tag rows where `exit_reason != exit_reason_v2` with a `mislabel_flag` derived from the comparison.
4. **Validation gate** before commit: spot-check 10 known-mislabel rows + 10 control rows (true SL hits). 0 false positives required — any true SL hit reclassified as BE/TRAILING blocks the commit until the threshold is adjusted.
5. Migrate consumers one at a time once spot-checks pass.

**Severity:** BLOCKING for Phase 7 if the meta-labeler will train on `exit_reason`. Promote to **Phase 7 Blocker #1b**.

---

## Finding 3 — The Apr 10 `ml_direct/XAUUSD` blacklist was a no-op for 18 days

### What was supposed to happen
Commit `b8a2c3b` on 2026-04-10 19:01:37 +0300 wrote a `strategy_blacklist` block to `config/base.yaml`. The commit message said "Blacklist check runs after signal generation but before execution" and rationalised the change with "All top 8 biggest losses were XAUUSD SELL ml_direct". Project lead's mental model since: from Apr 10 onwards, ml_direct/XAUUSD trades are blocked.

### What actually happened
- The engine selects its config via `engine/trading_engine.py::resolve_config_path()` based on `TRADING_MODE` env var. With `TRADING_MODE=paper` (the default), it loads **`config/paper.yaml`**, NOT `config/base.yaml`.
- The Apr 10 commit `b8a2c3b` modified **only `config/base.yaml`**. Verified via `git show b8a2c3b --stat -- config/`: 1 file changed.
- `config/paper.yaml` did NOT receive the blacklist until commit `a00fbb4` (2026-04-28 22:12:26 +0300, AI-002 deployment).
- Between Apr 10 19:01 and Apr 28 21:55 UTC (engine restart following AI-002), the blacklist was inert. Code path existed; data path didn't reach it.

### Quantified impact

| Window | XAUUSD `ml_direct` trades opened | Net PnL |
|---|---:|---:|
| Pre-Apr-10 (no blacklist anywhere) | 24 | **−$29,867.80** |
| Apr 10 → AI-002 (thought-blocked, actually open) | **69** | **+$29,596.80** |
| Post-AI-002 | 1 | −$2.60 |

The single post-AI-002 trade (`56431735932`, opened 2026-04-28 21:05:10 UTC) opened **50 minutes before the AI-002 engine restart at 21:55 UTC** — pre-restart, the engine still had paper.yaml without the blacklist loaded. After the restart no further XAUUSD ml_direct trades opened, and `/pause` was issued shortly after (first paused-scan log entry: 2026-04-28 23:05:00).

So **no trade slipped past an enforced blacklist**. The 22 trades absent from yesterday's audit CSV are mostly "before any effective blacklist" trades, plus the one Apr 28 trade that pre-dated the AI-002 engine restart.

### Why it didn't crater the v3 ledger
Coincidence: the 69 "thought-blocked" trades were **profitable** on the window (gold direction favoured the ml_direct SELL bias). The Apr 10 → Apr 28 window made +$29,596.80 from trades the project lead believed were blocked. This *masked* the bug: there were no losses to investigate, and the ledger looked healthy.

### Proposed actions

1. **Audit `config/base.yaml` vs `config/paper.yaml` for other drift.** AI-004 (config drift detection) was deployed on Apr 29 per yesterday's commits; verify it would have caught this case (it operates at runtime — check whether it was in place during the window in question).
2. **Document this incident** for the May 4 kickoff. Decisions made on the basis of "ml_direct/XAUUSD has been blocked since Apr 10" must be re-examined: any analysis that compared "pre-Apr-10 ml_direct/XAUUSD performance" to "post-Apr-10 (assumed-blocked)" was actually comparing to "still-trading" — the contrast is meaningless.
3. **Recompute headline v3 metrics** with the corrected window. The Phase 8 deferral decision (Vote 2, Apr 28) and the AI-002 elevation rationale were made under the assumption that the blacklist was effective from Apr 10. Re-evaluate whether those decisions still hold given the corrected timeline.

**Severity:** project-management, not technical. The bug is fixed (AI-002 closed it). The implication is interpretive — past decisions were informed by a wrong premise. Flag for May 4 kickoff.

---

## Phase 7 Blocker #1 — status

Per `docs/p.md` (2026-05-01) the redefined Blocker #1 scope is:

| Sub-item | Status | Notes |
|---|---|---|
| (a) Fix CSV exporter | **DONE this session** | `scripts/analyze_all_trades.py:250` now fills `realized_rr` from `risk_reward_actual`. CSV will reflect on next run. |
| (b) Factor inline calculator into reusable function | **DONE this session** | `analysis/rr_calculator.py::realized_rr`. Engine updated to import. |
| (c) Unit test that CSV roundtrips realized_rr | **DONE this session** | `tests/test_rr_calculator.py::TestCSVRoundtrip`. Plus 13 calculator/PF/gate tests. Smoke-run via plain Python passes; full pytest run pending pytest install. |
| (d) Dual-gate PF computation as callable function | **DONE this session** | `analysis/rr_calculator.py::phase7_ship_gate`. Reconciles to audit's $-PF 1.489 on the 76-ticket sample. Documented at `docs/research/phase7_ship_gate_definition.md`. |

Blocker #1 status moves from `OPEN` → `IN_PROGRESS` until the live CSV is regenerated and the test suite is run under pytest. Blocker #1b (the SL_HIT mislabel) is OPEN.

---

## Files modified or created this session

| Path | Action |
|---|---|
| `analysis/__init__.py` | new (empty) |
| `analysis/rr_calculator.py` | new — calculator + PF helpers + dual-gate function |
| `engine/trading_engine.py` | modified — import + delegate to `analysis.rr_calculator` |
| `scripts/analyze_all_trades.py` | modified — fill `realized_rr` from `risk_reward_actual` |
| `tests/test_rr_calculator.py` | new — calculator unit tests + CSV roundtrip test |
| `docs/research/phase7_ship_gate_definition.md` | new |
| `docs/research/ai017_supplemental_findings_2026_05_01.md` | new (this file) |
| `data/trading.db.bak.pre-phase7-prep.20260501T095425Z` | backup snapshot (151 MB) |

No DB rows were modified. No `optimized_params.yaml` changes (per Rule 2). Nothing committed (per Rule 4 / project convention).
