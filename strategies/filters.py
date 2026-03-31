"""
Shared strategy filters — STAT-003: ATR Regime Filter
Only allow signals when current ATR > threshold * average ATR(20).
Discovery: MACD winners had ATR=3.59 vs losers ATR=1.18 (119-trade analysis).
"""
import pandas as pd


def passes_atr_filter(df: pd.DataFrame, atr_col: str = "atr_14", threshold: float = 1.5) -> bool:
    """
    Check if current ATR is above threshold * average ATR(20).

    Args:
        df: DataFrame with ATR column computed
        atr_col: Name of the ATR column
        threshold: Multiplier (default 1.5x average)

    Returns:
        True if ATR is high enough for trading, False to skip.
    """
    if atr_col not in df.columns:
        return True  # Can't check, allow signal

    clean = df.dropna(subset=[atr_col])
    if len(clean) < 20:
        return True  # Not enough data, allow signal

    current_atr = float(clean.iloc[-1][atr_col])
    avg_atr = float(clean[atr_col].tail(20).mean())

    if avg_atr <= 0:
        return True

    return current_atr >= avg_atr * threshold
