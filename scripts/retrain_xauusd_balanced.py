"""AI-001 Path A: retrain XAUUSD ml_direct model with class-balanced sample weights.

Hypothesis: the current XAUUSD model (trained 2026-03-26) collapsed
onto SELL because LightGBM was given no class_weight / sample_weight,
so the multi_logloss objective took the easy wins on a regime where
SELL signals clustered cleanly. Training data has 5,311 BUY vs 4,632
SELL — favouring BUY by 14% — yet the model predicts SELL 6.6× more
often than BUY (per-class recall 76.7% vs 10.9%).

This script reruns the same training pipeline as ml/market_learner.py
with one minimum-impact change: sample weights derived from
sklearn.utils.class_weight.compute_class_weight('balanced', ...). All
other params, the train/val/test split, and the feature pipeline are
unchanged.

Output:
  models/market_learner/XAUUSD_model_balanced.pkl    new model (NOT a
                                                     replacement — sits
                                                     alongside the old)
  models/market_learner/XAUUSD_metrics_balanced.json new metrics
  docs/research/ai001_retrain_balanced_report.md     side-by-side
                                                     comparison vs old

Does NOT overwrite the deployed XAUUSD_model.pkl. Does NOT touch any
config or the engine. The deployment decision (whether the new model
replaces the old) is the project lead's call after reviewing the
report.

Re-runnable. Idempotent (overwrites its own output files only).
"""
from __future__ import annotations

import json
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

import numpy as np
import pandas as pd
from loguru import logger

import lightgbm as lgb
from sklearn.utils.class_weight import compute_class_weight

from ml.market_learner import (
    FORWARD_HOURS,
    MIN_MOVE_PIPS,
    create_labels,
    evaluate_model,
    get_feature_importance,
    load_data,
    split_data,
)
from features.ml.feature_engine import build_features, get_feature_columns

SYMBOL = "XAUUSD"
MODEL_DIR = Path("models/market_learner")
DOCS_DIR = Path("docs/research")
NEW_MODEL_PATH = MODEL_DIR / f"{SYMBOL}_model_balanced.pkl"
NEW_METRICS_PATH = MODEL_DIR / f"{SYMBOL}_metrics_balanced.json"
OLD_MODEL_PATH = MODEL_DIR / f"{SYMBOL}_model.pkl"
REPORT_PATH = DOCS_DIR / "ai001_retrain_balanced_report.md"


def train_model_balanced(train_df, val_df, feature_cols):
    """Same as ml.market_learner.train_model but with class-balanced
    sample weights. Returns the trained LightGBM Booster."""
    label_map = {-1: 0, 0: 1, 1: 2}  # SELL=0, NO_TRADE=1, BUY=2
    y_train = train_df["label"].map(label_map).values
    y_val = val_df["label"].map(label_map).values
    X_train = train_df[feature_cols].values
    X_val = val_df[feature_cols].values

    classes = np.array([0, 1, 2])
    cw = compute_class_weight("balanced", classes=classes, y=y_train)
    weight_map = dict(zip(classes, cw))
    sample_weight = np.array([weight_map[label] for label in y_train])

    logger.info(
        f"[{SYMBOL}] class weights derived: "
        f"SELL={cw[0]:.3f}  NO_TRADE={cw[1]:.3f}  BUY={cw[2]:.3f}"
    )

    train_data = lgb.Dataset(
        X_train, label=y_train, weight=sample_weight, feature_name=feature_cols,
    )
    val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

    params = {
        "objective": "multiclass",
        "num_class": 3,
        "metric": "multi_logloss",
        "learning_rate": 0.05,
        "num_leaves": 63,
        "max_depth": 8,
        "min_child_samples": 50,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 0.1,
        "n_jobs": -1,
        "verbose": -1,
        "seed": 42,
    }
    callbacks = [
        lgb.early_stopping(50, verbose=False),
        lgb.log_evaluation(0),
    ]

    model = lgb.train(
        params,
        train_data,
        num_boost_round=1000,
        valid_sets=[val_data],
        callbacks=callbacks,
    )
    logger.info(f"[{SYMBOL}] best iteration: {model.best_iteration}")
    return model


def compare_on_test_bars(old_model, new_model, test_df, feature_cols, top_n=200):
    """Predict with both models on the most-recent test bars; return
    summary stats of the prediction-class distributions.

    Used to verify whether the rebalanced model actually produces BUY
    predictions where the original model never did."""
    test_recent = test_df.tail(top_n)
    X = test_recent[feature_cols].values
    proba_old = old_model.predict(X)
    proba_new = new_model.predict(X)

    pred_old = proba_old.argmax(axis=1)  # 0=SELL, 1=NO, 2=BUY
    pred_new = proba_new.argmax(axis=1)

    return {
        "n_bars": len(test_recent),
        "old": {
            "p_buy_max":  float(proba_old[:, 2].max()),
            "p_buy_mean": float(proba_old[:, 2].mean()),
            "p_sell_max": float(proba_old[:, 0].max()),
            "p_sell_mean": float(proba_old[:, 0].mean()),
            "n_sell": int((pred_old == 0).sum()),
            "n_no":   int((pred_old == 1).sum()),
            "n_buy":  int((pred_old == 2).sum()),
        },
        "new": {
            "p_buy_max":  float(proba_new[:, 2].max()),
            "p_buy_mean": float(proba_new[:, 2].mean()),
            "p_sell_max": float(proba_new[:, 0].max()),
            "p_sell_mean": float(proba_new[:, 0].mean()),
            "n_sell": int((pred_new == 0).sum()),
            "n_no":   int((pred_new == 1).sum()),
            "n_buy":  int((pred_new == 2).sum()),
        },
    }


def render_report(meta_old: dict, metrics_new: dict, comparison: dict, *,
                  old_top: list, new_top: list) -> str:
    """Side-by-side markdown report."""
    today = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    old_m = meta_old["metrics"]
    lines = []
    lines.append(f"# AI-001 Path A — XAUUSD `class_weight='balanced'` retraining\n")
    lines.append(f"**Date:** {today}  ")
    lines.append(f"**Re-runnable:** `python scripts/retrain_xauusd_balanced.py`  ")
    lines.append(f"**Outputs:** `{NEW_MODEL_PATH}`, `{NEW_METRICS_PATH}`, this file.\n")

    lines.append("## What this commit does\n")
    lines.append(
        "Reruns the existing XAUUSD training pipeline (`ml/market_learner.py`) "
        "with one minimum-impact change: sample weights derived from "
        "`sklearn.utils.class_weight.compute_class_weight('balanced', ...)`. "
        "All other params, the train/val/test split, and the feature "
        "pipeline are unchanged. The new model is saved alongside the old "
        "(NOT overwriting); the engine still loads the old model. "
        "Deployment is the project lead's decision after reviewing this "
        "report.\n"
    )

    lines.append("## Per-class metrics (test set, walk-forward split)\n")
    lines.append("| Class | Old recall | **New recall** | Old precision | **New precision** |")
    lines.append("|---|---:|---:|---:|---:|")
    new_m = metrics_new
    for cls in ("SELL", "NO_TRADE", "BUY"):
        old_r = old_m[cls]["recall"]
        new_r = new_m[cls]["recall"]
        old_p = old_m[cls]["precision"]
        new_p = new_m[cls]["precision"]
        marker = " ← " + ("✓" if new_r > old_r else "✗") if cls == "BUY" else ""
        lines.append(
            f"| {cls} | {old_r:.3f} | **{new_r:.3f}** | "
            f"{old_p:.3f} | **{new_p:.3f}** |{marker}"
        )
    lines.append("")
    lines.append(f"Overall accuracy: old **{old_m['overall_accuracy']:.3f}**, "
                 f"new **{new_m['overall_accuracy']:.3f}**.\n")

    lines.append("## Prediction-class distribution on recent test bars\n")
    c = comparison
    lines.append(f"On the most recent **{c['n_bars']}** test bars:\n")
    lines.append("| Metric | Old | **New** |")
    lines.append("|---|---:|---:|")
    lines.append(f"| P(BUY) max | {c['old']['p_buy_max']:.3f} | **{c['new']['p_buy_max']:.3f}** |")
    lines.append(f"| P(BUY) mean | {c['old']['p_buy_mean']:.3f} | **{c['new']['p_buy_mean']:.3f}** |")
    lines.append(f"| P(SELL) max | {c['old']['p_sell_max']:.3f} | **{c['new']['p_sell_max']:.3f}** |")
    lines.append(f"| P(SELL) mean | {c['old']['p_sell_mean']:.3f} | **{c['new']['p_sell_mean']:.3f}** |")
    lines.append(f"| Predicted SELL | {c['old']['n_sell']} | **{c['new']['n_sell']}** |")
    lines.append(f"| Predicted NO_TRADE | {c['old']['n_no']} | **{c['new']['n_no']}** |")
    lines.append(f"| Predicted BUY | {c['old']['n_buy']} | **{c['new']['n_buy']}** |\n")

    if c['new']['n_buy'] == 0:
        lines.append(
            "**Verdict: PATH A ALONE INSUFFICIENT.** Even with class-balanced "
            "sample weights, the new model does not produce BUY predictions "
            "on recent bars. The bias is deeper than class weighting alone "
            "can fix — recommend escalating to **Path B** (regime-stratified "
            "retraining with curated up-and-down gold periods).\n"
        )
    elif c['new']['n_buy'] < 0.10 * c['n_bars']:
        lines.append(
            "**Verdict: MARGINAL IMPROVEMENT.** The new model produces BUY "
            "predictions but at very low frequency. May be acceptable if "
            "the precision is high; otherwise consider Path B.\n"
        )
    else:
        lines.append(
            "**Verdict: PATH A WORKS.** The new model produces BUY "
            "predictions at a meaningful rate. Next step: validate on "
            "AI-005's OOS holdout before deployment, and review whether "
            "the `class_weight='balanced'` change should be folded into "
            "ml/market_learner.py for all symbols.\n"
        )

    lines.append("## Top features (new model)\n")
    if new_top:
        for i, (name, score) in enumerate(new_top[:10], 1):
            lines.append(f"- {i}. `{name}` (importance={score:.4f})")
        lines.append("")
    if old_top:
        lines.append("## Top features (old model, for comparison)\n")
        for i, (name, score) in enumerate(old_top[:10], 1):
            lines.append(f"- {i}. `{name}` (importance={score:.4f})")
        lines.append("")

    lines.append("## What this does NOT do\n")
    lines.append(
        "- Deploy the new model. The engine still loads `XAUUSD_model.pkl`. "
        "Switching requires the project lead to either rename files, "
        "update the loader path, or add a config flag.\n"
        "- Lift the `ml_direct/XAUUSD` blacklist. That decision is "
        "downstream of deployment + AI-005-style holdout validation.\n"
        "- Address regime balance. Path A treats the issue as a class "
        "weighting problem; if the gold regime in the training window "
        "is the deeper cause, **Path B** (time-stratified retraining "
        "across multiple regimes) is the correct fix.\n"
    )

    lines.append("## Cross-references\n")
    lines.append("- `docs/research/ai001_zero_buy_root_cause.md` — diagnostic phase\n")
    lines.append("- `docs/research/ai005_holdout_validation.md` — OOS holdout for any deployment validation\n")
    lines.append("- `ml/market_learner.py` — original training pipeline\n")
    lines.append(f"- `{OLD_MODEL_PATH}` vs `{NEW_MODEL_PATH}` — side-by-side artefacts\n")
    return "\n".join(lines)


def main() -> int:
    t0 = time.time()
    logger.info(f"[{SYMBOL}] AI-001 Path A retraining begins")

    # 1. Load data + labels + features
    df = load_data(SYMBOL)
    if df.empty:
        logger.error(f"[{SYMBOL}] no data found")
        return 1
    df = create_labels(df, SYMBOL)
    df = build_features(df, dropna=True)
    feature_cols = [c for c in get_feature_columns(df)]
    df = df.dropna(subset=feature_cols + ["label"]).reset_index(drop=True)

    # 2. Walk-forward split
    train_df, val_df, test_df = split_data(df)

    # 3. Train balanced
    model = train_model_balanced(train_df, val_df, feature_cols)

    # 4. Evaluate on the same test set as the original
    new_metrics = evaluate_model(SYMBOL, model, test_df, feature_cols)

    # 5. Save new model + metrics
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "symbol": SYMBOL,
        "timeframe": "H1",
        "forward_hours": FORWARD_HOURS,
        "min_move": MIN_MOVE_PIPS.get(SYMBOL),
        "feature_cols": feature_cols,
        "train_samples": len(train_df),
        "val_samples": len(val_df),
        "test_samples": len(test_df),
        "metrics": new_metrics,
        "trained_at": pd.Timestamp.utcnow().isoformat(),
        "best_iteration": model.best_iteration,
        "training_method": "class_weight_balanced (AI-001 Path A)",
    }
    new_top = get_feature_importance(model, feature_cols, top_n=20)
    meta["top_features"] = new_top

    # JSON-serialisable copy of metrics
    def _to_jsonable(obj):
        if isinstance(obj, dict):
            return {k: _to_jsonable(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_to_jsonable(v) for v in obj]
        if isinstance(obj, (np.floating, np.integer)):
            return obj.item()
        return obj

    with open(NEW_MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "meta": meta}, f)
    with open(NEW_METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(_to_jsonable(meta), f, indent=2, ensure_ascii=False)

    logger.info(f"[{SYMBOL}] new model: {NEW_MODEL_PATH}")
    logger.info(f"[{SYMBOL}] new metrics: {NEW_METRICS_PATH}")

    # 6. Side-by-side comparison vs old model
    with open(OLD_MODEL_PATH, "rb") as f:
        old_data = pickle.load(f)
    old_model = old_data["model"]
    old_meta = old_data["meta"]
    # Use old model's feature_cols if they differ; align gracefully
    old_features = old_meta.get("feature_cols", feature_cols)
    common = [c for c in feature_cols if c in old_features]
    if len(common) < len(feature_cols):
        logger.warning(
            f"[{SYMBOL}] feature-column mismatch — using "
            f"{len(common)}/{len(feature_cols)} common cols for comparison"
        )

    # Predict with both models on test_df recent bars
    test_recent = test_df.tail(200)
    proba_old = old_model.predict(test_recent[old_features].values)
    proba_new = model.predict(test_recent[feature_cols].values)
    comparison = {
        "n_bars": len(test_recent),
        "old": {
            "p_buy_max":  float(proba_old[:, 2].max()),
            "p_buy_mean": float(proba_old[:, 2].mean()),
            "p_sell_max": float(proba_old[:, 0].max()),
            "p_sell_mean": float(proba_old[:, 0].mean()),
            "n_sell": int((proba_old.argmax(axis=1) == 0).sum()),
            "n_no":   int((proba_old.argmax(axis=1) == 1).sum()),
            "n_buy":  int((proba_old.argmax(axis=1) == 2).sum()),
        },
        "new": {
            "p_buy_max":  float(proba_new[:, 2].max()),
            "p_buy_mean": float(proba_new[:, 2].mean()),
            "p_sell_max": float(proba_new[:, 0].max()),
            "p_sell_mean": float(proba_new[:, 0].mean()),
            "n_sell": int((proba_new.argmax(axis=1) == 0).sum()),
            "n_no":   int((proba_new.argmax(axis=1) == 1).sum()),
            "n_buy":  int((proba_new.argmax(axis=1) == 2).sum()),
        },
    }

    # 7. Render report
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    old_top = old_meta.get("top_features") or []
    report = render_report(old_meta, new_metrics, comparison,
                            old_top=old_top, new_top=new_top)
    REPORT_PATH.write_text(report, encoding="utf-8")
    logger.info(f"[{SYMBOL}] report: {REPORT_PATH}")
    logger.info(f"[{SYMBOL}] elapsed: {time.time() - t0:.1f}s")

    # 8. Print headline diff for the operator
    print()
    print("=" * 78)
    print(" AI-001 Path A — Retrain Comparison Headline")
    print("=" * 78)
    print(f"  BUY recall:  old {old_meta['metrics']['BUY']['recall']:.1%}  "
          f"-> new {new_metrics['BUY']['recall']:.1%}")
    print(f"  SELL recall: old {old_meta['metrics']['SELL']['recall']:.1%}  "
          f"-> new {new_metrics['SELL']['recall']:.1%}")
    print(f"  Overall:     old {old_meta['metrics']['overall_accuracy']:.1%}  "
          f"-> new {new_metrics['overall_accuracy']:.1%}")
    print(f"  P(BUY) max on recent 200 test bars:")
    print(f"    old: {comparison['old']['p_buy_max']:.3f}")
    print(f"    new: {comparison['new']['p_buy_max']:.3f}")
    print(f"  Predicted BUYs on recent 200 test bars:")
    print(f"    old: {comparison['old']['n_buy']} / 200")
    print(f"    new: {comparison['new']['n_buy']} / 200")
    print()
    print(f"  Full report:    {REPORT_PATH}")
    print(f"  Engine still uses: {OLD_MODEL_PATH} (NOT replaced)")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
