"""
ML-Filtered SMA Crossover Strategy.
SMA crossover generates signals, LightGBM filters out low-quality trades.
"""
import json
import numpy as np
import pandas as pd
from loguru import logger
from features.technical.indicators import add_sma, add_rsi, add_atr
from features.ml.feature_engine import build_features, get_feature_columns


class MLFilteredStrategy:
    """SMA Crossover + LightGBM quality filter."""

    def __init__(
        self,
        symbol: str,
        fast_period: int = 20,
        slow_period: int = 50,
        rsi_period: int = 14,
        atr_period: int = 14,
        atr_sl_multiplier: float = 1.5,
        atr_tp_multiplier: float = 2.5,
        model=None,
        confidence_threshold: float = 0.50,
    ):
        self.name = "ml_filtered_sma"
        self.symbol = symbol
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.atr_sl_multiplier = atr_sl_multiplier
        self.atr_tp_multiplier = atr_tp_multiplier
        self.model = model
        self.confidence_threshold = confidence_threshold
        self._feature_cols = None

    def _build_feature_snapshot(self, df: pd.DataFrame) -> str | None:
        """Build features and return JSON snapshot for logging."""
        try:
            feat_df = build_features(df, dropna=True)
            if len(feat_df) > 0:
                if self._feature_cols is None:
                    self._feature_cols = get_feature_columns(feat_df)
                row = feat_df[self._feature_cols].iloc[-1]
                return json.dumps({k: round(float(v), 6) for k, v in row.items()})
        except Exception:
            pass
        return None

    def generate_signal(self, df: pd.DataFrame) -> dict | None:
        """Generate ML-filtered SMA crossover signal.

        Returns a signal dict with 'status' field:
        - "ACTIVE": signal passed all filters, ready to execute
        - "ML_FILTERED": signal blocked by ML confidence threshold
        - None: no SMA crossover detected (no signal at all)
        """
        # Prepare indicators
        tmp = df.copy()
        tmp = add_sma(tmp, self.fast_period)
        tmp = add_sma(tmp, self.slow_period)
        tmp = add_rsi(tmp, self.rsi_period)
        tmp = add_atr(tmp, self.atr_period)

        fast_col = f"sma_{self.fast_period}"
        slow_col = f"sma_{self.slow_period}"
        rsi_col = f"rsi_{self.rsi_period}"
        atr_col = f"atr_{self.atr_period}"

        required = [fast_col, slow_col, rsi_col, atr_col]
        clean = tmp.dropna(subset=required)
        if len(clean) < 2:
            return None

        curr = clean.iloc[-1]
        prev = clean.iloc[-2]

        atr = curr[atr_col]
        rsi = curr[rsi_col]
        price = curr["close"]

        # ── Check SMA crossover ─────────────────────────────────────
        signal_action = None

        if prev[fast_col] <= prev[slow_col] and curr[fast_col] > curr[slow_col]:
            if rsi < 70:
                signal_action = "BUY"

        elif prev[fast_col] >= prev[slow_col] and curr[fast_col] < curr[slow_col]:
            if rsi > 30:
                signal_action = "SELL"

        if signal_action is None:
            return None

        # ── Compute SL/TP ──────────────────────────────────────────
        if signal_action == "BUY":
            sl = price - atr * self.atr_sl_multiplier
            tp = price + atr * self.atr_tp_multiplier
        else:
            sl = price + atr * self.atr_sl_multiplier
            tp = price - atr * self.atr_tp_multiplier

        # ── ML Filter ───────────────────────────────────────────────
        ml_confidence = None
        features_json = self._build_feature_snapshot(df)
        status = "ACTIVE"

        if self.model is not None:
            try:
                feat_df = build_features(df, dropna=True)
                if len(feat_df) > 0:
                    if self._feature_cols is None:
                        self._feature_cols = get_feature_columns(feat_df)

                    x = feat_df[self._feature_cols].iloc[-1:].values
                    proba = self.model.predict_proba(x)[0]

                    # proba[1] = probability trade is profitable
                    ml_confidence = float(proba[1]) if len(proba) > 1 else float(proba[0])

                    if ml_confidence < self.confidence_threshold:
                        logger.info(
                            f"[{self.symbol}] {signal_action} filtered by ML "
                            f"(confidence {ml_confidence:.1%} < {self.confidence_threshold:.0%})"
                        )
                        status = "ML_FILTERED"
            except Exception as e:
                logger.warning(f"[{self.symbol}] ML filter error: {e}, taking trade anyway")

        # ── Build signal ────────────────────────────────────────────
        conf_str = f", ML={ml_confidence:.0%}" if ml_confidence else ""
        reason = (
            f"SMA{self.fast_period} x SMA{self.slow_period} {signal_action}, "
            f"RSI={rsi:.1f}{conf_str}"
        )

        signal = {
            "action": signal_action,
            "symbol": self.symbol,
            "price": price,
            "stop_loss": round(sl, 5),
            "take_profit": round(tp, 5),
            "atr": round(atr, 5),
            "rsi": round(rsi, 2),
            "ml_confidence": ml_confidence,
            "ml_threshold": self.confidence_threshold if self.model else None,
            "strategy": self.name,
            "reason": reason,
            "status": status,
            "features_json": features_json,
        }

        if status == "ACTIVE":
            logger.info(f"[{self.symbol}] {signal_action} signal | {reason}")
        return signal
