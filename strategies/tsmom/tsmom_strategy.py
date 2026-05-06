"""Time-Series Momentum (TSMOM) strategy.

Per Moskowitz, Ooi, Pedersen (2012) "Time Series Momentum". The
signal is the sign of the past N-day cumulative return; the position
size is scaled inversely by recent realised volatility (vol-targeting).

Phase 6 layer in the project's plan: parallel to the v3 trade
rotation, monthly rebalance, longer-horizon signal extraction.
Operates on existing v3 trade rotation; not blocked by the Phase 8
gate.

The earlier 2026-04-17 prototype delivered Sharpe 0.13 — that was a
research one-off. This module is a fresh build with proper
parameter defaults, vol-target capping, and a clear public API.

Two layers:
  - compute_tsmom_signal(): pure function over a price Series. No
    state, no time awareness. Easy to unit-test.
  - TSMOMStrategy: thin class wrapping the pure function and adding
    rebalance-timing awareness so the live engine can call it on
    every scan but only return a signal on rebalance days."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd


# ── Pure-function core ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class TSMOMSignal:
    """The output of one TSMOM signal computation.

    direction: "BUY" if cumulative return is positive, "SELL" if
        negative, "FLAT" if exactly zero (rare with floating-point
        prices but returned for completeness).
    raw_momentum: the cumulative return over `lookback_days` (a
        fraction, e.g. 0.05 means +5%).
    target_weight: position weight after vol-targeting and cap.
        Always positive — the direction sign rides on `direction`.
    vol_annualised: realised volatility annualised by sqrt(252).
        Used for diagnostics + downstream sizing checks."""
    direction: str
    raw_momentum: float
    target_weight: float
    vol_annualised: float


def compute_tsmom_signal(
    prices: pd.Series,
    *,
    lookback_days: int = 252,
    vol_window_days: int = 60,
    vol_target: float = 0.10,
    vol_floor: float = 0.01,
    weight_cap: float = 4.0,
) -> Optional[TSMOMSignal]:
    """Compute a TSMOM signal from a single instrument's price series.

    Args:
        prices: Series indexed by date (or datetime), values are
            close prices. Daily bars expected; weekly works too with
            adjusted lookback.
        lookback_days: number of bars to look back for the momentum
            signal. Default 252 = 12 months on D1.
        vol_window_days: number of bars to compute realised vol over.
            Default 60 = ~3 months.
        vol_target: target annualised vol the position is scaled to.
            Default 10% — appropriate for forex on a small portfolio.
            Raise to 0.40 for an equity-style setup.
        vol_floor: minimum annualised vol to use in the weight
            denominator. Prevents divide-by-zero / excessive
            leverage on near-zero-vol regimes (e.g. pegged FX).
        weight_cap: hard upper bound on the returned position
            weight. Caps gross exposure when vol is very low.

    Returns:
        TSMOMSignal if the input series has enough bars
        (max(lookback_days, vol_window_days) + 1). None otherwise.
        None is also returned if prices contain NaN at the lookback
        endpoints (caller should clean upstream).

    The math:
        cum_return = price_now / price_lookback - 1
        log_returns = log(price[t] / price[t-1])
        realised_vol_annualised = std(last vol_window_days log_returns) * sqrt(252)
        target_weight = min(weight_cap, vol_target / max(vol_floor, realised_vol))
        direction = "BUY" if cum_return > 0 else "SELL" if cum_return < 0 else "FLAT" """
    if prices is None or len(prices) == 0:
        return None
    if not isinstance(prices, pd.Series):
        return None

    needed = max(lookback_days, vol_window_days) + 1
    if len(prices) < needed:
        return None

    # Endpoint prices for the cumulative return — drop NaN defensively.
    p_now = prices.iloc[-1]
    p_then = prices.iloc[-1 - lookback_days]
    if pd.isna(p_now) or pd.isna(p_then) or p_then == 0:
        return None
    cum_return = float(p_now / p_then - 1.0)

    # Realised volatility on log returns over vol_window_days.
    log_rets = np.log(prices / prices.shift(1)).iloc[-vol_window_days:]
    log_rets = log_rets.dropna()
    if len(log_rets) < 2:
        return None
    daily_vol = float(log_rets.std(ddof=1))
    vol_annualised = daily_vol * np.sqrt(252.0)

    # Vol-targeted weight, capped.
    safe_vol = max(vol_floor, vol_annualised)
    target_weight = min(weight_cap, vol_target / safe_vol)

    if cum_return > 0:
        direction = "BUY"
    elif cum_return < 0:
        direction = "SELL"
    else:
        direction = "FLAT"

    return TSMOMSignal(
        direction=direction,
        raw_momentum=cum_return,
        target_weight=float(target_weight),
        vol_annualised=float(vol_annualised),
    )


# ── Rebalance timing ────────────────────────────────────────────────────────

def is_rebalance_day(
    today: pd.Timestamp,
    last_rebalance: Optional[pd.Timestamp],
    rebalance_freq: str = "monthly",
) -> bool:
    """Return True if `today` is a rebalance trigger.

    Monthly: first calendar day of a new month vs last_rebalance.
    Weekly: first calendar day of a new ISO week.
    Daily: every day (rebalance every call).

    None last_rebalance always triggers (first-time bootstrap)."""
    if rebalance_freq not in ("monthly", "weekly", "daily"):
        raise ValueError(f"unknown rebalance_freq: {rebalance_freq!r}")
    if last_rebalance is None:
        return True
    today = pd.Timestamp(today)
    last = pd.Timestamp(last_rebalance)
    if rebalance_freq == "monthly":
        return (today.year, today.month) != (last.year, last.month)
    if rebalance_freq == "weekly":
        return today.isocalendar().week != last.isocalendar().week or today.year != last.year
    # daily
    return today.date() != last.date()


# ── Engine-interface class ──────────────────────────────────────────────────

class TSMOMStrategy:
    """Engine-interface wrapper around compute_tsmom_signal().

    Designed to drop into the existing strategies/ pattern: prepare(df)
    + generate_signal(df). Difference from the H1 strategies: TSMOM
    rebalances on a monthly cadence, so generate_signal() returns a
    signal only on rebalance days and None otherwise.

    Stateful (tracks last_rebalance timestamp)."""

    def __init__(
        self,
        symbol: str,
        *,
        lookback_days: int = 252,
        vol_window_days: int = 60,
        vol_target: float = 0.10,
        vol_floor: float = 0.01,
        weight_cap: float = 4.0,
        rebalance_freq: str = "monthly",
        sl_atr_mult: float = 3.0,
        tp_atr_mult: float = 6.0,
    ):
        self.name = "tsmom"
        self.symbol = symbol
        self.lookback_days = lookback_days
        self.vol_window_days = vol_window_days
        self.vol_target = vol_target
        self.vol_floor = vol_floor
        self.weight_cap = weight_cap
        self.rebalance_freq = rebalance_freq
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult
        self.last_rebalance: Optional[pd.Timestamp] = None

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Stateless preparation. Adds derived columns the signal
        function reads. Returns the modified df (also mutates in place
        for compatibility with other strategies)."""
        # No-op for now — compute_tsmom_signal does its own derivation.
        # Hook here if the engine's caching pattern wants pre-computed
        # rolling vol etc.
        return df

    def generate_signal(self, df: pd.DataFrame) -> Optional[dict]:
        """Generate a TSMOM signal, or None if not a rebalance day.

        Args:
            df: DataFrame with columns close, atr (and a DateTimeIndex
                or a 'time' column). Must have enough rows for the
                lookback + vol windows. The last row is "today".

        Returns:
            Signal dict matching the standard project shape:
                {symbol, direction, sl, tp, atr, target_weight,
                 raw_momentum, vol_annualised}
            Or None if today isn't a rebalance day, or if there's
            insufficient data, or if the signal is FLAT."""
        if df is None or df.empty:
            return None
        # Determine today
        if isinstance(df.index, pd.DatetimeIndex):
            today = df.index[-1]
        elif "time" in df.columns:
            today = pd.Timestamp(df["time"].iloc[-1])
        else:
            return None

        if not is_rebalance_day(today, self.last_rebalance, self.rebalance_freq):
            return None

        prices = df["close"]
        sig = compute_tsmom_signal(
            prices,
            lookback_days=self.lookback_days,
            vol_window_days=self.vol_window_days,
            vol_target=self.vol_target,
            vol_floor=self.vol_floor,
            weight_cap=self.weight_cap,
        )
        if sig is None or sig.direction == "FLAT":
            return None

        # ATR-based SL/TP (matches other project strategies).
        atr = float(df["atr"].iloc[-1]) if "atr" in df.columns else 0.0
        price = float(prices.iloc[-1])
        if sig.direction == "BUY":
            sl = price - atr * self.sl_atr_mult
            tp = price + atr * self.tp_atr_mult
        else:  # SELL
            sl = price + atr * self.sl_atr_mult
            tp = price - atr * self.tp_atr_mult

        # Mark this rebalance so we don't fire again until next period.
        self.last_rebalance = today

        return {
            "symbol": self.symbol,
            "direction": sig.direction,
            "price": price,
            "sl": round(sl, 5),
            "tp": round(tp, 5),
            "atr": round(atr, 5),
            "strategy": self.name,
            "target_weight": sig.target_weight,
            "raw_momentum": sig.raw_momentum,
            "vol_annualised": sig.vol_annualised,
        }
