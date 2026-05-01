"""Tab 6 — Documents / الوثائق

Filesystem index of docs/research/ and docs/meetings/. Click a row
to expand the first ~80 lines inline, or download the full file.

Per dashboard_redesign_proposal.md. Index, not content."""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.utils.layout import page_intro, status_header

st.set_page_config(page_title="الوثائق — ForexAI", page_icon="📚", layout="wide")
status_header()
page_intro(
    arabic_title="الوثائق",
    arabic_subtitle="فهرس ملفات الأبحاث والاجتماعات — اضغط لعرض المعاينة أو التحميل",
)


# ── Discover files ───────────────────────────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def _discover() -> pd.DataFrame:
    rows = []
    for root, label in [("docs/research", "أبحاث"), ("docs/meetings", "اجتماعات")]:
        p = Path(root)
        if not p.exists():
            continue
        for f in sorted(p.rglob("*"), key=lambda x: x.stat().st_mtime if x.is_file() else 0, reverse=True):
            if not f.is_file():
                continue
            if f.suffix.lower() not in (".md", ".txt", ".html"):
                continue
            try:
                stat = f.stat()
                rows.append({
                    "category": label,
                    "filename": f.name,
                    "path": str(f).replace("\\", "/"),
                    "size_kb": stat.st_size / 1024,
                    "modified": datetime.fromtimestamp(stat.st_mtime),
                })
            except Exception:
                continue
    return pd.DataFrame(rows)


docs = _discover()

if docs.empty:
    st.warning("لا توجد ملفات في docs/research أو docs/meetings.")
    st.stop()


# ── KPI ribbon ───────────────────────────────────────────────────────────────
n_research = int((docs["category"] == "أبحاث").sum())
n_meetings = int((docs["category"] == "اجتماعات").sum())
total_kb = docs["size_kb"].sum()
last_mod = docs["modified"].max()

c1, c2, c3, c4 = st.columns(4)
c1.metric("الإجمالي", len(docs))
c2.metric("أبحاث", n_research)
c3.metric("اجتماعات", n_meetings)
c4.metric("آخر تحديث", last_mod.strftime("%Y-%m-%d"))

st.divider()


# ── Filters ──────────────────────────────────────────────────────────────────
fc1, fc2, fc3 = st.columns([1, 1, 2])
cat_options = sorted(docs["category"].unique())
cat_filter = fc1.multiselect(
    "النوع", options=cat_options, default=[], key="docs_cat"
)
days_back = fc2.selectbox(
    "آخر",
    options=[7, 14, 30, 60, 90, 365, "الكل"],
    index=6,
    format_func=lambda x: "الكل" if x == "الكل" else f"{x} يوم",
    key="docs_days",
)
search = fc3.text_input("بحث في اسم الملف", value="", key="docs_search").strip().lower()

f = docs.copy()
if cat_filter:
    f = f[f["category"].isin(cat_filter)]
if days_back != "الكل":
    cutoff = datetime.now() - pd.Timedelta(days=int(days_back))
    f = f[f["modified"] >= cutoff]
if search:
    f = f[f["filename"].str.lower().str.contains(search, na=False)]

f = f.sort_values("modified", ascending=False).reset_index(drop=True)

st.caption(f"عدد الملفات: {len(f)} من أصل {len(docs)}")
st.divider()


# ── File list ────────────────────────────────────────────────────────────────
if f.empty:
    st.info("لا توجد ملفات مطابقة للفلاتر.")
else:
    for _, row in f.iterrows():
        cat_color = "#42A5F5" if row["category"] == "أبحاث" else "#9C27B0"
        with st.expander(
            f"📄 {row['filename']} · {row['modified'].strftime('%Y-%m-%d')} · {row['size_kb']:.1f} KB"
        ):
            st.markdown(
                f"<div style='font-size:12px;color:#888;margin-bottom:8px'>"
                f"<span style='color:{cat_color};font-weight:600'>{row['category']}</span> · "
                f"<code>{row['path']}</code></div>",
                unsafe_allow_html=True,
            )
            try:
                content = Path(row["path"]).read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                st.error(f"تعذّر قراءة الملف: {e}")
                continue

            preview_lines = content.splitlines()[:80]
            preview = "\n".join(preview_lines)
            truncated = len(content.splitlines()) > 80

            if row["filename"].endswith(".md"):
                st.markdown(preview)
                if truncated:
                    st.caption(
                        f"… عُرضت أول 80 سطر من إجمالي {len(content.splitlines())}. "
                        "اضغط زر التحميل لرؤية الملف كاملاً."
                    )
            else:
                st.code(preview, language=None)
                if truncated:
                    st.caption(f"… {len(content.splitlines()) - 80} سطر إضافي.")

            st.download_button(
                "⬇️ تحميل الملف الكامل",
                data=content,
                file_name=row["filename"],
                key=f"dl_{row['path']}",
            )

# Refresh
st.divider()
if st.button("تحديث البيانات", use_container_width=False):
    st.cache_data.clear()
    st.rerun()
