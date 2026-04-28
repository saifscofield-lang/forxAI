"""Insert external-review records into improvements.db.
Idempotent on action_id / risk_id (UNIQUE constraints). Run once."""
import sqlite3, textwrap

DB = "data/improvements.db"
SOURCE = "external_review_claude_web_2026_04_28"
TODAY = "2026-04-28"

# §10 Final Synthesis text (verbatim) — for decision_inputs.summary (first 500 chars)
FINAL_SYNTHESIS = (
    'v3 is not "narrowly profitable v3" — it is "structurally broken model funded by an '
    'incidental window of bias × falling gold". The meeting\'s real question is not the '
    'schedule. It is whether the team confronts that framing or celebrates the +10.6% as '
    'accomplishment. The reviewer urges confrontation. The system is fixable, but not if '
    '+10.6% is read as confirmation.'
)
SUMMARY_500 = FINAL_SYNTHESIS[:500]

ACTION_ITEMS = [
    # (action_id, category, title, description, blocking_phase)
    ("AI-001", "BLOCKING", "Implement XAUUSD BUY-side capability",
     "Root-cause the zero-BUY asymmetry across all 105 XAUUSD trades. Either the ML model is SELL-biased (training-data class imbalance) or config thresholds are asymmetric. Required before Phase 8 because Phase 8 coincides with projected Q3 gold reversal — a zero-BUY system in a rising market is guaranteed drawdown.", 8),
    ("AI-002", "BLOCKING", "Retire bollinger_bounce + ml_filtered_sma from active rotation",
     "Both strategies show high WR with negative PnL (small wins, big losses pathology). Must retire BEFORE Phase 7 so they do not contribute to the meta-labeler training set composition.", 8),
    ("AI-003", "BLOCKING", "Build Alembic-based migration system OR equivalent CI guard",
     "Four schema-drift instances surfaced in two weeks. The 2026-04-22 incident fix addressed one instance, not the class. CI guard should compare inspect.get_columns() to Model.__table__.columns on every commit. P0 infrastructure debt.", 8),
    ("AI-004", "BLOCKING", "Startup-time config snapshot logger + restart self-check",
     "Engine loads config once at __init__. Currently no mechanism detects post-restart config drift. Required: log config hash at startup, periodically verify in-memory hash matches on-disk file hash. Same class of failure as the 6-day shadow outage.", 8),
    ("AI-005", "BLOCKING", "Hold out 30% of v3 trades; run R1-R7 OOS validation on holdout",
     "v3's R1-R7 are being tested on the same dataset that generated them — converting OOS into a second IS. v4 was rejected on stricter methodology; v3 must be held to the same bar. Hold out ~41 most recent v3 trades, validate filters on holdout before installation.", 8),
    ("AI-006", "SHADOW", "Install OVERLAP filter for XAUUSD in shadow logging only",
     "Filter would have been the highest-confidence recommendation in the original briefing, but the OVERLAP-session hypothesis was post-hoc. Run shadow-only for 14+ days, log what it would have rejected and outcomes, before any installation in paper.yaml.", 8),
    ("AI-007", "SHADOW", "Build ATR-controlled OVERLAP analysis (test confound hypothesis)",
     "OVERLAP coincides with the highest-ATR window for XAUUSD daily. The session-loss pattern may be ATR-loss masquerading as session-loss. Stratify the OVERLAP analysis by ATR bucket; if losses concentrate in high-ATR rather than session, the right filter is volatility-based.", 8),
    ("AI-008", "MONITORING", "Daily shadow-staleness alert (max 30 min lag) on dashboard",
     "The 6-day shadow outage was undetected because no monitoring flagged staleness. Required widget on Project Tracker: 'last shadow write > 30 min ago' triggers visible warning. Prevents the recurrence-by-silence pattern.", None),
    ("AI-009", "DOCS", "Write RFC for ml_direct/XAUUSD keep-or-block decision",
     "The decision must be justified on FORWARD risk in both regimes (rising and falling gold), not on retrospective P&L. The RFC documents the institutional reasoning before the meeting decides between options C and D on R3.", None),
    ("AI-010", "DOCS", "Define Phase 8 quantitative success criteria in writing",
     "Required before Phase 8 starts. Must specify: PnL floor, Sharpe target, minimum active symbols and directions for portfolio diversification, max drawdown, and explicit halt conditions. Without written criteria, Phase 8 has no defined fail state.", 8),
    ("AI-011", "DOCS", "Decide ML training set composition explicitly",
     "ML_TRAINING_THRESHOLD = 200 is manual-trigger only (verified at engine/trading_engine.py:985-993 — sends Telegram, no auto-retrain). When training is manually invoked, the dataset will currently include zero-BUY on XAUUSD, retired-strategies' losing patterns, and a single-regime sample. Composition must be decided BEFORE training is run.", None),
    ("AI-012", "MONITORING", "Gold regime monitor (5-day SMA > 20-day SMA, alert on crossover)",
     "Q3 institutional consensus is bullish. A zero-BUY system in a rising market is a guaranteed drawdown. Daily indicator + alert on regime transition gives the project lead time to decide on system response before the reversal is well-established.", None),
    ("AI-013", "MONITORING", "Per-symbol per-direction trade count dashboard",
     "Catches underpowered cells (n<10) before they become recommendations. The 04-28 briefing relied on cells that were UNDERPOWERED for non-XAUUSD symbols; surface this in the dashboard so future analyses cannot rely on them silently.", None),
    ("AI-014", "POST_MEETING", "Write decision_log.md entries for each YES vote",
     "After meeting, document each approved recommendation with date, rationale, and link to the relevant analysis files. Maintains the audit trail.", None),
    ("AI-015", "POST_MEETING", "Update improvements.db::go_no_go_decisions with meeting outcomes",
     "Insert one row per decided vote (votes 1-8) with verdict GREEN/YELLOW/RED, gates info, and bilingual rationale. Match existing schema convention.", None),
    ("AI-016", "POST_MEETING", "Update improvements.db::phase_steps for any phase transitions",
     "If Phase 5 → Phase 6/7 transition is approved (vote 1), mark Phase 5 step transitions, set Phase 6 and Phase 7 to IN_PROGRESS with started_at = approved start date.", None),
]

RISKS = [
    ("R-EXT-001", "Gold regime reversal during Phase 8 window",
     "Q3 2026 institutional consensus is bullish: JPMorgan target $5,000, Goldman Sachs $5,400-6,000, Deutsche Bank $6,000. Phase 8 (Jun 8 - Jul 20) coincides with the projected reversal. A zero-BUY system in a rising gold market is guaranteed drawdown — the system has no mechanism to participate in upward XAUUSD moves and will repeatedly stop into the trend.",
     "CRITICAL", "HIGH",
     "Implement XAUUSD BUY-side capability (AI-001) before Phase 8. Add gold-regime monitor (AI-012). Re-evaluate Phase 8 timing at June 1 gate."),
    ("R-EXT-002", "ML_TRAINING_THRESHOLD will bake current biases (manual trigger)",
     "ML_TRAINING_THRESHOLD = 200 verified at engine/trading_engine.py:28 with usage at L985-993. Trigger is manual: when threshold is hit, engine sends Telegram notification 'ML ready for training — run: python scripts/train_ml.py' and sets _ml_ready_notified=True. No auto-retraining. Risk severity downgraded from HIGH to MEDIUM after verification, but bias composition still unaddressed: when manually invoked, training set will include zero-BUY on XAUUSD, retired strategies' losing patterns, and a single-regime sample. Next model will inherit these biases.",
     "MEDIUM", "HIGH",
     "Decide training set composition explicitly (AI-011) BEFORE manual invocation. Hold out OOS sample (AI-005). Phase 7 audit must include training-set design, not just labeler design."),
    ("R-EXT-003", "Schema-drift class not resolved without migrations",
     "Four schema-drift instances surfaced in two weeks: shadow_signals.data_group (caused 6-day outage), Trade.data_group (latent), TradeResult.data_group (latent), and trade_results.{h1_trend, h4_trend, volatility_regime} (silently NULL since v2.4). The 'RESOLVED' label on the 2026-04-22 incident describes one instance, not the class. Without Alembic or equivalent CI guard, the next ALTER TABLE will produce another silent failure.",
     "HIGH", "MEDIUM",
     "Build migration system or CI guard (AI-003) before Phase 8. Treat as P0 infrastructure debt."),
    ("R-EXT-004", "Config-load-once + manual restart = silent stale-config window",
     "Engine reads YAML once at __init__; no hot-reload. Every config change opens a window where the running engine still holds the previous config in memory. The 6-day shadow outage demonstrated this exact failure pattern. No post-restart self-check exists to confirm in-memory config matches on-disk file.",
     "MEDIUM", "MEDIUM",
     "Implement startup-time config snapshot logger and post-restart self-check (AI-004). Mandate engine restart + verification step in the change-management process."),
]

con = sqlite3.connect(DB)
cur = con.cursor()
try:
    con.execute("BEGIN")

    # 1. decision_inputs row (Option C)
    cur.execute("""
        INSERT INTO decision_inputs
          (input_date, phase_number, subject, summary, artifacts, source)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        TODAY, 5,
        "External skeptical review of v3 go/no-go briefing",
        SUMMARY_500,
        "docs/research/external_review_2026_04_28.md",
        SOURCE,
    ))

    # 2. action_items
    for aid, cat, title, desc, bp in ACTION_ITEMS:
        cur.execute("""
            INSERT INTO action_items
              (action_id, category, title, description, blocking_phase, source, created_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (aid, cat, title, desc, bp, SOURCE, TODAY))

    # 3. risks_register
    for rid, title, desc, sev, lik, mit in RISKS:
        cur.execute("""
            INSERT INTO risks_register
              (risk_id, title, description, severity, likelihood, mitigation, source, identified_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (rid, title, desc, sev, lik, mit, SOURCE, TODAY))

    con.commit()
    print("[OK] all rows committed")
except Exception as e:
    con.rollback()
    print(f"[FAIL] rolled back: {e}")
    raise
finally:
    con.close()

# Verify counts
con = sqlite3.connect(DB)
print()
print("=== Verification counts ===")
n1 = con.execute("SELECT COUNT(*) FROM decision_inputs WHERE input_date='2026-04-28'").fetchone()[0]
n2 = con.execute("SELECT COUNT(*) FROM action_items WHERE source=?", (SOURCE,)).fetchone()[0]
n3 = con.execute("SELECT COUNT(*) FROM risks_register WHERE source=?", (SOURCE,)).fetchone()[0]
print(f"  decision_inputs (today's): {n1}  [expected 1]")
print(f"  action_items   (this src): {n2}  [expected 16]")
print(f"  risks_register (this src): {n3}  [expected 4]")
con.close()
