"""
ForexAI Health Check - Verify all systems are working.
Run: python scripts/health_check.py
Sends full results to Telegram (all details, not just "OK").
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()


def check(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}{f' - {detail}' if detail else ''}")
    return {"name": name, "passed": passed, "detail": detail}


def main():
    print()
    print("=" * 60)
    print("  ForexAI Health Check")
    print("=" * 60)
    results = []
    sections = {}

    # 1. Environment
    section = "ENVIRONMENT"
    print(f"\n[1] {section}")
    sec_results = []
    sec_results.append(check("MT5_LOGIN", bool(os.getenv("MT5_LOGIN")), os.getenv("MT5_LOGIN", "MISSING")))
    sec_results.append(check("MT5_PASSWORD", bool(os.getenv("MT5_PASSWORD")), "***" if os.getenv("MT5_PASSWORD") else "MISSING"))
    sec_results.append(check("MT5_SERVER", bool(os.getenv("MT5_SERVER")), os.getenv("MT5_SERVER", "MISSING")))
    mt5_path = os.getenv("MT5_PATH", "")
    sec_results.append(check("MT5_PATH", bool(mt5_path), mt5_path or "NOT SET (will use default)"))
    if mt5_path:
        sec_results.append(check("MT5_PATH exists", os.path.exists(mt5_path), mt5_path))
    sec_results.append(check("TELEGRAM_BOT_TOKEN", bool(os.getenv("TELEGRAM_BOT_TOKEN")), "***" if os.getenv("TELEGRAM_BOT_TOKEN") else "MISSING"))
    sec_results.append(check("TELEGRAM_CHAT_ID", bool(os.getenv("TELEGRAM_CHAT_ID")), os.getenv("TELEGRAM_CHAT_ID", "MISSING")))
    gdrive = os.getenv("GDRIVE_SYNC_PATH", "")
    sec_results.append(check("GDRIVE_SYNC_PATH", bool(gdrive), gdrive or "NOT SET"))
    if gdrive:
        sec_results.append(check("Google Drive accessible", os.path.exists(gdrive.split("/")[0] + "/"), gdrive))
    sections[section] = sec_results
    results.extend(sec_results)

    # 2. MT5 Connection
    section = "MT5 CONNECTION"
    print(f"\n[2] {section}")
    sec_results = []
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
                sec_results.append(check("MT5 connected", True, f"Account: {info.login} | {info.company}"))
                sec_results.append(check("Balance", True, f"${info.balance:,.2f}"))
                sec_results.append(check("Equity", True, f"${info.equity:,.2f}"))
                sec_results.append(check("Profit", True, f"${info.profit:+,.2f}"))

                # Test data fetch
                import pandas as pd
                rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_H1, 0, 10)
                sec_results.append(check("Data fetch (EURUSD H1)", rates is not None and len(rates) > 0,
                                         f"{len(rates)} bars" if rates is not None else "FAILED"))

                # Check AutoTrading status
                term_info = mt5.terminal_info()
                if term_info:
                    sec_results.append(check("AutoTrading enabled", term_info.trade_allowed,
                                             "ENABLED" if term_info.trade_allowed else "DISABLED!"))
                else:
                    sec_results.append(check("AutoTrading enabled", False, "Cannot read terminal info"))

                # Check filling mode support
                import yaml
                with open("config/base.yaml", "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                active_symbols = [i["symbol"] for i in config.get("instruments", [])]
                filling_issues = []
                for sym in active_symbols:
                    sym_info = mt5.symbol_info(sym)
                    if sym_info is None:
                        filling_issues.append(f"{sym}: not found")
                    elif sym_info.filling_mode == 0:
                        filling_issues.append(f"{sym}: no filling mode")
                if filling_issues:
                    sec_results.append(check("Filling mode", False, "; ".join(filling_issues)))
                else:
                    sec_results.append(check("Filling mode", True, f"All {len(active_symbols)} symbols OK"))

                # Open positions
                positions = mt5.positions_get()
                pos_count = len(positions) if positions else 0
                sec_results.append(check("Open positions", True, f"{pos_count} positions"))

                mt5.shutdown()
            else:
                sec_results.append(check("MT5 login", False, str(mt5.last_error())))
                mt5.shutdown()
        else:
            sec_results.append(check("MT5 initialize", False, str(mt5.last_error())))
    except ImportError:
        sec_results.append(check("MetaTrader5 package", False, "Not installed"))
    except Exception as e:
        sec_results.append(check("MT5 connection", False, str(e)))
    sections[section] = sec_results
    results.extend(sec_results)

    # 3. Database
    section = "DATABASE"
    print(f"\n[3] {section}")
    sec_results = []
    try:
        import sqlite3
        db_path = "data/trading.db"
        sec_results.append(check("Database file exists", os.path.exists(db_path), db_path))
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            c = conn.cursor()

            tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            table_names = [t[0] for t in tables]
            sec_results.append(check("Tables found", len(tables) > 0, f"{len(tables)} tables"))

            total = c.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            closed = c.execute("SELECT COUNT(*) FROM trades WHERE is_closed=1").fetchone()[0]
            open_t = c.execute("SELECT COUNT(*) FROM trades WHERE is_closed=0").fetchone()[0]
            sec_results.append(check("Trades", True, f"{total} total ({closed} closed, {open_t} open)"))

            if closed > 0:
                wins = c.execute("SELECT COUNT(*) FROM trades WHERE is_closed=1 AND profit>0").fetchone()[0]
                pnl = c.execute("SELECT COALESCE(SUM(profit),0) FROM trades WHERE is_closed=1").fetchone()[0]
                sec_results.append(check("Performance", True, f"WR: {wins/closed*100:.1f}% | PnL: ${pnl:+,.2f}"))

            scans = c.execute("SELECT COUNT(*) FROM scan_logs").fetchone()[0]
            sec_results.append(check("Scan logs", True, f"{scans} scans"))

            conn.close()
    except Exception as e:
        sec_results.append(check("Database", False, str(e)))
    sections[section] = sec_results
    results.extend(sec_results)

    # 4. Config
    section = "CONFIG"
    print(f"\n[4] {section}")
    sec_results = []
    try:
        import yaml
        with open("config/base.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        instruments = config.get("instruments", [])
        symbols = [i["symbol"] for i in instruments]
        sec_results.append(check("Config loaded", True, f"{len(instruments)} instruments"))
        sec_results.append(check("Symbols", True, ", ".join(symbols)))

        risk = config.get("risk", {})
        sec_results.append(check("Risk/trade", True, f"{risk.get('max_risk_per_trade', '?')}"))
        sec_results.append(check("Max positions", True, f"{risk.get('max_open_positions', '?')}"))
    except Exception as e:
        sec_results.append(check("Config", False, str(e)))
    sections[section] = sec_results
    results.extend(sec_results)

    # 5. Strategies
    section = "STRATEGIES"
    print(f"\n[5] {section}")
    sec_results = []
    try:
        from strategies.rsi_reversal import RSIReversalStrategy
        sec_results.append(check("RSI Reversal", True, "OK"))
        from strategies.macd_crossover import MACDCrossoverStrategy
        sec_results.append(check("MACD Crossover", True, "OK"))
        from strategies.sma_crossover import SMACrossoverStrategy
        sec_results.append(check("SMA Crossover", True, "OK (disabled)"))
    except ImportError as e:
        sec_results.append(check("Strategy import", False, str(e)))
    sections[section] = sec_results
    results.extend(sec_results)

    # 6. Log file
    section = "LOGS"
    print(f"\n[6] {section}")
    sec_results = []
    log_path = "data/logs/paper_trading.log"
    sec_results.append(check("Log file exists", os.path.exists(log_path), log_path))
    if os.path.exists(log_path):
        size_mb = os.path.getsize(log_path) / (1024 * 1024)
        sec_results.append(check("Log size", True, f"{size_mb:.1f} MB"))
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            if lines:
                last_line = lines[-1].strip()
                sec_results.append(check("Last entry", True, last_line[:80]))
    sections[section] = sec_results
    results.extend(sec_results)

    # 7. Google Drive
    section = "GOOGLE DRIVE"
    print(f"\n[7] {section}")
    sec_results = []
    if gdrive:
        drive_exists = os.path.exists(gdrive)
        sec_results.append(check("Sync folder", drive_exists, gdrive))
        if drive_exists:
            sync_file = os.path.join(gdrive, "last_sync.txt")
            if os.path.exists(sync_file):
                with open(sync_file) as f:
                    sec_results.append(check("Last sync", True, f.read().strip()))
            else:
                sec_results.append(check("Last sync", False, "Never synced"))
    else:
        sec_results.append(check("Google Drive", False, "GDRIVE_SYNC_PATH not set"))
    sections[section] = sec_results
    results.extend(sec_results)

    # ── Summary ───────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    total = len(results)

    print()
    print("=" * 60)
    print(f"  RESULT: {passed}/{total} passed, {failed} failed")
    if failed == 0:
        print("  STATUS: ALL SYSTEMS GO!")
    else:
        print("  STATUS: ISSUES FOUND - check FAIL items above")
    print("=" * 60)
    print()

    # ── Send full report to Telegram ──────────────────────────────────────
    print("[TELEGRAM] Sending full health check report...")
    try:
        from observability.telegram_notifier import TelegramNotifier
        notifier = TelegramNotifier()
        if not notifier.enabled:
            print("  [SKIP] Telegram not configured")
            return

        # Build detailed HTML message
        status_emoji = "OK" if failed == 0 else "ISSUES"
        lines = [f"<b>===== Health Check: {status_emoji} =====</b>"]
        lines.append(f"<b>{passed}/{total} passed | {failed} failed</b>\n")

        for section_name, sec_results in sections.items():
            sec_fails = sum(1 for r in sec_results if not r["passed"])
            sec_icon = "OK" if sec_fails == 0 else "!!"
            lines.append(f"<b>[{sec_icon}] {section_name}</b>")
            for r in sec_results:
                icon = "+" if r["passed"] else "X"
                detail = f" - {r['detail']}" if r["detail"] else ""
                lines.append(f"  [{icon}] {r['name']}{detail}")
            lines.append("")

        # Add failed items summary at the end if any
        if failed > 0:
            lines.append("<b>--- FAILED ITEMS ---</b>")
            for r in results:
                if not r["passed"]:
                    lines.append(f"  [X] {r['name']}: {r['detail']}")

        message = "\n".join(lines)

        # Send in chunks if too long
        if len(message) <= 3900:
            success = notifier.send(message)
        else:
            parts = []
            current = ""
            for line in lines:
                if len(current) + len(line) + 1 > 3900:
                    parts.append(current)
                    current = line
                else:
                    current += "\n" + line if current else line
            if current:
                parts.append(current)
            success = all(notifier.send(part) for part in parts)

        if success:
            print("  [PASS] Full report sent to Telegram")
        else:
            print("  [FAIL] Telegram send failed")

    except Exception as e:
        print(f"  [FAIL] Telegram error: {e}")


if __name__ == "__main__":
    main()
