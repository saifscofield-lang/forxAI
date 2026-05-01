"""
صفحة سجل الإشارات
كل محاولة إشارة — منفذة، مرشحة بـ ML، أو مرفوضة من المخاطر.
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import pandas as pd

st.title("🔍 سجل الإشارات")
st.caption("كل إشارة تم توليدها — بما في ذلك المرشحة بـ ML أو المرفوضة من إدارة المخاطر.")

# ── Filters ───────────────────────────────────────────────────────────────────
with st.expander("🔽 التصفية", expanded=True):
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        sym_filter = st.selectbox("الزوج", ["الكل", "EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])
    with col2:
        status_filter = st.selectbox(
            "الحالة",
            ["الكل", "EXECUTED", "ML_FILTERED", "RISK_REJECTED", "ERROR"],
        )
    with col3:
        action_filter = st.selectbox("الاتجاه", ["الكل", "BUY", "SELL"])
    with col4:
        days_filter = st.slider("أيام للخلف", 1, 90, 30)

# ── Load Data ─────────────────────────────────────────────────────────────────
from dashboard.utils.db import get_signal_log, get_signal_stats

df = get_signal_log(
    limit=2000,
    status=None if status_filter == "الكل" else status_filter,
    symbol=None if sym_filter == "الكل" else sym_filter,
    days=days_filter,
)

if not df.empty:
    if action_filter != "الكل":
        df = df[df["action"] == action_filter]

# ── Stats Bar ─────────────────────────────────────────────────────────────────
stats = get_signal_stats()

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("إجمالي الإشارات", stats["total"])
with col2:
    st.metric("منفذة", stats["executed"],
              delta=f"{stats['executed']/max(stats['total'],1)*100:.0f}%", delta_color="off")
with col3:
    st.metric("مرشحة ML", stats["ml_filtered"],
              delta=f"{stats['ml_filtered']/max(stats['total'],1)*100:.0f}%", delta_color="off")
with col4:
    st.metric("مرفوضة مخاطر", stats["risk_rejected"],
              delta=f"{stats['risk_rejected']/max(stats['total'],1)*100:.0f}%", delta_color="off")
with col5:
    from dashboard.utils.db import get_trade_results
    results = get_trade_results(limit=1000)
    if not results.empty and "profitable" in results.columns:
        prec = results["profitable"].mean() * 100
        st.metric("نسبة فوز الصفقات", f"{prec:.1f}%")
    else:
        st.metric("أخطاء", stats.get("error", 0))

st.divider()

# ── Charts ────────────────────────────────────────────────────────────────────
if not df.empty:
    from dashboard.components.charts import signal_status_bar, ml_confidence_histogram
    import plotly.express as px

    col_l, col_r = st.columns(2)

    with col_l:
        # Signal volume over time
        df_time = df.copy()
        df_time["date"] = pd.to_datetime(df_time["time"]).dt.date
        daily = df_time.groupby(["date", "status"]).size().reset_index(name="count")

        status_colors = {
            "EXECUTED": "#00C851",
            "ML_FILTERED": "#FF9800",
            "RISK_REJECTED": "#FF4444",
            "ERROR": "#666666",
        }

        fig = px.bar(
            daily, x="date", y="count", color="status",
            color_discrete_map=status_colors,
            title="حجم الإشارات اليومي حسب الحالة",
            labels={"count": "الإشارات", "date": "التاريخ"},
        )
        fig.update_layout(
            paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
            font=dict(color="#FAFAFA"),
            xaxis=dict(gridcolor="#1E2130"),
            yaxis=dict(gridcolor="#1E2130"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, width="stretch")

    with col_r:
        st.plotly_chart(ml_confidence_histogram(df), width="stretch")

# ── Signal Log Table ──────────────────────────────────────────────────────────
st.subheader(f"الإشارات ({len(df)})")

if df.empty:
    st.info("لا توجد إشارات للمرشحات المحددة.")
else:
    # Color-coded status
    status_colors = {
        "EXECUTED": "background-color: #00281A",
        "ML_FILTERED": "background-color: #1A1200",
        "RISK_REJECTED": "background-color: #1A0005",
        "ERROR": "background-color: #111111",
    }

    def style_status(val):
        return status_colors.get(val, "")

    fmt = {}
    if "price" in df.columns:
        fmt["price"] = "{:.5f}"
    if "ml_confidence" in df.columns:
        fmt["ml_confidence"] = lambda x: f"{x:.1%}" if pd.notna(x) else "—"
    if "ml_threshold" in df.columns:
        fmt["ml_threshold"] = lambda x: f"{x:.0%}" if pd.notna(x) else "—"
    if "atr" in df.columns:
        fmt["atr"] = lambda x: f"{x:.5f}" if pd.notna(x) else "—"
    if "rsi" in df.columns:
        fmt["rsi"] = lambda x: f"{x:.1f}" if pd.notna(x) else "—"

    display_cols = [c for c in [
        "time", "symbol", "action", "price", "status",
        "ml_confidence", "ml_threshold", "rsi", "atr",
        "strategy", "reason", "ticket",
    ] if c in df.columns]

    styled = df[display_cols].style.format(fmt)
    if "status" in display_cols:
        styled = styled.map(style_status, subset=["status"])

    st.dataframe(styled, width="stretch", hide_index=True)

    # Export
    csv = df[display_cols].to_csv(index=False)
    st.download_button(
        "⬇ تصدير CSV",
        data=csv,
        file_name=f"signal_log_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )

# ── ML Filter Impact Analysis ─────────────────────────────────────────────────
if not df.empty and "ml_confidence" in df.columns and df["ml_confidence"].notna().any():
    st.divider()
    st.subheader("تأثير فلتر ML حسب الزوج")

    sym_stats = []
    for symbol, g in df.groupby("symbol"):
        total = len(g)
        executed = (g["status"] == "EXECUTED").sum()
        filtered = (g["status"] == "ML_FILTERED").sum()
        avg_conf_exec = g[g["status"] == "EXECUTED"]["ml_confidence"].mean()
        avg_conf_filt = g[g["status"] == "ML_FILTERED"]["ml_confidence"].mean()
        sym_stats.append({
            "الزوج": symbol,
            "الإجمالي": total,
            "منفذة": executed,
            "مرشحة ML": filtered,
            "نسبة المرور": f"{executed/total*100:.0f}%" if total > 0 else "0%",
            "متوسط الثقة (مرور)": f"{avg_conf_exec:.1%}" if pd.notna(avg_conf_exec) else "—",
            "متوسط الثقة (حجب)": f"{avg_conf_filt:.1%}" if pd.notna(avg_conf_filt) else "—",
        })

    if sym_stats:
        st.dataframe(pd.DataFrame(sym_stats), width="stretch", hide_index=True)
