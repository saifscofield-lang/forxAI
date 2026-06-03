# Phase 12 — Cross-Asset Trend Premium — PRE-REGISTRATION

**Status:** DRAFT — awaiting owner approval before FREEZE. Once approved and committed,
gates and universe are LOCKED before the test is run. No edits after seeing results.
**Drafted:** 2026-06-03
**Context:** Price-only TA closed (rescue), carry closed (Phase 11). Inventory of 13
candidates showed the ONLY OOS life is trend/momentum on high-vol / diverse instruments;
the best (XAUUSD+D1) failed X2 walk-forward purely from too-few independent folds
(one symbol). This tests the trend premise where it can actually be powered: across
asset classes. Smoke test (5 instruments, `scripts/trend_smoke_test.py`) validated
data + plumbing: ENB 4.79/5, PC1 0.27, yfinance gold vs MT5 gold corr 0.985.

---

## 1. Hypothesis (single, pre-committed)

> **Does a measurable trend premium exist across multiple asset classes, after costs,
> out-of-sample?**

A diversified time-series-momentum portfolio earns a positive, cost-survivable,
out-of-sample return that is a genuine multi-bet phenomenon (not one macro bet
repeated). This is *non-price-pattern* information in the academic sense: the
documented trend/momentum risk premium, tested across asset classes for breadth.

---

## 2. Two-layer universe design (resolves power vs. tradability)

**Layer 1 — DISCOVERY (broad).** Tests whether the phenomenon EXISTS. Maximum genuine
cross-asset breadth → maximum statistical power. No execution decision is made from it
directly. This is where a high-power falsification lives.

**Layer 2 — EXECUTION (tradable subset).** Evaluated ONLY after Discovery. Tests whether
the phenomenon is CAPTURABLE on the owner's MT5 broker after real costs. It is a
feasibility filter, NOT a second high-power test and NOT independent replication.

**Three anti-bias controls (locked):**
1. The Execution universe is derived by an **ex-ante tradability rule** (what trades on
   MT5), **NOT** by which instruments performed well in Discovery. Frozen before any run.
2. **Asymmetric gates:** Discovery = strict high-power falsification; Execution = gentler
   feasibility check. An Execution FAIL means "not tradable here," NOT "phenomenon refuted."
3. **Attribution:** Execution reports the share of the Discovery premium attributable to
   tradable vs. non-tradable classes, to prevent a small tradable subset passing by luck
   while the real signal lives in non-tradable assets.

Plus: **no re-tuning between layers** (identical trend rule; only instruments + cost model
change), and a pre-registered **2×2 decision matrix** (§8).

---

## 3. Frozen universes

### 3.1 Discovery universe — selection rule (references liquidity/asset-class ONLY, never returns)

Rule: *the most-liquid continuous futures / liquid ETF proxies in each predefined
asset-class bucket, plus deliberately-included counter-examples (FX) known to trend
weakly.* List frozen below (~24 instruments, 7 classes). Data: yfinance daily,
auto-adjusted, longest available history.

| Class | Instruments (yfinance) |
|---|---|
| Equity indices | ES=F, NQ=F, ^GDAXI, ^N225 |
| Rates / bonds | ZN=F, ZB=F, ZF=F |
| Energy | CL=F, BZ=F, NG=F, HO=F |
| Metals | GC=F, SI=F, HG=F, PL=F |
| Agriculture | ZC=F, ZW=F, ZS=F, SB=F, KC=F |
| FX (counter-example) | EURUSD=X, GBPUSD=X, USDJPY=X, AUDUSD=X |
| Crypto | BTC-USD, ETH-USD |

The FULL frozen list is tested and reported as-is. **No post-hoc subset / no dropping
losers.** Instruments with insufficient history start when listed (dynamic start, as in
the existing crypto code); a minimum of 60 monthly observations is required to enter.

### 3.2 Execution universe — ex-ante tradable subset (frozen, by broker availability)

The MetaQuotes-Demo MT5 tradable subset: **FX majors {EURUSD, GBPUSD, USDJPY, AUDUSD,
USDCHF, USDCAD} + XAUUSD (gold) + XAGUSD (silver)**; crypto {BTC, ETH} included only if
tradable on the live venue. Defined by what the broker offers — **not** by Discovery results.

---

## 4. Trend rule (canonical, NO tuning — identical in both layers)

Monthly-rebalanced time-series momentum, vol-targeted. The same textbook rule used in the
smoke test; no parameter is fit on the data here.

| Parameter | Value |
|---|---|
| Frequency | Monthly (month-end close) |
| Signal | sign(trailing 12-month log return) |
| Position lag | 1 month (no lookahead): `pos_prev = (sign·lev).shift(1)` |
| Vol scaling | target 10% ann. / trailing 12-month realized vol, capped at 1× leverage |
| Portfolio weighting | **equal-asset-CLASS weight** (then equal within class) — so no class dominates |
| Rebalance cost | charged on position change only (see §5) |

---

## 5. Cost model (per asset class, realistic, locked)

Charged in return terms on monthly position change (turnover × cost). Base per-side:

| Class | Base cost/side | Class | Base cost/side |
|---|---|---|---|
| Equity index fut | 2 bps | Metals | 3 bps |
| Rates/bonds fut | 1 bps | Agriculture | 4 bps |
| Energy fut | 3 bps | FX | existing per-pair (Phase 5 spread+slippage) |
| | | Crypto | 10 bps (as Phase 10) |

Execution layer uses **broker-real MT5 costs** for the tradable subset (Phase 5 per-pair
spread+slippage; gold/silver spot spreads), which are higher than futures.

## 5b. Roll-artifact handling (locked, from smoke finding)

yfinance `=F` continuous contracts can carry roll jumps (smoke: CL=F had 42 days >10%).
Rule: **winsorize daily log returns at ±15%** before monthly aggregation; any instrument
with >60 such days over its history is flagged in the report (data-quality disclosure),
not silently dropped.

---

## 6. DISCOVERY PASS gates (ALL must hold — high-power falsification)

| Gate | Criterion |
|---|---|
| **D1 Significance** | Equal-class-weight portfolio mean monthly NET return > 0, t-stat ≥ 2.0 (full sample). |
| **D2 OOS hold-out** | Chronological 70/30 split: OOS net mean > 0 AND OOS net Sharpe ≥ 0.30; OOS not statistically worse than train at 95% (drift check). |
| **D3 Regime robustness** | Net positive in BOTH sample halves AND in each defined macro sub-era (no single-regime artifact). |
| **D4 Breadth** | ≥ 4 of 7 asset CLASSES have positive net trend premium (class-level, not instrument-level). |
| **D5 Diversification validity** | On strategy returns: ENB ≥ 0.4×N AND PC1 variance share < 0.50 AND max pairwise corr < 0.70. (The X2-fix: result must be genuinely multi-bet.) |
| **D6 Cost stress + beats passive** | Net premium positive at 1.5× base costs AND portfolio net Sharpe > equal-weight buy-and-hold of the same universe. |

**Pass all 6 → the trend premium is a real, cost-survivable, out-of-sample, multi-bet
phenomenon.** Proceed to Execution layer.

---

## 7. EXECUTION layer (only if Discovery passes — feasibility, gentler)

| Step | Criterion |
|---|---|
| **E1 Attribution** | Report % of Discovery premium from tradable vs non-tradable classes. If tradable classes contribute ≤ 0, Execution is moot → record "edge lives in non-tradable assets." |
| **E2 Feasibility** | Tradable-subset net premium > 0 with broker-real MT5 costs, t-stat ≥ 1.0 (gentler — low ENB by construction). |
| **E3 No re-tuning** | Identical trend rule; only instruments + costs differ. Any rule change = rescue trap, forbidden. |

---

## 8. Pre-registered 2×2 decision matrix

| | Execution PASS | Execution FAIL |
|---|---|---|
| **Discovery PASS** | **First defensible edge.** Build a diversified trend sleeve on the tradable subset → forward paper with its own pre-registration. | **Phenomenon real but not capturable on MT5.** Structural decision (futures access / different broker). Do NOT fish for a tradable variant. |
| **Discovery FAIL** | (not evaluated) | **Direction-level result.** The most-evidenced premise fails even on the broadest powered universe → systematic-alpha on accessible instruments is closed. Pivot the goal (run v3 paper / accept learning project). NO re-tuning, NO next price hypothesis. |

---

## 9. Caveats (honest, up front)

- **In-sample ≠ proof.** Smoke t-stats are full-sample; D2 OOS is the real test.
- **yfinance continuous futures** are approximate (roll/back-adjust); §5b mitigates, gold
  cross-check (0.985 vs MT5) is reassuring but per-class quality varies.
- **Survivorship:** even the broad universe is a liquid-survivor slice of all assets ever;
  treat a marginal D1 pass (t just above 2) with skepticism.
- **Execution is not replication** — same data sliced; it confirms tradability, not the
  premise a second time.
- **Crypto short history** (BTC from 2014, ETH 2017, etc.) → enters late via dynamic start.

---

## 10. Decision rule (pre-registered, binding)

Run Discovery once. Apply §6 gates exactly as written. If Discovery passes, run Execution
(§7) once. Read the §8 matrix. **Do not relax any gate, re-tune any parameter, or select
a post-hoc subset after seeing results** — that is the Phase 7 / X2 trap this document
exists to prevent. A failure is a result, not a problem to route around.
