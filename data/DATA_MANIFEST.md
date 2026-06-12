# DATA MANIFEST — forexAI

Catalog of every cached/ready dataset in `data/`. The project uses **on-demand caching**:
each research phase fetches the instruments it needs once, stores them as parquet, and
reuses them forever (loader `fetch()` functions check the cache before downloading).
This manifest is the single index of what is READY vs what a new hypothesis must fetch.

_Last updated: 2026-06-12 (after Phase 13 VRP added `raw_vol/`)._

## Ready datasets

| Folder | Contents | Source | Size | Used by |
|--------|----------|--------|------|---------|
| `raw/` | 38 parquet — MT5 OHLCV per (symbol, timeframe): EURUSD, GBPUSD, USDJPY, XAUUSD, AUDUSD, USDCAD, USDCHF, NZDUSD × M15/H1/H4/D1 | MT5 terminal | 59 MB | live engine, all FX/gold backtests, rescue phases |
| `raw_crypto/` | 4 parquet — BTC/ETH/BNB/SOL USDT D1 | Binance | 0.5 MB | Phase 10 v4 crypto-momentum (REJECTED) |
| `raw_trend/` | 26 parquet — cross-asset daily (equity/bonds/energy/metals/ag/FX/crypto futures & indices) | yfinance | 2.3 MB | Phase 12 + 12b trend premium (FAILED) |
| `raw_vol/` | 5 parquet — VXX, SVXY, ^VIX, ^VIX3M, ^GSPC daily | yfinance | 0.3 MB | Phase 13 VRP short-vol (FAILED) |
| `macro/` | central-bank policy-rate table (+ loader) | manual/CB | 16 KB | Phase 11 carry (FAILED) |
| `ml_training/` | 8 CSV training sets + 1 feature list | engineered from `raw/` | 17 MB | ML models, meta-labeler |
| `models/` | 4 LightGBM `.txt` + 4 `.json` meta (EURUSD, GBPUSD, USDJPY, XAUUSD) | trained | 15 MB | ml_filter / ml_direct (RETIRED) |
| `research/` | 8 CSV + 1 parquet — backtest/analysis outputs | computed | 1.0 MB | research reports |
| `reports/` | PDF + md + txt summaries | generated | 0.1 MB | reporting |
| `logs/` | 3 `.log` — paper trading / backtest / download | runtime | 1.4 MB | diagnostics |

## Key databases (in `data/`, not folders)

| File | What | Size |
|------|------|------|
| `trading.db` | live paper-trading log (STALE on ASUS — stops 2026-03-27; live copy is on the trading machine, snapshot in `workpc/worklogs_bundle/`) | 8 MB |
| `backtest_results.db` | all backtest runs (40+ per symbol) | 94 MB |
| `improvements.db` | improvements tracker, go/no-go decisions, action items | 0.3 MB |
| `hypothesis_registry.jsonl` | append-only multiple-testing registry — **K=12**, all FAIL | — |

## How to add a new dataset
1. Add the tickers to the phase's `fetch()` (cache dir = `data/raw_<domain>/`).
2. First run downloads + writes parquet; subsequent runs read cache.
3. Update this manifest (folder, source, what uses it).

## Notes
- yfinance `=F`/`^` continuous series carry roll artifacts → winsorize daily returns (see trend/VRP scripts).
- Tradable-instrument history is short: VXX (iPath B) starts **2018-01**, SVXY 2011-10 — a hard constraint on vol-strategy backtests (Phase 13 disclosure).
- No central data loader/ORM for the parquet caches — each script has its own `fetch()` (by design, kept simple).
