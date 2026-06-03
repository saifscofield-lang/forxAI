"""
MACD-M15 + D1 Trend Filter — Rescue Plan Phase 5c (READ-ONLY)
============================================================
Phase 5b proved MACD-M15 has no cost-survivable edge (PF_net 0.857, 1/8 folds).
Before abandoning the live engine, test the cheapest possible rescue: gate each
MACD-M15 signal by the HIGHER-timeframe (D1) trend — take BUYs only in a D1
uptrend, SELLs only in a D1 downtrend. This is "different information" (the daily
structure) WITHOUT changing holding time or margin (entries/exits stay on M15).

No-lookahead: for an M15 signal at time t we use only the most recent CLOSED D1
bar (its trend is made 'available' at next-day open via a +1d shift, then joined
with merge_asof backward). The same-day D1 bar — whose close isn't known yet — is
never used.

Reuses the Phase 5b cost model (per-symbol spread+slippage in ATR units) and the
same one-position-at-a-time ordered SL/TP sim, full ~100k-bar M15 sample.

Tests 3 D1 trend definitions vs the unfiltered baseline:
  D1a  EMA50 > EMA200            (trend regime, matches strategy style)
  D1b  close > EMA200           (simple long-term trend)
  D1c  close > SMA50            (medium-term trend)

READ-ONLY. Run: venv/Scripts/python.exe scripts/validate_macd_m15_d1filter.py
"""
import sys
import os
import glob
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from features.technical.indicators import add_macd, add_atr, add_ema, add_sma

OUT = "docs/research/rescue_phase5c_macd_m15_d1filter.md"
HORIZON = 100
MACD_SL, MACD_TP = 2.5, 3.5
ATR_THR = 1.2
N_FOLDS = 8

SPREAD_PRICE = {"EURUSD": 0.00009, "GBPUSD": 0.00013, "AUDUSD": 0.00011,
                "USDCAD": 0.00015, "USDCHF": 0.00015, "USDJPY": 0.009, "XAUUSD": 0.28}
SLIPPAGE_PRICE = {"EURUSD": 0.00003, "GBPUSD": 0.00004, "AUDUSD": 0.00004,
                  "USDCAD": 0.00005, "USDCHF": 0.00005, "USDJPY": 0.003, "XAUUSD": 0.10}


def enrich_m15(sym):
    df = pd.read_parquet(f"data/raw/{sym}/M15.parquet").sort_values("time").reset_index(drop=True)
    df = add_macd(df); df = add_atr(df, 14); df = add_ema(df, 50); df = add_ema(df, 200)
    df["avg_atr20"] = df["atr_14"].rolling(20).mean()
    df = df.dropna(subset=["macd_line", "macd_signal", "macd_hist", "atr_14",
                           "ema_50", "ema_200", "avg_atr20"]).reset_index(drop=True)
    return df


def d1_trend(sym):
    """Return a frame of D1 trend signs, made available at next-day open (no lookahead)."""
    d = pd.read_parquet(f"data/raw/{sym}/D1.parquet").sort_values("time").reset_index(drop=True)
    d = add_ema(d, 50); d = add_ema(d, 200); d = add_sma(d, 50)
    d = d.dropna(subset=["ema_50", "ema_200", "sma_50"]).reset_index(drop=True)
    c = d["close"].values
    out = pd.DataFrame({
        "avail": (d["time"] + pd.Timedelta(days=1)).astype("datetime64[ns]"),   # known only after the D1 bar closes
        "d1a": np.where(d["ema_50"].values > d["ema_200"].values, 1, -1),
        "d1b": np.where(c > d["ema_200"].values, 1, -1),
        "d1c": np.where(c > d["sma_50"].values, 1, -1),
    }).sort_values("avail").reset_index(drop=True)
    return out


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
    """merge_asof the D1 trend onto each M15 bar (backward, no lookahead)."""
    left = d[["time"]].copy()
    left["time"] = left["time"].astype("datetime64[ns]")
    m = pd.merge_asof(left, trend, left_on="time", right_on="avail", direction="backward")
    return m["d1a"].values, m["d1b"].values, m["d1c"].values


def simulate(d, dirs, cost_price, d1col=None, lo=None, hi=None):
    """One-position-at-a-time ordered SL/TP. If d1col given, a trade fires only when
    its direction matches the D1 trend sign at the entry bar."""
    high = d["high"].values; low = d["low"].values; close = d["close"].values
    atr = d["atr_14"].values; tarr = d["time"].values
    n = len(close)
    lo = 0 if lo is None else lo
    hi = n if hi is None else hi
    trades = []
    busy_until = lo - 1
    for i in np.where(dirs != 0)[0]:
        if i < lo or i >= hi or i <= busy_until:
            continue
        dirn = int(dirs[i])
        if d1col is not None and d1col[i] != dirn:
            continue  # signal not aligned with D1 trend -> skip
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        entry = close[i]
        if dirn == 1:
            tp, sl = entry + MACD_TP * a, entry - MACD_SL * a
        else:
            tp, sl = entry - MACD_TP * a, entry + MACD_SL * a
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
            continue
        trades.append({"win": outcome == "W", "atr": a, "time": tarr[i], "cost_atr": cost_price / a})
    return trades


def stats(trades):
    if not trades:
        return 0, 0.0, float("nan"), float("nan"), float("nan")
    n = len(trades); w = sum(t["win"] for t in trades); l = n - w
    wr = 100 * w / n
    pf_clean = (w * MACD_TP) / (l * MACD_SL) if l else float("inf")
    net = np.array([(MACD_TP if t["win"] else -MACD_SL) - t["cost_atr"] for t in trades])
    pos = net[net > 0].sum(); neg = -net[net < 0].sum()
    pf_net = pos / neg if neg > 0 else float("inf")
    return n, wr, pf_clean, pf_net, net.mean()


def main():
    syms = sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob("data/raw/*/M15.parquet"))
    cost_price = {s: SPREAD_PRICE.get(s, 1e-4) + SLIPPAGE_PRICE.get(s, 3e-5) for s in syms}

    data, dmark, d1cols = {}, {}, {}
    for s in syms:
        data[s] = enrich_m15(s)
        dmark[s] = macd_dir(data[s])
        a, b, c = attach_d1(data[s], d1_trend(s))
        d1cols[s] = {"d1a": a, "d1b": b, "d1c": c}
        print(f"  ready {s}: {len(data[s]):,} M15 bars", flush=True)

    L = ["# Rescue Plan — Phase 5c: MACD-M15 + D1 Trend Filter\n"]
    L.append(f"**Data:** {len(syms)} symbols × full M15 (~100k/symbol). Same MACD logic + "
             f"ATR({ATR_THR}), ordered SL/TP, horizon={HORIZON}, SL={MACD_SL}/TP={MACD_TP}×ATR, "
             f"per-symbol spread+slippage charged per trade. D1 trend joined no-lookahead "
             f"(prior closed daily bar).")
    L.append("**D1 filter:** BUY only if D1 trend up, SELL only if D1 trend down.\n")
    L.append("D1 variants: **d1a** EMA50>EMA200 · **d1b** close>EMA200 · **d1c** close>SMA50\n")

    # ---- A) Full-sample: baseline vs each D1 variant ----
    L.append("## A. Full-sample (pooled) — baseline vs D1 filters\n")
    L.append("| Config | Trades | Win% | PF_clean | PF_net | EV_net | Trades kept |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")

    def run_full(variant):
        allt = []
        for s in syms:
            col = None if variant is None else d1cols[s][variant]
            allt.extend(simulate(data[s], dmark[s], cost_price[s], d1col=col))
        return allt

    base = run_full(None)
    bn, bwr, bpfc, bpfn, bev = stats(base)
    L.append(f"| baseline (no D1) | {bn:,} | {bwr:.1f}% | {bpfc:.3f} | {bpfn:.3f} | {bev:+.4f} | 100% |")
    print(f"baseline: n={bn} pf_net={bpfn:.3f}", flush=True)

    variant_trades = {}
    for v, label in [("d1a", "+ D1a EMA50>200"), ("d1b", "+ D1b close>EMA200"), ("d1c", "+ D1c close>SMA50")]:
        t = run_full(v); variant_trades[v] = t
        n, wr, pfc, pfn, ev = stats(t)
        keep = f"{100*n/bn:.0f}%" if bn else "—"
        flag = " ✅" if (pfn == pfn and pfn >= 1.0) else ""
        L.append(f"| {label} | {n:,} | {wr:.1f}% | {pfc:.3f} | {pfn:.3f} | {ev:+.4f} | {keep}{flag} |")
        print(f"{v}: n={n} pf_clean={pfc:.3f} pf_net={pfn:.3f} ev={ev:+.4f}", flush=True)

    # pick best variant by PF_net for deeper analysis
    best_v = max(variant_trades, key=lambda v: (stats(variant_trades[v])[3] if stats(variant_trades[v])[3] == stats(variant_trades[v])[3] else -9))
    bpfn_best = stats(variant_trades[best_v])[3]
    L.append(f"\n**Best D1 variant by PF_net:** `{best_v}` (PF_net {bpfn_best:.3f}).")

    # ---- B) Per-symbol for best variant ----
    L.append(f"\n## B. Per-symbol — best variant `{best_v}` (net of cost)\n")
    L.append("| Symbol | Trades | Win% | PF_clean | PF_net | EV_net |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for s in syms:
        t = simulate(data[s], dmark[s], cost_price[s], d1col=d1cols[s][best_v])
        n, wr, pfc, pfn, ev = stats(t)
        flag = "" if (pfn == pfn and pfn >= 1.0) else " ❌"
        L.append(f"| {s} | {n:,} | {wr:.1f}% | {pfc:.3f} | {pfn:.3f} | {ev:+.4f}{flag} |")

    # ---- C) Walk-forward folds for best variant ----
    L.append(f"\n## C. Walk-forward stability — best variant `{best_v}` ({N_FOLDS} folds)\n")
    L.append("| Fold (old→new) | Trades | Win% | PF_clean | PF_net | EV_net |")
    L.append("|---|---:|---:|---:|---:|---:|")
    fold_pfnet = []
    for k in range(N_FOLDS):
        ftr = []
        for s in syms:
            nbar = len(data[s]); lo = nbar * k // N_FOLDS; hi = nbar * (k + 1) // N_FOLDS
            ftr.extend(simulate(data[s], dmark[s], cost_price[s], d1col=d1cols[s][best_v], lo=lo, hi=hi))
        n, wr, pfc, pfn, ev = stats(ftr)
        fold_pfnet.append(pfn)
        L.append(f"| {k+1} | {n:,} | {wr:.1f}% | {pfc:.3f} | {pfn:.3f} | {ev:+.4f} |")
        print(f"fold {k+1}: n={n} pf_net={pfn:.3f}", flush=True)
    valid = [x for x in fold_pfnet if x == x]
    n_pos = sum(1 for x in valid if x >= 1.0)
    L.append(f"\n**Fold PF_net:** min={min(valid):.3f}, max={max(valid):.3f}, "
             f"profitable folds = {n_pos}/{len(valid)}.")

    # ---- D) Per-year for best variant ----
    L.append(f"\n## D. Per-year — best variant `{best_v}` (net of cost)\n")
    L.append("| Year | Trades | Win% | PF_clean | PF_net | EV_net |")
    L.append("|---|---:|---:|---:|---:|---:|")
    by_year = {}
    for t in variant_trades[best_v]:
        by_year.setdefault(pd.Timestamp(t["time"]).year, []).append(t)
    for yr in sorted(by_year):
        n, wr, pfc, pfn, ev = stats(by_year[yr])
        L.append(f"| {yr} | {n:,} | {wr:.1f}% | {pfc:.3f} | {pfn:.3f} | {ev:+.4f} |")

    # ---- Verdict scaffold ----
    L.append("\n## Verdict (same gates as 5b)\n")
    L.append("- G1 Full-sample PF_net ≥ 1.05 · G2 ≥6/8 folds PF_net≥1.0 · "
             "G3 recent era (2025/26) PF_net≥1.0 · G4 ≥4/7 symbols PF_net≥1.0")
    L.append(f"\nBaseline (5b) PF_net was **{bpfn:.3f}**. If the best D1 filter clears the gates, "
             f"the D1-trend gate rescues the live MACD-M15 engine (cheap, no margin/holding change). "
             f"If it only nudges PF_net up but still <1.0, the daily trend is not enough and the "
             f"price-only-TA hypothesis is exhausted (per Phase 4a/5b).")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"\nReport written: {OUT}", flush=True)


if __name__ == "__main__":
    main()
