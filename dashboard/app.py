"""
ForexAI Dashboard — Main Entry Point
Run with: streamlit run dashboard/app.py
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import pandas as pd
from datetime import datetime, timezone

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ForexAI Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "ForexAI — Algorithmic Forex Trading Platform v3.1",
    },
)

# ── Professional CSS ─────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Clean dark theme */
    .block-container { padding-top: 1rem; padding-bottom: 0.5rem; max-width: 1400px; }

    /* Metric cards */
    div[data-testid="metric-container"] {
        background: linear-gradient(135deg, #1A1F2E 0%, #151A28 100%);
        border: 1px solid #2D3748;
        border-radius: 10px;
        padding: 14px 18px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }

    /* Sidebar */
    div[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0D1117 0%, #0A0E14 100%);
    }
    div[data-testid="stSidebar"] [data-testid="stMarkdown"] h2 {
        font-size: 1.3rem;
        letter-spacing: 0.5px;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 8px 20px;
        font-weight: 500;
    }

    /* Alerts */
    div[data-testid="stAlert"] { border-radius: 8px; }

    /* Dividers */
    hr { border-color: #1E2130 !important; margin: 0.8rem 0 !important; }

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

    /* Keep charts, tables, numbers LTR */
    .js-plotly-plot, .stDataFrame, table,
    div[data-testid="metric-container"] [data-testid="stMetricValue"],
    code, pre, .stCodeBlock {
        direction: ltr;
        text-align: left;
    }

    /* Navigation cards in sidebar */
    .nav-link {
        display: block;
        padding: 6px 12px;
        margin: 2px 0;
        border-radius: 6px;
        color: #AAA;
        text-decoration: none;
        font-size: 14px;
        transition: all 0.2s;
    }
    .nav-link:hover { background: #1A1F2E; color: #FFF; }

    /* Expander styling */
    .streamlit-expanderHeader { font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="text-align:center;padding:10px 0 5px 0">
        <div style="font-size:28px;font-weight:800;letter-spacing:1px;color:#1E88E5">ForexAI</div>
        <div style="font-size:12px;color:#666;margin-top:2px">Algorithmic Trading Platform</div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # MT5 status (cached 60s)
    @st.cache_data(ttl=60, show_spinner=False)
    def _get_mt5_status():
        from dashboard.utils.mt5_helper import get_connection_status
        return get_connection_status()

    status = _get_mt5_status()

    if status.get("connected"):
        acc = status.get("account", {})
        st.markdown(f"""
        <div style="background:#0D2818;border:1px solid #1B5E20;border-radius:8px;padding:10px 14px;margin-bottom:8px">
            <div style="color:#4CAF50;font-weight:600;font-size:13px">MT5 متصل</div>
            <div style="color:#888;font-size:12px;margin-top:4px">
                {acc.get('login', 'N/A')} | ${acc.get('balance', 0):,.0f}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="background:#2D1111;border:1px solid #B71C1C;border-radius:8px;padding:10px 14px;margin-bottom:8px">
            <div style="color:#EF5350;font-weight:600;font-size:13px">MT5 غير متصل</div>
            <div style="color:#888;font-size:12px;margin-top:4px">{status.get("error", "شغّل MT5")[:50]}</div>
        </div>
        """, unsafe_allow_html=True)

    # ── Market Status ─────────────────────────────────────────────────────
    now_utc = datetime.now(timezone.utc)
    weekday = now_utc.weekday()
    hour = now_utc.hour

    if weekday == 4 and hour >= 22:
        market_open = False
    elif weekday == 5:
        market_open = False
    elif weekday == 6 and hour < 22:
        market_open = False
    else:
        market_open = True

    sessions = []
    if market_open:
        if hour >= 22 or hour < 7:
            sessions.append("Sydney")
        if 0 <= hour < 9:
            sessions.append("Tokyo")
        if 8 <= hour < 17:
            sessions.append("London")
        if 13 <= hour < 22:
            sessions.append("New York")

    market_color = "#4CAF50" if market_open else "#EF5350"
    market_text = "مفتوح" if market_open else "مغلق"
    sessions_text = " | ".join(sessions) if sessions else "---"

    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;font-size:13px">
        <span style="color:#888">السوق</span>
        <span style="color:{market_color};font-weight:600">{market_text}</span>
    </div>
    """, unsafe_allow_html=True)

    if market_open and sessions:
        st.caption(f"الجلسات: {sessions_text}")

    # Mode indicator
    try:
        import yaml
        with open("config/base.yaml") as f:
            cfg = yaml.safe_load(f)
        mode = cfg.get("system", {}).get("mode", "paper").upper()
    except Exception:
        mode = "PAPER"

    mode_color = "#FFCA28" if mode == "PAPER" else "#EF5350"
    mode_ar = "ورقي" if mode == "PAPER" else "حقيقي"

    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;font-size:13px">
        <span style="color:#888">الوضع</span>
        <span style="color:{mode_color};font-weight:600">{mode_ar}</span>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ── News Alerts ───────────────────────────────────────────────────────
    from dashboard.utils.db import get_upcoming_news
    upcoming = get_upcoming_news(hours_ahead=4)
    if not upcoming.empty:
        high_impact = upcoming[upcoming["impact"] == "HIGH"]
        if not high_impact.empty:
            st.warning(f"{len(high_impact)} أخبار عالية التأثير قادمة")
            for _, row in high_impact.iterrows():
                t = row["time"].strftime("%H:%M") if hasattr(row["time"], "strftime") else str(row["time"])
                st.caption(f"  {t} -- {row['currency']} -- {row['event_name']}")
        else:
            med = upcoming[upcoming["impact"] == "MEDIUM"]
            if not med.empty:
                st.info(f"{len(med)} أخبار متوسطة التأثير")
    else:
        st.markdown('<div style="color:#4CAF50;font-size:13px;padding:4px 0">لا أخبار مؤثرة قريبة</div>', unsafe_allow_html=True)

    st.divider()

    # ── v3 / v4 status pill (auto-refreshes from DB) ─────────────────────
    @st.cache_data(ttl=60, show_spinner=False)
    def _get_version_status():
        import sqlite3
        v3_label = "STABLE"
        v4_label = "not started"
        v4_color = "#666"
        try:
            con = sqlite3.connect("data/improvements.db")
            # v4 verdict from latest go_no_go_decisions row for phase 10
            cur = con.execute(
                "SELECT verdict, gates_passed, gates_total FROM go_no_go_decisions "
                "WHERE phase_number = 10 ORDER BY decision_date DESC, id DESC LIMIT 1"
            )
            row = cur.fetchone()
            # Phase 10.5 activation state (encoded as 105)
            cur = con.execute("SELECT status FROM project_phases WHERE phase_number = 105")
            p105 = cur.fetchone()
            con.close()
            if row:
                verdict, gp, gt = row
                v4_label = f"{verdict} ({gp or 0}/{gt or 0})"
                v4_color = {"GREEN": "#4CAF50", "YELLOW": "#FFCA28", "RED": "#EF5350"}.get(verdict, "#666")
                if p105 and p105[0] == "PENDING_ACTIVATION":
                    v4_label += " — Phase 10.5 candidate"
        except Exception:
            pass
        return v3_label, v4_label, v4_color

    try:
        v3_lbl, v4_lbl, v4_clr = _get_version_status()
        st.markdown(
            f"<div style='background:#0D1117;border:1px solid #2D3748;border-radius:8px;padding:8px 12px;margin-bottom:6px;font-size:12px'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center'>"
            f"<span style='color:#888'>v3</span>"
            f"<span style='color:#4CAF50;font-weight:600'>{v3_lbl}</span>"
            f"</div>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;margin-top:4px'>"
            f"<span style='color:#888'>v4</span>"
            f"<span style='color:{v4_clr};font-weight:600;font-size:11px'>{v4_lbl}</span>"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    except Exception:
        pass

    st.caption(f"{now_utc.strftime('%H:%M:%S')} UTC")

    if st.button("تحديث البيانات", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Home Page Content ─────────────────────────────────────────────────────────
st.markdown("""
<div style="margin-bottom:16px">
    <span style="font-size:26px;font-weight:800;color:#FFF">لوحة التداول</span>
    <span style="font-size:14px;color:#666;margin-right:12px">v3.1 | Paper Trading</span>
</div>
""", unsafe_allow_html=True)

# ── Meeting-outcomes banner (latest go/no-go from improvements.db) ────────────
@st.cache_data(ttl=300, show_spinner=False)
def _get_latest_meeting_summary():
    import sqlite3
    try:
        con = sqlite3.connect("data/improvements.db")
        votes = con.execute(
            "SELECT decision_date, verdict, COUNT(*) FROM go_no_go_decisions "
            "WHERE decided_by LIKE 'meeting_%' "
            "GROUP BY decision_date, verdict "
            "ORDER BY decision_date DESC"
        ).fetchall()
        if not votes:
            con.close()
            return None
        # Group by date
        latest_date = votes[0][0]
        same_date = [v for v in votes if v[0] == latest_date]
        n_total = sum(v[2] for v in same_date)
        n_red = sum(v[2] for v in same_date if v[1] == "RED")
        n_yellow = sum(v[2] for v in same_date if v[1] == "YELLOW")
        # Days to next gate (Phase 8 gate Jun 1)
        from datetime import date
        gate = date(2026, 6, 1)
        days = (gate - date.today()).days
        con.close()
        return {"date": latest_date, "n_total": n_total, "n_red": n_red,
                "n_yellow": n_yellow, "gate_days": days}
    except Exception:
        return None

_meeting = _get_latest_meeting_summary()
if _meeting:
    border = "#EF5350" if _meeting["n_red"] > 0 else ("#FFCA28" if _meeting["n_yellow"] > 0 else "#4CAF50")
    badge = "🔴" if _meeting["n_red"] > 0 else ("🟡" if _meeting["n_yellow"] > 0 else "🟢")
    days_color = "#EF5350" if _meeting["gate_days"] <= 14 else ("#FFCA28" if _meeting["gate_days"] <= 30 else "#888")
    st.markdown(
        f"<div style='background:#12151C;border-left:4px solid {border};border-radius:8px;"
        f"padding:10px 16px;margin-bottom:14px;display:flex;align-items:center;gap:18px'>"
        f"<span style='font-size:18px'>📋</span>"
        f"<span style='color:#CCC;font-size:13px'>"
        f"<b style='color:#FFF'>Meeting {_meeting['date']}</b>: "
        f"{_meeting['n_total']} votes decided  {badge}  "
        f"<span style='color:#999'>(R={_meeting['n_red']} Y={_meeting['n_yellow']})</span>"
        f"</span>"
        f"<span style='color:{days_color};font-size:12px;margin-left:auto'>"
        f"<b>{_meeting['gate_days']} days</b> to Phase 8 gate (Jun 1)"
        f"</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    try:
        st.page_link("pages/15_Meeting_Outcomes.py",
                       label="View meeting outcomes, blockers, and risks",
                       icon="📋")
    except Exception:
        st.caption("→ Meeting Outcomes page (sidebar nav)")

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
    st.metric("صافي الربح", f"${pnl:+,.2f}", delta_color="normal")
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

# ── Main Dashboard ────────────────────────────────────────────────────────────
col_left, col_right = st.columns([3, 2])

with col_left:
    from dashboard.utils.db import get_equity_curve
    from dashboard.components.charts import equity_curve_chart, drawdown_chart

    st.subheader("منحنى رأس المال")
    days = st.slider("عدد الأيام", 7, 365, 30, key="home_days")
    eq_df = get_equity_curve(days=days)
    st.plotly_chart(equity_curve_chart(eq_df), width="stretch", key="home_equity")

    if not eq_df.empty:
        st.plotly_chart(drawdown_chart(eq_df), width="stretch", key="home_dd")

with col_right:
    from dashboard.components.charts import signal_status_bar, win_loss_pie
    from dashboard.utils.db import get_trade_results

    st.subheader("نتائج الإشارات")
    st.plotly_chart(signal_status_bar(signals), width="stretch", key="home_signals")

    st.subheader("ربح / خسارة")
    results_df = get_trade_results(limit=1000)
    st.plotly_chart(win_loss_pie(results_df), width="stretch", key="home_winloss")

st.divider()

# ── Symbol Breakdown Table ────────────────────────────────────────────────────
from dashboard.utils.db import get_symbol_breakdown

st.subheader("الأداء حسب الزوج")
sym_df = get_symbol_breakdown()
if not sym_df.empty:
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

    st.dataframe(styled, width="stretch", hide_index=True)
else:
    st.info("لا توجد صفقات مغلقة بعد.")

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
            "ml_confidence": lambda x: f"{x:.1%}" if pd.notna(x) else "-",
        }),
        width="stretch",
        hide_index=True,
    )
else:
    st.info("لا توجد إشارات بعد.")

# ── Quick Navigation ──────────────────────────────────────────────────────────
st.divider()
st.subheader("التنقل السريع")

nav_cols = st.columns(5)
pages = [
    ("الماسح", "مسح وتنفيذ الإشارات"),
    ("الصفقات", "الصفقات المفتوحة + المونيتور"),
    ("التحليلات", "Sharpe, Sortino, Calmar"),
    ("التقارير", "تقرير يومي + Telegram"),
    ("الاتصال", "حالة MT5 + الأخطاء"),
]

for col, (name, desc) in zip(nav_cols, pages):
    with col:
        st.markdown(f"""
        <div style="background:#1A1F2E;border:1px solid #2D3748;border-radius:10px;padding:16px;text-align:center;min-height:80px">
            <div style="font-size:15px;font-weight:700;color:#FFF">{name}</div>
            <div style="font-size:12px;color:#888;margin-top:4px">{desc}</div>
        </div>
        """, unsafe_allow_html=True)
