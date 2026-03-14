"""Unit tests for technical indicators"""
import sys
sys.path.insert(0, ".")

import pytest
import pandas as pd
import numpy as np
from features.technical.indicators import (
    add_sma, add_ema, add_rsi, add_macd, add_atr, add_bollinger_bands, add_all_indicators,
)


@pytest.fixture
def sample_df():
    """Generate sample OHLCV data"""
    np.random.seed(42)
    n = 100
    close = 1.1000 + np.cumsum(np.random.randn(n) * 0.001)
    return pd.DataFrame({
        "time": pd.date_range("2025-01-01", periods=n, freq="h"),
        "open": close + np.random.randn(n) * 0.0005,
        "high": close + abs(np.random.randn(n) * 0.001),
        "low": close - abs(np.random.randn(n) * 0.001),
        "close": close,
        "volume": np.random.randint(100, 5000, n).astype(float),
    })


class TestSMA:
    def test_column_created(self, sample_df):
        df = add_sma(sample_df, 20)
        assert "sma_20" in df.columns

    def test_first_values_nan(self, sample_df):
        df = add_sma(sample_df, 20)
        assert df["sma_20"].iloc[:19].isna().all()
        assert pd.notna(df["sma_20"].iloc[19])

    def test_value_is_mean(self, sample_df):
        df = add_sma(sample_df, 5)
        expected = sample_df["close"].iloc[:5].mean()
        assert abs(df["sma_5"].iloc[4] - expected) < 1e-10


class TestEMA:
    def test_column_created(self, sample_df):
        df = add_ema(sample_df, 12)
        assert "ema_12" in df.columns

    def test_no_nans_after_start(self, sample_df):
        df = add_ema(sample_df, 12)
        assert df["ema_12"].notna().all()


class TestRSI:
    def test_range(self, sample_df):
        df = add_rsi(sample_df, 14)
        valid = df["rsi_14"].dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_column_created(self, sample_df):
        df = add_rsi(sample_df, 14)
        assert "rsi_14" in df.columns


class TestMACD:
    def test_columns_created(self, sample_df):
        df = add_macd(sample_df)
        assert "macd_line" in df.columns
        assert "macd_signal" in df.columns
        assert "macd_hist" in df.columns

    def test_hist_equals_line_minus_signal(self, sample_df):
        df = add_macd(sample_df)
        diff = (df["macd_line"] - df["macd_signal"] - df["macd_hist"]).abs()
        assert (diff < 1e-10).all()


class TestATR:
    def test_positive_values(self, sample_df):
        df = add_atr(sample_df, 14)
        valid = df["atr_14"].dropna()
        assert (valid > 0).all()


class TestBollingerBands:
    def test_upper_above_lower(self, sample_df):
        df = add_bollinger_bands(sample_df, 20)
        valid = df.dropna(subset=["bb_upper", "bb_lower"])
        assert (valid["bb_upper"] > valid["bb_lower"]).all()

    def test_middle_is_sma(self, sample_df):
        df = add_bollinger_bands(sample_df, 20)
        sma = sample_df["close"].rolling(20).mean()
        diff = (df["bb_middle"] - sma).dropna().abs()
        assert (diff < 1e-10).all()


class TestAllIndicators:
    def test_all_columns(self, sample_df):
        df = add_all_indicators(sample_df)
        expected = [
            "sma_20", "sma_50", "ema_12", "ema_26", "rsi_14",
            "macd_line", "macd_signal", "macd_hist",
            "atr_14", "bb_upper", "bb_middle", "bb_lower", "bb_width",
        ]
        for col in expected:
            assert col in df.columns, f"Missing column: {col}"
