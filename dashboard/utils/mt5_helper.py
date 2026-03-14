"""
MT5 helper utilities for the dashboard.
Wraps the MT5Adapter with dashboard-friendly return types.
"""
import sys
from typing import Optional
import pandas as pd

sys.path.insert(0, ".")

try:
    from execution.broker_adapters.mt5_adapter import MT5Adapter
    _adapter = MT5Adapter()
    MT5_AVAILABLE = True
except Exception:
    MT5_AVAILABLE = False
    _adapter = None


def get_connection_status() -> dict:
    """Check MT5 connection and return status dict."""
    if not MT5_AVAILABLE:
        return {"connected": False, "error": "MT5 package not available on this machine"}
    try:
        connected = _adapter.connect()
        if not connected:
            return {"connected": False, "error": "MT5 failed to connect"}
        info = _adapter.get_account_info()
        _adapter.disconnect()
        return {"connected": True, "account": info}
    except Exception as e:
        return {"connected": False, "error": str(e)}


def get_account_info() -> Optional[dict]:
    """Return live account info from MT5."""
    if not MT5_AVAILABLE:
        return None
    try:
        if not _adapter.connect():
            return None
        info = _adapter.get_account_info()
        _adapter.disconnect()
        return info
    except Exception:
        return None


def get_open_positions() -> pd.DataFrame:
    """Return all open positions from MT5 as DataFrame."""
    if not MT5_AVAILABLE:
        return pd.DataFrame()
    try:
        if not _adapter.connect():
            return pd.DataFrame()
        positions = _adapter.get_open_positions()
        _adapter.disconnect()
        return positions if positions is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def get_current_prices(symbols: list) -> dict:
    """Return current bid/ask for each symbol."""
    if not MT5_AVAILABLE:
        return {}
    try:
        if not _adapter.connect():
            return {}
        prices = {}
        for sym in symbols:
            tick = _adapter.get_tick(sym)
            if tick:
                prices[sym] = tick
        _adapter.disconnect()
        return prices
    except Exception:
        return {}


def get_ohlcv(symbol: str, timeframe: str = "H1", bars: int = 200) -> pd.DataFrame:
    """Fetch OHLCV bars from MT5."""
    if not MT5_AVAILABLE:
        return pd.DataFrame()
    try:
        if not _adapter.connect():
            return pd.DataFrame()
        df = _adapter.get_ohlcv(symbol, timeframe, bars)
        _adapter.disconnect()
        return df if df is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def run_scan(use_ml: bool = True) -> list:
    """
    Run a full scan cycle using the trading engine.
    Returns list of signal dicts (all signals, not just executed ones).
    """
    if not MT5_AVAILABLE:
        return []
    try:
        import yaml
        from engine.trading_engine import TradingEngine

        engine = TradingEngine()

        # Load ML-filtered strategies if available
        if use_ml:
            try:
                import os
                from strategies.ml_filtered_strategy import MLFilteredStrategy
                with open("data/ml_filtered_validated.yaml") as f:
                    validated = yaml.safe_load(f)
                for symbol, info in validated.items():
                    if info.get("recommended", False):
                        model_path = f"data/models/{symbol}_lgbm.txt"
                        if os.path.exists(model_path):
                            strategy = MLFilteredStrategy(
                                symbol=symbol,
                                model_path=model_path,
                                confidence_threshold=info.get("threshold", 0.50),
                            )
                            engine.add_strategy(strategy)
            except Exception:
                # Fall back to plain strategy
                use_ml = False

        if not use_ml:
            from strategies.sma_crossover import SMACrossoverStrategy
            from strategies.ml_filtered_strategy import MLFilteredStrategy
            for sym in ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]:
                engine.add_strategy(SMACrossoverStrategy(symbol=sym))

        if not engine.start():
            return []

        signals = engine.scan_signals()
        engine.stop()
        return signals if signals else []
    except Exception as e:
        return [{"error": str(e)}]


def execute_signal_manual(signal: dict) -> tuple:
    """Manually execute a specific signal through the engine."""
    if not MT5_AVAILABLE:
        return False, "MT5 not available"
    try:
        from engine.trading_engine import TradingEngine
        engine = TradingEngine()
        if not engine.start():
            return False, "Could not connect to MT5"
        success, reason = engine.execute_signal(signal)
        engine.stop()
        return success, reason
    except Exception as e:
        return False, str(e)


def close_position(ticket: int) -> tuple:
    """Close an open position by ticket number."""
    if not MT5_AVAILABLE:
        return False, "MT5 not available"
    try:
        if not _adapter.connect():
            return False, "MT5 connection failed"
        result = _adapter.close_position(ticket)
        _adapter.disconnect()
        if result and result.get("success"):
            return True, f"Position {ticket} closed at {result.get('price')}"
        return False, result.get("error", "Unknown error")
    except Exception as e:
        return False, str(e)
