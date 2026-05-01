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
`engine/trading_engine.py:1109-1116`:

```python
comment = (close_deal.comment or "").upper()
if "SL" in comment or "STOP LOSS" in comment:
    exit_reason = "SL_HIT"
elif "TP" in comment or "TAKE PROFIT" in comment:
    exit_reason = "TP_HIT"
else:
    exit_reason = "MANUAL"
```

The substring match `"SL" in comment` matches `"SELL"`. When MT5 returns the original signal comment on a close (e.g., trailing-stop or break-even close paths), the comment contains text like `"ML Direct SELL | conf=56.6%"` — uppercase `"SELL"` contains `"SL"` — the trade is labelled `SL_HIT` regardless of how it actually exited.

### Impact

| Layer | Affected |
|---|---|
| `pnl`, `profit`, `risk_reward_actual`, prices | NOT affected (computed from price fields, not text) |
| `exit_reason`, anything that filters/aggregates by it | corrupted on ~27% of v3 SL_HIT |
| Yesterday's audit's exit-reason narrative for ml_direct (PF 1.49 vs PF 0.46 R:R interpretation) | unaffected for the headline numbers; affected for any "SL_HIT outcomes" narrative |
| Phase 7 meta-labeler training data if it uses `exit_reason` as a label or feature | **CRITICAL** — would learn from corrupted ground truth |
| Direct $ impact of the mislabels (treated-as-loss but actually small profit) | **+$635.80** total — small, but the *count* corruption is the real damage |

### Proposed fix (do NOT relabel data yet — investigation only)

Two-part fix:

**A. Code fix (engine):**
1. Replace the substring check with word-boundary detection AND structural cross-check against price proximity:
   ```python
   import re
   comment = (close_deal.comment or "").lower()
   sl_match = re.search(r"\b(sl|stop\s*loss)\b", comment)
   tp_match = re.search(r"\b(tp|take\s*profit)\b", comment)
   ```
2. Cross-check: if labelled SL_HIT but `|close_price - stop_loss| / |stop_loss - open_price| > 0.10`, downgrade to `BE_HIT` (break-even) or `TRAILING_STOP` based on whether close is near open (BE) or somewhere between open and TP (trailing).
3. Add new `exit_reason` enum values: `BE_HIT`, `TRAILING_STOP`. Update downstream filters.

**B. Retroactive relabel plan:**
1. Add column `exit_reason_v2` to `trade_results` (additive, doesn't disturb existing).
2. Run a one-off backfill that, for each closed trade, computes `exit_reason_v2` using the new logic plus price-proximity cross-check.
3. Tag rows where `exit_reason != exit_reason_v2` with `mislabel_flag = True`.
4. Surface the diff to the dashboard for spot review before any consumer is migrated to `exit_reason_v2`.
5. Migrate consumers (analyze_all_trades.py, dashboard pages, meta-labeler training) one at a time once spot-checks pass.

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
