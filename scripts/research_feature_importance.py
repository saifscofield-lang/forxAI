"""
Phase 5 Step 6 — Feature Importance Analysis (research only, freeze-safe)

Goal: shrink the 82-feature set down to a 15-25 feature shortlist for the
v3.0 Meta-Labeler, using the methods from Lopez de Prado Ch. 8:
  - MDI (Mean Decrease Impurity) — fast, biased toward high-cardinality
  - SFI (Single Feature Importance) — slow, unbiased per-feature score
  - PCA — detect multicollinearity and feature redundancy
  - Spearman correlation cluster — group near-duplicate features

Inputs:  H1 OHLCV from data/trading.db, 5 pairs, 2018-01-01 onward
Labels:  triple_barrier (existing label_engine.py — already aligned with v3.0)
Outputs: docs/research/feature_importance_report.md
         docs/research/feature_importance_data.csv (per-feature scores)
         docs/research/feature_corr_heatmap.png

Does NOT touch any production code or models. Read-only on the DB.
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
warnings.filterwarnings("ignore")

import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score, TimeSeriesSplit

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from features.ml.feature_engine import build_features, get_feature_columns
from features.ml.label_engine import add_labels, label_distribution

# ───────────────────────────── CONFIG ─────────────────────────────
PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF"]   # plan's 5 pairs
TIMEFRAME = "H1"
START_DATE = "2020-01-01"          # 6+ years to cover multiple regimes
END_DATE = "2026-04-01"
LABEL_HORIZON = 24                  # 24 H1 bars = 1 trading day
ATR_SL_MULT = 1.5                   # matches plan §5.2
ATR_TP_MULT = 2.5
RF_TREES = 200
RF_DEPTH = 6                        # shallow for speed + interpretability
SFI_CV_SPLITS = 3                   # SFI is N_features × N_splits trainings
SFI_SAMPLE_PER_PAIR = 8000          # cap to keep SFI tractable
N_TARGET = 20                       # final shortlist size

OUT_DIR = Path("docs/research")
OUT_DIR.mkdir(parents=True, exist_ok=True)

DB = "data/trading.db"


# ───────────────────────────── HELPERS ─────────────────────────────
def load_h1(symbol: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB)
    df = pd.read_sql(
        """SELECT time, open, high, low, close, volume, spread
           FROM ohlcv_bars
           WHERE symbol = ? AND timeframe = 'H1'
             AND time >= ? AND time < ?
           ORDER BY time""",
        conn,
        params=(symbol, START_DATE, END_DATE),
    )
    conn.close()
    df["time"] = pd.to_datetime(df["time"])
    return df


def build_pair_dataset(symbol: str) -> pd.DataFrame:
    raw = load_h1(symbol)
    if raw.empty:
        return raw
    feat = build_features(raw, dropna=False)
    labeled = add_labels(
        feat,
        horizon=LABEL_HORIZON,
        method="triple_barrier",
        atr_sl_mult=ATR_SL_MULT,
        atr_tp_mult=ATR_TP_MULT,
    )
    labeled["symbol"] = symbol
    # Drop HOLD rows for binary BUY/SELL importance
    labeled = labeled[labeled["label"] != 0].copy()
    labeled["label_bin"] = (labeled["label"] == 1).astype(int)
    labeled = labeled.dropna()
    return labeled


def compute_mdi(X: pd.DataFrame, y: pd.Series, features: list) -> pd.Series:
    rf = RandomForestClassifier(
        n_estimators=RF_TREES,
        max_depth=RF_DEPTH,
        min_samples_leaf=50,
        n_jobs=-1,
        random_state=42,
        class_weight="balanced",
    )
    rf.fit(X[features], y)
    return pd.Series(rf.feature_importances_, index=features).sort_values(ascending=False)


def compute_sfi(X: pd.DataFrame, y: pd.Series, features: list) -> pd.Series:
    """Single Feature Importance: train one tiny RF per feature, score by CV AUC."""
    cv = TimeSeriesSplit(n_splits=SFI_CV_SPLITS)
    scores = {}
    for f in features:
        try:
            rf = RandomForestClassifier(
                n_estimators=50, max_depth=4, min_samples_leaf=50,
                n_jobs=-1, random_state=42, class_weight="balanced",
            )
            s = cross_val_score(rf, X[[f]], y, cv=cv, scoring="roc_auc", n_jobs=-1)
            scores[f] = float(np.mean(s))
        except Exception:
            scores[f] = np.nan
    return pd.Series(scores).sort_values(ascending=False)


def compute_pca(X: pd.DataFrame, features: list) -> tuple[pd.DataFrame, pd.Series]:
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X[features].fillna(0))
    pca = PCA(n_components=min(20, len(features)))
    pca.fit(Xs)
    explained = pd.Series(pca.explained_variance_ratio_,
                          index=[f"PC{i+1}" for i in range(pca.n_components_)])
    loadings = pd.DataFrame(
        pca.components_.T, index=features,
        columns=[f"PC{i+1}" for i in range(pca.n_components_)],
    )
    return loadings, explained


def cluster_correlated(X: pd.DataFrame, features: list, threshold: float = 0.85) -> dict:
    corr = X[features].corr(method="spearman").abs()
    clusters = {}
    seen = set()
    for f in features:
        if f in seen:
            continue
        related = corr.index[corr[f] >= threshold].tolist()
        related = [r for r in related if r != f and r not in seen]
        if related:
            clusters[f] = related
            seen.update(related)
        seen.add(f)
    return clusters


# ───────────────────────────── MAIN ─────────────────────────────
def main():
    print(f"\n{'='*70}")
    print(f"  Phase 5 Step 6 — Feature Importance Analysis")
    print(f"  v3.0 Meta-Labeler shortlist generation")
    print(f"  Run: {datetime.now().isoformat(timespec='seconds')}")
    print(f"{'='*70}\n")

    # 1. Build per-pair datasets
    print("▶ Building feature × label dataset per pair...")
    frames = []
    for sym in PAIRS:
        df = build_pair_dataset(sym)
        if df.empty:
            print(f"  {sym:<8} EMPTY")
            continue
        # Sample to keep total tractable
        if len(df) > SFI_SAMPLE_PER_PAIR:
            df = df.sample(n=SFI_SAMPLE_PER_PAIR, random_state=42).sort_values("time")
        print(f"  {sym:<8} {len(df):>6,} labeled rows  "
              f"({df['time'].min().date()} → {df['time'].max().date()})")
        frames.append(df)

    if not frames:
        print("ERROR: no data — abort")
        return

    full = pd.concat(frames, ignore_index=True)
    print(f"\n  Combined: {len(full):,} rows across {len(frames)} pairs")

    features = [c for c in get_feature_columns(full)
                if c not in ("symbol", "label", "label_bin", "spread")]
    # Keep only numeric
    features = [c for c in features if np.issubdtype(full[c].dtype, np.number)]
    print(f"  Features available: {len(features)}")

    label_dist = full["label_bin"].value_counts().to_dict()
    print(f"  Label balance: BUY={label_dist.get(1,0):,}  SELL={label_dist.get(0,0):,}")

    X = full[features].fillna(0).replace([np.inf, -np.inf], 0)
    y = full["label_bin"]

    # 2. MDI
    print("\n▶ Computing MDI (Mean Decrease Impurity)...")
    mdi = compute_mdi(X, y, features)
    print(f"  Top 10 by MDI:")
    for f, v in mdi.head(10).items():
        print(f"    {f:<32} {v:.4f}")

    # 3. SFI
    print(f"\n▶ Computing SFI (Single Feature Importance, AUC) — "
          f"this trains {len(features)} small models, ~2-5 min...")
    sfi = compute_sfi(X, y, features)
    print(f"  Top 10 by SFI:")
    for f, v in sfi.head(10).items():
        print(f"    {f:<32} AUC={v:.4f}")

    # 4. PCA
    print("\n▶ Computing PCA...")
    loadings, explained = compute_pca(X, features)
    cum_var = explained.cumsum()
    n_for_90 = int((cum_var >= 0.90).idxmax().replace("PC", "")) if (cum_var >= 0.90).any() else len(explained)
    print(f"  {n_for_90} components explain 90% of variance "
          f"({len(features)} original features)")
    print(f"  Top 5 PCs: {explained.head(5).round(3).to_dict()}")

    # 5. Correlation clusters
    print("\n▶ Clustering correlated features (Spearman > 0.85)...")
    clusters = cluster_correlated(X, features, threshold=0.85)
    print(f"  Found {len(clusters)} clusters of redundant features")
    for head, members in list(clusters.items())[:5]:
        print(f"    [{head}] ← {', '.join(members[:3])}{'...' if len(members) > 3 else ''}")

    # 6. Build consensus shortlist
    print(f"\n▶ Building consensus shortlist (target: {N_TARGET} features)...")

    # Normalized rank (lower = better)
    mdi_rank = mdi.rank(ascending=False)
    sfi_rank = (sfi - 0.5).abs().rank(ascending=False)  # SFI: distance from 0.5 AUC
    combined = pd.DataFrame({
        "mdi": mdi, "mdi_rank": mdi_rank,
        "sfi_auc": sfi, "sfi_rank": sfi_rank,
    })
    combined["consensus_rank"] = (combined["mdi_rank"] + combined["sfi_rank"]) / 2
    combined = combined.sort_values("consensus_rank")

    # Drop redundant: from each correlation cluster keep only the highest-ranked member
    drop = set()
    for head, members in clusters.items():
        group = [head] + members
        ranks = [(m, combined.loc[m, "consensus_rank"]) for m in group if m in combined.index]
        if not ranks:
            continue
        ranks.sort(key=lambda x: x[1])
        keeper = ranks[0][0]
        for m, _ in ranks[1:]:
            drop.add(m)

    shortlist = [f for f in combined.index if f not in drop][:N_TARGET]
    print(f"  Dropped {len(drop)} redundant features")
    print(f"  Final shortlist ({len(shortlist)} features):")
    for i, f in enumerate(shortlist, 1):
        row = combined.loc[f]
        print(f"    {i:>2}. {f:<32}  MDI={row['mdi']:.4f}  AUC={row['sfi_auc']:.4f}")

    # 7. Save outputs
    print(f"\n▶ Writing reports to {OUT_DIR}/...")

    combined.to_csv(OUT_DIR / "feature_importance_data.csv")
    print(f"  ✓ feature_importance_data.csv ({len(combined)} rows)")

    # Heatmap of top 25 features only
    top25 = combined.head(25).index.tolist()
    fig, ax = plt.subplots(figsize=(12, 10))
    corr_top = X[top25].corr(method="spearman")
    im = ax.imshow(corr_top, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(top25))); ax.set_yticks(range(len(top25)))
    ax.set_xticklabels(top25, rotation=90, fontsize=8)
    ax.set_yticklabels(top25, fontsize=8)
    fig.colorbar(im, ax=ax)
    ax.set_title("Spearman correlation — top 25 features")
    plt.tight_layout()
    plt.savefig(OUT_DIR / "feature_corr_heatmap.png", dpi=110)
    plt.close()
    print(f"  ✓ feature_corr_heatmap.png")

    # Markdown report
    md = []
    md.append(f"# Phase 5 Step 6 — Feature Importance Analysis\n")
    md.append(f"_Generated: {datetime.now().isoformat(timespec='seconds')}_  ")
    md.append(f"_Data: {len(full):,} labeled rows · {len(PAIRS)} pairs · "
              f"H1 · {START_DATE} → {END_DATE}_  ")
    md.append(f"_Label: triple-barrier · horizon={LABEL_HORIZON} bars · "
              f"SL/TP={ATR_SL_MULT}/{ATR_TP_MULT} ATR_\n")

    md.append("## Summary\n")
    md.append(f"- **Original features:** {len(features)}")
    md.append(f"- **Redundant (Spearman > 0.85) clusters dropped:** {len(drop)} features")
    md.append(f"- **Final shortlist:** {len(shortlist)} features")
    md.append(f"- **PCA:** {n_for_90} components explain 90% variance "
              f"(suggests {n_for_90}–{n_for_90+5} effective dimensions)\n")

    md.append("## Recommended shortlist for v3.0 Meta-Labeler\n")
    md.append("| # | Feature | MDI | SFI (AUC) | Consensus rank |")
    md.append("|---|---------|-----|-----------|----------------|")
    for i, f in enumerate(shortlist, 1):
        row = combined.loc[f]
        md.append(f"| {i} | `{f}` | {row['mdi']:.4f} | {row['sfi_auc']:.4f} | {row['consensus_rank']:.1f} |")

    md.append("\n## Top 10 by MDI (raw, no redundancy filter)\n")
    md.append("| Feature | MDI |")
    md.append("|---------|-----|")
    for f, v in mdi.head(10).items():
        md.append(f"| `{f}` | {v:.4f} |")

    md.append("\n## Top 10 by SFI (single-feature AUC)\n")
    md.append("Closer to 0.5 = no signal. Above 0.55 = real signal. Above 0.60 = strong.\n")
    md.append("| Feature | AUC |")
    md.append("|---------|-----|")
    for f, v in sfi.head(10).items():
        md.append(f"| `{f}` | {v:.4f} |")

    md.append("\n## Redundant feature clusters (kept the highest-ranked from each)\n")
    if not clusters:
        md.append("_No clusters above Spearman 0.85._")
    else:
        for head, members in clusters.items():
            md.append(f"- `{head}` ⇄ {', '.join(f'`{m}`' for m in members)}")

    md.append("\n## How to read this\n")
    md.append("- **MDI** is fast but biased toward features with many split points. "
              "Trust it for ranking but not for absolute magnitude.")
    md.append("- **SFI** is the unbiased per-feature predictive power. AUC < 0.52 "
              "means the feature alone has near-zero edge.")
    md.append("- **Consensus rank** combines both. Lower = better.")
    md.append("- **Correlation clusters** identify near-duplicate features. v3.0 "
              "should use only one representative per cluster to reduce noise and "
              "improve interpretability.\n")

    md.append("## Next action\n")
    md.append("Use this shortlist as the FEATURES list when implementing "
              "`ml/meta_labeler.py` (Phase 7, days 6-7). Re-run this analysis "
              "after Triple Barrier labeling on actual primary signals (not on "
              "every bar) — the ranking may shift when labels come from "
              "MACD/RSI signals instead of every H1 bar.\n")

    with open(OUT_DIR / "feature_importance_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"  ✓ feature_importance_report.md")

    print(f"\n{'='*70}")
    print(f"  ✅ DONE — see docs/research/feature_importance_report.md")
    print(f"{'='*70}\n")

    return shortlist


if __name__ == "__main__":
    main()
