"""
Label-Optimism Audit  (Rescue Plan — Phase 1b, READ-ONLY)
=========================================================
Quantifies how OPTIMISTIC the current ML training labels are versus the
realistic, ordered outcome a real trade would have produced.

Background (the flaw):
  market_learner.create_labels() labels bar i as BUY if the future HIGH over
  the next 6 bars rose by >= min_move, SELL if the future LOW fell by
  >= min_move, and on ties picks the LARGER magnitude. It ignores which
  barrier was touched FIRST. So a bar where price first drops (hits a real SL)
  then later rises is still labeled BUY — a trade that would have stopped out.

This audit replays history two ways and measures the gap:

  TEST A — "Realism gap":
    For every bar the CURRENT labeler calls BUY/SELL, simulate the REAL trade
    ml_direct would take (TP = 3.0*ATR, SL = 2.0*ATR), ordered first-touch.
    optimism = share of those labels that actually LOSE or never reach TP.

  TEST B — "Pure ordering flip":
    Using a single symmetric barrier (min_move both sides, 6-bar window),
    compare the magnitude-tiebreak label (current logic) to the ordered
    first-touch label. Reports disagreement on the ambiguous bars where BOTH
    barriers were touched — this isolates the ordering flaw alone.

READ-ONLY: reads data/raw/*.parquet, writes a markdown report. No trading
code or live state touched. Safe during the freeze.

Run with the project venv (needs pyarrow):
    venv/Scripts/python.exe scripts/audit_label_optimism.py
"""
import sys
import os
import glob
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from features.technical.indicators import add_atr

OUT = "docs/research/rescue_phase1b_label_audit.md"

FORWARD_HOURS = 6           # current labeler window
TP_MULT = 3.0               # ml_direct real take-profit (ATR multiples)
SL_MULT = 2.0               # ml_direct real stop-loss
EVAL_HORIZON = 48           # max bars to resolve a real trade (~2 days)
SAMPLE_BARS = 30000         # last N bars per symbol (speed; ~3.4y H1)

MIN_MOVE = {
    "EURUSD": 0.0020, "GBPUSD": 0.0025, "USDJPY": 0.25, "XAUUSD": 8.0,
    "AUDUSD": 0.0020, "USDCAD": 0.0020, "USDCHF": 0.0020,
}


def current_labels(high, low, close, min_move, fwd):
    """Replicate market_learner.create_labels (unordered, magnitude tiebreak)."""
    n = len(close)
    fut_high = np.full(n, np.nan)
    fut_low = np.full(n, np.nan)
    for i in range(n - fwd):
        fut_high[i] = high[i + 1:i + 1 + fwd].max()
        fut_low[i] = low[i + 1:i + 1 + fwd].min()
    up = fut_high - close
    dn = close - fut_low
    buy = up >= min_move
    sell = dn >= min_move
    lab = np.zeros(n, dtype=np.int8)
    lab[buy & ~sell] = 1
    lab[~buy & sell] = -1
    both = buy & sell
    lab[both] = np.where(up[both] >= dn[both], 1, -1)
    lab[n - fwd:] = 0  # no future data
    return lab


def real_outcome(direction, high, low, close, atr, i, horizon, tp_m, sl_m):
    """Ordered first-touch with realistic asymmetric exits. Returns WIN/LOSS/TIMEOUT."""
    entry = close[i]
    a = atr[i]
    if not np.isfinite(a) or a <= 0:
        return None
    if direction == 1:  # long
        tp, sl = entry + tp_m * a, entry - sl_m * a
        for j in range(i + 1, min(i + 1 + horizon, len(close))):
            if low[j] <= sl:
                return "LOSS"
            if high[j] >= tp:
                return "WIN"
    else:  # short
        tp, sl = entry - tp_m * a, entry + sl_m * a
        for j in range(i + 1, min(i + 1 + horizon, len(close))):
            if high[j] >= sl:
                return "LOSS"
            if low[j] <= tp:
                return "WIN"
    return "TIMEOUT"


def ordered_symmetric(high, low, close, min_move, fwd):
    """First-touch label with a symmetric min_move barrier (for TEST B)."""
    n = len(close)
    lab = np.zeros(n, dtype=np.int8)
    both = np.zeros(n, dtype=bool)
    for i in range(n - fwd):
        up_lvl = close[i] + min_move
        dn_lvl = close[i] - min_move
        hit = 0
        touched_up = touched_dn = False
        for j in range(i + 1, i + 1 + fwd):
            uh = high[j] >= up_lvl
            dl = low[j] <= dn_lvl
            touched_up = touched_up or uh
            touched_dn = touched_dn or dl
            if uh and dl:
                hit = 1  # ambiguous within-bar: assume worst-neutral, count as up here
                break
            if uh:
                hit = 1
                break
            if dl:
                hit = -1
                break
        lab[i] = hit
        both[i] = touched_up and touched_dn
    return lab, both


def audit_symbol(sym):
    df = pd.read_parquet(f"data/raw/{sym}/H1.parquet")
    df = df.sort_values("time").tail(SAMPLE_BARS).reset_index(drop=True)
    df = add_atr(df, 14)
    high = df["high"].values.astype(float)
    low = df["low"].values.astype(float)
    close = df["close"].values.astype(float)
    atr = df["atr_14"].values.astype(float)
    mm = MIN_MOVE[sym]

    cur = current_labels(high, low, close, mm, FORWARD_HOURS)

    # TEST A — realism gap on directional labels
    res = {"BUY": {"WIN": 0, "LOSS": 0, "TIMEOUT": 0, "NA": 0},
           "SELL": {"WIN": 0, "LOSS": 0, "TIMEOUT": 0, "NA": 0}}
    for i in np.where(cur != 0)[0]:
        d = cur[i]
        o = real_outcome(d, high, low, close, atr, i, EVAL_HORIZON, TP_MULT, SL_MULT)
        side = "BUY" if d == 1 else "SELL"
        res[side][o or "NA"] += 1

    # TEST B — pure ordering flip on ambiguous bars
    ordsym, both = ordered_symmetric(high, low, close, mm, FORWARD_HOURS)
    amb = both & (cur != 0)
    flips = int(np.sum(amb & (ordsym != cur) & (ordsym != 0)))
    amb_total = int(np.sum(amb))

    n_dir = int(np.sum(cur != 0))
    n_total = len(cur) - FORWARD_HOURS
    return {
        "sym": sym, "n_total": n_total, "n_dir": n_dir,
        "dir_pct": 100 * n_dir / n_total,
        "res": res, "amb_total": amb_total, "flips": flips,
    }


def main():
    syms = [os.path.basename(os.path.dirname(p)) for p in glob.glob("data/raw/*/H1.parquet")]
    rows = [audit_symbol(s) for s in sorted(syms)]

    L = []
    L.append("# Rescue Plan — Phase 1b: Label-Optimism Audit\n")
    L.append(f"**Data:** data/raw/*/H1.parquet, last {SAMPLE_BARS:,} bars/symbol (~3.4y).")
    L.append(f"**Current labeler:** market_learner.create_labels (unordered, {FORWARD_HOURS}-bar window).")
    L.append(f"**Realistic exits:** TP={TP_MULT}×ATR, SL={SL_MULT}×ATR, ordered first-touch, "
             f"horizon={EVAL_HORIZON} bars.\n")

    # TEST A table
    L.append("## TEST A — Realism gap: do the labels survive real ordered exits?\n")
    L.append("For every bar the current labeler calls BUY/SELL, we simulate the real "
             "ml_direct trade (3×/2× ATR, ordered). A 'WIN' actually reached TP before SL.\n")
    L.append("| Symbol | Dir labels | Real WIN | Real LOSS | Timeout | **Real win% (decided)** | **Optimism\\*** |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    agg = {"WIN": 0, "LOSS": 0, "TIMEOUT": 0, "NA": 0, "dir": 0}
    for r in rows:
        w = r["res"]["BUY"]["WIN"] + r["res"]["SELL"]["WIN"]
        l = r["res"]["BUY"]["LOSS"] + r["res"]["SELL"]["LOSS"]
        t = r["res"]["BUY"]["TIMEOUT"] + r["res"]["SELL"]["TIMEOUT"]
        dec = w + l
        wr = f"{100*w/dec:.0f}%" if dec else "—"
        opt = f"{100*(l+t)/(w+l+t):.0f}%" if (w+l+t) else "—"
        L.append(f"| {r['sym']} | {r['n_dir']:,} | {w:,} | {l:,} | {t:,} | **{wr}** | **{opt}** |")
        agg["WIN"] += w; agg["LOSS"] += l; agg["TIMEOUT"] += t; agg["dir"] += r["n_dir"]
    dec = agg["WIN"] + agg["LOSS"]
    wr = f"{100*agg['WIN']/dec:.0f}%" if dec else "—"
    tot = agg["WIN"] + agg["LOSS"] + agg["TIMEOUT"]
    opt = f"{100*(agg['LOSS']+agg['TIMEOUT'])/tot:.0f}%" if tot else "—"
    L.append(f"| **ALL** | {agg['dir']:,} | {agg['WIN']:,} | {agg['LOSS']:,} | {agg['TIMEOUT']:,} | **{wr}** | **{opt}** |")
    L.append("\n\\*Optimism = share of BUY/SELL labels that do NOT reach TP first as a real "
             "trade (LOSS + never-reached). These are training targets the model learns as "
             "'good' but that lose money in reality — the direct cause of meaningless confidence.\n")

    # TEST B table
    L.append("## TEST B — Pure ordering flip (isolates the create_labels bug)\n")
    L.append("On the ambiguous bars where BOTH barriers (±min_move, 6-bar) are touched, "
             "how often does the ordered first-touch label DISAGREE with the current "
             "magnitude-tiebreak label?\n")
    L.append("| Symbol | Ambiguous dir-labels | Flipped by ordering | **Flip%** |")
    L.append("|---|---:|---:|---:|")
    fa = ft = 0
    for r in rows:
        fp = f"{100*r['flips']/r['amb_total']:.0f}%" if r["amb_total"] else "—"
        L.append(f"| {r['sym']} | {r['amb_total']:,} | {r['flips']:,} | **{fp}** |")
        fa += r["amb_total"]; ft += r["flips"]
    L.append(f"| **ALL** | {fa:,} | {ft:,} | **{100*ft/fa:.0f}%** |" if fa else "| **ALL** | 0 | 0 | — |")

    L.append("\n## Conclusion\n")
    L.append("- **TEST A** measures the headline harm: how many 'good' training labels are "
             "actually losing trades under the exits we really use.")
    L.append("- **TEST B** confirms the mechanism: the higher the flip%, the more the "
             "magnitude-tiebreak (ignoring order) corrupts the label vs. a first-touch rule.")
    L.append("- **Fix:** relabel with the ordered triple-barrier already in "
             "`features/ml/label_engine.py` using the SAME 3×/2× ATR exits, then retrain. "
             "This aligns training target with live trading and should restore meaningful "
             "confidence (so we can lower the 0.55 threshold to fire more trades safely).")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"Report written: {OUT}")


if __name__ == "__main__":
    main()
