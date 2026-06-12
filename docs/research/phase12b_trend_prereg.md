# Phase 12b — Cross-Asset Trend Premium (Corrected Re-test) — PRE-REGISTRATION

**Status:** FROZEN — pre-registration is locked before any data is seen beyond the cached yfinance daily used in Phase 12 Discovery. Gates and universe are immutable after this commit.
**Frozen:** 2026-06-12
**Context:** Phase 12 Discovery (commit 9fa6ee2 pre-reg, b09716c results) passed 5 of 6 gates strongly (D1 t=+3.36, D2 OOS Sharpe +0.57, D3 both halves positive, D4 six of seven classes positive, D6 beats passive and survives 1.5x cost). The only failure was D5's max-pairwise-corr<0.70 sub-gate (failed at 0.93 max). The Guardian defect detector (research/guardian/engine.py, DEF-1 rule) flagged D5 as **MIS-SPECIFIED** because its companion metrics are strong: ENB=12.27 of 26 instruments (need ≥10.4, pass), PC1=0.17 (need <0.50, pass). The six high-correlation pairs are all benign within-class duplicates (WTI/Brent crude, bond-curve points ZN/ZF/ZB, S&P/Nasdaq, EUR/GBP). Under the canonical gate set G1–G8 (which deliberately omits max-corr as a result gate per §3 of guardian_gate_spec.md), the same Phase 12 metrics PASS with DSR 0.961 at K=10. This Phase 12b proposal is the remedy called for in §6 of the gate specification: **a separately pre-registered re-test with corrected gate set, plus a structural (ex-ante, ex-performance) universe-pruning step to eliminate the within-class duplicates**. No signal tuning. Identical monthly TSMOM rule. Explicit disclosure: this re-uses partially-seen cached yfinance daily data (26 instruments, 7 classes, 2001-2026 in data/raw_trend/), so it is not a clean holdout; the remedy is correlation-based universe pruning (not performance-based) and performance-neutral under equal-class weighting, so it is not cherry-picking.

---

## 1. Hypothesis (single, falsifiable)

> **Does the cross-asset trend premium exist after removing benign within-class redundancy and applying the canonical gate set?**

The documented trend/momentum risk premium is a real, cost-survivable, out-of-sample, multi-bet phenomenon when tested across diversified asset classes with within-class correlation sub-clusters pruned ex-ante by liquidity/tradability (not performance). This is identical to the Phase 12 hypothesis, tested on the same premise under a corrected gate set that does not mis-specify within-asset-class correlation as a disqualifying result gate.

**Source of edge:** The academic trend/momentum premium documented across asset classes (Moskowitz, Ooi, Pedersen 2012; others). This is not a price pattern; it is an unconditional risk premium — time-series-momentum across diverse asset exposures earns a return not fully explained by conventional risk.

---

## 2. Universe construction — corrected for within-class redundancy

### 2.1 Phase 12b discovery universe — correlation-based pruning (locked ex-ante, before run)

**Starting point:** Phase 12 discovery universe (26 instruments, 7 classes, yfinance daily).

**Ex-ante correlation-based pruning rule (deterministic, not data-driven):**
For each asset class, identify correlation sub-clusters on the full Phase 12 historical data (2001-2026) using pairwise daily-return correlation. **One instrument per sub-cluster, chosen by liquidity/tradability, never by returns.** The pruning rule is:

| Class | Sub-clusters & selected instruments | Rationale |
|---|---|---|
| Equity indices | ES=F (leader, highest volume); drop NQ=F (corr ≥0.84 with ES) | S&P 500 is most liquid |
| Bonds/Rates | ZN=F (10Y, most liquid); drop ZB=F (30Y, corr ≥0.90 with ZN), ZF=F (5Y, corr ≥0.93 with ZN) | Front contract by volume |
| Energy | CL=F (WTI, most liquid); drop BZ=F (Brent, corr ≥0.93 with CL) | West Texas Intermediate is US-centric basket leader |
| Metals | GC=F, SI=F, HG=F, PL=F (four separate metals, low intra-class corr) | No pairs >0.70; all kept |
| Agriculture | ZC=F, ZW=F, ZS=F, SB=F, KC=F (five crops, low intra-class corr) | Distinct commodities; all kept |
| FX (counter-example) | EURUSD=X, USDJPY=X, AUDUSD=X (three majors, drop GBPUSD corr ≥0.74 with EURUSD) | EUR and GBP both euro-adjacent; USD-JPY is structurally different |
| Crypto | BTC-USD, ETH-USD | Only two; low corr; both kept |

**Result:** 20 instruments across 7 classes (vs. 26 in Phase 12). Pruning removes 6 within-class duplicates deterministically by liquidity, not by backtest results.

### 2.2 Holdout (locked, never opened in this pre-test)

A chronologically sequential holdout window is defined: **2024-07-01 .. 2026-06-30 (24 months, OOS).** This will NOT be read until after the pre-registered gates are evaluated on the discovery/train window (2001-01-01 .. 2024-06-30).

---

## 3. Trend rule (canonical, identical to Phase 12 — NO tuning)

Monthly-rebalanced time-series momentum, vol-targeted. Identical to the frozen rule in Phase 12 §4.

| Parameter | Value |
|---|---|
| Frequency | Monthly (month-end close) |
| Signal | sign(trailing 12-month log return) |
| Position lag | 1 month (no lookahead): `pos_prev = (sign·lev).shift(1)` |
| Vol scaling | target 10% ann. / trailing 12-month realized vol, capped at 1× leverage |
| Portfolio weighting | **equal-asset-CLASS weight** (then equal within class) — so no class dominates |
| Rebalance cost | charged on position change only (§4 below) |

---

## 4. Cost model (per asset class, identical to Phase 12)

Charged in return terms on monthly position change (turnover × cost). Base per-side:

| Class | Base cost/side |
|---|---|
| Equity index fut | 2 bps |
| Rates/bonds fut | 1 bps |
| Energy fut | 3 bps |
| Metals | 3 bps |
| Agriculture | 4 bps |
| FX | Phase 5 spread+slippage per pair (existing model) |
| Crypto | 10 bps |

### 4.1 Roll-artifact handling (locked, Phase 12 standard)

yfinance `=F` continuous contracts carry roll jumps. Rule: **winsorize daily log returns at ±15%** before monthly aggregation. Any instrument with >60 such days over its history is flagged in the report (data-quality disclosure), not silently dropped.

---

## 5. FROZEN gates — canonical set G1–G8 (omit max-corr as result gate)

ALL gates below must PASS. Any fail = FAIL. No gate relaxation. **Note: max-pairwise-corr does NOT appear as a hard result gate (unlike Phase 12's D5).** It is a universe-construction diagnostic, per guardian_gate_spec.md §3. The corrected gate set is:

| id | Gate | Criterion | Lesson |
|----|------|-----------|--------|
| **G1** | Economic rationale | `hypothesis` states a source of edge; edge is the documented trend/momentum risk premium (academic, not data-mined) | Kill junk pre-build |
| **G2** | Significance | Equal-class-weight portfolio mean monthly NET return > 0, t-stat ≥ 2.0 (discovery window, 2001-2024-06) | Basic signal |
| **G3** | Deflated Sharpe | DSR(alpha=0.95) passes at registry's K (currently K=11 after recording Phase 12 + Phase 11) | **Multiple testing** |
| **G4** | OOS robustness | OOS(2024-07..2026-06) net mean > 0 AND OOS net Sharpe ≥ 0.30 AND OOS not statistically worse than discovery at 95% (drift check: p > 0.05) | OOS drift (Phase 10 lesson) |
| **G5** | Regime robustness | Net positive return in BOTH discovery halves (first 50%, second 50% chronologically); also tested across defined eras (pre-2015 low-vol vs. 2015+ vol regime) | Single-regime artifact (Carry C5 lesson) |
| **G6** | Breadth | ≥ 4 of 7 asset classes have positive net trend premium (class-level mean, not instrument-level) | Not one-instrument luck |
| **G7** | Cost survivability | Net premium positive at 1.5× base costs AND portfolio net Sharpe > equal-weight buy-and-hold of the same 20-instrument universe | Cost cliff (Rescue lesson) |
| **G8** | Diversification | Strategy returns: ENB ≥ 0.4 × 20 (= ≥ 8.0) AND PC1 variance share < 0.50 (NOT max_corr<0.70) | Genuine independence, not max-corr artifact |

**Pass all 8 → the corrected trend premium is a real, cost-survivable, out-of-sample, multi-bet phenomenon on a non-redundant universe.**

---

## 6. Decision rule (pre-registered, binding)

1. Backtest the 20-instrument discovery universe on the train window (2001-01-01 .. 2024-06-30) with no tuning.
2. Compute metrics and apply gates G1–G8 exactly as written (deterministic Guardian engine in research/guardian/).
3. **If all 8 gates pass:** Proceed to holdout validation (open 2024-07-01 .. 2026-06-30 for OOS confirmation). Record the result and document as a validated edge.
4. **If any gate fails:** Record as FAIL. Do not relax any gate, re-tune any parameter, or post-hoc select a subset. A failure is a result, not a problem to route around.
5. **No gate-defect re-analysis after the run:** If the Guardian engine produces a flag (e.g., ENB strongly passes but some other metric fails), the flag is advisory for a *future, separately pre-registered* hypothesis — never used to justify relaxing this verdict.

---

## 7. Multiple-testing disclosure

This is trial K=11 in the hypothesis registry (data/hypothesis_registry.jsonl). Phase 12 and Phase 11 each consumed one trial; Phase 12b is the next. The Deflated Sharpe bar (G3) rises accordingly. Per López de Prado (2014), the expected maximum Sharpe under K=11 independent trials is higher than under K=10. This pre-registration is frozen at K=11; if the backtest runs, the counter must be incremented immediately (K=12) before any post-hoc hypothesis is proposed.

---

## 8. Caveats (honest, up front)

- **Partial data reuse:** yfinance daily cache (26 instruments, 2001-2026) is re-used from Phase 12 discovery runs. The pruning rule is correlation-based (not performance-based) and **does not re-rank by Sharpe or returns**, so it is not cherry-picking performance-in-hindsight. Equal-class weighting is performance-neutral. However, this is not a clean holdout; treat a marginal pass with appropriate skepticism.
- **Within-class correlation is approximate:** yfinance continuous contracts are approximations (roll-adjusted); exact correlation matrices may differ from live-fed. The pruning rule uses Phase 12's full-history correlation; real-time data may shift cluster membership slightly.
- **Survivorship & asset selection:** Even the 20-instrument universe is a liquid-survivor slice; results do not extend to illiquid or delisted assets.
- **OOS is sequential, not independent:** OOS window (2024-07..2026-06) is the natural forward period after the phase-12 discovery cutoff; it is not an independently designed holdout like a fresh test would be.
- **Cost model is approximate:** Per-class spread+slippage is a proxy for real execution. Micro-structure (tick size, order book depth, roll mechanics) is not modeled per-instrument.

---

## 9. Frozen artifacts (locked before run)

- **Universe list:** 20 instruments (7 classes) as §2.1, deterministically pruned ex-ante.
- **Gate set:** G1–G8 as §5, no max-corr hard gate.
- **Trend rule:** Identical to Phase 12 §3.
- **Cost model:** Per §4.
- **Train window:** 2001-01-01 .. 2024-06-30.
- **OOS window:** 2024-07-01 .. 2026-06-30 (locked, never read until gates evaluated on train).
- **Registry K:** 11 (Phase 12 + Phase 11 + this candidate = K=11; if run, increments to K=12 immediately).

---

## 10. Justification for this re-test (research-advisor findings incorporated)

Phase 12 **FAILED only on D5's max-pairwise-corr sub-gate** (0.93 observed, <0.70 required) while passing 5/6 other evidence gates with strong statistics (D1 t=+3.36, D2 OOS Sharpe +0.57, D3 both regimes, D4 six of seven classes). The Guardian defect detector flagged D5 as **MIS-SPECIFIED** under the canonical gate standard (guardian_gate_spec.md §3, §5): the companion metrics ENB=12.27/26 and PC1=0.17 prove genuine ~12-bet diversification; the six high-correlation pairs are all **benign within-class duplicates** (crude oils, bond curve, equity indices, EUR/GBP). Max-pairwise-corr is a **universe-construction diagnostic**, not a result gate — it fails any liquid multiclass universe with 2+ instruments per class measuring related exposures.

Phase 12b applies the **corrected gate set** (G1–G8 from the canonical template) to the **same underlying phenomenon after removing the within-class duplicates deterministically**. This is the remedy explicitly called for in guardian_gate_spec.md §6: "*a separately pre-registered re-test with corrected gate*." The novelty is procedural (universe pruning + corrected gates), not a new data-mine.

The edge remains novel and sources itself: documented cross-asset trend/momentum risk premium (Moskowitz, Ooi, Pedersen 2012). It does not resemble any other passing hypothesis (phase11_carry is regime-sensitive and distinct; phase12_trend is the same hypothesis, not a different one — phase12b is the corrected re-test of it).

---

End of Phase 12b Pre-Registration.
