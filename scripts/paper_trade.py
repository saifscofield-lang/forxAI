"""
Paper Trading Loop -- ForexAI
Runs SMA Crossover + ML Filter strategy on MT5 Demo account.
Scans every hour on H1 candle close, executes trades, logs everything.

Usage:
    python scripts/paper_trade.py           # Run continuously
    python scripts/paper_trade.py --once    # Run one scan and exit
"""
import sys
import os
sys.path.insert(0, ".")
os.environ["PYTHONIOENCODING"] = "utf-8"

from dotenv import load_dotenv
load_dotenv()

import signal as sig
import time
import yaml
import argparse
from datetime import datetime
from loguru import logger
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from engine.trading_engine import TradingEngine
from strategies.ml_filtered_strategy import MLFilteredStrategy
from storage.database import init_db
from news.news_filter import NewsFilter


# ── Globals ─────────────────────────────────────────────────────────────
engine: TradingEngine = None
scheduler: BlockingScheduler = None
scan_count = 0


def load_ml_models():
    """Load trained LightGBM models for each validated symbol."""
    import lightgbm as lgb

    models = {}
    model_dir = "data/models"

    # Load ML-validated config
    try:
        with open("data/ml_filtered_validated.yaml", "r") as f:
            ml_config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning("No ML validated config found, running without ML filter")
        return models

    for symbol, cfg in ml_config.items():
        model_path = f"{model_dir}/{symbol}_lgbm.txt"
        if os.path.exists(model_path):
            try:
                booster = lgb.Booster(model_file=model_path)
                # Wrap in LGBMClassifier-like interface
                model = lgb.LGBMClassifier()
                model._Booster = booster
                model.fitted_ = True
                model._n_classes = 2
                models[symbol] = {
                    "model": model,
                    "threshold": cfg.get("confidence_threshold", 0.50),
                }
                logger.info(f"  Loaded ML model for {symbol} (threshold={cfg.get('confidence_threshold', 0.50)})")
            except Exception as e:
                logger.warning(f"  Failed to load model for {symbol}: {e}")
        else:
            logger.warning(f"  No model file for {symbol} at {model_path}")

    return models


def create_strategies(config, ml_models):
    """Create ML-filtered strategies for validated symbols."""
    strategies = []

    # Load optimized SMA params
    try:
        with open("data/optimized_params.yaml", "r") as f:
            opt_params = yaml.safe_load(f)
    except FileNotFoundError:
        opt_params = {}

    # ML-validated symbols (use ML filter)
    try:
        with open("data/ml_filtered_validated.yaml", "r") as f:
            ml_validated = yaml.safe_load(f)
    except FileNotFoundError:
        ml_validated = {}

    instruments = {inst["symbol"]: inst for inst in config.get("instruments", [])}

    for symbol in instruments:
        params = opt_params.get(symbol, {})
        ml_info = ml_models.get(symbol)

        strategy = MLFilteredStrategy(
            symbol=symbol,
            fast_period=int(params.get("fast_period", 20)),
            slow_period=int(params.get("slow_period", 50)),
            rsi_period=int(params.get("rsi_period", 14)),
            atr_period=int(params.get("atr_period", 14)),
            atr_sl_multiplier=float(params.get("atr_sl_mult", 1.5)),
            atr_tp_multiplier=float(params.get("atr_tp_mult", 2.5)),
            model=ml_info["model"] if ml_info else None,
            confidence_threshold=ml_info["threshold"] if ml_info else 0.50,
        )

        ml_status = "ML ON" if ml_info else "NO ML"
        logger.info(
            f"  {symbol}: SMA {strategy.fast_period}/{strategy.slow_period} | "
            f"RSI {strategy.rsi_period} | ATR {strategy.atr_period} | "
            f"SL {strategy.atr_sl_multiplier}x TP {strategy.atr_tp_multiplier}x | "
            f"{ml_status}"
        )
        strategies.append(strategy)

    return strategies


def scan_and_trade():
    """Single scan cycle -- called by scheduler every hour."""
    global scan_count
    scan_count += 1

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    logger.info(f"{'='*50}")
    logger.info(f"Scan #{scan_count} at {now}")
    logger.info(f"{'='*50}")

    try:
        # Check MT5 connection
        account = engine.adapter.get_account_info()
        if not account:
            logger.error("MT5 disconnected, attempting reconnect...")
            if not engine.adapter.connect():
                logger.error("Reconnect failed, skipping scan")
                return

        # Show account status
        logger.info(
            f"Account: ${account['balance']:,.2f} | "
            f"Equity: ${account['equity']:,.2f} | "
            f"P&L: ${account['profit']:+,.2f}"
        )

        # Check open positions
        positions = engine.adapter.get_open_positions()
        if not positions.empty:
            logger.info(f"Open positions: {len(positions)}")
            for _, pos in positions.iterrows():
                logger.info(
                    f"  #{pos['ticket']} {pos['type']} {pos['symbol']} "
                    f"{pos['volume']} lots | P&L: ${pos['profit']:+,.2f}"
                )

        # Show news status
        if engine.news_filter:
            symbols = list(engine.instruments.keys())
            blocked_symbols = []
            for sym in symbols:
                blocked, reason = engine.news_filter.should_block_trading(sym)
                if blocked:
                    blocked_symbols.append(f"{sym}: {reason}")
            if blocked_symbols:
                logger.warning(f"News blocks active:")
                for bs in blocked_symbols:
                    logger.warning(f"  {bs}")
            else:
                logger.info("No news blocks active")

        # Run scan cycle
        executed = engine.run_once()

        if executed:
            for sig_info in executed:
                logger.success(
                    f"EXECUTED: {sig_info['action']} {sig_info['symbol']} | "
                    f"SL={sig_info['stop_loss']} TP={sig_info['take_profit']} | "
                    f"{sig_info['reason']}"
                )
        else:
            logger.info("No executed signals this scan")

        logger.info(f"Scan #{scan_count} complete")

        # Auto-sync data to Google Drive every 6 scans (~6 hours)
        if scan_count % 6 == 0:
            try:
                from scripts.sync_upload import sync_upload
                logger.info("Auto-syncing data to Google Drive...")
                sync_upload()
                logger.info("Data sync complete")
            except Exception as sync_err:
                logger.warning(f"Data sync failed (non-critical): {sync_err}")

    except Exception as e:
        logger.error(f"Scan error: {e}")


def shutdown(signum=None, frame=None):
    """Graceful shutdown."""
    logger.info("Shutting down paper trading...")
    if engine:
        engine.notifier.bot_stopped()
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
    if engine and engine.running:
        engine.stop()
    logger.info("Shutdown complete")
    sys.exit(0)


def main():
    global engine, scheduler

    parser = argparse.ArgumentParser(description="ForexAI Paper Trading")
    parser.add_argument("--once", action="store_true", help="Run one scan and exit")
    args = parser.parse_args()

    # ── Setup logging ───────────────────────────────────────────────
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        level="INFO",
        colorize=True,
    )
    os.makedirs("data/logs", exist_ok=True)
    logger.add(
        "data/logs/paper_trading.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
        level="INFO",
        rotation="10 MB",
        retention="30 days",
    )

    # ── Banner ──────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("     ForexAI Paper Trading")
    print("     Strategy: SMA Crossover + ML Filter + News Filter")
    print(f"     Mode: {'Single scan' if args.once else 'Continuous (H1 schedule)'}")
    print("=" * 60)
    print()

    # ── Initialize database ─────────────────────────────────────────
    init_db()

    # ── Load config ─────────────────────────────────────────────────
    with open("config/base.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # ── Load ML models ──────────────────────────────────────────────
    logger.info("Loading ML models...")
    ml_models = load_ml_models()

    # ── Create strategies ───────────────────────────────────────────
    logger.info("Creating strategies...")
    strategies = create_strategies(config, ml_models)

    # ── Initialize News Filter ────────────────────────────────────
    symbols = [inst['symbol'] for inst in config['instruments']]
    logger.info("Initializing news filter...")
    news_filter = NewsFilter(
        block_minutes_before=30,
        block_minutes_after=30,
        min_impact="HIGH",
        symbols=symbols,
    )
    logger.info("  News filter: block 30min before/after HIGH impact events")

    # ── Initialize engine ───────────────────────────────────────────
    logger.info("Initializing trading engine...")
    engine = TradingEngine()
    engine.set_news_filter(news_filter)

    for strategy in strategies:
        engine.add_strategy(strategy)

    if not engine.start():
        logger.error("Failed to start engine. Is MT5 running?")
        return

    account = engine.adapter.get_account_info()
    print()
    print(f"  Account: {account['login']}")
    print(f"  Server:  {account['server']}")
    print(f"  Balance: ${account['balance']:,.2f}")
    print(f"  Symbols: {', '.join(symbols)}")
    print(f"  ML Models: {', '.join(ml_models.keys()) if ml_models else 'None'}")
    print(f"  News Filter: ON (block 30min around HIGH impact)")
    print()

    # Telegram notification: bot started
    engine.notifier.bot_started(account, symbols, list(ml_models.keys()))

    # ── Register shutdown handler ───────────────────────────────────
    sig.signal(sig.SIGINT, shutdown)
    sig.signal(sig.SIGTERM, shutdown)

    if args.once:
        # ── Single scan mode ────────────────────────────────────────
        logger.info("Running single scan...")
        scan_and_trade()
        engine.stop()
    else:
        # ── Continuous mode with APScheduler ────────────────────────
        logger.info("Starting scheduled paper trading...")
        logger.info("Schedule: every hour at minute 5 (5 min after candle close)")
        logger.info("Press Ctrl+C to stop")
        print()

        # Run first scan immediately
        scan_and_trade()

        # Schedule hourly scans (5 min after each hour to ensure candle is closed)
        scheduler = BlockingScheduler()
        scheduler.add_job(
            scan_and_trade,
            trigger=CronTrigger(minute=5),  # Every hour at :05
            id="hourly_scan",
            name="Hourly H1 Scan",
            misfire_grace_time=300,  # 5 min grace period
        )

        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            shutdown()


if __name__ == "__main__":
    main()
