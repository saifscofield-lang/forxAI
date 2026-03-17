"""
استراتيجية ارتداد بولنجر — Bollinger Bounce Strategy
شراء عند لمس الحد السفلي، بيع عند لمس الحد العلوي (Mean Reversion)
استراتيجية عدوانية لجمع بيانات التدريب
"""
import pandas as pd
from loguru import logger
from features.technical.indicators import add_bollinger_bands, add_atr, add_rsi


class BollingerBounceStrategy:
    """Bollinger Bounce — buy at lower band, sell at upper band."""

    def __init__(
        self,
        symbol: str = "",
        bb_period: int = 20,
        atr_period: int = 14,
        atr_sl_multiplier: float = 1.0,
        atr_tp_multiplier: float = 1.5,
    ):
        self.name = "bollinger_bounce"
        self.symbol = symbol
        self.bb_period = bb_period
        self.atr_period = atr_period
        self.atr_sl_multiplier = atr_sl_multiplier
        self.atr_tp_multiplier = atr_tp_multiplier

    def generate_signal(self, df: pd.DataFrame) -> dict | None:
        tmp = df.copy()
        tmp = add_bollinger_bands(tmp, self.bb_period)
        tmp = add_atr(tmp, self.atr_period)
        tmp = add_rsi(tmp, 14)

        atr_col = f"atr_{self.atr_period}"
        clean = tmp.dropna(subset=["bb_upper", "bb_lower", atr_col])
        if len(clean) < 2:
            return None

        curr = clean.iloc[-1]
        price = float(curr["close"])
        bb_upper = float(curr["bb_upper"])
        bb_lower = float(curr["bb_lower"])
        atr = float(curr[atr_col])
        rsi = float(curr.get("rsi_14", 50))

        signal_action = None

        # BUY: price at or below lower Bollinger Band
        if price <= bb_lower:
            signal_action = "BUY"

        # SELL: price at or above upper Bollinger Band
        elif price >= bb_upper:
            signal_action = "SELL"

        if signal_action is None:
            return None

        if signal_action == "BUY":
            sl = price - atr * self.atr_sl_multiplier
            tp = price + atr * self.atr_tp_multiplier
        else:
            sl = price + atr * self.atr_sl_multiplier
            tp = price - atr * self.atr_tp_multiplier

        bb_range = bb_upper - bb_lower
        bb_pos = (price - bb_lower) / bb_range if bb_range > 0 else 0.5
        reason = f"BB bounce {signal_action} | BB_pos={bb_pos:.2f} RSI={rsi:.1f}"
        logger.info(f"[{self.symbol}] {reason}")

        return {
            "action": signal_action,
            "symbol": self.symbol,
            "price": price,
            "stop_loss": round(sl, 5),
            "take_profit": round(tp, 5),
            "atr": round(atr, 5),
            "rsi": round(rsi, 2),
            "strategy": self.name,
            "reason": reason,
            "status": "ACTIVE",
        }
