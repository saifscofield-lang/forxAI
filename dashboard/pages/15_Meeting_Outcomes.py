"""Meeting outcomes page — 2026-04-28 v3 go/no-go.
Renders 4 widgets: meeting banner, phase timeline, Phase 8 blockers countdown, risks register.
All data live from improvements.db. No hardcoded vote outcomes."""
import sys
sys.path.insert(0, ".")

import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Meeting Outcomes", page_icon="📋", layout="wide")

# CSS — match Project Tracker styling
st.markdown("""
<style>
    .block-container { padding-top: 1rem; max-width: 1400px; }
    div[data-testid="metric-container"] {
        background: linear-gradient(135deg, #1A1F2E 0%, #151A28 100%);
        border: 1px solid #2D3748;
        border-radius: 10px;
        padding: 14px 18px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }
    .vote-card {
        background: linear-gradient(135deg, #1A1F2E 0%, #151A28 100%);
        border: 1px solid #2D3748;
        border-radius: 12px;
        padding: 14px 18px;
        margin-bottom: 10px;
    }
    .blocker-row {
        background: #12151C;
        border-left: 3px solid #EF5350;
        border-radius: 6px;
        padding: 8px 12px;
        margin-bottom: 6px;
        font-size: 13px;
    }
    .blocker-row-done { border-left-color: #4CAF50; }
    .blocker-row-progress { border-left-color: #FF9800; }
    hr { border-color: #1E2130 !important; margin: 0.8rem 0 !important; }
</style>
""", unsafe_allow_html=True)

IMP_DB = "data/improvements.db"
MEETING_DATE = "2026-04-28"
DECIDED_BY = "meeting_2026_04_28"
GATE_DATE = date(2026, 6, 1)


def conn():
    return sqlite3.connect(IMP_DB)


# ── Header ───────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="display:flex;align-items:baseline;gap:16px;margin-bottom:4px">
    <span style="font-size:26px;font-weight:800;color:#1E88E5">📋 Meeting Outcomes</span>
    <span style="font-size:14px;color:#888">v3 Go/No-Go — {MEETING_DATE}</span>
</div>
""", unsafe_allow_html=True)
st.markdown(
    "<div style='color:#888;font-size:13px;margin-bottom:14px'>"
    "8 votes decided. 7 of 8 aligned with external skeptical review. "
    "Phase 5 → COMPLETE, Phase 6+7 → starting May 4, Phase 8 → DEFERRED to June 1 gate."
    "</div>",
    unsafe_allow_html=True,
)
st.divider()


# ════════════════════════════════════════════════════════════════════════
# WIDGET 1 — Meeting outcomes banner (8-vote table)
# ════════════════════════════════════════════════════════════════════════
st.subheader("Vote outcomes")

with conn() as c:
    votes = pd.read_sql(
        "SELECT phase_number, decision_date, verdict, gates_passed, gates_total, "
        "rationale_en, next_action FROM go_no_go_decisions "
        "WHERE decided_by = ? ORDER BY id",
        c, params=(DECIDED_BY,),
    )

if votes.empty:
    st.warning(f"No votes recorded with decided_by='{DECIDED_BY}'. Run Phase 1 of Post-meeting.md first.")
else:
    # Parse vote-number from rationale prefix "[Vote N]"
    votes["vote"] = votes["rationale_en"].str.extract(r"\[Vote (\d+)\]").astype(int)
    votes = votes.sort_values("vote").reset_index(drop=True)

    summary_cols = st.columns(4)
    n_total = len(votes)
    n_green = (votes["verdict"] == "GREEN").sum()
    n_yellow = (votes["verdict"] == "YELLOW").sum()
    n_red = (votes["verdict"] == "RED").sum()
    summary_cols[0].metric("Total votes", n_total)
    summary_cols[1].metric("🟢 GREEN", int(n_green))
    summary_cols[2].metric("🟡 YELLOW", int(n_yellow))
    summary_cols[3].metric("🔴 RED", int(n_red))

    st.markdown("&nbsp;", unsafe_allow_html=True)

    for _, v in votes.iterrows():
        verdict = v["verdict"]
        color = {"GREEN": "#4CAF50", "YELLOW": "#FFCA28", "RED": "#EF5350"}[verdict]
        bg = {"GREEN": "#0D2818", "YELLOW": "#2B2410", "RED": "#2D1111"}[verdict]
        emoji = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}[verdict]
        gates = ""
        if pd.notna(v["gates_passed"]) and pd.notna(v["gates_total"]):
            gates = f" gates {int(v['gates_passed'])}/{int(v['gates_total'])}"
        # Strip the "[Vote N]" prefix from the displayed rationale
        rationale_display = v["rationale_en"]
        if rationale_display.startswith("["):
            rationale_display = rationale_display.split("] ", 1)[1] if "] " in rationale_display else rationale_display

        st.markdown(
            f"<div class='vote-card' style='border-left:4px solid {color}'>"
            f"<div style='display:flex;gap:14px;align-items:baseline;margin-bottom:6px'>"
            f"<span style='background:{bg};color:{color};border:1px solid {color};"
            f"border-radius:14px;padding:3px 12px;font-weight:700;font-size:12px'>{emoji} {verdict}{gates}</span>"
            f"<span style='color:#FFF;font-size:14px;font-weight:600'>Vote {int(v['vote'])} — Phase {int(v['phase_number'])}</span>"
            f"</div>"
            f"<div style='color:#CCC;font-size:13px;line-height:1.5'>{rationale_display}</div>"
            f"<div style='color:#888;font-size:12px;margin-top:6px'><b>Next:</b> {v['next_action']}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    with st.expander("View external review synthesis (full document)"):
        synthesis_path = Path("docs/research/external_review_2026_04_28.md")
        if synthesis_path.exists():
            st.markdown(synthesis_path.read_text(encoding="utf-8"))
        else:
            st.info(f"Synthesis file not found at {synthesis_path}.")

st.divider()


# ════════════════════════════════════════════════════════════════════════
# WIDGET 2 — Phase Timeline (Gantt-style)
# ════════════════════════════════════════════════════════════════════════
st.subheader("Phase timeline")

# Build phase bars from project_phases + hardcoded conditional Phase 8 / Phase 9 windows
with conn() as c:
    phases_df = pd.read_sql(
        "SELECT phase_number, name, status, started_at, completed_at, notes "
        "FROM project_phases WHERE phase_number IN (5, 6, 7, 8, 9) ORDER BY phase_number",
        c,
    )

# Hardcoded planned windows for phases that haven't started or are conditional
TODAY = pd.Timestamp(date.today())
PLANNED = {
    5: {"start": "2026-04-17", "end": "2026-04-28"},
    6: {"start": "2026-05-04", "end": "2026-06-08"},
    7: {"start": "2026-05-04", "end": "2026-06-01"},
    8: {"start": "2026-06-01", "end": "2026-07-13"},  # conditional, 6 weeks if cleared at gate
    9: {"start": "2026-09-01", "end": "2026-12-01"},  # target window, far-future
}
COLORS = {"COMPLETED": "#4CAF50", "IN_PROGRESS": "#1E88E5", "DEFERRED": "#9E9E9E", "NOT_STARTED": "#555"}

bars = []
for _, p in phases_df.iterrows():
    pn = int(p["phase_number"])
    s_str = p["started_at"] or PLANNED[pn]["start"]
    e_str = p["completed_at"] or PLANNED[pn]["end"]
    bars.append(dict(
        phase=f"Phase {pn} — {p['name'][:50]}",
        start=pd.Timestamp(s_str),
        end=pd.Timestamp(e_str),
        status=p["status"],
        color=COLORS.get(p["status"], "#666"),
    ))

fig = go.Figure()
for b in bars:
    fig.add_trace(go.Bar(
        x=[(b["end"] - b["start"]).days],
        y=[b["phase"]],
        base=b["start"],
        orientation="h",
        marker=dict(color=b["color"], line=dict(width=0)),
        text=b["status"],
        textposition="inside",
        insidetextanchor="start",
        textfont=dict(size=11, color="#FFF"),
        hovertemplate=f"<b>{b['phase']}</b><br>"
                       f"Start: {b['start'].date()}<br>"
                       f"End: {b['end'].date()}<br>"
                       f"Status: {b['status']}<extra></extra>",
        showlegend=False,
    ))

# Gate-review milestone (June 1)
fig.add_shape(
    type="line", x0=GATE_DATE, x1=GATE_DATE, y0=-0.5, y1=len(bars) - 0.5,
    line=dict(color="#FFCA28", width=2, dash="dash"),
)
fig.add_annotation(
    x=GATE_DATE, y=len(bars) - 0.5, yshift=18,
    text="🟡 Phase 8 gate (Jun 1)",
    showarrow=False, font=dict(color="#FFCA28", size=11),
)

# July hosting re-eval
JULY_REEVAL = date(2026, 7, 15)
fig.add_shape(
    type="line", x0=JULY_REEVAL, x1=JULY_REEVAL, y0=-0.5, y1=len(bars) - 0.5,
    line=dict(color="#FFCA28", width=1, dash="dot"),
)
fig.add_annotation(
    x=JULY_REEVAL, y=0, yshift=-25,
    text="hosting re-eval",
    showarrow=False, font=dict(color="#FFCA28", size=10),
)

# Today line
fig.add_shape(
    type="line", x0=TODAY, x1=TODAY, y0=-0.5, y1=len(bars) - 0.5,
    line=dict(color="#1E88E5", width=2),
)
fig.add_annotation(
    x=TODAY, y=len(bars) - 0.5, yshift=8,
    text="today",
    showarrow=False, font=dict(color="#1E88E5", size=11),
)

fig.update_layout(
    height=320, barmode="stack", margin=dict(l=20, r=20, t=40, b=40),
    plot_bgcolor="#0D1117", paper_bgcolor="#0D1117",
    font=dict(color="#CCC", size=12),
    xaxis=dict(type="date", showgrid=True, gridcolor="#1E2130"),
    yaxis=dict(showgrid=False, autorange="reversed"),
    title=dict(text="Phase 5 → Phase 9 with milestones", x=0, font=dict(size=13)),
)
st.plotly_chart(fig, width="stretch")

st.divider()


# ════════════════════════════════════════════════════════════════════════
# WIDGET 3 + 4 — Phase 8 Blockers + Risks Register (side by side)
# ════════════════════════════════════════════════════════════════════════
col_blockers, col_risks = st.columns([1, 1])

# ── WIDGET 3 — Phase 8 Blockers countdown ──
with col_blockers:
    st.subheader("Phase 8 blockers")
    days_to_gate = (GATE_DATE - date.today()).days
    countdown_color = "#EF5350" if days_to_gate <= 14 else ("#FFCA28" if days_to_gate <= 30 else "#4CAF50")
    st.markdown(
        f"<div style='background:#12151C;border:1px dashed {countdown_color};border-radius:8px;"
        f"padding:10px 14px;margin-bottom:10px;text-align:center'>"
        f"<span style='color:{countdown_color};font-size:22px;font-weight:700'>{days_to_gate}</span> "
        f"<span style='color:#888;font-size:13px'>days until {GATE_DATE.isoformat()} gate review</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    with conn() as c:
        blockers = pd.read_sql(
            "SELECT action_id, title, description, status FROM action_items "
            "WHERE blocking_phase = 8 ORDER BY action_id",
            c,
        )

    if blockers.empty:
        st.info("No Phase 8 blockers found.")
    else:
        for _, b in blockers.iterrows():
            status = b["status"]
            row_class = "blocker-row"
            if status == "DONE":
                row_class = "blocker-row blocker-row-done"
                icon = "✅"
            elif status == "IN_PROGRESS":
                row_class = "blocker-row blocker-row-progress"
                icon = "🔶"
            else:
                icon = "⬜"
            st.markdown(
                f"<div class='{row_class}'>"
                f"<div style='display:flex;justify-content:space-between;align-items:baseline'>"
                f"<span style='font-weight:700;color:#FFF'>{icon} {b['action_id']}</span>"
                f"<span style='color:#888;font-size:11px'>{status}</span>"
                f"</div>"
                f"<div style='color:#CCC;font-size:12px;margin-top:2px'>{b['title']}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Card-border indicator: red if any OPEN, amber if any IN_PROGRESS, green if all DONE
        any_open = (blockers["status"] == "OPEN").any()
        any_progress = (blockers["status"] == "IN_PROGRESS").any()
        all_done = (blockers["status"] == "DONE").all()
        if all_done:
            st.success("✅ All blockers DONE — Phase 8 gate can vote GREEN.")
        elif any_open:
            n_open = (blockers["status"] == "OPEN").sum()
            st.error(f"🔴 {n_open} blocker(s) OPEN — Phase 8 cannot start.")
        elif any_progress:
            st.warning("🟡 Blockers in progress.")

# ── WIDGET 4 — Risks Register ──
with col_risks:
    st.subheader("External-review risks")
    with conn() as c:
        risks = pd.read_sql(
            "SELECT risk_id, title, severity, likelihood, mitigation, status "
            "FROM risks_register WHERE source LIKE '%external_review%' "
            "ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 "
            "WHEN 'MEDIUM' THEN 3 ELSE 4 END",
            c,
        )

    if risks.empty:
        st.info("No external-review risks found.")
    else:
        sev_color = {"CRITICAL": "#EF5350", "HIGH": "#FF9800", "MEDIUM": "#FFCA28", "LOW": "#4CAF50"}
        for _, r in risks.iterrows():
            color = sev_color.get(r["severity"], "#888")
            st.markdown(
                f"<div style='background:#12151C;border-left:3px solid {color};border-radius:6px;"
                f"padding:8px 12px;margin-bottom:6px'>"
                f"<div style='display:flex;gap:10px;align-items:baseline;margin-bottom:3px'>"
                f"<span style='font-weight:700;color:#FFF;font-size:13px'>{r['risk_id']}</span>"
                f"<span style='color:{color};font-size:11px;font-weight:600'>"
                f"{r['severity']} / likelihood {r['likelihood']}</span>"
                f"</div>"
                f"<div style='color:#CCC;font-size:12px'>{r['title']}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        with st.expander("Mitigations"):
            for _, r in risks.iterrows():
                st.markdown(f"**{r['risk_id']}** — {r['mitigation']}")

st.divider()


# ════════════════════════════════════════════════════════════════════════
# Footer — meeting-emergent action items
# ════════════════════════════════════════════════════════════════════════
st.subheader("Meeting-emergent action items (added during 04-28)")
with conn() as c:
    emergent = pd.read_sql(
        "SELECT action_id, category, title, blocking_phase, status FROM action_items "
        "WHERE source = 'meeting_2026_04_28' ORDER BY action_id",
        c,
    )
if emergent.empty:
    st.info("No meeting-emergent items.")
else:
    st.dataframe(emergent, width="stretch", hide_index=True)

st.caption(
    f"Source DB: `data/improvements.db`. Synthesis: `docs/research/external_review_2026_04_28.md`. "
    f"1-pager: `docs/meetings/2026_04_28_external_review_summary.md`."
)
