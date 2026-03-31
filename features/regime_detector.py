"""
Market Regime Detection
Classifies market state using ADX + ATR ratio + Bollinger Band Width.
Regimes: TRENDING_BULL, TRENDING_BEAR, RANGING, VOLATILE, TRANSITIONAL
"""
import numpy as np
import pandas as pd
from loguru import logger

from features.technical.indicators import add_atr, add_bollinger_bands, add_sma


# ---------------------------------------------------------------------------
# Strategy-regime compatibility map
# ---------------------------------------------------------------------------
_REGIME_COMPATIBILITY = {
    "trend_following": {"TRENDING_BULL", "TRENDING_BEAR"},
    "mean_reversion": {"RANGING"},
    "breakout": {"VOLATILE", "TRANSITIONAL"},
    "scalping": {"RANGING", "TRANSITIONAL"},
    "momentum": {"TRENDING_BULL", "TRENDING_BEAR", "VOLATILE"},
}


# ---------------------------------------------------------------------------
# ADX computation (not in existing indicators module)
# ---------------------------------------------------------------------------
def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Average Directional Index.

    Adds ``adx_{period}`` column to the DataFrame.
    Computes +DI / -DI internally but does not persist them as columns.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    # Directional movement
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # True range
    high_low = high - low
    high_close = (high - close.shift()).abs()
    low_close = (low - close.shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

    # Smoothed averages (Wilder smoothing)
    alpha = 1 / period
    atr_smooth = true_range.ewm(alpha=alpha, min_periods=period).mean()
    plus_dm_smooth = pd.Series(plus_dm, index=df.index).ewm(
        alpha=alpha, min_periods=period
    ).mean()
    minus_dm_smooth = pd.Series(minus_dm, index=df.index).ewm(
        alpha=alpha, min_periods=period
    ).mean()

    # Directional indicators
    plus_di = 100 * plus_dm_smooth / atr_smooth.replace(0, np.nan)
    minus_di = 100 * minus_dm_smooth / atr_smooth.replace(0, np.nan)

    # ADX
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    df[f"adx_{period}"] = dx.ewm(alpha=alpha, min_periods=period).mean()

    return df


# ---------------------------------------------------------------------------
# Regime detection
# ---------------------------------------------------------------------------
def detect_regime(
    df: pd.DataFrame,
    adx_period: int = 14,
    atr_period: int = 14,
    bb_period: int = 20,
) -> pd.DataFrame:
    """Classify each bar into a market regime.

    Adds ``regime`` column with one of:
    TRENDING_BULL, TRENDING_BEAR, RANGING, VOLATILE, TRANSITIONAL.

    Required indicators are computed if their columns are missing.
    """
    # Ensure required indicators exist
    adx_col = f"adx_{adx_period}"
    atr_col = f"atr_{atr_period}"
    sma50_col = "sma_50"

    if adx_col not in df.columns:
        df = compute_adx(df, period=adx_period)
    if atr_col not in df.columns:
        df = add_atr(df, period=atr_period)
    if sma50_col not in df.columns:
        df = add_sma(df, period=50)
    if "bb_width" not in df.columns:
        df = add_bollinger_bands(df, period=bb_period)

    # ATR ratio: current ATR vs rolling 20-bar average of ATR
    atr_avg_20 = df[atr_col].rolling(window=20).mean()
    atr_ratio = df[atr_col] / atr_avg_20.replace(0, np.nan)

    adx = df[adx_col]
    price = df["close"]
    sma50 = df[sma50_col]

    # Classification (applied in priority order)
    conditions = [
        (adx > 25) & (price > sma50),   # TRENDING_BULL
        (adx > 25) & (price < sma50),   # TRENDING_BEAR
        (atr_ratio > 2.0),              # VOLATILE (checked before RANGING)
        (adx < 20) & (atr_ratio < 1.0), # RANGING
    ]
    choices = [
        "TRENDING_BULL",
        "TRENDING_BEAR",
        "VOLATILE",
        "RANGING",
    ]

    df["regime"] = np.select(conditions, choices, default="TRANSITIONAL")

    # Store intermediate values used by get_current_regime
    df["_atr_ratio"] = atr_ratio

    logger.debug(
        "Regime detection complete — last regime: {}",
        df["regime"].iloc[-1] if len(df) > 0 else "N/A",
    )

    return df


# ---------------------------------------------------------------------------
# Current regime snapshot
# ---------------------------------------------------------------------------
def get_current_regime(df: pd.DataFrame) -> dict:
    """Return a summary dict for the most recent bar.

    Keys: regime, adx_value, atr_ratio, bb_width, confidence.

    ``confidence`` is a simple heuristic:
      - 1.0 when ADX > 35 or ATR ratio > 2.5 (strong signal)
      - 0.7 when ADX > 25 or ATR ratio > 1.5
      - 0.4 for TRANSITIONAL states
    """
    if "regime" not in df.columns:
        df = detect_regime(df)

    last = df.iloc[-1]
    regime = last["regime"]

    adx_value = last.get("adx_14", np.nan)
    atr_ratio = last.get("_atr_ratio", np.nan)
    bb_width = last.get("bb_width", np.nan)

    # Confidence heuristic
    if regime in ("TRENDING_BULL", "TRENDING_BEAR") and adx_value > 35:
        confidence = 1.0
    elif regime == "VOLATILE" and atr_ratio > 2.5:
        confidence = 1.0
    elif regime in ("TRENDING_BULL", "TRENDING_BEAR"):
        confidence = 0.7
    elif regime in ("VOLATILE", "RANGING"):
        confidence = 0.7
    else:
        confidence = 0.4

    return {
        "regime": regime,
        "adx_value": round(float(adx_value), 2) if not np.isnan(adx_value) else None,
        "atr_ratio": round(float(atr_ratio), 2) if not np.isnan(atr_ratio) else None,
        "bb_width": round(float(bb_width), 4) if not np.isnan(bb_width) else None,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Strategy compatibility check
# ---------------------------------------------------------------------------
def is_strategy_compatible(regime: str, strategy_regime_target: str) -> bool:
    """Check whether a regime is compatible with a strategy's target style.

    Known targets: ANY, TRENDING, RANGING, VOLATILE, trend_following,
    mean_reversion, breakout, scalping, momentum.
    Unknown targets default to compatible (returns True) to avoid blocking.
    """
    if not strategy_regime_target or strategy_regime_target.upper() == "ANY":
        return True

    target_upper = strategy_regime_target.upper()

    # Direct regime name matching
    if target_upper == "TRENDING":
        return regime in {"TRENDING_BULL", "TRENDING_BEAR"}
    if target_upper == "RANGING":
        return regime == "RANGING"
    if target_upper == "VOLATILE":
        return regime == "VOLATILE"
    if target_upper == regime:
        return True

    # Style-based matching
    compatible = _REGIME_COMPATIBILITY.get(strategy_regime_target, None)
    if compatible is None:
        return True  # Unknown target = don't block
    return regime in compatible
