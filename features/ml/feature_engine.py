"""
Feature Engineering for ML Models.
Builds 40+ features from OHLCV data for LightGBM signal prediction.
All features are computed from PAST data only — no look-ahead bias.
"""
import numpy as np
import pandas as pd
from features.technical.indicators import (
    add_sma, add_ema, add_rsi, add_macd, add_atr, add_bollinger_bands,
)


def build_features(df: pd.DataFrame, dropna: bool = True) -> pd.DataFrame:
    """
    Build all ML features from OHLCV DataFrame.

    Parameters
    ----------
    df : DataFrame with columns: time, open, high, low, close, volume
    dropna : whether to drop rows with NaN (warmup period)

    Returns
    -------
    DataFrame with original columns + all feature columns
    """
    df = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    open_ = df["open"]
    volume = df["volume"]

    # ── 1. Price Returns ─────────────────────────────────────────────
    for lag in [1, 2, 3, 5, 10, 20]:
        df[f"return_{lag}"] = close.pct_change(lag)

    # ── 2. Trend Indicators ──────────────────────────────────────────
    for p in [10, 20, 50, 100, 200]:
        df = add_sma(df, p)
        df[f"close_vs_sma_{p}"] = (close - df[f"sma_{p}"]) / df[f"sma_{p}"]

    for p in [12, 26, 50]:
        df = add_ema(df, p)

    # SMA crossover signals (as continuous features)
    df["sma_10_50_diff"] = (df["sma_10"] - df["sma_50"]) / df["sma_50"]
    df["sma_20_100_diff"] = (df["sma_20"] - df["sma_100"]) / df["sma_100"]
    df["sma_50_200_diff"] = (df["sma_50"] - df["sma_200"]) / df["sma_200"]

    # EMA crossover
    df["ema_12_26_diff"] = (df["ema_12"] - df["ema_26"]) / df["ema_26"]

    # ── 3. Momentum Indicators ───────────────────────────────────────
    for p in [7, 14, 21]:
        df = add_rsi(df, p)

    df = add_macd(df)

    # Rate of change
    for p in [5, 10, 20]:
        df[f"roc_{p}"] = close.pct_change(p) * 100

    # ── 4. Volatility Indicators ─────────────────────────────────────
    for p in [7, 14, 28]:
        df = add_atr(df, p)
        df[f"atr_{p}_pct"] = df[f"atr_{p}"] / close  # ATR as % of price

    df = add_bollinger_bands(df, 20)

    # Bollinger Band position (0-1 scale)
    bb_range = df["bb_upper"] - df["bb_lower"]
    df["bb_position"] = (close - df["bb_lower"]) / bb_range.replace(0, np.nan)

    # Historical volatility
    for p in [10, 20]:
        df[f"volatility_{p}"] = close.pct_change().rolling(p).std() * np.sqrt(252 * 24)

    # ── 5. Candle Patterns ───────────────────────────────────────────
    body = close - open_
    total_range = high - low
    total_range = total_range.replace(0, np.nan)

    df["candle_body_ratio"] = body.abs() / total_range
    df["candle_direction"] = np.sign(body)  # 1=bullish, -1=bearish
    df["upper_shadow_ratio"] = (high - np.maximum(close, open_)) / total_range
    df["lower_shadow_ratio"] = (np.minimum(close, open_) - low) / total_range

    # Consecutive candle direction
    direction = np.sign(body)
    df["consecutive_direction"] = _consecutive_count(direction.values)

    # ── 6. Support/Resistance (local highs/lows) ─────────────────────
    for p in [10, 20, 50]:
        df[f"high_{p}"] = high.rolling(p).max()
        df[f"low_{p}"] = low.rolling(p).min()
        range_p = df[f"high_{p}"] - df[f"low_{p}"]
        df[f"price_position_{p}"] = (close - df[f"low_{p}"]) / range_p.replace(0, np.nan)

    # Distance from recent high/low
    df["dist_from_high_20"] = (close - df["high_20"]) / close
    df["dist_from_low_20"] = (close - df["low_20"]) / close

    # ── 7. Volume Features ───────────────────────────────────────────
    if (volume > 0).any():
        vol_sma_20 = volume.rolling(20).mean()
        df["volume_ratio"] = volume / vol_sma_20.replace(0, np.nan)
        df["volume_change"] = volume.pct_change()
        df["volume_ma_5"] = volume.rolling(5).mean()
        df["volume_ma_20"] = vol_sma_20
    else:
        df["volume_ratio"] = 0
        df["volume_change"] = 0
        df["volume_ma_5"] = 0
        df["volume_ma_20"] = 0

    # ── 8. Time Features ─────────────────────────────────────────────
    if "time" in df.columns:
        dt = pd.to_datetime(df["time"])
        df["hour"] = dt.dt.hour
        df["day_of_week"] = dt.dt.dayofweek  # 0=Mon, 4=Fri

        # Trading session (London=8-16, NY=13-21, Asia=0-8 UTC)
        hour = dt.dt.hour
        df["session_london"] = ((hour >= 8) & (hour < 16)).astype(int)
        df["session_ny"] = ((hour >= 13) & (hour < 21)).astype(int)
        df["session_asia"] = ((hour >= 0) & (hour < 8)).astype(int)

        # Hour cyclical encoding (for tree models to understand wrap-around)
        df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
        df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
        df["dow_sin"] = np.sin(2 * np.pi * dt.dt.dayofweek / 5)
        df["dow_cos"] = np.cos(2 * np.pi * dt.dt.dayofweek / 5)

    # ── 9. Lag Features (shifted values for sequence context) ────────
    for lag in [1, 2, 3]:
        df[f"rsi_14_lag{lag}"] = df["rsi_14"].shift(lag)
        df[f"macd_hist_lag{lag}"] = df["macd_hist"].shift(lag)
        df[f"return_1_lag{lag}"] = df["return_1"].shift(lag)

    # RSI momentum (change in RSI)
    df["rsi_14_change"] = df["rsi_14"].diff()
    df["macd_hist_change"] = df["macd_hist"].diff()

    # ── 10. Relative Features (Report P1 — cross-pair comparable) ────
    # RSI distance from neutral (more meaningful than absolute value)
    df["rsi_14_dist_50"] = df["rsi_14"] - 50
    df["rsi_7_dist_50"] = df["rsi_7"] - 50

    # ATR ratio: current vs rolling average (volatility regime signal)
    atr_sma_20 = df["atr_14"].rolling(20).mean()
    df["atr_ratio_20"] = df["atr_14"] / atr_sma_20.replace(0, np.nan)

    # Spread vs ATR (execution cost relative to move size)
    if "spread" in df.columns:
        df["spread_vs_atr"] = df["spread"] / df["atr_14"].replace(0, np.nan)

    # Price vs 24h high/low normalized by ATR
    df["price_vs_high_20_atr"] = (close - high.rolling(20).max()) / df["atr_14"].replace(0, np.nan)
    df["price_vs_low_20_atr"] = (close - low.rolling(20).min()) / df["atr_14"].replace(0, np.nan)

    # MACD histogram relative to ATR (normalized momentum)
    df["macd_hist_vs_atr"] = df["macd_hist"] / df["atr_14"].replace(0, np.nan)

    # Body size relative to ATR (candle significance)
    df["body_vs_atr"] = body.abs() / df["atr_14"].replace(0, np.nan)

    # ── Clean up helper columns ──────────────────────────────────────
    # Drop raw indicator columns that are redundant with engineered features
    cols_to_drop = [
        "bb_upper", "bb_lower", "bb_middle",
        "high_10", "high_20", "high_50", "low_10", "low_20", "low_50",
        "volume_ma_5", "volume_ma_20",
    ]
    df.drop(columns=[c for c in cols_to_drop if c in df.columns], inplace=True)

    if dropna:
        df.dropna(inplace=True)
        df.reset_index(drop=True, inplace=True)

    return df


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return list of feature column names (excludes OHLCV, time, labels)."""
    exclude = {
        "time", "open", "high", "low", "close", "volume",
        "spread", "symbol", "timeframe",
        "label", "forward_return", "target",
    }
    return [c for c in df.columns if c not in exclude]


def _consecutive_count(arr: np.ndarray) -> np.ndarray:
    """Count consecutive same-direction candles (positive=bullish, negative=bearish)."""
    result = np.zeros(len(arr), dtype=np.float64)
    count = 0
    prev = 0
    for i in range(len(arr)):
        if arr[i] == prev and arr[i] != 0:
            count += arr[i]  # +1 for bullish, -1 for bearish
        else:
            count = arr[i]
        prev = arr[i]
        result[i] = count
    return result
