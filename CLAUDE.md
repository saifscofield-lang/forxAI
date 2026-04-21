# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Algorithmic forex trading platform connecting to MetaTrader 5 via Python. Paper trading mode on a MetaQuotes demo account. Phase 0-1 complete (indicators, strategy, risk, engine); Phase 2 next (backtesting, ML, analytics).

**Current state (2026-04-21):** v3 (engine v2.4) is the running STABLE segment on MT5 demo. v4 Phase 10 crypto-momentum research is at step 5 of 8 complete — OOS validation RED (both LO/12m and LO/12w fail the drift-stability gate; LO/12w passes 3 of 4 OOS gates). Correlation analysis confirmed v4 diversifies from the FX book (ρ=0.13). Phase 10.5 (regime-filter rescue) seeded as `PENDING_ACTIVATION`. Formal go/no-go decision deferred. v3 paper trading continues through the 2026-04-28 go/no-go meeting.

**Windows-only** — the MT5 Python API only works on Windows. MT5 Terminal must be installed and running locally.

## Environment Setup

```bash
cd d:/forexAI
python -m venv venv
venv/Scripts/activate
pip install -r requirements/requirements_phase0.txt
pip install -r requirements/requirements_dev.txt   # pytest, black, isort, flake8
```

Copy `.env.example` to `.env` and fill in MT5 credentials. The `.env` is loaded via `python-dotenv` at the top of each script before other imports.

## Commands

```bash
# Trading
python scripts/run_engine.py                    # Run one scan cycle
python scripts/test_mt5_connection.py            # Verify MT5 connectivity
python scripts/download_historical_data.py       # Bulk download historical bars

# Testing
pytest tests/ -v                                 # All tests
pytest tests/test_indicators.py -v               # Single file
pytest --cov=features,risk,engine tests/         # With coverage

# Formatting & linting
black .
isort .
flake8
```

No `pyproject.toml`, `setup.cfg`, or `pytest.ini` exists — all tools run with defaults.

## Architecture

Pipeline: **MT5 → Indicators → Strategy → Risk → Execution → Storage**

```
scripts/run_engine.py
  └─ TradingEngine (engine/trading_engine.py)    — orchestrator
       ├─ MT5Adapter.get_ohlcv()                 — fetch price bars
       ├─ Strategy.generate_signal(df)           — compute indicators, emit signal
       ├─ RiskManager.validate_trade()           — position sizing, drawdown check
       ├─ MT5Adapter.place_order()               — send order to broker
       └─ Trade model → SQLite                   — persist record
```

### Key Contracts

**Strategies** — implement `prepare(df)` and `generate_signal(df: DataFrame) → dict | None`. Signal dict: `{symbol, direction ("BUY"/"SELL"), sl, tp, atr}`. Register via `engine.add_strategy(instance)`.

**RiskManager** — constructed with `config_path` (default `config/base.yaml`). `validate_trade()` returns `(bool, str)`. `calculate_position_size(balance, stop_loss_pips, pip_value)` returns lot size.

**MT5Adapter** — wraps MetaTrader5 package. `connect()` returns bool. `get_ohlcv(symbol, timeframe, bars)` returns DataFrame. `place_order()` returns `{success, ticket, price, volume}` or `{success: False, error}`.

**Indicators** — stateless functions in `features/technical/indicators.py`. Each takes a DataFrame and returns it with new columns added (`add_sma`, `add_ema`, `add_rsi`, `add_atr`, `add_macd`, `add_bollinger_bands`).

**Storage** — SQLAlchemy 2.0 ORM in `storage/database.py`. Three models: `OHLCVBar`, `Trade`, `AccountSnapshot`. SQLite at `data/trading.db` with `check_same_thread=False`.

## Important Patterns

### Imports
All imports are **absolute** (e.g., `from engine.trading_engine import TradingEngine`). Scripts prepend the project root with `sys.path.insert(0, ".")`. All `__init__.py` files are empty.

### Config Loading
Both `TradingEngine` and `RiskManager` accept `config_path: str = "config/base.yaml"` in their constructors and load YAML once at init. Credentials come from `.env` via `os.getenv()`. Database URL defaults to `sqlite:///data/trading.db`.

### Database Sessions
`SessionLocal` factory from `storage/database.py`. Each operation creates a new session, commits/rollbacks in try/except, and closes in `finally`. No shared sessions across calls.

### Logging
Uses `loguru`. Modules import `from loguru import logger` and log directly — no centralized config. Scripts that need custom formatting call `logger.remove()` then `logger.add()` with their own format/rotation settings.

### Error Handling
No retry logic anywhere. MT5Adapter returns `False` or empty DataFrames on failure. TradingEngine wraps DB writes in try/except with rollback. Failures are logged and propagated, not retried.

## Gotchas

- **Timezone**: MT5 returns UTC timestamps. The downloader converts to UTC-aware then strips timezone (`tz_localize(None)`) for consistent UTC-naive storage. All datetime comparisons assume UTC.
- **MT5 bar limit**: MT5 caps fetches at 99,999 bars. `HistoricalDownloader` paginates in 50,000-bar batches, deduplicates, and upserts.
- **Pip value**: `pip_value` passed to RiskManager is pre-scaled (0.0001 for 5-digit pairs like EURUSD, 0.01 for 3-digit JPY pairs). The formula multiplies by 100,000 (standard lot size) internally.
- **Timeframe strings**: MT5Adapter maps string timeframes (`"M1"`, `"H1"`, `"D1"`, etc.) to MT5 constants via `TIMEFRAME_MAP` dict. Invalid timeframes return empty DataFrames.
- **DataFrame columns**: Consistent naming: `open, high, low, close, volume` (lowercase). MT5's `tick_volume` is renamed to `volume`. Indicator functions add columns like `sma_20`, `rsi_14`, etc.
- **Parquet files**: Stored at `data/raw/{SYMBOL}/{TIMEFRAME}.parquet` with upsert (read existing + concat + dedup on `symbol, timeframe, time`).
- **.gitignore comments are in Arabic** — the project creator's primary language.

## Adding a New Strategy

1. Create a class in `strategies/` with `prepare(df)` and `generate_signal(df)` methods
2. Use indicator functions from `features/technical/indicators.py`
3. Return `None` for no signal, or `{symbol, direction, sl, tp, atr}`
4. Register in `scripts/run_engine.py`: `engine.add_strategy(YourStrategy())`
5. Reference: `strategies/sma_crossover.py` (SMA20/50 crossover + RSI filter, ATR-based SL/TP)

## Configuration

- `config/base.yaml` — instruments (EURUSD, GBPUSD, USDJPY, XAUUSD), timeframes (H1 primary, H4 secondary, M15 confirmation), risk limits, logging settings
- `.env` — MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, DATABASE_URL, TRADING_MODE

## Test Structure

Tests live in `tests/`. No `conftest.py` — fixtures are defined in each test file. No mocking; tests use real pandas/numpy calculations with synthetic data. Test classes group related assertions (e.g., `TestSMA`, `TestRSI`).

## Requirements

- `requirements/requirements_phase0.txt` — core (MetaTrader5, pandas, numpy, sqlalchemy, loguru, pyyaml, dotenv, apscheduler)
- `requirements/requirements_dev.txt` — dev tools (black, isort, flake8, pytest, jupyter)
- `requirements/requirements_ml.txt` — Phase 2 (scikit-learn, lightgbm, xgboost, optuna)
- `requirements/requirements_backtest.txt` — Phase 2 (backtesting library)
