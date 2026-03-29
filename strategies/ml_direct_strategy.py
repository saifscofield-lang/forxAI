"""
ML Direct Strategy — Market-Driven Signal Generation
السوق يعلّمنا: الموديل يولّد إشارات BUY/SELL مباشرة من features السوق الحالية.
لا قواعد يدوية — الموديل تعلّم الأنماط من 100,000 شمعة تاريخية.

Usage:
    strategy = MLDirectStrategy(symbol="EURUSD")
    signal = strategy.generate_signal(df)  # df = H1 OHLCV with 200+ bars
"""
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from loguru import logger
from features.ml.feature_engine import build_features, get_feature_columns


MODEL_DIR = Path("models/market_learner")

# LightGBM class mapping: 0=SELL, 1=NO_TRADE, 2=BUY
CLASS_MAP = {0: "SELL", 1: None, 2: "BUY"}


class MLDirectStrategy:
    """Generate trade signals directly from ML model predictions."""
    VERSION = "1.0"

    def __init__(
        self,
        symbol: str,
        confidence_threshold: float = 0.55,
        atr_sl_multiplier: float = 2.0,
        atr_tp_multiplier: float = 3.0,
        model_dir: str | Path = MODEL_DIR,
    ):
        self.name = "ml_direct"
        self.symbol = symbol
        self.confidence_threshold = confidence_threshold
        self.atr_sl_multiplier = atr_sl_multiplier
        self.atr_tp_multiplier = atr_tp_multiplier
        self.model = None
        self.meta = None
        self.feature_cols = None

        self._load_model(Path(model_dir))

    def _load_model(self, model_dir: Path):
        """Load trained model for this symbol."""
        model_path = model_dir / f"{self.symbol}_model.pkl"
        if not model_path.exists():
            logger.warning(f"[{self.symbol}] No ML model found at {model_path}")
            return

        with open(model_path, "rb") as f:
            data = pickle.load(f)

        self.model = data["model"]
        self.meta = data["meta"]
        self.feature_cols = data["meta"]["feature_cols"]
        logger.info(
            f"[{self.symbol}] ML Direct model loaded "
            f"(trained {self.meta['trained_at'][:10]}, "
            f"accuracy={self.meta['metrics']['overall_accuracy']:.1%})"
        )

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Build features (required by engine interface)."""
        return build_features(df, dropna=True)

    def generate_signal(self, df: pd.DataFrame) -> dict | None:
        """
        Generate signal from ML model prediction.

        Returns dict with signal info or None if:
        - No model loaded
        - Model says NO_TRADE
        - Confidence below threshold
        """
        if self.model is None:
            return None

        # Build features
        try:
            feat_df = build_features(df.copy(), dropna=True)
        except Exception as e:
            logger.warning(f"[{self.symbol}] Feature build failed: {e}")
            return None

        if len(feat_df) < 1:
            return None

        # Get available features (handle missing columns gracefully)
        available_cols = [c for c in self.feature_cols if c in feat_df.columns]
        if len(available_cols) < len(self.feature_cols) * 0.9:
            logger.warning(
                f"[{self.symbol}] Too many missing features: "
                f"{len(available_cols)}/{len(self.feature_cols)}"
            )
            return None

        # Fill any missing columns with 0
        for c in self.feature_cols:
            if c not in feat_df.columns:
                feat_df[c] = 0

        # Predict
        X = feat_df[self.feature_cols].iloc[-1:].values
        proba = self.model.predict(X)[0]  # [P(SELL), P(NO_TRADE), P(BUY)]

        pred_class = int(proba.argmax())
        confidence = float(proba[pred_class])
        action = CLASS_MAP.get(pred_class)

        # No trade signal
        if action is None:
            return None

        # Confidence filter
        if confidence < self.confidence_threshold:
            logger.debug(
                f"[{self.symbol}] {action} skipped: confidence {confidence:.1%} "
                f"< {self.confidence_threshold:.0%}"
            )
            return None

        # Build signal with ATR-based SL/TP
        curr = feat_df.iloc[-1]
        price = curr["close"]

        # Use ATR for SL/TP (prefer atr_14, fallback to atr_7)
        atr = curr.get("atr_14", curr.get("atr_7", 0))
        if atr <= 0:
            logger.warning(f"[{self.symbol}] ATR is 0, skipping signal")
            return None

        if action == "BUY":
            sl = price - atr * self.atr_sl_multiplier
            tp = price + atr * self.atr_tp_multiplier
        else:
            sl = price + atr * self.atr_sl_multiplier
            tp = price - atr * self.atr_tp_multiplier

        rsi = curr.get("rsi_14", 50.0)

        signal = {
            "action": action,
            "symbol": self.symbol,
            "price": price,
            "stop_loss": round(sl, 5),
            "take_profit": round(tp, 5),
            "atr": round(atr, 5),
            "rsi": round(rsi, 2),
            "ml_confidence": round(confidence, 4),
            "ml_threshold": self.confidence_threshold,
            "strategy": self.name,
            "strategy_version": self.VERSION,
            "reason": (
                f"ML Direct {action} | conf={confidence:.1%} "
                f"[SELL={proba[0]:.1%} NO={proba[1]:.1%} BUY={proba[2]:.1%}]"
            ),
            "status": "ACTIVE",
        }

        logger.info(f"[{self.symbol}] {signal['reason']}")
        return signal
