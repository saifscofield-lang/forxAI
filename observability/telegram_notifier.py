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
            # Add ForexAI tag to every message
            message = f"[ForexAI] {message}"
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

    def detailed_scan_report(self, scan_number: int, account: dict,
                             open_positions: int, scan_details: list,
                             executed: list = None, news_events: list = None):
        """Send detailed scan report with per-symbol analysis."""
        lines = [f"<b>SCAN #{scan_number} REPORT</b>"]
        lines.append(f"Balance: ${account.get('balance', 0):,.2f} | Equity: ${account.get('equity', 0):,.2f}")
        lines.append(f"P&L: ${account.get('profit', 0):+,.2f} | Open: {open_positions}")
        lines.append("")

        # Per-symbol details
        for d in scan_details:
            sym = d.get("symbol", "?")
            cross = d.get("crossover", "NONE")
            gap = d.get("sma_gap_pct", 0)
            rsi = d.get("rsi", 0)
            atr = d.get("atr", 0)
            h1 = d.get("h1_trend", "?")
            h4 = d.get("h4_trend", "?")
            price = d.get("price", 0)

            # Signal status emoji
            if d.get("signal_generated"):
                status_emoji = "SIGNAL"
                status_text = f"{d.get('signal_action', '?')} [{d.get('signal_status', '?')}]"
            else:
                status_emoji = "NO SIGNAL"
                status_text = d.get("rejection_reason", "No crossover")

            lines.append(f"<b>{sym}</b>")
            lines.append(f"  Price: {price:.5f}")
            lines.append(f"  SMA gap: {gap:+.3f}% | Cross: {cross}")
            if d.get("cross_distance") is not None:
                lines.append(f"  Dist to cross: {d['cross_distance']:.1f} pips")
            lines.append(f"  RSI: {rsi:.1f} | ATR: {atr:.5f}")
            lines.append(f"  Trend H1: {h1} | H4: {h4}")
            if d.get("news_blocked"):
                lines.append(f"  NEWS BLOCK: {d.get('news_event', '')}")
            lines.append(f"  >> {status_emoji}: {status_text}")
            lines.append("")

        # Upcoming news
        if news_events:
            lines.append("<b>UPCOMING NEWS:</b>")
            for ev in news_events[:5]:
                impact = ev.get("impact", "?")
                name = ev.get("event_name", "?")
                currency = ev.get("currency", "?")
                ev_time = ev.get("time", "?")
                lines.append(f"  [{impact}] {currency}: {name} @ {ev_time}")
            lines.append("")

        # Executed trades
        if executed:
            lines.append("<b>EXECUTED:</b>")
            for sig in executed:
                lines.append(
                    f"  {sig['action']} {sig['symbol']} | "
                    f"SL={sig['stop_loss']} TP={sig['take_profit']}"
                )

        msg = "\n".join(lines)
        # Telegram has 4096 char limit
        if len(msg) > 4000:
            msg = msg[:4000] + "\n... (truncated)"
        self.send(msg)
