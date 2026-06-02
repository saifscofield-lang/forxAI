"""
SMA Crossover — Root-Cause Diagnosis (Rescue Phase 3b, READ-ONLY)
=================================================================
SMA crossover is a TREND strategy (fast SMA crosses slow + RSI gate). Since the
data rewards momentum (Phase 3a insight), SMA *could* have edge like MACD — or
its lag could kill it. Diagnose with the same rigor:

  T1 PREMISE. After a bullish cross does price continue UP (and bearish -> DOWN)?
     Forward move in ATR units, pooled. Trend-continuation edge exists only if
     cross-up fwd-move > 0 and cross-down fwd-move < 0, clearly above noise.
  T2 REGIME (ADX). A trend strategy should win in TRENDING, lose in RANGING.
  T3 PARAM SWEEP. Periods (10/30, 20/50, 50/100, 50/200) on H1 + the 20/50 on
     M15 (MACD gained on M15). Any config with R-PF > 1?
  T4 WALK-FORWARD. Is any edge stable across 3 time blocks (luck control)?

Real SMA exits: SL=2.0xATR, TP=3.0xATR (sma_crossover defaults).
READ-ONLY. Run: venv/Scripts/python.exe scripts/diagnose_sma.py
"""
import sys
import os
import glob
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from features.technical.indicators import add_sma, add_rsi, add_atr

OUT = "docs/research/rescue_phase3b_sma_diagnosis.md"
SL_MULT, TP_MULT = 2.0, 3.0
ATR_THR = 1.2
HORIZON = 100
FWD = 12
SAMPLE = 60000


def wilder_adx(df, n=14):
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    pc = np.roll(c, 1); ph = np.roll(h, 1); pl = np.roll(l, 1)
    tr = np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])
    up = h - ph; dn = pl - l
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr[0] = pdm[0] = mdm[0] = 0.0
    a = 1.0 / n
    st = pd.Series(tr).ewm(alpha=a, adjust=False).mean().values
    sp = pd.Series(pdm).ewm(alpha=a, adjust=False).mean().values
    sm = pd.Series(mdm).ewm(alpha=a, adjust=False).mean().values
    pdi = 100 * sp / np.where(st == 0, np.nan, st)
    mdi = 100 * sm / np.where(st == 0, np.nan, st)
    dx = 100 * np.abs(pdi - mdi) / np.where((pdi + mdi) == 0, np.nan, pdi + mdi)
    return pd.Series(dx).ewm(alpha=a, adjust=False).mean().values


def enrich(sym, tf="H1", fast=20, slow=50):
    df = pd.read_parquet(f"data/raw/{sym}/{tf}.parquet").sort_values("time").tail(SAMPLE).reset_index(drop=True)
    df = add_sma(df, fast); df = add_sma(df, slow); df = add_rsi(df, 14); df = add_atr(df, 14)
    df["avg_atr20"] = df["atr_14"].rolling(20).mean()
    df["adx"] = wilder_adx(df)
    return df.dropna(subset=[f"sma_{fast}", f"sma_{slow}", "rsi_14", "atr_14", "avg_atr20", "adx"]).reset_index(drop=True)


def sma_signals(d, fast=20, slow=50, use_atr=True, use_rsi=True):
    price = d["close"].values; rsi = d["rsi_14"].values
    f = d[f"sma_{fast}"].values; s = d[f"sma_{slow}"].values
    atr = d["atr_14"].values; avg = d["avg_atr20"].values
    pf, ps = np.roll(f, 1), np.roll(s, 1)
    ok = (atr >= ATR_THR * avg) if use_atr else np.ones(len(d), bool)
    buy = ok & (pf <= ps) & (f > s)
    sell = ok & (pf >= ps) & (f < s)
    if use_rsi:
        buy = buy & (rsi < 70); sell = sell & (rsi > 30)
    o = np.zeros(len(d), np.int8); o[buy] = 1; o[sell] = -1; o[:1] = 0
    return o


def simulate(d, dirs, mask=None):
    high = d["high"].values; low = d["low"].values; close = d["close"].values; atr = d["atr_14"].values
    n = len(close); w = l = 0; busy = -1
    for i in np.where(dirs != 0)[0]:
        if i <= busy:
            continue
        if mask is not None and not mask[i]:
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        e = close[i]; dn = dirs[i]
        tp, sl = (e + TP_MULT * a, e - SL_MULT * a) if dn == 1 else (e - TP_MULT * a, e + SL_MULT * a)
        out = None
        for j in range(i + 1, min(i + 1 + HORIZON, n)):
            if dn == 1:
                if low[j] <= sl: out = "L"; break
                if high[j] >= tp: out = "W"; break
            else:
                if high[j] >= sl: out = "L"; break
                if low[j] <= tp: out = "W"; break
            busy = j
        if out == "W": w += 1
        elif out == "L": l += 1
    pf = (w * TP_MULT) / (l * SL_MULT) if l else float("inf")
    return w, l, pf


def main():
    syms = sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob("data/raw/*/H1.parquet"))
    data = {s: enrich(s) for s in syms}  # H1, 20/50

    L = ["# Rescue Plan — Phase 3b: SMA Crossover Root-Cause Diagnosis\n"]
    L.append(f"**Data:** {len(syms)} symbols × {SAMPLE:,} H1 bars. Exits SL={SL_MULT}×/TP={TP_MULT}×ATR, "
             f"ordered, horizon={HORIZON}. SMA is a TREND strategy.\n")

    # ── T1 premise ──
    L.append("## T1 — Trend-continuation premise test\n")
    L.append(f"Forward move over {FWD} bars (ATR units) after each SMA20/50 cross, pooled. "
             "Edge exists only if cross-up move > 0 and cross-down move < 0.\n")
    up_mv = []; dn_mv = []
    for s in syms:
        d = data[s]; close = d["close"].values; atr = d["atr_14"].values
        sig = sma_signals(d, use_rsi=False, use_atr=False)  # raw crosses for premise
        n = len(close); fwd = np.full(n, np.nan); fwd[:n - FWD] = close[FWD:] - close[:n - FWD]
        fa = fwd / atr
        up_mv.append(fa[(sig == 1) & np.isfinite(fa)])
        dn_mv.append(fa[(sig == -1) & np.isfinite(fa)])
    um = np.concatenate(up_mv); dm = np.concatenate(dn_mv)
    L.append("| Cross | n | Mean fwd-move (ATR) | % in trend dir | Edge? |")
    L.append("|---|---:|---:|---:|:--:|")
    L.append(f"| Bullish (expect +) | {len(um):,} | {um.mean():+.3f} | {100*np.mean(um>0):.0f}% | "
             f"{'✅' if um.mean() > 0.02 else '❌'} |")
    L.append(f"| Bearish (expect −) | {len(dm):,} | {dm.mean():+.3f} | {100*np.mean(dm<0):.0f}% | "
             f"{'✅' if dm.mean() < -0.02 else '❌'} |")

    # ── T2 regime ──
    L.append("\n## T2 — Regime split (ADX)\n")
    L.append("| Regime | Trades | Wins | Losses | **R-PF** |")
    L.append("|---|---:|---:|---:|---:|")
    for label, lo, hi in [("RANGING (ADX<20)", 0, 20), ("TRANSITION (20–25)", 20, 25), ("TRENDING (ADX>25)", 25, 999)]:
        tw = tl = 0
        for s in syms:
            adx = data[s]["adx"].values
            w, l, _ = simulate(data[s], sma_signals(data[s]), mask=(adx >= lo) & (adx < hi))
            tw += w; tl += l
        pf = (tw * TP_MULT) / (tl * SL_MULT) if tl else float("inf")
        L.append(f"| {label} | {tw+tl} | {tw} | {tl} | **{pf:.2f}** |")

    # ── T3 param sweep (incl. M15) ──
    L.append("\n## T3 — Parameter & timeframe sweep: any config with PF>1?\n")
    L.append("| Config | Trades | Win% | **R-PF** |")
    L.append("|---|---:|---:|---:|")
    sweeps = [("H1 10/30", "H1", 10, 30), ("H1 20/50 (CURRENT)", "H1", 20, 50),
              ("H1 50/100", "H1", 50, 100), ("H1 50/200", "H1", 50, 200),
              ("M15 20/50", "M15", 20, 50), ("M15 50/200", "M15", 50, 200)]
    for name, tf, fa, sl in sweeps:
        tw = tl = 0
        ok = True
        for s in syms:
            p = f"data/raw/{s}/{tf}.parquet"
            if not os.path.exists(p):
                ok = False; break
            d = enrich(s, tf, fa, sl)
            w, l, _ = simulate(d, sma_signals(d, fast=fa, slow=sl))
            tw += w; tl += l
        if not ok:
            L.append(f"| {name} | — missing — | | |"); continue
        dec = tw + tl; wr = 100 * tw / dec if dec else 0
        pf = (tw * TP_MULT) / (tl * SL_MULT) if tl else float("inf")
        L.append(f"| {name} | {dec} | {wr:.0f}% | **{pf:.2f}** |")

    # ── T4 walk-forward ──
    L.append("\n## T4 — Walk-forward (H1 20/50): stable?\n")
    L.append("| Block | Trades | Win% | **R-PF** |")
    L.append("|---|---:|---:|---:|")
    for b in range(3):
        tw = tl = 0
        for s in syms:
            d = data[s]; n = len(d)
            seg = d.iloc[b * n // 3:(b + 1) * n // 3].reset_index(drop=True)
            w, l, _ = simulate(seg, sma_signals(seg)); tw += w; tl += l
        dec = tw + tl; wr = 100 * tw / dec if dec else 0
        pf = (tw * TP_MULT) / (tl * SL_MULT) if tl else float("inf")
        L.append(f"| block {b+1} | {dec} | {wr:.0f}% | **{pf:.2f}** |")

    L.append("\n## Verdict guidance\n")
    L.append("- T1: SMA is trend-following, so unlike RSI the premise *should* hold if momentum "
             "exists. If cross-up move ≈ 0, the lag has eaten the move (signal too late).")
    L.append("- T3: if any period/timeframe (esp. M15, which rescued MACD) clears PF>1, SMA is "
             "fixable by reconfiguration rather than retirement.")
    L.append("- If no config/regime/block clears PF>1, retire like RSI/ml_direct and let MACD-M15 "
             "carry the trend edge alone.")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"Report written: {OUT}")


if __name__ == "__main__":
    main()
