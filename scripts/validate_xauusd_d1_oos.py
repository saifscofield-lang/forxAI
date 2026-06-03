"""
XAUUSD + D1 Filter — OOS Validation  (Rescue Plan Phase 6, READ-ONLY)
====================================================================
Pre-registered test (docs/research/rescue_phase6_xauusd_prereg.md). Gates X1-X5
were fixed BEFORE this script was written. XAUUSD only, D1-trend-filtered MACD-M15
(EMA50>EMA200 daily, no-lookahead), same ATR(1.2) filter, ordered SL/TP, per-trade
spread+slippage in ATR units. Reuses the 5b/5c machinery.

PASS gates (ALL must hold):
  X1  Chronological 70/30 split -> OOS PF_net >= 1.05
  X2  >= 6/8 contiguous folds PF_net >= 1.0 (per-fold)
  X3  PF_net >= 1.0 in BOTH 2022-2024 and 2025-2026
  X4  PF_net >= 1.0 at 1.5x base cost
  X5  On OOS, D1-filtered PF_net > unfiltered PF_net

Run: venv/Scripts/python.exe scripts/validate_xauusd_d1_oos.py
"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from features.technical.indicators import add_macd, add_atr, add_ema

OUT = "docs/research/rescue_phase6_xauusd_oos_results.md"
SYM = "XAUUSD"
HORIZON = 100
MACD_SL, MACD_TP = 2.5, 3.5
ATR_THR = 1.2
N_FOLDS = 8
BASE_COST = 0.28 + 0.10   # spread + slippage, price units (matches 5b/5c)


def enrich_m15():
    df = pd.read_parquet(f"data/raw/{SYM}/M15.parquet").sort_values("time").reset_index(drop=True)
    df = add_macd(df); df = add_atr(df, 14); df = add_ema(df, 50); df = add_ema(df, 200)
    df["avg_atr20"] = df["atr_14"].rolling(20).mean()
    return df.dropna(subset=["macd_line", "macd_signal", "macd_hist", "atr_14",
                             "ema_50", "ema_200", "avg_atr20"]).reset_index(drop=True)


def d1_trend():
    d = pd.read_parquet(f"data/raw/{SYM}/D1.parquet").sort_values("time").reset_index(drop=True)
    d = add_ema(d, 50); d = add_ema(d, 200)
    d = d.dropna(subset=["ema_50", "ema_200"]).reset_index(drop=True)
    return pd.DataFrame({
        "avail": (d["time"] + pd.Timedelta(days=1)).astype("datetime64[ns]"),
        "d1a": np.where(d["ema_50"].values > d["ema_200"].values, 1, -1),
    }).sort_values("avail").reset_index(drop=True)


def macd_dir(d, thr=ATR_THR):
    price = d["close"].values; macd = d["macd_line"].values; sig = d["macd_signal"].values
    hist = d["macd_hist"].values; ema50 = d["ema_50"].values; ema200 = d["ema_200"].values
    atr = d["atr_14"].values; avg = d["avg_atr20"].values
    pm, ps, ph = np.roll(macd, 1), np.roll(sig, 1), np.roll(hist, 1)
    ok = atr >= thr * avg
    buy = ok & (pm <= ps) & (macd > sig) & (price > ema50) & (ema50 > ema200) & (hist > ph)
    sell = ok & (pm >= ps) & (macd < sig) & (price < ema50) & (ema50 < ema200) & (hist < ph)
    o = np.zeros(len(d), np.int8); o[buy] = 1; o[sell] = -1; o[:1] = 0
    return o


def attach_d1(d, trend):
    left = d[["time"]].copy()
    left["time"] = left["time"].astype("datetime64[ns]")
    return pd.merge_asof(left, trend, left_on="time", right_on="avail", direction="backward")["d1a"].values


def simulate(d, dirs, cost_price, d1col=None, lo=None, hi=None):
    high = d["high"].values; low = d["low"].values; close = d["close"].values
    atr = d["atr_14"].values; tarr = d["time"].values
    n = len(close); lo = 0 if lo is None else lo; hi = n if hi is None else hi
    trades = []; busy_until = lo - 1
    for i in np.where(dirs != 0)[0]:
        if i < lo or i >= hi or i <= busy_until:
            continue
        dirn = int(dirs[i])
        if d1col is not None and d1col[i] != dirn:
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        entry = close[i]
        if dirn == 1:
            tp, sl = entry + MACD_TP * a, entry - MACD_SL * a
        else:
            tp, sl = entry - MACD_TP * a, entry + MACD_SL * a
        outcome = None; end = min(i + 1 + HORIZON, hi)
        for j in range(i + 1, end):
            if dirn == 1:
                if low[j] <= sl: outcome = "L"; break
                if high[j] >= tp: outcome = "W"; break
            else:
                if high[j] >= sl: outcome = "L"; break
                if low[j] <= tp: outcome = "W"; break
            busy_until = j
        if outcome is None:
            continue
        trades.append({"win": outcome == "W", "atr": a, "time": tarr[i], "cost_atr": cost_price / a})
    return trades


def stats(trades, cost_mult=1.0):
    if not trades:
        return 0, 0.0, float("nan"), float("nan"), float("nan")
    n = len(trades); w = sum(t["win"] for t in trades); l = n - w
    wr = 100 * w / n
    pf_clean = (w * MACD_TP) / (l * MACD_SL) if l else float("inf")
    net = np.array([(MACD_TP if t["win"] else -MACD_SL) - t["cost_atr"] * cost_mult for t in trades])
    pos = net[net > 0].sum(); neg = -net[net < 0].sum()
    pf_net = pos / neg if neg > 0 else float("inf")
    return n, wr, pf_clean, pf_net, net.mean()


def main():
    d = enrich_m15()
    d1col = attach_d1(d, d1_trend())
    dmark = macd_dir(d)
    n_bars = len(d)
    print(f"{SYM}: {n_bars:,} M15 bars  {d.time.iloc[0]} -> {d.time.iloc[-1]}", flush=True)

    L = [f"# Rescue Plan — Phase 6: XAUUSD + D1 Filter — OOS Results\n"]
    L.append(f"**Pre-registered:** docs/research/rescue_phase6_xauusd_prereg.md (gates fixed before run).")
    L.append(f"**Data:** {SYM} {n_bars:,} M15 bars, D1-filtered MACD-M15 (EMA50>EMA200), "
             f"ATR({ATR_THR}), SL/TP {MACD_SL}/{MACD_TP}×ATR, horizon {HORIZON}, "
             f"base cost {BASE_COST} price/trade. PF_net = after cost.\n")

    results = {}

    # ---- X1: 70/30 chronological split ----
    split = n_bars * 70 // 100
    tr_train = simulate(d, dmark, BASE_COST, d1col=d1col, lo=0, hi=split)
    tr_oos = simulate(d, dmark, BASE_COST, d1col=d1col, lo=split, hi=n_bars)
    s_tr = stats(tr_train); s_oos = stats(tr_oos)
    results["X1"] = s_oos[3] >= 1.05
    L.append("## X1 — Chronological 70/30 split\n")
    L.append("| Segment | Trades | Win% | PF_clean | PF_net | EV_net |")
    L.append("|---|---:|---:|---:|---:|---:|")
    L.append(f"| Train (first 70%) | {s_tr[0]} | {s_tr[1]:.1f}% | {s_tr[2]:.3f} | {s_tr[3]:.3f} | {s_tr[4]:+.4f} |")
    L.append(f"| **OOS (last 30%)** | {s_oos[0]} | {s_oos[1]:.1f}% | {s_oos[2]:.3f} | **{s_oos[3]:.3f}** | {s_oos[4]:+.4f} |")
    L.append(f"\n**X1 gate:** OOS PF_net {s_oos[3]:.3f} ≥ 1.05 → {'✅ PASS' if results['X1'] else '❌ FAIL'}")
    print(f"X1 OOS pf_net={s_oos[3]:.3f} -> {results['X1']}", flush=True)

    # ---- X2: 8 walk-forward folds ----
    L.append(f"\n## X2 — Walk-forward ({N_FOLDS} contiguous folds)\n")
    L.append("| Fold (old→new) | Trades | Win% | PF_clean | PF_net | EV_net |")
    L.append("|---|---:|---:|---:|---:|---:|")
    fold_pass = 0; fold_valid = 0
    for k in range(N_FOLDS):
        lo = n_bars * k // N_FOLDS; hi = n_bars * (k + 1) // N_FOLDS
        ftr = simulate(d, dmark, BASE_COST, d1col=d1col, lo=lo, hi=hi)
        s = stats(ftr)
        if s[3] == s[3]:
            fold_valid += 1
            if s[3] >= 1.0:
                fold_pass += 1
        L.append(f"| {k+1} | {s[0]} | {s[1]:.1f}% | {s[2]:.3f} | {s[3]:.3f} | {s[4]:+.4f} |")
        print(f"fold {k+1}: n={s[0]} pf_net={s[3]:.3f}", flush=True)
    results["X2"] = fold_pass >= 6
    L.append(f"\n**X2 gate:** {fold_pass}/{fold_valid} folds PF_net ≥ 1.0 (need ≥6/8) → "
             f"{'✅ PASS' if results['X2'] else '❌ FAIL'}")

    # ---- X3: regime (2022-2024 vs 2025-2026) ----
    all_tr = simulate(d, dmark, BASE_COST, d1col=d1col)
    bull = [t for t in all_tr if 2022 <= pd.Timestamp(t["time"]).year <= 2024]
    recent = [t for t in all_tr if pd.Timestamp(t["time"]).year >= 2025]
    s_bull = stats(bull); s_recent = stats(recent)
    results["X3"] = (s_bull[3] >= 1.0) and (s_recent[3] >= 1.0)
    L.append("\n## X3 — Regime robustness\n")
    L.append("| Era | Trades | Win% | PF_clean | PF_net | EV_net |")
    L.append("|---|---:|---:|---:|---:|---:|")
    L.append(f"| 2022-2024 (gold bull) | {s_bull[0]} | {s_bull[1]:.1f}% | {s_bull[2]:.3f} | {s_bull[3]:.3f} | {s_bull[4]:+.4f} |")
    L.append(f"| 2025-2026 (recent) | {s_recent[0]} | {s_recent[1]:.1f}% | {s_recent[2]:.3f} | {s_recent[3]:.3f} | {s_recent[4]:+.4f} |")
    L.append(f"\n**X3 gate:** both PF_net ≥ 1.0 ({s_bull[3]:.3f} & {s_recent[3]:.3f}) → "
             f"{'✅ PASS' if results['X3'] else '❌ FAIL'}")

    # ---- X4: cost stress 1.5x ----
    s_15 = stats(all_tr, cost_mult=1.5)
    results["X4"] = s_15[3] >= 1.0
    L.append("\n## X4 — Cost stress (full sample)\n")
    L.append("| Cost multiple | Trades | PF_net | EV_net |")
    L.append("|---|---:|---:|---:|")
    for m in (1.0, 1.5, 2.0):
        s = stats(all_tr, cost_mult=m)
        L.append(f"| {m:.1f}× | {s[0]} | {s[3]:.3f} | {s[4]:+.4f} |")
    L.append(f"\n**X4 gate:** PF_net at 1.5× cost = {s_15[3]:.3f} ≥ 1.0 → "
             f"{'✅ PASS' if results['X4'] else '❌ FAIL'}")

    # ---- X5: filter adds value on OOS ----
    tr_oos_unf = simulate(d, dmark, BASE_COST, d1col=None, lo=split, hi=n_bars)
    s_oos_unf = stats(tr_oos_unf)
    results["X5"] = s_oos[3] > s_oos_unf[3]
    L.append("\n## X5 — D1 filter adds value (OOS segment)\n")
    L.append("| OOS config | Trades | Win% | PF_net |")
    L.append("|---|---:|---:|---:|")
    L.append(f"| Unfiltered MACD-M15 | {s_oos_unf[0]} | {s_oos_unf[1]:.1f}% | {s_oos_unf[3]:.3f} |")
    L.append(f"| + D1 filter | {s_oos[0]} | {s_oos[1]:.1f}% | {s_oos[3]:.3f} |")
    L.append(f"\n**X5 gate:** filtered {s_oos[3]:.3f} > unfiltered {s_oos_unf[3]:.3f} → "
             f"{'✅ PASS' if results['X5'] else '❌ FAIL'}")

    # ---- Verdict ----
    n_pass = sum(results.values())
    overall = all(results.values())
    L.append("\n## VERDICT\n")
    L.append("| Gate | Result |")
    L.append("|---|:--:|")
    for g in ("X1", "X2", "X3", "X4", "X5"):
        L.append(f"| {g} | {'✅ PASS' if results[g] else '❌ FAIL'} |")
    L.append(f"\n**{n_pass}/5 gates passed.** Overall: "
             f"{'🟢 PASS — XAUUSD+D1 is the surviving cornerstone engine' if overall else '🔴 FAIL — price-only-TA hypothesis closed; pivot to non-price information'}")
    if not overall:
        L.append("\nPer the pre-registered decision rule, any single failure closes the "
                 "price-only-TA hypothesis. Do NOT add more TA variants on the same bars; "
                 "pivot to non-price info (carry/rate-differential, cross-asset, higher-TF structure).")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"\n{n_pass}/5 gates passed. Overall {'PASS' if overall else 'FAIL'}", flush=True)
    print(f"Report written: {OUT}", flush=True)


if __name__ == "__main__":
    main()
