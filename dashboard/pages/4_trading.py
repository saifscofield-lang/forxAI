"""Tab 5 — Trading / التداول

The trading-system overview: live engine state + analytics + trade
log + signals/shadow. Consolidates content from old pages
2_open_trades, 3_trade_log, 4_signals, 5_analytics, 8_news,
10_Trade_Chart, 11_reports, 12_connection plus parts of
13_Project_Tracker.

Per dashboard_redesign_proposal.md. ML model views were moved to a
markdown report (per project lead default); not surfaced here."""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import sqlite3
import pandas as pd
import streamlit as st

from dashboard.utils.layout import page_intro, status_header
from dashboard.utils.db import (
    get_equity_curve, get_latest_snapshot, get_open_trades,
    get_closed_trades, get_signal_log, get_trade_results,
    get_performance_summary, get_symbol_breakdown,
    get_monthly_pnl, get_signal_stats,
    get_upcoming_news, get_recent_news,
)
from dashboard.components.charts import (
    equity_curve_chart, drawdown_chart, pnl_distribution_chart,
    win_loss_pie, monthly_pnl_chart, cumulative_pnl_by_symbol,
    signal_status_bar, candlestick_chart,
)
from analysis.rr_calculator import phase7_ship_gate

st.set_page_config(page_title="التداول — ForexAI", page_icon="📈", layout="wide")
status_header()
page_intro(
    arabic_title="التداول",
    arabic_subtitle="حالة المحرّك المباشرة، التحليلات، سجل الصفقات، والإشارات",
)


# ── Top header — account + dual-gate snapshot ────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def _account_summary():
    snap = get_latest_snapshot() or {}
    summary = get_performance_summary() or {}
    return snap, summary


@st.cache_data(ttl=120, show_spinner=False)
def _dual_gate_v3():
    """Compute Phase 7 dual-gate PF on full v3 (engine_version=2.4) trades."""
    try:
        con = sqlite3.connect("data/trading.db")
        rows = con.execute(
            "SELECT pnl, risk_reward_actual FROM trade_results "
            "WHERE engine_version='2.4'"
        ).fetchall()
        con.close()
        pnls = [r[0] for r in rows if r[0] is not None]
        rrs = [r[1] for r in rows if r[1] is not None]
        if not pnls and not rrs:
            return None
        return phase7_ship_gate(pnls=pnls, rrs=rrs)
    except Exception:
        return None


snap, summary = _account_summary()
gate = _dual_gate_v3()

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("الرصيد", f"${(snap or {}).get('balance', 0):,.0f}")
c2.metric("الإكويتي", f"${(snap or {}).get('equity', 0):,.0f}")
c3.metric("صفقات مفتوحة", len(get_open_trades()))
c4.metric("إجمالي الصفقات", summary.get("total_trades", 0))
c5.metric("نسبة الفوز", f"{summary.get('win_rate', 0):.1f}%")
if gate:
    pass_color = "normal" if gate["passes_dual_gate"] else "inverse"
    c6.metric(
        "بوابة Phase 7",
        "✓ PASS" if gate["passes_dual_gate"] else "✗ FAIL",
        delta=f"R-PF {gate['pf_r']:.2f} · $-PF {gate['pf_dollars']:.2f}",
        delta_color=pass_color,
    )
else:
    c6.metric("بوابة Phase 7", "—")

st.caption(
    "بوابة Phase 7: R-PF ≥ 1.3 و $-PF ≥ 1.0 (انظر docs/research/phase7_ship_gate_definition.md)"
    if gate else ""
)
st.divider()


# ── Inner tabs ───────────────────────────────────────────────────────────────
inner = st.tabs(["مباشر", "تحليلات", "سجل الصفقات", "الإشارات والظل"])


# ── 5A — Live ────────────────────────────────────────────────────────────────
with inner[0]:
    st.markdown("### الصفقات المفتوحة")
    open_df = get_open_trades()
    if open_df.empty:
        st.info("لا توجد صفقات مفتوحة حالياً.")
    else:
        cols = [c for c in ["ticket", "symbol", "order_type", "open_price",
                            "stop_loss", "take_profit", "volume", "open_time",
                            "strategy"] if c in open_df.columns]
        st.dataframe(
            open_df[cols].rename(columns={
                "ticket": "تذكرة", "symbol": "زوج", "order_type": "اتجاه",
                "open_price": "سعر الفتح", "stop_loss": "SL", "take_profit": "TP",
                "volume": "حجم", "open_time": "وقت الفتح", "strategy": "استراتيجية",
            }),
            hide_index=True, width="stretch",
        )

    st.markdown("### التقويم الاقتصادي — 24 ساعة قادمة")
    upcoming = get_upcoming_news(hours_ahead=24)
    if upcoming.empty:
        st.success("لا أحداث اقتصادية قادمة في 24 ساعة.")
    else:
        cols = [c for c in ["time", "currency", "event_name", "impact", "forecast", "previous"] if c in upcoming.columns]
        st.dataframe(upcoming[cols], hide_index=True, width="stretch", height=200)

    st.markdown("### سجل المحرّك (آخر 30 سطر)")
    try:
        with open("data/logs/paper_trading.log", "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 16384))
            tail = f.read().decode("utf-8", errors="ignore")
        last_lines = tail.splitlines()[-30:]
        st.code("\n".join(last_lines), language=None)
    except Exception as e:
        st.caption(f"تعذّر قراءة السجل: {e}")


# ── 5B — Analytics ───────────────────────────────────────────────────────────
with inner[1]:
    days = st.slider("عدد الأيام", 7, 365, 30, key="trading_days")
    eq_df = get_equity_curve(days=days)

    a1, a2 = st.columns([3, 2])
    with a1:
        st.markdown("### منحنى رأس المال")
        st.plotly_chart(equity_curve_chart(eq_df), width="stretch", key="t_eq")
        if not eq_df.empty:
            st.markdown("### التراجع")
            st.plotly_chart(drawdown_chart(eq_df), width="stretch", key="t_dd")

    with a2:
        st.markdown("### KPI الشامل")
        st.metric("صافي الربح", f"${summary.get('total_pnl', 0):+,.2f}")
        st.metric("عامل الربح ($)", f"{summary.get('profit_factor', 0):.3f}")
        st.metric("أقصى تراجع", f"${summary.get('max_drawdown', 0):,.2f}")
        if gate:
            st.metric("R-PF (v3)", f"{gate['pf_r']:.3f}")
            st.metric("$-PF (v3)", f"{gate['pf_dollars']:.3f}")
            verdict = "✓ PASS" if gate["passes_dual_gate"] else "✗ FAIL"
            st.metric("بوابة Phase 7", verdict)

        st.markdown("### نتائج الإشارات")
        sig_stats = get_signal_stats()
        st.plotly_chart(signal_status_bar(sig_stats), width="stretch", key="t_sig_bar")

        st.markdown("### ربح / خسارة")
        results_df = get_trade_results(limit=1000)
        st.plotly_chart(win_loss_pie(results_df), width="stretch", key="t_wl_pie")

    st.divider()
    st.markdown("### الأداء حسب الزوج")
    sym_df = get_symbol_breakdown()
    if not sym_df.empty:
        styled = sym_df.style.format({
            "win_rate": "{:.1f}%",
            "total_pnl": "${:+,.2f}",
            "profit_factor": "{:.3f}",
            "avg_pnl": "${:+,.2f}",
        })
        st.dataframe(styled, hide_index=True, width="stretch")
    else:
        st.info("لا توجد صفقات مغلقة بعد.")

    st.markdown("### الربح / الخسارة الشهري")
    monthly = get_monthly_pnl()
    if not monthly.empty:
        st.plotly_chart(monthly_pnl_chart(monthly), width="stretch", key="t_monthly")

    st.markdown("### الربح التراكمي حسب الزوج")
    if not results_df.empty:
        st.plotly_chart(cumulative_pnl_by_symbol(results_df), width="stretch", key="t_cumpnl")

    st.markdown("### توزيع الربح / الخسارة")
    if not results_df.empty:
        st.plotly_chart(pnl_distribution_chart(results_df), width="stretch", key="t_pnldist")


# ── 5C — Trade log ───────────────────────────────────────────────────────────
with inner[2]:
    st.markdown("### سجل الصفقات المغلقة")
    closed = get_closed_trades(limit=2000)
    if closed.empty:
        st.info("لا توجد صفقات مغلقة بعد.")
    else:
        # Filters
        fc1, fc2, fc3 = st.columns(3)
        symbol_options = sorted(closed["symbol"].dropna().unique()) if "symbol" in closed.columns else []
        sym_sel = fc1.multiselect("الزوج", options=symbol_options, default=[], key="trade_log_sym")
        strat_options = sorted(closed["strategy"].dropna().unique()) if "strategy" in closed.columns else []
        strat_sel = fc2.multiselect("الاستراتيجية", options=strat_options, default=[], key="trade_log_strat")
        side_sel = fc3.multiselect("الاتجاه", options=["BUY", "SELL"], default=[], key="trade_log_side")

        f = closed.copy()
        if sym_sel:
            f = f[f["symbol"].isin(sym_sel)]
        if strat_sel:
            f = f[f["strategy"].isin(strat_sel)]
        if side_sel and "order_type" in f.columns:
            f = f[f["order_type"].isin(side_sel)]

        st.caption(f"عدد الصفقات بعد الفلترة: {len(f)} من أصل {len(closed)}")

        cols = [c for c in ["ticket", "symbol", "order_type", "open_time",
                            "close_time", "open_price", "close_price",
                            "profit", "strategy"] if c in f.columns]
        st.dataframe(
            f[cols].rename(columns={
                "ticket": "تذكرة", "symbol": "زوج", "order_type": "اتجاه",
                "open_time": "فتح", "close_time": "إغلاق",
                "open_price": "سعر الفتح", "close_price": "سعر الإغلاق",
                "profit": "ربح", "strategy": "استراتيجية",
            }),
            hide_index=True, width="stretch", height=400,
        )

        # Per-trade chart drilldown
        st.markdown("### رسم بياني لصفقة")
        if "ticket" in f.columns and not f.empty:
            tickets = f["ticket"].astype(str).tolist()
            sel_ticket = st.selectbox(
                "اختر تذكرة", options=[None] + tickets,
                format_func=lambda x: "— اختر —" if x is None else x,
                key="trade_chart_select",
            )
            if sel_ticket:
                trade_row = f[f["ticket"].astype(str) == sel_ticket].iloc[0]
                # Try to fetch nearby OHLCV bars for the chart
                try:
                    con = sqlite3.connect("data/trading.db")
                    sym = str(trade_row["symbol"])
                    # Coerce open_time / close_time to strings — pandas
                    # Timestamp objects don't bind directly to sqlite3
                    # parameters and SQLite's datetime() function expects a
                    # text input anyway. Drop microseconds for cleanliness.
                    open_ts = pd.to_datetime(trade_row["open_time"])
                    close_ts = pd.to_datetime(trade_row["close_time"])
                    open_t = open_ts.strftime("%Y-%m-%d %H:%M:%S")
                    close_t = close_ts.strftime("%Y-%m-%d %H:%M:%S")
                    bars = pd.read_sql(
                        "SELECT time, open, high, low, close FROM ohlcv_bars "
                        "WHERE symbol=? AND timeframe='H1' "
                        "AND time BETWEEN datetime(?, '-12 hours') AND datetime(?, '+12 hours') "
                        "ORDER BY time",
                        con, params=(sym, open_t, close_t),
                    )
                    con.close()
                    if not bars.empty:
                        st.plotly_chart(
                            candlestick_chart(bars, sym),
                            width="stretch", key=f"chart_{sel_ticket}",
                        )
                        st.caption(
                            f"فتح {trade_row['open_price']:.5f} · "
                            f"SL {trade_row.get('stop_loss', '—')} · "
                            f"TP {trade_row.get('take_profit', '—')} · "
                            f"إغلاق {trade_row['close_price']:.5f} · "
                            f"ربح ${trade_row['profit']:.2f}"
                        )
                    else:
                        # Diagnose: is it a coverage problem (bars table stale) or
                        # a per-symbol gap?
                        con2 = sqlite3.connect("data/trading.db")
                        last_bar = con2.execute(
                            "SELECT MAX(time) FROM ohlcv_bars WHERE symbol=? AND timeframe='H1'",
                            (sym,),
                        ).fetchone()[0]
                        con2.close()
                        if last_bar and pd.to_datetime(last_bar) < open_ts:
                            st.warning(
                                f"بيانات OHLCV لـ {sym} متوقفة عند {last_bar} — "
                                f"الصفقة فُتحت {open_t}، خارج نطاق البيانات المحفوظة. "
                                "شغّل `python scripts/download_historical_data.py` لتحديث جدول ohlcv_bars."
                            )
                        else:
                            st.warning(
                                f"لا توجد بيانات OHLCV للنافذة المحيطة بالصفقة "
                                f"({open_t} → {close_t})."
                            )
                except Exception as e:
                    st.caption(f"تعذّر تحميل الرسم البياني: {e}")


# ── 5D — Signals & Shadow ────────────────────────────────────────────────────
with inner[3]:
    st.markdown("### سجل الإشارات (آخر 200)")
    sig_df = get_signal_log(limit=200, days=30)
    if sig_df.empty:
        st.info("لا توجد إشارات.")
    else:
        f1, f2, f3 = st.columns(3)
        sym_filter = f1.multiselect(
            "الزوج", options=sorted(sig_df["symbol"].dropna().unique()),
            default=[], key="sig_sym",
        )
        status_filter = f2.multiselect(
            "الحالة", options=sorted(sig_df["status"].dropna().unique()),
            default=[], key="sig_status",
        )
        strat_filter = f3.multiselect(
            "الاستراتيجية", options=sorted(sig_df["strategy"].dropna().unique()),
            default=[], key="sig_strat",
        )
        sf = sig_df.copy()
        if sym_filter:
            sf = sf[sf["symbol"].isin(sym_filter)]
        if status_filter:
            sf = sf[sf["status"].isin(status_filter)]
        if strat_filter:
            sf = sf[sf["strategy"].isin(strat_filter)]
        cols = [c for c in ["time", "symbol", "action", "price", "strategy",
                            "status", "ml_confidence", "reason"] if c in sf.columns]
        st.dataframe(
            sf[cols].style.format({
                "price": "{:.5f}",
                "ml_confidence": lambda x: f"{x:.1%}" if pd.notna(x) else "—",
            }),
            hide_index=True, width="stretch", height=400,
        )

    st.markdown("### الإشارات الظلية (Shadow)")
    try:
        con = sqlite3.connect("data/trading.db")
        shadow = pd.read_sql(
            "SELECT time, symbol, action, status, sim_status, sim_pnl, executed "
            "FROM shadow_signals ORDER BY time DESC LIMIT 100",
            con,
        )
        con.close()
    except Exception:
        shadow = pd.DataFrame()
    if shadow.empty:
        st.info("لا توجد إشارات ظلية.")
    else:
        st.dataframe(shadow, hide_index=True, width="stretch", height=300)


# Refresh
st.divider()
if st.button("تحديث البيانات", use_container_width=False):
    st.cache_data.clear()
    st.rerun()
