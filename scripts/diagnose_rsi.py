"""
RSI Reversal — Root-Cause Diagnosis (Rescue Phase 3a, READ-ONLY)
================================================================
Phase 1e/1f baseline: rsi_reversal R-PF 0.89 (H1) / 0.94 (M15) — no edge.
This asks WHY, with the same rigor used on ml_direct, so we can decide
fix-vs-retire on evidence:

  T1 PREMISE TEST. The strategy bets on mean-reversion: oversold (RSI<30) ->
     price bounces UP, overbought (RSI>70) -> price falls. Measure the actual
     forward move (in ATR units) after every extreme, pooled across symbols.
     If reversion is real, oversold fwd-move > 0 and overbought fwd-move < 0,
     beating the all-bars baseline. If ~0 or wrong sign, the premise is dead.

  T2 REGIME SPLIT. Mean-reversion should work in RANGING markets and fail in
     TRENDING ones. Split RSI signals by ADX (trend strength) and compute R-PF
     in each regime. If it wins when ranging, a regime filter could rescue it.

  T3 PARAMETER SWEEP. Try oversold/overbought thresholds (20/80, 25/75, 30/70)
     and the 2-bar/price confirmations on/off. Is there ANY config with PF>1?

  T4 WALK-FORWARD (luck control). PF across 3 sequential time blocks — is any
     edge stable or a lucky window?

Real RSI exits: SL=2.0xATR, TP=3.0xATR (rsi_reversal v1.1 defaults).
READ-ONLY. Run: venv/Scripts/python.exe scripts/diagnose_rsi.py
"""
import sys
import os
import glob
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from features.technical.indicators import add_rsi, add_atr

OUT = "docs/research/rescue_phase3a_rsi_diagnosis.md"
SL_MULT, TP_MULT = 2.0, 3.0
ATR_THR = 1.2
HORIZON = 100
FWD = 6
SAMPLE = 60000


def wilder_adx(df, n=14):
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    pc = np.roll(c, 1); ph = np.roll(h, 1); pl = np.roll(l, 1)
    tr = np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])
    up = h - ph; dn = pl - l
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr[0] = plus_dm[0] = minus_dm[0] = 0.0
    a = 1.0 / n
    s_tr = pd.Series(tr).ewm(alpha=a, adjust=False).mean().values
    s_p = pd.Series(plus_dm).ewm(alpha=a, adjust=False).mean().values
    s_m = pd.Series(minus_dm).ewm(alpha=a, adjust=False).mean().values
    pdi = 100 * s_p / np.where(s_tr == 0, np.nan, s_tr)
    mdi = 100 * s_m / np.where(s_tr == 0, np.nan, s_tr)
    dx = 100 * np.abs(pdi - mdi) / np.where((pdi + mdi) == 0, np.nan, pdi + mdi)
    adx = pd.Series(dx).ewm(alpha=a, adjust=False).mean().values
    return adx


def enrich(sym, tf="H1"):
    df = pd.read_parquet(f"data/raw/{sym}/{tf}.parquet").sort_values("time").tail(SAMPLE).reset_index(drop=True)
    df = add_rsi(df, 14); df = add_atr(df, 14)
    df["avg_atr20"] = df["atr_14"].rolling(20).mean()
    df["adx"] = wilder_adx(df)
    return df.dropna(subset=["rsi_14", "atr_14", "avg_atr20", "adx"]).reset_index(drop=True)


def rsi_signals(d, os_=30.0, ob=70.0, use_2bar=True, use_price=True, use_atr=True):
    price = d["close"].values; rsi = d["rsi_14"].values
    atr = d["atr_14"].values; avg = d["avg_atr20"].values
    rp, rp2, pc = np.roll(rsi, 1), np.roll(rsi, 2), np.roll(price, 1)
    ok = (atr >= ATR_THR * avg) if use_atr else np.ones(len(d), bool)
    if use_2bar:
        buy = (rsi < os_) & (rsi > rp) & (rp > rp2)
        sell = (rsi > ob) & (rsi < rp) & (rp < rp2)
    else:
        buy = (rsi < os_) & (rsi > rp)
        sell = (rsi > ob) & (rsi < rp)
    buy, sell = ok & buy, ok & sell
    if use_price:
        buy = buy & (price >= pc); sell = sell & (price <= pc)
    o = np.zeros(len(d), np.int8); o[buy] = 1; o[sell] = -1; o[:2] = 0
    return o


def simulate(d, dirs, mask=None):
    high = d["high"].values; low = d["low"].values; close = d["close"].values; atr = d["atr_14"].values
    n = len(close); w = l = 0; busy = -1
    idxs = np.where(dirs != 0)[0]
    for i in idxs:
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
    data = {s: enrich(s) for s in syms}

    L = ["# Rescue Plan — Phase 3a: RSI Reversal Root-Cause Diagnosis\n"]
    L.append(f"**Data:** {len(syms)} symbols × {SAMPLE:,} H1 bars. RSI exits SL={SL_MULT}×/TP={TP_MULT}×ATR, "
             f"ordered, horizon={HORIZON}.\n")

    # ── T1 premise: does reversion happen? ──
    L.append("## T1 — Mean-reversion premise test\n")
    L.append("Forward move over 6 bars (in ATR units) after each RSI extreme, pooled. "
             "Reversion is real only if oversold fwd-move > 0 and overbought fwd-move < 0.\n")
    os_moves = []; ob_moves = []; base_abs = []
    for s in syms:
        d = data[s]; close = d["close"].values; atr = d["atr_14"].values; rsi = d["rsi_14"].values
        n = len(close); fwd = np.full(n, np.nan)
        fwd[:n - FWD] = (close[FWD:] - close[:n - FWD])
        fwd_atr = fwd / atr
        os_moves.append(fwd_atr[(rsi < 30) & np.isfinite(fwd_atr)])
        ob_moves.append(fwd_atr[(rsi > 70) & np.isfinite(fwd_atr)])
        base_abs.append(np.abs(fwd_atr[np.isfinite(fwd_atr)]))
    osm = np.concatenate(os_moves); obm = np.concatenate(ob_moves)
    L.append("| Condition | n | Mean fwd-move (ATR) | % in reversion dir | Reversion edge? |")
    L.append("|---|---:|---:|---:|:--:|")
    os_pct = 100 * np.mean(osm > 0); ob_pct = 100 * np.mean(obm < 0)
    L.append(f"| Oversold RSI<30 (expect +) | {len(osm):,} | {osm.mean():+.3f} | {os_pct:.0f}% | "
             f"{'✅' if osm.mean() > 0.02 else '❌'} |")
    L.append(f"| Overbought RSI>70 (expect −) | {len(obm):,} | {obm.mean():+.3f} | {ob_pct:.0f}% | "
             f"{'✅' if obm.mean() < -0.02 else '❌'} |")
    L.append(f"\nInterpretation: a mean |fwd-move| baseline is ~{np.concatenate(base_abs).mean():.3f} ATR; "
             "reversion 'edge' must be a clear non-zero move in the bounce direction.\n")

    # ── T2 regime split ──
    L.append("## T2 — Regime split (ADX): does RSI win when ranging?\n")
    L.append("| Regime | Trades | Wins | Losses | **R-PF** |")
    L.append("|---|---:|---:|---:|---:|")
    for label, lo, hi in [("RANGING (ADX<20)", 0, 20), ("TRANSITION (20–25)", 20, 25), ("TRENDING (ADX>25)", 25, 999)]:
        tw = tl = 0
        for s in syms:
            d = data[s]; adx = d["adx"].values
            mask = (adx >= lo) & (adx < hi)
            w, l, _ = simulate(d, rsi_signals(d), mask=mask)
            tw += w; tl += l
        pf = (tw * TP_MULT) / (tl * SL_MULT) if tl else float("inf")
        L.append(f"| {label} | {tw + tl} | {tw} | {tl} | **{pf:.2f}** |")

    # ── T3 parameter sweep ──
    L.append("\n## T3 — Parameter sweep: is ANY config profitable?\n")
    L.append("| Config | Trades | Win% | **R-PF** |")
    L.append("|---|---:|---:|---:|")
    configs = [
        ("CURRENT 30/70, 2bar, price", dict()),
        ("25/75, 2bar, price", dict(os_=25, ob=75)),
        ("20/80, 2bar, price", dict(os_=20, ob=80)),
        ("30/70, no 2bar", dict(use_2bar=False)),
        ("30/70, no price confirm", dict(use_price=False)),
        ("20/80, no filters (raw extremes)", dict(os_=20, ob=80, use_2bar=False, use_price=False, use_atr=False)),
    ]
    for name, kw in configs:
        tw = tl = 0
        for s in syms:
            w, l, _ = simulate(data[s], rsi_signals(data[s], **kw))
            tw += w; tl += l
        dec = tw + tl
        wr = 100 * tw / dec if dec else 0
        pf = (tw * TP_MULT) / (tl * SL_MULT) if tl else float("inf")
        L.append(f"| {name} | {dec} | {wr:.0f}% | **{pf:.2f}** |")

    # ── T4 walk-forward (luck control) ──
    L.append("\n## T4 — Walk-forward (current config): is any edge stable?\n")
    L.append("| Block | Trades | Win% | **R-PF** |")
    L.append("|---|---:|---:|---:|")
    for b in range(3):
        tw = tl = 0
        for s in syms:
            d = data[s]; n = len(d)
            seg = d.iloc[b * n // 3:(b + 1) * n // 3].reset_index(drop=True)
            seg = seg.assign()  # keep
            w, l, _ = simulate(seg, rsi_signals(seg))
            tw += w; tl += l
        dec = tw + tl; wr = 100 * tw / dec if dec else 0
        pf = (tw * TP_MULT) / (tl * SL_MULT) if tl else float("inf")
        L.append(f"| block {b+1} | {dec} | {wr:.0f}% | **{pf:.2f}** |")

    L.append("\n## Verdict guidance\n")
    L.append("- **T1** is the make-or-break: if RSI extremes do not produce a reversion move, "
             "the strategy's premise is invalid and no parameter tuning will save it.")
    L.append("- **T2**: if PF > 1 in RANGING only, a regime filter (trade RSI only when ADX<20) "
             "is a candidate rescue — otherwise retire.")
    L.append("- **T3/T4**: if no config clears PF>1 and no block is positive, RSI reversal has no "
             "recoverable edge on this data → retire like ml_direct.")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"Report written: {OUT}")


if __name__ == "__main__":
    main()
