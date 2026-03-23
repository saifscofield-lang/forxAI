"""
ForexAI Health Check - Verify all systems are working.
Run: python scripts/health_check.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()


def check(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}{f' - {detail}' if detail else ''}")
    return passed


def main():
    print()
    print("=" * 60)
    print("  ForexAI Health Check")
    print("=" * 60)
    results = []

    # 1. Environment
    print("\n[1] ENVIRONMENT")
    results.append(check("MT5_LOGIN", bool(os.getenv("MT5_LOGIN")), os.getenv("MT5_LOGIN", "MISSING")))
    results.append(check("MT5_PASSWORD", bool(os.getenv("MT5_PASSWORD")), "***" if os.getenv("MT5_PASSWORD") else "MISSING"))
    results.append(check("MT5_SERVER", bool(os.getenv("MT5_SERVER")), os.getenv("MT5_SERVER", "MISSING")))
    mt5_path = os.getenv("MT5_PATH", "")
    results.append(check("MT5_PATH", bool(mt5_path), mt5_path or "NOT SET (will use default)"))
    if mt5_path:
        results.append(check("MT5_PATH exists", os.path.exists(mt5_path), mt5_path))
    results.append(check("TELEGRAM_BOT_TOKEN", bool(os.getenv("TELEGRAM_BOT_TOKEN")), "***" if os.getenv("TELEGRAM_BOT_TOKEN") else "MISSING"))
    results.append(check("TELEGRAM_CHAT_ID", bool(os.getenv("TELEGRAM_CHAT_ID")), os.getenv("TELEGRAM_CHAT_ID", "MISSING")))
    gdrive = os.getenv("GDRIVE_SYNC_PATH", "")
    results.append(check("GDRIVE_SYNC_PATH", bool(gdrive), gdrive or "NOT SET"))
    if gdrive:
        results.append(check("Google Drive accessible", os.path.exists(gdrive.split("/")[0] + "/"), gdrive))

    # 2. MT5 Connection
    print("\n[2] MT5 CONNECTION")
    try:
        import MetaTrader5 as mt5
        init_kwargs = {"path": mt5_path} if mt5_path else {}
        if mt5.initialize(**init_kwargs):
            login = int(os.getenv("MT5_LOGIN", 0))
            password = os.getenv("MT5_PASSWORD", "")
            server = os.getenv("MT5_SERVER", "")
            authorized = mt5.login(login, password=password, server=server)
            if authorized:
                info = mt5.account_info()
                results.append(check("MT5 connected", True, f"Account: {info.login} | {info.company}"))
                results.append(check("Balance", True, f"${info.balance:,.2f}"))
                results.append(check("Equity", True, f"${info.equity:,.2f}"))

                # Test data fetch
                import pandas as pd
                rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_H1, 0, 10)
                results.append(check("Data fetch (EURUSD H1)", rates is not None and len(rates) > 0,
                                     f"{len(rates)} bars" if rates is not None else "FAILED"))

                # Check open positions
                positions = mt5.positions_get()
                pos_count = len(positions) if positions else 0
                results.append(check("Open positions", True, f"{pos_count} positions"))

                mt5.shutdown()
            else:
                results.append(check("MT5 login", False, str(mt5.last_error())))
                mt5.shutdown()
        else:
            results.append(check("MT5 initialize", False, str(mt5.last_error())))
    except ImportError:
        results.append(check("MetaTrader5 package", False, "Not installed"))
    except Exception as e:
        results.append(check("MT5 connection", False, str(e)))

    # 3. Database
    print("\n[3] DATABASE")
    try:
        import sqlite3
        db_path = "data/trading.db"
        results.append(check("Database file exists", os.path.exists(db_path), db_path))
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            c = conn.cursor()

            tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            table_names = [t[0] for t in tables]
            results.append(check("Tables found", len(tables) > 0, ", ".join(table_names[:8])))

            total = c.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            closed = c.execute("SELECT COUNT(*) FROM trades WHERE is_closed=1").fetchone()[0]
            open_t = c.execute("SELECT COUNT(*) FROM trades WHERE is_closed=0").fetchone()[0]
            results.append(check("Trades", True, f"{total} total ({closed} closed, {open_t} open)"))

            if closed > 0:
                wins = c.execute("SELECT COUNT(*) FROM trades WHERE is_closed=1 AND profit>0").fetchone()[0]
                pnl = c.execute("SELECT COALESCE(SUM(profit),0) FROM trades WHERE is_closed=1").fetchone()[0]
                results.append(check("Performance", True, f"Win rate: {wins/closed*100:.1f}% | PnL: ${pnl:+,.2f}"))

            scans = c.execute("SELECT COUNT(*) FROM scan_logs").fetchone()[0]
            results.append(check("Scan logs", True, f"{scans} scans recorded"))

            conn.close()
    except Exception as e:
        results.append(check("Database", False, str(e)))

    # 4. Telegram
    print("\n[4] TELEGRAM")
    try:
        from observability.telegram_notifier import TelegramNotifier
        notifier = TelegramNotifier()
        if notifier.enabled:
            success = notifier.send("<b>Health Check:</b> All systems OK!")
            results.append(check("Telegram send", success, "Test message sent" if success else "Send failed"))
        else:
            results.append(check("Telegram configured", False, "Missing token or chat_id"))
    except Exception as e:
        results.append(check("Telegram", False, str(e)))

    # 5. Google Drive
    print("\n[5] GOOGLE DRIVE")
    if gdrive:
        drive_exists = os.path.exists(gdrive)
        results.append(check("Sync folder", drive_exists, gdrive))
        if drive_exists:
            sync_file = os.path.join(gdrive, "last_sync.txt")
            if os.path.exists(sync_file):
                with open(sync_file) as f:
                    results.append(check("Last sync", True, f.read().strip()))
            else:
                results.append(check("Last sync", False, "Never synced"))
    else:
        results.append(check("Google Drive", False, "GDRIVE_SYNC_PATH not set"))

    # 6. Config
    print("\n[6] CONFIG")
    try:
        import yaml
        with open("config/base.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        instruments = config.get("instruments", [])
        symbols = [i["symbol"] for i in instruments]
        results.append(check("Config loaded", True, f"{len(instruments)} instruments"))
        results.append(check("Symbols", True, ", ".join(symbols)))

        risk = config.get("risk", {})
        results.append(check("Risk per trade", True, f"{risk.get('max_risk_per_trade', '?')}"))
        results.append(check("Daily loss limit", True, f"{risk.get('max_daily_loss', '?')}"))
        results.append(check("Max positions", True, f"{risk.get('max_open_positions', '?')}"))
    except Exception as e:
        results.append(check("Config", False, str(e)))

    # 7. Strategies
    print("\n[7] STRATEGIES")
    try:
        from strategies.rsi_reversal import RSIReversalStrategy
        results.append(check("RSI Reversal", True, "importable"))
        from strategies.macd_crossover import MACDCrossoverStrategy
        results.append(check("MACD Crossover", True, "importable"))
        from strategies.bollinger_bounce import BollingerBounceStrategy
        results.append(check("Bollinger Bounce", True, "importable"))
        from strategies.sma_crossover import SMACrossoverStrategy
        results.append(check("SMA Crossover", True, "importable (disabled)"))
    except ImportError as e:
        results.append(check("Strategy import", False, str(e)))

    # 8. Log file
    print("\n[8] LOGS")
    log_path = "data/logs/paper_trading.log"
    results.append(check("Log file exists", os.path.exists(log_path), log_path))
    if os.path.exists(log_path):
        size_mb = os.path.getsize(log_path) / (1024 * 1024)
        results.append(check("Log size", True, f"{size_mb:.1f} MB"))

        # Check last log entry
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            if lines:
                last_line = lines[-1].strip()
                results.append(check("Last log entry", True, last_line[:80]))

    # Summary
    passed = sum(1 for r in results if r)
    failed = sum(1 for r in results if not r)
    print()
    print("=" * 60)
    print(f"  RESULT: {passed} passed, {failed} failed")
    if failed == 0:
        print("  STATUS: ALL SYSTEMS GO!")
    else:
        print("  STATUS: ISSUES FOUND - check FAIL items above")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
