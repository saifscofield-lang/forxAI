"""
Project Tracker — Phase progress, system state, decisions, improvements
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timezone

st.set_page_config(page_title="Project Tracker", page_icon="::clipboard::", layout="wide")

st.title("Project Tracker")
st.caption("Strategy Lab phases, system state, and enhancement history")

IMP_DB = "data/improvements.db"
TRADING_DB = "data/trading.db"
BACKTEST_DB = "data/backtest_results.db"


def get_conn(path):
    return sqlite3.connect(path)


# ══════════════════════════════════════════════════════════════
# TAB LAYOUT
# ══════════════════════════════════════════════════════════════
tab_phases, tab_state, tab_decisions, tab_improvements, tab_shadow = st.tabs([
    "Phases", "System State", "Decisions", "Improvements", "Shadow Trading"
])


# ── TAB 1: PHASES ────────────────────────────────────────────
with tab_phases:
    try:
        conn = get_conn(IMP_DB)

        # Phase overview
        phases = pd.read_sql("SELECT * FROM project_phases ORDER BY phase_number", conn)

        if not phases.empty:
            # Progress bar
            completed = len(phases[phases["status"] == "COMPLETED"])
            in_progress = len(phases[phases["status"] == "IN_PROGRESS"])
            total = len(phases)
            progress = (completed + in_progress * 0.5) / total
            st.progress(progress, text=f"Phase {completed}/{total} completed")

            # Phase cards
            for _, phase in phases.iterrows():
                pn = phase["phase_number"]
                status = phase["status"]

                if status == "COMPLETED":
                    color = "#4CAF50"
                    icon = "[DONE]"
                elif status == "IN_PROGRESS":
                    color = "#FF9800"
                    icon = "[ACTIVE]"
                else:
                    color = "#666"
                    icon = "[--]"

                with st.expander(f"{icon} Phase {pn} — {phase['name']}", expanded=(status == "IN_PROGRESS")):
                    cols = st.columns([2, 1, 1])
                    cols[0].markdown(f"**Duration:** {phase['duration']}")
                    cols[1].markdown(f"**Status:** :{color}[{status}]")
                    if phase["started_at"]:
                        cols[2].markdown(f"**Started:** {phase['started_at']}")

                    # Steps for this phase
                    steps = pd.read_sql(
                        f"SELECT * FROM phase_steps WHERE phase_number = {pn} ORDER BY step_order", conn
                    )
                    if not steps.empty:
                        for _, step in steps.iterrows():
                            s_status = step["status"]
                            if s_status == "COMPLETED":
                                st.markdown(f"  [x] ~~{step['description']}~~")
                            elif s_status == "IN_PROGRESS":
                                st.markdown(f"  [>] **{step['description']}**")
                            else:
                                st.markdown(f"  [ ] {step['description']}")

        conn.close()
    except Exception as e:
        st.error(f"Error loading phases: {e}")


# ── TAB 2: SYSTEM STATE ─────────────────────────────────────
with tab_state:
    try:
        # Live stats from trading.db
        conn_t = get_conn(TRADING_DB)

        col1, col2, col3, col4 = st.columns(4)

        # Account
        try:
            acc = pd.read_sql("SELECT balance, equity FROM account_snapshots ORDER BY time DESC LIMIT 1", conn_t)
            if not acc.empty:
                col1.metric("Balance", f"${acc.iloc[0]['balance']:,.2f}")
                col2.metric("Equity", f"${acc.iloc[0]['equity']:,.2f}")
        except Exception:
            pass

        # Trades
        try:
            trades = pd.read_sql("SELECT COUNT(*) as total, SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins, SUM(profit) as pnl FROM trades WHERE is_closed = 1", conn_t)
            if not trades.empty and trades.iloc[0]["total"] > 0:
                t = trades.iloc[0]
                wr = (t["wins"] / t["total"] * 100) if t["total"] > 0 else 0
                col3.metric("Total P&L", f"${t['pnl']:+,.2f}")
                col4.metric("Win Rate", f"{wr:.1f}% ({int(t['wins'])}/{int(t['total'])})")
        except Exception:
            pass

        st.divider()

        # Strategy status
        st.subheader("Active Strategies")
        try:
            strats = pd.read_sql("""
                SELECT strategy, symbol, COUNT(*) as trades,
                       SUM(profit) as pnl,
                       SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins
                FROM trades WHERE is_closed = 1
                GROUP BY strategy, symbol
                ORDER BY SUM(profit) DESC
            """, conn_t)
            if not strats.empty:
                strats["WR%"] = (strats["wins"] / strats["trades"] * 100).round(1)
                strats["pnl"] = strats["pnl"].round(2)
                st.dataframe(
                    strats[["strategy", "symbol", "trades", "WR%", "pnl"]].rename(
                        columns={"strategy": "Strategy", "symbol": "Symbol", "trades": "Trades", "pnl": "P&L"}
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
        except Exception:
            st.info("No trade data yet")

        st.divider()

        # Open positions
        st.subheader("Open Positions")
        try:
            opens = pd.read_sql("""
                SELECT symbol, order_type, strategy, volume, profit, open_time
                FROM trades WHERE is_closed = 0 ORDER BY open_time DESC
            """, conn_t)
            if not opens.empty:
                st.dataframe(opens, use_container_width=True, hide_index=True)
            else:
                st.info("No open positions")
        except Exception:
            pass

        conn_t.close()

    except Exception as e:
        st.error(f"Error loading state: {e}")


# ── TAB 3: DECISIONS ─────────────────────────────────────────
with tab_decisions:
    try:
        conn = get_conn(IMP_DB)
        decisions = pd.read_sql(
            "SELECT time, category, decision, reason, impact, phase FROM decisions_log ORDER BY time DESC",
            conn
        )
        conn.close()

        if not decisions.empty:
            for _, d in decisions.iterrows():
                cat_colors = {
                    "BACKTEST": "#2196F3",
                    "OPTIMIZATION": "#9C27B0",
                    "RISK": "#F44336",
                    "STRATEGY": "#FF9800",
                    "DATA": "#4CAF50",
                }
                color = cat_colors.get(d["category"], "#666")

                st.markdown(f"""
                <div style="background:#1A1F2E;border-left:3px solid {color};border-radius:4px;padding:10px 14px;margin-bottom:8px">
                    <div style="display:flex;justify-content:space-between">
                        <span style="color:{color};font-weight:600;font-size:13px">{d['category']}</span>
                        <span style="color:#666;font-size:12px">Phase {d['phase']} | {d['time']}</span>
                    </div>
                    <div style="color:#DDD;font-size:13px;margin-top:6px">{d['decision']}</div>
                    <div style="color:#888;font-size:12px;margin-top:4px">Reason: {d['reason']}</div>
                    <div style="color:#AAA;font-size:12px;margin-top:2px">Impact: {d['impact']}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No decisions logged yet")

    except Exception as e:
        st.error(f"Error loading decisions: {e}")


# ── TAB 4: IMPROVEMENTS ─────────────────────────────────────
with tab_improvements:
    try:
        conn = get_conn(IMP_DB)
        imps = pd.read_sql(
            "SELECT code, title, category, priority, status FROM improvements ORDER BY id DESC",
            conn
        )
        conn.close()

        if not imps.empty:
            # Summary metrics
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total", len(imps))
            c2.metric("Done", len(imps[imps["status"] == "DONE"]))
            c3.metric("Skipped", len(imps[imps["status"] == "SKIPPED"]))
            c4.metric("Pending", len(imps[imps["status"].isin(["PENDING", "TODO"])]))

            st.divider()

            # Filter
            status_filter = st.multiselect("Filter by status", imps["status"].unique().tolist(), default=["DONE"])
            filtered = imps[imps["status"].isin(status_filter)] if status_filter else imps

            st.dataframe(
                filtered,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "code": st.column_config.TextColumn("Code", width=80),
                    "title": st.column_config.TextColumn("Title", width=400),
                    "category": st.column_config.TextColumn("Category", width=100),
                    "priority": st.column_config.TextColumn("Priority", width=80),
                    "status": st.column_config.TextColumn("Status", width=80),
                },
            )
        else:
            st.info("No improvements tracked")

    except Exception as e:
        st.error(f"Error loading improvements: {e}")


# ── TAB 5: SHADOW TRADING ───────────────────────────────────
with tab_shadow:
    try:
        conn_t = get_conn(TRADING_DB)

        # Summary metrics
        total = pd.read_sql("SELECT COUNT(*) as n FROM shadow_signals", conn_t).iloc[0]["n"]
        executed = pd.read_sql("SELECT COUNT(*) as n FROM shadow_signals WHERE executed = 1", conn_t).iloc[0]["n"]
        blocked = pd.read_sql("SELECT COUNT(*) as n FROM shadow_signals WHERE executed = 0", conn_t).iloc[0]["n"]
        open_s = pd.read_sql("SELECT COUNT(*) as n FROM shadow_signals WHERE sim_status = 'OPEN'", conn_t).iloc[0]["n"]
        resolved = pd.read_sql("SELECT COUNT(*) as n FROM shadow_signals WHERE sim_status != 'OPEN'", conn_t).iloc[0]["n"]

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Signals", total)
        c2.metric("Executed", executed)
        c3.metric("Blocked", blocked)
        c4.metric("Open", open_s)
        c5.metric("Resolved", resolved)

        if resolved > 0:
            st.divider()
            st.subheader("Filter Effectiveness")

            filter_stats = pd.read_sql("""
                SELECT rejection_reason as Filter,
                       COUNT(*) as Total,
                       SUM(CASE WHEN label = 1 THEN 1 ELSE 0 END) as Would_Win,
                       SUM(CASE WHEN label = 0 THEN 1 ELSE 0 END) as Would_Lose
                FROM shadow_signals
                WHERE executed = 0 AND sim_status != 'OPEN'
                GROUP BY rejection_reason
            """, conn_t)

            if not filter_stats.empty:
                filter_stats["Accuracy%"] = (
                    filter_stats["Would_Lose"] / filter_stats["Total"] * 100
                ).round(1)
                st.dataframe(filter_stats, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Recent Shadow Signals")

        recent = pd.read_sql("""
            SELECT time, symbol, action, strategy, executed,
                   rejection_reason, regime, sim_status, sim_pnl_pips,
                   CASE WHEN label = 1 THEN 'WIN' WHEN label = 0 THEN 'LOSS' ELSE 'OPEN' END as outcome
            FROM shadow_signals
            ORDER BY time DESC LIMIT 50
        """, conn_t)

        if not recent.empty:
            st.dataframe(recent, use_container_width=True, hide_index=True)
        else:
            st.info("No shadow signals yet. Restart start.bat to begin collecting.")

        conn_t.close()

    except Exception as e:
        st.error(f"Error loading shadow data: {e}")
