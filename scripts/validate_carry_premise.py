"""
Phase 11 — Carry / Rate-Differential Premise Test — VALIDATION RUN.

Pre-registered in docs/research/phase11_carry_prereg.md (gates C1-C5 fixed BEFORE
this script was written). Rate table: data/macro/policy_rates.py (committed fe04b99).

Method (premise diagnosis, hold-based): monthly-rebalanced equal-weight carry
portfolio over 6 USD pairs. Each month-end position = sign(rate_diff) (long the
higher-yielding leg). Next-month pair return = directional spot return + carry
accrued (rate_diff x 1/12). Cost charged only on sign-flips. Decompose spot vs
carry. Report annualized return, Sharpe, %positive, maxDD, per-year, per-pair,
per-regime, then evaluate the 5 pre-registered gates.

Run:  python scripts/validate_carry_premise.py
"""
import sys

sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from data.macro.policy_rates import PAIR_LEGS, rate_diff_series

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "USDJPY"]

# Per-pair spread + slippage in PRICE units (matches Phase 5b/5c/6 — validate_macd_m15_d1filter.py)
SPREAD_PRICE = {"EURUSD": 0.00009, "GBPUSD": 0.00013, "AUDUSD": 0.00011,
                "USDCAD": 0.00015, "USDCHF": 0.00015, "USDJPY": 0.009}
SLIPPAGE_PRICE = {"EURUSD": 0.00003, "GBPUSD": 0.00004, "AUDUSD": 0.00004,
                  "USDCAD": 0.00005, "USDCHF": 0.00005, "USDJPY": 0.003}

L = []


def out(s=""):
    print(s)
    L.append(s)


def monthly_close(sym):
    """Month-end close series (UTC-naive) for a symbol from D1 parquet."""
    df = pd.read_parquet(f"data/raw/{sym}/D1.parquet").sort_values("time")
    s = df.set_index(pd.DatetimeIndex(df["time"]))["close"]
    return s.resample("ME").last().dropna()


def tstat(x):
    x = np.asarray(x, dtype=float)
    if len(x) < 2 or x.std(ddof=1) == 0:
        return 0.0
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))


def max_drawdown(monthly_ret):
    eq = (1.0 + pd.Series(monthly_ret)).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def main():
    # ---- assemble aligned month-end closes across all pairs ----
    closes = {p: monthly_close(p) for p in PAIRS}
    # common month index where every pair has a close
    idx = closes[PAIRS[0]].index
    for p in PAIRS[1:]:
        idx = idx.intersection(closes[p].index)
    idx = idx.sort_values()
    # restrict to the pre-registered window 2022-2026
    idx = idx[(idx >= "2022-01-01") & (idx <= "2026-12-31")]

    out("# Phase 11 — Carry Premise Test — RESULTS\n")
    out(f"Sample: {idx[0].date()} .. {idx[-1].date()}  ({len(idx)} month-ends, "
        f"{len(idx) - 1} monthly returns)\n")

    # ---- per-pair monthly series ----
    pair_total = {}   # pair -> Series of monthly total return (spot+carry-cost)
    pair_spot = {}    # pair -> Series of directional spot-only return
    pair_carry = {}   # pair -> Series of carry-only return
    flips = {}

    for p in PAIRS:
        c = closes[p].reindex(idx)
        spot_ret = c.pct_change()                       # raw pair spot return, month t
        rdiff = rate_diff_series(p, idx)                # rate_diff in PERCENT at each month
        pos = np.sign(rdiff).replace(0, 0.0)            # position set at month-end t
        pos_prev = pos.shift(1)                         # position held INTO month t

        dir_spot = pos_prev * spot_ret                  # directional spot return realised in month t
        carry = pos_prev * (rdiff.shift(1) / 100.0) / 12.0   # carry accrued holding higher yielder

        # cost in RETURN units, charged when position FLIPS sign at start of month t
        cost_price = SPREAD_PRICE[p] + SLIPPAGE_PRICE[p]
        cost_ret = cost_price / c                       # as fraction of price
        flipped = (pos_prev != pos_prev.shift(1)) & pos_prev.notna() & (pos_prev.shift(1).notna())
        cost = flipped.astype(float) * cost_ret

        total = (dir_spot + carry - cost).dropna()
        pair_total[p] = total
        pair_spot[p] = dir_spot.dropna()
        pair_carry[p] = carry.dropna()
        flips[p] = int(flipped.sum())

    # ---- equal-weight portfolio ----
    tot_df = pd.DataFrame(pair_total).dropna()
    spot_df = pd.DataFrame(pair_spot).reindex(tot_df.index)
    carry_df = pd.DataFrame(pair_carry).reindex(tot_df.index)

    port = tot_df.mean(axis=1)
    port_spot = spot_df.mean(axis=1)
    port_carry = carry_df.mean(axis=1)

    n = len(port)
    ann_ret = (1 + port).prod() ** (12 / n) - 1
    sharpe = (port.mean() / port.std(ddof=1)) * np.sqrt(12) if port.std(ddof=1) else 0.0
    pct_pos = (port > 0).mean()
    mdd = max_drawdown(port)

    out("## Portfolio (equal-weight, 6 pairs, monthly)\n")
    out(f"- Annualized return : {ann_ret:+.2%}")
    out(f"- Sharpe (x sqrt12) : {sharpe:+.2f}")
    out(f"- % positive months : {pct_pos:.0%}")
    out(f"- Max drawdown      : {mdd:.2%}")
    out(f"- Mean monthly tot  : {port.mean():+.4%}  (t = {tstat(port):+.2f})")
    out(f"- Decompose: spot mean {port_spot.mean():+.4%} | carry mean {port_carry.mean():+.4%}\n")

    # ---- per-year ----
    out("## Per calendar year (portfolio total return)\n")
    yr_ret = {}
    for y in [2022, 2023, 2024, 2025, 2026]:
        seg = port[port.index.year == y]
        if len(seg) == 0:
            continue
        r = (1 + seg).prod() - 1
        yr_ret[y] = r
        out(f"- {y}: {r:+.2%}  ({len(seg)} months)")
    out("")

    # ---- per-pair ----
    out("## Per-pair full-sample total return\n")
    pair_full = {}
    for p in PAIRS:
        r = (1 + pair_total[p]).prod() - 1
        pair_full[p] = r
        out(f"- {p}: {r:+.2%}  | flips={flips[p]} | carry-leg={PAIR_LEGS[p]}")
    out("")

    # ---- per-regime ----
    hike = port[port.index <= "2024-12-31"]
    ease = port[port.index >= "2025-01-01"]
    hike_mean = hike.mean() if len(hike) else float("nan")
    ease_mean = ease.mean() if len(ease) else float("nan")
    out("## Per-regime mean monthly return\n")
    out(f"- Hiking era 2022-2024 : {hike_mean:+.4%}  ({len(hike)} months)")
    out(f"- Easing era 2025-2026 : {ease_mean:+.4%}  ({len(ease)} months)\n")

    # ================= GATES =================
    out("## Pre-registered gates\n")

    t_port = tstat(port)
    c1 = (port.mean() > 0) and (t_port >= 2.0)

    t_spot = tstat(port_spot)
    c2 = t_spot > -2.0

    yrs_eval = [y for y in [2022, 2023, 2024, 2025] if y in yr_ret]
    yrs_pos = sum(1 for y in yrs_eval if yr_ret[y] > 0)
    c3 = yrs_pos >= 3

    pairs_pos = sum(1 for p in PAIRS if pair_full[p] > 0)
    c4 = pairs_pos >= 4

    c5 = (hike_mean > 0) and (ease_mean > 0)

    def row(tag, ok, detail):
        out(f"- **{tag}** {'PASS' if ok else 'FAIL'} — {detail}")

    row("C1 Premise", c1,
        f"mean {port.mean():+.4%} >0 and t={t_port:+.2f} (need >=2.0)")
    row("C2 Spot", c2,
        f"spot drift t={t_spot:+.2f} (need >-2.0)")
    row("C3 Persistence", c3,
        f"{yrs_pos}/{len(yrs_eval)} years positive (need >=3 of 4)")
    row("C4 Breadth", c4,
        f"{pairs_pos}/6 pairs positive (need >=4)")
    row("C5 Regime", c5,
        f"hike {hike_mean:+.4%} & ease {ease_mean:+.4%} (both must be >0)")

    all_pass = c1 and c2 and c3 and c4 and c5
    out("")
    out(f"## VERDICT: {'PASS ALL 5 — carry is a real non-price edge source' if all_pass else 'FAIL — carry premise does not hold robustly'}\n")
    if all_pass:
        out("Decision rule -> proceed to DESIGN a carry overlay/sleeve and validate "
            "THAT with its own pre-registration.")
    else:
        failed = [t for t, ok in
                  [("C1", c1), ("C2", c2), ("C3", c3), ("C4", c4), ("C5", c5)] if not ok]
        out(f"Decision rule -> failed {failed}. Do NOT tweak the rule post-hoc. "
            "Move to the next non-price hypothesis.")

    # ---- persist report ----
    with open("docs/research/phase11_carry_results.md", "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    out("\n(report written to docs/research/phase11_carry_results.md)")


if __name__ == "__main__":
    main()
