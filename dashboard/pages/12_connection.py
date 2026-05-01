"""
صفحة الاتصال والمشاكل التقنية
متابعة حالة الاتصال بـ MT5 والأخطاء التقنية.
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timezone

st.title("الاتصال والمشاكل التقنية")
st.caption("متابعة حالة الاتصال بـ MT5 وتحليل الأخطاء التقنية.")

# ── MT5 Connection Status ─────────────────────────────────────────────────────
st.subheader("حالة الاتصال الحالية")

@st.cache_data(ttl=30, show_spinner=False)
def _check_mt5():
    from dashboard.utils.mt5_helper import get_connection_status
    return get_connection_status()

status = _check_mt5()

if status.get("connected"):
    acc = status.get("account", {})
    st.success("MT5 متصل")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("الحساب", acc.get("login", "N/A"))
    with col2:
        st.metric("السيرفر", acc.get("server", "N/A"))
    with col3:
        st.metric("الرصيد", f"${acc.get('balance', 0):,.2f}")
    with col4:
        st.metric("الملكية", f"${acc.get('equity', 0):,.2f}")
else:
    st.error("MT5 غير متصل")
    st.caption(f"السبب: {status.get('error', 'غير معروف')}")

st.divider()

# ── Error Analysis ────────────────────────────────────────────────────────────
st.subheader("تحليل الأخطاء التقنية")

from dashboard.utils.db import get_error_signals, get_connection_timeline

days = st.slider("الفترة (أيام)", 1, 30, 7, key="error_days")
errors_df = get_error_signals(days=days)

if not errors_df.empty:
    # ── Error Summary ─────────────────────────────────────────────────────
    error_summary = errors_df.groupby("error_type").agg(
        count=("error_type", "count"),
        last_seen=("time", "max"),
    ).reset_index().sort_values("count", ascending=False)

    # Error type colors
    ERROR_COLORS = {
        "Filling Mode": "#FF4444",
        "AutoTrading Disabled": "#FF9800",
        "No Money": "#FFCA28",
        "Market Closed": "#666666",
        "Connection Error": "#1E88E5",
        "Other Error": "#AB47BC",
    }

    st.markdown(f"**إجمالي الأخطاء:** {len(errors_df)} خطأ في آخر {days} أيام")

    # KPIs per error type
    cols = st.columns(min(len(error_summary), 6))
    for i, (_, row) in enumerate(error_summary.iterrows()):
        if i < len(cols):
            with cols[i]:
                st.metric(
                    row["error_type"],
                    row["count"],
                    help=f"آخر حدوث: {row['last_seen']}",
                )

    st.divider()

    # ── Error Timeline Chart ──────────────────────────────────────────────
    st.subheader("الأخطاء عبر الزمن")

    errors_df["time"] = pd.to_datetime(errors_df["time"])
    errors_df["date"] = errors_df["time"].dt.date

    # Daily error counts by type
    daily_errors = errors_df.groupby(["date", "error_type"]).size().reset_index(name="count")

    fig = go.Figure()
    for error_type in daily_errors["error_type"].unique():
        et_data = daily_errors[daily_errors["error_type"] == error_type]
        color = ERROR_COLORS.get(error_type, "#666")
        fig.add_trace(go.Bar(
            x=et_data["date"].astype(str),
            y=et_data["count"],
            name=error_type,
            marker_color=color,
        ))

    fig.update_layout(
        paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
        font=dict(color="#FAFAFA"),
        title="الأخطاء اليومية حسب النوع",
        barmode="stack",
        xaxis=dict(gridcolor="#1E2130", title="التاريخ"),
        yaxis=dict(gridcolor="#1E2130", title="العدد"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=400,
    )
    st.plotly_chart(fig, width="stretch")

    st.divider()

    # ── Error Detail Table ────────────────────────────────────────────────
    st.subheader("تفاصيل الأخطاء")

    error_type_filter = st.selectbox(
        "تصفية حسب النوع",
        ["الكل"] + error_summary["error_type"].tolist(),
    )

    filtered = errors_df if error_type_filter == "الكل" else errors_df[errors_df["error_type"] == error_type_filter]

    display_cols = ["time", "symbol", "action", "error_type", "strategy", "reason"]
    available_cols = [c for c in display_cols if c in filtered.columns]
    st.dataframe(
        filtered[available_cols].head(100),
        width="stretch",
        hide_index=True,
    )

    # ── Comparison: Today vs Average ──────────────────────────────────────
    st.divider()
    st.subheader("مقارنة: اليوم مقابل المتوسط")

    today = datetime.now(timezone.utc).date()
    today_errors = errors_df[errors_df["date"] == today]
    avg_daily = len(errors_df) / max(days, 1)

    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        st.metric("أخطاء اليوم", len(today_errors))
    with cc2:
        st.metric("المتوسط اليومي", f"{avg_daily:.1f}")
    with cc3:
        delta = len(today_errors) - avg_daily
        st.metric("الفرق", f"{delta:+.1f}",
                  delta_color="inverse" if delta > 0 else "normal")

else:
    st.success(f"لا توجد أخطاء تقنية في آخر {days} أيام!")

st.divider()

# ── Connection Timeline ───────────────────────────────────────────────────────
st.subheader("سجل الفحوصات (اتصال)")

timeline = get_connection_timeline(days=days)
if not timeline.empty:
    timeline["time"] = pd.to_datetime(timeline["time"])

    # Detect gaps (>2 hours = potential disconnection)
    timeline["gap_hours"] = timeline["time"].diff().dt.total_seconds() / 3600
    gaps = timeline[timeline["gap_hours"] > 2]

    if not gaps.empty:
        st.warning(f"تم اكتشاف {len(gaps)} فجوة اتصال (> 2 ساعة)")
        for _, gap in gaps.iterrows():
            st.caption(f"فجوة {gap['gap_hours']:.1f} ساعة عند {gap['time']}")
    else:
        st.success("لا توجد فجوات اتصال كبيرة")

    st.metric("إجمالي الفحوصات", len(timeline))
else:
    st.info("لا توجد بيانات فحوصات.")

if st.button("تحديث", use_container_width=True):
    st.cache_data.clear()
    st.rerun()
