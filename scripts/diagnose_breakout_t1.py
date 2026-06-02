"""
Breakout Strategy — T1 Premise Diagnosis (Rescue Phase 4a, READ-ONLY)
=====================================================================
Before building a regime-gated volatility breakout strategy, test its core
premise with the same rigor used on RSI/SMA: does a channel breakout actually
predict trend CONTINUATION?

A breakout (Donchian/Turtle style): price closes above the highest high of the
prior N bars (upside) or below the lowest low (downside). If the premise holds,
the forward move (in ATR units) after an upside break is > 0 and after a
downside break < 0, clearly above noise.

Key addition learned from Phase 3: split by REGIME (ADX). Our design hypothesis
is that breakouts work in TRENDING markets and fail (false breaks) in RANGING
ones. T1 must confirm BOTH the raw premise AND that the regime gate sharpens it
— otherwise the regime gate (the strongest lever we found) is not justified here.

Pooled across symbols (forward move in ATR units is scale-invariant).
Fresh breakouts only (the crossing bar), N in {20, 55}, horizon 12 bars.

READ-ONLY. Run: venv/Scripts/python.exe scripts/diagnose_breakout_t1.py
"""
import sys
import os
import glob
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from features.technical.indicators import add_atr
from features.regime_detector import compute_adx

OUT = "docs/research/rescue_phase4a_breakout_t1.md"
SAMPLE = 60000
FWD = 12
CHANNELS = [20, 55]


def enrich(sym):
    df = pd.read_parquet(f"data/raw/{sym}/H1.parquet").sort_values("time").tail(SAMPLE).reset_index(drop=True)
    df = add_atr(df, 14)
    df = compute_adx(df, period=14)
    return df.dropna(subset=["atr_14", "adx_14"]).reset_index(drop=True)


def fresh_breakouts(d, n):
    """Return int8: 1=fresh upside break, -1=fresh downside break, 0=none."""
    high = d["high"].values; low = d["low"].values; close = d["close"].values
    prior_high = pd.Series(high).rolling(n).max().shift(1).values  # max of prior n highs
    prior_low = pd.Series(low).rolling(n).min().shift(1).values
    up = close > prior_high
    dn = close < prior_low
    pup = np.roll(up, 1); pup[0] = False
    pdn = np.roll(dn, 1); pdn[0] = False
    fresh_up = up & ~pup
    fresh_dn = dn & ~pdn
    o = np.zeros(len(d), np.int8); o[fresh_up] = 1; o[fresh_dn] = -1
    o[:n] = 0
    return o


def fwd_moves(d):
    close = d["close"].values; atr = d["atr_14"].values
    n = len(close); fwd = np.full(n, np.nan)
    fwd[:n - FWD] = close[FWD:] - close[:n - FWD]
    return fwd / atr


def main():
    syms = sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob("data/raw/*/H1.parquet"))
    data = {s: enrich(s) for s in syms}

    L = ["# Rescue Plan — Phase 4a: Breakout T1 Premise Diagnosis\n"]
    L.append(f"**Data:** {len(syms)} symbols × {SAMPLE:,} H1 bars, pooled. Fresh Donchian "
             f"breakouts, forward move over {FWD} bars in ATR units. ADX via project compute_adx.\n")
    L.append("Edge exists only if **upside break fwd-move > 0** and **downside < 0**, clearly "
             "above the noise baseline.\n")

    # baseline
    base = np.concatenate([np.abs(fwd_moves(data[s])[np.isfinite(fwd_moves(data[s]))]) for s in syms])
    L.append(f"Noise baseline: mean |forward move| ≈ **{base.mean():.3f} ATR**.\n")

    for n in CHANNELS:
        L.append(f"## Channel N={n}\n")
        L.append("| Condition | Regime | n | Mean fwd-move (ATR) | % in trend dir | Edge? |")
        L.append("|---|---|---:|---:|---:|:--:|")
        # collect pooled arrays per (side, regime)
        buckets = {}
        for s in syms:
            d = data[s]; fa = fwd_moves(d); sig = fresh_breakouts(d, n); adx = d["adx_14"].values
            fin = np.isfinite(fa) & np.isfinite(adx)
            for side, sv in [("UP", 1), ("DN", -1)]:
                for rname, rmask in [("ALL", np.ones(len(d), bool)),
                                     ("TRENDING ADX≥25", adx >= 25),
                                     ("RANGING ADX<20", adx < 20)]:
                    m = (sig == sv) & fin & rmask
                    buckets.setdefault((side, rname), []).append(fa[m])
        for side, sv in [("UP", 1), ("DN", -1)]:
            for rname in ["ALL", "TRENDING ADX≥25", "RANGING ADX<20"]:
                arr = np.concatenate(buckets[(side, rname)]) if buckets[(side, rname)] else np.array([])
                if len(arr) == 0:
                    L.append(f"| {side} break | {rname} | 0 | — | — | — |"); continue
                mean = arr.mean()
                pct = 100 * (np.mean(arr > 0) if side == "UP" else np.mean(arr < 0))
                if side == "UP":
                    edge = "✅" if mean > 0.05 else ("~" if mean > 0.02 else "❌")
                else:
                    edge = "✅" if mean < -0.05 else ("~" if mean < -0.02 else "❌")
                exp = "+" if side == "UP" else "−"
                L.append(f"| {side} break (expect {exp}) | {rname} | {len(arr):,} | {mean:+.3f} | {pct:.0f}% | {edge} |")

    L.append("\n## How to read / next step\n")
    L.append("- **Make-or-break:** in the TRENDING bucket, upside breaks should show a clearly "
             "positive forward move and downside clearly negative — that is the continuation edge "
             "the strategy will harvest.")
    L.append("- If TRENDING shows edge but ALL/RANGING do not, the regime gate (ADX≥25) is "
             "justified and becomes a core part of the design (as in SMA Phase 3b).")
    L.append("- If even the TRENDING bucket is ≈0, breakouts do not predict continuation on this "
             "data → stop and reconsider (do not proceed to T2–T4), exactly as we would have for "
             "a failed RSI premise.")
    L.append("- Caveat: fwd move ≠ tradable P&L (no SL/TP/spread). T1 only checks the premise; "
             "economics come in T2–T4.")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    # ascii-safe console summary
    print("Breakout T1 premise diagnosis complete.")
    print(f"Report written: {OUT}")


if __name__ == "__main__":
    main()
