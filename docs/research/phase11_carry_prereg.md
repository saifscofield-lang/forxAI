# Phase 11 — Carry / Rate-Differential Premise Test — PRE-REGISTRATION

**Status:** PRE-REGISTERED 2026-06-03. Gates fixed BEFORE building/running.
**Context:** The rescue closed the price-only-TA hypothesis (Phase 4a/5b/6 — no
H1/M15 technical strategy has a cost-survivable edge; XAUUSD+D1 failed 4/5). This
is the first test of a NON-price information source: the interest-rate
differential (carry).

## Hypothesis

The carry premise (a documented FX phenomenon — the "forward-premium puzzle" /
UIP failure): currencies with higher policy rates do **not** depreciate enough to
offset the rate gap, so being long the higher-yielding currency earns a positive
**total return = spot move + carry** on average, across pairs and time.

This is *different information* from price TA: it is the macro rate structure, not
a pattern in the same OHLC bars that already failed.

## Scope & data

- **Pairs (6):** EURUSD, GBPUSD, AUDUSD, USDCAD, USDCHF, USDJPY. XAUUSD excluded
  (gold has no policy rate).
- **Price:** existing daily (D1) closes, 2022-2026, from `data/raw/{SYM}/D1.parquet`.
- **Rates:** a monthly central-bank **policy-rate table** constructed from public
  history (Fed, ECB, BoE, RBA, BoC, SNB, BoJ), committed alongside the script for
  sanity-check. This is the key new input and the main assumption.
  - `rate_diff(pair) = rate(base_ccy) − rate(quote_ccy)`, e.g. for USDJPY =
    Fed − BoJ; for EURUSD = ECB − Fed.
  - **Carry direction** = long the higher-yielding leg = sign(rate_diff). Position
    in the *pair's* terms: if rate_diff>0 go long the pair, else short.
- **Period caveat (stated up front):** 2022-2024 was a strong USD-rate-hiking
  regime (Fed ~0→5.5% while BoJ ~0). This period likely FAVORS carry (USD legs
  earned both carry and spot). A pass here is necessary but not sufficient — it
  must also hold in the 2025-2026 easing era (see gate C3/C5), or it is just the
  hiking regime.

## Method (premise diagnosis, hold-based not trade-based)

Monthly rebalanced, equal-weight carry portfolio:
1. Each month-end, for each pair set position = sign(rate_diff) (long higher yield).
2. Next-month return for that pair = directional spot return + carry accrued
   (rate_diff × 1/12, the monthly carry of holding the higher yielder).
3. Portfolio monthly return = equal-weight mean across the 6 pairs.
4. Report: annualized return, monthly Sharpe×√12, % positive months, max drawdown,
   and decompose spot-only vs carry-only contribution.

Costs: charge a per-rebalance round-trip cost only when a pair's position FLIPS
sign (carry direction is sticky, so turnover is low). Base cost per flip = the
same per-pair spread+slippage used in Phase 5 (in return terms at D1).

## PASS gates (ALL must hold)

| Gate | Criterion |
|---|---|
| **C1 Premise (significance)** | Equal-weight carry portfolio mean monthly total return > 0 with t-stat ≥ 2.0 over the full sample. |
| **C2 Spot doesn't kill it** | Carry-direction SPOT-only drift is not significantly negative (t-stat > −2). Tests UIP failure, not "earning carry while spot bleeds." |
| **C3 Persistence** | Total return positive in ≥ 3 of 4 calendar years (2022, 2023, 2024, 2025). |
| **C4 Breadth** | ≥ 4 of 6 pairs have positive carry-direction total return over the full sample. |
| **C5 Regime/OOS** | Positive mean return in BOTH the hiking era (2022-2024) AND the easing era (2025-2026). Not a single-regime artifact. |

## Decision rule (pre-registered)

- **Pass all 5** → carry is a real, non-price edge source on this book. Proceed to
  design a carry overlay/tilt (e.g., bias or gate trades by carry direction, or a
  standalone monthly carry sleeve) and validate THAT with its own pre-registration.
- **Fail any** → the carry premise does not hold robustly on these 6 USD-pairs in
  this period. Document and move to the next non-price hypothesis (cross-asset
  signals, or higher-TF/seasonality) — do NOT tweak the carry rule post-hoc to
  force a pass (the Phase 7 / X2 discipline).

## Caveats (honest, up front)

- Only 6 pairs, all sharing USD as one leg → not a true diversified cross-section;
  results are USD-regime-sensitive (hence C5).
- Policy-rate table is monthly and approximate; differentials are large (often
  >3%) so the *sign* is robust to small errors, but precise magnitudes are not.
- Spot returns use D1 closes; intramonth path and exact carry/swap mechanics
  (broker swap ≠ policy differential) are approximated. This is a PREMISE test, not
  a live-P&L forecast — same status as Phase 4a T1.
- ~48 monthly observations × 6 pairs is a modest sample; treat marginal results
  with skepticism and require C1's t-stat ≥ 2.
