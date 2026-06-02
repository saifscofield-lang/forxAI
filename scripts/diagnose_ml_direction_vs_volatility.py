"""
ML Diagnosis: Direction vs Volatility predictability (Rescue, READ-ONLY)
=======================================================================
Goal: before rebuilding ml_direct, prove WHY it has no edge so the rebuild
avoids the same mistake.

Hypothesis (from model metrics: top features are atr_*, hour, session_*):
the feature set predicts WHETHER price moves (volatility/tradability) but NOT
WHICH WAY it moves (direction). The strategy trades DIRECTION -> structural
mismatch -> no edge.

Test: train two fresh LightGBM models on the SAME features, time-split OOS:
  A) DIRECTION  — predict sign of the 6-bar forward return (up vs down)
  B) VOLATILITY — predict whether the 6-bar move magnitude exceeds min_move
Report OOS accuracy + AUC for each. If A ~ 0.50 (coin flip) while B > 0.55,
the hypothesis holds: features carry volatility info, not directional info.

Implication if confirmed: do NOT rebuild ml_direct as a direction predictor on
these features. Use ML as a volatility/tradability FILTER on rule-based
directional signals, OR source genuinely directional features.

READ-ONLY. Run: venv/Scripts/python.exe scripts/diagnose_ml_direction_vs_volatility.py
"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from features.ml.feature_engine import build_features, get_feature_columns

import lightgbm as lgb

OUT = "docs/research/rescue_phase2a_ml_diagnosis.md"
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY"]
FWD = 6
MIN_MOVE = {"EURUSD": 0.0020, "GBPUSD": 0.0025, "USDJPY": 0.25}
SAMPLE = 60000


def auc(y, p):
    """Simple AUC via rank statistic (no sklearn dependency)."""
    y = np.asarray(y); p = np.asarray(p)
    n1 = y.sum(); n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    order = np.argsort(p)
    ranks = np.empty(len(p), float); ranks[order] = np.arange(1, len(p) + 1)
    return (ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def train_eval(X_tr, y_tr, X_te, y_te):
    params = dict(objective="binary", metric="binary_logloss", learning_rate=0.05,
                  num_leaves=63, max_depth=8, min_child_samples=50, subsample=0.8,
                  colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1, verbose=-1, seed=42)
    dtr = lgb.Dataset(X_tr, label=y_tr)
    dva = lgb.Dataset(X_te, label=y_te, reference=dtr)
    m = lgb.train(params, dtr, num_boost_round=400,
                  valid_sets=[dva], callbacks=[lgb.early_stopping(40, verbose=False)])
    p = m.predict(X_te)
    acc = ((p >= 0.5).astype(int) == y_te).mean()
    return acc, auc(y_te, p)


def run_symbol(sym):
    df = pd.read_parquet(f"data/raw/{sym}/H1.parquet").sort_values("time").tail(SAMPLE).reset_index(drop=True)
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    n = len(df)
    fut_close = np.full(n, np.nan)
    fut_hi = np.full(n, np.nan)
    fut_lo = np.full(n, np.nan)
    for i in range(n - FWD):
        fut_close[i] = close[i + FWD]
        fut_hi[i] = high[i + 1:i + 1 + FWD].max()
        fut_lo[i] = low[i + 1:i + 1 + FWD].min()
    ret = fut_close - close
    mm = MIN_MOVE[sym]
    moved = ((fut_hi - close) >= mm) | ((close - fut_lo) >= mm)  # volatility target

    feat = build_features(df.copy(), dropna=False)
    cols = get_feature_columns(feat)
    feat = feat.assign(_dir=(ret > 0).astype(int), _vol=moved.astype(int))
    feat = feat.iloc[:n - FWD]
    feat = feat.replace([np.inf, -np.inf], np.nan).dropna(subset=cols + ["_dir", "_vol"]).reset_index(drop=True)

    split = int(len(feat) * 0.8)
    tr, te = feat.iloc[:split], feat.iloc[split:]
    X_tr, X_te = tr[cols].values, te[cols].values

    # A) direction (only on bars that actually moved up or down clearly)
    dacc, dauc = train_eval(X_tr, tr["_dir"].values, X_te, te["_dir"].values)
    # B) volatility / tradability
    vacc, vauc = train_eval(X_tr, tr["_vol"].values, X_te, te["_vol"].values)
    base_dir = max(te["_dir"].mean(), 1 - te["_dir"].mean())
    base_vol = max(te["_vol"].mean(), 1 - te["_vol"].mean())
    return dict(sym=sym, n=len(feat), dacc=dacc, dauc=dauc, vacc=vacc, vauc=vauc,
                base_dir=base_dir, base_vol=base_vol)


def main():
    rows = []
    for s in SYMBOLS:
        print(f"diagnosing {s}...", flush=True)
        rows.append(run_symbol(s))

    L = ["# Rescue Plan — Phase 2a: ml_direct Root-Cause Diagnosis\n"]
    L.append("**Question:** can the feature set predict DIRECTION, or only VOLATILITY?")
    L.append("Two fresh LightGBM models, same features, 80/20 time split (OOS).\n")
    L.append("- **AUC 0.50 = no skill (coin flip). >0.55 = real signal.**")
    L.append("- Accuracy compared to the majority-class baseline.\n")
    L.append("| Symbol | Dir acc | Dir AUC | (base) | Vol acc | Vol AUC | (base) |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        L.append(f"| {r['sym']} | {r['dacc']:.3f} | **{r['dauc']:.3f}** | {r['base_dir']:.3f} "
                 f"| {r['vacc']:.3f} | **{r['vauc']:.3f}** | {r['base_vol']:.3f} |")

    da = np.mean([r["dauc"] for r in rows])
    va = np.mean([r["vauc"] for r in rows])
    L.append(f"\n**Mean direction AUC = {da:.3f} | Mean volatility AUC = {va:.3f}**\n")

    L.append("## Verdict & rebuild guidance\n")
    L.append("- If **direction AUC ≈ 0.50** and **volatility AUC > 0.55**: confirmed — the "
             "features (ATR, hour, session) predict WHETHER price moves, not WHICH WAY. "
             "`ml_direct` was built to predict direction from non-directional features, so it "
             "is structurally incapable of an edge. This is why calibration was flat (Phase 1c).")
    L.append("\n### How to rebuild WITHOUT repeating the mistake\n")
    L.append("1. **Stop predicting direction from TA features.** The data says it isn't there. "
             "Either (a) repurpose the model as a **tradability/volatility filter** on the "
             "rule-based directional strategies (MACD etc.) — play to what it CAN predict; or "
             "(b) bring genuinely directional inputs (multi-TF trend structure, momentum "
             "persistence, order-flow/COT, cross-pair lead-lag) before attempting direction again.")
    L.append("2. **Align target with execution** (ordered triple-barrier at the real ATR SL/TP, "
             "Phase 1b) — never the 6-bar min-move proxy.")
    L.append("3. **Calibrate probabilities** (isotonic on validation) so a threshold means a "
             "true probability; gate live only above a proven OOS edge.")
    L.append("4. **Judge on trade EV, not classification accuracy** — accuracy here was inflated "
             "by the majority NO_TRADE class while directional precision stayed < 0.50.")
    L.append("- If instead direction AUC > 0.55 somewhere, that symbol/feature is worth a "
             "focused rebuild; pursue it rather than a blanket model.")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"Report written: {OUT}")


if __name__ == "__main__":
    main()
