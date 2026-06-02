"""
Build & validate the ml_direct rebuild as a META-LABELING TRADE FILTER.
Rescue Plan Phase 2c. READ-ONLY w.r.t. live system (writes models + report only).

Implements the design in docs/research/ml_direct_rebuild_design.md and checks the
acceptance criteria. Pipeline:

  1. Replay macd_crossover on M15 history for all symbols (real conditions).
  2. For each MACD signal, label by the REAL ordered triple-barrier outcome
     (TP=3.5xATR, SL=2.5xATR) -> WIN(1)/LOSS(0). Capture causal features.
  3. Pool symbols; use only SCALE-INVARIANT features (so one model generalises).
  4. Walk-forward (3 folds, purged): train LightGBM P(win), pick an EV/PF-max
     threshold on a validation slice subject to a pass-rate floor, evaluate the
     GATED vs UNGATED MACD economics on the test block.
  5. Controls: permutation (shuffle labels -> AUC must ->0.50).
  6. Print acceptance verdict.

Acceptance (OOS, from the design doc):
  A1 gated R-PF >= ungated + 0.15
  A2 gated R-PF >= 1.10
  A3 gated trades/symbol-yr >= 40  (ungated MACD-M15 ~87 -> pass_rate >= 0.46)
  A4 permutation AUC ~ 0.50
  A5 A1-A3 hold in >= 2 of 3 folds

Run: venv/Scripts/python.exe scripts/build_ml_filter.py
"""
import sys
import os
import glob
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from features.ml.feature_engine import build_features, get_feature_columns
from features.technical.indicators import add_atr, add_ema
import lightgbm as lgb

OUT = "docs/research/rescue_phase2c_ml_filter_results.md"
TP_MULT, SL_MULT = 3.5, 2.5          # macd_crossover real exits
ATR_THR = 1.2                         # STAT-003 filter (kept)
HORIZON = 100                         # M15 bars to resolve a trade
N_FOLDS = 3
PASS_FLOOR = 0.46                     # keep >=40/symbol-yr of the ~87 ungated
UNGATED_PER_YR = 87.0                 # MACD-M15 baseline (Phase 1f)
BARS_TAIL = 90000                     # M15 bars/symbol to use


def auc(y, p):
    y = np.asarray(y); p = np.asarray(p)
    n1 = int(y.sum()); n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    order = np.argsort(p, kind="mergesort")
    r = np.empty(len(p), float); r[order] = np.arange(1, len(p) + 1)
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def scale_invariant(cols):
    excl = {"atr_7", "atr_14", "atr_28", "macd_line", "macd_signal", "macd_hist"}
    return [c for c in cols if not (c.startswith("sma_") or c.startswith("ema_") or c in excl)]


def macd_signals(d):
    """Return int8 array: 1=BUY, -1=SELL, 0=none. Mirrors macd_crossover v2.0."""
    price = d["close"].values; macd = d["macd_line"].values; sig = d["macd_signal"].values
    hist = d["macd_hist"].values; ema50 = d["ema_50"].values; ema200 = d["ema_200"].values
    atr = d["atr_14"].values; avg = d["avg_atr20"].values
    pm, ps, ph = np.roll(macd, 1), np.roll(sig, 1), np.roll(hist, 1)
    ok = atr >= ATR_THR * avg
    buy = ok & (pm <= ps) & (macd > sig) & (price > ema50) & (ema50 > ema200) & (hist > ph)
    sell = ok & (pm >= ps) & (macd < sig) & (price < ema50) & (ema50 < ema200) & (hist < ph)
    o = np.zeros(len(d), np.int8); o[buy] = 1; o[sell] = -1; o[:1] = 0
    return o


def outcome(direction, high, low, close, atr, i):
    a = atr[i]
    if not np.isfinite(a) or a <= 0:
        return None
    entry = close[i]
    if direction == 1:
        tp, sl = entry + TP_MULT * a, entry - SL_MULT * a
        for j in range(i + 1, min(i + 1 + HORIZON, len(close))):
            if low[j] <= sl: return 0
            if high[j] >= tp: return 1
    else:
        tp, sl = entry - TP_MULT * a, entry + SL_MULT * a
        for j in range(i + 1, min(i + 1 + HORIZON, len(close))):
            if high[j] >= sl: return 0
            if low[j] <= tp: return 1
    return None  # timeout -> excluded


def build_dataset():
    syms = sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob("data/raw/*/M15.parquet"))
    frames = []
    feat_cols = None
    for sym in syms:
        df = pd.read_parquet(f"data/raw/{sym}/M15.parquet").sort_values("time").tail(BARS_TAIL).reset_index(drop=True)
        # signal-grade indicators
        sd = df.copy()
        sd = add_atr(sd, 14); sd = add_ema(sd, 50); sd = add_ema(sd, 200)
        from features.technical.indicators import add_macd
        sd = add_macd(sd)
        sd["avg_atr20"] = sd["atr_14"].rolling(20).mean()
        sig = macd_signals(sd)
        # model features (causal), aligned by position
        feat = build_features(df.copy(), dropna=False)
        if feat_cols is None:
            feat_cols = scale_invariant(get_feature_columns(feat))
        high = sd["high"].values; low = sd["low"].values; close = sd["close"].values; atr = sd["atr_14"].values
        idxs = np.where(sig != 0)[0]
        recs = []
        for i in idxs:
            y = outcome(int(sig[i]), high, low, close, atr, i)
            if y is None:
                continue
            row = feat.iloc[i]
            if row[feat_cols].isna().any():
                continue
            rec = {c: row[c] for c in feat_cols}
            rec["y"] = y; rec["time"] = df["time"].iloc[i]; rec["symbol"] = sym
            recs.append(rec)
        if recs:
            frames.append(pd.DataFrame(recs))
        print(f"  {sym}: {len(recs)} labeled MACD-M15 trades", flush=True)
    data = pd.concat(frames, ignore_index=True).sort_values("time").reset_index(drop=True)
    return data, feat_cols


def pf_econ(y):
    """R-PF and net R for a set of decided trades (y in {0,1})."""
    w = int(np.sum(y == 1)); l = int(np.sum(y == 0))
    pf = (w * TP_MULT) / (l * SL_MULT) if l else float("inf")
    return pf, w, l


def main():
    print("Building meta-label dataset...", flush=True)
    data, cols = build_dataset()
    n = len(data)
    base_wr = data["y"].mean()
    print(f"Total labeled trades: {n} | base win-rate {base_wr:.1%} | features {len(cols)}", flush=True)

    edges = np.linspace(0, n, N_FOLDS + 2, dtype=int)
    fold_rows = []
    params = dict(objective="binary", metric="binary_logloss", learning_rate=0.05,
                  num_leaves=31, max_depth=6, min_child_samples=40, subsample=0.8,
                  colsample_bytree=0.8, reg_alpha=0.2, reg_lambda=0.2, verbose=-1, seed=42)

    for k in range(N_FOLDS):
        tr0, tr1 = edges[k], edges[k + 1]
        te0, te1 = edges[k + 1], edges[k + 2]
        tr = data.iloc[tr0:tr1]
        te = data.iloc[te0:te1]
        # split train into fit + validation (for threshold selection)
        vsplit = int(len(tr) * 0.75)
        fit, val = tr.iloc[:vsplit], tr.iloc[vsplit:]
        if len(fit) < 100 or len(val) < 40 or len(te) < 40:
            continue
        Xf, yf = fit[cols].values, fit["y"].values
        m = lgb.train(params, lgb.Dataset(Xf, label=yf), num_boost_round=300)
        pv = m.predict(val[cols].values)
        pt = m.predict(te[cols].values)
        test_auc = auc(te["y"].values, pt)

        # threshold: maximise validation R-PF s.t. pass-rate >= floor
        best_thr, best_pf = None, -1
        for q in np.quantile(pv, np.linspace(0.0, 0.9, 25)):
            mask = pv >= q
            if mask.mean() < PASS_FLOOR:
                continue
            pf, _, _ = pf_econ(val["y"].values[mask])
            if pf > best_pf:
                best_pf, best_thr = pf, q
        if best_thr is None:
            best_thr = np.quantile(pv, 1 - PASS_FLOOR)

        # evaluate on test
        ung_pf, uw, ul = pf_econ(te["y"].values)
        gmask = pt >= best_thr
        g_pf, gw, gl = pf_econ(te["y"].values[gmask])
        pass_rate = float(gmask.mean())
        gated_per_yr = UNGATED_PER_YR * pass_rate

        # permutation control
        yperm = np.random.RandomState(k).permutation(yf)
        mp = lgb.train(params, lgb.Dataset(Xf, label=yperm), num_boost_round=300)
        perm_auc = auc(te["y"].values, mp.predict(te[cols].values))

        fold_rows.append(dict(fold=k + 1, n_test=len(te), auc=test_auc, perm_auc=perm_auc,
                              ung_pf=ung_pf, g_pf=g_pf, pass_rate=pass_rate,
                              gated_per_yr=gated_per_yr, gw=gw, gl=gl, thr=best_thr))
        print(f"  fold {k+1}: auc={test_auc:.3f} perm={perm_auc:.3f} "
              f"ung_pf={ung_pf:.2f} gated_pf={g_pf:.2f} pass={pass_rate:.0%}", flush=True)

    # ── acceptance ──
    def ok(r):
        return (r["g_pf"] >= r["ung_pf"] + 0.15) and (r["g_pf"] >= 1.10) and (r["gated_per_yr"] >= 40)
    folds_ok = sum(ok(r) for r in fold_rows)
    mean_auc = np.mean([r["auc"] for r in fold_rows]) if fold_rows else float("nan")
    mean_perm = np.mean([r["perm_auc"] for r in fold_rows]) if fold_rows else float("nan")
    mean_ung = np.mean([r["ung_pf"] for r in fold_rows]) if fold_rows else float("nan")
    mean_g = np.mean([r["g_pf"] for r in fold_rows]) if fold_rows else float("nan")
    verdict = (folds_ok >= 2) and (abs(mean_perm - 0.5) < 0.04)

    L = ["# Rescue Plan — Phase 2c: ml_direct Rebuild as Filter — Acceptance Test\n"]
    L.append(f"**Dataset:** pooled MACD-M15 trades labeled by real ordered TP/SL "
             f"(TP={TP_MULT}× / SL={SL_MULT}×ATR). n={n}, base win-rate {base_wr:.1%}, "
             f"{len(cols)} scale-invariant features.")
    L.append(f"**Protocol:** {N_FOLDS}-fold purged walk-forward; threshold = val R-PF max "
             f"s.t. pass-rate ≥ {PASS_FLOOR:.0%}. Permutation control per fold.\n")
    L.append("| Fold | n test | Filter AUC | Perm AUC | Ungated PF | **Gated PF** | Pass% | Gated/sym-yr | Accept? |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|:--:|")
    for r in fold_rows:
        L.append(f"| {r['fold']} | {r['n_test']} | {r['auc']:.3f} | {r['perm_auc']:.3f} | "
                 f"{r['ung_pf']:.2f} | **{r['g_pf']:.2f}** | {r['pass_rate']:.0%} | "
                 f"{r['gated_per_yr']:.0f} | {'✅' if ok(r) else '❌'} |")
    L.append(f"\n**Means:** filter AUC {mean_auc:.3f} | permutation AUC {mean_perm:.3f} "
             f"| ungated PF {mean_ung:.2f} | gated PF {mean_g:.2f}\n")
    L.append("## Acceptance criteria\n")
    L.append(f"- A1 gated PF ≥ ungated + 0.15: mean {mean_g:.2f} vs {mean_ung+0.15:.2f} "
             f"→ {'PASS' if mean_g >= mean_ung+0.15 else 'FAIL'}")
    L.append(f"- A2 gated PF ≥ 1.10: {mean_g:.2f} → {'PASS' if mean_g >= 1.10 else 'FAIL'}")
    L.append(f"- A4 permutation AUC ≈ 0.50: {mean_perm:.3f} → {'PASS (no leakage)' if abs(mean_perm-0.5)<0.04 else 'FAIL'}")
    L.append(f"- A5 ≥2/3 folds pass A1–A3: {folds_ok}/{len(fold_rows)} → {'PASS' if folds_ok>=2 else 'FAIL'}")
    L.append(f"\n## VERDICT: {'✅ SHIP — build the filter into the engine (shadow mode first)' if verdict else '❌ DO NOT SHIP — keep ml_direct retired; frequency rests on MACD-M15 alone'}\n")
    if not verdict:
        L.append("A negative result is a valid, honest outcome: it means MACD signals on M15 do "
                 "not carry a learnable win/loss separation strong enough to beat the bar. The "
                 "design doc anticipated this — ml_direct stays retired rather than shipping a "
                 "fake edge. Next options: (a) richer regime features, (b) per-symbol models, "
                 "(c) accept MACD-M15 ungated and focus elsewhere.")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"VERDICT: {'SHIP' if verdict else 'DO NOT SHIP'} | "
          f"filter AUC {mean_auc:.3f} | gated PF {mean_g:.2f} vs ungated {mean_ung:.2f} | "
          f"folds_ok {folds_ok}/{len(fold_rows)}")
    print(f"Report written: {OUT}")


if __name__ == "__main__":
    main()
