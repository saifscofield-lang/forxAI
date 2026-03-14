"""
المؤشرات الفنية — Technical Indicators
RSI, MACD, ATR, Bollinger Bands, SMA, EMA
"""
import pandas as pd
import numpy as np


def add_sma(df: pd.DataFrame, period: int = 20, col: str = "close") -> pd.DataFrame:
    """Simple Moving Average"""
    df[f"sma_{period}"] = df[col].rolling(window=period).mean()
    return df


def add_ema(df: pd.DataFrame, period: int = 20, col: str = "close") -> pd.DataFrame:
    """Exponential Moving Average"""
    df[f"ema_{period}"] = df[col].ewm(span=period, adjust=False).mean()
    return df


def add_rsi(df: pd.DataFrame, period: int = 14, col: str = "close") -> pd.DataFrame:
    """Relative Strength Index"""
    delta = df[col].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    df[f"rsi_{period}"] = 100 - (100 / (1 + rs))
    return df


def add_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    col: str = "close",
) -> pd.DataFrame:
    """MACD — Moving Average Convergence Divergence"""
    ema_fast = df[col].ewm(span=fast, adjust=False).mean()
    ema_slow = df[col].ewm(span=slow, adjust=False).mean()

    df["macd_line"] = ema_fast - ema_slow
    df["macd_signal"] = df["macd_line"].ewm(span=signal, adjust=False).mean()
    df["macd_hist"] = df["macd_line"] - df["macd_signal"]
    return df


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Average True Range"""
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()

    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df[f"atr_{period}"] = true_range.ewm(alpha=1 / period, min_periods=period).mean()
    return df


def add_bollinger_bands(
    df: pd.DataFrame, period: int = 20, std_dev: float = 2.0, col: str = "close"
) -> pd.DataFrame:
    """Bollinger Bands"""
    sma = df[col].rolling(window=period).mean()
    std = df[col].rolling(window=period).std()

    df["bb_upper"] = sma + std_dev * std
    df["bb_middle"] = sma
    df["bb_lower"] = sma - std_dev * std
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
    return df


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all standard indicators to a DataFrame"""
    df = add_sma(df, 20)
    df = add_sma(df, 50)
    df = add_ema(df, 12)
    df = add_ema(df, 26)
    df = add_rsi(df, 14)
    df = add_macd(df)
    df = add_atr(df, 14)
    df = add_bollinger_bands(df, 20)
    return df
