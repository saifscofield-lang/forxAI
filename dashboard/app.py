"""
ForexAI Dashboard — Main Entry Point
Run with: streamlit run dashboard/app.py
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
from datetime import datetime, timezone

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ForexAI — لوحة التحكم",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "ForexAI — Algorithmic Forex Trading Platform\nPhase 3: Live Dashboard",
    },
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Dark theme overrides */
    .block-container { padding-top: 1.5rem; padding-bottom: 1rem; }
    div[data-testid="metric-container"] {
        background: #1A1F2E;
        border: 1px solid #2D3748;
        border-radius: 8px;
        padding: 12px 16px;
    }
    div[data-testid="stSidebar"] { background: #0D1117; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { border-radius: 6px; padding: 6px 16px; }
    div[data-testid="stAlert"] { border-radius: 8px; }

    /* RTL for Arabic text */
    h1, h2, h3, h4, h5, h6,
    p, span, label, .stMarkdown,
    div[data-testid="stSidebar"],
    div[data-testid="stAlert"],
    div[data-testid="stCaption"],
    .stSelectbox label, .stSlider label, .stNumberInput label,
    .stMultiSelect label, .stCheckbox label {
        direction: rtl;
        text-align: right;
    }
    /* Keep charts, tables, and numbers LTR */
    .js-plotly-plot, .stDataFrame, table,
    div[data-testid="metric-container"] [data-testid="stMetricValue"],
    code, pre, .stCodeBlock {
        direction: ltr;
        text-align: left;
    }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📈 ForexAI")
    st.caption("منصة التداول الخوارزمي")
    st.divider()

    # MT5 status (cached 60s)
    @st.cache_data(ttl=60, show_spinner=False)
    def _get_mt5_status():
        from dashboard.utils.mt5_helper import get_connection_status
        return get_connection_status()

    status = _get_mt5_status()

    if status.get("connected"):
        acc = status.get("account", {})
        st.success("🟢 MT5 متصل")
        st.markdown(f"""
        | | |
        |---|---|
        | **الحساب** | {acc.get('login', 'N/A')} |
        | **الرصيد** | ${acc.get('balance', 0):,.2f} |
        | **الملكية** | ${acc.get('equity', 0):,.2f} |
        | **الربح المفتوح** | ${acc.get('profit', 0):+,.2f} |
        """)
    else:
        st.error("🔴 MT5 غير متصل")
        st.caption(status.get("error", "شغّل منصة MT5"))

    st.divider()

    # ── Market Status ────────────────────────────────────────────────────────
    now_utc = datetime.now(timezone.utc)
    weekday = now_utc.weekday()  # 0=Mon ... 6=Sun
    hour = now_utc.hour

    # Forex: open Sun 22:00 UTC → Fri 22:00 UTC
    if weekday == 4 and hour >= 22:        # Friday after 22:00
        market_open = False
    elif weekday == 5:                      # Saturday
        market_open = False
    elif weekday == 6 and hour < 22:        # Sunday before 22:00
        market_open = False
    else:
        market_open = True

    # Active sessions (approximate UTC ranges)
    sessions = []
    if market_open:
        if hour >= 22 or hour < 7:
            sessions.append("🇦🇺 Sydney")
        if 0 <= hour < 9:
            sessions.append("🇯🇵 Tokyo")
        if 8 <= hour < 17:
            sessions.append("🇬🇧 London")
        if 13 <= hour < 22:
            sessions.append("🇺🇸 New York")

    if market_open:
        st.success("🟢 السوق مفتوح")
        if sessions:
            st.caption("الجلسات النشطة: " + " · ".join(sessions))
    else:
        st.error("🔴 السوق مغلق")
        st.caption("يفتح الأحد 22:00 UTC")

    st.divider()

    # Mode indicator
    try:
        import yaml
        with open("config/base.yaml") as f:
            cfg = yaml.safe_load(f)
        mode = cfg.get("system", {}).get("mode", "paper").upper()
    except Exception:
        mode = "PAPER"

    mode_color = "🟡" if mode == "PAPER" else "🔴"
    mode_ar = "ورقي" if mode == "PAPER" else "حقيقي"
    st.markdown(f"**الوضع:** {mode_color} تداول {mode_ar}")

    st.divider()

    # ── News Alerts ──────────────────────────────────────────────────────────
    from dashboard.utils.db import get_upcoming_news
    upcoming = get_upcoming_news(hours_ahead=4)
    if not upcoming.empty:
        high_impact = upcoming[upcoming["impact"] == "HIGH"]
        if not high_impact.empty:
            st.warning(f"📰 {len(high_impact)} أخبار عالية التأثير قادمة")
            for _, row in high_impact.iterrows():
                t = row["time"].strftime("%H:%M") if hasattr(row["time"], "strftime") else str(row["time"])
                st.caption(f"⚠️ {t} — {row['currency']} — {row['event_name']}")
        else:
            med = upcoming[upcoming["impact"] == "MEDIUM"]
            if not med.empty:
                st.info(f"📰 {len(med)} أخبار متوسطة التأثير قادمة")
    else:
        st.success("📰 لا أخبار مؤثرة قريبة")

    st.divider()
    st.caption(f"Updated: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC")

    if st.button("🔄 تحديث البيانات", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Home Page Content ─────────────────────────────────────────────────────────
st.title("📈 ForexAI — لوحة التداول")
st.caption("المرحلة 3 | SMA Crossover + LightGBM ML | تداول ورقي")

st.divider()

# ── Overview KPIs ─────────────────────────────────────────────────────────────
from dashboard.utils.db import get_performance_summary, get_signal_stats, get_latest_snapshot, get_open_trades

col1, col2, col3, col4, col5, col6 = st.columns(6)

summary = get_performance_summary()
signals = get_signal_stats()
snap = get_latest_snapshot()
open_trades = get_open_trades()

with col1:
    st.metric("إجمالي الصفقات", summary["total_trades"])
with col2:
    wr = summary["win_rate"]
    st.metric("نسبة الفوز", f"{wr:.1f}%", delta_color="off")
with col3:
    pnl = summary["total_pnl"]
    st.metric("إجمالي الربح/الخسارة", f"${pnl:+,.2f}", delta_color="normal")
with col4:
    pf = summary["profit_factor"]
    color = "normal" if pf >= 1.0 else "inverse"
    st.metric("عامل الربح", f"{pf:.3f}", delta_color=color)
with col5:
    st.metric("الصفقات المفتوحة", len(open_trades))
with col6:
    dd = summary["max_drawdown"]
    st.metric("أقصى تراجع", f"${dd:,.2f}", delta_color="inverse")

st.divider()

# ── Main Dashboard Tabs ───────────────────────────────────────────────────────
col_left, col_right = st.columns([3, 2])

with col_left:
    # Equity Curve
    from dashboard.utils.db import get_equity_curve
    from dashboard.components.charts import equity_curve_chart, drawdown_chart

    st.subheader("منحنى رأس المال")
    days = st.slider("عدد الأيام", 7, 365, 30, key="home_days")
    eq_df = get_equity_curve(days=days)
    st.plotly_chart(equity_curve_chart(eq_df), use_container_width=True, key="home_equity")

    if not eq_df.empty:
        st.plotly_chart(drawdown_chart(eq_df), use_container_width=True, key="home_dd")

with col_right:
    # Signal Stats
    from dashboard.components.charts import signal_status_bar, win_loss_pie
    from dashboard.utils.db import get_trade_results

    st.subheader("نتائج الإشارات")
    st.plotly_chart(signal_status_bar(signals), use_container_width=True, key="home_signals")

    st.subheader("ربح / خسارة")
    results_df = get_trade_results(limit=1000)
    st.plotly_chart(win_loss_pie(results_df), use_container_width=True, key="home_winloss")

st.divider()

# ── Symbol Breakdown Table ────────────────────────────────────────────────────
from dashboard.utils.db import get_symbol_breakdown

st.subheader("الأداء حسب الزوج")
sym_df = get_symbol_breakdown()
if not sym_df.empty:
    # Style the table
    def _color_pf(val):
        if val >= 1.2:
            return "color: #00C851; font-weight: bold"
        elif val >= 1.0:
            return "color: #FFCA28"
        return "color: #FF4444"

    def _color_pnl(val):
        return "color: #00C851" if val >= 0 else "color: #FF4444"

    styled = sym_df.style.format({
        "win_rate": "{:.1f}%",
        "total_pnl": "${:+,.2f}",
        "profit_factor": "{:.3f}",
        "avg_pnl": "${:+,.2f}",
    }).map(_color_pf, subset=["profit_factor"]).map(_color_pnl, subset=["total_pnl", "avg_pnl"])

    st.dataframe(styled, use_container_width=True, hide_index=True)
else:
    st.info("لا توجد صفقات مغلقة بعد. شغّل الماسح ونفّذ الإشارات لتعبئة البيانات.")

st.divider()

# ── Recent Activity ───────────────────────────────────────────────────────────
st.subheader("آخر الإشارات")
from dashboard.utils.db import get_signal_log

recent_signals = get_signal_log(limit=10, days=7)
if not recent_signals.empty:
    display_cols = ["time", "symbol", "action", "price", "status", "ml_confidence", "reason"]
    cols_present = [c for c in display_cols if c in recent_signals.columns]
    st.dataframe(
        recent_signals[cols_present].style.format({
            "price": "{:.5f}",
            "ml_confidence": lambda x: f"{x:.1%}" if x == x else "—",
        }),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("لا توجد إشارات بعد. انتقل إلى **الماسح** لتشغيل أول مسح.")

# ── Navigation Help ───────────────────────────────────────────────────────────
st.divider()
st.markdown("""
### التنقل
| الصفحة | الوصف |
|------|-------------|
| 📡 **الماسح** | مسح الإشارات وتنفيذ الصفقات يدوياً |
| 📊 **الصفقات** | عرض وإغلاق الصفقات المفتوحة |
| 📋 **السجل** | سجل كامل للصفقات المغلقة |
| 🔍 **الإشارات** | جميع الإشارات مع تحليل فلتر ML |
| 📈 **التحليلات** | تحليلات أداء متقدمة ورسوم بيانية |
| 🤖 **الذكاء الاصطناعي** | أداء نموذج LightGBM والميزات |
| ⚡ **الاختبار** | تشغيل اختبارات بمعلمات مخصصة |
| 📰 **الأخبار** | التقويم الاقتصادي وفلتر الأخبار |
""")
