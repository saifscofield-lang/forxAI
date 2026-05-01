"""Tab 3 — Decisions / القرارات

Single home for go_no_go_decisions + decision_inputs + (legacy)
decisions_log. Replaces 6 prior surfaces of decision data.

Per dashboard_redesign_proposal.md."""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import sqlite3
import pandas as pd
import streamlit as st

from dashboard.utils.layout import IMP_DB, page_intro, status_header

st.set_page_config(page_title="القرارات — ForexAI", page_icon="📋", layout="wide")
status_header()
page_intro(
    arabic_title="القرارات",
    arabic_subtitle="قرارات go/no-go، مدخلات المراجعات، والسجل القديم — مصدر موحَّد",
)


# ── Load all three tables ────────────────────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def _load_decisions() -> pd.DataFrame:
    try:
        con = sqlite3.connect(IMP_DB)
        df = pd.read_sql(
            "SELECT id, phase_number, decision_date, verdict, gates_passed, "
            "gates_total, rationale_en, rationale_ar, decided_by, next_action, created_at "
            "FROM go_no_go_decisions "
            "ORDER BY decision_date DESC, id DESC",
            con,
        )
        con.close()
        return df
    except Exception as e:
        st.error(f"تعذّر تحميل القرارات: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner=False)
def _load_inputs() -> pd.DataFrame:
    try:
        con = sqlite3.connect(IMP_DB)
        df = pd.read_sql(
            "SELECT id, input_date, phase_number, subject, summary, artifacts, source "
            "FROM decision_inputs ORDER BY input_date DESC, id DESC",
            con,
        )
        con.close()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner=False)
def _load_legacy() -> pd.DataFrame:
    try:
        con = sqlite3.connect(IMP_DB)
        df = pd.read_sql(
            "SELECT time, category, decision, reason, impact, phase "
            "FROM decisions_log ORDER BY time DESC",
            con,
        )
        con.close()
        return df
    except Exception:
        return pd.DataFrame()


decisions = _load_decisions()
inputs = _load_inputs()
legacy = _load_legacy()

if decisions.empty and inputs.empty and legacy.empty:
    st.warning("لا توجد قرارات مسجلة.")
    st.stop()


# ── KPI ribbon ───────────────────────────────────────────────────────────────
total = len(decisions)
n_green = int((decisions["verdict"] == "GREEN").sum()) if not decisions.empty else 0
n_yellow = int((decisions["verdict"] == "YELLOW").sum()) if not decisions.empty else 0
n_red = int((decisions["verdict"] == "RED").sum()) if not decisions.empty else 0
last_date = decisions["decision_date"].iloc[0] if not decisions.empty else "—"
n_inputs = len(inputs)
n_legacy = len(legacy)

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("إجمالي القرارات", total)
c2.metric("GREEN", n_green)
c3.metric("YELLOW", n_yellow)
c4.metric("RED", n_red)
c5.metric("آخر قرار", last_date)
c6.metric("مدخلات مراجعة", n_inputs)

st.divider()


# ── Filters ──────────────────────────────────────────────────────────────────
st.markdown("### الفلاتر")
fc1, fc2, fc3, fc4 = st.columns([1, 1, 1, 2])

phase_options = sorted([int(p) for p in decisions["phase_number"].dropna().unique()]) if not decisions.empty else []
phase_filter = fc1.multiselect(
    "المرحلة", options=phase_options, default=[], key="dec_phase"
)

verdict_filter = fc2.multiselect(
    "الحكم", options=["GREEN", "YELLOW", "RED"], default=[], key="dec_verdict"
)

source_options = sorted(decisions["decided_by"].dropna().unique()) if not decisions.empty else []
source_filter = fc3.multiselect(
    "المصدر", options=source_options, default=[], key="dec_source"
)

search = fc4.text_input(
    "بحث في الحكم أو السبب",
    value="", key="dec_search",
).strip().lower()


# ── Apply filters ────────────────────────────────────────────────────────────
filtered = decisions.copy()
if phase_filter:
    filtered = filtered[filtered["phase_number"].isin(phase_filter)]
if verdict_filter:
    filtered = filtered[filtered["verdict"].isin(verdict_filter)]
if source_filter:
    filtered = filtered[filtered["decided_by"].isin(source_filter)]
if search:
    fields = ["rationale_en", "rationale_ar", "next_action", "decided_by"]
    mask = pd.Series(False, index=filtered.index)
    for f in fields:
        if f in filtered.columns:
            mask = mask | filtered[f].astype(str).str.lower().str.contains(search, na=False)
    filtered = filtered[mask]


# ── Main chronological list ──────────────────────────────────────────────────
st.markdown(f"### السجل الزمني ({len(filtered)} قرار)")

verdict_color = {"GREEN": "#4CAF50", "YELLOW": "#FFCA28", "RED": "#EF5350"}

if filtered.empty:
    st.info("لا توجد قرارات مطابقة للفلاتر.")
else:
    for _, d in filtered.iterrows():
        v_clr = verdict_color.get(d["verdict"], "#888")
        ph = f"Phase {int(d['phase_number'])}" if pd.notna(d.get("phase_number")) else "—"
        gates = (
            f"({int(d['gates_passed'])}/{int(d['gates_total'])} gates)"
            if pd.notna(d.get("gates_passed")) and pd.notna(d.get("gates_total"))
            else ""
        )
        rationale = d.get("rationale_ar") or d.get("rationale_en") or ""
        with st.container():
            st.markdown(
                f"""
                <div style="background:#12151C;border-left:4px solid {v_clr};
                            border-radius:6px;padding:10px 14px;margin-bottom:10px">
                    <div style="font-size:12px;color:#888;font-weight:600">
                        <span style="color:{v_clr};font-weight:700;font-size:13px">
                            {d['verdict']}
                        </span>
                        · {d['decision_date']} · {ph} {gates}
                    </div>
                    <div style="color:#DDD;font-size:13px;margin-top:6px">
                        <b>قرار:</b> {d['decided_by']}
                    </div>
                    <div style="color:#AAA;font-size:12px;margin-top:4px">
                        {rationale[:300]}{'…' if len(rationale) > 300 else ''}
                    </div>
                    <div style="color:#FF9800;font-size:12px;margin-top:6px">
                        <b>التالي:</b> {d['next_action'] or '—'}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

st.divider()


# ── Decision inputs section ──────────────────────────────────────────────────
st.markdown(f"### مدخلات المراجعة ({len(inputs)})")
st.caption("مراجعات وتقييمات تَدخل في عملية اتخاذ القرار قبل التصويت.")
if inputs.empty:
    st.info("لا توجد مدخلات مراجعة مسجلة.")
else:
    for _, ip in inputs.iterrows():
        ph = f"Phase {int(ip['phase_number'])}" if pd.notna(ip.get("phase_number")) else "—"
        st.markdown(
            f"""
            <div style="background:#12151C;border-left:4px solid #42A5F5;
                        border-radius:6px;padding:10px 14px;margin-bottom:8px">
                <div style="font-size:12px;color:#888">
                    <b style="color:#42A5F5">{ip['source']}</b> ·
                    {ip['input_date']} · {ph}
                </div>
                <div style="color:#DDD;font-size:13px;margin-top:4px;font-weight:600">
                    {ip['subject']}
                </div>
                <div style="color:#AAA;font-size:12px;margin-top:4px">
                    {(ip['summary'] or '')[:300]}
                </div>
                <div style="color:#666;font-size:11px;margin-top:6px">
                    المرفقات: {ip['artifacts'] or '—'}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.divider()


# ── Legacy decisions_log (collapsed) ─────────────────────────────────────────
with st.expander(f"📜 السجل القديم — decisions_log ({n_legacy} مدخل)"):
    st.caption(
        "هذه السجلات بُنية مخطط أقدم من go_no_go_decisions (الذي بدأ في أبريل 2026). "
        "محفوظة هنا للمرجعية التاريخية."
    )
    if legacy.empty:
        st.info("لا توجد سجلات قديمة.")
    else:
        st.dataframe(
            legacy.rename(
                columns={
                    "time": "الوقت", "category": "الفئة", "decision": "القرار",
                    "reason": "السبب", "impact": "الأثر", "phase": "المرحلة",
                }
            ),
            hide_index=True, width="stretch",
        )

# Refresh
st.divider()
if st.button("تحديث البيانات", use_container_width=False):
    st.cache_data.clear()
    st.rerun()
