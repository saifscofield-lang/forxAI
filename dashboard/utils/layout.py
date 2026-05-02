"""Shared layout widgets for the redesigned dashboard.

Per dashboard_redesign_proposal.md: every tab shows a top status strip
with phase / days-to-gate / engine state. This module owns that strip
and any other widgets that span multiple tabs."""
from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st

IMP_DB = "data/improvements.db"
TRADING_DB = "data/trading.db"
PAPER_LOG = "data/logs/paper_trading.log"

# Phase 8 gate (Jun 1) is the next formal gate; Sep 1 is Phase 9 target.
PHASE_8_GATE = date(2026, 6, 1)
PHASE_9_TARGET = date(2026, 9, 1)

# Short Arabic purpose for each phase — what this phase tries to accomplish.
# Used by the dashboard's phase cards. project_phases.name_ar already holds
# the Arabic title; this dict adds a one-line explanation for non-technical
# reading. Keep each value short (one line) — long context stays in notes.
PHASE_PURPOSES_AR = {
    0: "تأسيس البنية التحتية الأساسية — مؤشرات، استراتيجيات، إدارة مخاطر، محرّك تنفيذ",
    1: "أول إصدار قابل للتشغيل لجمع بيانات حقيقية وتثبيت الواجهة الأساسية",
    2: "(مهجورة) — حلّت محلها مراحل v3.0 منذ 17 أبريل 2026",
    3: "(مهجورة) — حلّت محلها مراحل v3.0 منذ 17 أبريل 2026",
    4: "(مهجورة) — حلّت محلها مراحل v3.0 منذ 17 أبريل 2026",
    5: "تحضير البيانات + اختيار الميزات + بناء أوّلي قبل بناء v3.0 الكامل",
    6: "بناء استراتيجية زخم اتجاه السلسلة الزمنية (TSMOM) كطبقة مستقلة موازية",
    7: "بناء فلتر تعلّم آلي (Meta-Labeler) يحدّد جودة الإشارات قبل تنفيذها",
    8: "تشغيل النظام الكامل على حساب تجريبي مدّة 6 أسابيع لإثبات الجدوى قبل الحقيقي",
    9: "إطلاق رأس مال صغير حقيقي ($2,000) + معالجة فجوات الانزلاق والعمولة والأخبار",
    10: "اختبار TSMOM على العملات الرقمية (BTC/ETH/BNB/SOL) — رُفِض في 22 أبريل (نتيجة سلبية)",
    11: "إضافة 4-5 استراتيجيات متعددة الأصول غير مرتبطة: crypto، commodity، VIX",
    12: "الانتقال من MT5 إلى بنية متعددة الأصول: IBKR + ccxt + TimescaleDB + Grafana",
    13: "اختبار v4 ورقياً ≥ 90 يوماً مع walk-forward + Purged CV لكل استراتيجية",
    14: "إطلاق v4 على حساب حقيقي ($5-10K)، توسيع تدريجي مع تأكيد Sharpe",
    105: "محاولة إنقاذ Phase 10 بإضافة فلتر نظام (regime filter) — لم تنجح، أُغلقت",
}


def phase_purpose_ar(phase_number: int) -> str:
    """Return the short Arabic purpose for a phase. Empty string if not known."""
    return PHASE_PURPOSES_AR.get(int(phase_number), "")


def phase_display_name(name: str, name_ar: str | None) -> str:
    """Prefer the Arabic name when populated; fall back to English."""
    if name_ar and name_ar.strip() and not name_ar.strip().startswith("Phase "):
        return name_ar
    return name


@st.cache_data(ttl=60, show_spinner=False)
def _engine_state_from_log() -> dict:
    """Tail paper_trading.log to infer engine state.

    The dashboard cannot read the engine's in-memory pause flag, so the
    next-best signal is the most recent scan-related log line."""
    try:
        with open(PAPER_LOG, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 16384))
            tail = f.read().decode("utf-8", errors="ignore")
    except Exception:
        return {"marker": None, "age_min": None, "scan_no": None}
    lines = tail.splitlines()[-200:]
    marker, ts, scan_no = None, None, None
    for line in reversed(lines):
        if "Trading paused via /pause" in line:
            marker = "paused"
        elif "complete" in line and "Scan #" in line:
            marker = "active"
            try:
                scan_no = int(line.split("Scan #")[1].split()[0])
            except Exception:
                pass
        elif "Scan #" in line and " at " in line:
            marker = "scanning"
        else:
            continue
        try:
            ts = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
        break
    age_min = (
        (datetime.now() - ts).total_seconds() / 60 if ts else None
    )
    return {"marker": marker, "age_min": age_min, "scan_no": scan_no, "ts": ts}


@st.cache_data(ttl=60, show_spinner=False)
def _current_phase() -> dict:
    """Pick the phase to display in the status strip.

    Priority: IN_PROGRESS phases first (lowest phase_number), then
    KICKOFF / next-up phase, then most recently completed."""
    try:
        con = sqlite3.connect(IMP_DB)
        rows = con.execute(
            "SELECT phase_number, name, status, started_at, completed_at "
            "FROM project_phases ORDER BY phase_number"
        ).fetchall()
        con.close()
    except Exception:
        return {"number": None, "name": "?", "status": "?"}
    if not rows:
        return {"number": None, "name": "?", "status": "?"}
    in_progress = [r for r in rows if r[2] == "IN_PROGRESS"]
    if in_progress:
        r = min(in_progress, key=lambda x: x[0])
    else:
        not_started = [r for r in rows if r[2] == "NOT_STARTED" and r[0] < 100]
        r = min(not_started, key=lambda x: x[0]) if not_started else rows[-1]
    return {
        "number": r[0], "name": r[1], "status": r[2],
        "started_at": r[3], "completed_at": r[4],
    }


def status_header() -> None:
    """Render the always-visible top strip.

    Layout: timestamp · current phase · days-to-gate · engine marker.
    Called at the top of every tab. Rendered in Arabic; data values in
    English/numeric (no script-mixing per project policy)."""
    now = datetime.utcnow()
    eng = _engine_state_from_log()
    ph = _current_phase()
    days_to_gate = (PHASE_8_GATE - date.today()).days
    days_to_live = (PHASE_9_TARGET - date.today()).days

    # Engine marker text + colour
    if eng.get("marker") == "paused":
        eng_label, eng_color = "موقوف", "#FFCA28"
    elif eng.get("marker") in ("active", "scanning"):
        if eng.get("age_min") and eng["age_min"] > 180:
            eng_label, eng_color = "صامت", "#EF5350"
        else:
            eng_label, eng_color = "نشط", "#4CAF50"
    else:
        eng_label, eng_color = "غير معروف", "#888"

    age_txt = (
        f"آخر مسح قبل {eng['age_min']:.0f} دقيقة"
        if eng.get("age_min") is not None else "—"
    )
    scan_txt = f"#{eng['scan_no']}" if eng.get("scan_no") else ""

    # Single-line strip — RTL friendly. Use four columns for visual rhythm.
    st.markdown(
        f"""
        <div style="background:#0D1117;border:1px solid #1E2130;border-radius:8px;
                    padding:8px 14px;margin-bottom:14px;
                    display:flex;justify-content:space-between;align-items:center;
                    font-size:12px;color:#AAA">
            <span><b style="color:#FFF">ForexAI Dashboard</b>
                  · آخر تحديث {now.strftime('%H:%M')} UTC</span>
            <span>المرحلة الحالية: <b style="color:#FFF">Phase {ph['number']}</b>
                  · {ph['name']} · <i>{ph['status']}</i></span>
            <span>أيام حتى بوابة 1 يونيو:
                  <b style="color:{'#EF5350' if days_to_gate<=14 else ('#FFCA28' if days_to_gate<=30 else '#FFF')}">
                  {days_to_gate}</b></span>
            <span>المحرّك: <b style="color:{eng_color}">{eng_label}</b>
                  {scan_txt} · {age_txt}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_intro(arabic_title: str, arabic_subtitle: str = "") -> None:
    """Standardised page header below the status strip."""
    st.markdown(
        f"""
        <div style="margin-bottom:14px">
            <div style="font-size:22px;font-weight:800;color:#FFF">{arabic_title}</div>
            <div style="font-size:13px;color:#888;margin-top:2px">{arabic_subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
