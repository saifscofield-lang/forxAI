"""
Stop Hunt Reversal Strategy (LIQ-001)
Detects liquidity grabs: price breaks a swing high/low by a few pips,
then reverses — indicating institutional stop hunting.

Edge: Market makers need the liquidity sitting at obvious levels.
      After sweeping those stops, the real move is in the opposite direction.

Entry: Swing high/low broken by 3-15 pips + reversal candle within 2 bars
Invalidation: Price closes far beyond the broken level for > 3 bars
Regime: RANGING (stop hunts are most reliable in range-bound markets)
Pairs: EURUSD, GBPUSD, XAUUSD
TF: H1, H4
"""
import pandas as pd
import numpy as np
from loguru import logger
from features.technical.indicators import add_atr, add_rsi


class StopHuntReversalStrategy:
    """LIQ-001: Stop Hunt Reversal — fade the liquidity grab."""
    VERSION = "1.0"

    def __init__(
        self,
        symbol: str = "",
        lookback: int = 20,
        min_sweep_pips: float = 3.0,
        max_sweep_pips: float = 15.0,
        atr_period: int = 14,
        atr_sl_multiplier: float = 2.0,
        atr_tp_multiplier: float = 3.0,
        pip_value: float = 0.0001,
    ):
        self.name = "stop_hunt_reversal"
        self.symbol = symbol
        self.lookback = lookback
        self.min_sweep_pips = min_sweep_pips
        self.max_sweep_pips = max_sweep_pips
        self.atr_period = atr_period
        self.atr_sl_multiplier = atr_sl_multiplier
        self.atr_tp_multiplier = atr_tp_multiplier
        self.pip_value = pip_value
        self.regime_target = "RANGING"

    def generate_signal(self, df: pd.DataFrame) -> dict | None:
        tmp = df.copy()
        tmp = add_atr(tmp, self.atr_period)
        tmp = add_rsi(tmp, 14)

        atr_col = f"atr_{self.atr_period}"
        clean = tmp.dropna(subset=[atr_col, "rsi_14"])
        if len(clean) < self.lookback + 5:
            return None

        curr = clean.iloc[-1]
        prev = clean.iloc[-2]
        atr = float(curr[atr_col])
        rsi = float(curr["rsi_14"])
        price = float(curr["close"])

        # ATR regime filter: skip low volatility
        atr_avg = float(clean[atr_col].tail(20).mean())
        if atr < atr_avg * 0.5:
            return None

        # Find swing high and swing low over lookback period (excluding last 2 bars)
        window = clean.iloc[-(self.lookback + 2):-2]
        swing_high = float(window["high"].max())
        swing_low = float(window["low"].min())

        # Scale sweep thresholds by pip value
        pip = self.pip_value
        if self.symbol and "JPY" in self.symbol:
            pip = 0.01
        if self.symbol and "XAU" in self.symbol:
            pip = 0.01

        min_sweep = self.min_sweep_pips * pip
        max_sweep = self.max_sweep_pips * pip

        signal_action = None
        sweep_type = None

        # Check for HIGH sweep (bearish stop hunt → BUY signal is wrong, SELL after sweep up)
        # Actually: price spikes ABOVE swing high (hunting buy stops), then reverses DOWN
        # But we fade it: the real move after stop hunt of highs is often continuation or reversal
        # Standard: sweep of highs = sell, sweep of lows = buy

        curr_high = float(curr["high"])
        curr_low = float(curr["low"])
        prev_high = float(prev["high"])

        # Sweep of swing HIGH: wick above but close back below
        sweep_above = curr_high - swing_high
        if min_sweep <= sweep_above <= max_sweep and price < swing_high:
            # Price swept above swing high but closed back below = bearish rejection
            if rsi > 50:  # RSI confirms overbought tendency
                signal_action = "SELL"
                sweep_type = f"HIGH sweep +{sweep_above/pip:.1f} pips"

        # Sweep of swing LOW: wick below but close back above
        sweep_below = swing_low - curr_low
        if min_sweep <= sweep_below <= max_sweep and price > swing_low:
            # Price swept below swing low but closed back above = bullish rejection
            if rsi < 50:  # RSI confirms oversold tendency
                signal_action = "BUY"
                sweep_type = f"LOW sweep +{sweep_below/pip:.1f} pips"

        if signal_action is None:
            return None

        # Reversal candle confirmation: current bar should have a rejection wick
        body = abs(price - float(curr["open"]))
        full_range = curr_high - curr_low
        if full_range > 0 and body / full_range > 0.7:
            # Body too large relative to range — no rejection wick
            return None

        if signal_action == "BUY":
            sl = price - atr * self.atr_sl_multiplier
            tp = price + atr * self.atr_tp_multiplier
        else:
            sl = price + atr * self.atr_sl_multiplier
            tp = price - atr * self.atr_tp_multiplier

        reason = (
            f"Stop Hunt {signal_action} | {sweep_type} | "
            f"RSI={rsi:.1f} ATR={atr:.5f} Swing H={swing_high:.5f} L={swing_low:.5f}"
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
