"""
صفحة التحليلات
تحليلات أداء متقدمة — منحنى رأس المال، التراجع، الربح الشهري، تحليل الأزواج.
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import pandas as pd
import numpy as np

st.title("📈 تحليلات الأداء")
st.caption("تحليل معمّق لمقاييس الأداء والرسوم البيانية.")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("إعدادات التحليلات")
    days = st.slider("فترة المراجعة (أيام)", 7, 365, 90)
    sym_filter = st.selectbox("الزوج", ["الكل", "EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])

# ── Load Data ─────────────────────────────────────────────────────────────────
from dashboard.utils.db import (
    get_equity_curve, get_trade_results, get_performance_summary,
    get_symbol_breakdown, get_monthly_pnl
)
from dashboard.components.charts import (
    equity_curve_chart, drawdown_chart, pnl_distribution_chart,
    monthly_pnl_chart, cumulative_pnl_by_symbol, win_loss_pie,
    symbol_performance_radar
)

eq_df = get_equity_curve(days=days)
symbol = None if sym_filter == "الكل" else sym_filter
results_df = get_trade_results(limit=5000, symbol=symbol)
summary = get_performance_summary()
sym_df = get_symbol_breakdown()
monthly_df = get_monthly_pnl()

# ── Top KPIs ──────────────────────────────────────────────────────────────────
col1, col2, col3, col4, col5, col6 = st.columns(6)
with col1:
    st.metric("إجمالي الصفقات", summary["total_trades"])
with col2:
    st.metric("نسبة الفوز", f"{summary['win_rate']:.1f}%")
with col3:
    pnl = summary["total_pnl"]
    st.metric("صافي الربح", f"${pnl:+,.2f}",
              delta_color="normal" if pnl >= 0 else "inverse")
with col4:
    pf = summary["profit_factor"]
    st.metric("عامل الربح", f"{pf:.3f}",
              delta="جيد" if pf >= 1.2 else ("مقبول" if pf >= 1.0 else "ضعيف"),
              delta_color="normal" if pf >= 1.0 else "inverse")
with col5:
    st.metric("نسبة شارب", f"{summary['sharpe']:.3f}",
              delta_color="normal" if summary["sharpe"] >= 0.5 else "inverse")
with col6:
    dd = summary["max_drawdown"]
    st.metric("أقصى تراجع", f"${dd:,.2f}",
              delta_color="inverse")

st.divider()

# ── Equity + Drawdown ─────────────────────────────────────────────────────────
st.subheader("منحنى رأس المال والتراجع")
tab_eq, tab_dd = st.tabs(["منحنى رأس المال", "التراجع"])

with tab_eq:
    show_balance = st.checkbox("إظهار خط الرصيد", value=True)
    st.plotly_chart(equity_curve_chart(eq_df, show_balance=show_balance),
                    width="stretch")

with tab_dd:
    st.plotly_chart(drawdown_chart(eq_df), width="stretch")

st.divider()

# ── Monthly P&L + Symbol Comparison ──────────────────────────────────────────
col_l, col_r = st.columns([3, 2])

with col_l:
    st.subheader("الربح/الخسارة الشهري")
    if not monthly_df.empty:
        st.plotly_chart(monthly_pnl_chart(monthly_df), width="stretch")
    else:
        st.info("لا توجد بيانات شهرية بعد.")

with col_r:
    st.subheader("ربح / خسارة")
    st.plotly_chart(win_loss_pie(results_df), width="stretch")

st.divider()

# ── P&L Distribution ─────────────────────────────────────────────────────────
col_l2, col_r2 = st.columns([3, 2])

with col_l2:
    st.subheader("الربح التراكمي حسب الزوج")
    if not results_df.empty:
        st.plotly_chart(cumulative_pnl_by_symbol(results_df), width="stretch")
    else:
        st.info("لا توجد نتائج صفقات بعد.")

with col_r2:
    st.subheader("توزيع الربح/الخسارة")
    st.plotly_chart(pnl_distribution_chart(results_df), width="stretch")

st.divider()

# ── Symbol Breakdown ──────────────────────────────────────────────────────────
st.subheader("تحليل أداء الأزواج")

if not sym_df.empty:
    col_table, col_radar = st.columns([2, 3])

    with col_table:
        def _color_pf(val):
            if val >= 1.2:
                return "color: #00C851; font-weight: bold"
            elif val >= 1.0:
                return "color: #FFCA28"
            return "color: #FF4444"

        def _color_pnl(val):
            return "color: #00C851" if val >= 0 else "color: #FF4444"

        st.dataframe(
            sym_df.style.format({
                "win_rate": "{:.1f}%",
                "total_pnl": "${:+,.2f}",
                "profit_factor": "{:.3f}",
                "avg_pnl": "${:+,.2f}",
            }).map(_color_pf, subset=["profit_factor"])
              .map(_color_pnl, subset=["total_pnl", "avg_pnl"]),
            width="stretch", hide_index=True,
        )

    with col_radar:
        st.plotly_chart(symbol_performance_radar(sym_df), width="stretch")
else:
    st.info("لا توجد بيانات أزواج بعد.")

st.divider()

# ── Advanced Stats ────────────────────────────────────────────────────────────
st.subheader("إحصائيات متقدمة")

if not results_df.empty and "pnl" in results_df.columns:
    pnl = results_df["pnl"]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("أفضل صفقة", f"${pnl.max():+,.2f}")
        st.metric("متوسط الربح", f"${summary['avg_win']:+,.2f}")
    with col2:
        st.metric("أسوأ صفقة", f"${pnl.min():+,.2f}")
        st.metric("متوسط الخسارة", f"${summary['avg_loss']:+,.2f}")
    with col3:
        if "profitable" in results_df.columns:
            profitable = results_df.sort_values("close_time")["profitable"].tolist()
            max_wins = max_losses = cur_wins = cur_losses = 0
            for p in profitable:
                if p:
                    cur_wins += 1; cur_losses = 0
                else:
                    cur_losses += 1; cur_wins = 0
                max_wins = max(max_wins, cur_wins)
                max_losses = max(max_losses, cur_losses)
            st.metric("أقصى سلسلة ربح", max_wins)
            st.metric("أقصى سلسلة خسارة", max_losses)
        else:
            st.metric("صفقات (رابحة)", f"{(pnl > 0).sum()}")
            st.metric("صفقات (خاسرة)", f"{(pnl <= 0).sum()}")
    with col4:
        wins = pnl[pnl > 0]
        losses = pnl[pnl <= 0]
        wr = len(wins) / len(pnl)
        avg_w = wins.mean() if not wins.empty else 0
        avg_l = abs(losses.mean()) if not losses.empty else 0
        expectancy = (wr * avg_w) - ((1 - wr) * avg_l)
        st.metric("التوقع/صفقة", f"${expectancy:+,.2f}")

        payoff = avg_w / avg_l if avg_l > 0 else 0
        st.metric("نسبة العائد", f"{payoff:.2f}")

    # ── Calmar & Sortino Ratios ────────────────────────────────────────────
    st.divider()
    st.subheader("نسب متقدمة")
    col_s1, col_s2, col_s3 = st.columns(3)

    # Sortino: use only negative daily returns for denominator
    daily_returns = results_df.groupby(pd.to_datetime(results_df["close_time"]).dt.date)["pnl"].sum()
    if len(daily_returns) > 1:
        downside = daily_returns[daily_returns < 0]
        downside_std = downside.std() if len(downside) > 1 else 0
        sortino = (daily_returns.mean() / downside_std * (252**0.5)) if downside_std > 0 else 0
    else:
        sortino = 0

    # Calmar: annualized return / max drawdown
    total_days = max((pd.to_datetime(results_df["close_time"]).max() - pd.to_datetime(results_df["close_time"]).min()).days, 1)
    annual_return = pnl.sum() / total_days * 365
    max_dd_abs = abs(summary["max_drawdown"]) if summary["max_drawdown"] != 0 else 1
    calmar = annual_return / max_dd_abs

    # Recovery factor
    recovery = pnl.sum() / max_dd_abs if max_dd_abs > 0 else 0

    with col_s1:
        st.metric("نسبة سورتينو", f"{sortino:.3f}",
                  delta="جيد" if sortino >= 1.0 else ("مقبول" if sortino >= 0.5 else "ضعيف"),
                  delta_color="normal" if sortino >= 0.5 else "inverse")
    with col_s2:
        st.metric("نسبة كالمار", f"{calmar:.3f}",
                  delta_color="normal" if calmar >= 1.0 else "inverse")
    with col_s3:
        st.metric("عامل الاسترداد", f"{recovery:.2f}",
                  delta_color="normal" if recovery >= 1.0 else "inverse")
else:
    st.info("لا توجد نتائج صفقات لحساب الإحصائيات. نفّذ صفقات من الماسح.")

# ── Trade Duration Analysis ───────────────────────────────────────────────────
if not results_df.empty and "open_time" in results_df.columns and "close_time" in results_df.columns:
    st.divider()
    st.subheader("تحليل مدة الصفقات")

    df_dur = results_df.copy()
    df_dur["open_time"] = pd.to_datetime(df_dur["open_time"])
    df_dur["close_time"] = pd.to_datetime(df_dur["close_time"])
    df_dur["duration_hours"] = (df_dur["close_time"] - df_dur["open_time"]).dt.total_seconds() / 3600

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("متوسط المدة", f"{df_dur['duration_hours'].mean():.1f} ساعة")
    with col2:
        st.metric("أقصر صفقة", f"{df_dur['duration_hours'].min():.1f} ساعة")
    with col3:
        st.metric("أطول صفقة", f"{df_dur['duration_hours'].max():.1f} ساعة")

    if "pnl" in df_dur.columns:
        import plotly.express as px
        fig = px.scatter(
            df_dur, x="duration_hours", y="pnl",
            color="symbol" if "symbol" in df_dur.columns else None,
            title="مدة الصفقة مقابل الربح/الخسارة",
            labels={"duration_hours": "المدة (ساعات)", "pnl": "الربح ($)"},
        )
        fig.update_layout(
            paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
            font=dict(color="#FAFAFA"),
            xaxis=dict(gridcolor="#1E2130"),
            yaxis=dict(gridcolor="#1E2130"),
        )
        fig.add_hline(y=0, line_dash="dash", line_color="#666")
        st.plotly_chart(fig, width="stretch")
