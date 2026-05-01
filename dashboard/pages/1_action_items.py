"""Tab 2 — Action Items / بنود التنفيذ

THE single home for action_items rows (AI-*, GAP-FID-*, GAP-OPS-*).
Filter by phase, category, status; search by title; click a row's ID
in the detail dropdown to expand full notes + source.

Per dashboard_redesign_proposal.md. Replaces 6 prior surfaces of the
same DB table. Legacy `improvements` table is intentionally NOT
surfaced (DB rows preserved; not shown)."""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import sqlite3
import pandas as pd
import streamlit as st

from dashboard.utils.layout import IMP_DB, page_intro, status_header

st.set_page_config(page_title="بنود التنفيذ — ForexAI", page_icon="✅", layout="wide")
status_header()
page_intro(
    arabic_title="بنود التنفيذ",
    arabic_subtitle="جميع البنود (AI-* / GAP-* / R-EXT) من جدول action_items — مصدر واحد للحقيقة",
)


# ── Data load ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def _load_actions() -> pd.DataFrame:
    try:
        con = sqlite3.connect(IMP_DB)
        df = pd.read_sql(
            "SELECT action_id, category, title, description, blocking_phase, "
            "status, created_date, due_date, completed_date, source, notes "
            "FROM action_items "
            "ORDER BY CASE status WHEN 'OPEN' THEN 0 WHEN 'IN_PROGRESS' THEN 1 "
            "WHEN 'DONE' THEN 2 ELSE 3 END, "
            "blocking_phase ASC, action_id",
            con,
        )
        con.close()
        return df
    except Exception as e:
        st.error(f"تعذّر تحميل بنود التنفيذ: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner=False)
def _load_status_history(action_id: str) -> pd.DataFrame:
    """status_history table is currently 34 rows; surfaced here per the
    redesign proposal (was unsurfaced before)."""
    try:
        con = sqlite3.connect(IMP_DB)
        # Schema may vary; try a generic select
        cols = [r[1] for r in con.execute("PRAGMA table_info(status_history)").fetchall()]
        if "action_id" not in cols and "item_id" in cols:
            df = pd.read_sql(
                "SELECT * FROM status_history WHERE item_id=? ORDER BY id DESC",
                con, params=(action_id,),
            )
        elif "action_id" in cols:
            df = pd.read_sql(
                "SELECT * FROM status_history WHERE action_id=? ORDER BY id DESC",
                con, params=(action_id,),
            )
        else:
            df = pd.DataFrame()
        con.close()
        return df
    except Exception:
        return pd.DataFrame()


actions = _load_actions()
if actions.empty:
    st.warning("لا توجد بنود.")
    st.stop()


# ── KPI ribbon (Principle 3 — status before detail) ──────────────────────────
total = len(actions)
n_open = int((actions["status"] == "OPEN").sum())
n_in_progress = int((actions["status"] == "IN_PROGRESS").sum())
n_done = int((actions["status"] == "DONE").sum())

cat_counts = actions.groupby("category").size()
n_blocking = int(cat_counts.get("BLOCKING", 0))
n_blocking_open = int(
    actions[(actions["category"] == "BLOCKING") & (actions["status"] != "DONE")].shape[0]
)
n_docs = int(cat_counts.get("DOCS", 0))
n_monitoring = int(cat_counts.get("MONITORING", 0))
n_shadow = int(cat_counts.get("SHADOW", 0))

col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
col1.metric("الإجمالي", total)
col2.metric("معلّق", n_open)
col3.metric("قيد التنفيذ", n_in_progress)
col4.metric("تم", n_done)
col5.metric("BLOCKING", f"{n_blocking_open}/{n_blocking}", help="مفتوح/الإجمالي")
col6.metric("DOCS", n_docs)
col7.metric("MONITORING", n_monitoring)

st.divider()


# ── Filters ──────────────────────────────────────────────────────────────────
st.markdown("### الفلاتر")
fc1, fc2, fc3, fc4 = st.columns([1, 1, 1, 2])

phase_options = sorted([int(x) for x in actions["blocking_phase"].dropna().unique()])
phase_filter = fc1.multiselect(
    "المرحلة", options=phase_options + ["بدون مرحلة"], default=[], key="ai_phase"
)

category_options = sorted(actions["category"].dropna().unique())
category_filter = fc2.multiselect(
    "الفئة", options=category_options, default=[], key="ai_cat"
)

status_options = ["OPEN", "IN_PROGRESS", "DONE"]
default_status = ["OPEN", "IN_PROGRESS"]
status_filter = fc3.multiselect(
    "الحالة", options=status_options, default=default_status, key="ai_status"
)

search = fc4.text_input(
    "بحث في العنوان أو الوصف", value="", key="ai_search"
).strip().lower()


# ── Apply filters ────────────────────────────────────────────────────────────
filtered = actions.copy()
if phase_filter:
    keep_no_phase = "بدون مرحلة" in phase_filter
    numeric_phases = [p for p in phase_filter if p != "بدون مرحلة"]
    mask = filtered["blocking_phase"].isin(numeric_phases)
    if keep_no_phase:
        mask = mask | filtered["blocking_phase"].isna()
    filtered = filtered[mask]
if category_filter:
    filtered = filtered[filtered["category"].isin(category_filter)]
if status_filter:
    filtered = filtered[filtered["status"].isin(status_filter)]
if search:
    mask = (
        filtered["title"].str.lower().str.contains(search, na=False)
        | filtered["description"].str.lower().str.contains(search, na=False)
    )
    filtered = filtered[mask]

st.caption(f"عدد البنود بعد الفلترة: {len(filtered)} من أصل {total}")


# ── Main table (clickable row → detail panel below) ──────────────────────────
st.markdown("### القائمة")

if filtered.empty:
    st.info("لا توجد بنود مطابقة للفلاتر.")
else:
    display = filtered[
        ["action_id", "category", "title", "blocking_phase", "status",
         "created_date", "source"]
    ].copy()
    display.columns = ["ID", "الفئة", "العنوان", "المرحلة", "الحالة", "أُنشئ", "المصدر"]
    # Render with style — color the status / category
    def _style_status(v):
        return {
            "OPEN": "color: #EF5350; font-weight: bold",
            "IN_PROGRESS": "color: #42A5F5; font-weight: bold",
            "DONE": "color: #4CAF50",
        }.get(v, "")
    def _style_category(v):
        return {
            "BLOCKING": "color: #EF5350",
            "DOCS": "color: #888",
            "MONITORING": "color: #FFCA28",
            "SHADOW": "color: #42A5F5",
            "POST_MEETING": "color: #9C27B0",
        }.get(v, "")
    styled = display.style.map(_style_status, subset=["الحالة"]).map(
        _style_category, subset=["الفئة"]
    ).format({"المرحلة": lambda x: "—" if pd.isna(x) else str(int(x))})
    st.dataframe(styled, hide_index=True, width="stretch")


st.divider()

# ── Detail panel (select an ID to view full info) ────────────────────────────
st.markdown("### تفاصيل البند")
ids = filtered["action_id"].tolist() if not filtered.empty else actions["action_id"].tolist()
selected = st.selectbox(
    "اختر البند لعرض التفاصيل",
    options=[None] + ids,
    format_func=lambda x: "— اختر بندًا —" if x is None else x,
    key="ai_detail_select",
)

if selected:
    row = actions[actions["action_id"] == selected].iloc[0]
    cat_color = {
        "BLOCKING": "#EF5350", "DOCS": "#888",
        "MONITORING": "#FFCA28", "SHADOW": "#42A5F5",
        "POST_MEETING": "#9C27B0",
    }.get(row["category"], "#888")
    status_color = {
        "OPEN": "#EF5350", "IN_PROGRESS": "#42A5F5",
        "DONE": "#4CAF50",
    }.get(row["status"], "#888")

    st.markdown(
        f"""
        <div style="background:#12151C;border:1px solid #2D3748;border-left:4px solid {cat_color};
                    border-radius:8px;padding:14px 18px;margin-bottom:12px">
            <div style="font-size:12px;color:#888;font-weight:600;letter-spacing:0.5px">
                {row['action_id']} ·
                <span style="color:{cat_color}">{row['category']}</span> ·
                <span style="color:{status_color}">{row['status']}</span>
                {f"· Phase {int(row['blocking_phase'])}" if pd.notna(row['blocking_phase']) else ""}
            </div>
            <div style="font-size:18px;color:#FFF;font-weight:700;margin-top:6px">
                {row['title']}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Description
    if pd.notna(row["description"]) and row["description"]:
        st.markdown("**الوصف**")
        st.write(row["description"])

    # Notes
    if pd.notna(row["notes"]) and row["notes"]:
        st.markdown("**ملاحظات**")
        st.write(row["notes"])

    # Metadata
    md_c1, md_c2, md_c3 = st.columns(3)
    with md_c1:
        st.markdown("**أُنشئ**")
        st.caption(str(row["created_date"]) if pd.notna(row["created_date"]) else "—")
    with md_c2:
        st.markdown("**موعد الاستحقاق**")
        st.caption(str(row["due_date"]) if pd.notna(row["due_date"]) else "—")
    with md_c3:
        st.markdown("**المصدر**")
        st.caption(str(row["source"]) if pd.notna(row["source"]) else "—")

    if row["status"] == "DONE" and pd.notna(row["completed_date"]):
        st.caption(f"اكتمل: {row['completed_date']}")

    # Status history (if table populated for this item)
    history = _load_status_history(selected)
    if not history.empty:
        with st.expander("سجل التحوّلات (status_history)"):
            st.dataframe(history, hide_index=True, width="stretch")


# Refresh
st.divider()
if st.button("تحديث البيانات", use_container_width=False):
    st.cache_data.clear()
    st.rerun()
