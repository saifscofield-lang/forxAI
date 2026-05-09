"""ForexAI Dashboard — Main entry point + Tab 1 (Where are we?).

Tabs (in sidebar order, all under dashboard/pages/):
  1. Where are we?  (this file — home / status overview)
  2. Action Items   (pages/1_action_items.py)
  3. Decisions      (pages/2_decisions.py)
  4. Risks          (pages/3_risks.py)
  5. Trading        (pages/4_trading.py)
  6. Documents      (pages/5_documents.py)

Run: streamlit run dashboard/app.py
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import sqlite3
from datetime import date, datetime, timezone

import pandas as pd
import streamlit as st

from dashboard.utils.layout import (
    IMP_DB, PHASE_8_GATE, PHASE_9_TARGET,
    page_intro, status_header,
    phase_purpose_ar, phase_display_name,
)


# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ForexAI Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "ForexAI — Algorithmic Forex Trading Platform"},
)


# ── Professional CSS ─────────────────────────────────────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 0.5rem; max-width: 1400px; }
    div[data-testid="metric-container"] {
        background: linear-gradient(135deg, #1A1F2E 0%, #151A28 100%);
        border: 1px solid #2D3748;
        border-radius: 10px;
        padding: 14px 18px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }
    div[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0D1117 0%, #0A0E14 100%);
    }
    div[data-testid="stSidebar"] [data-testid="stMarkdown"] h2 {
        font-size: 1.3rem;
        letter-spacing: 0.5px;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 8px 20px;
        font-weight: 500;
    }
    div[data-testid="stAlert"] { border-radius: 8px; }
    hr { border-color: #1E2130 !important; margin: 0.8rem 0 !important; }
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
    .js-plotly-plot, .stDataFrame, table,
    div[data-testid="metric-container"] [data-testid="stMetricValue"],
    code, pre, .stCodeBlock {
        direction: ltr;
        text-align: left;
    }
    .streamlit-expanderHeader { font-weight: 600; }
</style>
""", unsafe_allow_html=True)


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="text-align:center;padding:10px 0 5px 0">
        <div style="font-size:28px;font-weight:800;letter-spacing:1px;color:#1E88E5">ForexAI</div>
        <div style="font-size:12px;color:#666;margin-top:2px">Algorithmic Trading Platform</div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # MT5 status
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

    # Market status
    now_utc = datetime.now(timezone.utc)
    weekday, hour = now_utc.weekday(), now_utc.hour
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
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;font-size:13px">
        <span style="color:#888">السوق</span>
        <span style="color:{market_color};font-weight:600">{market_text}</span>
    </div>
    """, unsafe_allow_html=True)
    if market_open and sessions:
        st.caption(f"الجلسات: {' | '.join(sessions)}")

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

    # News alerts (next 4h, high-impact only)
    from dashboard.utils.db import get_upcoming_news
    upcoming = get_upcoming_news(hours_ahead=4)
    if not upcoming.empty:
        high = upcoming[upcoming["impact"] == "HIGH"]
        if not high.empty:
            st.warning(f"{len(high)} أخبار عالية التأثير قادمة")
            for _, row in high.iterrows():
                t = row["time"].strftime("%H:%M") if hasattr(row["time"], "strftime") else str(row["time"])
                st.caption(f"  {t} -- {row['currency']} -- {row['event_name']}")
    else:
        st.markdown(
            '<div style="color:#4CAF50;font-size:13px;padding:4px 0">لا أخبار مؤثرة قريبة</div>',
            unsafe_allow_html=True,
        )

    st.divider()
    st.caption(f"{now_utc.strftime('%H:%M:%S')} UTC")
    if st.button("تحديث البيانات", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ── Main content — Tab 1 (Where are we?) ─────────────────────────────────────
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
            "SELECT phase_number, name, name_ar, status, started_at, completed_at "
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
        sub = ""
        if int(ph["phase_number"]) == 8:
            d = (PHASE_8_GATE - date.today()).days
            sub = f"بوابة 1 يونيو · {d} يوم"
        elif int(ph["phase_number"]) == 9:
            d = (PHASE_9_TARGET - date.today()).days
            sub = f"هدف 1 سبتمبر · {d} يوم"
        elif n_total > 0:
            sub = f"{n_done}/{n_total} خطوات"
        display = phase_display_name(ph["name"], ph.get("name_ar"))
        purpose = phase_purpose_ar(int(ph["phase_number"]))
        with col:
            st.markdown(
                f"""
                <div style="background:#12151C;border:1px solid #2D3748;
                            border-left:4px solid {clr};border-radius:8px;
                            padding:12px 14px;min-height:170px">
                    <div style="font-size:11px;color:#888;font-weight:600">
                        Phase {int(ph['phase_number'])}
                    </div>
                    <div style="font-size:14px;color:#FFF;font-weight:700;margin:4px 0 6px 0">
                        {display}
                    </div>
                    <div style="font-size:11px;color:{clr};font-weight:700">
                        {ph['status']}
                    </div>
                    <div style="font-size:11px;color:#AAA;margin-top:4px">
                        {sub}
                    </div>
                    <div style="font-size:11px;color:#999;margin-top:8px;
                                line-height:1.5;border-top:1px solid #2D3748;padding-top:6px">
                        {purpose}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

# ── All-phases overview (collapsible) ────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _all_phases_full():
    try:
        con = sqlite3.connect(IMP_DB)
        df = pd.read_sql(
            "SELECT phase_number, name, name_ar, status FROM project_phases "
            "ORDER BY CASE WHEN phase_number = 105 THEN 10.5 "
            "ELSE phase_number END",
            con,
        )
        con.close()
        return df
    except Exception:
        return pd.DataFrame()


def _is_archived_phase(ph_num: int, status: str, notes: str | None) -> bool:
    """Phase counts as archived when superseded, completed, or in the v1
    legacy band (0-4). v3 active band (5-9) and v4 future band (11-14)
    stay in the active list even when individual phases are completed/deferred."""
    notes_l = (notes or "").lower()
    if "supersed" in notes_l or "superseded" in notes_l:
        return True
    if ph_num in (0, 1, 2, 3, 4):       # v1 legacy — always archived
        return True
    if ph_num in (10, 105):             # v4 research closed
        return True
    if status == "COMPLETED" and ph_num not in (6, 7, 8, 9):
        return True
    return False


@st.cache_data(ttl=300, show_spinner=False)
def _all_phases_with_notes():
    try:
        con = sqlite3.connect(IMP_DB)
        df = pd.read_sql(
            "SELECT phase_number, name, name_ar, status, notes FROM project_phases "
            "ORDER BY CASE WHEN phase_number = 105 THEN 10.5 ELSE phase_number END",
            con,
        )
        con.close()
        return df
    except Exception:
        return pd.DataFrame()


def _render_phase_card(ph, status_color_full):
    ph_num = int(ph["phase_number"])
    ph_label = "10.5" if ph_num == 105 else str(ph_num)
    clr = status_color_full.get(ph["status"], "#888")
    display_name = phase_display_name(ph["name"], ph.get("name_ar"))
    purpose = phase_purpose_ar(ph_num)
    st.markdown(
        f"""
        <div style="background:#12151C;border-left:3px solid {clr};
                    border-radius:6px;padding:8px 14px;margin-bottom:6px">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <div>
                    <span style="font-size:11px;color:#888;font-weight:600">
                        Phase {ph_label}
                    </span>
                    <span style="font-size:13px;color:#FFF;font-weight:700;margin-right:8px">
                        {display_name}
                    </span>
                </div>
                <span style="font-size:11px;color:{clr};font-weight:700">
                    {ph['status']}
                </span>
            </div>
            <div style="font-size:11px;color:#AAA;margin-top:4px;line-height:1.5">
                {purpose if purpose else '—'}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


status_color_full = {
    "IN_PROGRESS": "#42A5F5", "NOT_STARTED": "#888",
    "DEFERRED": "#FFCA28", "COMPLETED": "#4CAF50",
    "PENDING_ACTIVATION": "#9C27B0",
}

with st.expander("📋 المراحل النشطة — v3 (5-9) و v4 (11-14)"):
    st.caption(
        "المراحل قيد العمل أو المُخطَّطة. v3 = المسار الإنتاجي الحالي. "
        "v4 = توسعات مستقبلية (multi-asset). الأرشيف للمراحل المُستبدَلة في الأسفل."
    )
    full = _all_phases_with_notes()
    if full.empty:
        st.warning("تعذّر تحميل المراحل.")
    else:
        active = full[~full.apply(
            lambda r: _is_archived_phase(int(r["phase_number"]), r["status"], r.get("notes")),
            axis=1
        )]
        for _, ph in active.iterrows():
            _render_phase_card(ph, status_color_full)


# ── Complete plan tree — phase + step level ──────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def _all_steps_for_active_phases():
    try:
        con = sqlite3.connect(IMP_DB)
        df = pd.read_sql(
            "SELECT phase_number, step_order, description, description_ar, "
            "status, completed_at, notes "
            "FROM phase_steps "
            "WHERE phase_number IN (5,6,7,8,9,11,12,13,14) "
            "ORDER BY phase_number, step_order",
            con,
        )
        con.close()
        return df
    except Exception:
        return pd.DataFrame()


with st.expander("🌳 خطة كاملة بمستوى الخطوات (Phase + Step)"):
    st.caption(
        "كل المراحل النشطة مع جميع خطواتها. اللون يعكس الحالة. "
        "خطوات المراحل المؤرشفة لا تظهر هنا — افتح قسم الأرشيف للمزيد."
    )
    steps_df = _all_steps_for_active_phases()
    if steps_df.empty:
        st.warning("تعذّر تحميل خطوات الخطة.")
    else:
        step_color = {
            "COMPLETED": "#4CAF50", "IN_PROGRESS": "#42A5F5",
            "PENDING": "#888", "BLOCKED": "#EF5350",
            "DEFERRED": "#FFCA28", "RESCOPED": "#9C27B0",
            "CANCELLED": "#666", "SKIPPED": "#666",
        }
        # Group by phase, render each as a sub-section
        for ph_num, ph_steps in steps_df.groupby("phase_number"):
            ph_num = int(ph_num)
            ph_label = "10.5" if ph_num == 105 else str(ph_num)
            n_total = len(ph_steps)
            n_done = int((ph_steps["status"] == "COMPLETED").sum())
            n_blocked = int(ph_steps["status"].isin(["BLOCKED","DEFERRED","RESCOPED"]).sum())
            block_text = f" · {n_blocked} محجوب/مؤجَّل" if n_blocked else ""
            st.markdown(
                f"<div style='margin-top:10px;font-size:13px;color:#42A5F5;font-weight:700'>"
                f"Phase {ph_label} — {n_done}/{n_total} مكتمل{block_text}</div>",
                unsafe_allow_html=True,
            )
            for _, st_row in ph_steps.iterrows():
                clr = step_color.get(st_row["status"], "#888")
                desc = st_row.get("description_ar") or st_row["description"] or "—"
                desc = (desc[:120] + "…") if len(desc) > 120 else desc
                done_badge = ""
                if st_row["completed_at"]:
                    done_badge = (
                        f"<span style='font-size:10px;color:#4CAF50;margin-right:6px'>"
                        f"✓ {st_row['completed_at']}</span>"
                    )
                notes_summary = ""
                if st_row.get("notes"):
                    n = str(st_row["notes"])
                    notes_summary = (n[:140] + "…") if len(n) > 140 else n
                st.markdown(
                    f"""
                    <div style="background:#0D1117;border-left:2px solid {clr};
                                border-radius:4px;padding:6px 10px;margin:3px 0 3px 18px">
                        <div style="display:flex;justify-content:space-between;align-items:center">
                            <span style="font-size:12px;color:#FFF">
                                <span style="color:#888">#{st_row['step_order']}</span> {desc}
                            </span>
                            <span>{done_badge}<span style="font-size:10px;color:{clr};font-weight:700">{st_row['status']}</span></span>
                        </div>
                        {f"<div style='font-size:10px;color:#888;margin-top:3px;line-height:1.4'>{notes_summary}</div>" if notes_summary else ""}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# ── Archived phases (collapsed by default) ──────────────────────────────────
with st.expander("📦 الأرشيف — مراحل مُستبدَلة أو مُغلقة (v1 + v4 research)"):
    st.caption(
        "مراحل لم تعد قيد العمل: v1 (0-4) استُبدِلت بـ v3 في 17 أبريل 2026؛ "
        "Phase 10 و 10.5 (أبحاث crypto momentum) أُغلقت في أبريل 2026."
    )
    full = _all_phases_with_notes()
    if not full.empty:
        archived = full[full.apply(
            lambda r: _is_archived_phase(int(r["phase_number"]), r["status"], r.get("notes")),
            axis=1
        )]
        if archived.empty:
            st.info("لا توجد مراحل مؤرشفة.")
        else:
            for _, ph in archived.iterrows():
                _render_phase_card(ph, status_color_full)

st.divider()


# ── Top 5 blocking action items ──────────────────────────────────────────────
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


# ── Phase plan progress (steps closed in the last 7 days) ───────────────────
@st.cache_data(ttl=120, show_spinner=False)
def _recent_phase_steps():
    try:
        con = sqlite3.connect(IMP_DB)
        df = pd.read_sql(
            "SELECT phase_number, step_order, status, completed_at, "
            "substr(description, 1, 100) AS description "
            "FROM phase_steps "
            "WHERE status = 'COMPLETED' AND completed_at IS NOT NULL "
            "AND completed_at >= date('now', '-7 days') "
            "ORDER BY completed_at DESC, phase_number, step_order",
            con,
        )
        con.close()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner=False)
def _phase_progress_summary():
    """Per-phase {done, total} for the active phases."""
    try:
        con = sqlite3.connect(IMP_DB)
        rows = con.execute(
            "SELECT phase_number, "
            "SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) AS done, "
            "COUNT(*) AS total "
            "FROM phase_steps GROUP BY phase_number ORDER BY phase_number"
        ).fetchall()
        con.close()
        return [(int(r[0]), int(r[1]), int(r[2])) for r in rows]
    except Exception:
        return []


_recent_steps = _recent_phase_steps()
if not _recent_steps.empty:
    st.markdown("### 📈 تقدّم الخطة هذا الأسبوع")
    progress = _phase_progress_summary()
    progress_active = [(n, d, t) for n, d, t in progress if n in (6, 7) and t > 0]
    if progress_active:
        cols = st.columns(len(progress_active))
        for col, (ph_num, done, total) in zip(cols, progress_active):
            pct = (done / total * 100) if total else 0
            color = "#4CAF50" if pct >= 75 else "#42A5F5" if pct >= 25 else "#888"
            col.markdown(
                f"<div style='background:#12151C;border:1px solid #2D3748;"
                f"border-left:4px solid {color};border-radius:8px;padding:10px 14px'>"
                f"<div style='font-size:11px;color:#888;font-weight:600'>Phase {ph_num} plan</div>"
                f"<div style='font-size:18px;color:#FFF;font-weight:700;margin:4px 0'>"
                f"{done} / {total} <span style='font-size:12px;color:{color}'>({pct:.0f}%)</span></div>"
                f"<div style='background:#0D1117;border-radius:4px;height:6px;overflow:hidden'>"
                f"<div style='background:{color};height:6px;width:{pct:.0f}%'></div>"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.caption(f"خطوات أُنجزت في آخر 7 أيام ({len(_recent_steps)} خطوة):")
    for _, row in _recent_steps.head(8).iterrows():
        st.markdown(
            f"<div style='background:#12151C;border-left:3px solid #4CAF50;"
            f"border-radius:6px;padding:6px 12px;margin-bottom:4px;font-size:12px'>"
            f"<span style='color:#888;font-weight:600'>P{int(row['phase_number'])} · "
            f"Step {int(row['step_order'])}</span> · "
            f"<span style='color:#4CAF50;font-size:11px'>{row['completed_at']}</span>"
            f"<div style='color:#DDD;font-size:12px;margin-top:2px'>{row['description']}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    st.divider()


# ── Last 3 decisions ─────────────────────────────────────────────────────────
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


# ── Recent activity (items completed in the last 7 days) ─────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def _recent_completions():
    try:
        con = sqlite3.connect(IMP_DB)
        df = pd.read_sql(
            "SELECT action_id, category, title, blocking_phase, completed_date "
            "FROM action_items "
            "WHERE status = 'DONE' AND completed_date IS NOT NULL "
            "AND completed_date >= date('now', '-7 days') "
            "ORDER BY completed_date DESC, action_id LIMIT 5",
            con,
        )
        con.close()
        return df
    except Exception:
        return pd.DataFrame()


_recent = _recent_completions()
if not _recent.empty:
    st.markdown("### ✅ آخر التحديثات (آخر 7 أيام)")
    for _, it in _recent.iterrows():
        ph = (
            f"<span style='background:#1A1F2E;color:#AAA;border:1px solid #2D3748;"
            f"border-radius:4px;padding:1px 6px;font-size:11px;margin-right:6px'>"
            f"Phase {int(it['blocking_phase'])}</span>"
            if pd.notna(it["blocking_phase"]) else ""
        )
        st.markdown(
            f"""
            <div style="background:#12151C;border-left:3px solid #4CAF50;
                        border-radius:6px;padding:8px 12px;margin-bottom:6px">
                <div style="font-size:11px;color:#4CAF50;font-weight:700">
                    {it['action_id']} · DONE · {it['completed_date']} {ph}
                </div>
                <div style="color:#DDD;font-size:13px;margin-top:2px">
                    {it['title']}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.caption("← التفاصيل في تبويب «بنود التنفيذ»")
    st.divider()


# ── Engine health snapshot ───────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def _engine_health():
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
    try:
        con = sqlite3.connect("data/trading.db")
        n_open = con.execute("SELECT COUNT(*) FROM trades WHERE is_closed=0").fetchone()[0]
        con.close()
        info["n_open"] = n_open
    except Exception:
        info["n_open"] = None
    try:
        with open("data/logs/paper_trading.log", "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 65536))
            tail = f.read().decode("utf-8", errors="ignore")
        cfg_lines = [ln for ln in tail.splitlines() if "[CONFIG]" in ln]
        info["last_config"] = cfg_lines[-1] if cfg_lines else None
        # AI-004b: parse the most recent [CONFIG PARITY] / [CONFIG ALL] /
        # [CONFIG PARITY MISMATCH] line so the dashboard surfaces parity
        # status without re-reading the yaml files itself.
        parity_lines = [
            ln for ln in tail.splitlines()
            if "[CONFIG PARITY" in ln or "[CONFIG ALL]" in ln
        ]
        info["last_parity"] = parity_lines[-1] if parity_lines else None
        # Short status verdict for the tile
        if info["last_parity"] is None:
            info["parity_verdict"] = "—"  # AI-004b not active yet
        elif "MISMATCH" in info["last_parity"]:
            info["parity_verdict"] = "mismatch"
        elif "[CONFIG PARITY]" in info["last_parity"] and "matches between" in info["last_parity"]:
            info["parity_verdict"] = "match"
        elif "loaded config is base.yaml" in info["last_parity"]:
            info["parity_verdict"] = "self"
        elif "base.yaml unreadable" in info["last_parity"]:
            info["parity_verdict"] = "unavailable"
        else:
            info["parity_verdict"] = "unknown"
    except Exception:
        info["last_config"] = None
        info["last_parity"] = None
        info["parity_verdict"] = "—"
    return info


# Running processes — engine, scheduler, dashboard ──────────────────────────
# Surfaces "what's actually running on this machine for forexAI" so you don't
# need to alt-tab through cmd windows. Three checks: engine python.exe count,
# Windows Task Scheduler entries (TSMOM daily), and the streamlit dashboard
# itself (which is rendering this page right now, so always at least 1).
@st.cache_data(ttl=30, show_spinner=False)
def _running_processes() -> dict:
    import subprocess
    info = {"engine": -1, "scheduler_state": "—", "scheduler_last_run": "—",
            "scheduler_next_run": "—", "scheduler_last_result": "—"}
    # Engine count via the same wmic filter the watchdog uses
    try:
        result = subprocess.run(
            ["wmic", "process", "where",
             "Name='python.exe' and CommandLine like '%paper_trade.py%' "
             "and ExecutablePath like '%forexAI%'",
             "get", "ProcessId"],
            capture_output=True, text=True, timeout=8,
        )
        info["engine"] = sum(1 for ln in result.stdout.splitlines() if ln.strip().isdigit())
    except Exception:
        pass
    # Task Scheduler — TSMOM daily entry
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/tn", "ForexAI_TSMOM_Daily", "/fo", "LIST", "/v"],
            capture_output=True, text=True, timeout=8,
        )
        for ln in result.stdout.splitlines():
            ln_l = ln.lower()
            if "status:" in ln_l and "schedul" not in ln_l:  # avoid "Schedule Type"
                info["scheduler_state"] = ln.split(":", 1)[1].strip()
            elif "last run time:" in ln_l:
                info["scheduler_last_run"] = ln.split(":", 1)[1].strip()
            elif "next run time:" in ln_l:
                info["scheduler_next_run"] = ln.split(":", 1)[1].strip()
            elif "last result:" in ln_l:
                info["scheduler_last_result"] = ln.split(":", 1)[1].strip()
    except Exception:
        pass
    return info


st.markdown("### 🖥️ العمليات الجارية")
proc = _running_processes()
pc1, pc2, pc3 = st.columns(3)
with pc1:
    if proc["engine"] > 0:
        st.metric("محرّك التداول", "يعمل", delta=f"{proc['engine']} python.exe", delta_color="off")
    elif proc["engine"] == 0:
        st.metric("محرّك التداول", "متوقّف", delta="نفّذ start.bat", delta_color="inverse")
    else:
        st.metric("محرّك التداول", "—", delta="wmic غير متاح", delta_color="off")
with pc2:
    sched_ok = proc["scheduler_state"] in ("Ready", "Running")
    color = "off" if sched_ok else "inverse"
    label = {"Ready": "جاهز", "Running": "يعمل", "Disabled": "معطّل"}.get(
        proc["scheduler_state"], proc["scheduler_state"]
    )
    st.metric("جدولة TSMOM اليومية", label, delta=proc["scheduler_last_result"], delta_color=color)
    if proc["scheduler_next_run"] != "—":
        st.caption(f"التشغيل التالي: {proc['scheduler_next_run']}")
with pc3:
    st.metric("لوحة التحكّم", "تعمل", delta="streamlit", delta_color="off")
    st.caption("هذه الصفحة")

if proc["scheduler_last_run"] != "—":
    st.caption(f"ℹ️ آخر تشغيل لجدولة TSMOM: {proc['scheduler_last_run']}")

st.divider()


# AI-008: Shadow staleness alert ─────────────────────────────────────────────
# The 6-day shadow outage in 2026-04 went undetected because no surface flagged
# staleness. Tiered thresholds tuned for this engine's actual cadence:
# H1 strategies + ml_direct produce shadow rows roughly once per H1 candle
# (= 60 min), so single-hour gaps are normal. Two consecutive missed candles
# (~120-150 min) is the real "something is wrong" signal.
#
# Threshold history: original implementation used 30 min (audit-suggested
# generic), which fired routinely on this H1-cadence engine. Tuned 2026-05-08
# to 90/150 min after the first false-positive case observed live.
SHADOW_STALE_INFO_MIN = 90    # 1× H1 candle + buffer
SHADOW_STALE_ERROR_MIN = 150  # 2 missed candles — real outage signal


@st.cache_data(ttl=60, show_spinner=False)
def _shadow_staleness():
    try:
        con = sqlite3.connect("data/trading.db")
        row = con.execute(
            "SELECT MAX(time) FROM shadow_signals"
        ).fetchone()
        con.close()
        last_ts = row[0] if row else None
    except Exception:
        last_ts = None
    if not last_ts:
        return {"last_ts": None, "age_min": None}
    try:
        ts = pd.to_datetime(last_ts)
        age_min = (datetime.now(timezone.utc).replace(tzinfo=None) - ts.to_pydatetime()).total_seconds() / 60.0
    except Exception:
        return {"last_ts": str(last_ts), "age_min": None}
    return {"last_ts": str(ts), "age_min": age_min}


def _market_open_now() -> bool:
    now = datetime.now(timezone.utc)
    wd, hr = now.weekday(), now.hour
    if wd == 5: return False
    if wd == 6 and hr < 22: return False
    if wd == 4 and hr >= 22: return False
    return True


_shadow = _shadow_staleness()
_age = _shadow.get("age_min")
_market = _market_open_now()
if _age is None:
    pass  # silent — table empty or query failed; engine-health tile handles
elif _age >= SHADOW_STALE_ERROR_MIN and _market:
    st.error(
        f"🚨 **shadow_signals بدون كتابة منذ {int(_age)} دقيقة** "
        f"(آخر كتابة: {_shadow['last_ts']}، السوق مفتوح، >2 شموع H1 مفقودة). "
        f"تحقق من المحرّك — قد تكون كتابة الإشارات الظلية معطّلة "
        f"(مثل حادثة 6 أيام في أبريل 2026).",
    )
elif _age >= SHADOW_STALE_INFO_MIN and _market:
    st.warning(
        f"⏱️ shadow_signals عمر آخر كتابة {int(_age)} دقيقة (آخر كتابة: "
        f"{_shadow['last_ts']}). شمعة H1 واحدة فُوِّتت — راقب؛ سيصبح خطأ عند "
        f"{SHADOW_STALE_ERROR_MIN} دقيقة."
    )
elif _age >= SHADOW_STALE_INFO_MIN:
    st.caption(
        f"ℹ️ shadow_signals عمر آخر كتابة {int(_age)} دقيقة (السوق مغلق — متوقّع)"
    )

st.markdown("### ⚙️ صحة المحرّك")
h = _engine_health()
c1, c2, c3, c4, c5 = st.columns(5)
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
with c5:
    # AI-004b: cross-config blacklist parity status.
    verdict = h.get("parity_verdict", "—")
    label = {
        "match": "متطابق ✓",
        "mismatch": "تعارض ✗",
        "self": "—",
        "unavailable": "غير متاح",
        "unknown": "غير معروف",
        "—": "—",
    }.get(verdict, "—")
    delta = {
        "match": "configs in sync",
        "mismatch": "FIX REQUIRED",
        "self": "loaded base.yaml",
        "unavailable": "base.yaml unreadable",
    }.get(verdict)
    delta_color = {
        "match": "off", "mismatch": "inverse",
        "self": "off", "unavailable": "off",
    }.get(verdict, "off")
    st.metric(
        "تطابق الإعدادات",
        label,
        delta=delta,
        delta_color=delta_color,
        help=(
            "AI-004b: يقارن قائمة الحظر strategy_blacklist بين paper.yaml و base.yaml "
            "للكشف عن التحرير الذي يهبط في ملف ولا يصل المحرّك (مثل حادثة Apr-10). "
            "يتم تحديثها تلقائياً مع كل سطر [CONFIG PARITY] في السجل."
        ),
    )

if h.get("last_config"):
    st.caption(f"`{h['last_config'][:200]}`")
if h.get("last_parity"):
    st.caption(f"`{h['last_parity'][:200]}`")
elif h.get("last_config"):
    st.caption(
        "ℹ️ AI-004b dormant — سيظهر [CONFIG PARITY] بعد إعادة تشغيل المحرّك."
    )
