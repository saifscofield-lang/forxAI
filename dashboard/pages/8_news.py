"""
📰 الأخبار — التقويم الاقتصادي وفلتر الأخبار
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import pandas as pd
from datetime import datetime, timezone

st.title("📰 الأخبار والتقويم الاقتصادي")
st.caption("فلتر الأخبار عالية التأثير | تقويم MT5 الاقتصادي")

st.divider()

from dashboard.utils.db import get_upcoming_news, get_recent_news, get_news_stats, get_scan_logs

# ── Impact colors ─────────────────────────────────────────────────────────────
IMPACT_COLORS = {
    "HIGH": "🔴",
    "MEDIUM": "🟡",
    "LOW": "🟢",
}

# ── News Stats KPIs ──────────────────────────────────────────────────────────
stats = get_news_stats(days=30)
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("إجمالي الأحداث (30 يوم)", stats["total"])
with col2:
    st.metric("🔴 عالية التأثير", stats["high"])
with col3:
    st.metric("🟡 متوسطة", stats["medium"])
with col4:
    st.metric("🟢 منخفضة", stats["low"])

st.divider()

# ── Upcoming News ─────────────────────────────────────────────────────────────
st.subheader("الأحداث القادمة (24 ساعة)")

hours = st.slider("ساعات للأمام", 1, 72, 24, key="news_hours")
upcoming = get_upcoming_news(hours_ahead=hours)

if not upcoming.empty:
    # Add impact emoji
    upcoming["التأثير"] = upcoming["impact"].map(IMPACT_COLORS)
    upcoming["الوقت"] = pd.to_datetime(upcoming["time"]).dt.strftime("%Y-%m-%d %H:%M")

    # Highlight HIGH impact
    display_df = upcoming[["الوقت", "currency", "event_name", "التأثير", "forecast", "previous"]].copy()
    display_df.columns = ["الوقت", "العملة", "الحدث", "التأثير", "المتوقع", "السابق"]

    # Show HIGH impact as warnings
    high_events = upcoming[upcoming["impact"] == "HIGH"]
    if not high_events.empty:
        st.warning(f"⚠️ {len(high_events)} أحداث عالية التأثير قادمة — التداول سيُحظر 30 دقيقة قبل/بعد كل حدث")
        for _, row in high_events.iterrows():
            t = pd.to_datetime(row["time"]).strftime("%H:%M")
            forecast_str = f" | المتوقع: {row['forecast']}" if pd.notna(row['forecast']) else ""
            st.error(f"🔴 {t} UTC — **{row['currency']}** — {row['event_name']}{forecast_str}")

    st.dataframe(display_df, width="stretch", hide_index=True)
else:
    st.success("لا توجد أحداث اقتصادية في الفترة المحددة")

st.divider()

# ── Recent News ───────────────────────────────────────────────────────────────
st.subheader("الأحداث السابقة (24 ساعة)")

recent = get_recent_news(hours_behind=24)
if not recent.empty:
    recent["التأثير"] = recent["impact"].map(IMPACT_COLORS)
    recent["الوقت"] = pd.to_datetime(recent["time"]).dt.strftime("%Y-%m-%d %H:%M")
    recent["المفاجأة"] = recent["surprise"].apply(
        lambda x: f"{x:+.2f}" if pd.notna(x) else "—"
    )

    display_df = recent[["الوقت", "currency", "event_name", "التأثير", "actual", "forecast", "المفاجأة"]].copy()
    display_df.columns = ["الوقت", "العملة", "الحدث", "التأثير", "الفعلي", "المتوقع", "المفاجأة"]

    st.dataframe(display_df, width="stretch", hide_index=True)
else:
    st.info("لا توجد أحداث سابقة في آخر 24 ساعة")

st.divider()

# ── News Filter Activity ─────────────────────────────────────────────────────
st.subheader("نشاط فلتر الأخبار")

scans = get_scan_logs(limit=100, days=7)
if not scans.empty:
    news_blocked_scans = scans[scans["news_blocked"] == True]
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("إجمالي الفحوصات (7 أيام)", len(scans))
    with col2:
        st.metric("فحوصات محجوبة بالأخبار", len(news_blocked_scans))
    with col3:
        total_news_filtered = scans["signals_news_filtered"].sum()
        st.metric("إشارات محجوبة بالأخبار", int(total_news_filtered))

    if not news_blocked_scans.empty:
        st.markdown("**آخر الفحوصات المحجوبة:**")
        blocked_display = news_blocked_scans[["time", "scan_number", "news_event_name", "signals_news_filtered"]].head(10)
        blocked_display.columns = ["الوقت", "رقم الفحص", "سبب الحجب", "إشارات محجوبة"]
        st.dataframe(blocked_display, width="stretch", hide_index=True)
else:
    st.info("لا توجد بيانات فحص بعد. شغّل البوت لبدء جمع البيانات.")

st.divider()

# ── Trades Affected by News ──────────────────────────────────────────────────
st.subheader("الصفقات المتأثرة بالأخبار")
st.caption("صفقات تم فتحها خلال ساعة من حدث إخباري عالي التأثير.")

from dashboard.utils.db import get_trades_near_news, get_trade_results

news_trades = get_trades_near_news(hours_window=1)
if not news_trades.empty:
    col_n1, col_n2, col_n3 = st.columns(3)
    with col_n1:
        st.metric("صفقات قرب الأخبار", len(news_trades))
    with col_n2:
        news_wr = (news_trades["profitable"] == True).mean() * 100 if len(news_trades) > 0 else 0
        st.metric("نسبة فوز (قرب أخبار)", f"{news_wr:.1f}%")
    with col_n3:
        all_results = get_trade_results(limit=5000)
        if not all_results.empty and "profitable" in all_results.columns:
            normal_wr = all_results["profitable"].mean() * 100
            delta = news_wr - normal_wr
            st.metric("مقارنة بالعادي", f"{normal_wr:.1f}%",
                      delta=f"{delta:+.1f}%", delta_color="normal" if delta >= 0 else "inverse")

    display_cols = ["ticket", "symbol", "action", "pnl", "strategy", "news_event_name", "news_impact"]
    available_cols = [c for c in display_cols if c in news_trades.columns]
    fmt = {}
    if "pnl" in available_cols:
        fmt["pnl"] = "${:+,.2f}"

    def _color_news_pnl(val):
        if isinstance(val, (int, float)):
            return "color: #00C851" if val >= 0 else "color: #FF4444"
        return ""

    styled = news_trades[available_cols].head(50).style.format(fmt)
    if "pnl" in available_cols:
        styled = styled.map(_color_news_pnl, subset=["pnl"])
    st.dataframe(styled, width="stretch", hide_index=True)
else:
    st.info("لا توجد صفقات مسجلة بالقرب من أحداث إخبارية.")

st.divider()

# ── Filter Settings Info ──────────────────────────────────────────────────────
st.subheader("إعدادات الفلتر")
st.markdown("""
| الإعداد | القيمة |
|---------|--------|
| **مدة الحجب قبل الحدث** | 30 دقيقة |
| **مدة الحجب بعد الحدث** | 30 دقيقة |
| **الحد الأدنى للتأثير** | HIGH (عالي فقط) |
| **المصدر** | تقويم MT5 الاقتصادي المدمج |
| **العملات المراقبة** | USD, EUR, GBP, JPY |
""")
