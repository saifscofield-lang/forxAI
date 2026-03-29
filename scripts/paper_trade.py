"""
Paper Trading Loop -- ForexAI (Clean Data Collection Mode)
Runs 4 strategies on 8 symbols, scans every H1 candle.
Goal: collect high-quality trades for ML training.

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
from strategies.sma_crossover import SMACrossoverStrategy
from strategies.rsi_reversal import RSIReversalStrategy
from strategies.macd_crossover import MACDCrossoverStrategy
from strategies.bollinger_bounce import BollingerBounceStrategy
from strategies.ml_direct_strategy import MLDirectStrategy
from storage.database import init_db
from news.news_filter import NewsFilter
from observability.telegram_commands import (
    TelegramCommandHandler, generate_daily_report,
    generate_weekly_report, check_loss_alert,
)


# -- Globals --
engine: TradingEngine = None
scheduler: BlockingScheduler = None
cmd_handler: TelegramCommandHandler = None
scan_count = 0


def create_strategies(config):
    """Create all strategies for all symbols - no ML filter, maximum signals."""
    strategies = []

    # Load optimized SMA params (if available)
    try:
        with open("data/optimized_params.yaml", "r") as f:
            opt_params = yaml.safe_load(f) or {}
    except FileNotFoundError:
        opt_params = {}

    instruments = {inst["symbol"]: inst for inst in config.get("instruments", [])}

    for symbol in instruments:
        params = opt_params.get(symbol, {})

        # 1. SMA Crossover - DISABLED (IMP-03: 33% WR, -$1,522 net loss)
        # Re-enable only after backtesting with H4 trend filter
        # strategies.append(SMACrossoverStrategy(
        #     symbol=symbol,
        #     fast_period=int(params.get("fast_period", 20)),
        #     slow_period=int(params.get("slow_period", 50)),
        #     rsi_period=int(params.get("rsi_period", 14)),
        #     atr_period=int(params.get("atr_period", 14)),
        #     atr_sl_multiplier=float(params.get("atr_sl_mult", 1.5)),
        #     atr_tp_multiplier=float(params.get("atr_tp_mult", 2.5)),
        # ))

        # IMP-09: Use per-symbol optimized SL/TP multipliers
        sl_mult = float(params.get("atr_sl_mult", 2.0))
        tp_mult = float(params.get("atr_tp_mult", 3.0))

        # 2. RSI Reversal — IMP-51: exclude XAUUSD (0% WR), IMP-52: exclude USDCAD (33% WR)
        if symbol not in ("XAUUSD", "USDCAD"):
            strategies.append(RSIReversalStrategy(
                symbol=symbol,
                rsi_period=14,
                oversold=30.0,
                overbought=70.0,
                atr_sl_multiplier=sl_mult,
                atr_tp_multiplier=tp_mult,
            ))

        # 3. MACD Crossover (slightly wider than base)
        strategies.append(MACDCrossoverStrategy(
            symbol=symbol,
            atr_sl_multiplier=sl_mult * 1.25,
            atr_tp_multiplier=tp_mult * 1.15,
        ))

        # 4. Bollinger Bounce — DISABLED (IMP-49): 41% WR, -$3,126, avg RR -0.11
        # strategies.append(BollingerBounceStrategy(
        #     symbol=symbol,
        #     atr_sl_multiplier=sl_mult,
        #     atr_tp_multiplier=tp_mult,
        # ))

        # 5. ML Direct Strategy — market-driven signal generation
        ml_strat = MLDirectStrategy(
            symbol=symbol,
            confidence_threshold=0.55,
            atr_sl_multiplier=sl_mult,
            atr_tp_multiplier=tp_mult,
        )
        if ml_strat.model is not None:
            strategies.append(ml_strat)
            ml_loaded = True
        else:
            ml_loaded = False

        if symbol in ("XAUUSD", "USDCAD"):
            logger.info(f"  {symbol}: {'2' if ml_loaded else '1'} strategies (MACD{', ML Direct' if ml_loaded else ''}) - RSI excluded (IMP-51/52)")
        else:
            logger.info(f"  {symbol}: {'3' if ml_loaded else '2'} strategies (RSI, MACD{', ML Direct' if ml_loaded else ''}) - SMA disabled (IMP-03), BB disabled (IMP-49)")

    return strategies


def _is_market_open():
    """Check if forex market is open (closed Sat 00:00 - Sun 22:00 UTC approx)."""
    from datetime import timezone
    now_utc = datetime.now(timezone.utc)
    weekday = now_utc.weekday()  # 0=Mon, 5=Sat, 6=Sun
    hour = now_utc.hour
    # Closed: Friday ~22:00 UTC to Sunday ~22:00 UTC
    if weekday == 5:  # Saturday
        return False
    if weekday == 6 and hour < 22:  # Sunday before 22:00
        return False
    if weekday == 4 and hour >= 22:  # Friday after 22:00
        return False
    return True


def scan_and_trade():
    """Single scan cycle -- called by scheduler every H1 candle."""
    global scan_count

    if not _is_market_open():
        logger.info("Market closed (weekend) - skipping scan")
        return

    # Check if paused via Telegram /pause command
    if cmd_handler and cmd_handler.is_paused:
        logger.info("Trading paused via /pause command - skipping scan")
        return

    scan_count += 1

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    logger.info(f"{'='*60}")
    logger.info(f"Scan #{scan_count} at {now}")
    logger.info(f"{'='*60}")

    try:
        # Check MT5 connection
        account = engine.adapter.get_account_info()
        if not account:
            logger.error("MT5 disconnected, attempting reconnect...")
            if not engine.adapter.connect():
                logger.error("Reconnect failed, skipping scan")
                engine.notifier.send("🔌 <b>خطأ:</b> انقطع الاتصال بـ MT5 وفشلت إعادة الاتصال!")
                return

        # IMP-53 + IMP-61: Check if AutoTrading is enabled — skip cycle if disabled
        import MetaTrader5 as mt5
        term_info = mt5.terminal_info()
        if term_info and not term_info.trade_allowed:
            msg = "[ForexAI] AutoTrading DISABLED! Press Ctrl+E in MT5. Skipping this cycle."
            logger.warning(msg)
            engine.notifier.send(f"⚠️ <b>تحذير:</b> التداول التلقائي معطل! اضغط Ctrl+E في MT5.")
            return

        # Show account status
        logger.info(
            f"Account: ${account['balance']:,.2f} | "
            f"Equity: ${account['equity']:,.2f} | "
            f"P&L: ${account['profit']:+,.2f}"
        )

        # Check open positions and update live PnL in DB
        positions = engine.adapter.get_open_positions()
        if not positions.empty:
            logger.info(f"Open positions: {len(positions)}")
            for _, pos in positions.iterrows():
                logger.info(
                    f"  #{pos['ticket']} {pos['type']} {pos['symbol']} "
                    f"{pos['volume']} lots | P&L: ${pos['profit']:+,.2f}"
                )

            # Update live PnL in DB so dashboard can show it
            try:
                import sqlite3
                conn = sqlite3.connect("data/trading.db")
                for _, pos in positions.iterrows():
                    conn.execute(
                        "UPDATE trades SET profit=? WHERE ticket=? AND is_closed=0",
                        (pos['profit'], pos['ticket'])
                    )
                conn.commit()
                conn.close()
            except Exception:
                pass

        # Show news status
        blocked_symbols = []
        upcoming_news = []
        if engine.news_filter:
            symbols = list(engine.instruments.keys())
            for sym in symbols:
                blocked, reason = engine.news_filter.should_block_trading(sym)
                if blocked:
                    blocked_symbols.append(f"{sym}: {reason}")

            upcoming_news = engine.news_filter.fetch_events(hours_ahead=8, hours_behind=1)
            high_news = [e for e in upcoming_news if e.get("impact") == "HIGH"]

            if blocked_symbols:
                logger.warning("News blocks active:")
                for bs in blocked_symbols:
                    logger.warning(f"  {bs}")
            else:
                logger.info("No news blocks active")

            if high_news:
                logger.info(f"Upcoming HIGH impact news: {len(high_news)}")
                for ev in high_news[:5]:
                    logger.info(f"  [{ev['currency']}] {ev['event_name']} @ {ev['time']}")

        # Run scan cycle
        executed, scan_details = engine.run_once()

        if executed:
            for sig_info in executed:
                logger.success(
                    f"EXECUTED: {sig_info['action']} {sig_info['symbol']} "
                    f"[{sig_info.get('strategy', '?')}] | "
                    f"SL={sig_info['stop_loss']} TP={sig_info['take_profit']} | "
                    f"{sig_info['reason']}"
                )
        else:
            logger.info("No executed signals this scan")

        # Send Telegram report with open positions
        open_count = 0 if positions is None or (hasattr(positions, 'empty') and positions.empty) else len(positions)

        # Build open positions summary for Telegram
        pos_lines = []
        if not positions.empty:
            for _, pos in positions.iterrows():
                pnl_icon = "🟢" if pos['profit'] >= 0 else "🔴"
                pos_lines.append(
                    f"  {pnl_icon} {pos['type']} <b>{pos['symbol']}</b> | {pos['volume']} لوت\n"
                    f"     💵 ${pos['profit']:+,.2f} | دخول: {pos['open_price']}\n"
                    f"     🛑 SL: {pos.get('sl', 0)} | 🎯 TP: {pos.get('tp', 0)}"
                )

        pos_text = "\n".join(pos_lines) if pos_lines else "لا يوجد"
        positions_msg = f"\n\n📂 <b>الصفقات المفتوحة:</b>\n{pos_text}" if pos_lines else ""

        engine.notifier.detailed_scan_report(
            scan_number=scan_count,
            account=account,
            open_positions=open_count,
            scan_details=scan_details,
            executed=executed,
            news_events=upcoming_news if upcoming_news else None,
        )

        # Send positions detail separately (detailed_scan_report has char limit)
        if pos_lines:
            engine.notifier.send(
                f"📂 <b>الصفقات المفتوحة ({open_count})</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n" +
                "\n".join(pos_lines)
            )

        logger.info(f"Scan #{scan_count} complete")

        # Auto-sync data to Google Drive every 6 scans (~6 hours at H1 interval)
        if scan_count % 6 == 0:
            try:
                from scripts.sync_upload import sync_upload
                logger.info("Auto-syncing data to Google Drive...")
                sync_upload()
                logger.info("Data sync complete")
            except Exception as sync_err:
                logger.warning(f"Data sync failed (non-critical): {sync_err}")

        # Export training data every 24 scans (~24 hours at H1 interval)
        if scan_count % 24 == 0:
            try:
                from scripts.export_training_data import export_all
                logger.info("Exporting ML training data...")
                export_all()
                logger.info("Training data export complete")
            except Exception as export_err:
                logger.warning(f"Training data export failed (non-critical): {export_err}")

    except Exception as e:
        logger.error(f"Scan error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        engine.notifier.send(f"❌ <b>خطأ في المسح:</b>\n<code>{e}</code>")


def monitor_positions():
    """Monitor open positions for breakeven/trailing stops (IMP-07)."""
    try:
        if not _is_market_open():
            return
        if engine and engine.running:
            engine.monitor_positions()
    except Exception as e:
        logger.debug(f"Position monitor error: {e}")


def shutdown(signum=None, frame=None):
    """Graceful shutdown."""
    logger.info("Shutting down paper trading...")
    if cmd_handler:
        cmd_handler.stop()
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

    # -- Setup logging --
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

    # -- Banner --
    print()
    print("=" * 60)
    print("     ForexAI Paper Trading - CLEAN DATA COLLECTION")
    print("     Strategies: RSI + MACD (x7 symbols)")
    print(f"     Mode: {'Single scan' if args.once else 'Continuous (H1 candle)'}")
    print("=" * 60)
    print()

    # -- Pre-start health check --
    logger.info("Running pre-start health check...")
    from observability.telegram_notifier import TelegramNotifier
    _notifier = TelegramNotifier()
    errors = []

    # Check .env
    if not os.getenv("MT5_LOGIN"):
        errors.append("MT5_LOGIN missing in .env")
    if not os.getenv("MT5_PASSWORD"):
        errors.append("MT5_PASSWORD missing in .env")

    # Check MT5 connection
    try:
        import MetaTrader5 as mt5
        mt5_path = os.getenv("MT5_PATH", "")
        if mt5_path:
            if not mt5.initialize(path=mt5_path):
                errors.append(f"MT5 not running: {mt5.last_error()}")
        elif not mt5.initialize():
            errors.append(f"MT5 not running: {mt5.last_error()}")
        if not errors:
            info = mt5.account_info()
            if info:
                logger.info(f"  MT5: OK (Account {info.login}, ${info.balance:,.2f})")
            else:
                errors.append("MT5 connected but no account info")
            mt5.shutdown()
    except Exception as e:
        errors.append(f"MT5 error: {e}")

    # Check database
    try:
        import sqlite3
        if os.path.exists("data/trading.db"):
            conn = sqlite3.connect("data/trading.db")
            count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            logger.info(f"  Database: OK ({count} trades)")
            conn.close()
        else:
            errors.append("Database file not found")
    except Exception as e:
        errors.append(f"Database error: {e}")

    # Check config
    try:
        from engine.trading_engine import resolve_config_path
        _cfg_path = resolve_config_path()
        with open(_cfg_path, "r", encoding="utf-8") as f:
            _test_cfg = yaml.safe_load(f)
        logger.info(f"  Config: OK ({_cfg_path}, {len(_test_cfg.get('instruments', []))} instruments)")
    except Exception as e:
        errors.append(f"Config error: {e}")

    if errors:
        error_msg = "\n".join(f"- {e}" for e in errors)
        logger.error(f"Health check FAILED:\n{error_msg}")
        _notifier.send(f"❌ <b>فشل فحص النظام</b>\n{error_msg}")
        print(f"\n  HEALTH CHECK FAILED - {len(errors)} errors. Fix and retry.\n")
        return
    else:
        logger.info("  Health check: ALL PASS")
        _notifier.send(
            "✅ <b>فحص النظام — نجح</b>\n"
            f"🔗 MT5: متصل\n"
            f"💾 قاعدة البيانات: OK\n"
            f"⚙️ الإعدادات: OK\n"
            "🚀 جاري تشغيل البوت..."
        )

    # -- Initialize database --
    init_db()

    # -- Load config (IMP-27: auto-select paper/live based on TRADING_MODE) --
    from engine.trading_engine import resolve_config_path
    _cfg_path = resolve_config_path()
    logger.info(f"Loading config: {_cfg_path}")
    with open(_cfg_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # -- Create strategies (no ML filter) --
    logger.info("Creating strategies (data collection mode - no ML filter)...")
    strategies = create_strategies(config)
    logger.info(f"Total strategies: {len(strategies)}")

    # -- Initialize News Filter --
    symbols = [inst['symbol'] for inst in config['instruments']]
    logger.info("Initializing news filter...")
    news_filter = NewsFilter(
        block_minutes_before=30,
        block_minutes_after=30,
        min_impact="HIGH",
        symbols=symbols,
    )
    logger.info("  News filter: block 30min before/after HIGH impact events")

    # -- Initialize engine --
    logger.info("Initializing trading engine...")
    engine = TradingEngine()
    engine.set_news_filter(news_filter)

    for strategy in strategies:
        engine.add_strategy(strategy)

    if not engine.start():
        logger.error("Failed to start engine. Is MT5 running?")
        _notifier.send("❌ <b>فشل التشغيل</b>\nلم يتمكن المحرك من الاتصال بـ MT5.")
        return

    account = engine.adapter.get_account_info()
    print()
    print(f"  Account: {account['login']}")
    print(f"  Server:  {account['server']}")
    print(f"  Balance: ${account['balance']:,.2f}")
    print(f"  Symbols: {', '.join(symbols)}")
    print(f"  Strategies per symbol: 3 (RSI, MACD, BB) - SMA disabled")
    print(f"  Total strategy instances: {len(strategies)}")
    print(f"  Scan interval: every H1 candle")
    print(f"  Drive sync: every 6 hours")
    print(f"  News Filter: ON (block 30min around HIGH impact)")
    print()

    # Telegram notification: bot started
    engine.notifier.bot_started(account, symbols, [])

    # -- Start Telegram command handler (interactive commands) --
    global cmd_handler
    cmd_handler = TelegramCommandHandler(engine=engine)
    cmd_handler.start()
    logger.info("Telegram commands active: /status /positions /performance /pause /resume")

    # -- Register shutdown handler --
    sig.signal(sig.SIGINT, shutdown)
    sig.signal(sig.SIGTERM, shutdown)

    if args.once:
        logger.info("Running single scan...")
        scan_and_trade()
        engine.stop()
    else:
        # -- Continuous mode --
        logger.info("Starting scheduled paper trading (CLEAN DATA)...")
        logger.info("Schedule: every H1 candle (at :05 past each hour)")
        logger.info("Press Ctrl+C to stop")
        print()

        # Run first scan immediately
        scan_and_trade()

        # Schedule scans every H1 (at 5 minutes past each hour)
        scheduler = BlockingScheduler()
        scheduler.add_job(
            scan_and_trade,
            trigger=CronTrigger(minute="5"),
            id="scan_h1",
            name="H1 Scan",
            misfire_grace_time=300,
        )

        # IMP-07: Monitor open positions every 5 minutes (breakeven + trailing)
        scheduler.add_job(
            monitor_positions,
            trigger=CronTrigger(minute="*/5"),
            id="monitor_positions",
            name="Position Monitor",
            misfire_grace_time=60,
        )

        # Daily report at 23:00 UTC
        def _send_daily_report():
            if engine and engine.running:
                report = generate_daily_report(engine)
                engine.notifier.send(report)

        scheduler.add_job(
            _send_daily_report,
            trigger=CronTrigger(hour=23, minute=0),
            id="daily_report",
            name="Daily Report",
            misfire_grace_time=300,
        )

        # Weekly report — Sunday at 23:30 UTC
        def _send_weekly_report():
            if engine and engine.running:
                report = generate_weekly_report(engine)
                engine.notifier.send(report)

        scheduler.add_job(
            _send_weekly_report,
            trigger=CronTrigger(day_of_week="sun", hour=23, minute=30),
            id="weekly_report",
            name="Weekly Report",
            misfire_grace_time=300,
        )

        # Loss alert check every hour
        def _check_loss():
            if engine and engine.running:
                check_loss_alert(engine, threshold=-500.0)

        scheduler.add_job(
            _check_loss,
            trigger=CronTrigger(minute="30"),
            id="loss_alert",
            name="Loss Alert Check",
            misfire_grace_time=60,
        )

        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            shutdown()


if __name__ == "__main__":
    main()
