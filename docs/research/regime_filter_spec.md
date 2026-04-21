# Phase 10.5 — Regime Filter Specification (DRAFT)

*Author: Claude Code*
*Drafted: 2026-04-21*
*Status: **DRAFT — awaiting user confirmation before implementation (Phase 10.5 step 2)***

---

## 1. Purpose

Address the whipsaw-in-chop failure mode exposed by Phase 10 step 4:
- Training Sharpe 1.27 (LO/12w) collapsed to OOS Sharpe 0.55 on a 69-week window dominated by a bear/sideways regime.
- Fold 4 (≈2022 crypto winter) had negative Sharpe (−0.75) in both train-window variants — regime-dependent performance is the core fragility.
- Ungated strategy returns are essentially a vol-targeted long-crypto basket with momentum timing. When momentum and market direction disagree, the strategy pays turnover cost without earning return.

**Filter hypothesis:** In high-volatility regimes, momentum signals are less reliable (more false positives). Disabling long entries above a volatility threshold should preserve signal in trending regimes while avoiding whipsaw in chop.

This is a rescue attempt, not a signal improvement. If the filter adds Sharpe lift in OOS, v4 moves to Phase 11 (paper trading). If not, v4 crypto-momentum is formally rejected and the user pivots to a different Phase-10 track.

---

## 2. Strategy context (what we are filtering)

The filter is an **overlay on the unchanged LO/12w TSMOM strategy** from Phase 10 step 3:

| Strategy parameter | Value |
|---|---|
| Direction | Long-only |
| Momentum lookback | 12 weeks (sum of log returns) |
| Vol estimator | 24-week rolling stdev × √52 |
| Vol target | 10% annualized |
| Per-asset weight | `sign(mom) × (target_vol / N_active) / σ_asset`, capped at ±1.0 |
| Weight lag | 1 week |
| Rebalance | Weekly (W-FRI close) |
| Transaction cost | 0.1% per side |
| Universe | BTC/USDT, ETH/USDT, BNB/USDT, SOL/USDT (dynamic — each asset active from listing) |

The filter does **not** change any of the above. It only decides whether to apply the computed weights or zero them out for a given week.

---

## 3. Signal definition

### 3.1 Basket volatility

Let `r_i(t)` be the weekly simple return of asset `i ∈ {BTC, ETH, BNB, SOL}` at week `t`. The **basket return** is the equal-weighted average of **active** assets at week `t`:

```
r_basket(t) = mean( r_i(t) for i in active_assets(t) )
```

Where `active_assets(t)` = assets with a weekly close both at `t` and `t-1`.

### 3.2 Rolling vol

The **4-week rolling basket volatility** is the sample stdev of the last 4 weekly basket returns:

```
vol_basket(t) = stdev( r_basket(t-3..t), ddof=0 ) × √52
```

(Annualized with the √52 factor for comparability with the 10% target vol used in strategy sizing.)

### 3.3 Threshold (no lookahead)

The threshold is the **80th percentile of `vol_basket`** computed from **training data only**:

```
THRESHOLD = percentile_80( vol_basket(t) for t in [2017-08-17, 2024-12-31] )
```

Locked at end of training period. Applied verbatim to OOS (2025-01-01 onward). The OOS data is **never** used to set or adjust the threshold.

### 3.4 Filter rule

At each weekly rebalance `t`, compute `vol_basket(t)` using only data available at `t`. Then:

```
if vol_basket(t) > THRESHOLD:
    weights(t) = 0 across all assets    # sit in cash for next week
else:
    weights(t) = unchanged strategy weights
```

In words: **when the basket is more volatile than 80% of training-period history, go to cash for the next week. Otherwise, behave exactly like the ungated strategy.**

The lag convention matches the base strategy: the filter decision at close of week `t` affects the return earned in week `t+1`.

---

## 4. Edge cases and dynamic universe

| Situation | Handling |
|---|---|
| Fewer than 4 weeks of basket return history | Filter inactive (weights unchanged); impossible after week 4 of dataset |
| Fewer than 2 active assets | Basket return = single-asset return; filter still computes vol, still applies |
| BTC-only period (pre-ETH-and-BNB, 2017-08-17 to 2017-11-09) | Not relevant — BTC/ETH both listed on 2017-08-17; basket has 2 assets from week 1 |
| NaN in `r_basket` at week `t` | Skip — filter inactive that week (no replacement/interpolation) |
| Training period has <50 observations | Threshold unreliable; fail loudly and stop (cannot happen with current data: training window has ~380 weeks) |

---

## 5. Output — comparison metrics

The filter is evaluated by comparing **gated** vs **ungated** LO/12w on the OOS window (2025-01-01 → latest) using the exact same metrics as Phase 10 step 4:

| Metric | Gated OOS | Ungated OOS (baseline) |
|---|---|---|
| Sharpe (ann., weekly) | ? | 0.553 |
| Sortino | ? | 1.477 |
| CAGR % | ? | +3.56% |
| Max drawdown % | ? | −4.44% |
| Hit rate monthly | ? | ? (step 4) |
| Weekly turnover (avg) | ? | ? |
| Weeks with active exposure | ? | ? |

Also: **what fraction of OOS weeks did the filter fire?** (% of weeks with zeroed weights). Expect roughly 20% by construction (80th-percentile threshold on training data), but OOS frequency may differ — a useful diagnostic.

---

## 6. Gate criteria (locked — apply the same evaluation_report.md §7.3 thresholds as step 4)

Gated LO/12w will be tested against:

1. **OOS Sharpe ≥ 0.4** after costs (absolute)
2. **OOS MaxDD ≤ 25%** (absolute, ≥ −25%)
3. **OOS within 30% of train Sharpe** (drift)
4. **OOS Sharpe > Buy-and-Hold BTC Sharpe** (OOS window)

Plus one additional gate specific to the filter:

5. **Gated OOS Sharpe > Ungated OOS Sharpe** — filter must demonstrably add value, not just match baseline

**Pass condition:** all 5 gates GREEN → recommend Phase 11 paper trading.
**Fail condition:** any of 1–4 RED → v4 crypto-momentum formally rejected; user pivots.
**Inconclusive:** gate 5 FAIL but 1–4 GREEN → filter is neutral; ungated LO/12w with known regime dependence is the honest product. Discuss before proceeding.

---

## 7. Scope of this spec — intentionally narrow

**This spec defines one filter, one knob, one evaluation.** Explicitly **not** in scope:

- ❌ Parameter sweep over percentile thresholds (70/75/80/85/90) — risks in-sample reoptimization
- ❌ Alternative filter families (correlation-spike, trend-strength, regime-HMM)
- ❌ Changes to the underlying TSMOM strategy parameters
- ❌ Combining multiple filters
- ❌ Adjusting the 4-week vol window length

If the single-knob 80th-percentile filter fails the gates, we **reject v4 crypto momentum**, not iterate on the filter. Iterating would reintroduce the exact overfitting problem Phase 10 step 4 is designed to detect.

The only scope expansion allowed **after** a GREEN result: verify robustness by sweeping the 80th-percentile knob to {70, 75, 85, 90} — **only** if the 80th percentile passed, to confirm the result isn't knife-edge. This is a sanity check, not a parameter search.

---

## 8. Known risks and caveats

1. **Short OOS window.** 69 weeks. If the filter fires on ~20% of weeks, that's ~14 filtered weeks in OOS — small sample. Result will be noisy.
2. **Training-data threshold may understate OOS vol.** If 2025-2026 structurally has higher basket vol than training-period typical, the filter will fire more often than 20%, possibly zeroing most OOS weeks. Report the actual OOS fire rate and flag if >40%.
3. **Vol as a regime signal is lagging.** By the time vol spikes, the chop has already happened. The filter may help avoid *continuation* of chop but won't avoid the initial drawdown. Acceptable for this experiment.
4. **Correlation with known regime indicators.** The 80th-percentile vol trigger correlates with VIX spikes, credit spreads, risk-off episodes. If we pass OOS, check that the filter's activation dates align with known market stress (plausibility check, not causation proof).
5. **No backtest-validated benefit.** The AQR / Hurst literature on crypto-TSMOM-with-vol-filter is thin. This is a plausible heuristic, not a proven overlay. Treat any positive result cautiously.

---

## 9. Implementation plan (Phase 10.5 steps 2-5)

Steps are **gated sequentially**; each requires user sign-off before the next.

| Step | Deliverable | Artifact |
|---|---|---|
| **2.** Implement filter as overlay | Drop-in function `apply_regime_filter(weights, basket_returns, threshold)` + threshold computation from training data | `scripts/research_tsmom_crypto_gated.py` |
| **3.** Re-run full IS backtest (gated) | Same 8-variant grid as step 3 for diagnostic comparison OR just primary LO/12w gated vs ungated | Update `tsmom_runs` with `crypto_*_gated` scopes |
| **4.** Re-run OOS validation (gated) | LO/12w gated on held-out 2025-01 → latest | Same format as step-4 OOS report |
| **5.** Compare gated vs ungated | Side-by-side metrics table + 5-gate scorecard + plot showing where the filter fired | `docs/research/regime_filter_results.md` |

Estimated wall time: 2-3 hours of research compute + reporting, given step 3-4 infra already exists.

---

## 10. Files that will change

**New:**
- `scripts/research_tsmom_crypto_gated.py` — implementation
- `docs/research/regime_filter_results.md` — step 5 comparison report
- `docs/research/regime_filter_equity.png` — gated vs ungated equity curves
- `data/research/tsmom_crypto_gated_metrics.csv` — numeric results

**Modified:**
- `improvements.db::tsmom_runs` — new rows with scope `crypto_LO_12w_c10bps_gated_{train,oos}`
- `improvements.db::go_no_go_decisions` — new row after step 5 results
- `improvements.db::phase_steps` — Phase 10.5 steps 2-6 status updates
- `docs/research/decision_log.md` — step-5 entry
- `dashboard/pages/14_v4_Crypto_Status.py` — render gated vs ungated alongside existing tables

**Untouched:**
- Underlying strategy code (`scripts/research_tsmom_crypto.py`) — the filter is an overlay, not a modification
- Raw crypto data (`data/raw_crypto/`) — no data changes needed

---

## 11. Open questions for user

Before I implement (step 2), please confirm or override:

- [ ] **Basket definition:** equal-weighted mean of active asset returns (my default). Alternative: vol-target-weighted basket matching strategy's own weights (more sophisticated but makes filter performance entangled with strategy vol-targeting — harder to attribute).
- [ ] **Vol window:** 4 weeks (per your seed). Alternative: 8 weeks (smoother, less whippy threshold; may miss sharp regime shifts).
- [ ] **Threshold source:** training window only, end-of-training snapshot (my default — avoids lookahead). Alternative: rolling threshold (e.g. trailing 2-year percentile, updated weekly) — adaptive but introduces a second free parameter.
- [ ] **Scope clarification:** Apply the filter **only** to LO/12w (primary rescue target), or **also** to LO/12m (reporting consistency)? I recommend LO/12w only; LO/12m failed the absolute Sharpe gate too decisively to rescue with a filter.
- [ ] **Robustness sweep:** Run the {70, 75, 85, 90}-percentile sensitivity sweep only if 80th passes? Or skip the sweep entirely and take a pass-at-80 result as-is?

Default answers (if you just say "approve"): basket=equal-weighted, window=4w, threshold=training-snapshot, scope=LO/12w only, sensitivity sweep only on pass.

---

*End of draft. Confirm or amend, and I'll run step 2 (implementation).*
