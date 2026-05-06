"""Unit tests for features/importance/feature_selector.py.

Each test builds synthetic data with a known true-feature signal and
verifies the ranking method correctly surfaces the informative features.
Pytest-free runner at the bottom (matches the rest of the project).
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from features.importance.feature_selector import (
    apply_pca,
    combined_rank,
    compute_mdi,
    compute_sfi,
    pca_components_to_keep,
    top_n_features,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

def make_synthetic_dataset(n_samples=300, n_informative=3, n_noise=7, seed=42):
    """Build (X, y) with known informative features.

    The first `n_informative` columns predict y; the remaining are noise."""
    rng = np.random.default_rng(seed)
    n_features = n_informative + n_noise
    X = rng.normal(0, 1, size=(n_samples, n_features))
    # Linear combination of informative features → 2-class label
    weights = rng.normal(0, 1, size=n_informative)
    score = X[:, :n_informative] @ weights
    y = (score > 0).astype(int)
    cols = [f"f_inf_{i}" for i in range(n_informative)] + [f"f_noise_{i}" for i in range(n_noise)]
    return pd.DataFrame(X, columns=cols), y, cols


# ── compute_mdi tests ───────────────────────────────────────────────────────

def test_mdi_with_lightgbm_booster():
    """Train a small LightGBM model + check MDI prefers informative features."""
    import lightgbm as lgb
    X, y, cols = make_synthetic_dataset(n_samples=500, n_informative=3, n_noise=7)
    train_data = lgb.Dataset(X.values, label=y, feature_name=cols)
    model = lgb.train(
        {"objective": "binary", "verbose": -1, "seed": 42},
        train_data, num_boost_round=20,
    )
    importance = compute_mdi(model, cols)
    # Informative features should fill at least 2 of the top 3 slots
    top3 = top_n_features(importance, 3)
    n_inf_in_top = sum(1 for c in top3 if c.startswith("f_inf"))
    assert n_inf_in_top >= 2, f"expected ≥2 informative in top 3, got {top3}"
    # Importance should be normalised (sum to 1.0)
    assert abs(importance.sum() - 1.0) < 1e-9


def test_mdi_with_sklearn_random_forest():
    from sklearn.ensemble import RandomForestClassifier
    X, y, cols = make_synthetic_dataset(n_samples=400, n_informative=3, n_noise=7)
    rf = RandomForestClassifier(n_estimators=30, random_state=42).fit(X.values, y)
    importance = compute_mdi(rf, cols)
    top3 = top_n_features(importance, 3)
    n_inf_in_top = sum(1 for c in top3 if c.startswith("f_inf"))
    assert n_inf_in_top >= 2


def test_mdi_handles_zero_importance():
    """Degenerate case: all importances zero → uniform distribution."""
    class DummyModel:
        feature_importances_ = np.array([0.0, 0.0, 0.0])
    importance = compute_mdi(DummyModel(), ["a", "b", "c"])
    assert all(abs(v - 1/3) < 1e-9 for v in importance.values)


def test_mdi_raises_on_invalid_input():
    try:
        compute_mdi(None, ["a", "b"])
        assert False, "expected ValueError"
    except ValueError:
        pass

    class NoFeatureMethod:
        pass
    try:
        compute_mdi(NoFeatureMethod(), ["a"])
        assert False, "expected TypeError"
    except TypeError:
        pass


def test_mdi_raises_on_length_mismatch():
    class DummyModel:
        feature_importances_ = np.array([0.5, 0.3])
    try:
        compute_mdi(DummyModel(), ["a", "b", "c"])
        assert False, "expected ValueError"
    except ValueError as e:
        assert "length" in str(e).lower()


def test_top_n_features_respects_n():
    s = pd.Series([0.5, 0.3, 0.1, 0.05, 0.05], index=["a", "b", "c", "d", "e"])
    assert top_n_features(s, 3) == ["a", "b", "c"]
    assert top_n_features(s, 10) == ["a", "b", "c", "d", "e"]
    assert top_n_features(pd.Series(dtype=float), 5) == []


# ── SFI tests ───────────────────────────────────────────────────────────────

def test_sfi_ranks_informative_first():
    from sklearn.tree import DecisionTreeClassifier
    X, y, cols = make_synthetic_dataset(n_samples=200, n_informative=3, n_noise=4)
    sfi = compute_sfi(
        X, y, cols,
        model_factory=lambda: DecisionTreeClassifier(max_depth=3, random_state=42),
        cv_splits=3,
    )
    top3 = list(sfi.head(3).index)
    n_inf_in_top = sum(1 for c in top3 if c.startswith("f_inf"))
    assert n_inf_in_top >= 2, f"expected ≥2 informative in top 3, got {top3}"
    # mean_score columns present
    assert "mean_score" in sfi.columns
    assert "std_score" in sfi.columns
    assert "n_folds" in sfi.columns


def test_sfi_raises_on_missing_column():
    from sklearn.tree import DecisionTreeClassifier
    X = pd.DataFrame({"a": [1, 2, 3, 4], "b": [4, 3, 2, 1]})
    try:
        compute_sfi(X, np.array([0, 1, 0, 1]), ["a", "missing"],
                    model_factory=DecisionTreeClassifier, cv_splits=2)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "missing" in str(e).lower()


def test_sfi_raises_on_invalid_inputs():
    from sklearn.tree import DecisionTreeClassifier
    try:
        compute_sfi(pd.DataFrame(), np.array([]), [], model_factory=DecisionTreeClassifier)
        assert False, "expected ValueError on empty X"
    except ValueError:
        pass

    X = pd.DataFrame({"a": [1, 2, 3, 4]})
    try:
        compute_sfi(X, np.array([0, 1]), ["a"], model_factory=DecisionTreeClassifier)
        assert False, "expected ValueError on length mismatch"
    except ValueError:
        pass

    try:
        compute_sfi(X, np.array([0, 1, 0, 1]), ["a"],
                    model_factory=DecisionTreeClassifier, cv_splits=1)
        assert False, "expected ValueError on cv_splits<2"
    except ValueError:
        pass


# ── PCA tests ───────────────────────────────────────────────────────────────

def test_pca_basic_shape():
    X, _, cols = make_synthetic_dataset(n_samples=200, n_informative=3, n_noise=7)
    result = apply_pca(X, n_components=5)
    assert result.transformed.shape == (200, 5)
    assert len(result.explained_variance_ratio) == 5
    assert len(result.cumulative_explained) == 5
    assert result.cumulative_explained[-1] <= 1.0 + 1e-9


def test_pca_default_keeps_all():
    X, _, cols = make_synthetic_dataset(n_samples=300, n_informative=3, n_noise=7)
    result = apply_pca(X, n_components=None)
    assert result.transformed.shape[1] == len(cols)


def test_pca_components_to_keep_at_threshold():
    X, _, _ = make_synthetic_dataset(n_samples=300, n_informative=3, n_noise=10)
    result = apply_pca(X)
    # 95% threshold should keep fewer than the full feature set
    n95 = pca_components_to_keep(result, threshold=0.95)
    assert 1 <= n95 <= len(result.feature_names)
    # 100% threshold keeps all
    n100 = pca_components_to_keep(result, threshold=1.0)
    assert n100 == len(result.cumulative_explained)


def test_pca_invalid_inputs():
    try:
        apply_pca(pd.DataFrame())
        assert False, "expected ValueError on empty X"
    except ValueError:
        pass

    X = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    try:
        apply_pca(X, n_components=0)
        assert False, "expected ValueError on n_components<1"
    except ValueError:
        pass
    try:
        apply_pca(X, n_components=10)
        assert False, "expected ValueError on n_components>features"
    except ValueError:
        pass


def test_pca_columns_named_pc():
    X, _, _ = make_synthetic_dataset(n_samples=100, n_informative=2, n_noise=3)
    result = apply_pca(X, n_components=3)
    assert list(result.transformed.columns) == ["PC1", "PC2", "PC3"]


def test_pca_threshold_validation():
    X, _, _ = make_synthetic_dataset()
    result = apply_pca(X)
    try:
        pca_components_to_keep(result, threshold=0)
        assert False, "expected ValueError"
    except ValueError:
        pass
    try:
        pca_components_to_keep(result, threshold=1.5)
        assert False, "expected ValueError"
    except ValueError:
        pass


# ── combined_rank tests ────────────────────────────────────────────────────

def test_combined_rank_agrees_when_methods_agree():
    """If MDI and SFI rank features identically, combined rank matches."""
    mdi = pd.Series([0.5, 0.3, 0.2], index=["a", "b", "c"])
    sfi = pd.DataFrame(
        {"mean_score": [0.9, 0.7, 0.5], "std_score": [0.01, 0.01, 0.01], "n_folds": [3, 3, 3]},
        index=["a", "b", "c"],
    )
    combined = combined_rank(mdi, sfi)
    assert list(combined.index) == ["a", "b", "c"]


def test_combined_rank_resolves_disagreement():
    """If MDI says a > b > c and SFI says c > b > a, combined puts b in middle."""
    mdi = pd.Series([0.5, 0.3, 0.2], index=["a", "b", "c"])
    sfi = pd.DataFrame(
        {"mean_score": [0.5, 0.7, 0.9], "std_score": [0.01]*3, "n_folds": [3]*3},
        index=["a", "b", "c"],
    )
    combined = combined_rank(mdi, sfi, weight_mdi=0.5, weight_sfi=0.5)
    # 'b' has avg rank 2 under both → it should rank middle
    ranks = list(combined.index)
    assert ranks[1] == "b"


def test_combined_rank_handles_partial_overlap():
    """Features only in MDI or only in SFI are dropped from combined."""
    mdi = pd.Series([0.5, 0.3], index=["a", "b"])
    sfi = pd.DataFrame(
        {"mean_score": [0.9, 0.7], "std_score": [0.01]*2, "n_folds": [3]*2},
        index=["b", "c"],
    )
    combined = combined_rank(mdi, sfi)
    assert list(combined.index) == ["b"]  # only common feature


def test_combined_rank_raises_on_no_overlap():
    mdi = pd.Series([0.5], index=["a"])
    sfi = pd.DataFrame(
        {"mean_score": [0.9], "std_score": [0.01], "n_folds": [3]}, index=["b"],
    )
    try:
        combined_rank(mdi, sfi)
        assert False, "expected ValueError"
    except ValueError:
        pass


# ── Pytest-free runner ─────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    fail = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            fail += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            fail += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print()
    print(f"{len(tests) - fail}/{len(tests)} pass")
    sys.exit(0 if fail == 0 else 1)
