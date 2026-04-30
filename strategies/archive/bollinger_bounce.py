"""
استراتيجية ارتداد بولنجر — Bollinger Bounce Strategy v2.0
IMP-16: Only fire in range/low-volatility markets (BB Width filter)
IMP-64: Bounce confirmation (prev outside → curr inside) + RSI 40/60 + BB width 2x avg filter
"""
import pandas as pd
from loguru import logger
from features.technical.indicators import add_bollinger_bands, add_atr, add_rsi
from strategies.filters import passes_atr_filter


class BollingerBounceStrategy:
    """Bollinger Bounce v2.0 — confirmed reversal at bands with RSI + BB width filters."""
    VERSION = "2.0"

    def __init__(
        self,
        symbol: str = "",
        bb_period: int = 20,
        atr_period: int = 14,
        atr_sl_multiplier: float = 2.0,
        atr_tp_multiplier: float = 3.0,
        max_bb_width_pct: float = 0.03,  # IMP-16: max BB width as % of price
    ):
        self.name = "bollinger_bounce"
        self.symbol = symbol
        self.bb_period = bb_period
        self.atr_period = atr_period
        self.atr_sl_multiplier = atr_sl_multiplier
        self.atr_tp_multiplier = atr_tp_multiplier
        self.max_bb_width_pct = max_bb_width_pct

    def generate_signal(self, df: pd.DataFrame) -> dict | None:
        tmp = df.copy()
        tmp = add_bollinger_bands(tmp, self.bb_period)
        tmp = add_atr(tmp, self.atr_period)
        tmp = add_rsi(tmp, 14)

        atr_col = f"atr_{self.atr_period}"
        clean = tmp.dropna(subset=["bb_upper", "bb_lower", atr_col, "rsi_14"])
        if len(clean) < 20:
            return None

        # STAT-003: ATR regime filter (lower threshold for mean-reversion)
        if not passes_atr_filter(clean, atr_col, threshold=1.0):
            return None

        curr = clean.iloc[-1]
        prev = clean.iloc[-2]

        price = float(curr["close"])
        bb_upper = float(curr["bb_upper"])
        bb_lower = float(curr["bb_lower"])
        prev_price = float(prev["close"])
        prev_bb_lower = float(prev["bb_lower"])
        prev_bb_upper = float(prev["bb_upper"])
        atr = float(curr[atr_col])
        rsi = float(curr["rsi_14"])

        # IMP-16: Block BB signals in trending/volatile markets
        bb_width_pct = (bb_upper - bb_lower) / price if price > 0 else 0
        if bb_width_pct > self.max_bb_width_pct:
            return None

        signal_action = None

        # IMP-64: Confirmation — prev candle was OUTSIDE band, current closed BACK INSIDE
        if prev_price <= prev_bb_lower and price > bb_lower:
            signal_action = "BUY"
        elif prev_price >= prev_bb_upper and price < bb_upper:
            signal_action = "SELL"

        if signal_action is None:
            return None

        # IMP-64: RSI must confirm the reversal (forex thresholds: 40/60)
        if signal_action == "BUY" and rsi > 40:
            return None
        if signal_action == "SELL" and rsi < 60:
            return None

        # IMP-64: BB Width expanding filter — don't counter strong momentum
        bb_width = bb_upper - bb_lower
        bb_width_avg = float((clean["bb_upper"] - clean["bb_lower"]).tail(20).mean())
        if bb_width > bb_width_avg * 2.0:
            return None

        if signal_action == "BUY":
            sl = price - atr * self.atr_sl_multiplier
            tp = price + atr * self.atr_tp_multiplier
        else:
            sl = price + atr * self.atr_sl_multiplier
            tp = price - atr * self.atr_tp_multiplier

        bb_range = bb_upper - bb_lower
        bb_pos = (price - bb_lower) / bb_range if bb_range > 0 else 0.5
        reason = (
            f"BB bounce {signal_action} | BB_pos={bb_pos:.2f} RSI={rsi:.1f} "
            f"BBW={bb_width_pct:.4f} BBW_avg_ratio={bb_width/bb_width_avg:.2f}"
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
