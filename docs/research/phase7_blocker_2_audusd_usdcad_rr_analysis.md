# Phase 7 Blocker #2 — AUDUSD/USDCAD R:R Analysis

**Date:** 2026-05-01
**Author:** automated analysis (Claude Code), per `docs/p.md` Phase 2 instructions
**Scope:** analysis only — `data/optimized_params.yaml` is unchanged. Recommendation Path A vs Path B at the end.
**Prior context:** `ai017_rr_audit.md` (2026-04-30) flagged AUDUSD (designed R:R 0.60) and USDCAD (designed R:R 0.625) as having TP < SL by design. This document traces the source.

---

## Provenance

### Git blame on `data/optimized_params.yaml`

Both AUDUSD (atr_sl_mult 2.5 / atr_tp_mult 1.5 → R:R 0.60) and USDCAD (atr_sl_mult 2.0 / atr_tp_mult 1.25 → R:R 0.625) were committed in **commit `0328376`, 2026-03-31 18:32:11 +0300**, message: *"Add pre-flight checks, all 6 strategies to backtest, and optimized params"*.

The same commit added 250 lines to `scripts/run_backtest_all.py` and wrote `data/backtest_results.db`. Earlier values (committed 2026-03-17 in `1ec833e3`) were structural (symbol headers, rsi_period defaults) — the multipliers themselves are all from the 03-31 optimizer run.

### The optimizer

`scripts/optimize_strategy.py` runs an Optuna TPE study per symbol (200 trials by default) sampling:
- `atr_sl_mult` ∈ [0.5, 3.0] step 0.25
- `atr_tp_mult` ∈ [1.0, 5.0] step 0.25
- (plus fast_period, slow_period, rsi_period, atr_period)

Hard constraint: `if result.total_trades < 50: return float("-inf")` — runs producing fewer than 50 trades are rejected outright.

### Optimization objective

`scripts/optimize_strategy.py:107-150`:

```python
# Optimize for Sharpe ratio (penalize few trades)
if result.total_trades < 50:
    return float("-inf")

# Multi-objective score: Sharpe + profit_factor bonus - drawdown penalty
score = result.sharpe_ratio
if result.max_drawdown_pct > 50:
    score -= (result.max_drawdown_pct - 50) * 0.05

return score
```

The comment claims "Sharpe + profit_factor bonus" but **the code only returns Sharpe** (with a drawdown penalty if MDD > 50%). The promised PF bonus is not implemented.

**Why this matters for the R:R<1 designs:**
Sharpe rewards smooth, frequent wins with low return-volatility. A strategy that wins often (high WR) with small profits and rare large losses produces a high mean / low std-dev — high Sharpe — because the rare large losses are dispersed over many bars and don't dominate the std-dev. This is exactly the signature of TP < SL designs. The optimizer was not asked to maximise expected value; it was asked to minimise return volatility. It found a corner that does so by design.

---

## The backtest run that produced these params

### AUDUSD

Per `data/backtest_results.db::backtest_runs`, **23 AUDUSD configs were tested** across 7 strategies × 2 timeframes (H4, D1). Verdicts:

- **PASS = 1** (AUDUSD/ml_filtered_sma/D1: n=79, WR 73.4%, PF **1.58**, Sharpe **5.41**, MDD 3.6%, expectancy +$173.25/trade, score 90.9, grade S)
- A near-identical row tagged on `sma_crossover/D1` with the same metrics (artifact of how ml_filtered SMA falls back to plain SMA when ML signal is absent — same trades drove both).
- All other 21 AUDUSD/* configs FAILED (most for negative EV, PF<1, or MDD>15%).

### USDCAD

Per `data/backtest_results.db::backtest_runs`, **40 USDCAD configs were tested** across 7 strategies × 2 timeframes. Verdicts:

- **PASS = 0**
- Best: `stop_hunt_reversal/D1` grade B, Sharpe 1.00, expectancy +$22.52, PF 1.06 — but did not pass approval thresholds (PF below 1.15 floor).
- Most configs are net-negative and drawdown-ridden.

USDCAD has **no approved strategy in `data/backtest_approved.yaml`** despite having entries in `data/optimized_params.yaml`. The two files are decoupled — `optimize_strategy.py` writes to the params file regardless of approval verdict.

---

## Three crippling premise issues

### Issue 1 — Timeframe mismatch (most consequential)

`config/paper.yaml` line 39: `timeframes: { primary: "H1", secondary: "H4", confirmation: "M15" }`.

The live engine runs **H1**. But:
- AUDUSD/ml_filtered_sma/D1 backtest (the only PASS): PF 1.58, Sharpe 5.41 — *on daily bars*.
- AUDUSD/ml_filtered_sma/H4 backtest: PF 0.867, Sharpe **−1.48**, expectancy **−$46/trade**, FAIL.
- No H1 backtest exists in `backtest_runs` for AUDUSD.

The "approved" R:R<1 design at PF 1.58 is conditioned on a daily bar generation rate. On 4-hourly bars the same strategy turns into a money-loser. We have no evidence about H1.

Live v3 (engine 2.4) actuals on AUDUSD `ml_filtered_sma` (which is what the H1 engine actually trades): **n=5, WR 80%, $-PF 0.39, R-PF 0.32**. Sample is small, but it lines up with the H4 failure mode.

### Issue 2 — Sharpe-not-EV objective

The optimizer maximises Sharpe. Sharpe ≠ EV. For trading-system selection, EV (per-trade expectancy) is the load-bearing metric — it's what compounds the bankroll. Sharpe is a statistical property of the return series, useful for portfolio-construction context (volatility-adjusted return) but the wrong primary objective when the question is "should I run this strategy at all?". A strategy with EV near zero but very smooth returns can score Sharpe 5+ and still produce no compounding edge. AUDUSD/ml_filtered_sma/D1's Sharpe 5.41 on 79 D1 trades is a textbook example: the EV ($173/trade) is positive but the Sharpe is artificially inflated by low return-variance — and the strategy fails on H4/H1 where bar-to-bar variance is structurally different.

### Issue 3 — n_trades ≥ 50 hard floor pushes toward high-frequency / high-WR configs

Combined with Sharpe objective: the optimizer rejects (returns −∞) any config that doesn't generate ≥ 50 trades over the backtest window. On D1 over a typical 1–2 year window, that floor is hard to clear unless the strategy fires often. Configs with conservative high-R:R signal generation get filtered out before Sharpe ranking even runs. Result: the surviving solution space is biased toward over-trading and small-target captures — the same shape that produces high WR and low R:R. The 50-trade floor was meant as a statistical-significance guard, but here it's actively selecting for the failure mode.

---

## Live v3 reality check

### AUDUSD (n=15 v3 trades total)

| Strategy | n | WR | $-PF | R-PF | mean planned R:R |
|---|---:|---:|---:|---:|---:|
| asia_breakout | 2 | 100% | inf | inf | 0.66 |
| bollinger_bounce | 3 | 67% | 0.76 | 0.44 | 0.49 |
| ml_direct | 2 | 100% | inf | inf | 0.40 |
| **ml_filtered_sma** | **5** | **80%** | **0.39** | **0.32** | **0.70** |
| stop_hunt_reversal | 3 | 100% | inf | inf | 0.76 |

Net AUDUSD v3 PnL: **+$101.60** (basically random walk).

### USDCAD (n=11 v3 trades total)

| Strategy | n | WR | $-PF | R-PF | mean planned R:R |
|---|---:|---:|---:|---:|---:|
| bollinger_bounce | 8 | 62.5% | 0.18 | 0.21 | 0.71 |
| ml_filtered_sma | 3 | 67% | 0.17 | 0.15 | 0.48 |

Net USDCAD v3 PnL: **−$544.01**.

USDCAD's WR sits exactly on the 62.5% break-even threshold yet PF is 0.18 — confirming that the WR-threshold reasoning is fragile in live conditions. The realized R:R drift (planned 0.5–0.7, realized 0.15–0.21 in R-units) replicates the same pattern AI-017 found on ml_direct.

---

## Path A vs Path B

### Path A — Document and accept

> Add a note in optimized_params.yaml explaining why R:R < 1 is intentional. Requires WR > 62.5% (AUDUSD) or 61.5% (USDCAD) to break even. Confirm v3 actual WR exceeds these thresholds.

**Premise check — fails on three counts:**

1. The "approved" backtest that justifies the R:R<1 design is a D1 backtest. The live engine runs H1. Acceptance based on D1 numbers is a category error.
2. v3 live AUDUSD ml_filtered_sma has WR 80% (above the 62.5% threshold) but $-PF 0.39 — the threshold reasoning *demonstrably fails in production*. The realized R:R is materially worse than the planned R:R, and the WR-breakeven calculation only holds at planned R:R.
3. USDCAD has no approved strategy in any timeframe at any backtest run. Path A would amount to documenting "we kept these multipliers despite zero supporting evidence", which is the opposite of what Path A is designed for.

**Verdict on Path A: not supported by data.**

### Path B — Re-optimize for EV

> Re-optimize for expected value, not PF/WR. Likely produces R:R ≥ 1 with possibly lower WR. 1–2 hours of optimization + re-validation.

**Premise check — supported on multiple counts:**

1. Sharpe is the wrong objective for "should we run this strategy". Per-trade expectancy is the right one.
2. The optimizer must run on H1 (the live timeframe), not D1.
3. The 50-trade floor needs reframing — either dropped, replaced with a confidence-interval guard (e.g., Wilson lower bound on EV), or scaled by timeframe (D1 has fewer bars than H1, so 50 trades on D1 = fundamentally different statistical regime).
4. Add a hard constraint: **`atr_tp_mult >= atr_sl_mult`** (R:R ≥ 1). The Phase 7 ship gate (R-PF ≥ 1.3 + $-PF ≥ 1.0, see `phase7_ship_gate_definition.md`) is much harder to meet with R:R < 1 — making a constraint here aligns the optimizer with the ship gate rather than fighting it.
5. For USDCAD: do not auto-write to optimized_params.yaml unless the strategy passes `backtest_approved.yaml` thresholds. The current decoupling between the two files is a hidden mis-feature.

**Verdict on Path B: supported by data; recommended.**

### Recommendation

**Path B** — but with three additions to the playbook description:

| Addition | Reason |
|---|---|
| Run the optimizer on **H1** for paper-mode targets | Eliminate the D1/H1 timeframe mismatch — the single biggest validity issue |
| Add hard constraint `atr_tp_mult >= atr_sl_mult` | Make the optimizer respect Phase 7 ship-gate semantics rather than fight them |
| Tighten `optimize_strategy.py → optimized_params.yaml` write logic to gate on approval verdict | Prevent USDCAD-style cases where un-approved strategies still get params persisted |

**Out of scope of Path B but worth noting for May 4 kickoff:**
- USDCAD has not produced a profitable strategy in any backtest. Adding it to the live trading symbol set may itself be the wrong question — the right one might be "should USDCAD be traded at all?" That decision should precede any params re-optimisation. Same logic potentially applies to symbols beyond USDCAD; full audit warrants a separate work item.

---

## AI-004 backward audit (per `docs/p.md` add-on)

### Question
Would AI-004 (config drift detection, deployed Apr 29, commit `df45115`) catch a base.yaml-vs-paper.yaml divergence like Apr 10's?

### Implementation
`engine/trading_engine.py:95-117`:

```python
def _compute_config_snapshot(self) -> dict:
    on_disk_bytes = Path(self._config_path).read_bytes()
    on_disk_hash = hashlib.sha256(on_disk_bytes).hexdigest()[:16]
    ...
```

`_check_config_drift()` (line 133+) re-hashes the same `self._config_path` every 6 scans and warns if the hash changes.

### Verdict
**AI-004 would NOT catch the Apr-10 case.** It hashes only the loaded config file. With `TRADING_MODE=paper`, `self._config_path = "config/paper.yaml"`. AI-004 monitors paper.yaml in isolation. If someone edits `base.yaml` (as in Apr-10's `b8a2c3b`) but not `paper.yaml`, AI-004's drift check on paper.yaml correctly reports "no drift" — and the engine never cross-references base.yaml.

**Gap class:** AI-004 detects single-file in-memory-vs-on-disk drift. It does NOT detect cross-file divergence between sibling configs that should remain synchronised (base.yaml ↔ paper.yaml ↔ live.yaml).

### Proposed AI-004 enhancement (new sub-blocker recommended)

Two layers:

1. **Multi-file snapshot:** at startup, hash all of `base.yaml`, `paper.yaml`, `live.yaml`, log each fingerprint. On every drift check, re-hash all three. Alert on any change to any file, not just the loaded one.
2. **Cross-config consistency check:** at startup AND on each drift check, verify that the **`strategy_blacklist`** entries are identical across base.yaml and the active mode-specific config. The Apr-28 AI-002 commit message explicitly states "Both configs MUST stay synchronized until config-parity CI guard (AI-004) lands" — but AI-004 as shipped doesn't actually enforce that parity. AI-004 should enforce it at runtime.

Recommendation: open `AI-004b` (or amend AI-004 status) for these enhancements. Severity is BLOCKING for live trading (the Apr-10 case would have lost real money in live mode); WARN-level for paper.

---

## Recommended kickoff agenda items

1. **Path B approval** — explicit go-ahead to re-optimize AUDUSD on H1 for EV with R:R ≥ 1 constraint. (~1–2h of compute + 1h validation review.)
2. **USDCAD scope decision** — should USDCAD trade any strategy? Decide before re-optimisation effort.
3. **AI-004b** — enhance AI-004 to monitor cross-file config divergence. (~2h work.)
4. **Optimizer objective change** — confirm switch from Sharpe to EV (or risk-adjusted EV). Affects all future symbol params, not just AUDUSD/USDCAD.
5. **Premise re-examination on AI-019** (already on agenda from yesterday) — folds in here because the same kind of premise drift produced both findings.

---

## Files affected this session

- This document (new).
- `data/improvements.db` (will be updated with AI-004b suggestion + Path B recommendation note when checkpoint cleared).
- `data/optimized_params.yaml`: **NOT modified** (per Rule 2).

## Cross-references

- `docs/research/ai017_rr_audit.md` — original AI-017 audit
- `docs/research/ai017_supplemental_findings_2026_05_01.md` — corrections + 3 new findings (incl. AI-019)
- `docs/research/phase7_ship_gate_definition.md` — dual-gate PF definition
- `data/backtest_results.db::backtest_runs` — source for AUDUSD/USDCAD verdict counts
- `data/optimized_params.yaml` — params under audit
- `scripts/optimize_strategy.py:107-150` — objective function
- `engine/trading_engine.py:95-160` — AI-004 implementation
