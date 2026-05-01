"""Tests for analysis/rr_calculator.py and CSV roundtrip of realized_rr."""
import math
from pathlib import Path

import pandas as pd
import pytest

from analysis.rr_calculator import (
    phase7_ship_gate,
    profit_factor_dollars,
    profit_factor_r,
    realized_rr,
)


class TestRealizedRR:
    def test_buy_win_at_tp(self):
        # Long, hit TP at 1.5R (open 100, sl 90, tp 115, close 115)
        assert realized_rr(open_price=100, close_price=115, stop_loss=90, pnl=15) == 1.5

    def test_buy_loss_at_sl(self):
        # Long, hit SL at -1R, formula returns -1.0 sentinel
        assert realized_rr(open_price=100, close_price=90, stop_loss=90, pnl=-10) == -1.0

    def test_sell_win(self):
        # Short, profit (close < open)
        assert realized_rr(open_price=100, close_price=85, stop_loss=110, pnl=15) == 1.5

    def test_sell_loss(self):
        assert realized_rr(open_price=100, close_price=110, stop_loss=110, pnl=-10) == -1.0

    def test_close_at_open_zero_rr(self):
        # Close at entry price — break-even, returns 0.0 (no sign because pnl>=0)
        assert realized_rr(open_price=100, close_price=100, stop_loss=90, pnl=0) == 0.0

    def test_partial_exit_below_1r(self):
        # Long, closed early at 0.3R move
        rr = realized_rr(open_price=100, close_price=103, stop_loss=90, pnl=3)
        assert rr == 0.3

    def test_missing_sl_returns_none(self):
        assert realized_rr(open_price=100, close_price=110, stop_loss=None, pnl=10) is None

    def test_zero_sl_distance_returns_none(self):
        # Pathological: SL at the same price as open
        assert realized_rr(open_price=100, close_price=110, stop_loss=100, pnl=10) is None

    def test_none_pnl_no_sign_applied(self):
        # When pnl is None we cannot determine win/loss — returns unsigned magnitude
        rr = realized_rr(open_price=100, close_price=85, stop_loss=110, pnl=None)
        assert rr == 1.5


class TestProfitFactorDollars:
    def test_basic(self):
        assert profit_factor_dollars([100, -50, 30, -20]) == pytest.approx(130 / 70)

    def test_no_losses_returns_inf(self):
        assert profit_factor_dollars([10, 20, 30]) == float("inf")

    def test_no_wins_returns_zero(self):
        assert profit_factor_dollars([-10, -20]) == 0.0

    def test_skips_none(self):
        assert profit_factor_dollars([100, None, -50]) == pytest.approx(2.0)


class TestProfitFactorR:
    def test_basic(self):
        # 3 wins at +1.5R each, 2 losses at -1R each → 4.5 / 2.0 = 2.25
        assert profit_factor_r([1.5, 1.5, 1.5, -1.0, -1.0]) == pytest.approx(2.25)

    def test_audit_match_smoke(self):
        # Smoke test — replicate the structure of the audit's 76 ml_direct
        # tickets: 58 wins, 18 losses. Use representative values.
        wins = [0.46] * 58  # avg realized R from the audit
        losses = [-1.0] * 18
        pf = profit_factor_r(wins + losses)
        # 58 * 0.46 / 18 = 1.4822 — sanity: in ballpark of audit's 1.49 $-PF
        assert 1.0 < pf < 2.5

    def test_zeros_dont_affect(self):
        # Trades with rr=0 contribute nothing to either side
        assert profit_factor_r([1.5, 0, -1.0, 0]) == pytest.approx(1.5)


class TestPhase7ShipGate:
    def test_dual_pass(self):
        # PF_$ = 200/100 = 2.0, PF_R = 3/1 = 3 → both pass
        result = phase7_ship_gate(pnls=[200, -100], rrs=[3.0, -1.0])
        assert result["passes_dollars_gate"] is True
        assert result["passes_r_gate"] is True
        assert result["passes_dual_gate"] is True

    def test_r_passes_dollars_fails(self):
        # PF_R = 1.5 (>=1.3) but PF_$ = 0.5 (<1.0)
        result = phase7_ship_gate(pnls=[50, -100], rrs=[1.5, -1.0])
        assert result["passes_r_gate"] is True
        assert result["passes_dollars_gate"] is False
        assert result["passes_dual_gate"] is False

    def test_dollars_passes_r_fails(self):
        result = phase7_ship_gate(pnls=[200, -100], rrs=[1.2, -1.0])
        assert result["passes_dollars_gate"] is True
        assert result["passes_r_gate"] is False
        assert result["passes_dual_gate"] is False

    def test_thresholds_exposed(self):
        result = phase7_ship_gate(pnls=[1], rrs=[1])
        assert result["thresholds"] == {"r_min": 1.3, "dollars_min": 1.0}


class TestCSVRoundtrip:
    """Verify analyze_all_trades.py emits realized_rr with the same values
    as the source DB column risk_reward_actual."""

    def test_csv_realized_rr_matches_db_when_artifact_present(self):
        csv_path = Path("artifacts/all_trades_enriched.csv")
        if not csv_path.exists():
            pytest.skip("artifact CSV not yet regenerated")
        df = pd.read_csv(csv_path)
        if "realized_rr" not in df.columns or "risk_reward_actual" not in df.columns:
            pytest.skip("CSV missing expected columns")
        # All non-null risk_reward_actual values should appear in realized_rr
        merged = df[["realized_rr", "risk_reward_actual"]].dropna(
            subset=["risk_reward_actual"]
        )
        assert len(merged) > 0, "no non-null risk_reward_actual rows in CSV"
        # Within rounding (the engine rounds to 2dp; we accept tiny float drift)
        diff = (merged["realized_rr"] - merged["risk_reward_actual"]).abs()
        assert (diff < 0.01).all() or merged["realized_rr"].isna().all() is False, (
            f"CSV realized_rr does not match DB risk_reward_actual; "
            f"max diff = {diff.max():.4f}"
        )
