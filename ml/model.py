"""
LightGBM Model for Forex Signal Prediction.
Handles training, prediction, feature importance, and model persistence.
"""
import os
import json
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import (
    accuracy_score, classification_report, f1_score, log_loss,
)
from dataclasses import dataclass, field


@dataclass
class ModelResult:
    """Training/evaluation result."""
    accuracy: float
    f1_macro: float
    f1_per_class: dict
    log_loss_val: float
    feature_importance: dict
    label_distribution: dict
    n_train: int
    n_test: int


class ForexLGBM:
    """LightGBM wrapper for forex signal prediction."""

    def __init__(
        self,
        n_estimators: int = 1000,
        learning_rate: float = 0.05,
        max_depth: int = 7,
        num_leaves: int = 63,
        min_child_samples: int = 50,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        reg_alpha: float = 0.1,
        reg_lambda: float = 1.0,
        class_weight: str = "balanced",
        random_state: int = 42,
        device: str = "cpu",
    ):
        self.params = {
            "n_estimators": n_estimators,
            "learning_rate": learning_rate,
            "max_depth": max_depth,
            "num_leaves": num_leaves,
            "min_child_samples": min_child_samples,
            "subsample": subsample,
            "colsample_bytree": colsample_bytree,
            "reg_alpha": reg_alpha,
            "reg_lambda": reg_lambda,
            "class_weight": class_weight,
            "random_state": random_state,
            "device": device,
            "verbose": -1,
            "n_jobs": -1,
        }
        self.model = None
        self.feature_names = None
        self.classes_ = None

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray = None,
        y_val: np.ndarray = None,
        feature_names: list = None,
        early_stopping_rounds: int = 50,
    ) -> None:
        """Train the model with optional validation for early stopping."""
        self.feature_names = feature_names
        self.classes_ = np.unique(y_train)

        self.model = lgb.LGBMClassifier(**self.params)

        fit_params = {}
        if X_val is not None and y_val is not None:
            fit_params["eval_set"] = [(X_val, y_val)]
            fit_params["callbacks"] = [
                lgb.early_stopping(early_stopping_rounds, verbose=False),
                lgb.log_evaluation(period=0),
            ]

        self.model.fit(X_train, y_train, **fit_params)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict class labels."""
        return self.model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities."""
        return self.model.predict_proba(X)

    def evaluate(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray,
        feature_names: list = None,
    ) -> ModelResult:
        """Evaluate model on test data."""
        y_pred = self.predict(X_test)
        y_proba = self.predict_proba(X_test)

        acc = accuracy_score(y_test, y_pred)
        f1_m = f1_score(y_test, y_pred, average="macro", zero_division=0)

        # Per-class F1
        f1_per = {}
        for cls in self.classes_:
            name = {1: "BUY", 0: "HOLD", -1: "SELL"}.get(int(cls), str(int(cls)))
            mask = y_test == cls
            if mask.sum() > 0:
                cls_f1 = f1_score(y_test == cls, y_pred == cls, zero_division=0)
                f1_per[name] = round(cls_f1, 3)

        # Log loss
        try:
            ll = log_loss(y_test, y_proba, labels=self.classes_)
        except Exception:
            ll = float("nan")

        # Feature importance
        importance = self.get_feature_importance(feature_names)

        # Label distribution
        label_dist = {}
        for cls in self.classes_:
            name = {1: "BUY", 0: "HOLD", -1: "SELL"}.get(int(cls), str(int(cls)))
            train_count = int((y_train == cls).sum())
            test_count = int((y_test == cls).sum())
            pred_count = int((y_pred == cls).sum())
            label_dist[name] = {
                "train": train_count,
                "test": test_count,
                "predicted": pred_count,
            }

        return ModelResult(
            accuracy=round(acc, 4),
            f1_macro=round(f1_m, 4),
            f1_per_class=f1_per,
            log_loss_val=round(ll, 4),
            feature_importance=importance,
            label_distribution=label_dist,
            n_train=len(y_train),
            n_test=len(y_test),
        )

    def get_feature_importance(self, feature_names: list = None) -> dict:
        """Get top feature importances (gain-based)."""
        if self.model is None:
            return {}

        importance = self.model.feature_importances_
        names = feature_names or self.feature_names or [
            f"f{i}" for i in range(len(importance))
        ]

        pairs = sorted(zip(names, importance), key=lambda x: x[1], reverse=True)
        return {name: int(imp) for name, imp in pairs[:25]}

    def save(self, path: str) -> None:
        """Save model and metadata."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.model.booster_.save_model(path)

        meta_path = path.replace(".txt", "_meta.json")
        meta = {
            "feature_names": self.feature_names,
            "classes": [int(c) for c in self.classes_],
            "params": {k: v for k, v in self.params.items()
                       if isinstance(v, (int, float, str, bool))},
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

    def load(self, path: str) -> None:
        """Load model and metadata."""
        booster = lgb.Booster(model_file=path)
        self.model = lgb.LGBMClassifier(**self.params)
        self.model._Booster = booster
        self.model.fitted_ = True

        meta_path = path.replace(".txt", "_meta.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            self.feature_names = meta.get("feature_names")
            self.classes_ = np.array(meta.get("classes", [-1, 0, 1]))


def optimize_lgbm(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    n_trials: int = 100,
    feature_names: list = None,
) -> dict:
    """Optuna hyperparameter optimization for LightGBM."""
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        params = {
            "n_estimators": 1000,
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "num_leaves": trial.suggest_int("num_leaves", 15, 127),
            "min_child_samples": trial.suggest_int("min_child_samples", 20, 200),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.4, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 10, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10, log=True),
            "class_weight": "balanced",
            "random_state": 42,
            "verbose": -1,
            "n_jobs": -1,
        }

        model = lgb.LGBMClassifier(**params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[
                lgb.early_stopping(50, verbose=False),
                lgb.log_evaluation(period=0),
            ],
        )

        y_pred = model.predict(X_val)
        return f1_score(y_val, y_pred, average="macro", zero_division=0)

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

    return study.best_params
