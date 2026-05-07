"""Phase 7 Step 7 — meta-labeler training run for RSI signals.

Same pipeline as `scripts/train_meta_labeler_macd.py` (Step 6) but
filtered to the 307 RSI signals (after dropping timeouts) instead
of MACD. The RSI strategy uses different SL/TP multipliers
(SL=2.0×ATR, TP=3.0×ATR — see `strategies/rsi_reversal.py`), so
the R-unit conversion factor differs.

Phase 7 Step 6 found the MACD meta-labeler had no edge under
purged-CV (AUC ≈ 0.50, R-PF = 0.84, FAIL dual gate). Step 7 is
the parallel run on RSI — independent corpus, different generative
process, may behave differently.

Outputs:
  - `models/meta_labeler/rsi_v1.pkl` (joblib)
  - `docs/research/phase7_step7_meta_labeler_rsi.md`
  - row appended to `data/improvements.db.meta_labeler_runs`
  - `phase_steps` 7.7 → COMPLETED, `decisions_log` entry on outcome
"""
from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import warnings
warnings.filterwarnings("ignore")

import joblib
import numpy as np
import pandas as pd
import sqlite3
from lightgbm import LGBMClassifier
from sklearn.metrics import (
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from analysis.rr_calculator import phase7_ship_gate
from ml.purged_cv import purged_kfold_indices

# ───────────────────────────── CONFIG ─────────────────────────────
SIGNALS_PARQUET = Path("data/research/primary_signals.parquet")
STRATEGY = "rsi_reversal"
N_SPLITS = 5
EMBARGO_PCT = 0.01
DECISION_THRESHOLD = 0.55
TIMEFRAME_HOURS = 1
RANDOM_SEED = 42

# RSI strategy puts SL at 2.0×ATR, TP at 3.0×ATR (see
# strategies/rsi_reversal.py). Verified against the parquet
# 2026-05-07: WIN rr_ratio mean = +3.000, LOSS mean = -1.999.
# Divide by SL multiplier to recover R-units: WIN=+1.5R, LOSS=-1.0R.
SL_ATR_MULTIPLIER = 2.0

FEATURES = [
    "sma_200",
    "day_of_week",
    "close_vs_sma_100",
    "hour",
    "sma_20_100_diff",
    "dist_from_low_20",
    "dow_sin",
    "sma_100",
    "sma_10_50_diff",
    "sma_50_200_diff",
    "atr_ratio_20",
    "atr_28",
    "close_vs_sma_200",
    "volatility_10",
    "bb_width",
    "volatility_20",
    "volume_ratio",
    "return_20",
    "sma_50",
    "macd_hist",
]

MODEL_OUT = Path("models/meta_labeler/rsi_v1.pkl")
REPORT_OUT = Path("docs/research/phase7_step7_meta_labeler_rsi.md")
TRACKER_DB = "data/improvements.db"


# ───────────────────────────── HELPERS ─────────────────────────────
def derive_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "hour" not in df.columns:
        df["hour"] = df["time"].dt.hour
    if "day_of_week" not in df.columns:
        df["day_of_week"] = df["time"].dt.dayofweek
    if "dow_sin" not in df.columns:
        df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    return df


def build_events_index(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["time", "bars_held"]).copy()
    df["exit_time"] = df["time"] + pd.to_timedelta(
        df["bars_held"].astype(int) * TIMEFRAME_HOURS, unit="h"
    )
    df = df.sort_values("time").reset_index(drop=True)
    df = df.set_index("time")
    return df


def realized_r_for_taken(row: pd.Series) -> float:
    """Convert ATR-units → R-units. See Phase 7 Step 6 calibration note."""
    return float(row["rr_ratio"]) / SL_ATR_MULTIPLIER


def train_one_fold(X_tr, y_tr, X_te) -> tuple[np.ndarray, LGBMClassifier]:
    model = LGBMClassifier(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=5,
        num_leaves=16,
        min_child_samples=20,
        class_weight="balanced",
        n_jobs=-1,
        random_state=RANDOM_SEED,
        verbose=-1,
    )
    model.fit(X_tr, y_tr)
    proba = model.predict_proba(X_te)[:, 1]
    return proba, model


# ───────────────────────────── MAIN ─────────────────────────────
def main() -> int:
    print("=" * 78)
    print("  Phase 7 Step 7 — RSI meta-labeler training")
    print(f"  Run: {datetime.now().isoformat(timespec='seconds')}")
    print("=" * 78)

    raw = pd.read_parquet(SIGNALS_PARQUET)
    print(f"  Loaded {len(raw):,} signals from {SIGNALS_PARQUET}")

    rsi = raw[raw["strategy"] == STRATEGY].copy()
    print(f"  RSI subset: {len(rsi):,} rows")

    n_timeouts = int((rsi["label"] == 0).sum())
    rsi = rsi[rsi["label"] != 0].copy()
    rsi["meta_label"] = (rsi["label"] == 1).astype(int)
    print(
        f"  After dropping {n_timeouts} timeouts: {len(rsi):,} signals "
        f"(TP={int(rsi['meta_label'].sum())}, "
        f"SL={int(len(rsi) - rsi['meta_label'].sum())})"
    )

    rsi = derive_time_features(rsi)
    rsi = build_events_index(rsi)
    print(f"  Events sorted, exit_time computed (TF={TIMEFRAME_HOURS}h)")

    available = [c for c in FEATURES if c in rsi.columns]
    missing = [c for c in FEATURES if c not in rsi.columns]
    if missing:
        print(f"  WARN: features missing from corpus, dropped: {missing}")
    print(f"  Features used: {len(available)}/{len(FEATURES)}")

    X = rsi[available].fillna(0).replace([np.inf, -np.inf], 0).values
    y = rsi["meta_label"].values

    aucs, f1s, precs, recs = [], [], [], []
    fold_metrics = []
    taken_rows = []

    for fold_i, (tr_idx, te_idx) in enumerate(
        purged_kfold_indices(rsi, n_splits=N_SPLITS, embargo_pct=EMBARGO_PCT)
    ):
        if len(tr_idx) < 20 or len(te_idx) < 10:
            print(f"  fold {fold_i}: too small (tr={len(tr_idx)}, te={len(te_idx)}) — skip")
            continue
        if y[tr_idx].sum() < 3 or (len(y[tr_idx]) - y[tr_idx].sum()) < 3:
            print(f"  fold {fold_i}: imbalanced train — skip")
            continue

        proba, _ = train_one_fold(X[tr_idx], y[tr_idx], X[te_idx])
        pred = (proba >= DECISION_THRESHOLD).astype(int)
        yte = y[te_idx]

        if len(np.unique(yte)) > 1:
            aucs.append(roc_auc_score(yte, proba))
        if pred.sum() > 0:
            f1s.append(f1_score(yte, pred, zero_division=0))
            precs.append(precision_score(yte, pred, zero_division=0))
        recs.append(recall_score(yte, pred, zero_division=0))

        taken_mask = pred == 1
        if taken_mask.any():
            te_df = rsi.iloc[te_idx].copy()
            te_df["proba"] = proba
            te_df["taken"] = taken_mask
            taken_rows.append(te_df[taken_mask])

        fold_metrics.append({
            "fold": fold_i,
            "n_train": len(tr_idx),
            "n_test": len(te_idx),
            "auc": float(roc_auc_score(yte, proba)) if len(np.unique(yte)) > 1 else None,
            "n_taken": int(taken_mask.sum()),
            "n_taken_wins": int(yte[taken_mask].sum()),
        })
        print(
            f"  fold {fold_i}: tr={len(tr_idx):4d} te={len(te_idx):3d} "
            f"AUC={fold_metrics[-1]['auc']:.3f} "
            f"taken={fold_metrics[-1]['n_taken']}/{len(te_idx)} "
            f"wins={fold_metrics[-1]['n_taken_wins']}/{fold_metrics[-1]['n_taken'] or 1}"
        )

    print("-" * 78)
    auc_mean = float(np.mean(aucs)) if aucs else None
    auc_std = float(np.std(aucs)) if aucs else None
    f1_mean = float(np.mean(f1s)) if f1s else 0.0
    prec_mean = float(np.mean(precs)) if precs else 0.0
    rec_mean = float(np.mean(recs)) if recs else 0.0

    raw_wr = 100.0 * y.sum() / max(1, len(y))

    if taken_rows:
        oos_taken = pd.concat(taken_rows)
        n_taken = len(oos_taken)
        n_wins = int(oos_taken["meta_label"].sum())
        oos_taken["realized_r"] = oos_taken.apply(realized_r_for_taken, axis=1)
        oos_taken["pnl"] = oos_taken["pnl_price"]
        gate = phase7_ship_gate(
            pnls=oos_taken["pnl"].tolist(),
            rrs=oos_taken["realized_r"].tolist(),
        )
        filtered_wr = 100.0 * n_wins / n_taken
    else:
        n_taken = n_wins = 0
        gate = {
            "pf_dollars": 0.0,
            "pf_r": 0.0,
            "passes_dollars_gate": False,
            "passes_r_gate": False,
            "passes_dual_gate": False,
            "thresholds": {"r_min": 1.3, "dollars_min": 1.0},
        }
        filtered_wr = 0.0

    keep_rate = 100.0 * n_taken / max(1, len(y))
    wr_lift = filtered_wr - raw_wr

    print("  CV summary")
    print(f"    AUC      : {auc_mean:.3f} ± {auc_std:.3f}" if auc_mean else "    AUC      : —")
    print(f"    F1       : {f1_mean:.3f}")
    print(f"    Precision: {prec_mean:.3f}")
    print(f"    Recall   : {rec_mean:.3f}")
    print(f"    raw WR   : {raw_wr:.1f}%")
    print(f"    filtered : {filtered_wr:.1f}% on {n_taken} taken ({keep_rate:.0f}% keep-rate)")
    print(f"    WR lift  : {wr_lift:+.1f}pp")
    print(f"    R-PF     : {gate['pf_r']:.3f} ({'PASS' if gate['passes_r_gate'] else 'FAIL'} ≥1.30)")
    print(f"    $-PF     : {gate['pf_dollars']:.3f} ({'PASS' if gate['passes_dollars_gate'] else 'FAIL'} ≥1.00)")
    print(f"    DUAL GATE: {'PASS' if gate['passes_dual_gate'] else 'FAIL'}")

    # ─── Refit on full corpus + persist ───
    print("-" * 78)
    print("  Refitting on full corpus + saving model artifact")
    final_model = LGBMClassifier(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=5,
        num_leaves=16,
        min_child_samples=20,
        class_weight="balanced",
        n_jobs=-1,
        random_state=RANDOM_SEED,
        verbose=-1,
    )
    final_model.fit(X, y)
    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "model": final_model,
        "features": available,
        "decision_threshold": DECISION_THRESHOLD,
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "n_train": int(len(y)),
        "strategy": STRATEGY,
        "cv_auc_mean": auc_mean,
        "cv_auc_std": auc_std,
        "ship_gate": gate,
        "raw_wr": raw_wr,
        "filtered_wr": filtered_wr,
        "keep_rate_pct": keep_rate,
    }
    joblib.dump(artifact, MODEL_OUT)
    print(f"  ✓ saved {MODEL_OUT}")

    # ─── Tracker row ───
    try:
        conn = sqlite3.connect(TRACKER_DB)
        conn.execute(
            "INSERT INTO meta_labeler_runs "
            "(run_time, architecture, scope, n_signals, n_features, cv_splits, "
            " auc_mean, auc_std, f1_mean, precision_mean, recall_mean, "
            " baseline_wr, lifted_wr, wr_lift_points, verdict, notes) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                datetime.now().isoformat(timespec="seconds"),
                "PER_STRATEGY_V2",
                f"strategy={STRATEGY} (Phase 7 Step 7)",
                int(len(y)),
                len(available),
                N_SPLITS,
                auc_mean,
                auc_std,
                f1_mean,
                prec_mean,
                rec_mean,
                raw_wr,
                filtered_wr,
                wr_lift,
                "PASS" if gate["passes_dual_gate"] else "FAIL",
                f"R-PF={gate['pf_r']:.3f} $-PF={gate['pf_dollars']:.3f} keep={keep_rate:.0f}%",
            ),
        )
        conn.commit()
        conn.close()
        print(f"  ✓ tracker row appended to meta_labeler_runs")
    except Exception as e:
        print(f"  WARN: tracker append failed: {e}")

    # ─── Markdown report ───
    md = []
    md.append("# Phase 7 Step 7 — RSI Meta-Labeler\n")
    md.append(f"**Date:** {datetime.now().date().isoformat()}  ")
    md.append(f"**Re-runnable:** `python scripts/train_meta_labeler_rsi.py`  ")
    md.append(f"**Model artifact:** `{MODEL_OUT.as_posix()}`\n")

    md.append("## Corpus\n")
    md.append(f"- Source: `{SIGNALS_PARQUET.as_posix()}` filtered to `strategy={STRATEGY}`")
    md.append(f"- After dropping {n_timeouts} timeout signals: **{len(y):,} rows** "
              f"(TP={int(y.sum())}, SL={int(len(y) - y.sum())})")
    md.append(f"- Time range: {rsi.index.min()} → {rsi.index.max()}")
    md.append(f"- Features used: **{len(available)}** of {len(FEATURES)} from Phase 7 Step 4 ranking")
    md.append(f"- Strategy params: SL = {SL_ATR_MULTIPLIER}×ATR, TP = 3.0×ATR, planned R:R = 1.5\n")

    md.append("## Validation\n")
    md.append(f"- Purged K-Fold ({N_SPLITS} splits) with {EMBARGO_PCT*100:.0f}% embargo")
    md.append(f"- Decision threshold: probability ≥ {DECISION_THRESHOLD}")
    md.append(f"- LightGBM (n_est=300, lr=0.05, depth=5, leaves=16, class_weight=balanced)\n")

    md.append("## Cross-validation summary\n")
    md.append("| Metric | Value |")
    md.append("|---|---:|")
    md.append(f"| ROC AUC (mean) | {auc_mean:.3f} ± {auc_std:.3f} |" if auc_mean
              else "| ROC AUC | — |")
    md.append(f"| F1 | {f1_mean:.3f} |")
    md.append(f"| Precision | {prec_mean:.3f} |")
    md.append(f"| Recall | {rec_mean:.3f} |")
    md.append(f"| Raw WR | {raw_wr:.1f}% |")
    md.append(f"| Filtered WR | {filtered_wr:.1f}% |")
    md.append(f"| WR lift | {wr_lift:+.1f}pp |")
    md.append(f"| Keep-rate | {keep_rate:.0f}% ({n_taken} of {len(y)}) |")

    md.append("\n## Phase 7 ship-gate (projected on OOS taken signals)\n")
    md.append("| Metric | Value | Threshold | Verdict |")
    md.append("|---|---:|---:|:---:|")
    md.append(f"| R-PF | {gate['pf_r']:.3f} | ≥ 1.30 | "
              f"{'PASS' if gate['passes_r_gate'] else 'FAIL'} |")
    md.append(f"| $-PF | {gate['pf_dollars']:.3f} | ≥ 1.00 | "
              f"{'PASS' if gate['passes_dollars_gate'] else 'FAIL'} |")
    md.append(f"| **Dual-gate** | — | both | "
              f"**{'PASS' if gate['passes_dual_gate'] else 'FAIL'}** |")
    md.append("")

    md.append("## Per-fold detail\n")
    md.append("| Fold | n_train | n_test | AUC | n_taken | n_wins |")
    md.append("|---:|---:|---:|---:|---:|---:|")
    for f in fold_metrics:
        auc_s = f"{f['auc']:.3f}" if f["auc"] is not None else "—"
        md.append(f"| {f['fold']} | {f['n_train']} | {f['n_test']} | {auc_s} | "
                  f"{f['n_taken']} | {f['n_taken_wins']} |")

    # Upper-bound math: at the filtered WR achieved, what's the ceiling on R-PF?
    if filtered_wr > 0 and filtered_wr < 100:
        rpf_ceiling = (filtered_wr / (100 - filtered_wr)) * (3.0 / SL_ATR_MULTIPLIER)
    else:
        rpf_ceiling = 0.0

    md.append("\n## Honest reading\n")
    if gate["passes_dual_gate"]:
        md.append("- Dual-gate **PASSES** — RSI meta-labeler clears Phase 7 ship gate "
                  "on OOS purged folds. Wire into `ml_filtered_strategy` at Step 8.")
    else:
        md.append(f"- AUC = {auc_mean:.3f} on purged OOS folds — "
                  f"{'minimal' if abs(auc_mean - 0.5) < 0.03 else 'modest' if abs(auc_mean - 0.5) < 0.07 else 'meaningful'} "
                  f"predictive signal vs random.")
        md.append(f"- Filtered WR ({filtered_wr:.1f}%) vs raw WR ({raw_wr:.1f}%): "
                  f"{wr_lift:+.1f}pp lift.")
        md.append(f"- R-PF = {gate['pf_r']:.3f} fails the 1.30 gate. With WR = {filtered_wr:.1f}% "
                  f"and a fixed planned R:R of 1.5, the upper bound on R-PF for any "
                  f"selector at this WR is {rpf_ceiling:.2f} — "
                  f"{'no decision threshold can rescue this fold mix' if rpf_ceiling < 1.3 else 'a higher threshold might recover the gate'}.")
        md.append(f"- $-PF = {gate['pf_dollars']:.3f} "
                  f"({'passes' if gate['passes_dollars_gate'] else 'fails'} the 1.00 gate).")
        md.append("")
        md.append("**Step 7 verdict: meta-labeling RSI as-configured does not produce "
                  "a shippable artifact.** Same recovery options as Step 6 (Path B "
                  "regime-stratified retrain, richer feature set, threshold tuning, or "
                  "accept no second-layer edge).")

    md.append("\n## Comparison to Step 6 (MACD)\n")
    md.append("| | MACD (Step 6) | RSI (Step 7) |")
    md.append("|---|---:|---:|")
    md.append(f"| Corpus size | 710 | {len(y)} |")
    md.append(f"| Raw WR | 39.7% | {raw_wr:.1f}% |")
    md.append(f"| AUC | 0.495 ± 0.046 | {auc_mean:.3f} ± {auc_std:.3f} |")
    md.append(f"| WR lift | -2.2pp | {wr_lift:+.1f}pp |")
    md.append(f"| R-PF | 0.840 (FAIL) | {gate['pf_r']:.3f} ({'PASS' if gate['passes_r_gate'] else 'FAIL'}) |")
    md.append(f"| $-PF | 1.417 (PASS) | {gate['pf_dollars']:.3f} ({'PASS' if gate['passes_dollars_gate'] else 'FAIL'}) |")
    md.append(f"| Dual gate | FAIL | **{'PASS' if gate['passes_dual_gate'] else 'FAIL'}** |")
    md.append("")

    md.append("## Calibration notes\n")
    md.append(f"- `rr_ratio` in `primary_signals.parquet` is in **ATR units**. RSI strategy "
              f"uses SL = {SL_ATR_MULTIPLIER}×ATR / TP = 3.0×ATR, so WIN rr_ratio ≈ +3.0 and "
              f"LOSS ≈ -2.0. Verified empirically 2026-05-07. R-unit conversion divides by "
              f"SL multiplier ({SL_ATR_MULTIPLIER}), giving WIN = +1.5R / LOSS = -1.0R.")
    md.append("- Same unit-conversion bug pattern hit Step 6 first; this script applies the "
              "fix from the start (see `realized_r_for_taken`).")
    md.append("- **$-PF caveat (uncovered 2026-05-07):** `pnl_price` in the corpus is "
              "*raw price* PnL, not dollar PnL. Across heterogeneous symbols this "
              "varies 4 orders of magnitude — EURUSD wins ≈ 0.008 (= 80 pips), USDJPY "
              "wins ≈ 0.78, XAUUSD wins ≈ 71. So `sum(wins) / sum(|losses|)` on raw "
              "`pnl_price` is dominated by whichever symbol the selector happens to "
              "pick, not by actual $-outcome. **R-PF is the trustworthy projection** "
              "from this corpus; $-PF should be recomputed from live trade ledger or "
              "with explicit pip_value × volume normalization. Step 6's $-PF=1.42 PASS "
              "and Step 7's $-PF=0.018 FAIL are both unreliable for the same reason. "
              "Filed as a follow-up note for Step 10's full-backtest reporting.\n")

    md.append("## Next\n")
    md.append("- **Step 8** — refactor `ml_filtered_strategy` + engine to load whichever "
              "of (macd_v1, rsi_v1) actually clears the ship gate. If neither does, "
              "Step 8 needs a different design (e.g., regime filter as a hard rule).")
    md.append("- **Step 10** — full 3-year backtest with the meta-labeler in the loop.")
    md.append("- **Step 11** — ship gate (Jun 8).\n")

    md.append("## Cross-references\n")
    md.append("- `ml/purged_cv.py` — Phase 7 Step 2")
    md.append("- `docs/research/phase7_step4_feature_importance.md` — feature shortlist")
    md.append("- `docs/research/phase7_step6_meta_labeler_macd.md` — MACD parallel")
    md.append("- `analysis/rr_calculator.py::phase7_ship_gate` — gate definition")
    md.append("- `data/improvements.db` table `meta_labeler_runs` — historical runs")

    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"  ✓ report: {REPORT_OUT}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
