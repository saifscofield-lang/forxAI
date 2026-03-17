"""Unit tests for risk manager"""
import sys
sys.path.insert(0, ".")

import pytest
from risk.risk_manager import RiskManager


@pytest.fixture
def rm(tmp_path):
    """Create RiskManager with test config"""
    config = tmp_path / "test_config.yaml"
    config.write_text("""
risk:
  max_risk_per_trade: 0.01
  max_daily_drawdown: 0.05
  max_open_positions: 5
  max_correlated_positions: 2
""")
    return RiskManager(str(config))


class TestPositionSizing:
    def test_basic_calculation(self, rm):
        # $100k balance, 50 pip SL, EURUSD pip_value=0.0001
        lot = rm.calculate_position_size(100000, 50, 0.0001)
        # risk = 1000, pip_value_per_lot = 10, lot = 1000/(50*10) = 2.0
        assert lot == 2.0

    def test_minimum_lot(self, rm):
        # Very tight risk → clamped to 0.01
        lot = rm.calculate_position_size(100, 500, 0.0001)
        assert lot == 0.01

    def test_maximum_lot(self, rm):
        lot = rm.calculate_position_size(10_000_000, 10, 0.0001)
        assert lot == 10.0

    def test_zero_sl_returns_zero(self, rm):
        lot = rm.calculate_position_size(100000, 0, 0.0001)
        assert lot == 0.0


class TestCanOpenTrade:
    def test_allows_under_limit(self, rm):
        assert rm.can_open_trade(3) is True

    def test_blocks_at_limit(self, rm):
        assert rm.can_open_trade(5) is False

    def test_blocks_on_drawdown(self, rm):
        rm.set_balance(100000)
        rm.update_pnl(-6000)  # -6% > 5% limit
        assert rm.can_open_trade(0) is False


class TestValidateTrade:
    def test_valid_buy(self, rm):
        ok, msg = rm.validate_trade("EURUSD", "BUY", 0.1, 1.0900, 1.1100, 1.1000)
        assert ok is True

    def test_rejects_small_lot(self, rm):
        ok, msg = rm.validate_trade("EURUSD", "BUY", 0.001, 1.09, 1.11, 1.10)
        assert ok is False

    def test_rejects_no_sl(self, rm):
        ok, msg = rm.validate_trade("EURUSD", "BUY", 0.1, 0, 1.11, 1.10)
        assert ok is False

    def test_rejects_bad_rr(self, rm):
        # Risk 100 pips, reward 20 pips = 0.2 RR (below 0.3 minimum)
        ok, msg = rm.validate_trade("EURUSD", "BUY", 0.1, 1.09, 1.102, 1.10)
        assert ok is False
