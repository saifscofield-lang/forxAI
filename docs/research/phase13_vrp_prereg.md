# Phase 13 — Volatility Risk Premium (VRP) — Tradable Short-Vol (VXX/SVXY) — PRE-REGISTRATION

**Status:** FROZEN — pre-registration is locked before any data is seen or any backtest run. Gates, instruments, and rule are immutable after this commit.
**Frozen:** 2026-06-12
**Trial:** K=12 in `data/hypothesis_registry.jsonl` (phase12b_trend was K=11).

**Context.** All 11 prior registry hypotheses are **price-derived** (direction, momentum, RSI, MACD, carry rate-differentials, trend) and all FAILED. Failure taxonomy: (1) no directional edge in price (ml_direct AUC 0.51); (2) false price premises (rsi_reversal, donchian); (3) thin edges that die post-cost (sma, macd_m15 PF 0.857, macd_m15_d1filter 0.898, xauusd_d1); (4) single-regime artifact (phase11_carry, USDJPY-hiking only); (5) OOS drift (crypto_tsmom); (6) marginal edge killed by deflated Sharpe at rising K (phase12b DSR 0.907<0.95 @K=11). **VRP is the first NON-price hypothesis:** its signal comes from the options/volatility market (implied vs realized vol), a different information domain, with a documented economic mechanism — the variance risk premium (Bakshi-Kapadia, Carr-Wu): hedgers pay a persistent insurance premium (implied > realized), and the short-vol seller earns it.

**Implementation tightening (vs the Stage-1 draft).** The draft harvested VRP via a *synthetic variance-swap on the untradable `^VIX` index*, which risks a circular "the premium exists in the index" result rather than a tradable edge. This frozen version instead trades the **real, tradable** short-vol ETPs (`VXX` short / `SVXY` long) whose price series already embed real roll costs and real tail events (Feb-2018, Mar-2020). A PASS therefore means an **implementable, cost-and-tail-surviving** edge, not an index fact.

---

## 1. Hypothesis (single, falsifiable, economic)

> **Can the variance risk premium be harvested with a positive, cost-survivable, out-of-sample return via a tradable, defined-risk short-volatility position — without being wiped out by volatility spikes?**

The VRP is an economic phenomenon (insurance demand), not a price pattern. Short-vol ETPs (`VXX`) structurally decay because the VIX-futures curve is usually in contango (the premium); shorting that decay (or holding its inverse) harvests the VRP, in exchange for bearing the left tail when vol spikes. The edge is sourced from the volatility market, not price history, and is claimed regime-robust because hedging demand persists across rate and vol regimes — unlike carry (single-regime) or price momentum (exhausted).

---

## 2. Instruments & data (locked, yfinance — all free)

### 2.1 Tradable instrument (the return source)
- **`VXX`** — iPath Series B S&P 500 VIX Short-Term Futures ETN. **PRIMARY: the strategy is SHORT `VXX`** (return = −1 × `VXX` daily total return). Real, tradable, roll costs embedded in price.
- **`SVXY`** — ProShares Short VIX Short-Term Futures ETF (long). **ROBUSTNESS CROSS-CHECK only.** Note the locked caveat: SVXY was −1× before 2018-02 and −0.5× after the Feb-2018 rebalance — a documented instrument-mechanics artifact, so it is a secondary check, not the primary series.

### 2.2 Signal inputs (decide WHEN to be short vol)
- **`^VIX`** — 30-day implied vol (CBOE close).
- **`^GSPC`** — S&P 500 close → realized vol = trailing 21-day std of daily log returns, annualized.
- **`^VIX3M`** — 3-month implied vol → term-structure carry signal (contango = `^VIX` < `^VIX3M`).

### 2.3 Windows (locked)
- **Train (in-sample):** 2010-01-01 .. 2023-12-31. Includes the real Aug-2015, Feb-2018, Mar-2020 vol spikes. (If the continuous `VXX`/VXXB series in yfinance begins later than 2010, use the earliest clean available start and DISCLOSE it in the results — do not silently truncate.)
- **Holdout (OOS):** 2024-01-01 .. 2026-06-30. **LOCKED — not read until all gates evaluated on train.**

---

## 3. Defined-risk rule (FROZEN ex-ante — no tuning)

| Parameter | Value |
|---|---|
| Frequency | Daily mark, monthly signal refresh (month-end) |
| Signal | `VRP_premium = ^VIX − realized_vol_21d` **AND** curve in contango (`^VIX < ^VIX3M`) |
| Position | If both conditions hold → **SHORT `VXX`** at a **fixed fractional notional of 20% of capital** (the defined-risk cap); else **FLAT** |
| Leverage | None. Position is a fixed 20% sleeve; the other 80% is cash (earns 0% — conservative). |
| Defined-risk mechanism | The 20% fractional sizing IS the capped-loss structure: even a +100% `VXX` day costs ≤20% of capital. No naked unlimited exposure. |
| Rebalance | Month-end; reset to 20% short if signal on, flat if off |
| Stop | Hard intramonth stop: if the short sleeve loses >50% of its own value, close to flat until next month-end signal |

**No parameter search.** The 20% sleeve, 21-day realized window, month-end frequency, and contango filter are fixed before the run. They are not optimized on results.

---

## 4. Cost model (locked, realistic)

`VXX`'s roll cost is already embedded in its price (we trade the real series), so explicit costs are only execution + borrow:

| Component | Cost |
|---|---|
| ETF round-trip spread + slippage | 5 bps per rebalance |
| Short borrow fee on `VXX` (locked, conservative) | 6% annualized ≈ 0.5 bps/day while short |
| **Stress test** | all gates re-checked at **1.5× costs** (G7) |

---

## 5. FROZEN gates — canonical G1–G8 (VRP-adapted)

ALL must PASS. Any fail = FAIL. No relaxation, no re-tune, no post-hoc defect re-analysis.

| id | Gate | Criterion | Lesson |
|----|------|-----------|--------|
| **G1** | Economic rationale | Edge stated as the variance risk premium (insurance demand), not a price pattern. ✓ | Kill junk pre-build |
| **G2** | Significance | Mean monthly NET return > 0 and t-stat ≥ 2.0 on the train window | Basic signal |
| **G3** | Deflated Sharpe | DSR(α=0.95) passes at **K=12** | Multiple testing (binding) |
| **G4** | OOS robustness | OOS net mean > 0 AND OOS net Sharpe ≥ 0.30 AND drift p(OOS<train) > 0.05 | OOS drift (Phase 10) |
| **G5** | Vol-regime robustness | Net return > 0 in EACH vol regime present in train: low (`^VIX`≤20), mid (20–30), high (>30) | Single-regime artifact (Carry) |
| **G6** | Consistency / breadth | ≥ 55% of train calendar months net-positive (not 3–4 lucky months) | Not luck/single-event |
| **G7** | Tail + cost survival | (a) net positive at 1.5× cost; (b) **max drawdown < 30% across the REAL Feb-2018 + Mar-2020 + Aug-2015 episodes in-sample**; (c) net Sharpe > buy-and-hold `^GSPC` Sharpe | Cost cliff (Rescue) + the short-vol left-tail original sin |
| **G8** | Scope / no-leverage | No leverage; defined-risk fixed-fractional sizing; **SPX-vol-only universe stated ex-ante** (gold/oil/bond vol = separate future pre-regs). Single-instrument → ENB/PC1 diversification gate N/A, stated explicitly. | Scope lock |

**Pass all 8 → VRP is a real, tradable, regime-robust, tail-surviving, OOS edge — the project's first validated non-price edge.**

---

## 6. Decision rule (binding)

1. Backtest the short-`VXX` rule on the train window with §4 costs. No tuning.
2. Apply G1–G8 via the deterministic Guardian engine.
3. **All 8 pass on train** → open the locked OOS holdout, re-check G4, document as validated.
4. **Any gate fails** → record FAIL. No relaxation, no re-tune, no regime/subset cherry-pick, do NOT open OOS. A failure is a result.
5. No post-hoc gate-defect re-analysis: any engine flag is advisory for a *future, separately pre-registered* hypothesis only.

---

## 7. Multiple-testing disclosure

Trial **K=12**. The deflated-Sharpe bar (G3) rises with K. Academic VRP Sharpe (~0.8–1.2) is **pre-cost, pre-multiple-testing, pre-OOS** and is NOT a gate — it is aspirational. The binding bars are G3 (DSR at K=12) and G4 (OOS Sharpe ≥ 0.30 post-cost). A train Sharpe near ~0.6–0.7 (like phase12b) would likely FAIL G3 at K=12; the edge must be genuinely strong to pass.

---

## 8. Caveats (honest, up front)

- **ETP mechanics:** `VXX` is an ETN (credit/rebalance mechanics); the series has had a 2019 reverse split and the iPath-A→iPath-B (VXXB) transition. Use yfinance's adjusted continuous series and disclose any split/transition artifact; flag any day with |return| > 50% for inspection (real vol spikes are expected, data errors are not).
- **Borrow availability:** shorting `VXX` assumes locate + the 6% borrow in §4; in practice borrow can spike during stress. The `SVXY`-long cross-check (no borrow) bounds this risk.
- **In-sample tail:** Feb-2018/Mar-2020 are in the train window, so G7 proves "survives KNOWN crises," not "handles unknown future ones." The OOS window provides genuine forward tail data only if a spike occurs in 2024–2026.
- **Cash drag:** the 80% cash sleeve earns 0% (conservative); a real book would earn the risk-free rate, so live returns would be modestly higher — we deliberately understate.
- **Single instrument:** SPX-vol only. No multi-asset extension in this pre-reg.

---

## 9. Frozen artifacts

- **Instruments:** `VXX` (short, primary), `SVXY` (long, robustness); signals `^VIX`, `^GSPC`, `^VIX3M`.
- **Rule:** short 20% sleeve when `VRP_premium>0` AND contango; flat otherwise; 50% sleeve stop; §3.
- **Cost:** 5 bps/rebalance + 6% borrow; gates re-checked @1.5×.
- **Train:** 2010-01-01 .. 2023-12-31 (or earliest clean `VXX` start, disclosed).
- **OOS:** 2024-01-01 .. 2026-06-30 (locked).
- **Gates:** G1–G8 (§5). **Registry K:** 12.

---

## 10. Why this differs from all 11 prior failures

First **non-price** hypothesis (options/vol market, not price history); documented economic mechanism (insurance premium), not a data-mined pattern; **tradable real instrument** (short `VXX`) with embedded real costs and real tail events, not a synthetic index construct; regime-robustness and tail-control **locked ex-ante** (G5, G7). If it fails, it fails on legitimate grounds (DSR at K=12, OOS drift, cost, or the real left tail) — never on a mis-specified gate or exhausted price space.

End of Phase 13 Pre-Registration (frozen).
