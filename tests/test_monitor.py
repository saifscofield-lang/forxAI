"""Unit tests for Hybrid Monitor (4-phase position management)."""
import sys
sys.path.insert(0, ".")

import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch, call


# ── Helpers ──

def make_position(ticket=1001, symbol="EURUSD", action="BUY", volume=0.10,
                  open_price=1.10000, current_price=1.10000, sl=1.09500,
                  tp=1.11000, profit=0.0):
    """Create a single-row positions DataFrame."""
    return pd.DataFrame([{
        "ticket": ticket, "symbol": symbol, "type": action,
        "volume": volume, "open_price": open_price,
        "current_price": current_price, "sl": sl, "tp": tp,
        "profit": profit, "swap": 0.0,
        "open_time": pd.Timestamp("2026-03-20 10:00:00"), "comment": "",
    }])


def make_engine():
    """Create a TradingEngine with mocked dependencies."""
    with patch("engine.trading_engine.MT5Adapter") as MockAdapter, \
         patch("engine.trading_engine.RiskManager"), \
         patch("engine.trading_engine.TelegramNotifier") as MockNotifier, \
         patch("engine.trading_engine.SessionLocal"):

        engine_obj = __import__("engine.trading_engine", fromlist=["TradingEngine"])
        eng = engine_obj.TradingEngine.__new__(engine_obj.TradingEngine)

        eng.adapter = MagicMock()
        eng.risk_manager = MagicMock()
        eng.notifier = MagicMock()
        eng.running = True
        eng._position_states = {}
        eng._optimized_params = {}
        eng._ml_ready_notified = False
        eng.scan_count = 0
        eng.news_filter = None
        eng.strategies = []
        eng._last_ticket = None
        eng.config = {
            "instruments": [
                {"symbol": "EURUSD", "digits": 5, "pip_value": 0.0001},
                {"symbol": "USDJPY", "digits": 3, "pip_value": 0.01},
                {"symbol": "XAUUSD", "digits": 2, "pip_value": 0.01},
            ]
        }
        eng.instruments = {i["symbol"]: i for i in eng.config["instruments"]}

        # Mock _save_monitor_states to avoid DB calls in tests
        eng._save_monitor_states = MagicMock()

        return eng


# ── ATR constant for tests ──
ATR = 0.00500  # 50 pips for EURUSD


class TestPhase0NoAction:
    """When price hasn't moved enough, no action should be taken."""

    def test_no_action_below_1_atr(self):
        eng = make_engine()
        # Price moved only +0.5 ATR (25 pips) — should NOT trigger breakeven
        pos = make_position(current_price=1.10025, sl=1.09500)
        atr_cache = {"EURUSD": ATR}

        eng._manage_position(pos.iloc[0], atr_cache)

        eng.adapter.modify_position.assert_not_called()
        eng.adapter.partial_close.assert_not_called()
        assert eng._position_states[1001]["phase"] == 0

    def test_no_action_negative_move(self):
        eng = make_engine()
        # Price went against us
        pos = make_position(current_price=1.09800, sl=1.09500)
        atr_cache = {"EURUSD": ATR}

        eng._manage_position(pos.iloc[0], atr_cache)

        eng.adapter.modify_position.assert_not_called()
        assert eng._position_states[1001]["phase"] == 0

    def test_no_action_unknown_symbol(self):
        eng = make_engine()
        pos = make_position(symbol="UNKNOWN", current_price=1.20000)
        atr_cache = {"UNKNOWN": ATR}

        eng._manage_position(pos.iloc[0], atr_cache)

        eng.adapter.modify_position.assert_not_called()

    def test_no_action_zero_atr(self):
        eng = make_engine()
        pos = make_position(current_price=1.11000)
        atr_cache = {"EURUSD": 0.0}

        eng._manage_position(pos.iloc[0], atr_cache)

        eng.adapter.modify_position.assert_not_called()

    def test_no_action_missing_atr(self):
        eng = make_engine()
        pos = make_position(current_price=1.11000)
        atr_cache = {}  # No ATR for EURUSD

        eng._manage_position(pos.iloc[0], atr_cache)

        eng.adapter.modify_position.assert_not_called()


class TestPhase1Breakeven:
    """Phase 1: Move SL to breakeven when +1.0x ATR in favor."""

    def test_buy_breakeven_at_1_atr(self):
        eng = make_engine()
        # Price moved +1.1 ATR (55 pips) — slightly over to avoid float imprecision
        pos = make_position(current_price=1.10550, sl=1.09500)
        atr_cache = {"EURUSD": ATR}
        eng.adapter.modify_position.return_value = {"success": True}

        eng._manage_position(pos.iloc[0], atr_cache)

        # SL should move to entry + 2 pips = 1.10000 + 0.00020
        expected_sl = round(1.10000 + 0.0001 * 2, 5)  # 1.10020
        eng.adapter.modify_position.assert_called_once()
        actual_sl = eng.adapter.modify_position.call_args[1]["stop_loss"]
        assert abs(actual_sl - expected_sl) < 1e-6
        assert eng._position_states[1001]["phase"] == 1

    def test_sell_breakeven_at_1_atr(self):
        eng = make_engine()
        # SELL: entry 1.10000, TP at 1.09000, price at 1.09450 (+1.1 ATR, not yet at TP)
        pos = make_position(action="SELL", open_price=1.10000,
                           current_price=1.09450, sl=1.10500, tp=1.09000)
        atr_cache = {"EURUSD": ATR}
        eng.adapter.modify_position.return_value = {"success": True}

        eng._manage_position(pos.iloc[0], atr_cache)

        # SL should move to entry - 2 pips = 1.10000 - 0.00020
        expected_sl = round(1.10000 - 0.0001 * 2, 5)  # 1.09980
        eng.adapter.modify_position.assert_called_once()
        actual_sl = eng.adapter.modify_position.call_args[1]["stop_loss"]
        assert abs(actual_sl - expected_sl) < 1e-6
        assert eng._position_states[1001]["phase"] == 1

    def test_buy_no_move_if_sl_already_above_breakeven(self):
        eng = make_engine()
        # SL is already above breakeven level
        pos = make_position(current_price=1.10500, sl=1.10100)
        atr_cache = {"EURUSD": ATR}

        eng._manage_position(pos.iloc[0], atr_cache)

        # SL 1.10100 > breakeven 1.10020, so no modification needed
        eng.adapter.modify_position.assert_not_called()
        # Phase should still be set to 1 since atr_units >= 1.0
        # Actually, phase won't be set because should_move is False
        assert eng._position_states[1001]["phase"] == 0

    def test_sell_no_move_if_sl_already_below_breakeven(self):
        eng = make_engine()
        # SELL: +1.1 ATR move, TP at 1.09000, SL already below breakeven
        pos = make_position(action="SELL", open_price=1.10000,
                           current_price=1.09450, sl=1.09900, tp=1.09000)
        atr_cache = {"EURUSD": ATR}

        eng._manage_position(pos.iloc[0], atr_cache)

        # SL 1.09900 < breakeven 1.09980, already more protective
        eng.adapter.modify_position.assert_not_called()

    def test_breakeven_not_triggered_twice(self):
        eng = make_engine()
        eng._position_states[1001] = {
            "phase": 1, "tp1_closed": False,
            "original_volume": 0.10, "original_tp": 1.11000,
            "entry_atr": ATR, "symbol": "EURUSD",
        }
        pos = make_position(current_price=1.10600, sl=1.10020)
        atr_cache = {"EURUSD": ATR}

        eng._manage_position(pos.iloc[0], atr_cache)

        # Phase already 1, tp not reached — no action
        eng.adapter.modify_position.assert_not_called()
        eng.adapter.partial_close.assert_not_called()


class TestPhase2PartialClose:
    """Phase 2: Close 50% at TP1, move SL to mid-profit, set TP2."""

    def test_buy_partial_close_at_tp(self):
        eng = make_engine()
        # Price reached TP (1.11000)
        pos = make_position(current_price=1.11000, sl=1.10020, tp=1.11000)
        atr_cache = {"EURUSD": ATR}
        eng.adapter.partial_close.return_value = {"success": True, "volume_closed": 0.05, "price": 1.11000}
        eng.adapter.modify_position.return_value = {"success": True}

        eng._manage_position(pos.iloc[0], atr_cache)

        # Should partial close 50% = 0.05 lots
        eng.adapter.partial_close.assert_called_once_with(1001, 0.05)

        # Should modify SL to mid-profit and TP to TP1 + 1 ATR
        mid_sl = round(1.10000 + (1.11000 - 1.10000) * 0.5, 5)  # 1.10500
        new_tp = round(1.11000 + ATR * 1.0, 5)  # 1.11500
        eng.adapter.modify_position.assert_called_once_with(
            1001, stop_loss=mid_sl, take_profit=new_tp
        )

        state = eng._position_states[1001]
        assert state["phase"] == 2
        assert state["tp1_closed"] is True

    def test_sell_partial_close_at_tp(self):
        eng = make_engine()
        # SELL: entry 1.10000, TP 1.09000, price reached TP
        pos = make_position(action="SELL", open_price=1.10000,
                           current_price=1.09000, sl=1.09980, tp=1.09000)
        atr_cache = {"EURUSD": ATR}
        eng.adapter.partial_close.return_value = {"success": True, "volume_closed": 0.05, "price": 1.09000}
        eng.adapter.modify_position.return_value = {"success": True}

        eng._manage_position(pos.iloc[0], atr_cache)

        eng.adapter.partial_close.assert_called_once_with(1001, 0.05)

        mid_sl = round(1.10000 - (1.10000 - 1.09000) * 0.5, 5)  # 1.09500
        new_tp = round(1.09000 - ATR * 1.0, 5)  # 1.08500
        eng.adapter.modify_position.assert_called_once_with(
            1001, stop_loss=mid_sl, take_profit=new_tp
        )

    def test_partial_close_not_repeated(self):
        eng = make_engine()
        # State already has tp1_closed=True — should go to Phase 3, NOT partial close again
        eng._position_states[1001] = {
            "phase": 2, "tp1_closed": True,
            "original_volume": 0.10, "original_tp": 1.11000,
            "entry_atr": ATR, "symbol": "EURUSD",
        }
        pos = make_position(current_price=1.11200, sl=1.10500, tp=1.11500, volume=0.05)
        atr_cache = {"EURUSD": ATR}
        eng.adapter.modify_position.return_value = {"success": True}

        eng._manage_position(pos.iloc[0], atr_cache)

        # Should NOT call partial_close again
        eng.adapter.partial_close.assert_not_called()
        # Should apply trailing (Phase 3)
        assert eng._position_states[1001]["phase"] == 3

    def test_partial_close_fails_gracefully(self):
        eng = make_engine()
        pos = make_position(current_price=1.11000, sl=1.10020, tp=1.11000)
        atr_cache = {"EURUSD": ATR}
        eng.adapter.partial_close.return_value = {"success": False, "error": "No liquidity"}

        eng._manage_position(pos.iloc[0], atr_cache)

        # State should NOT be updated to tp1_closed
        assert eng._position_states[1001]["tp1_closed"] is False
        assert eng._position_states[1001]["phase"] == 0

    def test_min_volume_check(self):
        eng = make_engine()
        # Volume too small: 0.01 * 0.5 = 0.005 < 0.01
        pos = make_position(current_price=1.11000, sl=1.10020, tp=1.11000, volume=0.01)
        atr_cache = {"EURUSD": ATR}

        eng._manage_position(pos.iloc[0], atr_cache)

        # 0.01 * 0.5 = 0.005 rounds to 0.01, which is >= 0.01, so it WILL close
        # Actually round(0.005, 2) = 0.01 in Python (banker's rounding) — let's check
        # round(0.01 * 0.5, 2) = round(0.005, 2) = 0.0 in Python 3 (banker's rounds to even)
        # So 0.0 < 0.01 — should NOT call partial_close
        eng.adapter.partial_close.assert_not_called()


class TestPhase3Trailing:
    """Phase 3: Trail at 1.0x ATR after partial close."""

    def test_buy_trailing_after_tp1(self):
        eng = make_engine()
        eng._position_states[1001] = {
            "phase": 2, "tp1_closed": True,
            "original_volume": 0.10, "original_tp": 1.11000,
            "entry_atr": ATR, "symbol": "EURUSD",
        }
        # Price at 1.11200, SL at 1.10500
        pos = make_position(current_price=1.11200, sl=1.10500, tp=1.11500, volume=0.05)
        atr_cache = {"EURUSD": ATR}
        eng.adapter.modify_position.return_value = {"success": True}

        eng._manage_position(pos.iloc[0], atr_cache)

        # Trail SL = 1.11200 - 0.005 = 1.10700
        expected_sl = round(1.11200 - ATR * 1.0, 5)  # 1.10700
        eng.adapter.modify_position.assert_called_once_with(1001, stop_loss=expected_sl)
        assert eng._position_states[1001]["phase"] == 3

    def test_sell_trailing_after_tp1(self):
        eng = make_engine()
        eng._position_states[1001] = {
            "phase": 2, "tp1_closed": True,
            "original_volume": 0.10, "original_tp": 1.09000,
            "entry_atr": ATR, "symbol": "EURUSD",
        }
        # SELL: price at 1.08800, SL at 1.09500
        pos = make_position(action="SELL", open_price=1.10000,
                           current_price=1.08800, sl=1.09500, tp=1.08500, volume=0.05)
        atr_cache = {"EURUSD": ATR}
        eng.adapter.modify_position.return_value = {"success": True}

        eng._manage_position(pos.iloc[0], atr_cache)

        # Trail SL = 1.08800 + 0.005 = 1.09300
        expected_sl = round(1.08800 + ATR * 1.0, 5)  # 1.09300
        eng.adapter.modify_position.assert_called_once_with(1001, stop_loss=expected_sl)

    def test_trailing_only_moves_in_favor(self):
        eng = make_engine()
        eng._position_states[1001] = {
            "phase": 3, "tp1_closed": True,
            "original_volume": 0.10, "original_tp": 1.11000,
            "entry_atr": ATR, "symbol": "EURUSD",
        }
        # BUY: price pulled back, new trail SL would be LOWER than current
        pos = make_position(current_price=1.10800, sl=1.10700, tp=1.11500, volume=0.05)
        atr_cache = {"EURUSD": ATR}

        eng._manage_position(pos.iloc[0], atr_cache)

        # Trail SL = 1.10800 - 0.005 = 1.10300 < current SL 1.10700 → no move
        eng.adapter.modify_position.assert_not_called()


class TestPhase4TightTrail:
    """Phase 4: Tighten trail to 0.7x ATR after +3.0x ATR from entry."""

    def test_buy_tight_trail_at_3_atr(self):
        eng = make_engine()
        eng._position_states[1001] = {
            "phase": 3, "tp1_closed": True,
            "original_volume": 0.10, "original_tp": 1.11000,
            "entry_atr": ATR, "symbol": "EURUSD",
        }
        # Price at +3.1 ATR to avoid float imprecision
        pos = make_position(current_price=1.11550, sl=1.10700, tp=1.11500, volume=0.05)
        atr_cache = {"EURUSD": ATR}
        eng.adapter.modify_position.return_value = {"success": True}

        eng._manage_position(pos.iloc[0], atr_cache)

        # Tight trail SL = 1.11550 - 0.005 * 0.7 = 1.11200
        expected_sl = round(1.11550 - ATR * 0.7, 5)
        eng.adapter.modify_position.assert_called_once()
        actual_sl = eng.adapter.modify_position.call_args[1]["stop_loss"]
        assert abs(actual_sl - expected_sl) < 1e-5
        assert eng._position_states[1001]["phase"] == 4

    def test_sell_tight_trail_at_3_atr(self):
        eng = make_engine()
        eng._position_states[1001] = {
            "phase": 3, "tp1_closed": True,
            "original_volume": 0.10, "original_tp": 1.09000,
            "entry_atr": ATR, "symbol": "EURUSD",
        }
        # SELL: entry 1.10000, price at 1.08500 (+3.0 ATR in favor)
        pos = make_position(action="SELL", open_price=1.10000,
                           current_price=1.08500, sl=1.09300, tp=1.08500, volume=0.05)
        atr_cache = {"EURUSD": ATR}
        eng.adapter.modify_position.return_value = {"success": True}

        eng._manage_position(pos.iloc[0], atr_cache)

        # Tight trail SL = 1.08500 + 0.005 * 0.7 = 1.08850
        expected_sl = round(1.08500 + ATR * 0.7, 5)  # 1.08850
        eng.adapter.modify_position.assert_called_once_with(1001, stop_loss=expected_sl)
        assert eng._position_states[1001]["phase"] == 4

    def test_phase4_requires_tp1_closed(self):
        eng = make_engine()
        # Price moved +3 ATR but tp1 NOT closed — should try Phase 2 (TP hit), not Phase 4
        pos = make_position(current_price=1.11500, sl=1.10020, tp=1.11000, volume=0.10)
        atr_cache = {"EURUSD": ATR}
        eng.adapter.partial_close.return_value = {"success": True, "volume_closed": 0.05, "price": 1.11500}
        eng.adapter.modify_position.return_value = {"success": True}

        eng._manage_position(pos.iloc[0], atr_cache)

        # Should trigger partial close (Phase 2), not tight trail
        eng.adapter.partial_close.assert_called_once()
        assert eng._position_states[1001]["phase"] == 2


class TestStateLifecycle:
    """Test position state creation, persistence, and cleanup."""

    def test_state_created_on_first_encounter(self):
        eng = make_engine()
        pos = make_position()
        atr_cache = {"EURUSD": ATR}

        eng._manage_position(pos.iloc[0], atr_cache)

        assert 1001 in eng._position_states
        state = eng._position_states[1001]
        assert state["phase"] == 0
        assert state["tp1_closed"] is False
        assert state["original_volume"] == 0.10
        assert state["original_tp"] == 1.11000
        assert state["symbol"] == "EURUSD"

    def test_state_preserved_across_calls(self):
        eng = make_engine()
        eng._position_states[1001] = {
            "phase": 2, "tp1_closed": True,
            "original_volume": 0.10, "original_tp": 1.11000,
            "entry_atr": ATR, "symbol": "EURUSD",
        }
        pos = make_position(current_price=1.11200, sl=1.10500, tp=1.11500, volume=0.05)
        atr_cache = {"EURUSD": ATR}
        eng.adapter.modify_position.return_value = {"success": True}

        eng._manage_position(pos.iloc[0], atr_cache)

        # original_volume should still be 0.10, not updated to current 0.05
        assert eng._position_states[1001]["original_volume"] == 0.10

    def test_cleanup_closed_positions(self):
        eng = make_engine()
        eng._position_states = {
            1001: {"phase": 3, "tp1_closed": True, "original_volume": 0.10,
                   "original_tp": 1.11, "entry_atr": ATR, "symbol": "EURUSD"},
            1002: {"phase": 1, "tp1_closed": False, "original_volume": 0.10,
                   "original_tp": 1.11, "entry_atr": ATR, "symbol": "EURUSD"},
        }
        # Only ticket 1001 is still open
        eng.adapter.get_open_positions.return_value = make_position(ticket=1001, current_price=1.11200,
                                                                     sl=1.10500, tp=1.11500, volume=0.05)
        eng.adapter.get_ohlcv.return_value = pd.DataFrame()  # skip ATR calc
        eng.adapter.modify_position.return_value = {"success": True}

        eng.monitor_positions()

        # 1002 should be cleaned up
        assert 1002 not in eng._position_states
        assert 1001 in eng._position_states

    def test_all_positions_closed_clears_states(self):
        eng = make_engine()
        eng._position_states = {
            1001: {"phase": 2, "tp1_closed": True, "original_volume": 0.10,
                   "original_tp": 1.11, "entry_atr": ATR, "symbol": "EURUSD"},
        }
        eng.adapter.get_open_positions.return_value = pd.DataFrame()

        eng.monitor_positions()

        assert len(eng._position_states) == 0
        eng._save_monitor_states.assert_called()

    def test_monitor_skips_when_not_running(self):
        eng = make_engine()
        eng.running = False
        eng.adapter.get_open_positions.return_value = make_position()

        eng.monitor_positions()

        eng.adapter.get_open_positions.assert_not_called()


class TestDigitsRounding:
    """Test per-symbol digit rounding (5 for forex, 3 for JPY, 2 for XAUUSD)."""

    def test_usdjpy_3_digits(self):
        eng = make_engine()
        # USDJPY: entry 150.000, ATR 0.500, +1 ATR move
        pos = make_position(symbol="USDJPY", open_price=150.000,
                           current_price=150.500, sl=149.500, tp=151.500)
        atr_cache = {"USDJPY": 0.500}
        eng.adapter.modify_position.return_value = {"success": True}

        eng._manage_position(pos.iloc[0], atr_cache)

        # Breakeven SL = 150.000 + 0.01 * 2 = 150.020, rounded to 3 digits
        expected_sl = round(150.000 + 0.01 * 2, 3)  # 150.02
        eng.adapter.modify_position.assert_called_once_with(1001, stop_loss=expected_sl)

    def test_xauusd_2_digits(self):
        eng = make_engine()
        # XAUUSD: entry 2000.00, ATR 20.00, +1 ATR move
        pos = make_position(symbol="XAUUSD", open_price=2000.00,
                           current_price=2020.00, sl=1980.00, tp=2050.00)
        atr_cache = {"XAUUSD": 20.00}
        eng.adapter.modify_position.return_value = {"success": True}

        eng._manage_position(pos.iloc[0], atr_cache)

        # Breakeven SL = 2000.00 + 0.01 * 2 = 2000.02, rounded to 2 digits
        expected_sl = round(2000.00 + 0.01 * 2, 2)  # 2000.02
        eng.adapter.modify_position.assert_called_once_with(1001, stop_loss=expected_sl)


class TestMultiplePositions:
    """Test monitoring multiple positions simultaneously."""

    def test_two_positions_independent_phases(self):
        eng = make_engine()
        # Position 1: BUY EURUSD, +1.1 ATR move (breakeven)
        # Position 2: BUY EURUSD already in trailing (tp1_closed)
        eng._position_states[2002] = {
            "phase": 2, "tp1_closed": True,
            "original_volume": 0.10, "original_tp": 1.11000,
            "entry_atr": ATR, "symbol": "EURUSD",
        }

        positions = pd.concat([
            make_position(ticket=1001, current_price=1.10550, sl=1.09500),
            make_position(ticket=2002, current_price=1.11200, sl=1.10500,
                         tp=1.11500, volume=0.05),
        ], ignore_index=True)

        eng.adapter.get_open_positions.return_value = positions
        eng.adapter.modify_position.return_value = {"success": True}

        # Mock get_ohlcv to return data that produces ATR ~= 0.005
        np.random.seed(42)
        n = 50
        close = 1.1000 + np.cumsum(np.random.randn(n) * 0.001)
        ohlcv = pd.DataFrame({
            "open": close + np.random.randn(n) * 0.0005,
            "high": close + abs(np.random.randn(n) * 0.003),
            "low": close - abs(np.random.randn(n) * 0.003),
            "close": close,
            "volume": np.random.randint(100, 5000, n).astype(float),
        })
        eng.adapter.get_ohlcv.return_value = ohlcv

        eng.monitor_positions()

        # Position 2002 should be in Phase 3 trailing
        assert eng._position_states[2002]["phase"] == 3
        # Position 1001 should have been processed (phase depends on computed ATR)
        assert 1001 in eng._position_states
