"""
MACD-M15 Edge Re-Validation  (Rescue Plan — Phase 5b, READ-ONLY)
================================================================
Phase 5a flagged that MACD-M15's "edge" (PF ~1.03 on 30k bars, ~0.96 on 90k)
straddles break-even and FLIPS SIGN with the window — i.e. it is unconfirmed.
Before layering any sizing/management on it, Phase 5a demanded a rigorous test:

  (1) Walk-forward R-PF across the FULL sample (not just the recent tail)
  (2) Recent-vs-old eras (per calendar year)
  (3) WITH spread/slippage costs (the prior sims were all clean)

This script does all three. Same MACD logic + ATR(1.2) filter as the live
strategy (strategies/macd_crossover.py), one-position-at-a-time, ordered SL/TP
first-touch. Two new things vs the earlier clean sims:

  - Uses the FULL M15 history (~100k bars/symbol, 2022-2026), not tail(30k).
  - Charges a realistic per-symbol spread + slippage on EVERY trade, expressed
    in ATR units, so PF_net is a live-cost forecast not a clean comparison.

Cost model (per trade, paid once on entry — the round-trip bid/ask crossing):
    cost_atr = (spread_price + slippage_price) / atr_at_entry
    net win  = +tp_m - cost_atr     (in ATR units)
    net loss = -sl_m - cost_atr
PF_net = sum(net wins) / |sum(net losses)|.  EV_net = mean(net pnl) in ATR.

READ-ONLY: reads data/raw/*/M15.parquet, prints + writes markdown. No live state.
Run: venv/Scripts/python.exe scripts/validate_macd_m15_walkforward.py
"""
import sys
import os
import glob
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from features.technical.indicators import add_macd, add_atr, add_ema

OUT = "docs/research/rescue_phase5b_macd_m15_revalidation.md"
HORIZON = 100          # M15 bars to resolve a trade (~25h)
MACD_SL, MACD_TP = 2.5, 3.5   # strategies/macd_crossover.py defaults
ATR_THR = 1.2          # live ATR regime filter
N_FOLDS = 8            # contiguous walk-forward folds per symbol

# Realistic retail/demo spreads in PRICE units (one-way mid->ask ≈ full spread
# charged once per round trip). Conservative-but-fair MetaQuotes-demo-ish values.
SPREAD_PRICE = {
    "EURUSD": 0.00009, "GBPUSD": 0.00013, "AUDUSD": 0.00011,
    "USDCAD": 0.00015, "USDCHF": 0.00015, "USDJPY": 0.009,
    "XAUUSD": 0.28,
}
# Extra slippage on entry+exit, same price units (fills not at the exact level).
SLIPPAGE_PRICE = {
    "EURUSD": 0.00003, "GBPUSD": 0.00004, "AUDUSD": 0.00004,
    "USDCAD": 0.00005, "USDCHF": 0.00005, "USDJPY": 0.003,
    "XAUUSD": 0.10,
}


def enrich(sym):
    df = pd.read_parquet(f"data/raw/{sym}/M15.parquet").sort_values("time").reset_index(drop=True)
    df = add_macd(df); df = add_atr(df, 14); df = add_ema(df, 50); df = add_ema(df, 200)
    df["avg_atr20"] = df["atr_14"].rolling(20).mean()
    df = df.dropna(subset=["macd_line", "macd_signal", "macd_hist", "atr_14",
                           "ema_50", "ema_200", "avg_atr20"]).reset_index(drop=True)
    return df


def macd_dir(d, thr=ATR_THR):
    """Exact live MACD logic, vectorised. +1 BUY / -1 SELL / 0 none."""
    price = d["close"].values; macd = d["macd_line"].values; sig = d["macd_signal"].values
    hist = d["macd_hist"].values; ema50 = d["ema_50"].values; ema200 = d["ema_200"].values
    atr = d["atr_14"].values; avg = d["avg_atr20"].values
    pm, ps, ph = np.roll(macd, 1), np.roll(sig, 1), np.roll(hist, 1)
    ok = atr >= thr * avg
    buy = ok & (pm <= ps) & (macd > sig) & (price > ema50) & (ema50 > ema200) & (hist > ph)
    sell = ok & (pm >= ps) & (macd < sig) & (price < ema50) & (ema50 < ema200) & (hist < ph)
    o = np.zeros(len(d), np.int8); o[buy] = 1; o[sell] = -1; o[:1] = 0
    return o


def simulate(d, dirs, sl_m, tp_m, cost_price, lo=None, hi=None):
    """One-position-at-a-time, ordered SL/TP first-touch over [lo, hi) bar window.
    Returns a list of per-trade dicts: {win, atr, time}."""
    high = d["high"].values; low = d["low"].values; close = d["close"].values
    atr = d["atr_14"].values; tarr = d["time"].values
    n = len(close)
    lo = 0 if lo is None else lo
    hi = n if hi is None else hi
    trades = []
    busy_until = lo - 1
    fire = np.where(dirs != 0)[0]
    for i in fire:
        if i < lo or i >= hi:
            continue
        if i <= busy_until:
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        entry = close[i]; dirn = int(dirs[i])
        if dirn == 1:
            tp, sl = entry + tp_m * a, entry - sl_m * a
        else:
            tp, sl = entry - tp_m * a, entry + sl_m * a
        outcome = None
        end = min(i + 1 + HORIZON, hi)
        for j in range(i + 1, end):
            if dirn == 1:
                if low[j] <= sl: outcome = "L"; break
                if high[j] >= tp: outcome = "W"; break
            else:
                if high[j] >= sl: outcome = "L"; break
                if low[j] <= tp: outcome = "W"; break
            busy_until = j
        if outcome is None:
            continue  # timeout — undecided, excluded (matches prior sims)
        trades.append({"win": outcome == "W", "atr": a, "time": tarr[i],
                       "cost_atr": cost_price / a})
    return trades


def stats(trades, sl_m, tp_m):
    """Return (n, win%, PF_clean, PF_net, EV_net_atr) for a trade list."""
    if not trades:
        return 0, 0.0, float("nan"), float("nan"), float("nan")
    n = len(trades)
    w = sum(1 for t in trades if t["win"])
    l = n - w
    wr = 100 * w / n
    # clean R-PF (matches prior reports)
    pf_clean = (w * tp_m) / (l * sl_m) if l else float("inf")
    # net per-trade pnl in ATR units after cost
    net = []
    for t in trades:
        g = tp_m if t["win"] else -sl_m
        net.append(g - t["cost_atr"])
    net = np.array(net)
    pos = net[net > 0].sum()
    neg = -net[net < 0].sum()
    pf_net = pos / neg if neg > 0 else float("inf")
    ev_net = net.mean()
    return n, wr, pf_clean, pf_net, ev_net


def main():
    syms = sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob("data/raw/*/M15.parquet"))
    print(f"Symbols: {syms}", flush=True)

    data = {}
    for s in syms:
        data[s] = enrich(s)
        print(f"  enriched {s}: {len(data[s]):,} bars", flush=True)

    L = ["# Rescue Plan — Phase 5b: MACD-M15 Edge Re-Validation\n"]
    L.append(f"**Data:** {len(syms)} symbols × FULL M15 history (~100k bars/symbol, "
             f"2022→2026). MACD logic + ATR({ATR_THR}) filter, one-position-at-a-time, "
             f"ordered SL/TP, horizon={HORIZON}. SL={MACD_SL}×ATR, TP={MACD_TP}×ATR.")
    L.append("**Costs:** per-symbol spread+slippage charged once per trade, in ATR units "
             "(see table). PF_clean = (W×TP)/(L×SL); PF_net is after costs.\n")

    # cost per symbol table
    L.append("## Cost assumptions (price units, charged once per trade)\n")
    L.append("| Symbol | Spread | Slippage | Total | ~Total / median ATR |")
    L.append("|---|---:|---:|---:|---:|")
    cost_price = {}
    for s in syms:
        sp = SPREAD_PRICE.get(s, 0.00010); sl = SLIPPAGE_PRICE.get(s, 0.00003)
        cost_price[s] = sp + sl
        med_atr = float(data[s]["atr_14"].median())
        L.append(f"| {s} | {sp:.5f} | {sl:.5f} | {cost_price[s]:.5f} | {cost_price[s]/med_atr:.1%} |")

    # ---- 1) FULL-SAMPLE pooled ----
    all_trades = []
    per_sym = {}
    for s in syms:
        ts = simulate(data[s], macd_dir(data[s]), MACD_SL, MACD_TP, cost_price[s])
        per_sym[s] = ts
        all_trades.extend(ts)
    n, wr, pfc, pfn, ev = stats(all_trades, MACD_SL, MACD_TP)
    L.append("\n## 1. Full-sample (pooled, all symbols, all years)\n")
    L.append("| Trades | Win% | PF_clean | PF_net | EV_net (ATR/trade) |")
    L.append("|---:|---:|---:|---:|---:|")
    L.append(f"| {n:,} | {wr:.1f}% | {pfc:.3f} | {pfn:.3f} | {ev:+.4f} |")
    print(f"FULL: n={n} wr={wr:.1f} pf_clean={pfc:.3f} pf_net={pfn:.3f} ev={ev:+.4f}", flush=True)

    # ---- 2) Per-symbol ----
    L.append("\n## 2. Per-symbol (full sample, net of cost)\n")
    L.append("| Symbol | Trades | Win% | PF_clean | PF_net | EV_net |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for s in syms:
        n, wr, pfc, pfn, ev = stats(per_sym[s], MACD_SL, MACD_TP)
        flag = "" if (pfn == pfn and pfn >= 1.0) else " ❌"
        L.append(f"| {s} | {n:,} | {wr:.1f}% | {pfc:.3f} | {pfn:.3f} | {ev:+.4f}{flag} |")

    # ---- 3) Walk-forward folds (contiguous, per symbol -> pooled per fold) ----
    L.append(f"\n## 3. Walk-forward stability ({N_FOLDS} contiguous folds, pooled)\n")
    L.append("Each symbol's bars split into equal contiguous time-folds; trades from the "
             "same fold index pooled across symbols. A real edge holds its sign across folds.\n")
    L.append("| Fold (old→new) | Trades | Win% | PF_clean | PF_net | EV_net |")
    L.append("|---|---:|---:|---:|---:|---:|")
    fold_pfnet = []
    fold_ev = []
    for k in range(N_FOLDS):
        ftr = []
        for s in syms:
            d = data[s]; nbar = len(d)
            lo = nbar * k // N_FOLDS
            hi = nbar * (k + 1) // N_FOLDS
            ftr.extend(simulate(d, macd_dir(d), MACD_SL, MACD_TP, cost_price[s], lo, hi))
        n, wr, pfc, pfn, ev = stats(ftr, MACD_SL, MACD_TP)
        fold_pfnet.append(pfn); fold_ev.append(ev)
        L.append(f"| {k+1} | {n:,} | {wr:.1f}% | {pfc:.3f} | {pfn:.3f} | {ev:+.4f} |")
        print(f"fold {k+1}: n={n} pf_net={pfn:.3f} ev={ev:+.4f}", flush=True)

    valid = [x for x in fold_pfnet if x == x]
    n_pos = sum(1 for x in valid if x >= 1.0)
    L.append(f"\n**Fold PF_net:** min={min(valid):.3f}, max={max(valid):.3f}, "
             f"profitable folds = {n_pos}/{len(valid)}. "
             f"EV_net sign flips: {sum(1 for e in fold_ev if e>0)} pos / "
             f"{sum(1 for e in fold_ev if e<0)} neg.")

    # ---- 4) Per calendar year (era) ----
    L.append("\n## 4. Per-year era breakdown (net of cost)\n")
    L.append("| Year | Trades | Win% | PF_clean | PF_net | EV_net |")
    L.append("|---|---:|---:|---:|---:|---:|")
    by_year = {}
    for t in all_trades:
        yr = pd.Timestamp(t["time"]).year
        by_year.setdefault(yr, []).append(t)
    for yr in sorted(by_year):
        n, wr, pfc, pfn, ev = stats(by_year[yr], MACD_SL, MACD_TP)
        L.append(f"| {yr} | {n:,} | {wr:.1f}% | {pfc:.3f} | {pfn:.3f} | {ev:+.4f} |")

    # ---- 5) Cost sensitivity (full sample) ----
    L.append("\n## 5. Cost sensitivity (full sample, PF_net)\n")
    L.append("| Cost multiple | PF_net | EV_net |")
    L.append("|---|---:|---:|")
    for mult in (0.0, 1.0, 1.5, 2.0):
        net = []
        for s in syms:
            c = cost_price[s] * mult
            for t in per_sym[s]:
                g = MACD_TP if t["win"] else -MACD_SL
                net.append(g - c / t["atr"])
        net = np.array(net)
        pos = net[net > 0].sum(); neg = -net[net < 0].sum()
        pfn = pos / neg if neg > 0 else float("inf")
        tag = " (clean)" if mult == 0 else (" (base)" if mult == 1 else "")
        L.append(f"| {mult:.1f}×{tag} | {pfn:.3f} | {net.mean():+.4f} |")

    # ---- Verdict scaffold ----
    L.append("\n## Verdict (gates)\n")
    L.append(f"- **G1 Full-sample PF_net ≥ 1.05** (a real, cost-survivable edge)")
    L.append(f"- **G2 Walk-forward: ≥ 6/8 folds PF_net ≥ 1.0** (stable across time, no sign flips)")
    L.append(f"- **G3 Recent era (2025-2026) PF_net ≥ 1.0** (edge is not only historical)")
    L.append(f"- **G4 Majority of symbols PF_net ≥ 1.0** (not carried by one pair)")
    L.append("\nIf G1-G4 fail, MACD-M15's edge is NOT confirmed under live costs → "
             "stop layering machinery on it; per the Phase 4a meta-finding, no price-only "
             "H1/M15 technical strategy in this project has a reliable edge.")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"\nReport written: {OUT}", flush=True)


if __name__ == "__main__":
    main()
