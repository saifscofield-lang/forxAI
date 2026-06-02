"""
Volatility-Scaled Position Sizing — build & verify (Rescue Phase 5a, READ-ONLY).

The RiskManager already sizes each trade to a constant 1% $-risk (lot ~ 1/ATR),
so per-trade risk is volatility-normalised in absolute terms. The INCREMENTAL
idea is a REGIME overlay: scale the risk FRACTION down when volatility is
elevated vs its own norm (atr_ratio = ATR / mean(ATR,100)). High-vol regimes are
where gaps/slippage and loss clusters cause big drawdowns; down-sizing there
should cut the tail the owner is worried about.

We verify on the real MACD-M15 trade stream:
  T-A  Outcome (win% / R-PF) by volatility tercile — are high-vol trades worse?
  T-B  Equity-curve comparison (fixed 1% vs vol-scaled): total return, MAX
       DRAWDOWN (the key metric for "big loss"), return/maxDD, worst single
       trade, per-trade P&L std. Per walk-forward block too (robustness).

Sizing rule (vol-scaled): f = base * clip(target_ratio / atr_ratio, floor, cap)
  - defensive variant: cap=1.0 (never up-size; pure protection)
  - symmetric variant: cap=1.5 (vol targeting both directions)

Outcomes from the ordered triple-barrier (TP=3.5x/SL=2.5x ATR), R:R = 1.4.
Note: clean sim has NO gaps/slippage, so it UNDERstates the high-vol benefit;
treat drawdown reduction here as a conservative lower bound.

Run: venv/Scripts/python.exe scripts/build_vol_scaled_sizing.py
"""
import sys
import os
import glob
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from features.technical.indicators import add_atr, add_ema, add_macd

OUT = "docs/research/rescue_phase5a_vol_scaled_sizing.md"
TP_MULT, SL_MULT = 3.5, 2.5
RR = TP_MULT / SL_MULT
ATR_THR = 1.2
HORIZON = 100
BARS_TAIL = 90000
BASE_F = 0.01
TARGET_RATIO = 1.0
FLOOR, CAP_DEF, CAP_SYM = 0.33, 1.0, 1.5


def enrich(sym):
    df = pd.read_parquet(f"data/raw/{sym}/M15.parquet").sort_values("time").tail(BARS_TAIL).reset_index(drop=True)
    df = add_atr(df, 14); df = add_ema(df, 50); df = add_ema(df, 200); df = add_macd(df)
    df["avg_atr20"] = df["atr_14"].rolling(20).mean()
    df["atr_ratio"] = df["atr_14"] / df["atr_14"].rolling(100).mean()
    return df.dropna(subset=["atr_14", "ema_50", "ema_200", "macd_line", "macd_signal",
                             "macd_hist", "avg_atr20", "atr_ratio"]).reset_index(drop=True)


def macd_signals(d):
    price = d["close"].values; macd = d["macd_line"].values; sig = d["macd_signal"].values
    hist = d["macd_hist"].values; ema50 = d["ema_50"].values; ema200 = d["ema_200"].values
    atr = d["atr_14"].values; avg = d["avg_atr20"].values
    pm, ps, ph = np.roll(macd, 1), np.roll(sig, 1), np.roll(hist, 1)
    ok = atr >= ATR_THR * avg
    buy = ok & (pm <= ps) & (macd > sig) & (price > ema50) & (ema50 > ema200) & (hist > ph)
    sell = ok & (pm >= ps) & (macd < sig) & (price < ema50) & (ema50 < ema200) & (hist < ph)
    o = np.zeros(len(d), np.int8); o[buy] = 1; o[sell] = -1; o[:1] = 0
    return o


def gen_trades():
    syms = sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob("data/raw/*/M15.parquet"))
    rows = []
    for sym in syms:
        d = enrich(sym); sig = macd_signals(d)
        high = d["high"].values; low = d["low"].values; close = d["close"].values
        atr = d["atr_14"].values; ar = d["atr_ratio"].values; t = d["time"].values
        n = len(close); busy = -1
        for i in np.where(sig != 0)[0]:
            if i <= busy:
                continue
            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                continue
            e = close[i]; dn = sig[i]
            tp, sl = (e + TP_MULT*a, e - SL_MULT*a) if dn == 1 else (e - TP_MULT*a, e + SL_MULT*a)
            out = None
            for j in range(i+1, min(i+1+HORIZON, n)):
                if dn == 1:
                    if low[j] <= sl: out = 0; break
                    if high[j] >= tp: out = 1; break
                else:
                    if high[j] >= sl: out = 0; break
                    if low[j] <= tp: out = 1; break
                busy = j
            if out is not None:
                rows.append((t[i], out, ar[i]))
    df = pd.DataFrame(rows, columns=["time", "win", "atr_ratio"]).sort_values("time").reset_index(drop=True)
    return df


def equity_curve(wins, mults):
    eq = 1.0; peak = 1.0; maxdd = 0.0; rets = []; worst = 0.0
    for w, m in zip(wins, mults):
        f = BASE_F * m
        risk = f * eq
        change = risk * RR if w == 1 else -risk
        rets.append(change / eq)
        if change < worst:
            worst = change / eq
        eq += change
        peak = max(peak, eq)
        dd = (peak - eq) / peak
        maxdd = max(maxdd, dd)
    return dict(ret=eq - 1.0, maxdd=maxdd, calmar=(eq - 1.0) / maxdd if maxdd > 0 else float("inf"),
                worst=worst, std=float(np.std(rets)))


def vmult(ar, cap):
    return np.clip(TARGET_RATIO / ar, FLOOR, cap)


def main():
    print("Generating MACD-M15 trades...", flush=True)
    tr = gen_trades()
    wins = tr["win"].values; ar = tr["atr_ratio"].values
    print(f"{len(tr)} trades, base win-rate {wins.mean():.1%}", flush=True)

    L = ["# Rescue Plan — Phase 5a: Volatility-Scaled Sizing — Build & Verify\n"]
    L.append(f"**Trades:** {len(tr)} MACD-M15 (real ordered TP/SL, R:R={RR:.2f}). "
             f"Sizing fraction scaled by atr_ratio = ATR/mean(ATR,100).\n")

    # T-A terciles
    L.append("## T-A — Outcome by volatility tercile (are high-vol trades worse?)\n")
    q1, q2 = np.quantile(ar, [1/3, 2/3])
    L.append("| Vol tercile | Trades | Win% | R-PF |")
    L.append("|---|---:|---:|---:|")
    for name, m in [("LOW vol (calm)", ar <= q1), ("MID vol", (ar > q1) & (ar <= q2)), ("HIGH vol", ar > q2)]:
        w = int(wins[m].sum()); l = int(m.sum() - w)
        pf = (w*TP_MULT)/(l*SL_MULT) if l else float("inf")
        wr = 100*w/m.sum() if m.sum() else 0
        L.append(f"| {name} | {int(m.sum())} | {wr:.0f}% | {pf:.2f} |")
    L.append(f"\n(atr_ratio tercile cuts ≈ {q1:.2f} / {q2:.2f})\n")

    # T-B equity curves
    fixed = equity_curve(wins, np.ones(len(tr)))
    defv = equity_curve(wins, vmult(ar, CAP_DEF))
    symv = equity_curve(wins, vmult(ar, CAP_SYM))
    L.append("## T-B — Equity-curve comparison (fixed 1% vs vol-scaled)\n")
    L.append("| Scheme | Total return | **Max drawdown** | Return/MaxDD | Worst trade | P&L std |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for name, r in [("Fixed 1%", fixed), ("Vol-scaled (defensive, cap 1.0)", defv),
                    ("Vol-scaled (symmetric, cap 1.5)", symv)]:
        L.append(f"| {name} | {r['ret']*100:+.1f}% | **{r['maxdd']*100:.1f}%** | "
                 f"{r['calmar']:.2f} | {r['worst']*100:.2f}% | {r['std']*100:.3f}% |")

    # robustness: maxDD per time block (defensive vs fixed)
    L.append("\n## Robustness — max drawdown per time block (fixed vs defensive)\n")
    L.append("| Block | Fixed MaxDD | Vol-scaled MaxDD |")
    L.append("|---|---:|---:|")
    nB = 3
    for b in range(nB):
        seg = tr.iloc[b*len(tr)//nB:(b+1)*len(tr)//nB]
        fw = seg["win"].values; fa = seg["atr_ratio"].values
        f0 = equity_curve(fw, np.ones(len(seg)))
        f1 = equity_curve(fw, vmult(fa, CAP_DEF))
        L.append(f"| {b+1} | {f0['maxdd']*100:.1f}% | {f1['maxdd']*100:.1f}% |")

    # acceptance (defensive variant — the one matching the owner's goal)
    dd_cut = (fixed["maxdd"] - defv["maxdd"]) / fixed["maxdd"] if fixed["maxdd"] > 0 else 0
    ret_keep = defv["ret"] / fixed["ret"] if fixed["ret"] != 0 else 0
    worst_cut = (abs(fixed["worst"]) - abs(defv["worst"])) / abs(fixed["worst"]) if fixed["worst"] != 0 else 0
    A1 = defv["maxdd"] < fixed["maxdd"]
    A2 = defv["calmar"] >= fixed["calmar"]
    A3 = ret_keep >= 0.80
    A4 = abs(defv["worst"]) < abs(fixed["worst"])
    ship = A1 and A2 and A3 and A4

    L.append("\n## Acceptance (defensive variant — matches the 'avoid big losses' goal)\n")
    L.append(f"- A1 max drawdown reduced: {fixed['maxdd']*100:.1f}% → {defv['maxdd']*100:.1f}% "
             f"({dd_cut*100:+.0f}%) → {'PASS' if A1 else 'FAIL'}")
    L.append(f"- A2 return/MaxDD not worse: {fixed['calmar']:.2f} → {defv['calmar']:.2f} → {'PASS' if A2 else 'FAIL'}")
    L.append(f"- A3 retains ≥80% of return: {ret_keep*100:.0f}% → {'PASS' if A3 else 'FAIL'}")
    L.append(f"- A4 worst single trade smaller: {fixed['worst']*100:.2f}% → {defv['worst']*100:.2f}% "
             f"({worst_cut*100:+.0f}%) → {'PASS' if A4 else 'FAIL'}")
    L.append(f"\n## VERDICT: {'SHIP vol-scaled (defensive) sizing' if ship else 'MIXED — see notes'}\n")
    L.append("Caveat: clean sim excludes gaps/slippage, so the real high-vol protection is LARGER "
             "than shown — this drawdown reduction is a conservative lower bound. If shipped: scale "
             "max_risk_per_trade by clip(1/atr_ratio, 0.33, 1.0) in RiskManager.calculate_position_size.")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"fixed maxDD {fixed['maxdd']*100:.1f}% -> vol-scaled {defv['maxdd']*100:.1f}% | "
          f"ret keep {ret_keep*100:.0f}% | SHIP={ship}")
    print(f"Report written: {OUT}")


if __name__ == "__main__":
    main()
