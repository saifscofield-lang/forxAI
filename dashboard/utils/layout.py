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
