"""Feature-importance + selection methods for the Phase 7 meta-labeler.

Per Marcos López de Prado, "Advances in Financial Machine Learning"
(2018), Chapter 8. Three complementary methods, each catching a
different failure mode:

  MDI — Mean Decrease Impurity
        Tree-based feature importance from a fitted ensemble.
        Cheap, fast, but biased toward high-cardinality features
        and unreliable on correlated features (substitution effect:
        a strong feature can hide a similarly strong correlated
        one). Good first pass.

  SFI — Single-Feature Importance
        Train one model per feature in isolation; rank by CV
        score. Robust to substitution effects (each feature is
        evaluated alone) but expensive (one fit per feature) and
        misses interactions. Good cross-check against MDI.

  PCA — Principal Component Analysis (orthogonalised features)
        Decorrelates the feature matrix. Useful when MDI / SFI
        agree but the top features are mutually correlated — the
        first few principal components often carry most of the
        variance and form a smaller decorrelated feature set.

The Phase 7 plan uses these three side-by-side: MDI for the cheap
first pass, SFI to confirm, PCA when the top features are
correlated. Combined output is the basis for the "20 final
features" list (Phase 7 Step 4).

Pure functions over numpy / pandas / sklearn / lightgbm. No DB,
no engine, no filesystem dependencies."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

import numpy as np
import pandas as pd


# ── MDI ─────────────────────────────────────────────────────────────────────

def compute_mdi(model, feature_names: Sequence[str]) -> pd.Series:
    """Extract Mean Decrease Impurity feature importance from a fitted model.

    Supports:
      - LightGBM Booster: uses `feature_importance(importance_type='gain')`.
      - sklearn ensembles (RandomForest, GradientBoosting, etc.):
        uses `feature_importances_`.
      - Anything with a callable `.feature_importance` attribute.

    Returns a pd.Series indexed by feature_name, sorted descending.
    Values are normalised to sum to 1.0 (so they're comparable across
    models / runs)."""
    if model is None:
        raise ValueError("model is None")
    if not feature_names:
        raise ValueError("feature_names is empty")

    # LightGBM Booster: feature_importance() with gain
    if hasattr(model, "feature_importance") and callable(getattr(model, "feature_importance")):
        try:
            raw = model.feature_importance(importance_type="gain")
        except TypeError:
            raw = model.feature_importance()
    elif hasattr(model, "feature_importances_"):
        # sklearn-style attribute
        raw = np.asarray(model.feature_importances_, dtype=float)
    else:
        raise TypeError(
            f"model of type {type(model).__name__} does not expose "
            "feature_importance() or feature_importances_"
        )

    raw = np.asarray(raw, dtype=float)
    if len(raw) != len(feature_names):
        raise ValueError(
            f"feature_importance length {len(raw)} does not match "
            f"feature_names length {len(feature_names)}"
        )
    total = raw.sum()
    if total <= 0:
        # Degenerate: model gave zero importance everywhere; return uniform
        normalised = np.full(len(raw), 1.0 / len(raw))
    else:
        normalised = raw / total
    s = pd.Series(normalised, index=list(feature_names), name="mdi")
    return s.sort_values(ascending=False)


def top_n_features(importance: pd.Series, n: int = 20) -> list:
    """Return the top-N feature names from a sorted importance Series."""
    if importance is None or importance.empty:
        return []
    return list(importance.sort_values(ascending=False).head(n).index)


# ── SFI ─────────────────────────────────────────────────────────────────────

@dataclass
class SFIResult:
    """One feature's single-feature-importance score."""
    feature: str
    mean_score: float
    std_score: float
    n_folds: int


def compute_sfi(
    X: pd.DataFrame,
    y: np.ndarray,
    feature_names: Sequence[str],
    *,
    model_factory: Callable,
    cv_splits: int = 5,
    scoring: str = "accuracy",
) -> pd.DataFrame:
    """Single-Feature-Importance: train one model per feature, return
    CV scores ranked descending.

    Each feature is evaluated in isolation — robust against the
    substitution effect that biases MDI when features are correlated.

    Args:
        X: feature DataFrame (n_samples, n_features). Columns must
            include `feature_names`.
        y: target array (n_samples,). Class labels for the trees.
        feature_names: list of feature columns to evaluate one-by-one.
        model_factory: zero-arg callable that returns a fresh model
            instance on each call. The model must support sklearn's
            `fit(X, y)` + `predict(X)` API. Each call produces an
            independent model so SFI fits don't leak state.
        cv_splits: number of K-fold splits per feature. Default 5.
        scoring: sklearn-compatible scoring metric. Default "accuracy".

    Returns:
        DataFrame indexed by feature, columns ['mean_score',
        'std_score', 'n_folds'], sorted by mean_score descending.

    Raises ValueError on missing columns / empty inputs / cv_splits<2."""
    if X is None or len(X) == 0:
        raise ValueError("X is empty")
    if y is None or len(y) != len(X):
        raise ValueError("y must have same length as X")
    if not feature_names:
        raise ValueError("feature_names is empty")
    missing = [f for f in feature_names if f not in X.columns]
    if missing:
        raise ValueError(f"features missing from X: {missing}")
    if cv_splits < 2:
        raise ValueError(f"cv_splits must be >= 2, got {cv_splits}")

    from sklearn.model_selection import cross_val_score

    rows = []
    for feat in feature_names:
        X_one = X[[feat]].values
        try:
            model = model_factory()
        except Exception as e:
            raise RuntimeError(
                f"model_factory() failed for feature {feat!r}: {e}"
            ) from e
        scores = cross_val_score(model, X_one, y, cv=cv_splits, scoring=scoring)
        rows.append(SFIResult(
            feature=feat,
            mean_score=float(np.mean(scores)),
            std_score=float(np.std(scores, ddof=1)) if len(scores) > 1 else 0.0,
            n_folds=int(len(scores)),
        ))

    df = pd.DataFrame(
        [{"feature": r.feature, "mean_score": r.mean_score,
          "std_score": r.std_score, "n_folds": r.n_folds} for r in rows]
    )
    return df.sort_values("mean_score", ascending=False).set_index("feature")


# ── PCA ─────────────────────────────────────────────────────────────────────

@dataclass
class PCAResult:
    """Output of apply_pca()."""
    components: np.ndarray              # (n_components, n_features) — loadings
    explained_variance_ratio: np.ndarray  # (n_components,) — fraction of total
    cumulative_explained: np.ndarray   # (n_components,) — cumulative
    transformed: pd.DataFrame           # (n_samples, n_components) — projected
    feature_names: list                 # original feature column names


def apply_pca(
    X: pd.DataFrame,
    *,
    n_components: Optional[int] = None,
    standardise: bool = True,
) -> PCAResult:
    """Principal Component Analysis on the feature matrix.

    Args:
        X: feature DataFrame. Numeric columns only.
        n_components: number of principal components to retain. None
            keeps all.
        standardise: if True (default), each feature is mean-centered
            and scaled to unit variance before PCA. Highly recommended
            when features have different scales (e.g. ATR vs RSI vs
            log-returns).

    Returns:
        PCAResult with the loadings, explained-variance ratio,
        cumulative-explained-variance curve, and the transformed
        (samples × components) DataFrame for downstream training.

    The columns of `transformed` are named PC1, PC2, ... so they're
    drop-in for any modeling pipeline. The loadings tell you which
    original features each PC weights heaviest."""
    if X is None or len(X) == 0:
        raise ValueError("X is empty")
    feature_names = list(X.columns)
    if n_components is not None and n_components < 1:
        raise ValueError(f"n_components must be >= 1, got {n_components}")
    if n_components is not None and n_components > len(feature_names):
        raise ValueError(
            f"n_components {n_components} exceeds feature count {len(feature_names)}"
        )

    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    arr = X.values.astype(float)
    if standardise:
        scaler = StandardScaler()
        arr = scaler.fit_transform(arr)

    n_max = min(arr.shape[0], arr.shape[1])
    n_comp = n_components if n_components is not None else n_max
    n_comp = min(n_comp, n_max)

    pca = PCA(n_components=n_comp, random_state=42)
    transformed_arr = pca.fit_transform(arr)
    transformed = pd.DataFrame(
        transformed_arr,
        index=X.index,
        columns=[f"PC{i+1}" for i in range(n_comp)],
    )
    return PCAResult(
        components=pca.components_,
        explained_variance_ratio=pca.explained_variance_ratio_,
        cumulative_explained=np.cumsum(pca.explained_variance_ratio_),
        transformed=transformed,
        feature_names=feature_names,
    )


def pca_components_to_keep(
    pca_result: PCAResult, *, threshold: float = 0.95
) -> int:
    """Return the smallest n_components whose cumulative explained
    variance reaches `threshold`.

    Standard rule-of-thumb for dimensionality reduction: 95% of the
    variance often sits in fewer than half the original components."""
    if pca_result is None or len(pca_result.cumulative_explained) == 0:
        return 0
    if not 0.0 < threshold <= 1.0:
        raise ValueError(f"threshold must be in (0, 1], got {threshold}")
    above = np.where(pca_result.cumulative_explained >= threshold)[0]
    if len(above) == 0:
        return len(pca_result.cumulative_explained)
    return int(above[0]) + 1


# ── Combined-rank helper ───────────────────────────────────────────────────

def combined_rank(
    mdi_series: pd.Series,
    sfi_df: pd.DataFrame,
    *,
    weight_mdi: float = 0.5,
    weight_sfi: float = 0.5,
) -> pd.Series:
    """Combine MDI and SFI rankings into a single descending rank.

    For each feature, computes its rank under each method (1=best),
    then combines via weighted average. Useful for picking a final
    top-N when MDI and SFI partially disagree.

    Returns a pd.Series indexed by feature with the combined rank
    score (lower is better), sorted ascending."""
    if mdi_series is None or sfi_df is None or sfi_df.empty:
        raise ValueError("both mdi_series and sfi_df must be non-empty")
    common = mdi_series.index.intersection(sfi_df.index)
    if len(common) == 0:
        raise ValueError("mdi and sfi share no features")

    mdi_rank = mdi_series.loc[common].rank(ascending=False)
    sfi_rank = sfi_df.loc[common, "mean_score"].rank(ascending=False)
    total = weight_mdi + weight_sfi
    if total <= 0:
        raise ValueError("weights must sum to > 0")
    combined = (weight_mdi * mdi_rank + weight_sfi * sfi_rank) / total
    return combined.sort_values()
