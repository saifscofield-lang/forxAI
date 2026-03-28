"""
صفحة التقارير اليومية
تصدير تقرير شامل لليوم وإرساله عبر Telegram.
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import pandas as pd
from datetime import datetime, date, timezone

st.title("التقارير اليومية")
st.caption("تقرير شامل لليوم: صفقات، إشارات، أخطاء، صفقات مفتوحة.")

# ── Date Selector ─────────────────────────────────────────────────────────────
report_date = st.date_input("اختر التاريخ", value=date.today())

# ── Load Data ─────────────────────────────────────────────────────────────────
from dashboard.utils.db import get_daily_report_data, get_signal_log, get_monitor_states

report = get_daily_report_data(report_date)

# ── Summary KPIs ──────────────────────────────────────────────────────────────
st.divider()
st.subheader("ملخص اليوم")

col1, col2, col3, col4, col5, col6 = st.columns(6)
with col1:
    st.metric("الرصيد", f"${report['balance']:,.2f}")
with col2:
    st.metric("الملكية", f"${report['equity']:,.2f}")
with col3:
    pnl = report["pnl"]
    st.metric("ربح اليوم", f"${pnl:+,.2f}",
              delta_color="normal" if pnl >= 0 else "inverse")
with col4:
    st.metric("الصفقات المغلقة", report["trades_closed"])
with col5:
    st.metric("نسبة الفوز", f"{report['win_rate']:.1f}%")
with col6:
    st.metric("المفتوحة", report["open_count"])

# ── Signals Summary ───────────────────────────────────────────────────────────
st.divider()
st.subheader("ملخص الإشارات")

cs1, cs2, cs3, cs4, cs5 = st.columns(5)
with cs1:
    st.metric("إجمالي الإشارات", report["signals_total"])
with cs2:
    st.metric("منفذة", report["signals_executed"])
with cs3:
    st.metric("مرفوضة مخاطر", report["signals_rejected"])
with cs4:
    st.metric("مرشحة ML", report["signals_ml_filtered"])
with cs5:
    st.metric("أخطاء تقنية", report["errors_count"])

# ── Closed Trades Table ───────────────────────────────────────────────────────
st.divider()
st.subheader("الصفقات المغلقة")

closed_trades = report["closed_trades_detail"]
if closed_trades:
    df_closed = pd.DataFrame(closed_trades)

    def _color_pnl(val):
        if isinstance(val, (int, float)):
            return "color: #00C851; font-weight: bold" if val >= 0 else "color: #FF4444; font-weight: bold"
        return ""

    fmt = {"profit": "${:+,.2f}"} if "profit" in df_closed.columns else {}
    styled = df_closed.style.format(fmt)
    if "profit" in df_closed.columns:
        styled = styled.map(_color_pnl, subset=["profit"])
    st.dataframe(styled, width="stretch", hide_index=True)
else:
    st.info("لا توجد صفقات مغلقة في هذا اليوم.")

# ── Open Positions ────────────────────────────────────────────────────────────
st.divider()
st.subheader("الصفقات المفتوحة")

open_positions = report["open_positions_detail"]
if open_positions:
    df_open = pd.DataFrame(open_positions)
    monitor_states = get_monitor_states()

    PHASE_LABELS = {
        0: "انتظار", 1: "بريك إيفن", 2: "TP1",
        3: "تتبع", 4: "تتبع ضيق",
    }

    if "ticket" in df_open.columns:
        df_open["المرحلة"] = df_open["ticket"].apply(
            lambda t: PHASE_LABELS.get(monitor_states.get(t, {}).get("phase", 0), "انتظار")
        )

    fmt = {}
    for col in ["profit", "open_price", "stop_loss", "take_profit"]:
        if col in df_open.columns:
            if col == "profit":
                fmt[col] = "${:+,.2f}"
            else:
                fmt[col] = "{:.5f}"

    st.dataframe(df_open.style.format(fmt), width="stretch", hide_index=True)
else:
    st.info("لا توجد صفقات مفتوحة.")

# ── Errors ────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("الأخطاء التقنية")

errors = report["error_details"]
if errors:
    df_errors = pd.DataFrame(errors)
    st.dataframe(df_errors, width="stretch", hide_index=True)
else:
    st.success("لا توجد أخطاء تقنية في هذا اليوم.")

# ── Export / Send ─────────────────────────────────────────────────────────────
st.divider()
st.subheader("تصدير وإرسال")

col_export, col_telegram = st.columns(2)

# ── Build report text ──
def build_report_text(report):
    """Build a formatted text report."""
    lines = [
        f"===== ForexAI Daily Report =====",
        f"Date: {report['date']}",
        f"",
        f"-- Account --",
        f"Balance: ${report['balance']:,.2f}",
        f"Equity:  ${report['equity']:,.2f}",
        f"Day PnL: ${report['pnl']:+,.2f}",
        f"",
        f"-- Trades --",
        f"Closed: {report['trades_closed']} ({report['wins']}W / {report['losses']}L)",
        f"Win Rate: {report['win_rate']:.1f}%",
        f"Open: {report['open_count']}",
        f"",
        f"-- Signals --",
        f"Total: {report['signals_total']}",
        f"Executed: {report['signals_executed']}",
        f"Risk Rejected: {report['signals_rejected']}",
        f"ML Filtered: {report['signals_ml_filtered']}",
        f"News Filtered: {report['signals_news_filtered']}",
        f"Errors: {report['errors_count']}",
    ]

    if report["closed_trades_detail"]:
        lines.append("")
        lines.append("-- Closed Trades --")
        for t in report["closed_trades_detail"]:
            lines.append(f"  {t['symbol']} {t['order_type']} | ${t['profit']:+,.2f} | {t['strategy']}")

    if report["open_positions_detail"]:
        lines.append("")
        lines.append("-- Open Positions --")
        for t in report["open_positions_detail"]:
            lines.append(f"  {t['symbol']} {t['order_type']} @ {t['open_price']} | ${t['profit']:+,.2f} | {t['strategy']}")

    if report["error_details"]:
        lines.append("")
        lines.append("-- Errors --")
        for e in report["error_details"]:
            lines.append(f"  {e['time']} | {e['symbol']} | {e['reason']}")

    return "\n".join(lines)


report_text = build_report_text(report)

with col_export:
    st.download_button(
        "تحميل التقرير (TXT)",
        data=report_text,
        file_name=f"report_{report['date']}.txt",
        mime="text/plain",
        use_container_width=True,
    )

with col_telegram:
    if st.button("إرسال عبر Telegram", type="primary", use_container_width=True):
        try:
            from dotenv import load_dotenv
            load_dotenv()
            from observability.telegram_notifier import TelegramNotifier

            notifier = TelegramNotifier()
            if not notifier.enabled:
                st.error("Telegram غير مُهيأ. تأكد من إعداد TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID في .env")
            else:
                # Build HTML message for Telegram
                html_msg = (
                    f"<b>===== Daily Report: {report['date']} =====</b>\n\n"
                    f"<b>Account:</b>\n"
                    f"  Balance: ${report['balance']:,.2f}\n"
                    f"  Equity: ${report['equity']:,.2f}\n"
                    f"  Day PnL: <b>${report['pnl']:+,.2f}</b>\n\n"
                    f"<b>Trades:</b>\n"
                    f"  Closed: {report['trades_closed']} ({report['wins']}W/{report['losses']}L) | WR: {report['win_rate']:.1f}%\n"
                    f"  Open: {report['open_count']}\n\n"
                    f"<b>Signals:</b> {report['signals_total']} total | {report['signals_executed']} exec | {report['errors_count']} errors"
                )

                # Add closed trades
                if report["closed_trades_detail"]:
                    html_msg += "\n\n<b>Closed Trades:</b>\n<pre>"
                    for t in report["closed_trades_detail"]:
                        html_msg += f"  {t['symbol']:8} {t['order_type']:4} ${t['profit']:>+8.2f} {t['strategy']}\n"
                    html_msg += "</pre>"

                # Add open positions
                if report["open_positions_detail"]:
                    html_msg += "\n<b>Open Positions:</b>\n<pre>"
                    for t in report["open_positions_detail"]:
                        html_msg += f"  {t['symbol']:8} {t['order_type']:4} ${t['profit']:>+8.2f}\n"
                    html_msg += "</pre>"

                # Send in chunks if needed (Telegram limit ~4000 chars)
                if len(html_msg) <= 3900:
                    success = notifier.send(html_msg)
                else:
                    # Split into parts
                    parts = [html_msg[i:i+3900] for i in range(0, len(html_msg), 3900)]
                    success = all(notifier.send(part) for part in parts)

                if success:
                    st.success("تم إرسال التقرير عبر Telegram بنجاح!")
                else:
                    st.error("فشل إرسال التقرير. تحقق من إعدادات Telegram.")
        except Exception as e:
            st.error(f"خطأ: {e}")
