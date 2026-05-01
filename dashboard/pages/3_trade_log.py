"""
صفحة سجل الصفقات
سجل كامل لجميع الصفقات المغلقة مع التصفية والتصدير.
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import pandas as pd

st.title("📋 سجل الصفقات")
st.caption("سجل كامل لجميع الصفقات المغلقة.")

# ── Filters ───────────────────────────────────────────────────────────────────
with st.expander("🔽 التصفية", expanded=True):
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        symbols = ["الكل", "EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
        sym_filter = st.selectbox("الزوج", symbols)
    with col2:
        action_filter = st.selectbox("الاتجاه", ["الكل", "BUY", "SELL"])
    with col3:
        strategy_filter = st.selectbox("الاستراتيجية", ["الكل", "sma_crossover", "ml_filtered"])
    with col4:
        result_filter = st.selectbox("النتيجة", ["الكل", "رابحة", "خاسرة"])

# ── Load Data ─────────────────────────────────────────────────────────────────
from dashboard.utils.db import get_trade_results, get_closed_trades

sym_val = None if sym_filter == "الكل" else sym_filter
results_df = get_trade_results(limit=2000, symbol=sym_val)

if results_df.empty:
    trades_df = get_closed_trades(limit=2000, symbol=sym_val)
    use_results = False
else:
    trades_df = results_df
    use_results = True

# Apply remaining filters
if not trades_df.empty:
    act_val = None if action_filter == "الكل" else action_filter
    if act_val and "action" in trades_df.columns:
        trades_df = trades_df[trades_df["action"] == act_val]
    elif act_val and "order_type" in trades_df.columns:
        trades_df = trades_df[trades_df["order_type"] == act_val]

    strat_val = None if strategy_filter == "الكل" else strategy_filter
    if strat_val and "strategy" in trades_df.columns:
        trades_df = trades_df[trades_df["strategy"].str.contains(strat_val, na=False, case=False)]

    if result_filter != "الكل" and "profitable" in trades_df.columns:
        trades_df = trades_df[trades_df["profitable"] == (result_filter == "رابحة")]
    elif result_filter != "الكل" and "profit" in trades_df.columns:
        if result_filter == "رابحة":
            trades_df = trades_df[trades_df["profit"] > 0]
        else:
            trades_df = trades_df[trades_df["profit"] <= 0]

# ── Summary KPIs ──────────────────────────────────────────────────────────────
if not trades_df.empty:
    pnl_col = "pnl" if "pnl" in trades_df.columns else "profit"
    total_pnl = trades_df[pnl_col].sum() if pnl_col in trades_df.columns else 0
    wins = (trades_df[pnl_col] > 0).sum() if pnl_col in trades_df.columns else 0
    win_rate = wins / len(trades_df) * 100

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("الصفقات المصفاة", len(trades_df))
    with col2:
        st.metric("نسبة الفوز", f"{win_rate:.1f}%")
    with col3:
        st.metric("إجمالي الربح/الخسارة", f"${total_pnl:+,.2f}",
                  delta_color="normal" if total_pnl >= 0 else "inverse")
    with col4:
        avg_pnl = trades_df[pnl_col].mean() if pnl_col in trades_df.columns else 0
        st.metric("متوسط الربح/الصفقة", f"${avg_pnl:+,.2f}")

st.divider()

# ── Charts ────────────────────────────────────────────────────────────────────
if not trades_df.empty and use_results:
    from dashboard.components.charts import cumulative_pnl_by_symbol, pnl_distribution_chart

    col_l, col_r = st.columns([3, 2])
    with col_l:
        st.plotly_chart(cumulative_pnl_by_symbol(trades_df), width="stretch")
    with col_r:
        st.plotly_chart(pnl_distribution_chart(trades_df), width="stretch")

# ── Table ─────────────────────────────────────────────────────────────────────
st.subheader(f"الصفقات ({len(trades_df)})")

if trades_df.empty:
    st.info("لا توجد صفقات. نفّذ إشارات من الماسح لبناء السجل.")
else:
    # Format columns
    fmt = {}
    for col in ["open_price", "close_price"]:
        if col in trades_df.columns:
            fmt[col] = "{:.5f}"
    for col in ["pnl", "profit"]:
        if col in trades_df.columns:
            fmt[col] = "${:+,.2f}"
    if "pnl_pips" in trades_df.columns:
        fmt["pnl_pips"] = "{:+.1f}"
    if "ml_confidence" in trades_df.columns:
        fmt["ml_confidence"] = lambda x: f"{x:.1%}" if pd.notna(x) else "—"

    def _color_pnl(val):
        if isinstance(val, (int, float)):
            return "color: #00C851; font-weight: bold" if val >= 0 else "color: #FF4444; font-weight: bold"
        return ""

    pnl_col = "pnl" if "pnl" in trades_df.columns else "profit"

    # Select display columns based on available data
    priority_cols = [
        "close_time", "open_time", "symbol", "action", "order_type",
        "open_price", "close_price", "pnl", "profit", "pnl_pips",
        "exit_reason", "ml_confidence", "strategy", "ticket",
    ]
    display_cols = [c for c in priority_cols if c in trades_df.columns]

    styled = trades_df[display_cols].style.format(fmt)
    if pnl_col in display_cols:
        styled = styled.map(_color_pnl, subset=[pnl_col])

    st.dataframe(styled, width="stretch", hide_index=True,
                 column_config={
                     "ticket": st.column_config.NumberColumn("التذكرة", format="%d"),
                 })

    # ── Export ────────────────────────────────────────────────────────────────
    col_dl1, col_dl2 = st.columns([2, 6])
    with col_dl1:
        csv = trades_df[display_cols].to_csv(index=False)
        st.download_button(
            "⬇ تصدير CSV",
            data=csv,
            file_name=f"trades_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

# ── Exit Reason Breakdown ─────────────────────────────────────────────────────
if not trades_df.empty and "exit_reason" in trades_df.columns:
    st.divider()
    st.subheader("تحليل أسباب الخروج")
    exit_counts = trades_df["exit_reason"].value_counts().reset_index()
    exit_counts.columns = ["سبب الخروج", "العدد"]

    col_left, col_right = st.columns([3, 3])
    with col_left:
        st.dataframe(exit_counts, width="stretch", hide_index=True)
    with col_right:
        if "pnl" in trades_df.columns:
            exit_pnl = trades_df.groupby("exit_reason")["pnl"].agg(["sum", "mean", "count"]).reset_index()
            exit_pnl.columns = ["سبب الخروج", "إجمالي الربح", "متوسط الربح", "العدد"]
            st.dataframe(
                exit_pnl.style.format({"إجمالي الربح": "${:+,.2f}", "متوسط الربح": "${:+,.2f}"}),
                width="stretch", hide_index=True,
            )
