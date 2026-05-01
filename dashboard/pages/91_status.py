"""Tab 1 — Where are we? / أين نحن؟

Single-screen project status answer. Composes:
- Phase status header (5-card row)
- Top 5 blocking action items (with link to Tab 2)
- Last 3 decisions (with link to Tab 3)
- Engine health summary

Per dashboard_redesign_proposal.md. No code duplication of action-items
or decisions tables — those live in Tabs 2 and 3 respectively; this
page is a status overview that links into them."""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import sqlite3
from datetime import date

import pandas as pd
import streamlit as st

from dashboard.utils.layout import (
    IMP_DB, PHASE_8_GATE, PHASE_9_TARGET,
    page_intro, status_header,
)

st.set_page_config(page_title="أين نحن؟ — ForexAI", page_icon="📍", layout="wide")
status_header()
page_intro(
    arabic_title="أين نحن؟",
    arabic_subtitle="نظرة سريعة على حالة المشروع — المرحلة، البنود الحرجة، آخر القرارات، والمحرّك",
)


# ── Phase status header (5-card row) ─────────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def _all_phases():
    try:
        con = sqlite3.connect(IMP_DB)
        df = pd.read_sql(
            "SELECT phase_number, name, status, started_at, completed_at "
            "FROM project_phases WHERE phase_number BETWEEN 6 AND 9 "
            "ORDER BY phase_number",
            con,
        )
        con.close()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner=False)
def _phase_steps(phase_number: int):
    try:
        con = sqlite3.connect(IMP_DB)
        df = pd.read_sql(
            "SELECT step_order, status FROM phase_steps "
            "WHERE phase_number = ? ORDER BY step_order",
            con, params=(phase_number,),
        )
        con.close()
        return df
    except Exception:
        return pd.DataFrame()


phases = _all_phases()
if phases.empty:
    st.warning("تعذّر تحميل بيانات المراحل.")
else:
    cols = st.columns(len(phases))
    status_color = {
        "IN_PROGRESS": "#42A5F5", "NOT_STARTED": "#888",
        "DEFERRED": "#FFCA28", "COMPLETED": "#4CAF50",
        "PENDING_ACTIVATION": "#9C27B0",
    }
    for col, (_, ph) in zip(cols, phases.iterrows()):
        steps = _phase_steps(int(ph["phase_number"]))
        n_total = len(steps)
        n_done = int((steps["status"] == "COMPLETED").sum()) if n_total else 0
        clr = status_color.get(ph["status"], "#888")
        # Special-case Phase 8 / 9 to display gate dates
        sub = ""
        if int(ph["phase_number"]) == 8:
            d = (PHASE_8_GATE - date.today()).days
            sub = f"بوابة 1 يونيو · {d} يوم"
        elif int(ph["phase_number"]) == 9:
            d = (PHASE_9_TARGET - date.today()).days
            sub = f"هدف 1 سبتمبر · {d} يوم"
        elif n_total > 0:
            sub = f"{n_done}/{n_total} خطوات"

        with col:
            st.markdown(
                f"""
                <div style="background:#12151C;border:1px solid #2D3748;
                            border-left:4px solid {clr};border-radius:8px;
                            padding:12px 14px;min-height:110px">
                    <div style="font-size:11px;color:#888;font-weight:600">
                        Phase {int(ph['phase_number'])}
                    </div>
                    <div style="font-size:14px;color:#FFF;font-weight:700;margin:4px 0 8px 0">
                        {ph['name']}
                    </div>
                    <div style="font-size:11px;color:{clr};font-weight:700">
                        {ph['status']}
                    </div>
                    <div style="font-size:11px;color:#AAA;margin-top:4px">
                        {sub}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

st.divider()


# ── Section B — Top 5 blocking action items ──────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def _top_blockers():
    try:
        con = sqlite3.connect(IMP_DB)
        df = pd.read_sql(
            "SELECT action_id, category, title, blocking_phase, status "
            "FROM action_items "
            "WHERE status IN ('OPEN','IN_PROGRESS') AND category='BLOCKING' "
            "ORDER BY blocking_phase NULLS LAST, "
            "CASE status WHEN 'IN_PROGRESS' THEN 0 ELSE 1 END, "
            "created_date DESC LIMIT 5",
            con,
        )
        con.close()
        return df
    except Exception:
        return pd.DataFrame()


st.markdown("### 🚧 ما يجب التركيز عليه الآن")
top = _top_blockers()
if top.empty:
    st.success("لا توجد بنود حرجة مفتوحة.")
else:
    for _, it in top.iterrows():
        ph_chip = (
            f"<span style='background:#1A1F2E;color:#AAA;border:1px solid #2D3748;"
            f"border-radius:4px;padding:1px 6px;font-size:11px;margin-right:6px'>"
            f"Phase {int(it['blocking_phase'])}</span>"
            if pd.notna(it["blocking_phase"]) else ""
        )
        status_chip = (
            f"<span style='background:#1F2937;color:#42A5F5;border-radius:4px;"
            f"padding:1px 6px;font-size:11px;margin-right:6px'>{it['status']}</span>"
            if it["status"] == "IN_PROGRESS" else ""
        )
        st.markdown(
            f"""
            <div style="background:#12151C;border-left:3px solid #EF5350;
                        border-radius:6px;padding:8px 12px;margin-bottom:6px">
                <div style="font-size:11px;color:#EF5350;font-weight:700">
                    {it['action_id']} {ph_chip}{status_chip}
                </div>
                <div style="color:#DDD;font-size:13px;margin-top:2px">
                    {it['title']}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.caption("← القائمة الكاملة في تبويب «بنود التنفيذ»")

st.divider()


# ── Section C — Last 3 decisions ─────────────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def _last_decisions():
    try:
        con = sqlite3.connect(IMP_DB)
        df = pd.read_sql(
            "SELECT decision_date, phase_number, verdict, decided_by, next_action "
            "FROM go_no_go_decisions "
            "ORDER BY decision_date DESC, id DESC LIMIT 3",
            con,
        )
        con.close()
        return df
    except Exception:
        return pd.DataFrame()


st.markdown("### 📋 آخر القرارات")
dec = _last_decisions()
verdict_color = {"GREEN": "#4CAF50", "YELLOW": "#FFCA28", "RED": "#EF5350"}
if dec.empty:
    st.info("لا توجد قرارات مسجلة بعد.")
else:
    for _, d in dec.iterrows():
        v_clr = verdict_color.get(d["verdict"], "#888")
        ph_str = f"Phase {int(d['phase_number'])}" if pd.notna(d.get("phase_number")) else "—"
        st.markdown(
            f"""
            <div style="background:#12151C;border-left:3px solid {v_clr};
                        border-radius:6px;padding:8px 12px;margin-bottom:6px">
                <div style="font-size:11px;color:{v_clr};font-weight:700">
                    {d['verdict']} · {d['decision_date']} · {ph_str}
                </div>
                <div style="color:#DDD;font-size:13px;margin-top:2px">
                    {d['decided_by']}
                </div>
                <div style="color:#888;font-size:12px;margin-top:4px">
                    التالي: {d['next_action'] or '—'}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.caption("← السجل الكامل في تبويب «القرارات»")

st.divider()


# ── Section D — Engine health snapshot ───────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def _engine_health():
    """Compose a small engine-health summary from sources the dashboard already reads."""
    try:
        from dashboard.utils.mt5_helper import get_connection_status
        s = get_connection_status() or {}
    except Exception:
        s = {}
    info = {
        "mt5_connected": bool(s.get("connected")),
        "balance": (s.get("account") or {}).get("balance"),
        "login": (s.get("account") or {}).get("login"),
        "error": s.get("error"),
    }
    # Open positions
    try:
        con = sqlite3.connect("data/trading.db")
        n_open = con.execute("SELECT COUNT(*) FROM trades WHERE is_closed=0").fetchone()[0]
        con.close()
        info["n_open"] = n_open
    except Exception:
        info["n_open"] = None
    # Latest [CONFIG] line from log
    try:
        with open("data/logs/paper_trading.log", "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 65536))
            tail = f.read().decode("utf-8", errors="ignore")
        cfg_lines = [ln for ln in tail.splitlines() if "[CONFIG]" in ln]
        info["last_config"] = cfg_lines[-1] if cfg_lines else None
    except Exception:
        info["last_config"] = None
    return info


st.markdown("### ⚙️ صحة المحرّك")
h = _engine_health()
c1, c2, c3, c4 = st.columns(4)
with c1:
    if h["mt5_connected"]:
        st.metric("MT5", "متصل", delta_color="off")
        st.caption(f"حساب {h.get('login') or '—'}")
    else:
        st.metric("MT5", "غير متصل", delta_color="off")
        if h.get("error"):
            st.caption(h["error"][:50])
with c2:
    if h["balance"] is not None:
        st.metric("الرصيد", f"${h['balance']:,.0f}")
with c3:
    if h["n_open"] is not None:
        st.metric("صفقات مفتوحة", h["n_open"])
with c4:
    cfg = h.get("last_config")
    if cfg:
        st.metric("آخر [CONFIG]", cfg[:19])
    else:
        st.metric("آخر [CONFIG]", "—")

if h.get("last_config"):
    st.caption(f"`{h['last_config'][:200]}`")

# Refresh control
st.divider()
if st.button("تحديث البيانات", use_container_width=False):
    st.cache_data.clear()
    st.rerun()
