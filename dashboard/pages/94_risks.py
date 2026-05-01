"""Tab 4 — Risks / المخاطر

All risks_register rows with severity × likelihood matrix and
mitigation text. AI-* references in mitigation are visually
highlighted so the user can cross-reference Tab 2 (Action Items).

Per dashboard_redesign_proposal.md."""
from __future__ import annotations

import re
import sys
sys.path.insert(0, ".")

import sqlite3
import pandas as pd
import streamlit as st

from dashboard.utils.layout import IMP_DB, page_intro, status_header

st.set_page_config(page_title="المخاطر — ForexAI", page_icon="⚠️", layout="wide")
status_header()
page_intro(
    arabic_title="المخاطر",
    arabic_subtitle="سجل المخاطر مع مصفوفة الشدة × الاحتمال وروابط لبنود التخفيف",
)


# ── Load data ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def _load_risks() -> pd.DataFrame:
    try:
        con = sqlite3.connect(IMP_DB)
        df = pd.read_sql(
            "SELECT risk_id, title, description, severity, likelihood, "
            "mitigation, status, identified_date, source "
            "FROM risks_register ORDER BY id",
            con,
        )
        con.close()
        return df
    except Exception as e:
        st.error(f"تعذّر تحميل المخاطر: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner=False)
def _load_action_status_map() -> dict:
    """Map action_id → status, for lighting up linked mitigation refs."""
    try:
        con = sqlite3.connect(IMP_DB)
        rows = con.execute(
            "SELECT action_id, status FROM action_items"
        ).fetchall()
        con.close()
        return dict(rows)
    except Exception:
        return {}


risks = _load_risks()
action_status = _load_action_status_map()

if risks.empty:
    st.info("لا توجد مخاطر مسجلة.")
    st.stop()


# ── KPI ribbon ───────────────────────────────────────────────────────────────
total = len(risks)
n_critical = int((risks["severity"] == "CRITICAL").sum())
n_high = int((risks["severity"] == "HIGH").sum())
n_medium = int((risks["severity"] == "MEDIUM").sum())
n_low = int((risks["severity"] == "LOW").sum())
n_open = int((risks["status"] == "OPEN").sum())

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("الإجمالي", total)
c2.metric("CRITICAL", n_critical)
c3.metric("HIGH", n_high)
c4.metric("MEDIUM", n_medium)
c5.metric("LOW", n_low)
c6.metric("مفتوح", n_open)

st.divider()


# ── Severity × likelihood matrix ─────────────────────────────────────────────
st.markdown("### مصفوفة الشدة × الاحتمال")
sev_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
lik_order = ["HIGH", "MEDIUM", "LOW"]

# Bucket risks by (severity, likelihood)
matrix: dict = {(s, l): [] for s in sev_order for l in lik_order}
for _, r in risks.iterrows():
    key = (r["severity"], r["likelihood"])
    if key in matrix:
        matrix[key].append(r["risk_id"])

# Heat colour by severity × likelihood (qualitative)
def _cell_color(sev: str, lik: str, n: int) -> str:
    if n == 0:
        return "#0D1117"
    if sev in ("CRITICAL",) and lik in ("HIGH", "MEDIUM"):
        return "#3D0C0C"
    if sev == "HIGH" and lik == "HIGH":
        return "#3D0C0C"
    if sev in ("CRITICAL", "HIGH") or lik == "HIGH":
        return "#3D2D0C"
    if sev == "MEDIUM" and lik == "MEDIUM":
        return "#3D2D0C"
    return "#1A1A0C"

# Render as HTML table (stable across Arabic + LTR data)
header = (
    "<tr><th style='padding:6px 10px;color:#888;font-size:11px;text-align:right'>الشدة \\ الاحتمال</th>"
    + "".join(
        f"<th style='padding:6px 10px;color:#888;font-size:11px'>{l}</th>"
        for l in lik_order
    )
    + "</tr>"
)
rows_html = []
for s in sev_order:
    cells = []
    for l in lik_order:
        ids = matrix.get((s, l), [])
        n = len(ids)
        bg = _cell_color(s, l, n)
        ids_str = "<br>".join(ids) if ids else "—"
        cells.append(
            f"<td style='background:{bg};padding:10px;text-align:center;"
            f"border:1px solid #2D3748;color:{'#FFF' if n else '#444'};"
            f"font-size:12px;min-width:120px'>"
            f"<b>{n}</b><br><span style='font-size:11px'>{ids_str}</span></td>"
        )
    rows_html.append(
        f"<tr><th style='background:#0D1117;color:#FFF;padding:8px 10px;font-size:12px;"
        f"text-align:right;border:1px solid #2D3748'>{s}</th>"
        + "".join(cells)
        + "</tr>"
    )

st.markdown(
    f"""
    <table style='border-collapse:collapse;margin:8px 0 16px 0'>
        <thead>{header}</thead>
        <tbody>{''.join(rows_html)}</tbody>
    </table>
    """,
    unsafe_allow_html=True,
)

st.divider()


# ── Risk list (sorted by severity × likelihood descending) ───────────────────
sev_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
lik_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
risks_sorted = risks.assign(
    _sev=risks["severity"].map(sev_rank).fillna(99),
    _lik=risks["likelihood"].map(lik_rank).fillna(99),
).sort_values(["_sev", "_lik"]).drop(columns=["_sev", "_lik"])

st.markdown(f"### قائمة المخاطر ({len(risks_sorted)})")

severity_color = {
    "CRITICAL": "#9C27B0", "HIGH": "#EF5350",
    "MEDIUM": "#FFCA28", "LOW": "#888",
}

ai_pattern = re.compile(r"\b(AI-\d+[a-z]?|GAP-(?:FID|OPS)-\d+|R-EXT-\d+)\b")


def _highlight_actions(text: str) -> str:
    """Replace AI-* / GAP-* / R-EXT-* tokens with coloured spans, status-aware."""
    if not text:
        return ""
    def _repl(match):
        token = match.group(0)
        status = action_status.get(token)
        if status == "DONE":
            color = "#4CAF50"
        elif status == "IN_PROGRESS":
            color = "#42A5F5"
        elif status == "OPEN":
            color = "#FFCA28"
        else:
            color = "#888"
        return (
            f"<span style='background:#1A1F2E;color:{color};border:1px solid #2D3748;"
            f"border-radius:4px;padding:1px 6px;font-family:monospace;font-size:11px'>"
            f"{token}</span>"
        )
    return ai_pattern.sub(_repl, text)


for _, r in risks_sorted.iterrows():
    sev_clr = severity_color.get(r["severity"], "#888")
    lik_chip = (
        f"<span style='color:#888;font-size:11px;margin-right:6px'>"
        f"احتمال: {r['likelihood']}</span>"
    )
    src_chip = (
        f"<span style='color:#666;font-size:11px;margin-right:6px'>"
        f"مصدر: {r['source']}</span>"
    )
    st.markdown(
        f"""
        <div style="background:#12151C;border-left:4px solid {sev_clr};
                    border-radius:6px;padding:12px 14px;margin-bottom:10px">
            <div style="font-size:11px;color:#888;font-weight:600">
                <span style='color:{sev_clr};font-weight:700'>{r['risk_id']}</span> ·
                <span style='color:{sev_clr};font-weight:700'>{r['severity']}</span> · {lik_chip}
                <span style='color:#AAA'>الحالة: {r['status']}</span>
            </div>
            <div style="color:#FFF;font-size:14px;font-weight:700;margin-top:6px">
                {r['title']}
            </div>
            <div style="color:#AAA;font-size:12px;margin-top:6px">
                {r['description']}
            </div>
            <div style="background:#0D1117;border-radius:4px;padding:6px 10px;margin-top:8px;
                        font-size:12px;color:#DDD">
                <b style="color:#4CAF50">التخفيف:</b> {_highlight_actions(r['mitigation'] or '—')}
            </div>
            <div style="margin-top:6px">{src_chip}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.caption(
    "🎯 الكلمات المُلوّنة في حقل التخفيف هي بنود تنفيذ — أخضر = اكتمل، أزرق = قيد التنفيذ، "
    "أصفر = مفتوح. اضغط تبويب «بنود التنفيذ» لرؤية التفاصيل."
)

# Refresh
st.divider()
if st.button("تحديث البيانات", use_container_width=False):
    st.cache_data.clear()
    st.rerun()
