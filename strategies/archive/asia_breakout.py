"""
Asia Range Breakout Strategy (SES-001)
Asia session (22:00-08:00 GMT) builds a range. London breaks it
in the first 2 hours (08:00-10:00 GMT) with momentum continuation.

Edge: London institutional traders need Asia's accumulated liquidity
      to start their directional move — this is structural, not optional.

Entry: Break of Asia high/low in first 2 hours of London + ATR confirmation
Invalidation: Fridays, before NFP, holidays
Regime: ANY (session mechanics work in all regimes)
Pairs: GBPUSD, EURUSD, USDJPY
TF: H1 (designed for hourly bars)
"""
import pandas as pd
import numpy as np
from loguru import logger
from features.technical.indicators import add_atr, add_rsi


class AsiaBreakoutStrategy:
    """SES-001: Asia Range Breakout — trade London's break of Asia range."""
    VERSION = "1.0"

    def __init__(
        self,
        symbol: str = "",
        asia_start_hour: int = 22,   # GMT
        asia_end_hour: int = 8,      # GMT
        london_window_hours: int = 2, # hours after asia_end to look for breakout
        min_range_pips: float = 20.0,
        max_range_pips: float = 80.0,
        atr_period: int = 14,
        atr_sl_multiplier: float = 1.5,
        atr_tp_multiplier: float = 2.5,
        pip_value: float = 0.0001,
    ):
        self.name = "asia_breakout"
        self.symbol = symbol
        self.asia_start_hour = asia_start_hour
        self.asia_end_hour = asia_end_hour
        self.london_window_hours = london_window_hours
        self.min_range_pips = min_range_pips
        self.max_range_pips = max_range_pips
        self.atr_period = atr_period
        self.atr_sl_multiplier = atr_sl_multiplier
        self.atr_tp_multiplier = atr_tp_multiplier
        self.pip_value = pip_value
        self.regime_target = "ANY"

    def _get_asia_range(self, df: pd.DataFrame) -> tuple:
        """Find the most recent Asia session range (high, low)."""
        if "time" not in df.columns:
            return None, None

        df_with_hour = df.copy()
        df_with_hour["hour"] = pd.to_datetime(df_with_hour["time"]).dt.hour

        # Asia session: 22:00 to 08:00 GMT
        # For H1 bars, select bars where hour is in Asia range
        asia_mask = (df_with_hour["hour"] >= self.asia_start_hour) | (df_with_hour["hour"] < self.asia_end_hour)
        asia_bars = df_with_hour[asia_mask]

        if len(asia_bars) < 3:
            return None, None

        # Get the most recent complete Asia session (last N asia bars before London open)
        # Find the last bar that's still in Asia (hour < 8)
        recent_asia = asia_bars.tail(10)  # Last ~10 hours of Asia

        asia_high = float(recent_asia["high"].max())
        asia_low = float(recent_asia["low"].min())

        return asia_high, asia_low

    def _is_london_window(self, df: pd.DataFrame) -> bool:
        """Check if current bar is within the London breakout window (08:00-10:00 GMT)."""
        if "time" not in df.columns:
            return False

        last_time = pd.to_datetime(df.iloc[-1]["time"])
        hour = last_time.hour
        return self.asia_end_hour <= hour < (self.asia_end_hour + self.london_window_hours)

    def _is_friday(self, df: pd.DataFrame) -> bool:
        """Check if current bar is Friday (filter out)."""
        if "time" not in df.columns:
            return False
        last_time = pd.to_datetime(df.iloc[-1]["time"])
        return last_time.weekday() == 4  # Friday

    def generate_signal(self, df: pd.DataFrame) -> dict | None:
        tmp = df.copy()
        tmp = add_atr(tmp, self.atr_period)
        tmp = add_rsi(tmp, 14)

        atr_col = f"atr_{self.atr_period}"
        clean = tmp.dropna(subset=[atr_col, "rsi_14"])
        if len(clean) < 30:
            return None

        # Skip Fridays
        if self._is_friday(clean):
            return None

        # Must be in London window
        if not self._is_london_window(clean):
            return None

        curr = clean.iloc[-1]
        atr = float(curr[atr_col])
        rsi = float(curr["rsi_14"])
        price = float(curr["close"])
        curr_high = float(curr["high"])
        curr_low = float(curr["low"])

        # Get Asia range
        asia_high, asia_low = self._get_asia_range(clean.iloc[:-2])  # Exclude last 2 bars (London)
        if asia_high is None:
            return None

        # Scale pip value
        pip = self.pip_value
        if self.symbol and "JPY" in self.symbol:
            pip = 0.01
        if self.symbol and "XAU" in self.symbol:
            pip = 0.01

        asia_range_pips = (asia_high - asia_low) / pip
        if asia_range_pips < self.min_range_pips or asia_range_pips > self.max_range_pips:
            return None

        # ATR filter: need decent volatility for breakout
        atr_avg = float(clean[atr_col].tail(20).mean())
        if atr < atr_avg * 0.8:
            return None

        signal_action = None

        # Bullish breakout: price breaks above Asia high
        if curr_high > asia_high and price > asia_high:
            signal_action = "BUY"

        # Bearish breakout: price breaks below Asia low
        elif curr_low < asia_low and price < asia_low:
            signal_action = "SELL"

        if signal_action is None:
            return None

        # RSI should confirm direction (not extreme counter)
        if signal_action == "BUY" and rsi < 30:
            return None  # Too oversold for a bullish breakout
        if signal_action == "SELL" and rsi > 70:
            return None  # Too overbought for a bearish breakout

        if signal_action == "BUY":
            sl = price - atr * self.atr_sl_multiplier
            tp = price + atr * self.atr_tp_multiplier
        else:
            sl = price + atr * self.atr_sl_multiplier
            tp = price - atr * self.atr_tp_multiplier

        reason = (
            f"Asia Breakout {signal_action} | "
            f"Asia H={asia_high:.5f} L={asia_low:.5f} Range={asia_range_pips:.0f}p | "
            f"RSI={rsi:.1f} ATR={atr:.5f}"
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
