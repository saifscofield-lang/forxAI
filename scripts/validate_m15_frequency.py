"""
M15-Frequency Validation  (Rescue Plan — Phase 1f, READ-ONLY backtest-lite)
===========================================================================
Phase 1e proved relaxing the ATR filter destroys edge. The remaining frequency
lever is scanning a LOWER timeframe (M15) with the SAME strategy logic and the
SAME (kept) filters — ~4x more candles => more setups at unchanged per-trade
quality. This validates that: does PF hold on M15 vs H1?

Compares H1 (current) vs M15 for MACD and RSI at their real configs, reporting
trades, win%, R-PF, net R, and trades/symbol-year (per timeframe bar density).

READ-ONLY. Run: venv/Scripts/python.exe scripts/validate_m15_frequency.py
"""
import sys
import os
import glob
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from features.technical.indicators import add_macd, add_atr, add_ema, add_rsi

OUT = "docs/research/rescue_phase1f_m15_validation.md"
SAMPLE_BARS = 30000
HORIZON = 100
MACD_SL, MACD_TP = 2.5, 3.5
RSI_SL, RSI_TP = 2.0, 3.0
# approx bars/year by timeframe (FX ~24h x ~5d): H1 ~6000, M15 ~24000
BARS_PER_YEAR = {"H1": 6000, "M15": 24000}


def enrich(sym, tf):
    df = pd.read_parquet(f"data/raw/{sym}/{tf}.parquet").sort_values("time").tail(SAMPLE_BARS).reset_index(drop=True)
    df = add_macd(df); df = add_atr(df, 14); df = add_ema(df, 50); df = add_ema(df, 200); df = add_rsi(df, 14)
    df["avg_atr20"] = df["atr_14"].rolling(20).mean()
    return df.dropna(subset=["macd_line", "macd_signal", "macd_hist", "atr_14",
                             "ema_50", "ema_200", "rsi_14", "avg_atr20"]).reset_index(drop=True)


def macd_dir(d, thr=1.2):
    price = d["close"].values; macd = d["macd_line"].values; sig = d["macd_signal"].values
    hist = d["macd_hist"].values; ema50 = d["ema_50"].values; ema200 = d["ema_200"].values
    atr = d["atr_14"].values; avg = d["avg_atr20"].values
    pm, ps, ph = np.roll(macd, 1), np.roll(sig, 1), np.roll(hist, 1)
    ok = atr >= thr * avg
    buy = ok & (pm <= ps) & (macd > sig) & (price > ema50) & (ema50 > ema200) & (hist > ph)
    sell = ok & (pm >= ps) & (macd < sig) & (price < ema50) & (ema50 < ema200) & (hist < ph)
    o = np.zeros(len(d), np.int8); o[buy] = 1; o[sell] = -1; o[:1] = 0
    return o


def rsi_dir(d, thr=1.2, os_=30.0, ob=70.0):
    price = d["close"].values; rsi = d["rsi_14"].values
    atr = d["atr_14"].values; avg = d["avg_atr20"].values
    rp, rp2, pc = np.roll(rsi, 1), np.roll(rsi, 2), np.roll(price, 1)
    ok = atr >= thr * avg
    buy = ok & (rsi < os_) & (rsi > rp) & (rp > rp2) & (price >= pc)
    sell = ok & (rsi > ob) & (rsi < rp) & (rp < rp2) & (price <= pc)
    o = np.zeros(len(d), np.int8); o[buy] = 1; o[sell] = -1; o[:2] = 0
    return o


def simulate(d, dirs, sl_m, tp_m):
    high = d["high"].values; low = d["low"].values; close = d["close"].values; atr = d["atr_14"].values
    n = len(close); wins = losses = trades = 0; busy_until = -1
    for i in np.where(dirs != 0)[0]:
        if i <= busy_until:
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        entry = close[i]; dirn = dirs[i]
        tp, sl = (entry + tp_m * a, entry - sl_m * a) if dirn == 1 else (entry - tp_m * a, entry + sl_m * a)
        outcome = None
        for j in range(i + 1, min(i + 1 + HORIZON, n)):
            if dirn == 1:
                if low[j] <= sl: outcome = "L"; break
                if high[j] >= tp: outcome = "W"; break
            else:
                if high[j] >= sl: outcome = "L"; break
                if low[j] <= tp: outcome = "W"; break
            busy_until = j
        if outcome == "W": wins += 1; trades += 1
        elif outcome == "L": losses += 1; trades += 1
    return trades, wins, losses


def main():
    syms = sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob("data/raw/*/H1.parquet"))
    L = ["# Rescue Plan — Phase 1f: M15-Frequency Validation\n"]
    L.append(f"**Data:** {len(syms)} symbols × {SAMPLE_BARS:,} bars per timeframe. Same strategy "
             f"logic + ATR filter (1.2). One-position-at-a-time, ordered SL/TP, horizon={HORIZON}.\n")

    for name, dir_fn, sl_m, tp_m in [("MACD Crossover", macd_dir, MACD_SL, MACD_TP),
                                     ("RSI Reversal", rsi_dir, RSI_SL, RSI_TP)]:
        L.append(f"\n## {name}\n")
        L.append("| Timeframe | Trades | Win% | PF (R) | Net R | Trades/symbol-yr |")
        L.append("|---|---:|---:|---:|---:|---:|")
        for tf in ("H1", "M15"):
            data = {}
            ok = True
            for s in syms:
                p = f"data/raw/{s}/{tf}.parquet"
                if not os.path.exists(p):
                    ok = False; break
                data[s] = enrich(s, tf)
            if not ok:
                L.append(f"| {tf} | — missing data — | | | | |"); continue
            total_bars = sum(len(d) for d in data.values())
            tt = tw = tl = 0
            for d in data.values():
                t, w, l = simulate(d, dir_fn(d), sl_m, tp_m)
                tt += t; tw += w; tl += l
            wr = 100 * tw / (tw + tl) if (tw + tl) else 0
            pf = (tw * tp_m) / (tl * sl_m) if tl else float("inf")
            net_r = tw * tp_m - tl * sl_m
            per_yr = tt / total_bars * BARS_PER_YEAR[tf]
            print(f"{name} {tf}: trades={tt} pf={pf:.2f}", flush=True)
            L.append(f"| {tf} | {tt:,} | {wr:.0f}% | {pf:.2f} | {net_r:+.0f} | {per_yr:.0f} |")

    L.append("\n## Verdict\n")
    L.append("- If M15 keeps **PF (R) ≈ H1's** while raising trades/symbol-yr substantially, "
             "M15 is the validated frequency lever → add M15 signal generation (keep all filters).")
    L.append("- If M15 PF degrades materially, lower-timeframe noise hurts these strategies → "
             "frequency must come from more symbols or new strategies instead.")
    L.append("- Same caveat as 1e: clean ATR-exit sim, no spread/slippage/downstream filters; "
             "PF is a *relative* H1-vs-M15 comparison.")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"Report written: {OUT}")


if __name__ == "__main__":
    main()
