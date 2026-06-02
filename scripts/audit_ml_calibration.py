"""
ML Confidence-Calibration Audit  (Rescue Plan — Phase 1c, READ-ONLY)
====================================================================
Directly tests the freeze-doc claim: "the ML model is not differentiating
winning from losing setups at the 0.55 threshold."

Method:
  For each symbol, load the trained model, run it over a recent held-out
  slice, take the bars where it predicts BUY/SELL, and bin them by the
  model's CONFIDENCE (max class probability). For each bin we compute the
  REAL trade outcome (TP=3*ATR, SL=2*ATR, ordered first-touch) and the real
  win rate. A well-calibrated model shows win% RISING with confidence.
  A flat curve proves confidence is meaningless.

READ-ONLY: loads models + data/raw, writes a markdown report. No live state.

Caveat: the recent slice overlaps the model's own training test window, so
this is the OPTIMISTIC case. If calibration is poor even here, it is
definitively poor out-of-sample.

Run with project venv:
    venv/Scripts/python.exe scripts/audit_ml_calibration.py
"""
import sys
import os
import glob
import pickle
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from features.ml.feature_engine import build_features
from features.technical.indicators import add_atr

OUT = "docs/research/rescue_phase1c_ml_calibration.md"
MODEL_DIR = "models/market_learner"
EVAL_BARS = 8000        # recent bars per symbol to evaluate
TP_MULT, SL_MULT = 3.0, 2.0
EVAL_HORIZON = 48
CONF_BINS = [(0.40, 0.50), (0.50, 0.55), (0.55, 0.60), (0.60, 0.70), (0.70, 1.01)]
# LightGBM classes: 0=SELL, 1=NO_TRADE, 2=BUY
DIR = {0: -1, 2: 1}


def real_outcome(direction, high, low, close, atr, i, horizon):
    entry, a = close[i], atr[i]
    if not np.isfinite(a) or a <= 0:
        return None
    if direction == 1:
        tp, sl = entry + TP_MULT * a, entry - SL_MULT * a
        for j in range(i + 1, min(i + 1 + horizon, len(close))):
            if low[j] <= sl:
                return "LOSS"
            if high[j] >= tp:
                return "WIN"
    else:
        tp, sl = entry - TP_MULT * a, entry + SL_MULT * a
        for j in range(i + 1, min(i + 1 + horizon, len(close))):
            if high[j] >= sl:
                return "LOSS"
            if low[j] <= tp:
                return "WIN"
    return "TIMEOUT"


def audit_symbol(sym):
    mp = f"{MODEL_DIR}/{sym}_model.pkl"
    if not os.path.exists(mp):
        return None
    d = pickle.load(open(mp, "rb"))
    model, feat_cols = d["model"], d["meta"]["feature_cols"]

    df = pd.read_parquet(f"data/raw/{sym}/H1.parquet").sort_values("time").reset_index(drop=True)
    feat = build_features(df.copy(), dropna=False)
    feat = add_atr(feat, 14) if "atr_14" not in feat.columns else feat
    # align to feature columns the model expects
    missing = [c for c in feat_cols if c not in feat.columns]
    if missing:
        return {"sym": sym, "error": f"missing {len(missing)} features e.g. {missing[:3]}"}

    n = len(feat)
    lo_idx = max(0, n - EVAL_BARS)
    hi_idx = n - EVAL_HORIZON  # leave room to resolve trades
    sl = feat.iloc[lo_idx:hi_idx].copy()
    valid = sl[feat_cols].notna().all(axis=1)
    sl = sl[valid]
    if len(sl) < 100:
        return {"sym": sym, "error": "too few valid rows"}

    X = sl[feat_cols].values
    proba = model.predict(X)
    pred = proba.argmax(axis=1)
    conf = proba.max(axis=1)

    high = feat["high"].values.astype(float)
    low = feat["low"].values.astype(float)
    close = feat["close"].values.astype(float)
    atr = feat["atr_14"].values.astype(float)
    orig_idx = sl.index.values

    # bin -> outcomes (only BUY/SELL predictions)
    bins = {b: {"WIN": 0, "LOSS": 0, "TIMEOUT": 0, "n": 0} for b in CONF_BINS}
    for k in range(len(sl)):
        c = pred[k]
        if c == 1:  # NO_TRADE
            continue
        direction = DIR[c]
        cf = conf[k]
        b = next((bb for bb in CONF_BINS if bb[0] <= cf < bb[1]), None)
        if b is None:
            continue
        o = real_outcome(direction, high, low, close, atr, orig_idx[k], EVAL_HORIZON)
        if o is None:
            continue
        bins[b][o] += 1
        bins[b]["n"] += 1
    return {"sym": sym, "bins": bins}


def main():
    syms = [os.path.basename(p).replace("_model.pkl", "")
            for p in sorted(glob.glob(f"{MODEL_DIR}/*_model.pkl"))]
    results = [audit_symbol(s) for s in syms]

    L = ["# Rescue Plan — Phase 1c: ML Confidence-Calibration Audit\n"]
    L.append(f"**Models:** {MODEL_DIR}/*.pkl (trained 2026-03-26).")
    L.append(f"**Eval:** last {EVAL_BARS:,} bars/symbol, real exits TP={TP_MULT}×/SL={SL_MULT}×ATR, "
             f"ordered, horizon={EVAL_HORIZON}.")
    L.append("**Question:** does real win% RISE with model confidence? If flat → confidence is noise.\n")

    # aggregate across symbols
    agg = {b: {"WIN": 0, "LOSS": 0, "TIMEOUT": 0, "n": 0} for b in CONF_BINS}
    for r in results:
        if not r or "bins" not in r:
            L.append(f"- {r['sym'] if r else '?'}: SKIPPED ({r.get('error') if r else 'no model'})")
            continue
        for b in CONF_BINS:
            for k in ("WIN", "LOSS", "TIMEOUT", "n"):
                agg[b][k] += r["bins"][b][k]

    L.append("\n## Aggregate (all symbols) — confidence bin vs real win rate\n")
    L.append("| Confidence bin | Signals | Real WIN | Real LOSS | Timeout | **Real win% (decided)** |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for b in CONF_BINS:
        s = agg[b]
        dec = s["WIN"] + s["LOSS"]
        wr = f"{100*s['WIN']/dec:.0f}%" if dec else "—"
        L.append(f"| {b[0]:.2f}–{b[1]:.2f} | {s['n']:,} | {s['WIN']:,} | {s['LOSS']:,} | {s['TIMEOUT']:,} | **{wr}** |")

    # per-symbol compact
    L.append("\n## Per-symbol real win% by confidence bin\n")
    header = "| Symbol | " + " | ".join(f"{b[0]:.2f}–{b[1]:.2f}" for b in CONF_BINS) + " |"
    L.append(header)
    L.append("|" + "---|" * (len(CONF_BINS) + 1))
    for r in results:
        if not r or "bins" not in r:
            continue
        cells = []
        for b in CONF_BINS:
            s = r["bins"][b]
            dec = s["WIN"] + s["LOSS"]
            cells.append(f"{100*s['WIN']/dec:.0f}% (n={s['n']})" if dec else "—")
        L.append(f"| {r['sym']} | " + " | ".join(cells) + " |")

    L.append("\n## How to read\n")
    L.append("- If real win% is **roughly flat** across bins (e.g. ~70% at 0.50 and ~70% at 0.70), "
             "the model's confidence carries **no extra information** — raising the threshold "
             "filters quantity but not quality. This confirms the freeze-doc finding.")
    L.append("- If win% **rises** with confidence, confidence is meaningful and the lever is to "
             "trade only high-confidence bins.")
    L.append("- Either way: **probability calibration** (isotonic/Platt on a validation set) plus "
             "relabeling with realistic exits (Phase 1b) is the fix. Calibration makes the 0.55 "
             "threshold mean a true 55%, so it can be tuned to balance trade frequency vs quality.")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"Report written: {OUT}")


if __name__ == "__main__":
    main()
