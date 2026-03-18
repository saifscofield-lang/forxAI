"""
استراتيجية تقاطع MACD — MACD Crossover Strategy
شراء عند تقاطع MACD فوق خط الإشارة، بيع عند تقاطع تحته
استراتيجية عدوانية لجمع بيانات التدريب
"""
import pandas as pd
from loguru import logger
from features.technical.indicators import add_macd, add_atr


class MACDCrossoverStrategy:
    """MACD Crossover — signal on MACD/signal line cross."""

    def __init__(
        self,
        symbol: str = "",
        atr_period: int = 14,
        atr_sl_multiplier: float = 2.5,
        atr_tp_multiplier: float = 3.5,
    ):
        self.name = "macd_crossover"
        self.symbol = symbol
        self.atr_period = atr_period
        self.atr_sl_multiplier = atr_sl_multiplier
        self.atr_tp_multiplier = atr_tp_multiplier

    def generate_signal(self, df: pd.DataFrame) -> dict | None:
        tmp = df.copy()
        tmp = add_macd(tmp)
        tmp = add_atr(tmp, self.atr_period)

        atr_col = f"atr_{self.atr_period}"
        clean = tmp.dropna(subset=["macd_line", "macd_signal", atr_col])
        if len(clean) < 2:
            return None

        curr = clean.iloc[-1]
        prev = clean.iloc[-2]

        macd = float(curr["macd_line"])
        macd_sig = float(curr["macd_signal"])
        prev_macd = float(prev["macd_line"])
        prev_sig = float(prev["macd_signal"])
        atr = float(curr[atr_col])
        price = float(curr["close"])

        signal_action = None

        # BUY: MACD crosses above signal line
        if prev_macd <= prev_sig and macd > macd_sig:
            signal_action = "BUY"

        # SELL: MACD crosses below signal line
        elif prev_macd >= prev_sig and macd < macd_sig:
            signal_action = "SELL"

        if signal_action is None:
            return None

        if signal_action == "BUY":
            sl = price - atr * self.atr_sl_multiplier
            tp = price + atr * self.atr_tp_multiplier
        else:
            sl = price + atr * self.atr_sl_multiplier
            tp = price - atr * self.atr_tp_multiplier

        rsi_val = float(tmp.iloc[-1].get("rsi_14", 50)) if "rsi_14" in tmp.columns else 50.0
        reason = f"MACD crossover {signal_action} | MACD={macd:.5f} Signal={macd_sig:.5f}"
        logger.info(f"[{self.symbol}] {reason}")

        return {
            "action": signal_action,
            "symbol": self.symbol,
            "price": price,
            "stop_loss": round(sl, 5),
            "take_profit": round(tp, 5),
            "atr": round(atr, 5),
            "rsi": round(rsi_val, 2),
            "strategy": self.name,
            "reason": reason,
            "status": "ACTIVE",
        }
