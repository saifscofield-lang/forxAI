"""v4 Crypto Momentum — pipeline status, IS vs OOS, gates, equity, decisions."""
import sys
sys.path.insert(0, ".")

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="v4 Crypto Status", page_icon="🪙", layout="wide")

st.markdown("""
<style>
    .block-container { padding-top: 1rem; max-width: 1400px; }
    .v4-card {
        background: linear-gradient(135deg, #1A1F2E 0%, #151A28 100%);
        border: 1px solid #2D3748;
        border-radius: 12px;
        padding: 18px 22px;
        margin-bottom: 14px;
    }
    .gate-pass { color: #4CAF50; font-weight: 700; }
    .gate-fail { color: #EF5350; font-weight: 700; }
    .gate-cell { font-size: 13px; padding: 4px 10px; border-radius: 6px; display: inline-block; }
    .pill-green { background: #0D2818; color: #4CAF50; border: 1px solid #1B5E20; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
    .pill-yellow { background: #2B2410; color: #FFCA28; border: 1px solid #6B5A1A; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
    .pill-red { background: #2D1111; color: #EF5350; border: 1px solid #B71C1C; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
    .option-box { background: #0D1117; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; border-left: 3px solid #444; }
    .option-chosen { border-left-color: #FF9800; background: #1A1810; }
    hr { border-color: #1E2130 !important; margin: 0.8rem 0 !important; }
</style>
""", unsafe_allow_html=True)

IMP_DB = "data/improvements.db"
PHASE_10 = 10
PHASE_10_5 = 105  # integer encoding of "10.5"

# ── HEADER ─────────────────────────────────────────────────────────
st.markdown("""
<div style="display:flex;align-items:baseline;gap:16px;margin-bottom:4px">
    <span style="font-size:26px;font-weight:800;color:#FF9800">v4 Crypto Momentum — Status</span>
    <span style="font-size:13px;color:#666;letter-spacing:0.5px">Phase 10 — TSMOM on BTC/ETH/BNB/SOL (Binance)</span>
</div>
""", unsafe_allow_html=True)


def conn():
    return sqlite3.connect(IMP_DB)


# ════════════════════════════════════════════════════════════════════
# 1. Pipeline progress (Steps 1-8 + Phase 10.5)
# ════════════════════════════════════════════════════════════════════
with conn() as c:
    steps = pd.read_sql(f"SELECT * FROM phase_steps WHERE phase_number IN ({PHASE_10}, {PHASE_10_5}) ORDER BY phase_number, step_order", c)
    phases = pd.read_sql(f"SELECT * FROM project_phases WHERE phase_number IN ({PHASE_10}, {PHASE_10_5}) ORDER BY phase_number", c)

p10_steps = steps[steps["phase_number"] == PHASE_10]
p105_steps = steps[steps["phase_number"] == PHASE_10_5]

st.subheader("Phase 10 — Pipeline Progress")
done = int((p10_steps["status"] == "COMPLETED").sum())
total = len(p10_steps)
st.progress(done / total if total else 0, text=f"{done} / {total} steps complete")

cols = st.columns(total)
icons = {"COMPLETED": "✅", "IN_PROGRESS": "🔶", "PENDING": "⬜"}
colors = {"COMPLETED": "#4CAF50", "IN_PROGRESS": "#FF9800", "PENDING": "#555"}
for (_, row), col in zip(p10_steps.iterrows(), cols):
    ic = icons.get(row["status"], "⬜")
    c = colors.get(row["status"], "#555")
    short = row["description"][:45] + ("..." if len(row["description"]) > 45 else "")
    col.markdown(
        f"<div style='text-align:center;border:1px solid {c};border-radius:8px;padding:8px 4px;background:#12151C'>"
        f"<div style='font-size:20px'>{ic}</div>"
        f"<div style='color:{c};font-weight:700;margin-top:4px;font-size:13px'>Step {row['step_order']}</div>"
        f"<div style='color:#888;font-size:11px;margin-top:4px'>{short}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

st.divider()

# ════════════════════════════════════════════════════════════════════
# 2. IS vs OOS comparison table
# ════════════════════════════════════════════════════════════════════
st.subheader("In-Sample vs Out-of-Sample")
with conn() as c:
    runs = pd.read_sql("SELECT scope, sharpe, max_drawdown, cagr, annual_vol, sortino, verdict, notes FROM tsmom_runs WHERE scope LIKE 'crypto_%' ORDER BY scope", c)

if runs.empty:
    st.info("No crypto tsmom_runs rows yet.")
else:
    # Split scopes: base in-sample variants vs _train / _oos slices
    is_rows = runs[~runs["scope"].str.endswith(("_train", "_oos"))].copy()
    slice_rows = runs[runs["scope"].str.endswith(("_train", "_oos"))].copy()

    def pct(x):
        return f"{x*100:+.2f}%" if pd.notna(x) else "-"

    def fmt_sharpe(x):
        if pd.isna(x):
            return "-"
        color = "#4CAF50" if x >= 0.4 else "#EF5350"
        return f"<span style='color:{color};font-weight:700'>{x:.3f}</span>"

    with st.expander("All 8 in-sample variants (step 3)", expanded=False):
        show = is_rows.copy()
        show["sharpe"] = show["sharpe"].map(lambda x: f"{x:.3f}" if pd.notna(x) else "-")
        show["cagr"] = show["cagr"].map(pct)
        show["max_drawdown"] = show["max_drawdown"].map(pct)
        show["annual_vol"] = show["annual_vol"].map(pct)
        show["sortino"] = show["sortino"].map(lambda x: f"{x:.3f}" if pd.notna(x) else "-")
        st.dataframe(show[["scope", "sharpe", "cagr", "annual_vol", "max_drawdown", "sortino", "verdict"]], width="stretch", hide_index=True)

    st.markdown("**OOS validation (step 4) — primary + secondary only**")
    if not slice_rows.empty:
        slice_rows["sharpe_fmt"] = slice_rows["sharpe"].map(lambda x: f"{x:.3f}" if pd.notna(x) else "-")
        slice_rows["cagr_fmt"] = slice_rows["cagr"].map(pct)
        slice_rows["dd_fmt"] = slice_rows["max_drawdown"].map(pct)
        st.dataframe(
            slice_rows[["scope", "sharpe_fmt", "cagr_fmt", "dd_fmt", "verdict"]]
            .rename(columns={"sharpe_fmt": "Sharpe", "cagr_fmt": "CAGR", "dd_fmt": "MaxDD", "verdict": "Verdict"}),
            width="stretch", hide_index=True,
        )

st.divider()

# ════════════════════════════════════════════════════════════════════
# 3. Gate scoreboard — 4 gates × 2 variants
# ════════════════════════════════════════════════════════════════════
st.subheader("OOS Gate Scoreboard")
gate_data = {
    "Gate": [
        "OOS Sharpe ≥ 0.4",
        "OOS MaxDD ≥ -25%",
        "OOS within 30% of train Sharpe",
        "OOS Sharpe > BH BTC Sharpe",
    ],
    "Primary (LO/12m)": [
        ("FAIL", "Sharpe 0.030"),
        ("PASS", "DD -8.5%"),
        ("FAIL", "drift 0.98"),
        ("PASS", "0.03 > -0.33"),
    ],
    "Secondary (LO/12w)": [
        ("PASS", "Sharpe 0.553"),
        ("PASS", "DD -4.4%"),
        ("FAIL", "drift 0.57"),
        ("PASS", "0.55 > -0.33"),
    ],
}
gate_df = pd.DataFrame({
    "Gate": gate_data["Gate"],
    "Primary (LO/12m)": [f"{'🟢' if s == 'PASS' else '🔴'} {s} — {d}" for s, d in gate_data["Primary (LO/12m)"]],
    "Secondary (LO/12w)": [f"{'🟢' if s == 'PASS' else '🔴'} {s} — {d}" for s, d in gate_data["Secondary (LO/12w)"]],
})
st.dataframe(gate_df, width="stretch", hide_index=True)

p_pass = sum(1 for s, _ in gate_data["Primary (LO/12m)"] if s == "PASS")
s_pass = sum(1 for s, _ in gate_data["Secondary (LO/12w)"] if s == "PASS")
c1, c2 = st.columns(2)
c1.metric("Primary gates passed", f"{p_pass} / 4", "RED" if p_pass < 4 else "GREEN", delta_color="inverse")
c2.metric("Secondary gates passed", f"{s_pass} / 4", "RED" if s_pass < 4 else "GREEN", delta_color="inverse")

st.divider()

# ════════════════════════════════════════════════════════════════════
# 4. Equity curves chart (from step-4 PNG)
# ════════════════════════════════════════════════════════════════════
st.subheader("Equity Curves — Train vs OOS")
png_path = Path("docs/research/tsmom_crypto_oos_equity.png")
if png_path.exists():
    st.image(str(png_path), width="stretch", caption="Train (blue) → OOS (orange) + Buy-and-Hold BTC OOS (dashed)")
else:
    st.info(f"Run step 4 to generate {png_path.name}.")

col_a, col_b = st.columns(2)
with col_a:
    step3_png = Path("docs/research/tsmom_crypto_equity_curves.png")
    if step3_png.exists():
        st.image(str(step3_png), width="stretch", caption="Step 3 — 8 variants (in-sample)")
with col_b:
    corr_png = Path("docs/research/tsmom_crypto_corr_heatmap.png")
    if corr_png.exists():
        st.image(str(corr_png), width="stretch", caption="Step 5 — correlation heatmap (full vs OOS)")

st.divider()

# ════════════════════════════════════════════════════════════════════
# 5. Fold stability (from step 4)
# ════════════════════════════════════════════════════════════════════
st.subheader("Purged K-Fold Stability — Training Window")
fold_data = pd.DataFrame({
    "Fold": [1, 2, 3, 4, 5, "mean", "std"],
    "LO_12m Sharpe": [0.37, 1.92, 0.69, -0.93, 2.37, 0.89, 1.21],
    "LO_12w Sharpe": [1.71, 0.28, 2.42, -0.75, 2.22, 1.18, 1.27],
})
st.dataframe(fold_data, width="stretch", hide_index=True)
st.caption("Fold 4 (roughly 2022 crypto winter) is negative in both variants — confirms regime-dependent performance.")

st.divider()

# ════════════════════════════════════════════════════════════════════
# 6. Current verdict + next action (from go_no_go_decisions)
# ════════════════════════════════════════════════════════════════════
st.subheader("Current Verdict & Next Action")
with conn() as c:
    try:
        decisions = pd.read_sql(
            "SELECT * FROM go_no_go_decisions WHERE phase_number=? ORDER BY decision_date DESC, id DESC LIMIT 1",
            c, params=(PHASE_10,),
        )
    except Exception as e:
        decisions = pd.DataFrame()
        st.warning(f"go_no_go_decisions not queryable: {e}")

if not decisions.empty:
    d = decisions.iloc[0]
    pill_class = {"GREEN": "pill-green", "YELLOW": "pill-yellow", "RED": "pill-red"}.get(d["verdict"], "pill-red")
    st.markdown(
        f"<div class='v4-card'>"
        f"<div style='display:flex;gap:16px;align-items:center;margin-bottom:10px'>"
        f"<span class='{pill_class}'>{d['verdict']}</span>"
        f"<span style='color:#999;font-size:13px'>Phase {d['phase_number']}</span>"
        f"<span style='color:#666;font-size:12px'>decided {d['decision_date']} by {d['decided_by'] or 'unknown'}</span>"
        f"<span style='color:#888;font-size:13px;margin-left:auto'>Gates: <b>{d['gates_passed']}/{d['gates_total']}</b></span>"
        f"</div>"
        f"<div style='color:#CCC;font-size:13px;line-height:1.6;margin-bottom:10px'>"
        f"<b>Rationale (EN):</b> {d['rationale_en']}</div>"
        f"<div style='color:#AAA;font-size:13px;line-height:1.6;margin-bottom:10px;direction:rtl'>"
        f"<b>السبب (AR):</b> {d['rationale_ar']}</div>"
        f"<div style='background:#1A1810;border-left:3px solid #FF9800;border-radius:6px;padding:10px 14px'>"
        f"<div style='color:#FF9800;font-weight:700;font-size:13px;margin-bottom:4px'>NEXT ACTION</div>"
        f"<div style='color:#FFF;font-size:13px'>{d['next_action']}</div>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
else:
    st.info("No decision recorded for Phase 10 yet.")

st.divider()

# ════════════════════════════════════════════════════════════════════
# 7. Decision tree — 5 options with chosen path highlighted
# ════════════════════════════════════════════════════════════════════
st.subheader("Options Considered")
options = [
    ("Option 1 — Reject v4 as-is", False, "Honor strict thresholds. Pivot to different Phase-10 track (commodities, crypto basis, volatility selling)."),
    ("Option 2 — Downgrade primary to secondary (LO/12w)", False, "Treat the drift-stability gate as tie-breaker. LO/12w is 3/4 gates and beats BH BTC handsomely."),
    ("Option 3 — Wait 6-12 more months of OOS", False, "16-month window is unrepresentative (bear regime). Accumulate more OOS data before final call."),
    ("Option 4 — Rescue with regime filter (Phase 10.5)", True, "Add vol-based or correlation-spike filter to TSMOM LO/12w. Re-validate OOS. Ship if gated OOS Sharpe > 0.4."),
    ("Option 5 — Expand universe", False, "Thin 4-coin portfolio. Add uncorrelated positions (sector ETFs, gold, FX). Scope of Phase 11, not Phase 10."),
]
for label, chosen, desc in options:
    css = "option-box option-chosen" if chosen else "option-box"
    mark = "→ CHOSEN" if chosen else ""
    st.markdown(
        f"<div class='{css}'>"
        f"<div style='display:flex;justify-content:space-between;align-items:baseline'>"
        f"<span style='font-weight:700;font-size:14px;color:{'#FF9800' if chosen else '#CCC'}'>{label}</span>"
        f"<span style='color:#FF9800;font-size:12px;font-weight:700'>{mark}</span>"
        f"</div>"
        f"<div style='color:#888;font-size:12px;margin-top:4px;line-height:1.5'>{desc}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

st.divider()

# ════════════════════════════════════════════════════════════════════
# 8. Phase 10.5 status
# ════════════════════════════════════════════════════════════════════
st.subheader("Phase 10.5 — Regime Filter Rescue (Pending Activation)")
if not phases[phases["phase_number"] == PHASE_10_5].empty:
    ph = phases[phases["phase_number"] == PHASE_10_5].iloc[0]
    st.markdown(
        f"<div class='v4-card' style='border-left:3px solid #555;opacity:0.9'>"
        f"<div style='color:#CCC;font-weight:700;font-size:14px;margin-bottom:4px'>{ph['name']}</div>"
        f"<div style='color:#888;font-size:12px;margin-bottom:4px;direction:rtl'>{ph['name_ar']}</div>"
        f"<div style='color:#999;font-size:12px;margin-top:8px'>{ph['notes']}</div>"
        f"<div style='color:#FF9800;font-size:12px;margin-top:8px'>Status: <b>{ph['status']}</b> — estimated duration {ph['duration']}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption("Steps seeded (all PENDING):")
    if not p105_steps.empty:
        for _, s in p105_steps.iterrows():
            st.markdown(f"⬜ Step {s['step_order']}: {s['description']}")
else:
    st.info("Phase 10.5 not seeded yet.")

st.divider()

# ════════════════════════════════════════════════════════════════════
# 9. Research artifacts (links)
# ════════════════════════════════════════════════════════════════════
st.subheader("Research Artifacts")
artifacts = [
    ("Step 3 — in-sample report", "docs/research/tsmom_crypto_prototype.md"),
    ("Step 4 — OOS validation report", "docs/research/tsmom_crypto_oos_report.md"),
    ("Step 5 — correlation report", "docs/research/tsmom_crypto_corr_report.md"),
    ("Crypto D1 data quality report", "data/raw_crypto/data_quality_report.md"),
    ("Step 4 metrics CSV", "data/research/tsmom_crypto_oos_metrics.csv"),
    ("Step 5 correlation matrix (full)", "data/research/tsmom_crypto_corr_matrix_full.csv"),
    ("Step 5 correlation matrix (OOS)", "data/research/tsmom_crypto_corr_matrix_oos.csv"),
]
for title, path in artifacts:
    p = Path(path)
    if p.exists():
        size_kb = p.stat().st_size / 1024
        st.markdown(f"• **{title}** — `{path}` ({size_kb:.1f} KB)")
    else:
        st.markdown(f"• ~~{title}~~ — `{path}` (missing)")
