"""
ATR-Lever Validation  (Rescue Plan — Phase 1e, READ-ONLY backtest-lite)
=======================================================================
The silence audit (Phase 1d) showed the ATR regime filter (>=1.2x avg) is the
dominant throttle on MACD & RSI, and lowering it 1.2 -> 1.0 yields ~4x / ~3x
more signals. The balanced approach REQUIRES we confirm profit factor holds
before deploying. This script does that fast.

For each strategy config it computes the fire mask (vectorised, matching the
real strategy logic) then simulates each fired trade with that strategy's OWN
ATR SL/TP multipliers, ordered first-touch. Reports trades, win%, R-multiple
profit factor, net R, and trades/symbol-year for ATR thresholds 1.2 vs 1.0.

PF (R) = (wins * tp_mult) / (losses * sl_mult). PF > 1.0 = profitable edge.

READ-ONLY: reads data/raw/*.parquet, prints + writes markdown. No live state.
Run: venv/Scripts/python.exe scripts/validate_atr_lever.py
"""
import sys
import os
import glob
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from features.technical.indicators import add_macd, add_atr, add_ema, add_rsi

OUT = "docs/research/rescue_phase1e_atr_validation.md"
SAMPLE_BARS = 30000
BARS_PER_YEAR = 6000
HORIZON = 100  # bars to resolve a trade (wide SL/TP can run long)

MACD_SL, MACD_TP = 2.5, 3.5   # strategies/macd_crossover.py defaults
RSI_SL, RSI_TP = 2.0, 3.0     # strategies/rsi_reversal.py defaults


def enrich(sym):
    df = pd.read_parquet(f"data/raw/{sym}/H1.parquet").sort_values("time").tail(SAMPLE_BARS).reset_index(drop=True)
    df = add_macd(df); df = add_atr(df, 14); df = add_ema(df, 50); df = add_ema(df, 200); df = add_rsi(df, 14)
    df["avg_atr20"] = df["atr_14"].rolling(20).mean()
    return df.dropna(subset=["macd_line", "macd_signal", "macd_hist", "atr_14",
                             "ema_50", "ema_200", "rsi_14", "avg_atr20"]).reset_index(drop=True)


def macd_dir(d, atr_thr):
    price = d["close"].values; macd = d["macd_line"].values; sig = d["macd_signal"].values
    hist = d["macd_hist"].values; ema50 = d["ema_50"].values; ema200 = d["ema_200"].values
    atr = d["atr_14"].values; avg = d["avg_atr20"].values
    pm, ps, ph = np.roll(macd, 1), np.roll(sig, 1), np.roll(hist, 1)
    ok = atr >= atr_thr * avg
    buy = ok & (pm <= ps) & (macd > sig) & (price > ema50) & (ema50 > ema200) & (hist > ph)
    sell = ok & (pm >= ps) & (macd < sig) & (price < ema50) & (ema50 < ema200) & (hist < ph)
    d2 = np.zeros(len(d), dtype=np.int8); d2[buy] = 1; d2[sell] = -1; d2[:1] = 0
    return d2


def rsi_dir(d, atr_thr, os_=30.0, ob=70.0):
    price = d["close"].values; rsi = d["rsi_14"].values
    atr = d["atr_14"].values; avg = d["avg_atr20"].values
    rp, rp2, pc = np.roll(rsi, 1), np.roll(rsi, 2), np.roll(price, 1)
    ok = atr >= atr_thr * avg
    buy = ok & (rsi < os_) & (rsi > rp) & (rp > rp2) & (price >= pc)
    sell = ok & (rsi > ob) & (rsi < rp) & (rp < rp2) & (price <= pc)
    d2 = np.zeros(len(d), dtype=np.int8); d2[buy] = 1; d2[sell] = -1; d2[:2] = 0
    return d2


def simulate(d, dirs, sl_m, tp_m):
    """One-position-at-a-time sim (skip new signals while in a trade). Returns (n,wins,losses)."""
    high = d["high"].values; low = d["low"].values; close = d["close"].values; atr = d["atr_14"].values
    n = len(close); i = 0; wins = losses = trades = 0
    idxs = np.where(dirs != 0)[0]
    set_idx = set(idxs.tolist())
    busy_until = -1
    for i in idxs:
        if i <= busy_until:
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        entry = close[i]; dirn = dirs[i]
        if dirn == 1:
            tp, sl = entry + tp_m * a, entry - sl_m * a
        else:
            tp, sl = entry - tp_m * a, entry + sl_m * a
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
        # timeout: not counted as decided
    return trades, wins, losses


def run_cfg(data, dir_fn, sl_m, tp_m, thr):
    tot_t = tot_w = tot_l = 0
    for d in data.values():
        dirs = dir_fn(d, thr)
        t, w, l = simulate(d, dirs, sl_m, tp_m)
        tot_t += t; tot_w += w; tot_l += l
    return tot_t, tot_w, tot_l


def main():
    syms = sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob("data/raw/*/H1.parquet"))
    data = {s: enrich(s) for s in syms}
    total_bars = sum(len(d) for d in data.values())
    nsym = len(syms)

    L = ["# Rescue Plan — Phase 1e: ATR-Lever Validation (backtest-lite)\n"]
    L.append(f"**Data:** {nsym} symbols × {SAMPLE_BARS:,} H1 bars. One-position-at-a-time, "
             f"ordered SL/TP, horizon={HORIZON} bars. Decided trades only (timeouts excluded).")
    L.append("**PF (R)** = (wins×TP_mult)/(losses×SL_mult). PF>1.0 = profitable edge.\n")

    def block(name, dir_fn, sl_m, tp_m):
        rows = [f"\n## {name}  (SL={sl_m}×ATR, TP={tp_m}×ATR)\n",
                "| ATR thr | Trades | Win% | PF (R) | Net R | Trades/symbol-yr |",
                "|---|---:|---:|---:|---:|---:|"]
        base_t = None
        for thr in (1.2, 1.0):
            t, w, l = run_cfg(data, dir_fn, sl_m, tp_m, thr)
            wr = 100 * w / (w + l) if (w + l) else 0
            pf = (w * tp_m) / (l * sl_m) if l else float("inf")
            net_r = w * tp_m - l * sl_m
            per_yr = t / total_bars * BARS_PER_YEAR
            tag = " (CURRENT)" if thr == 1.2 else " (RELAXED)"
            rows.append(f"| {thr:.1f}{tag} | {t:,} | {wr:.0f}% | {pf:.2f} | {net_r:+.0f} | {per_yr:.0f} |")
        return "\n".join(rows)

    print("Running MACD...", flush=True)
    L.append(block("MACD Crossover", macd_dir, MACD_SL, MACD_TP))
    print("Running RSI...", flush=True)
    L.append(block("RSI Reversal", rsi_dir, RSI_SL, RSI_TP))

    L.append("\n## Verdict\n")
    L.append("- If **PF (R) stays > 1.0** (ideally near the current value) when ATR thr drops "
             "1.2→1.0, the relaxation increases trade count **without destroying edge** → SHIP it.")
    L.append("- If PF collapses below 1.0, the 1.2 filter is carrying the edge → keep it and find "
             "frequency elsewhere (M15 timeframe, more symbols).")
    L.append("- Note: this is a clean ATR-exit sim without spread/slippage/downstream filters; "
             "treat PF as a *relative* comparison between thresholds, not a live P&L forecast.")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"Report written: {OUT}")


if __name__ == "__main__":
    main()
