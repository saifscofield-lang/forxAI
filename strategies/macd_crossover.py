"""
استراتيجية تقاطع MACD — MACD Crossover Strategy v2.0
IMP-63: EMA50/200 trend confirmation + histogram momentum filter
شراء فقط في ترند صاعد مؤكد، بيع فقط في ترند هابط مؤكد
"""
import pandas as pd
from loguru import logger
from features.technical.indicators import add_macd, add_atr, add_ema


class MACDCrossoverStrategy:
    """MACD Crossover v2.0 — signal on MACD/signal line cross with EMA trend + histogram momentum."""
    VERSION = "2.0"

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
        tmp = add_ema(tmp, 50)
        tmp = add_ema(tmp, 200)

        atr_col = f"atr_{self.atr_period}"
        clean = tmp.dropna(subset=["macd_line", "macd_signal", "macd_hist", atr_col, "ema_50", "ema_200"])
        if len(clean) < 2:
            return None

        curr = clean.iloc[-1]
        prev = clean.iloc[-2]

        macd = float(curr["macd_line"])
        macd_sig = float(curr["macd_signal"])
        prev_macd = float(prev["macd_line"])
        prev_sig = float(prev["macd_signal"])
        hist = float(curr["macd_hist"])
        prev_hist = float(prev["macd_hist"])
        atr = float(curr[atr_col])
        price = float(curr["close"])
        ema_50 = float(curr["ema_50"])
        ema_200 = float(curr["ema_200"])

        signal_action = None

        # BUY: MACD crosses above signal line + confirmed uptrend
        if prev_macd <= prev_sig and macd > macd_sig:
            if price > ema_50 and ema_50 > ema_200:
                signal_action = "BUY"

        # SELL: MACD crosses below signal line + confirmed downtrend
        elif prev_macd >= prev_sig and macd < macd_sig:
            if price < ema_50 and ema_50 < ema_200:
                signal_action = "SELL"

        if signal_action is None:
            return None

        # Histogram momentum must be increasing in signal direction
        if signal_action == "BUY" and hist <= prev_hist:
            return None
        if signal_action == "SELL" and hist >= prev_hist:
            return None

        if signal_action == "BUY":
            sl = price - atr * self.atr_sl_multiplier
            tp = price + atr * self.atr_tp_multiplier
        else:
            sl = price + atr * self.atr_sl_multiplier
            tp = price - atr * self.atr_tp_multiplier

        rsi_val = float(tmp.iloc[-1].get("rsi_14", 50)) if "rsi_14" in tmp.columns else 50.0
        reason = (
            f"MACD crossover {signal_action} | MACD={macd:.5f} Signal={macd_sig:.5f} "
            f"Hist={hist:.5f} | EMA50={ema_50:.5f} EMA200={ema_200:.5f}"
        )
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
            "strategy_version": self.VERSION,
            "reason": reason,
            "status": "ACTIVE",
        }
