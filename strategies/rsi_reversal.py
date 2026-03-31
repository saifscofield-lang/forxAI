"""
استراتيجية انعكاس RSI — RSI Reversal Strategy v1.1
IMP-65: 2-bar RSI confirmation + price direction check
شراء عند RSI < oversold مع ارتداد مؤكد لشريطين، بيع عند RSI > overbought مع انخفاض لشريطين
"""
import json
import pandas as pd
from loguru import logger
from features.technical.indicators import add_rsi, add_atr
from strategies.filters import passes_atr_filter


class RSIReversalStrategy:
    """RSI Reversal v1.1 — 2-bar confirmation + price direction check."""
    VERSION = "1.1"

    def __init__(
        self,
        symbol: str = "",
        rsi_period: int = 14,
        atr_period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        atr_sl_multiplier: float = 2.0,
        atr_tp_multiplier: float = 3.0,
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
        if len(clean) < 4:
            return None

        # STAT-003: ATR regime filter
        if not passes_atr_filter(clean, atr_col, threshold=1.5):
            return None

        curr = clean.iloc[-1]
        prev = clean.iloc[-2]
        prev2 = clean.iloc[-3]

        rsi = float(curr[rsi_col])
        rsi_prev = float(prev[rsi_col])
        rsi_2bars = float(prev2[rsi_col])
        atr = float(curr[atr_col])
        price = float(curr["close"])
        prev_close = float(prev["close"])

        signal_action = None

        # IMP-65: 2-bar RSI confirmation (RSI turning for 2 consecutive bars)
        if rsi < self.oversold and rsi > rsi_prev and rsi_prev > rsi_2bars:
            signal_action = "BUY"
        elif rsi > self.overbought and rsi < rsi_prev and rsi_prev < rsi_2bars:
            signal_action = "SELL"

        if signal_action is None:
            return None

        # IMP-65: Price must confirm reversal direction
        if signal_action == "BUY" and price < prev_close:
            return None
        if signal_action == "SELL" and price > prev_close:
            return None

        if signal_action == "BUY":
            sl = price - atr * self.atr_sl_multiplier
            tp = price + atr * self.atr_tp_multiplier
        else:
            sl = price + atr * self.atr_sl_multiplier
            tp = price - atr * self.atr_tp_multiplier

        reason = (
            f"RSI reversal {signal_action} | RSI={rsi:.1f} "
            f"(prev={rsi_prev:.1f}, 2bars={rsi_2bars:.1f}) price_confirm=yes"
        )
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
            "strategy_version": self.VERSION,
            "reason": reason,
            "status": "ACTIVE",
        }
