"""Unit tests for risk/kelly_sizer.py.

Covers the pure formula, the fractional/capped wrapper, dollar-size
composition, and the avg_win/avg_loss helper. Pytest-free runner."""
from __future__ import annotations

import math
import sys

sys.path.insert(0, ".")

from risk.kelly_sizer import (
    KellyResult,
    fractional_kelly,
    kelly_fraction,
    kelly_position_size,
    win_loss_ratio_from_pnl,
)


# ── kelly_fraction (pure formula) ───────────────────────────────────────────

def test_textbook_55pct_2x_ratio():
    """Wikipedia Kelly example. p=0.55, b=2.0 -> f* = (0.55*2 - 0.45)/2 = 0.325"""
    assert math.isclose(kelly_fraction(0.55, 2.0), 0.325, abs_tol=1e-9)


def test_breakeven_returns_zero():
    """p × b == q exactly -> Kelly = 0 (no edge)."""
    # p=0.5, b=1 -> Kelly = (0.5*1 - 0.5)/1 = 0
    assert kelly_fraction(0.5, 1.0) == 0.0


def test_negative_edge_returns_negative_kelly():
    """p × b < q -> f* < 0. Caller must skip the trade."""
    f = kelly_fraction(0.40, 1.0)  # p*b=0.4 < q=0.6
    assert f < 0


def test_high_win_prob_high_ratio():
    """Strong edge (p=0.7, b=3): Kelly = (2.1 - 0.3)/3 = 0.6"""
    assert math.isclose(kelly_fraction(0.7, 3.0), 0.6, abs_tol=1e-9)


def test_winprob_zero():
    """Always lose -> Kelly = (0 - 1)/b = -1/b"""
    assert kelly_fraction(0.0, 2.0) == -0.5


def test_winprob_one():
    """Always win -> Kelly = (1*b)/b = 1.0 (bet whole bankroll)"""
    assert kelly_fraction(1.0, 2.0) == 1.0


def test_invalid_win_prob_raises():
    try:
        kelly_fraction(-0.1, 2.0)
        assert False
    except ValueError:
        pass
    try:
        kelly_fraction(1.5, 2.0)
        assert False
    except ValueError:
        pass


def test_invalid_ratio_raises():
    try:
        kelly_fraction(0.55, 0.0)
        assert False
    except ValueError:
        pass
    try:
        kelly_fraction(0.55, -1.0)
        assert False
    except ValueError:
        pass


# ── fractional_kelly (wrapper) ──────────────────────────────────────────────

def test_fractional_kelly_quarter_default():
    """multiplier=0.25 by default. p=0.55, b=2 -> f*=0.325 -> 0.0813"""
    r = fractional_kelly(0.55, 2.0)
    assert isinstance(r, KellyResult)
    assert math.isclose(r.full_kelly, 0.325, abs_tol=1e-9)
    assert math.isclose(r.fractional_kelly, 0.325 * 0.25, abs_tol=1e-9)
    assert math.isclose(r.capped, 0.325 * 0.25, abs_tol=1e-9)
    assert r.skip_trade is False


def test_fractional_kelly_caps_at_max_fraction():
    """Strong edge with full multiplier should hit max_fraction."""
    # p=0.9, b=5 -> full Kelly = (4.5 - 0.1)/5 = 0.88
    r = fractional_kelly(0.90, 5.0, multiplier=1.0, max_fraction=0.25)
    assert r.full_kelly > 0.25
    assert r.capped == 0.25  # capped at max_fraction


def test_fractional_kelly_negative_edge_skips():
    """Negative edge -> skip_trade=True, capped=0."""
    r = fractional_kelly(0.40, 1.0)
    assert r.skip_trade is True
    assert r.capped == 0.0
    assert r.fractional_kelly == 0.0


def test_fractional_kelly_zero_edge_skips():
    r = fractional_kelly(0.50, 1.0)
    assert r.skip_trade is True
    assert r.capped == 0.0


def test_fractional_kelly_invalid_multiplier_raises():
    try:
        fractional_kelly(0.55, 2.0, multiplier=0.0)
        assert False
    except ValueError:
        pass
    try:
        fractional_kelly(0.55, 2.0, multiplier=-0.1)
        assert False
    except ValueError:
        pass
    try:
        fractional_kelly(0.55, 2.0, multiplier=2.5)
        assert False
    except ValueError:
        pass


def test_fractional_kelly_invalid_max_fraction_raises():
    try:
        fractional_kelly(0.55, 2.0, max_fraction=0.0)
        assert False
    except ValueError:
        pass
    try:
        fractional_kelly(0.55, 2.0, max_fraction=1.5)
        assert False
    except ValueError:
        pass


# ── kelly_position_size (dollars) ───────────────────────────────────────────

def test_position_size_textbook():
    """$10,000 balance, p=0.55, b=2, quarter Kelly -> $10000 * 0.0813 = $813.50"""
    size = kelly_position_size(10000.0, 0.55, 2.0)
    assert math.isclose(size, 10000.0 * 0.325 * 0.25, abs_tol=0.01)


def test_position_size_zero_balance():
    assert kelly_position_size(0.0, 0.55, 2.0) == 0.0


def test_position_size_negative_balance():
    assert kelly_position_size(-100.0, 0.55, 2.0) == 0.0


def test_position_size_skip_on_negative_edge():
    assert kelly_position_size(10000.0, 0.40, 1.0) == 0.0


def test_position_size_min_floor():
    """If computed size is below min_size, return 0."""
    # Tiny edge × small balance × min_size cutoff
    size = kelly_position_size(100.0, 0.51, 1.0, min_size=10.0)
    # full Kelly = (0.51 - 0.49)/1 = 0.02; quarter = 0.005; size = $0.50
    assert size == 0.0


def test_position_size_above_min_floor():
    """When size exceeds min_size, return the size."""
    size = kelly_position_size(10000.0, 0.55, 2.0, min_size=10.0)
    # quarter Kelly size = 10000 × 0.0813 = $813
    assert size > 10.0


def test_position_size_caps():
    """Strong edge with full Kelly multiplier hits the cap."""
    # p=0.9, b=5, full multiplier, default cap 0.25
    size = kelly_position_size(10000.0, 0.90, 5.0, multiplier=1.0)
    assert size == 10000.0 * 0.25  # capped at 25%


# ── win_loss_ratio_from_pnl helper ──────────────────────────────────────────

def test_win_loss_ratio_basic():
    assert win_loss_ratio_from_pnl(200.0, 100.0) == 2.0


def test_win_loss_ratio_returns_none_on_invalid():
    assert win_loss_ratio_from_pnl(None, 100.0) is None
    assert win_loss_ratio_from_pnl(200.0, None) is None
    assert win_loss_ratio_from_pnl(0.0, 100.0) is None
    assert win_loss_ratio_from_pnl(200.0, 0.0) is None
    assert win_loss_ratio_from_pnl(-100.0, 50.0) is None
    assert win_loss_ratio_from_pnl(100.0, -50.0) is None


def test_win_loss_ratio_composes_with_kelly():
    """End-to-end: avg_win/avg_loss -> Kelly fraction -> position size."""
    avg_win = 150.0
    avg_loss = 100.0
    win_prob = 0.55
    b = win_loss_ratio_from_pnl(avg_win, avg_loss)
    assert b == 1.5
    f = kelly_fraction(win_prob, b)
    # f* = (0.55*1.5 - 0.45)/1.5 = (0.825 - 0.45)/1.5 = 0.25
    assert math.isclose(f, 0.25, abs_tol=1e-9)


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
