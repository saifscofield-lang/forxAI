"""
استراتيجية انعكاس RSI — RSI Reversal Strategy
شراء عند RSI < 35 مع بداية ارتداد، بيع عند RSI > 65 مع بداية انخفاض
استراتيجية عدوانية لجمع بيانات التدريب
"""
import json
import pandas as pd
from loguru import logger
from features.technical.indicators import add_rsi, add_atr


class RSIReversalStrategy:
    """RSI Reversal — buy oversold, sell overbought."""

    def __init__(
        self,
        symbol: str = "",
        rsi_period: int = 14,
        atr_period: int = 14,
        oversold: float = 35.0,
        overbought: float = 65.0,
        atr_sl_multiplier: float = 1.0,
        atr_tp_multiplier: float = 1.5,
    ):
        self.name = "rsi_reversal"
        self.symbol = symbol
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.oversold = oversold
        self.overbought = overbought
        self.atr_sl_multiplier = atr_sl_multiplier
        self.atr_tp_multiplier = atr_tp_multiplier

    def generate_signal(self, df: pd.DataFrame) -> dict | None:
        tmp = df.copy()
        tmp = add_rsi(tmp, self.rsi_period)
        tmp = add_atr(tmp, self.atr_period)

        rsi_col = f"rsi_{self.rsi_period}"
        atr_col = f"atr_{self.atr_period}"

        clean = tmp.dropna(subset=[rsi_col, atr_col])
        if len(clean) < 3:
            return None

        curr = clean.iloc[-1]
        prev = clean.iloc[-2]

        rsi = float(curr[rsi_col])
        rsi_prev = float(prev[rsi_col])
        atr = float(curr[atr_col])
        price = float(curr["close"])

        signal_action = None

        # BUY: RSI was oversold and is turning up
        if rsi < self.oversold and rsi > rsi_prev:
            signal_action = "BUY"

        # SELL: RSI was overbought and is turning down
        elif rsi > self.overbought and rsi < rsi_prev:
            signal_action = "SELL"

        if signal_action is None:
            return None

        if signal_action == "BUY":
            sl = price - atr * self.atr_sl_multiplier
            tp = price + atr * self.atr_tp_multiplier
        else:
            sl = price + atr * self.atr_sl_multiplier
            tp = price - atr * self.atr_tp_multiplier

        reason = f"RSI reversal {signal_action} | RSI={rsi:.1f} (prev={rsi_prev:.1f})"
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
