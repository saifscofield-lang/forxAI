"""
Telegram Command Handler — interactive bot commands
IMP-NEW: /status, /positions, /performance, /pause, /resume
Runs in a background thread, polls for updates every 2 seconds.
"""
import os
import json
import time
import threading
import urllib.request
import urllib.parse
import sqlite3
from datetime import datetime, timezone, timedelta
from loguru import logger


class TelegramCommandHandler:
    """Polls Telegram for commands and responds."""

    def __init__(self, engine=None):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.token and self.chat_id)
        self.engine = engine
        self._last_update_id = 0
        self._running = False
        self._thread = None
        self._paused = False  # /pause state

    @property
    def is_paused(self):
        return self._paused

    def start(self):
        """Start polling in background thread."""
        if not self.enabled:
            logger.warning("Telegram commands disabled (no token/chat_id)")
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("Telegram command handler started")

    def stop(self):
        self._running = False

    def _poll_loop(self):
        """Poll for new messages every 2 seconds."""
        while self._running:
            try:
                self._check_updates()
            except Exception as e:
                logger.debug(f"Telegram poll error: {e}")
            time.sleep(2)

    def _check_updates(self):
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        params = urllib.parse.urlencode({
            "offset": self._last_update_id + 1,
            "timeout": 1,
            "allowed_updates": json.dumps(["message"]),
        }).encode("utf-8")
        req = urllib.request.Request(f"{url}?{params.decode()}", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        if not data.get("ok"):
            return

        for update in data.get("result", []):
            self._last_update_id = update["update_id"]
            msg = update.get("message", {})
            text = msg.get("text", "").strip()
            chat_id = str(msg.get("chat", {}).get("id", ""))

            # Only respond to our chat
            if chat_id != self.chat_id:
                continue

            if text.startswith("/"):
                self._handle_command(text)

    def _handle_command(self, text: str):
        cmd = text.split()[0].lower().split("@")[0]  # strip @botname
        handlers = {
            "/status": self._cmd_status,
            "/positions": self._cmd_positions,
            "/performance": self._cmd_performance,
            "/pause": self._cmd_pause,
            "/resume": self._cmd_resume,
            "/help": self._cmd_help,
        }
        handler = handlers.get(cmd)
        if handler:
            try:
                handler(text)
            except Exception as e:
                self._reply(f"خطأ: {e}")
        else:
            self._reply(
                "الأوامر المتاحة:\n"
                "/status — حالة الحساب\n"
                "/positions — الصفقات المفتوحة\n"
                "/performance — أداء اليوم/الأسبوع/الشهر\n"
                "/pause — إيقاف التداول مؤقتاً\n"
                "/resume — استئناف التداول\n"
                "/help — المساعدة"
            )

    def _reply(self, message: str):
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
            }).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            logger.debug(f"Telegram reply failed: {e}")

    # ── Commands ──────────────────────────────────────────

    def _cmd_status(self, text: str):
        if not self.engine or not self.engine.running:
            self._reply("البوت غير متصل")
            return

        account = self.engine.adapter.get_account_info()
        positions = self.engine.adapter.get_open_positions()
        open_count = 0 if positions is None or positions.empty else len(positions)
        profit = account.get("profit", 0)
        pnl_icon = "📈" if profit >= 0 else "📉"
        paused = "⏸ متوقف مؤقتاً" if self._paused else "▶️ يعمل"

        msg = (
            f"📊 <b>حالة النظام</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔄 الحالة: {paused}\n"
            f"💰 الرصيد: <code>${account.get('balance', 0):,.2f}</code>\n"
            f"💎 الملكية: <code>${account.get('equity', 0):,.2f}</code>\n"
            f"{pnl_icon} الأرباح: <code>${profit:+,.2f}</code>\n"
            f"📂 صفقات مفتوحة: {open_count}\n"
            f"🔧 المحرك: v{self.engine.config.get('system', {}).get('version', '?')}\n"
            f"📋 الاستراتيجيات: {len(self.engine.strategies)}"
        )
        self._reply(msg)

    def _cmd_positions(self, text: str):
        if not self.engine or not self.engine.running:
            self._reply("البوت غير متصل")
            return

        positions = self.engine.adapter.get_open_positions()
        if positions is None or positions.empty:
            self._reply("📂 لا توجد صفقات مفتوحة")
            return

        lines = [f"📂 <b>الصفقات المفتوحة ({len(positions)})</b>\n"]

        for _, pos in positions.iterrows():
            ticket = int(pos.get("ticket", 0))
            symbol = pos.get("symbol", "?")
            action = "BUY" if pos.get("type", 0) == 0 else "SELL"
            volume = pos.get("volume", 0)
            open_price = pos.get("price_open", 0)
            current = pos.get("price_current", 0)
            profit = pos.get("profit", 0)
            sl = pos.get("sl", 0)
            tp = pos.get("tp", 0)
            open_time = pos.get("time", None)

            # Duration
            duration_str = ""
            if open_time:
                try:
                    if isinstance(open_time, (int, float)):
                        dt = datetime.fromtimestamp(open_time, tz=timezone.utc)
                    else:
                        dt = open_time
                    delta = datetime.now(timezone.utc) - dt
                    hours = int(delta.total_seconds() // 3600)
                    mins = int((delta.total_seconds() % 3600) // 60)
                    duration_str = f"{hours}h {mins}m"
                except Exception:
                    duration_str = "?"

            # Digits
            digits = 3 if "JPY" in symbol else (2 if "XAU" in symbol else 5)
            pnl_icon = "🟢" if profit >= 0 else "🔴"

            # Monitor phase
            state = self.engine._position_states.get(ticket, {})
            phase = state.get("phase", 0)
            phase_names = {0: "انتظار", 1: "تعادل", 2: "إغلاق جزئي", 3: "تريلنج", 4: "تريلنج ضيق"}
            phase_text = phase_names.get(phase, f"P{phase}")

            lines.append(f"{'─' * 18}")
            lines.append(
                f"{pnl_icon} <b>{symbol}</b> {action} | #{ticket}\n"
                f"  📦 {volume} لوت | ⏱ {duration_str}\n"
                f"  💰 دخول: <code>{open_price:.{digits}f}</code> | حالي: <code>{current:.{digits}f}</code>\n"
                f"  🛑 SL: <code>{sl:.{digits}f}</code> | 🎯 TP: <code>{tp:.{digits}f}</code>\n"
                f"  💵 P&L: <code>${profit:+.2f}</code> | 🔄 {phase_text}"
            )

        msg = "\n".join(lines)
        if len(msg) > 4000:
            msg = msg[:4000] + "\n... (مقتطع)"
        self._reply(msg)

    def _cmd_performance(self, text: str):
        try:
            db_path = os.getenv("DATABASE_URL", "sqlite:///data/trading.db").replace("sqlite:///", "")
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            now = datetime.now(timezone.utc)

            periods = {
                "اليوم": now.strftime("%Y-%m-%d 00:00:00"),
                "الأسبوع": (now - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00"),
                "الشهر": (now - timedelta(days=30)).strftime("%Y-%m-%d 00:00:00"),
            }

            lines = ["📊 <b>تقرير الأداء</b>\n"]

            for period_name, since in periods.items():
                c.execute("""
                    SELECT COUNT(*), COALESCE(SUM(pnl), 0),
                           COALESCE(SUM(CASE WHEN profitable THEN 1 ELSE 0 END), 0),
                           COALESCE(MAX(pnl), 0), COALESCE(MIN(pnl), 0)
                    FROM trade_results WHERE close_time >= ?
                """, (since,))
                row = c.fetchone()
                trades, total_pnl, wins, best, worst = row
                wr = (wins / trades * 100) if trades > 0 else 0
                pnl_icon = "📈" if total_pnl >= 0 else "📉"

                lines.append(f"━━ <b>{period_name}</b> ━━")
                lines.append(f"  🔄 صفقات: {trades} | ✅ WR: {wr:.0f}%")
                lines.append(f"  {pnl_icon} إجمالي: <code>${total_pnl:+,.2f}</code>")
                lines.append(f"  🏆 أفضل: <code>${best:+.2f}</code> | 💀 أسوأ: <code>${worst:+.2f}</code>")
                lines.append("")

            # Per-strategy breakdown (this month)
            c.execute("""
                SELECT strategy, strategy_version, COUNT(*),
                       COALESCE(SUM(pnl), 0),
                       COALESCE(SUM(CASE WHEN profitable THEN 1 ELSE 0 END), 0)
                FROM trade_results WHERE close_time >= ?
                GROUP BY strategy, strategy_version ORDER BY SUM(pnl) DESC
            """, (periods["الشهر"],))
            strat_rows = c.fetchall()
            if strat_rows:
                lines.append("━━ <b>حسب الاستراتيجية (شهر)</b> ━━")
                for srow in strat_rows:
                    s_name, s_ver, s_trades, s_pnl, s_wins = srow
                    s_wr = (s_wins / s_trades * 100) if s_trades > 0 else 0
                    ver_text = f" v{s_ver}" if s_ver else ""
                    s_icon = "🟢" if s_pnl >= 0 else "🔴"
                    lines.append(
                        f"  {s_icon} {s_name}{ver_text}: "
                        f"{s_trades} صفقات | WR {s_wr:.0f}% | ${s_pnl:+,.2f}"
                    )

            conn.close()
            msg = "\n".join(lines)
            self._reply(msg)
        except Exception as e:
            self._reply(f"خطأ في تقرير الأداء: {e}")

    def _cmd_pause(self, text: str):
        self._paused = True
        self._reply("⏸ <b>تم إيقاف التداول مؤقتاً</b>\nلن يتم فتح صفقات جديدة.\nالمراقبة مستمرة للصفقات المفتوحة.\n\n/resume للاستئناف")

    def _cmd_resume(self, text: str):
        self._paused = False
        self._reply("▶️ <b>تم استئناف التداول</b>\nسيتم فحص الإشارات في الدورة القادمة.")

    def _cmd_help(self, text: str):
        msg = (
            "🤖 <b>أوامر ForexAI Bot</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "/status — حالة الحساب والنظام\n"
            "/positions — تفاصيل الصفقات المفتوحة مع P&L\n"
            "/performance — أداء اليوم/الأسبوع/الشهر\n"
            "/pause — إيقاف فتح صفقات جديدة\n"
            "/resume — استئناف التداول\n"
            "/help — هذه الرسالة"
        )
        self._reply(msg)


def generate_daily_report(engine) -> str:
    """Generate comprehensive daily report (called at 23:00 UTC)."""
    try:
        db_path = os.getenv("DATABASE_URL", "sqlite:///data/trading.db").replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d 00:00:00")

        c.execute("""
            SELECT COUNT(*), COALESCE(SUM(pnl), 0),
                   COALESCE(SUM(CASE WHEN profitable THEN 1 ELSE 0 END), 0),
                   COALESCE(MAX(pnl), 0), COALESCE(MIN(pnl), 0),
                   COALESCE(AVG(trade_duration_minutes), 0)
            FROM trade_results WHERE close_time >= ?
        """, (today,))
        row = c.fetchone()
        trades, total_pnl, wins, best, worst, avg_duration = row
        wr = (wins / trades * 100) if trades > 0 else 0
        losses = trades - wins

        # Per-strategy
        c.execute("""
            SELECT strategy, strategy_version, COUNT(*), COALESCE(SUM(pnl), 0),
                   COALESCE(SUM(CASE WHEN profitable THEN 1 ELSE 0 END), 0)
            FROM trade_results WHERE close_time >= ?
            GROUP BY strategy, strategy_version ORDER BY SUM(pnl) DESC
        """, (today,))
        strat_rows = c.fetchall()

        # Account
        account = engine.adapter.get_account_info() if engine and engine.running else {}
        balance = account.get("balance", 0)
        equity = account.get("equity", 0)

        # Open positions count
        positions = engine.adapter.get_open_positions() if engine and engine.running else None
        open_count = 0 if positions is None or (hasattr(positions, 'empty') and positions.empty) else len(positions)

        conn.close()

        pnl_icon = "📈" if total_pnl >= 0 else "📉"
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        lines = [
            f"📋 <b>التقرير اليومي — {date_str}</b>",
            f"━━━━━━━━━━━━━━━━━━",
            f"💰 الرصيد: <code>${balance:,.2f}</code> | 💎 الملكية: <code>${equity:,.2f}</code>",
            f"📂 صفقات مفتوحة: {open_count}",
            f"",
            f"━━ <b>نتائج اليوم</b> ━━",
            f"  🔄 صفقات: {trades} (✅ {wins} | ❌ {losses})",
            f"  📊 نسبة الربح: {wr:.0f}%",
            f"  {pnl_icon} إجمالي: <code>${total_pnl:+,.2f}</code>",
            f"  🏆 أفضل صفقة: <code>${best:+.2f}</code>",
            f"  💀 أسوأ صفقة: <code>${worst:+.2f}</code>",
            f"  ⏱ متوسط المدة: {int(avg_duration)} دقيقة",
        ]

        if strat_rows:
            lines.append("")
            lines.append("━━ <b>حسب الاستراتيجية</b> ━━")
            for s_name, s_ver, s_trades, s_pnl, s_wins in strat_rows:
                s_wr = (s_wins / s_trades * 100) if s_trades > 0 else 0
                ver = f" v{s_ver}" if s_ver else ""
                icon = "🟢" if s_pnl >= 0 else "🔴"
                lines.append(f"  {icon} {s_name}{ver}: {s_trades} صفقات | WR {s_wr:.0f}% | ${s_pnl:+,.2f}")

        return "\n".join(lines)
    except Exception as e:
        return f"خطأ في التقرير اليومي: {e}"


def generate_weekly_report(engine) -> str:
    """Generate weekly strategy comparison report (called Sunday 23:00)."""
    try:
        db_path = os.getenv("DATABASE_URL", "sqlite:///data/trading.db").replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00")

        c.execute("""
            SELECT COUNT(*), COALESCE(SUM(pnl), 0),
                   COALESCE(SUM(CASE WHEN profitable THEN 1 ELSE 0 END), 0)
            FROM trade_results WHERE close_time >= ?
        """, (week_ago,))
        total_trades, total_pnl, total_wins = c.fetchone()
        total_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0

        # Per strategy + version
        c.execute("""
            SELECT strategy, strategy_version, COUNT(*), COALESCE(SUM(pnl), 0),
                   COALESCE(SUM(CASE WHEN profitable THEN 1 ELSE 0 END), 0),
                   COALESCE(AVG(pnl), 0),
                   COALESCE(AVG(risk_reward_actual), 0)
            FROM trade_results WHERE close_time >= ?
            GROUP BY strategy, strategy_version ORDER BY SUM(pnl) DESC
        """, (week_ago,))
        strat_rows = c.fetchall()

        # Per symbol
        c.execute("""
            SELECT symbol, COUNT(*), COALESCE(SUM(pnl), 0),
                   COALESCE(SUM(CASE WHEN profitable THEN 1 ELSE 0 END), 0)
            FROM trade_results WHERE close_time >= ?
            GROUP BY symbol ORDER BY SUM(pnl) DESC
        """, (week_ago,))
        sym_rows = c.fetchall()

        conn.close()

        pnl_icon = "📈" if total_pnl >= 0 else "📉"
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        lines = [
            f"📊 <b>التقرير الأسبوعي — {date_str}</b>",
            f"━━━━━━━━━━━━━━━━━━",
            f"  🔄 إجمالي الصفقات: {total_trades}",
            f"  📊 WR: {total_wr:.0f}%",
            f"  {pnl_icon} إجمالي P&L: <code>${total_pnl:+,.2f}</code>",
            "",
        ]

        if strat_rows:
            lines.append("━━ <b>مقارنة الاستراتيجيات</b> ━━")
            for s_name, s_ver, s_trades, s_pnl, s_wins, s_avg, s_rr in strat_rows:
                s_wr = (s_wins / s_trades * 100) if s_trades > 0 else 0
                ver = f" v{s_ver}" if s_ver else ""
                icon = "🟢" if s_pnl >= 0 else "🔴"
                lines.append(
                    f"  {icon} <b>{s_name}{ver}</b>\n"
                    f"    {s_trades} صفقات | WR {s_wr:.0f}% | ${s_pnl:+,.2f}\n"
                    f"    متوسط: ${s_avg:+.2f} | R:R فعلي: {s_rr:.2f}"
                )
            lines.append("")

        if sym_rows:
            lines.append("━━ <b>حسب الزوج</b> ━━")
            for sym, s_trades, s_pnl, s_wins in sym_rows:
                s_wr = (s_wins / s_trades * 100) if s_trades > 0 else 0
                icon = "🟢" if s_pnl >= 0 else "🔴"
                lines.append(f"  {icon} {sym}: {s_trades} صفقات | WR {s_wr:.0f}% | ${s_pnl:+,.2f}")

        return "\n".join(lines)
    except Exception as e:
        return f"خطأ في التقرير الأسبوعي: {e}"


def check_loss_alert(engine, threshold: float = -500.0):
    """Alert if daily realized loss exceeds threshold."""
    try:
        db_path = os.getenv("DATABASE_URL", "sqlite:///data/trading.db").replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d 00:00:00")
        c.execute("SELECT COALESCE(SUM(pnl), 0) FROM trade_results WHERE close_time >= ?", (today,))
        daily_pnl = c.fetchone()[0]
        conn.close()

        if daily_pnl <= threshold:
            engine.notifier.send(
                f"🚨 <b>تنبيه خسارة!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💀 خسارة اليوم: <code>${daily_pnl:+,.2f}</code>\n"
                f"⚠️ تجاوز الحد: ${threshold:,.2f}\n"
                f"💡 استخدم /pause لإيقاف التداول مؤقتاً"
            )
    except Exception:
        pass
