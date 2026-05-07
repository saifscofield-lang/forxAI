"""Phase 7 Step 6 — meta-labeler training run for MACD signals.

This is the production-grade training script that promotes the Phase 5
research prototype (`scripts/research_meta_labeler_prototype.py`) to a
shippable artifact. Differences vs the prototype:

  - Uses the new `ml.purged_cv.purged_kfold_indices` (López de Prado
    Ch.7) instead of an inline class. Embargo defaults to 1% of n.
  - Uses the 20 features from Phase 7 Step 4's combined MDI+SFI
    ranking (`docs/research/phase7_step4_feature_importance.md`)
    instead of the 20-feature shortlist from Phase 5 step 7.
  - Reports Phase 7 ship-gate metrics (R-PF, $-PF) computed on the
    OOS taken signals — projects what the engine would book if it
    trusted the meta-labeler. Uses `analysis.rr_calculator` so the
    definition matches the live engine.
  - Saves a fitted artifact (`models/meta_labeler/macd_v1.pkl`)
    refit on the full dataset so engine code can load it directly.
    Phase 7 Step 8 wires this into `ml_filtered_strategy`.

The corpus is `data/research/primary_signals.parquet` filtered to
MACD signals only (815 of 1,144 rows). RSI signals get their own
training run in Phase 7 Step 7.

Outputs:
  - `models/meta_labeler/macd_v1.pkl` (joblib)
  - `docs/research/phase7_step6_meta_labeler_macd.md`
  - rows appended to `data/improvements.db` table `meta_labeler_runs`
"""
from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 stdout so loguru / print don't crash on the Arabic comments
# elsewhere in the project when this script is piped to a file.
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
STRATEGY = "macd_crossover"
N_SPLITS = 5
EMBARGO_PCT = 0.01            # 1% of corpus
DECISION_THRESHOLD = 0.55     # same as the Phase 5 prototype
TIMEFRAME_HOURS = 1           # H1 — primary timeframe per CLAUDE.md
RANDOM_SEED = 42

# MACD strategy puts SL at 2.5×ATR, TP at 3.5×ATR (see
# strategies/macd_crossover.py). primary_signals.parquet stores
# rr_ratio in ATR-units (signed). To convert to R-units (multiples
# of risk-per-trade) divide by the SL multiplier — that gives
# WIN ≈ +1.4R, LOSS ≈ -1.0R as expected.
SL_ATR_MULTIPLIER = 2.5

# Phase 7 Step 4 combined MDI+SFI top 20.
# Time-of-day features (hour, day_of_week, dow_sin) are derived from
# the `time` column in the corpus if not present as columns.
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

MODEL_OUT = Path("models/meta_labeler/macd_v1.pkl")
REPORT_OUT = Path("docs/research/phase7_step6_meta_labeler_macd.md")
TRACKER_DB = "data/improvements.db"


# ───────────────────────────── HELPERS ─────────────────────────────
def derive_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add hour / day_of_week / dow_sin if absent. Mutates a copy."""
    df = df.copy()
    if "hour" not in df.columns:
        df["hour"] = df["time"].dt.hour
    if "day_of_week" not in df.columns:
        df["day_of_week"] = df["time"].dt.dayofweek
    if "dow_sin" not in df.columns:
        df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    return df


def build_events_index(df: pd.DataFrame) -> pd.DataFrame:
    """Index by entry time (`time`) and add `exit_time` column for
    purged_kfold. Exit = entry + bars_held×TIMEFRAME_HOURS (H1).
    Drop rows with missing time or bars_held."""
    df = df.dropna(subset=["time", "bars_held"]).copy()
    df["exit_time"] = df["time"] + pd.to_timedelta(
        df["bars_held"].astype(int) * TIMEFRAME_HOURS, unit="h"
    )
    df = df.sort_values("time").reset_index(drop=True)
    df = df.set_index("time")
    return df


def realized_r_for_taken(row: pd.Series) -> float:
    """Realized R for one taken signal, normalized to risk units.

    `rr_ratio` in primary_signals.parquet is in **ATR units**, not R
    units — verified empirically 2026-05-07: macd wins ≈ +3.5 (=TP×ATR
    multiplier), macd losses ≈ -2.5 (=SL×ATR multiplier). To convert to
    realized R (multiples of risk per trade), normalize by the SL
    multiplier in ATR units.

    For MACD strategy: SL = 2.5×ATR (see strategies/macd_crossover.py).
    So realized_r = rr_ratio / 2.5 gives WIN = +1.4R, LOSS = -1.0R,
    matching the planned R:R = 3.5/2.5 = 1.4."""
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
    print("  Phase 7 Step 6 — MACD meta-labeler training")
    print(f"  Run: {datetime.now().isoformat(timespec='seconds')}")
    print("=" * 78)

    raw = pd.read_parquet(SIGNALS_PARQUET)
    print(f"  Loaded {len(raw):,} signals from {SIGNALS_PARQUET}")

    macd = raw[raw["strategy"] == STRATEGY].copy()
    print(f"  MACD subset: {len(macd):,} rows")

    # Drop timeouts (label=0) — meta-labeling is binary TP-vs-SL.
    n_timeouts = int((macd["label"] == 0).sum())
    macd = macd[macd["label"] != 0].copy()
    macd["meta_label"] = (macd["label"] == 1).astype(int)
    print(
        f"  After dropping {n_timeouts} timeouts: {len(macd):,} signals "
        f"(TP={int(macd['meta_label'].sum())}, "
        f"SL={int(len(macd) - macd['meta_label'].sum())})"
    )

    macd = derive_time_features(macd)
    macd = build_events_index(macd)
    print(f"  Events sorted, exit_time computed (TF={TIMEFRAME_HOURS}h)")

    available = [c for c in FEATURES if c in macd.columns]
    missing = [c for c in FEATURES if c not in macd.columns]
    if missing:
        print(f"  WARN: features missing from corpus, dropped: {missing}")
    print(f"  Features used: {len(available)}/{len(FEATURES)}")

    X = macd[available].fillna(0).replace([np.inf, -np.inf], 0).values
    y = macd["meta_label"].values

    aucs, f1s, precs, recs = [], [], [], []
    fold_metrics = []
    taken_rows = []   # accumulate OOS taken signals across folds for ship-gate

    for fold_i, (tr_idx, te_idx) in enumerate(
        purged_kfold_indices(macd, n_splits=N_SPLITS, embargo_pct=EMBARGO_PCT)
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
            te_df = macd.iloc[te_idx].copy()
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
        oos_taken["pnl"] = oos_taken["pnl_price"]   # primary_signals stores per-unit price PnL
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

    # ─── Refit on full corpus and persist ───
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
                f"strategy={STRATEGY} (Phase 7 Step 6)",
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
    md.append("# Phase 7 Step 6 — MACD Meta-Labeler\n")
    md.append(f"**Date:** {datetime.now().date().isoformat()}  ")
    md.append(f"**Re-runnable:** `python scripts/train_meta_labeler_macd.py`  ")
    md.append(f"**Model artifact:** `{MODEL_OUT.as_posix()}`\n")

    md.append("## Corpus\n")
    md.append(f"- Source: `{SIGNALS_PARQUET.as_posix()}` filtered to `strategy={STRATEGY}`")
    md.append(f"- After dropping {n_timeouts} timeout signals: **{len(y):,} rows** "
              f"(TP={int(y.sum())}, SL={int(len(y) - y.sum())})")
    md.append(f"- Time range: {macd.index.min()} → {macd.index.max()}")
    md.append(f"- Features used: **{len(available)}** of {len(FEATURES)} from Phase 7 Step 4 ranking\n")

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

    md.append("\n## Honest reading\n")
    if gate["passes_dual_gate"]:
        md.append("- Dual-gate **PASSES** — MACD meta-labeler clears Phase 7 ship gate "
                  "on OOS purged folds. Ready for Step 8 wiring into "
                  "`ml_filtered_strategy`.")
    else:
        md.append(f"- AUC ≈ 0.50 on purged OOS folds means **the classifier has no "
                  f"predictive edge** on this corpus with this feature set.")
        md.append(f"- Filtered WR ({filtered_wr:.1f}%) is **below** raw WR ({raw_wr:.1f}%) — "
                  f"selection is not just neutral, it's net-negative on hit rate.")
        md.append(f"- R-PF = {gate['pf_r']:.3f} fails the 1.30 gate. With WR = {filtered_wr:.1f}% "
                  f"and a fixed planned R:R of 1.4, the upper bound on R-PF for any "
                  f"selector at this WR is {(filtered_wr/(100-filtered_wr)) * 1.4:.2f}, "
                  f"so no decision threshold can rescue this fold mix.")
        md.append(f"- $-PF = {gate['pf_dollars']:.3f} passes — the model happens to pick "
                  f"larger-magnitude wins (higher-ATR conditions) — but that does NOT "
                  f"compensate for the WR drop in R units, which is what the ship gate "
                  f"is intentionally measuring.")
        md.append("")
        md.append("**Step 6 verdict: meta-labeling MACD as-configured does not produce "
                  "a shippable artifact.** Possible recovery paths, in order of "
                  "seriousness:")
        md.append("  1. **Path B (regime-stratified retrain)** — split corpus by "
                  "volatility / trend regime and train one meta-labeler per regime. "
                  "Already on the Phase 9 follow-up list.")
        md.append("  2. **Richer feature set** — Phase 7 Step 4 used 20 features. "
                  "Add interaction terms, lagged indicators, or context features "
                  "(news_nearby, time-of-day-of-week interactions).")
        md.append("  3. **Tighten decision threshold** — at proba ≥ 0.55 the recall is "
                  f"{rec_mean:.2f}; raising to 0.60+ trades volume for precision but "
                  "given AUC ≈ 0.50 there's no monotone improvement to exploit.")
        md.append("  4. **Accept the edge isn't there** — MACD's primary signal may be "
                  "the entire edge, and a secondary classifier on top is just noise. "
                  "In that case Phase 7 ship gate routes through a different mechanism "
                  "(e.g., regime filter as a hard rule, not a learned model).")
    md.append("")
    md.append("Compare to the Phase 5 prototype (`docs/research/meta_labeler_prototype.md`): "
              "this run uses purged_cv with embargo (stricter), Phase 7 Step 4's feature "
              "ranking (newer), and projects the dual ship-gate (closer to live truth). "
              "The Phase 5 prototype reported a positive lift at 0.55 threshold using "
              "non-purged K-fold; that lift did not survive purging — consistent with "
              "label leakage being the source of the prototype's apparent edge.\n")

    md.append("## Calibration notes (2026-05-07 unit-bug fix)\n")
    md.append("First run reported R-PF = 2.10 (PASS). Investigation found the "
              "`realized_r_for_taken` helper used `rr_ratio` from "
              "`primary_signals.parquet` directly, but that column is in "
              "**ATR units** (WIN ≈ +3.5, LOSS ≈ −2.5 = TP/SL multipliers), not "
              "**R units**. Correct conversion is `rr_ratio / SL_ATR_MULTIPLIER`, "
              "which gives WIN = +1.4R, LOSS = −1.0R as expected. The fix is in "
              "the script header (`SL_ATR_MULTIPLIER = 2.5`). Future strategies "
              "with different SL multipliers (e.g., RSI Step 7) need the same "
              "treatment with their own multiplier.\n")

    md.append("## Next\n")
    md.append("- **Step 7** — same pipeline against the 329 RSI signals.")
    md.append("- **Step 8** — refactor `ml_filtered_strategy` + engine to load this "
              "artifact and gate orders on `proba >= decision_threshold`.")
    md.append("- **Step 10** — full 3-year backtest with the meta-labeler in the loop.")
    md.append("- **Step 11** — ship gate (Jun 8).\n")

    md.append("## Cross-references\n")
    md.append("- `ml/purged_cv.py` — Phase 7 Step 2")
    md.append("- `docs/research/phase7_step4_feature_importance.md` — feature shortlist")
    md.append("- `analysis/rr_calculator.py::phase7_ship_gate` — gate definition")
    md.append("- `data/improvements.db` table `meta_labeler_runs` — historical runs")

    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"  ✓ report: {REPORT_OUT}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
