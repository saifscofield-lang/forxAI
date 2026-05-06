"""Phase 7 Step 4: feature-importance run on historical data.

Uses the modules shipped earlier this week:
  - features.labels.triple_barrier (Step 1) for labels
  - features.importance.feature_selector (Step 5) for MDI/SFI/PCA
  - ml.purged_cv (Step 2) is used by SFI internally (via the model_factory
    pattern; SFI internally uses sklearn cross_val_score for simplicity)

Loads H1 bars for the 6 v3 symbols, builds features via the existing
features.ml.feature_engine.build_features, generates triple-barrier
labels per symbol, concatenates, trains a single LightGBM Booster on
the unified data, then ranks features via:

  - MDI from the trained Booster (cheap, gain-based)
  - SFI on the top-30 MDI candidates (one model per feature; expensive
    on all 80+ features, so we cull to a reasonable shortlist first)
  - PCA on the standardised feature matrix to gauge effective
    dimensionality

Output:
  artifacts/phase7_step4_feature_ranking_<date>.csv
  docs/research/phase7_step4_feature_importance.md

Re-runnable. Read-only against trading data files. Produces no model
artifact (the trained Booster is for ranking, not deployment)."""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, ".")

import numpy as np
import pandas as pd
from loguru import logger

import lightgbm as lgb

from features.ml.feature_engine import build_features, get_feature_columns
from features.labels.triple_barrier import label_events
from features.importance.feature_selector import (
    apply_pca,
    combined_rank,
    compute_mdi,
    compute_sfi,
    pca_components_to_keep,
    top_n_features,
)

V3_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "AUDUSD", "USDCHF"]
TIMEFRAME = "H1"
RAW_DIR = Path("data/raw")
ARTIFACTS_DIR = Path("artifacts")
DOCS_DIR = Path("docs/research")

# Triple-barrier params — match the live engine's typical SL/TP design
TP_ATR_MULT = 2.0
SL_ATR_MULT = 1.0
MAX_HOLD_BARS = 24  # 1 trading day on H1

# How many features to keep for the SFI cross-check + final list
SFI_SHORTLIST = 30
TOP_N = 20

# History window — last N bars per symbol (avoid running on 60k bars per symbol)
WINDOW_BARS = 5000  # ~7 months of H1 data per symbol → 30k total across 6


def load_symbol_bars(symbol: str, timeframe: str = TIMEFRAME) -> pd.DataFrame:
    p = RAW_DIR / symbol / f"{timeframe}.parquet"
    if not p.exists():
        logger.warning(f"[{symbol}] {p} not found")
        return pd.DataFrame()
    df = pd.read_parquet(p)
    if "time" in df.columns:
        df = df.set_index(pd.to_datetime(df["time"]))
    return df.sort_index()


def build_symbol_dataset(symbol: str) -> Optional[pd.DataFrame]:
    """Load + feature-engineer + label one symbol's recent bars.

    Returns a DataFrame with feature columns + 'label' + 'symbol'
    columns, or None on failure."""
    bars = load_symbol_bars(symbol)
    if bars.empty:
        return None
    bars = bars.tail(WINDOW_BARS)

    # Feature engineering (existing pipeline)
    feat = build_features(bars, dropna=False)

    # Build triple-barrier labels using ATR at entry as the barrier scale.
    # We use atr_14 if present (added by build_features), else atr_7.
    atr_col = "atr_14" if "atr_14" in feat.columns else "atr_7" if "atr_7" in feat.columns else None
    if atr_col is None:
        logger.warning(f"[{symbol}] no ATR column found; skipping")
        return None

    # Each bar acts as a potential entry. We label each non-NaN row.
    events = pd.DataFrame({
        "side": "BUY",  # one direction; SELL would mirror — for ranking
                         # we use BUY to keep things simple. The features
                         # that matter for direction are the same either way
                         # for tree-based models.
        "price": feat["close"],
        "atr": feat[atr_col],
    }, index=feat.index)
    events = events.dropna(subset=["price", "atr"])

    labelled = label_events(
        events, feat[["high", "low", "close"]],
        tp_atr_mult=TP_ATR_MULT,
        sl_atr_mult=SL_ATR_MULT,
        max_hold_bars=MAX_HOLD_BARS,
    )
    # Map +1/-1/0 to a binary "was profitable" target — meta-labeler-style.
    # 0 (timeout) treated as not profitable for the importance ranking.
    labels = (labelled["label"] == 1).astype(int)
    feat = feat.loc[labels.index].copy()
    feat["label"] = labels.values
    feat["symbol"] = symbol
    return feat.dropna(subset=get_feature_columns(feat) + ["label"])


def assemble_unified_dataset(symbols: list) -> pd.DataFrame:
    parts = []
    for sym in symbols:
        d = build_symbol_dataset(sym)
        if d is None or d.empty:
            logger.warning(f"[{sym}] empty after labelling, skipped")
            continue
        logger.info(f"[{sym}] dataset: {len(d):,} labelled rows  "
                    f"(positive class: {(d['label']==1).sum()/len(d)*100:.1f}%)")
        parts.append(d)
    if not parts:
        raise RuntimeError("no symbols produced labelled data")
    df = pd.concat(parts, ignore_index=False).sort_index()
    return df


def train_unified_lightgbm(df: pd.DataFrame, feature_cols: list):
    """Train a binary LightGBM on the unified (multi-symbol) dataset.

    Used purely as a feature-ranking model. Not deployed."""
    X = df[feature_cols].values
    y = df["label"].values

    # Walk-forward split for validation: oldest 80% train, newest 20% val.
    n = len(df)
    n_train = int(n * 0.80)
    X_train, y_train = X[:n_train], y[:n_train]
    X_val, y_val = X[n_train:], y[n_train:]

    train_data = lgb.Dataset(X_train, label=y_train, feature_name=feature_cols)
    val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

    params = {
        "objective": "binary",
        "metric": "binary_logloss",
        "learning_rate": 0.05,
        "num_leaves": 63,
        "max_depth": 8,
        "min_child_samples": 100,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 0.1,
        "n_jobs": -1,
        "verbose": -1,
        "seed": 42,
    }
    callbacks = [
        lgb.early_stopping(30, verbose=False),
        lgb.log_evaluation(0),
    ]
    model = lgb.train(
        params, train_data, num_boost_round=300,
        valid_sets=[val_data], callbacks=callbacks,
    )
    return model


def render_report(
    symbols_used: list,
    df: pd.DataFrame,
    feature_cols: list,
    mdi: pd.Series,
    sfi: pd.DataFrame,
    pca_n95: int,
    final_top20: list,
    elapsed_sec: float,
) -> str:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    lines = []
    lines.append("# Phase 7 Step 4 — Feature Importance Run\n")
    lines.append(f"**Date:** {today}  ")
    lines.append(f"**Re-runnable:** `python scripts/run_feature_importance.py`  ")
    lines.append(f"**Output:** the **20 final features** below + "
                 f"`artifacts/phase7_step4_feature_ranking_{today}.csv`\n")

    lines.append("## Pipeline\n")
    lines.append(f"- Symbols: {', '.join(symbols_used)} ({len(symbols_used)} of 6 v3 instruments)")
    lines.append(f"- Timeframe: {TIMEFRAME}  ·  bars per symbol: {WINDOW_BARS:,}")
    lines.append(f"- Triple-barrier labels: TP={TP_ATR_MULT}×ATR, SL={SL_ATR_MULT}×ATR, hold={MAX_HOLD_BARS} bars")
    lines.append(f"- Total labelled rows after dropna: **{len(df):,}**")
    lines.append(f"- Positive class share: {(df['label']==1).sum()/len(df)*100:.1f}%")
    lines.append(f"- Total features evaluated: **{len(feature_cols)}**")
    lines.append(f"- Wall time: {elapsed_sec:.1f}s\n")

    lines.append("## MDI top 20 (LightGBM gain)\n")
    lines.append("| Rank | Feature | MDI |")
    lines.append("|---:|---|---:|")
    for i, (feat, val) in enumerate(mdi.head(20).items(), 1):
        lines.append(f"| {i} | `{feat}` | {val:.4f} |")
    lines.append("")

    lines.append(f"## SFI on top {SFI_SHORTLIST} MDI candidates (3-fold CV accuracy)\n")
    lines.append(f"SFI evaluates each feature in isolation — cross-checks MDI's "
                 f"susceptibility to the substitution effect. "
                 f"Mean accuracy across {SFI_SHORTLIST} features: "
                 f"**{sfi['mean_score'].mean():.3f}** "
                 f"(range {sfi['mean_score'].min():.3f}–{sfi['mean_score'].max():.3f}).\n")
    lines.append("Top 10 by SFI:\n")
    lines.append("| Rank | Feature | Mean accuracy | Std |")
    lines.append("|---:|---|---:|---:|")
    for i, (feat, row) in enumerate(sfi.head(10).iterrows(), 1):
        lines.append(f"| {i} | `{feat}` | {row['mean_score']:.4f} | ±{row['std_score']:.4f} |")
    lines.append("")

    lines.append("## PCA dimensionality\n")
    lines.append(
        f"With standardised features and 95% explained-variance threshold, "
        f"**{pca_n95}** principal components capture 95% of the variance "
        f"out of {len(feature_cols)} original features. Effective dimensionality "
        f"≈ {pca_n95 / len(feature_cols) * 100:.0f}% of the raw feature count "
        f"— some features carry redundant information.\n"
    )

    lines.append("## Final 20 features (combined MDI + SFI rank)\n")
    lines.append(
        "Combined rank: each feature's MDI rank and SFI rank are averaged "
        "(equal weights), and the smallest combined rank wins. Features in "
        "both rankings.\n"
    )
    lines.append("| Rank | Feature |")
    lines.append("|---:|---|")
    for i, feat in enumerate(final_top20, 1):
        lines.append(f"| {i} | `{feat}` |")
    lines.append("")

    lines.append("## Methodology notes\n")
    lines.append(
        "- **Single direction (BUY) for ranking.** The triple-barrier labels are\n"
        "  computed for BUY events. Tree-based models extract the same\n"
        "  feature-importance information regardless of direction; SELL would\n"
        "  produce a mirrored ranking. The Phase 7 meta-labeler (Step 6) will\n"
        "  use this feature set for both directions.\n"
        "- **Multi-symbol unified training.** Features are computed per symbol\n"
        "  (so e.g. RSI is symbol-agnostic in interpretation) and the model\n"
        "  learns which features generalise. A symbol-stratified version would\n"
        "  produce per-symbol rankings; that's a separate analysis.\n"
        "- **Walk-forward 80/20 split** for the LightGBM training validation.\n"
        "  No purging applied here because we're ranking, not evaluating\n"
        "  generalisation. Phase 7 Step 2's purged_cv would apply for any\n"
        "  outcome prediction we run on this feature set later.\n"
        "- **MDI uses gain, not split-count.** Per LightGBM convention; gain\n"
        "  is more interpretable as 'feature contribution to loss reduction'.\n"
    )

    lines.append("## What this does NOT decide\n")
    lines.append(
        "- Whether the meta-labeler should use these 20 features verbatim or\n"
        "  add interaction terms / regime indicators.\n"
        "- Whether the same feature set works for both BUY and SELL\n"
        "  directions in the meta-labeler.\n"
        "- The α / β / γ training-corpus choice (separate kickoff decision).\n"
    )

    lines.append("## Cross-references\n")
    lines.append("- `features/labels/triple_barrier.py` — Phase 7 Step 1\n")
    lines.append("- `ml/purged_cv.py` — Phase 7 Step 2\n")
    lines.append("- `features/importance/feature_selector.py` — Phase 7 Step 5\n")
    lines.append(f"- `artifacts/phase7_step4_feature_ranking_{today}.csv` — full per-feature ranking\n")

    return "\n".join(lines)


def main() -> int:
    t0 = time.time()
    logger.info("[step4] starting feature-importance run")

    # 1. Build unified dataset
    df = assemble_unified_dataset(V3_SYMBOLS)
    feature_cols = [c for c in get_feature_columns(df) if c not in ("symbol",)]
    logger.info(f"[step4] unified dataset: {len(df):,} rows × {len(feature_cols)} features")

    # 2. Train unified LightGBM
    model = train_unified_lightgbm(df, feature_cols)
    logger.info(f"[step4] LightGBM best iteration: {model.best_iteration}")

    # 3. MDI
    mdi = compute_mdi(model, feature_cols)
    logger.info(f"[step4] MDI computed; top feature: {mdi.index[0]}")

    # 4. SFI on top SFI_SHORTLIST MDI candidates
    sfi_features = top_n_features(mdi, SFI_SHORTLIST)
    logger.info(f"[step4] running SFI on top {SFI_SHORTLIST} MDI candidates...")
    from sklearn.tree import DecisionTreeClassifier
    sfi = compute_sfi(
        df[sfi_features], df["label"].values, sfi_features,
        model_factory=lambda: DecisionTreeClassifier(max_depth=4, random_state=42),
        cv_splits=3,  # 3 keeps SFI fast; 5 would be ~67% slower for marginal precision gain
    )
    logger.info(f"[step4] SFI computed")

    # 5. PCA dimensionality
    pca_result = apply_pca(df[feature_cols], n_components=None)
    pca_n95 = pca_components_to_keep(pca_result, threshold=0.95)
    logger.info(f"[step4] PCA: {pca_n95} components for 95% variance "
                f"(of {len(feature_cols)})")

    # 6. Combined rank → top 20
    combined = combined_rank(mdi, sfi)
    final_top20 = list(combined.head(TOP_N).index)
    logger.info(f"[step4] final top {TOP_N}: {final_top20}")

    # 7. Save artifact + report
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    csv_path = ARTIFACTS_DIR / f"phase7_step4_feature_ranking_{today}.csv"

    out = pd.DataFrame({"feature": feature_cols})
    out["mdi"] = out["feature"].map(mdi)
    out["mdi_rank"] = out["mdi"].rank(ascending=False)
    out = out.merge(
        sfi[["mean_score", "std_score"]].rename(
            columns={"mean_score": "sfi_mean", "std_score": "sfi_std"}
        ),
        left_on="feature", right_index=True, how="left",
    )
    out["sfi_rank"] = out["sfi_mean"].rank(ascending=False)
    out["combined_rank"] = out["feature"].map(combined)
    out["in_final_top20"] = out["feature"].isin(final_top20)
    out = out.sort_values("combined_rank", na_position="last")
    out.to_csv(csv_path, index=False)

    elapsed = time.time() - t0
    report = render_report(
        symbols_used=V3_SYMBOLS,
        df=df, feature_cols=feature_cols,
        mdi=mdi, sfi=sfi, pca_n95=pca_n95,
        final_top20=final_top20, elapsed_sec=elapsed,
    )
    report_path = DOCS_DIR / "phase7_step4_feature_importance.md"
    report_path.write_text(report, encoding="utf-8")

    print()
    print("=" * 78)
    print(" Phase 7 Step 4 — Feature Importance Run")
    print("=" * 78)
    print(f"  unified dataset:       {len(df):,} rows × {len(feature_cols)} features")
    print(f"  PCA 95% threshold:     {pca_n95} components")
    print(f"  final top {TOP_N}:")
    for i, feat in enumerate(final_top20, 1):
        print(f"    {i:>2}. {feat}")
    print(f"  report:    {report_path}")
    print(f"  artifact:  {csv_path}")
    print(f"  elapsed:   {elapsed:.1f}s")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
