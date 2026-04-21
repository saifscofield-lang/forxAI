# Project Tracker — Evaluation Framework

*Version-by-version, weighted multi-criteria methodology*

---

## 1. Why This Document Exists

The earlier evaluation of the system mixed data from all versions (v1 + v2 + v3) into a single verdict. **That methodology is wrong.** It punishes the system for bugs and weaknesses that were already fixed in later versions.

This document defines the correct methodology going forward:

- Evaluate each version **separately** on its own data
- Compare versions to see whether the system is **improving**
- Judge the **latest version on its own merits** — because that is the one that will actually run

---

## 2. Evaluation Methodology

### Step 1 — Separate data by version

Each version is evaluated **only** on data generated while that version was active. Mixing versions produces a meaningless average.

### Step 2 — Weighted scoring across all criteria

Each version receives a composite score from the following weighted criteria:

| Criterion | Weight | Rationale |
|---|---|---|
| **Net PnL** (profitability) | **30%** | Ultimate goal — does the system actually make money after costs? |
| **Risk / Reward Ratio** | **20%** | Are winning trades meaningfully bigger than losing trades? |
| **Sharpe Ratio** (stability) | **20%** | Risk-adjusted return — smoothness of the equity curve, not just raw profit |
| **Win Rate** | **15%** | Consistency of signal quality — how often is the system right? |
| **Max Drawdown** | **15%** | Survivability — can you psychologically and financially tolerate the worst period? |
| **Total** | **100%** | |

### Step 3 — Track the improvement curve

Plot the composite score of each version: **v1 → v2 → v3 → v4**.

A rising curve means the system is **learning and improving**. That is a viable system, not a failed one — even if early versions lost money.

### Step 4 — Judge only the current version

The verdict *viable / not viable* applies **only to the latest version**, because that is what will run going forward. Killing a system because v1 was bad is like firing an engineer for a bug they already fixed.

---

## 3. Data Required for a Proper Evaluation

To apply the framework above to the existing versions, the following inputs are needed:

| Item | Description |
|---|---|
| **Trade log per version** | For each of v1, v2, v3 (and v4 when run): start/end dates, list of trades (entry, exit, PnL, symbol). If full log is unavailable: summary stats — total trades, wins, losses, total PnL, max drawdown. |
| **Changelog between versions** | One line per version describing the core change (e.g., *"v2: added ATR stop-loss"*, *"v3: switched from 1h to 4h timeframe"*). Lets us distinguish real improvement from noise. |
| **Capital / position sizing** | Starting capital and position-size rule — required for correct Sharpe and drawdown calculation. |

Any format is acceptable: spreadsheet, CSV, or a raw text dump. The data will be organized by version before scoring.

---

## 4. v4 Research — Crypto Momentum (BTC / ETH / SOL on ccxt)

**Overall approach: correct.** Backtesting momentum on ccxt with free historical data before committing capital is exactly how serious quantitative strategies are validated.

The following guardrails must be locked in **before v4 starts**, so that v4 produces usable evaluation data (unlike earlier versions where the methodology itself may have been the weak link):

- **Fixed backtest window** — decide start and end dates up front (e.g., Jan 2022 → today) so results cannot be cherry-picked after the fact.
- **Out-of-sample split** — optimize parameters on 70% of the data, validate on the untouched 30%. This is the single biggest defense against self-deception.
- **Transaction costs included** — ccxt provides clean prices, but real trades pay fees and slippage. Add at least **0.1% per side** or the backtest will lie.
- **Benchmark vs buy-and-hold BTC** — the momentum strategy must beat *"just hold BTC"* after costs, otherwise the added complexity is not paying for itself.
- **Same weighted criteria as Section 2** — so v4 is directly comparable to v1–v3 on the same ruler.

---

## 5. Open Questions Before Finalizing v4

- [ ] Is v4 a **clean new track** with independent logic, or an **extension** of the existing system?
- [ ] What is the planned **backtest window** on ccxt before any real capital is deployed?
- [ ] Which of BTC / ETH / SOL is the **primary** instrument, and which are secondary for diversification?
- [ ] What is the **out-of-sample validation period** (the held-out 30%)?
- [ ] What is the **go / no-go threshold** on the composite score for deploying real capital?

---

## 6. Version Comparison Template

Fill this in once per-version data is collected:

| Metric | v1 | v2 | v3 | v4 (backtest) |
|---|---|---|---|---|
| Start date | | | | |
| End date | | | | |
| Total trades | | | | |
| Net PnL | | | | |
| Win rate | | | | |
| Avg R:R | | | | |
| Sharpe | | | | |
| Max drawdown | | | | |
| **Composite score** | | | | |
| Core change from prior version | — | | | |

---

## 7. Next Step

1. Gather the per-version data described in Section 3.
2. Answer the open questions in Section 5.
3. Apply the framework to produce a fair, version-by-version verdict and a **go / no-go recommendation for v4**.

---

*Document created: 2026-04-21*
*Methodology: weighted multi-criteria, version-isolated evaluation*
