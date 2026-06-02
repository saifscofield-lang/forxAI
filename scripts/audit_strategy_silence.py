"""
Strategy-Silence Funnel Audit  (Rescue Plan — Phase 1d, READ-ONLY)
==================================================================
Goal (the user's priority = MORE TRADES): find exactly which gating condition
kills the most potential signals in each rule-based strategy, and quantify how
many extra signals we would get by relaxing each single condition.

For each strategy we replay history as a funnel (conditions in firing order)
and count how many bars survive each stage. Then a "what-if" table recomputes
the fire rate when each lever is relaxed one at a time — so we can pick the
loosening that maximises trade frequency with the smallest quality risk.

Fire rate is reported as signals per 1,000 bars and projected signals/year/
symbol (FX H1 ≈ 6,000 bars/year), aggregated over all symbols.

READ-ONLY: reads data/raw/*.parquet, writes a markdown report. Mirrors the
exact conditions in strategies/{macd_crossover,rsi_reversal,bollinger_bounce}.py
and strategies/filters.py (passes_atr_filter). Safe during the freeze.

Run with project venv:
    venv/Scripts/python.exe scripts/audit_strategy_silence.py
"""
import sys
import os
import glob
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from features.technical.indicators import add_macd, add_atr, add_ema, add_rsi, add_bollinger_bands

OUT = "docs/research/rescue_phase1d_strategy_silence.md"
SAMPLE_BARS = 30000
BARS_PER_YEAR = 6000


def enrich(sym):
    df = pd.read_parquet(f"data/raw/{sym}/H1.parquet").sort_values("time").tail(SAMPLE_BARS).reset_index(drop=True)
    df = add_macd(df)
    df = add_atr(df, 14)
    df = add_ema(df, 50)
    df = add_ema(df, 200)
    df = add_rsi(df, 14)
    df = add_bollinger_bands(df, 20)
    df["avg_atr20"] = df["atr_14"].rolling(20).mean()
    return df.dropna(subset=["macd_line", "macd_signal", "macd_hist", "atr_14",
                             "ema_50", "ema_200", "rsi_14", "bb_upper", "bb_lower",
                             "avg_atr20"]).reset_index(drop=True)


def macd_masks(d, atr_thr=1.2, use_hist=True):
    price = d["close"].values
    macd, sig = d["macd_line"].values, d["macd_signal"].values
    hist = d["macd_hist"].values
    ema50, ema200 = d["ema_50"].values, d["ema_200"].values
    atr, avg = d["atr_14"].values, d["avg_atr20"].values
    pm, ps = np.roll(macd, 1), np.roll(sig, 1)
    ph = np.roll(hist, 1)
    atr_ok = atr >= atr_thr * avg
    cross_up = (pm <= ps) & (macd > sig)
    cross_dn = (pm >= ps) & (macd < sig)
    buy = atr_ok & cross_up & (price > ema50) & (ema50 > ema200)
    sell = atr_ok & cross_dn & (price < ema50) & (ema50 < ema200)
    if use_hist:
        buy = buy & (hist > ph)
        sell = sell & (hist < ph)
    buy[:1] = sell[:1] = False
    return atr_ok, (cross_up | cross_dn), (buy | sell)


def rsi_masks(d, atr_thr=1.2, os_=30.0, ob=70.0, use_2bar=True, use_price=True):
    price = d["close"].values
    rsi = d["rsi_14"].values
    atr, avg = d["atr_14"].values, d["avg_atr20"].values
    rp, rp2 = np.roll(rsi, 1), np.roll(rsi, 2)
    pc = np.roll(price, 1)
    atr_ok = atr >= atr_thr * avg
    if use_2bar:
        buy = (rsi < os_) & (rsi > rp) & (rp > rp2)
        sell = (rsi > ob) & (rsi < rp) & (rp < rp2)
    else:
        buy = (rsi < os_) & (rsi > rp)
        sell = (rsi > ob) & (rsi < rp)
    buy, sell = atr_ok & buy, atr_ok & sell
    if use_price:
        buy = buy & (price >= pc)
        sell = sell & (price <= pc)
    buy[:2] = sell[:2] = False
    return atr_ok, (buy | sell)


def bb_masks(d, atr_thr=1.0, width_cap=0.03, rsi_buy=40.0, rsi_sell=60.0):
    price = d["close"].values
    bu, bl = d["bb_upper"].values, d["bb_lower"].values
    rsi = d["rsi_14"].values
    atr, avg = d["atr_14"].values, d["avg_atr20"].values
    pp, pbu, pbl = np.roll(price, 1), np.roll(bu, 1), np.roll(bl, 1)
    width_pct = (bu - bl) / np.where(price > 0, price, np.nan)
    width = bu - bl
    width_avg = pd.Series(width).rolling(20).mean().values
    atr_ok = atr >= atr_thr * avg
    width_ok = width_pct <= width_cap
    bounce_buy = (pp <= pbl) & (price > bl)
    bounce_sell = (pp >= pbu) & (price < bu)
    buy = atr_ok & width_ok & bounce_buy & (rsi <= rsi_buy) & (width <= width_avg * 2.0)
    sell = atr_ok & width_ok & bounce_sell & (rsi >= rsi_sell) & (width <= width_avg * 2.0)
    buy[:20] = sell[:20] = False
    return atr_ok, width_ok, (bounce_buy | bounce_sell), (buy | sell)


def main():
    syms = sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob("data/raw/*/H1.parquet"))
    data = {s: enrich(s) for s in syms}
    total_bars = sum(len(d) for d in data.values())

    def fire_rate(fn_key):
        fires = 0
        for s in syms:
            fires += fn_key(data[s])
        return fires

    L = ["# Rescue Plan — Phase 1d: Strategy-Silence Funnel Audit\n"]
    L.append(f"**Data:** {len(syms)} symbols × last {SAMPLE_BARS:,} H1 bars "
             f"= {total_bars:,} bars (~3.4y/symbol).")
    L.append("**Goal:** identify the condition that blocks the most signals, and quantify "
             "the trade-frequency gain from relaxing each lever.\n")

    def line(label, fires):
        per1k = 1000 * fires / total_bars
        per_yr = per1k / 1000 * BARS_PER_YEAR  # per symbol-year
        return f"| {label} | {fires:,} | {per1k:.2f} | {per_yr:.0f} |"

    # ── MACD ──
    L.append("## MACD Crossover — funnel\n")
    L.append("| Stage (cumulative) | Bars passing | per 1k bars | per symbol-yr |")
    L.append("|---|---:|---:|---:|")
    atr_p = cross_p = fire = 0
    for s in syms:
        a, c, f = macd_masks(data[s])
        atr_p += int(a.sum()); cross_p += int((a & c).sum()); fire += int(f.sum())
    L.append(line("1. ATR filter ≥1.2×avg", atr_p))
    L.append(line("2. + MACD cross", cross_p))
    L.append(line("3. + trend & histogram = FIRE", fire))
    L.append("\n**What-if levers (relax one at a time):**\n")
    L.append("| Lever | Signals | per 1k | per symbol-yr | vs current |")
    L.append("|---|---:|---:|---:|---:|")
    base = fire
    for label, fn in [
        ("CURRENT", lambda d: int(macd_masks(d)[2].sum())),
        ("ATR thr 1.2→1.0", lambda d: int(macd_masks(d, atr_thr=1.0)[2].sum())),
        ("ATR filter OFF", lambda d: int(macd_masks(d, atr_thr=0.0)[2].sum())),
        ("histogram momentum OFF", lambda d: int(macd_masks(d, use_hist=False)[2].sum())),
        ("ATR 1.0 + hist OFF", lambda d: int(macd_masks(d, atr_thr=1.0, use_hist=False)[2].sum())),
    ]:
        f = fire_rate(fn)
        mult = f"{f/base:.1f}×" if base else "—"
        L.append(f"| {label} | {f:,} | {1000*f/total_bars:.2f} | {f/total_bars*BARS_PER_YEAR:.0f} | {mult} |")

    # ── RSI ──
    L.append("\n## RSI Reversal — funnel\n")
    L.append("| Stage (cumulative) | Bars passing | per 1k bars | per symbol-yr |")
    L.append("|---|---:|---:|---:|")
    atr_p = fire = 0
    for s in syms:
        a, f = rsi_masks(data[s])
        atr_p += int(a.sum()); fire += int(f.sum())
    L.append(line("1. ATR filter ≥1.2×avg", atr_p))
    L.append(line("2. + RSI extreme +2bar +price = FIRE", fire))
    L.append("\n**What-if levers:**\n")
    L.append("| Lever | Signals | per 1k | per symbol-yr | vs current |")
    L.append("|---|---:|---:|---:|---:|")
    base = fire
    for label, fn in [
        ("CURRENT (30/70, 2bar, price)", lambda d: int(rsi_masks(d)[1].sum())),
        ("bands 30/70→35/65", lambda d: int(rsi_masks(d, os_=35, ob=65)[1].sum())),
        ("drop 2-bar confirm", lambda d: int(rsi_masks(d, use_2bar=False)[1].sum())),
        ("drop price confirm", lambda d: int(rsi_masks(d, use_price=False)[1].sum())),
        ("ATR thr 1.2→1.0", lambda d: int(rsi_masks(d, atr_thr=1.0)[1].sum())),
        ("35/65 + no 2-bar + ATR1.0", lambda d: int(rsi_masks(d, atr_thr=1.0, os_=35, ob=65, use_2bar=False)[1].sum())),
    ]:
        f = fire_rate(fn)
        mult = f"{f/base:.1f}×" if base else "—"
        L.append(f"| {label} | {f:,} | {1000*f/total_bars:.2f} | {f/total_bars*BARS_PER_YEAR:.0f} | {mult} |")

    # ── Bollinger ──
    L.append("\n## Bollinger Bounce — funnel\n")
    L.append("| Stage (cumulative) | Bars passing | per 1k bars | per symbol-yr |")
    L.append("|---|---:|---:|---:|")
    atr_p = w_p = b_p = fire = 0
    for s in syms:
        a, w, b, f = bb_masks(data[s])
        atr_p += int(a.sum()); w_p += int((a & w).sum()); b_p += int((a & w & b).sum()); fire += int(f.sum())
    L.append(line("1. ATR filter ≥1.0×avg", atr_p))
    L.append(line("2. + BB width ≤3%", w_p))
    L.append(line("3. + bounce confirm", b_p))
    L.append(line("4. + RSI 40/60 & width = FIRE", fire))
    L.append("\n**What-if levers:**\n")
    L.append("| Lever | Signals | per 1k | per symbol-yr | vs current |")
    L.append("|---|---:|---:|---:|---:|")
    base = fire
    for label, fn in [
        ("CURRENT", lambda d: int(bb_masks(d)[3].sum())),
        ("RSI 40/60→45/55", lambda d: int(bb_masks(d, rsi_buy=45, rsi_sell=55)[3].sum())),
        ("RSI confirm OFF (50/50)", lambda d: int(bb_masks(d, rsi_buy=50, rsi_sell=50)[3].sum())),
        ("BB width cap 3%→5%", lambda d: int(bb_masks(d, width_cap=0.05)[3].sum())),
    ]:
        f = fire_rate(fn)
        mult = f"{f/base:.1f}×" if base else "—"
        L.append(f"| {label} | {f:,} | {1000*f/total_bars:.2f} | {f/total_bars*BARS_PER_YEAR:.0f} | {mult} |")

    L.append("\n## How to use this\n")
    L.append("- The funnel shows WHERE signals die. The **what-if** table shows the trade-count "
             "multiplier from each single relaxation.")
    L.append("- Pick levers with the best frequency gain **and** that Phase 1a/evidence says are "
             "safe. The ATR filter is evidence-backed (STAT-003: winners ATR 3.59 vs losers 1.18) "
             "so prefer tuning its threshold over removing it.")
    L.append("- **Next step after choosing levers:** backtest the relaxed config on "
             "`data/backtest_results.db` tooling to confirm profit factor holds BEFORE going live "
             "(per the balanced approach). Adding M15 timeframe is a separate ~4× frequency lever "
             "not modelled here (it multiplies bar count).")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"Report written: {OUT}")


if __name__ == "__main__":
    main()
