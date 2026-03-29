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
        self._last_trailing_phase = {}  # {ticket: phase} — only notify on phase change

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
        conf = f"{signal['ml_confidence']:.0%}" if signal.get("ml_confidence") else "—"
        strategy = signal.get("strategy", "?").replace("_", " ").title()
        version = signal.get("strategy_version", "")
        ver_text = f" v{version}" if version else ""

        # Calculate planned R:R
        rr_text = "—"
        try:
            price = signal["price"]
            sl = signal["stop_loss"]
            tp = signal["take_profit"]
            risk = abs(price - sl)
            reward = abs(tp - price)
            if risk > 0:
                rr_text = f"1:{reward/risk:.1f}"
        except (KeyError, ZeroDivisionError):
            pass

        msg = (
            f"🟢 <b>صفقة جديدة</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>{signal['symbol']}</b> | {signal['action']}\n"
            f"📋 الاستراتيجية: {strategy}{ver_text}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 سعر الدخول: <code>{signal['price']:.5f}</code>\n"
            f"🛑 وقف الخسارة: <code>{signal['stop_loss']:.5f}</code>\n"
            f"🎯 جني الأرباح: <code>{signal['take_profit']:.5f}</code>\n"
            f"📐 R:R المخطط: {rr_text}\n"
            f"🤖 ثقة ML: {conf}\n"
        )
        if ticket:
            msg += f"🎫 تذكرة: <code>#{ticket}</code>"
        self.send(msg)

    def signal_filtered(self, signal: dict, reason: str = ""):
        """Notify: signal was filtered by ML or risk."""
        conf = f"{signal['ml_confidence']:.0%}" if signal.get("ml_confidence") else "—"
        msg = (
            f"🔴 <b>إشارة مرفوضة</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>{signal['symbol']}</b> | {signal['action']}\n"
            f"🤖 ثقة ML: {conf}\n"
            f"❌ السبب: {reason}"
        )
        self.send(msg)

    def trade_closed(self, symbol: str, action: str, pnl: float, pnl_pips: float,
                     exit_reason: str, ticket: int = None, duration_minutes: int = None,
                     strategy: str = None, strategy_version: str = None,
                     rr_planned: float = None, rr_actual: float = None):
        """Notify: trade was closed."""
        if pnl > 0:
            icon = "🟢"
            result_text = "ربح ✅"
        elif pnl < 0:
            icon = "🔴"
            result_text = "خسارة ❌"
        else:
            icon = "⚪"
            result_text = "تعادل"

        # Duration
        dur_text = ""
        if duration_minutes is not None:
            hours = duration_minutes // 60
            mins = duration_minutes % 60
            dur_text = f"\n⏱ مدة الاحتفاظ: {hours}h {mins}m"

        # Strategy info
        strat_text = ""
        if strategy:
            ver = f" v{strategy_version}" if strategy_version else ""
            strat_text = f"\n📋 الاستراتيجية: {strategy.replace('_', ' ').title()}{ver}"

        # R:R
        rr_text = ""
        if rr_planned is not None or rr_actual is not None:
            planned = f"1:{rr_planned:.1f}" if rr_planned else "—"
            actual = f"1:{rr_actual:.1f}" if rr_actual else "—"
            rr_text = f"\n📐 R:R: مخطط {planned} | فعلي {actual}"

        msg = (
            f"{icon} <b>إغلاق صفقة — {result_text}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>{symbol}</b> | {action}\n"
            f"💵 الربح/الخسارة: <code>${pnl:+.2f}</code> ({pnl_pips:+.1f} نقطة)"
            f"{strat_text}{rr_text}{dur_text}\n"
            f"📝 سبب الخروج: {exit_reason}\n"
        )
        if ticket:
            msg += f"🎫 تذكرة: <code>#{ticket}</code>"
        self.send(msg)

    def bot_started(self, account: dict, symbols: list, ml_models: list):
        """Notify: bot started running."""
        ml_text = ", ".join(ml_models) if ml_models else "لا يوجد"
        msg = (
            f"🚀 <b>ForexAI — تم التشغيل</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 الحساب: <code>{account.get('login', 'N/A')}</code>\n"
            f"💰 الرصيد: <code>${account.get('balance', 0):,.2f}</code>\n"
            f"📊 الأزواج: {', '.join(symbols)}\n"
            f"🤖 نماذج ML: {ml_text}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏱ المسح: كل ساعة | المراقبة: كل 5 دقائق"
        )
        self.send(msg)

    def bot_stopped(self):
        """Notify: bot stopped."""
        self.send("🛑 <b>ForexAI — تم الإيقاف</b>")

    def scan_summary(self, scan_number: int, account: dict, open_positions: int,
                     executed: list = None, blocked_symbols: list = None):
        """Notify: scan cycle completed."""
        signals_text = "لا يوجد"
        if executed:
            lines = []
            for sig in executed:
                lines.append(
                    f"  ▸ {sig['action']} {sig['symbol']} | "
                    f"SL: {sig['stop_loss']} | TP: {sig['take_profit']}"
                )
            signals_text = "\n".join(lines)

        news_text = "لا يوجد"
        if blocked_symbols:
            news_text = ", ".join(blocked_symbols)

        balance = account.get("balance", 0)
        equity = account.get("equity", 0)
        profit = account.get("profit", 0)
        pnl_icon = "📈" if profit >= 0 else "📉"

        msg = (
            f"📡 <b>مسح #{scan_number}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 الرصيد: <code>${balance:,.2f}</code>\n"
            f"💎 الملكية: <code>${equity:,.2f}</code>\n"
            f"{pnl_icon} الأرباح: <code>${profit:+,.2f}</code>\n"
            f"📂 صفقات مفتوحة: {open_positions}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📰 حظر أخبار: {news_text}\n"
            f"⚡ إشارات منفذة:\n{signals_text}"
        )
        self.send(msg)

    def daily_summary(self, balance: float, equity: float, profit: float,
                      open_positions: int, trades_today: int):
        """Notify: daily summary."""
        pnl_icon = "📈" if profit >= 0 else "📉"
        msg = (
            f"📊 <b>التقرير اليومي</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 الرصيد: <code>${balance:,.2f}</code>\n"
            f"💎 الملكية: <code>${equity:,.2f}</code>\n"
            f"{pnl_icon} أرباح اليوم: <code>${profit:+,.2f}</code>\n"
            f"📂 صفقات مفتوحة: {open_positions}\n"
            f"🔄 صفقات اليوم: {trades_today}"
        )
        self.send(msg)

    def detailed_scan_report(self, scan_number: int, account: dict,
                             open_positions: int, scan_details: list,
                             executed: list = None, news_events: list = None):
        """Send detailed scan report with per-symbol analysis."""
        balance = account.get("balance", 0)
        equity = account.get("equity", 0)
        profit = account.get("profit", 0)
        pnl_icon = "📈" if profit >= 0 else "📉"

        lines = [
            f"📡 <b>تقرير المسح #{scan_number}</b>",
            f"━━━━━━━━━━━━━━━━━━",
            f"💰 {balance:,.2f}$ | 💎 {equity:,.2f}$",
            f"{pnl_icon} الأرباح: ${profit:+,.2f} | 📂 مفتوحة: {open_positions}",
            "",
        ]

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

            # Signal status
            if d.get("signal_generated"):
                status_icon = "⚡"
                action = d.get("signal_action", "?")
                status = d.get("signal_status", "?")
                status_text = f"{action} [{status}]"
            else:
                status_icon = "⏸"
                status_text = d.get("rejection_reason", "لا يوجد تقاطع")

            lines.append(f"{'─'*18}")
            lines.append(f"📊 <b>{sym}</b> — {price:.5f}")
            lines.append(f"  SMA: {gap:+.3f}% | Cross: {cross}")
            if d.get("cross_distance") is not None:
                lines.append(f"  مسافة التقاطع: {d['cross_distance']:.1f} نقطة")
            lines.append(f"  RSI: {rsi:.1f} | ATR: {atr:.5f}")
            lines.append(f"  اتجاه: H1={h1} | H4={h4}")
            if d.get("news_blocked"):
                lines.append(f"  ⚠️ حظر أخبار: {d.get('news_event', '')}")
            lines.append(f"  {status_icon} {status_text}")

        # Upcoming news
        if news_events:
            lines.append("")
            lines.append(f"{'─'*18}")
            lines.append("📰 <b>أخبار قادمة:</b>")
            for ev in news_events[:5]:
                impact = ev.get("impact", "?")
                name = ev.get("event_name", "?")
                currency = ev.get("currency", "?")
                ev_time = ev.get("time", "?")
                impact_icon = "🔴" if impact == "HIGH" else "🟡" if impact == "MEDIUM" else "⚪"
                lines.append(f"  {impact_icon} {currency}: {name} @ {ev_time}")

        # Executed trades
        if executed:
            lines.append("")
            lines.append(f"{'─'*18}")
            lines.append("⚡ <b>صفقات منفذة:</b>")
            for sig in executed:
                lines.append(
                    f"  ▸ {sig['action']} {sig['symbol']} | "
                    f"SL: {sig['stop_loss']} | TP: {sig['take_profit']}"
                )

        msg = "\n".join(lines)
        if len(msg) > 4000:
            msg = msg[:4000] + "\n... (مقتطع)"
        self.send(msg)

    def position_tp1(self, ticket, symbol, action, close_volume, close_price,
                     new_sl, new_tp, digits):
        """Notify: TP1 partial close."""
        msg = (
            f"🎯 <b>TP1 — إغلاق جزئي</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>{symbol}</b> | {action} | #{ticket}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📦 تم إغلاق 50% ({close_volume} لوت)\n"
            f"💰 سعر الإغلاق: <code>{close_price:.{digits}f}</code>\n"
            f"🛑 SL الجديد: <code>{new_sl:.{digits}f}</code> (منتصف الربح)\n"
            f"🎯 TP2: <code>{new_tp:.{digits}f}</code> (+1 ATR)"
        )
        self.send(msg)

    def position_breakeven(self, ticket, symbol, action, be_sl, atr_moved, digits):
        """Notify: breakeven triggered."""
        msg = (
            f"🔒 <b>نقطة التعادل</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>{symbol}</b> | {action} | #{ticket}\n"
            f"🛑 SL → <code>{be_sl:.{digits}f}</code>\n"
            f"📏 تحرك السعر: {atr_moved:.1f}x ATR لصالحك"
        )
        self.send(msg)

    def position_trailing(self, ticket, symbol, action, phase, old_sl, new_sl,
                          current_price, current_tp, digits):
        """Notify: trailing stop updated — only on phase change to reduce noise."""
        # Only send notification when phase changes for this ticket
        last_phase = self._last_trailing_phase.get(ticket)
        if last_phase == phase:
            return  # Same phase, skip notification
        self._last_trailing_phase[ticket] = phase

        icon = "📈" if action == "BUY" else "📉"
        msg = (
            f"{icon} <b>تريلنج ستوب</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>{symbol}</b> | {action} | #{ticket}\n"
            f"🔄 المرحلة: {phase}\n"
            f"🛑 SL: <code>{old_sl:.{digits}f}</code> → <code>{new_sl:.{digits}f}</code>\n"
            f"💹 السعر: <code>{current_price:.{digits}f}</code> | TP: <code>{current_tp:.{digits}f}</code>"
        )
        self.send(msg)
