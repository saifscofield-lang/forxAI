"""
Phase 5 extra — Meta-Labeler Prototype (research only, freeze-safe)

Trains LightGBM binary classifiers on the 1,144-signal dataset from step 7
under 3 architectures:

  1. GLOBAL        — one model for everything (baseline)
  2. PER_STRATEGY  — separate MACD and RSI models
  3. PER_COMBO     — one model per (strategy, pair) with enough samples

Validates with Purged K-Fold (Lopez de Prado Ch. 7) — removes overlapping
samples around test fold boundaries to prevent label leakage.

Success metric: threshold=0.55 probability → does filtered-WR beat raw-WR
by enough to justify the complexity?

Writes results to:
  - data/improvements.db → meta_labeler_runs table
  - docs/research/meta_labeler_prototype.md
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

from lightgbm import LGBMClassifier
from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score
from sklearn.model_selection import KFold

from features.ml.feature_engine import get_feature_columns

# ───────────────────────────── CONFIG ─────────────────────────────
SIGNALS_PARQUET = Path("data/research/primary_signals.parquet")
N_SPLITS = 5
EMBARGO_FRAC = 0.01        # 1% of dataset size as embargo on each side
DECISION_THRESHOLD = 0.55  # plan §5.2 step 4
MIN_COMBO_SAMPLES = 80     # skip combos with < 80 signals
TOP_FEATURES = [
    # top 20 from step 7 (signal-conditioned ranking)
    "candle_body_ratio", "price_position_50", "lower_shadow_ratio",
    "close_vs_sma_200", "macd_hist", "volatility_10",
    "price_vs_high_20_atr", "rsi_14_lag1", "rsi_14_lag2", "macd_hist_lag1",
    "volume_ratio", "atr_28_pct", "price_position_10", "volume_change",
    "body_vs_atr", "atr_ratio_20", "macd_hist_change", "ema_12",
    "return_5", "dist_from_high_20",
]

OUT_REPORT = Path("docs/research/meta_labeler_prototype.md")
DB = "data/improvements.db"


# ───────────────────────────── PURGED K-FOLD ─────────────────────────────
class PurgedKFold:
    """Lopez de Prado §7.3. Removes samples within `embargo` index distance
    of the test fold to prevent leakage when labels overlap in time."""
    def __init__(self, n_splits=5, embargo=0.01):
        self.n_splits = n_splits
        self.embargo = embargo

    def split(self, X, y=None, groups=None):
        n = len(X)
        embargo_n = max(1, int(n * self.embargo))
        kf = KFold(n_splits=self.n_splits, shuffle=False)
        for train_idx, test_idx in kf.split(X):
            # Remove train samples within embargo_n of any test sample
            test_set = set(test_idx)
            mask = np.ones(n, dtype=bool)
            for t in test_idx:
                lo = max(0, t - embargo_n)
                hi = min(n, t + embargo_n + 1)
                mask[lo:hi] = False
            # Restore test indices themselves to test set
            mask_train = mask.copy()
            for t in test_idx:
                mask_train[t] = False
            train_purged = np.where(mask_train)[0]
            yield train_purged, test_idx


# ───────────────────────────── TRAINING ─────────────────────────────
def train_and_score(df, features, scope_label, threshold=DECISION_THRESHOLD):
    """Train LGBM on binary meta-label with Purged K-Fold. Return CV metrics."""
    df = df.sort_values("time").reset_index(drop=True)

    X = df[features].fillna(0).replace([np.inf, -np.inf], 0).values
    y = df["meta_label"].values

    if y.sum() < 5 or (len(y) - y.sum()) < 5:
        return None   # not enough of both classes

    cv = PurgedKFold(n_splits=N_SPLITS, embargo=EMBARGO_FRAC)
    aucs, f1s, precs, recs = [], [], [], []
    filtered_wins, filtered_total = 0, 0
    raw_wins, raw_total = int(y.sum()), len(y)

    for train_idx, test_idx in cv.split(X, y):
        if len(train_idx) < 20 or len(test_idx) < 10:
            continue
        Xtr, ytr = X[train_idx], y[train_idx]
        Xte, yte = X[test_idx], y[test_idx]

        if ytr.sum() < 3 or (len(ytr) - ytr.sum()) < 3:
            continue

        model = LGBMClassifier(
            n_estimators=200, learning_rate=0.05, max_depth=5,
            num_leaves=16, min_child_samples=20,
            class_weight="balanced", n_jobs=-1, random_state=42,
            verbose=-1,
        )
        model.fit(Xtr, ytr)
        proba = model.predict_proba(Xte)[:, 1]
        pred = (proba >= threshold).astype(int)

        if len(np.unique(yte)) > 1:
            aucs.append(roc_auc_score(yte, proba))
        if pred.sum() > 0:
            f1s.append(f1_score(yte, pred, zero_division=0))
            precs.append(precision_score(yte, pred, zero_division=0))
        recs.append(recall_score(yte, pred, zero_division=0))

        # Count filtered wins
        taken = proba >= threshold
        if taken.sum() > 0:
            filtered_total += taken.sum()
            filtered_wins += yte[taken].sum()

    raw_wr = 100 * raw_wins / max(1, raw_total)
    lifted_wr = 100 * filtered_wins / max(1, filtered_total) if filtered_total else 0
    lift = lifted_wr - raw_wr

    return {
        "scope": scope_label,
        "n_signals": len(df),
        "n_features": len(features),
        "cv_splits": N_SPLITS,
        "auc_mean": float(np.mean(aucs)) if aucs else None,
        "auc_std": float(np.std(aucs)) if aucs else None,
        "f1_mean": float(np.mean(f1s)) if f1s else 0.0,
        "precision_mean": float(np.mean(precs)) if precs else 0.0,
        "recall_mean": float(np.mean(recs)) if recs else 0.0,
        "baseline_wr": raw_wr,
        "lifted_wr": lifted_wr,
        "wr_lift_points": lift,
        "filtered_total": int(filtered_total),
        "filtered_wins": int(filtered_wins),
    }


def verdict_for(res):
    if res is None:
        return "SKIP", "Not enough data"
    auc = res.get("auc_mean") or 0
    lift = res.get("wr_lift_points") or 0
    if auc >= 0.55 and lift >= 5:
        return "✅ STRONG", f"AUC {auc:.3f} · WR lift +{lift:.1f}pp"
    elif auc >= 0.53 and lift >= 2:
        return "⚠️ WEAK", f"AUC {auc:.3f} · WR lift +{lift:.1f}pp"
    elif auc >= 0.52 or lift >= 1:
        return "❌ MARGINAL", f"AUC {auc:.3f} · WR lift {lift:+.1f}pp"
    else:
        return "❌ NONE", f"AUC {auc:.3f} · WR lift {lift:+.1f}pp"


# ───────────────────────────── MAIN ─────────────────────────────
def main():
    print(f"\n{'='*72}")
    print(f"  Meta-Labeler Prototype — Phase 5 research")
    print(f"  Run: {datetime.now().isoformat(timespec='seconds')}")
    print(f"{'='*72}\n")

    df = pd.read_parquet(SIGNALS_PARQUET)
    print(f"Loaded {len(df):,} signals from {SIGNALS_PARQUET}")

    # Use binary meta-label (1=TP, 0=SL); drop timeouts
    df = df[df["label"] != 0].copy()
    df["meta_label"] = (df["label"] == 1).astype(int)
    print(f"After dropping timeouts: {len(df):,} signals (TP={df.meta_label.sum()}, SL={len(df)-df.meta_label.sum()})")

    available_feats = [c for c in TOP_FEATURES if c in df.columns]
    print(f"Features used: {len(available_feats)}/{len(TOP_FEATURES)} available")

    runs = []

    # ─── 1. GLOBAL ───
    print(f"\n▶ Architecture 1: GLOBAL (one model for all {len(df):,} signals)")
    res = train_and_score(df, available_feats, "GLOBAL")
    if res:
        v, desc = verdict_for(res)
        print(f"  {v}: {desc}")
        print(f"  Baseline WR: {res['baseline_wr']:.1f}%  →  Filtered WR: {res['lifted_wr']:.1f}%  ({res['filtered_total']} taken of {res['n_signals']})")
        runs.append(("GLOBAL", "all", res, v))

    # ─── 2. PER STRATEGY ───
    print(f"\n▶ Architecture 2: PER_STRATEGY (separate MACD vs RSI models)")
    for strat in ["macd_crossover", "rsi_reversal"]:
        sub = df[df["strategy"] == strat]
        if len(sub) < MIN_COMBO_SAMPLES:
            print(f"  {strat}: {len(sub)} < {MIN_COMBO_SAMPLES}, skip")
            continue
        res = train_and_score(sub, available_feats, f"strategy={strat}")
        if res:
            v, desc = verdict_for(res)
            print(f"  {strat:<18}: {v}: {desc}  (n={len(sub):,})")
            runs.append(("PER_STRATEGY", strat, res, v))

    # ─── 3. PER STRATEGY × PAIR (only combos with enough samples) ───
    print(f"\n▶ Architecture 3: PER_COMBO (strategy × pair with ≥{MIN_COMBO_SAMPLES} samples)")
    for (strat, sym), sub in df.groupby(["strategy", "symbol"]):
        if len(sub) < MIN_COMBO_SAMPLES:
            continue
        res = train_and_score(sub, available_feats, f"{strat}/{sym}")
        if res:
            v, desc = verdict_for(res)
            print(f"  {strat:<18} {sym:<8}: {v}: {desc}  (n={len(sub):,})")
            runs.append(("PER_COMBO", f"{strat}/{sym}", res, v))

    # ─── Save to DB ───
    print(f"\n▶ Saving {len(runs)} runs to data/improvements.db...")
    conn = sqlite3.connect(DB)
    run_time = datetime.now().isoformat(timespec="seconds")
    for arch, scope, res, verdict in runs:
        conn.execute("""
            INSERT INTO meta_labeler_runs
            (run_time, architecture, scope, n_signals, n_features, cv_splits,
             auc_mean, auc_std, f1_mean, precision_mean, recall_mean,
             baseline_wr, lifted_wr, wr_lift_points, verdict, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (run_time, arch, scope,
              res["n_signals"], res["n_features"], res["cv_splits"],
              res["auc_mean"], res["auc_std"], res["f1_mean"],
              res["precision_mean"], res["recall_mean"],
              res["baseline_wr"], res["lifted_wr"], res["wr_lift_points"],
              verdict, f"filtered {res['filtered_total']} / {res['n_signals']}"))
    conn.commit()
    conn.close()
    print(f"  ✓ saved")

    # ─── Markdown report ───
    md = []
    md.append(f"# Meta-Labeler Prototype — Results\n")
    md.append(f"_Run: {run_time}_  ")
    md.append(f"_Dataset: {len(df):,} signals (TP={df.meta_label.sum()}, SL={len(df)-df.meta_label.sum()})_  ")
    md.append(f"_Validation: Purged K-Fold, {N_SPLITS} splits, embargo {EMBARGO_FRAC*100:.0f}%_  ")
    md.append(f"_Decision threshold: proba ≥ {DECISION_THRESHOLD}_  ")
    md.append(f"_Features: {len(available_feats)} from step 7 shortlist_\n")

    md.append("## Results table\n")
    md.append("| Architecture | Scope | N | AUC ± std | WR base → filtered | Lift | Verdict |")
    md.append("|---|---|---:|---:|---:|---:|---|")
    for arch, scope, r, v in runs:
        auc = f"{r['auc_mean']:.3f} ± {r['auc_std']:.3f}" if r['auc_mean'] else "—"
        md.append(
            f"| {arch} | `{scope}` | {r['n_signals']:,} | {auc} | "
            f"{r['baseline_wr']:.1f}% → {r['lifted_wr']:.1f}% | "
            f"{r['wr_lift_points']:+.1f}pp | {v} |"
        )

    md.append("\n## Interpretation\n")
    md.append("- **AUC ≥ 0.55** is the bar for \"this model has real signal\".")
    md.append("- **WR lift ≥ 5pp** is the bar for \"this is worth the operational complexity\".")
    md.append("- **Filtered WR** is the actual metric that matters: of the signals the meta-labeler says to take, what fraction win?\n")

    # Pick the winning architecture
    best = max(
        [r for r in runs if r[2]["auc_mean"] is not None],
        key=lambda r: (r[2]["wr_lift_points"] or 0) + (r[2]["auc_mean"] or 0) * 10,
        default=None,
    )
    if best:
        arch, scope, r, v = best
        md.append(f"## Recommended architecture for v3.0 Phase 7\n")
        md.append(f"**{arch}** ({scope}) — {v}\n")
        md.append(f"- AUC: {r['auc_mean']:.3f} ± {r['auc_std']:.3f}")
        md.append(f"- Raw WR: {r['baseline_wr']:.1f}% → Filtered: {r['lifted_wr']:.1f}% (lift {r['wr_lift_points']:+.1f}pp)")
        md.append(f"- {r['filtered_total']} signals taken of {r['n_signals']} primary ({100*r['filtered_total']/r['n_signals']:.0f}% keep-rate)\n")

    md.append("## Next action\n")
    md.append("If any architecture reached ✅ STRONG, that is the v3.0 Phase 7 starting point.")
    md.append("If all are ⚠️ or ❌, investigate: (a) richer feature set, (b) different labels "
              "(e.g., triple-barrier with volatility-scaled barriers), (c) admit the edge "
              "may not be large enough for meta-labeling to help meaningfully.\n")

    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text("\n".join(md), encoding="utf-8")
    print(f"\n✓ report: {OUT_REPORT}")

    print(f"\n{'='*72}")
    if best:
        print(f"  BEST: {best[0]} / {best[1]} — {best[3]}")
    print(f"  See {OUT_REPORT} for full results")
    print(f"{'='*72}\n")


if __name__ == "__main__":
    main()
