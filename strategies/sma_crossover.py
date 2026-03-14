"""
استراتيجية تقاطع المتوسطات — SMA Crossover Strategy
إشارة شراء: SMA السريع يقطع البطيء للأعلى + RSI < 70
إشارة بيع: SMA السريع يقطع البطيء للأسفل + RSI > 30
"""
import pandas as pd
from loguru import logger
from features.technical.indicators import add_sma, add_rsi, add_atr


class SMACrossoverStrategy:
    """Simple SMA Crossover with RSI filter"""

    def __init__(
        self,
        fast_period: int = 20,
        slow_period: int = 50,
        rsi_period: int = 14,
        atr_period: int = 14,
        atr_sl_multiplier: float = 1.5,
        atr_tp_multiplier: float = 2.0,
    ):
        self.name = "sma_crossover"
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.atr_sl_multiplier = atr_sl_multiplier
        self.atr_tp_multiplier = atr_tp_multiplier

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add required indicators to the DataFrame"""
        df = add_sma(df, self.fast_period)
        df = add_sma(df, self.slow_period)
        df = add_rsi(df, self.rsi_period)
        df = add_atr(df, self.atr_period)
        return df

    def generate_signal(self, df: pd.DataFrame) -> dict | None:
        """
        Analyze the latest bars and generate a trade signal.
        Returns dict with signal info or None.
        """
        df = self.prepare(df.copy())

        fast_col = f"sma_{self.fast_period}"
        slow_col = f"sma_{self.slow_period}"
        rsi_col = f"rsi_{self.rsi_period}"
        atr_col = f"atr_{self.atr_period}"

        # Need at least slow_period + 1 bars
        if len(df) < self.slow_period + 2:
            return None

        # Drop NaN rows for indicator columns
        required = [fast_col, slow_col, rsi_col, atr_col]
        clean = df.dropna(subset=required)
        if len(clean) < 2:
            return None

        curr = clean.iloc[-1]
        prev = clean.iloc[-2]

        atr = curr[atr_col]
        rsi = curr[rsi_col]
        price = curr["close"]

        # BUY signal: fast crosses above slow
        if prev[fast_col] <= prev[slow_col] and curr[fast_col] > curr[slow_col]:
            if rsi < 70:  # Not overbought
                sl = price - atr * self.atr_sl_multiplier
                tp = price + atr * self.atr_tp_multiplier
                signal = {
                    "action": "BUY",
                    "symbol": curr.get("symbol", ""),
                    "price": price,
                    "stop_loss": round(sl, 5),
                    "take_profit": round(tp, 5),
                    "atr": round(atr, 5),
                    "rsi": round(rsi, 2),
                    "strategy": self.name,
                    "reason": f"SMA{self.fast_period} crossed above SMA{self.slow_period}, RSI={rsi:.1f}",
                }
                logger.info(f"📈 BUY signal | {signal['reason']}")
                return signal

        # SELL signal: fast crosses below slow
        if prev[fast_col] >= prev[slow_col] and curr[fast_col] < curr[slow_col]:
            if rsi > 30:  # Not oversold
                sl = price + atr * self.atr_sl_multiplier
                tp = price - atr * self.atr_tp_multiplier
                signal = {
                    "action": "SELL",
                    "symbol": curr.get("symbol", ""),
                    "price": price,
                    "stop_loss": round(sl, 5),
                    "take_profit": round(tp, 5),
                    "atr": round(atr, 5),
                    "rsi": round(rsi, 2),
                    "strategy": self.name,
                    "reason": f"SMA{self.fast_period} crossed below SMA{self.slow_period}, RSI={rsi:.1f}",
                }
                logger.info(f"📉 SELL signal | {signal['reason']}")
                return signal

        return None
