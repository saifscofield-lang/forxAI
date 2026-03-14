"""Tests for NewsFilter — no MT5 connection required."""
import pytest
from datetime import datetime, timedelta
from news.news_filter import NewsFilter


class TestNewsFilterInit:
    def test_default_params(self):
        nf = NewsFilter()
        assert nf.block_before == timedelta(minutes=30)
        assert nf.block_after == timedelta(minutes=30)
        assert nf.min_impact == "HIGH"

    def test_custom_params(self):
        nf = NewsFilter(block_minutes_before=15, block_minutes_after=45, min_impact="MEDIUM")
        assert nf.block_before == timedelta(minutes=15)
        assert nf.block_after == timedelta(minutes=45)
        assert nf.min_impact == "MEDIUM"

    def test_symbol_currency_mapping(self):
        nf = NewsFilter(symbols=["EURUSD", "USDJPY"])
        assert "USD" in nf._symbol_currencies["EURUSD"]
        assert "EUR" in nf._symbol_currencies["EURUSD"]
        assert "USD" in nf._symbol_currencies["USDJPY"]
        assert "JPY" in nf._symbol_currencies["USDJPY"]


class TestShouldBlockTrading:
    def test_no_events_no_block(self):
        nf = NewsFilter(symbols=["EURUSD"])
        nf._cached_events = []
        nf._cache_time = datetime.utcnow()
        blocked, reason = nf.should_block_trading("EURUSD")
        assert blocked is False
        assert reason is None

    def test_blocks_on_high_impact_event(self):
        nf = NewsFilter(symbols=["EURUSD"], min_impact="HIGH")
        now = datetime.utcnow()
        nf._cached_events = [{
            "event_id": 1,
            "time": now + timedelta(minutes=10),
            "currency": "USD",
            "event_name": "Non-Farm Payrolls",
            "impact": "HIGH",
            "actual": None, "forecast": None, "previous": None, "surprise": None,
        }]
        nf._cache_time = now
        blocked, reason = nf.should_block_trading("EURUSD")
        assert blocked is True
        assert "Non-Farm Payrolls" in reason

    def test_no_block_on_medium_when_high_only(self):
        nf = NewsFilter(symbols=["EURUSD"], min_impact="HIGH")
        now = datetime.utcnow()
        nf._cached_events = [{
            "event_id": 2,
            "time": now + timedelta(minutes=10),
            "currency": "USD",
            "event_name": "Building Permits",
            "impact": "MEDIUM",
            "actual": None, "forecast": None, "previous": None, "surprise": None,
        }]
        nf._cache_time = now
        blocked, reason = nf.should_block_trading("EURUSD")
        assert blocked is False

    def test_no_block_on_irrelevant_currency(self):
        nf = NewsFilter(symbols=["EURUSD"], min_impact="HIGH")
        now = datetime.utcnow()
        nf._cached_events = [{
            "event_id": 3,
            "time": now + timedelta(minutes=10),
            "currency": "JPY",
            "event_name": "BOJ Rate Decision",
            "impact": "HIGH",
            "actual": None, "forecast": None, "previous": None, "surprise": None,
        }]
        nf._cache_time = now
        blocked, reason = nf.should_block_trading("EURUSD")
        assert blocked is False

    def test_no_block_outside_window(self):
        nf = NewsFilter(symbols=["EURUSD"], block_minutes_before=30, min_impact="HIGH")
        now = datetime.utcnow()
        nf._cached_events = [{
            "event_id": 4,
            "time": now + timedelta(minutes=60),  # Too far away
            "currency": "USD",
            "event_name": "CPI",
            "impact": "HIGH",
            "actual": None, "forecast": None, "previous": None, "surprise": None,
        }]
        nf._cache_time = now
        blocked, reason = nf.should_block_trading("EURUSD")
        assert blocked is False


class TestGetNewsFeatures:
    def test_no_events_defaults(self):
        nf = NewsFilter(symbols=["EURUSD"])
        nf._cached_events = []
        nf._cache_time = datetime.utcnow()
        features = nf.get_news_features("EURUSD")
        assert features["has_news_1h"] is False
        assert features["has_high_impact_1h"] is False
        assert features["minutes_to_next_news"] == 999.0

    def test_nearby_event_detected(self):
        nf = NewsFilter(symbols=["EURUSD"])
        now = datetime.utcnow()
        nf._cached_events = [{
            "event_id": 5,
            "time": now + timedelta(minutes=20),
            "currency": "USD",
            "event_name": "FOMC",
            "impact": "HIGH",
            "actual": None, "forecast": None, "previous": None, "surprise": None,
        }]
        nf._cache_time = now
        features = nf.get_news_features("EURUSD")
        assert features["has_news_1h"] is True
        assert features["has_high_impact_1h"] is True
        assert features["minutes_to_next_news"] < 25
        assert features["nearest_news_impact_high"] == 1
