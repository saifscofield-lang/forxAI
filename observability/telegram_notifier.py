"""
Telegram Notifier -- sends trade alerts via Telegram Bot API.
"""
import os
import urllib.request
import urllib.parse
import json
from loguru import logger


class TelegramNotifier:
    """Sends notifications to Telegram."""

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.token and self.chat_id)

        if not self.enabled:
            logger.warning("Telegram not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env)")

    def send(self, message: str) -> bool:
        """Send a text message to Telegram."""
        if not self.enabled:
            return False

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
            }).encode("utf-8")

            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                return result.get("ok", False)
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    # ── Convenience methods ────────────────────────────────────

    def signal_executed(self, signal: dict, ticket: int = None):
        """Notify: trade was executed."""
        conf = f" | ML: {signal['ml_confidence']:.0%}" if signal.get("ml_confidence") else ""
        msg = (
            f"<b>TRADE OPENED</b>\n"
            f"{signal['action']} {signal['symbol']}\n"
            f"Price: {signal['price']:.5f}\n"
            f"SL: {signal['stop_loss']:.5f}\n"
            f"TP: {signal['take_profit']:.5f}{conf}\n"
        )
        if ticket:
            msg += f"Ticket: #{ticket}"
        self.send(msg)

    def signal_filtered(self, signal: dict, reason: str = ""):
        """Notify: signal was filtered by ML or risk."""
        conf = f"{signal['ml_confidence']:.0%}" if signal.get("ml_confidence") else "N/A"
        msg = (
            f"<b>SIGNAL FILTERED</b>\n"
            f"{signal['action']} {signal['symbol']}\n"
            f"ML Confidence: {conf}\n"
            f"Reason: {reason}"
        )
        self.send(msg)

    def trade_closed(self, symbol: str, action: str, pnl: float, pnl_pips: float,
                     exit_reason: str, ticket: int = None):
        """Notify: trade was closed."""
        emoji = "PROFIT" if pnl > 0 else "LOSS"
        msg = (
            f"<b>TRADE CLOSED - {emoji}</b>\n"
            f"{action} {symbol}\n"
            f"PnL: ${pnl:+.2f} ({pnl_pips:+.1f} pips)\n"
            f"Exit: {exit_reason}"
        )
        if ticket:
            msg += f"\nTicket: #{ticket}"
        self.send(msg)

    def bot_started(self, account: dict, symbols: list, ml_models: list):
        """Notify: bot started running."""
        msg = (
            f"<b>ForexAI Bot STARTED</b>\n"
            f"Account: {account.get('login', 'N/A')}\n"
            f"Balance: ${account.get('balance', 0):,.2f}\n"
            f"Symbols: {', '.join(symbols)}\n"
            f"ML Models: {', '.join(ml_models) if ml_models else 'None'}"
        )
        self.send(msg)

    def bot_stopped(self):
        """Notify: bot stopped."""
        self.send("<b>ForexAI Bot STOPPED</b>")

    def scan_summary(self, scan_number: int, account: dict, open_positions: int,
                     executed: list = None, blocked_symbols: list = None):
        """Notify: scan cycle completed."""
        signals_text = "None"
        if executed:
            lines = []
            for sig in executed:
                lines.append(f"  {sig['action']} {sig['symbol']} | SL={sig['stop_loss']} TP={sig['take_profit']}")
            signals_text = "\n".join(lines)

        news_text = "None"
        if blocked_symbols:
            news_text = ", ".join(blocked_symbols)

        msg = (
            f"<b>SCAN #{scan_number}</b>\n"
            f"Balance: ${account.get('balance', 0):,.2f}\n"
            f"Equity: ${account.get('equity', 0):,.2f}\n"
            f"P&L: ${account.get('profit', 0):+,.2f}\n"
            f"Open Positions: {open_positions}\n"
            f"News Blocks: {news_text}\n"
            f"Signals: {signals_text}"
        )
        self.send(msg)

    def daily_summary(self, balance: float, equity: float, profit: float,
                      open_positions: int, trades_today: int):
        """Notify: daily summary."""
        msg = (
            f"<b>DAILY SUMMARY</b>\n"
            f"Balance: ${balance:,.2f}\n"
            f"Equity: ${equity:,.2f}\n"
            f"Day P&L: ${profit:+,.2f}\n"
            f"Open Positions: {open_positions}\n"
            f"Trades Today: {trades_today}"
        )
        self.send(msg)
