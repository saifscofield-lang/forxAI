"""Unit tests for strategies/tsmom/tsmom_strategy.py.

Covers the pure compute_tsmom_signal() core, the rebalance-timing
helper, and the engine-interface TSMOMStrategy class.

Pytest-free runner at the bottom (matches the rest of the project)."""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

import math

import numpy as np
import pandas as pd

from strategies.tsmom.tsmom_strategy import (
    TSMOMSignal,
    TSMOMStrategy,
    compute_tsmom_signal,
    is_rebalance_day,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

def make_prices(returns, start=100.0, freq="1D", start_date="2025-05-06"):
    """Build a price Series from a list/array of period returns."""
    prices = [start]
    for r in returns:
        prices.append(prices[-1] * (1 + r))
    idx = pd.date_range(start_date, periods=len(prices), freq=freq)
    return pd.Series(prices, index=idx)


def constant_drift(n_days, daily_drift, daily_vol=0.0, start=100.0, seed=42):
    rng = np.random.default_rng(seed)
    rets = daily_drift + rng.normal(0, daily_vol, size=n_days)
    return make_prices(rets, start=start)


# ── compute_tsmom_signal — core direction logic ────────────────────────────

def test_uptrend_returns_buy():
    """Steady +0.1%/day for 300 days. 12-month return ≈ +35%; expect BUY."""
    prices = constant_drift(n_days=300, daily_drift=0.001, daily_vol=0.005)
    sig = compute_tsmom_signal(prices)
    assert sig is not None
    assert sig.direction == "BUY"
    assert sig.raw_momentum > 0


def test_downtrend_returns_sell():
    prices = constant_drift(n_days=300, daily_drift=-0.001, daily_vol=0.005)
    sig = compute_tsmom_signal(prices)
    assert sig is not None
    assert sig.direction == "SELL"
    assert sig.raw_momentum < 0


def test_flat_series_returns_flat():
    """No drift, no vol → exactly 0 cum return → FLAT."""
    prices = constant_drift(n_days=300, daily_drift=0.0, daily_vol=0.0)
    sig = compute_tsmom_signal(prices)
    assert sig is not None
    assert sig.direction == "FLAT"


def test_short_history_returns_none():
    """Less than lookback + 1 bars → None."""
    prices = constant_drift(n_days=100, daily_drift=0.001, daily_vol=0.005)
    sig = compute_tsmom_signal(prices, lookback_days=252)
    assert sig is None


def test_empty_series_returns_none():
    sig = compute_tsmom_signal(pd.Series([], dtype=float))
    assert sig is None


def test_non_series_input_returns_none():
    sig = compute_tsmom_signal([100, 101, 102])
    assert sig is None


def test_nan_at_lookback_endpoint_returns_none():
    prices = constant_drift(n_days=300, daily_drift=0.001, daily_vol=0.005)
    prices.iloc[-1] = np.nan
    sig = compute_tsmom_signal(prices)
    assert sig is None


def test_zero_at_lookback_endpoint_returns_none():
    prices = constant_drift(n_days=300, daily_drift=0.001, daily_vol=0.005)
    prices.iloc[-1 - 252] = 0.0
    sig = compute_tsmom_signal(prices)
    assert sig is None


# ── Volatility targeting ────────────────────────────────────────────────────

def test_low_vol_yields_capped_weight():
    """Near-zero realised vol → weight should hit weight_cap, not infinity."""
    prices = constant_drift(n_days=300, daily_drift=0.0005, daily_vol=0.00001)
    sig = compute_tsmom_signal(prices, vol_target=0.10, weight_cap=4.0)
    assert sig is not None
    assert sig.target_weight == 4.0  # cap


def test_high_vol_yields_small_weight():
    """High realised vol → weight should be small."""
    prices = constant_drift(n_days=300, daily_drift=0.001, daily_vol=0.05)
    sig = compute_tsmom_signal(prices, vol_target=0.10)
    assert sig is not None
    # daily vol ~5% → annualised ~79% → target 10% / 79% ≈ 0.13
    assert 0.05 < sig.target_weight < 0.4


def test_vol_target_doubles_weight():
    """Doubling vol_target should roughly double target_weight (when not capped)."""
    prices = constant_drift(n_days=300, daily_drift=0.001, daily_vol=0.01)
    sig_a = compute_tsmom_signal(prices, vol_target=0.10, weight_cap=10.0)
    sig_b = compute_tsmom_signal(prices, vol_target=0.20, weight_cap=10.0)
    assert sig_a is not None and sig_b is not None
    ratio = sig_b.target_weight / sig_a.target_weight
    assert 1.9 < ratio < 2.1


def test_vol_floor_prevents_divide_by_zero():
    """Even with all-zero log returns, vol_floor saves us."""
    prices = pd.Series(
        [100.0] * 300,
        index=pd.date_range("2025-05-06", periods=300, freq="1D"),
    )
    sig = compute_tsmom_signal(prices, vol_floor=0.05, weight_cap=10.0)
    # cum_return is 0 → FLAT, but signal should still be returned with weights
    assert sig is not None
    assert sig.direction == "FLAT"
    assert math.isfinite(sig.target_weight)


# ── is_rebalance_day ───────────────────────────────────────────────────────

def test_rebalance_first_call_always_true():
    assert is_rebalance_day(pd.Timestamp("2026-05-06"), None) is True


def test_rebalance_monthly_same_month_false():
    assert is_rebalance_day(
        pd.Timestamp("2026-05-31"), pd.Timestamp("2026-05-01"), "monthly"
    ) is False


def test_rebalance_monthly_new_month_true():
    assert is_rebalance_day(
        pd.Timestamp("2026-06-01"), pd.Timestamp("2026-05-15"), "monthly"
    ) is True


def test_rebalance_weekly_same_week_false():
    # Both fall in ISO week of 2026-05-04 / 2026-05-06
    assert is_rebalance_day(
        pd.Timestamp("2026-05-06"), pd.Timestamp("2026-05-04"), "weekly"
    ) is False


def test_rebalance_weekly_new_week_true():
    assert is_rebalance_day(
        pd.Timestamp("2026-05-11"), pd.Timestamp("2026-05-04"), "weekly"
    ) is True


def test_rebalance_daily_same_day_false():
    assert is_rebalance_day(
        pd.Timestamp("2026-05-06 12:00"),
        pd.Timestamp("2026-05-06 09:00"),
        "daily",
    ) is False


def test_rebalance_daily_next_day_true():
    assert is_rebalance_day(
        pd.Timestamp("2026-05-07 09:00"),
        pd.Timestamp("2026-05-06 21:00"),
        "daily",
    ) is True


def test_rebalance_unknown_freq_raises():
    try:
        is_rebalance_day(pd.Timestamp("2026-05-06"), None, "fortnightly")
        assert False, "expected ValueError"
    except ValueError:
        pass


# ── TSMOMStrategy class ────────────────────────────────────────────────────

def test_strategy_returns_signal_on_first_call():
    """First call always rebalances → expect a signal if data sufficient."""
    n = 300
    prices = constant_drift(n_days=n, daily_drift=0.001, daily_vol=0.005)
    df = pd.DataFrame({
        "close": prices.values,
        "atr": np.full(n + 1, 0.5),
    }, index=prices.index)
    s = TSMOMStrategy("EURUSD")
    sig = s.generate_signal(df)
    assert sig is not None
    assert sig["direction"] == "BUY"
    assert sig["symbol"] == "EURUSD"
    assert sig["strategy"] == "tsmom"
    assert "sl" in sig and "tp" in sig


def test_strategy_skips_when_not_rebalance_day():
    """Second call same month → None even if signal would change."""
    n = 300
    prices = constant_drift(n_days=n, daily_drift=0.001, daily_vol=0.005)
    df1 = pd.DataFrame({"close": prices.values, "atr": np.full(n + 1, 0.5)},
                       index=prices.index)
    s = TSMOMStrategy("EURUSD")
    s.generate_signal(df1)  # first call rebalances
    # Same-month follow-up: append one bar in the same month
    next_idx = df1.index[-1] + pd.Timedelta(days=1)
    df2 = pd.concat([df1, pd.DataFrame(
        {"close": [df1["close"].iloc[-1]], "atr": [0.5]}, index=[next_idx],
    )])
    sig2 = s.generate_signal(df2)
    assert sig2 is None


def test_strategy_signal_dict_shape():
    n = 300
    prices = constant_drift(n_days=n, daily_drift=-0.001, daily_vol=0.005)
    df = pd.DataFrame({"close": prices.values, "atr": np.full(n + 1, 0.5)},
                      index=prices.index)
    s = TSMOMStrategy("EURUSD")
    sig = s.generate_signal(df)
    expected_keys = {"symbol", "direction", "price", "sl", "tp", "atr",
                     "strategy", "target_weight", "raw_momentum",
                     "vol_annualised"}
    assert set(sig.keys()) >= expected_keys
    assert sig["direction"] == "SELL"
    # SELL → SL above price, TP below price
    assert sig["sl"] > sig["price"]
    assert sig["tp"] < sig["price"]


def test_strategy_returns_none_on_flat_signal():
    """Constant prices → FLAT → no signal even on rebalance day."""
    prices = pd.Series(
        [100.0] * 300,
        index=pd.date_range("2025-05-06", periods=300, freq="1D"),
    )
    df = pd.DataFrame({"close": prices.values, "atr": np.full(300, 0.5)},
                      index=prices.index)
    s = TSMOMStrategy("EURUSD")
    sig = s.generate_signal(df)
    assert sig is None


def test_strategy_returns_none_on_short_history():
    """Insufficient history → None even on rebalance day."""
    prices = constant_drift(n_days=100, daily_drift=0.001, daily_vol=0.005)
    df = pd.DataFrame({"close": prices.values, "atr": np.full(101, 0.5)},
                      index=prices.index)
    s = TSMOMStrategy("EURUSD")
    sig = s.generate_signal(df)
    assert sig is None


def test_strategy_handles_empty_df():
    s = TSMOMStrategy("EURUSD")
    sig = s.generate_signal(pd.DataFrame())
    assert sig is None


# ── Pytest-free runner ─────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    fail = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            fail += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            fail += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print()
    print(f"{len(tests) - fail}/{len(tests)} pass")
    sys.exit(0 if fail == 0 else 1)
