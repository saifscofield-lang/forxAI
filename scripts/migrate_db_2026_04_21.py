"""One-shot migration applied 2026-04-21 for dashboard.md instructions.

Changes:
  - phase_steps: Phase 10 steps 3, 4, 5 -> COMPLETED (step 5 adapted: dashboard.md
    had this as IN_PROGRESS, but step 5 was completed before this migration ran)
  - project_phases: add Phase 10.5 as phase_number=105 (integer encoding of "10.5"
    because the existing schema/dashboard casts phase_number to int)
  - phase_steps: seed 6 steps for Phase 10.5 (all PENDING)
  - improvements schema: no change
  - new table go_no_go_decisions (if missing)
  - seed go_no_go_decisions row for Phase 10 (post-step-5 verdict)

All changes happen inside a single transaction; rollback on any error.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date

DB = "data/improvements.db"
TODAY = "2026-04-21"
PHASE_10_5 = 105  # integer encoding for "Phase 10.5"


def main() -> None:
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")
    cur = con.cursor()

    try:
        # ─── A. phase_steps: Phase 10 steps 3, 4, 5 → COMPLETED ─────────────────
        updates = [
            (3, "COMPLETED", TODAY,
             "8 in-sample variants run. LO/12m best (Sharpe 1.06). See docs/research/tsmom_crypto_prototype.md"),
            (4, "COMPLETED", TODAY,
             "OOS RED — primary 2/4 gates, secondary 3/4 gates. Strategy fails drift-stability gate due to 2025-2026 bear regime. See docs/research/tsmom_crypto_oos_report.md"),
            (5, "COMPLETED", TODAY,
             "Correlations computed: rho(FX)=0.13, rho(SPY)=0.21, rho(BTC OOS)=0.57. Option-4 diversification threshold met. See docs/research/tsmom_crypto_corr_report.md"),
        ]
        for step_order, status, done_date, notes in updates:
            cur.execute(
                "UPDATE phase_steps SET status=?, completed_at=?, notes=? "
                "WHERE phase_number=10 AND step_order=?",
                (status, done_date, notes, step_order),
            )
        # Step 7: keep PENDING but append deferred-decision note
        cur.execute(
            "UPDATE phase_steps SET notes=? WHERE phase_number=10 AND step_order=7",
            ("Decision deferred pending Phase 10.5 (regime filter) validation — correlations support Option 4 rescue",),
        )

        # ─── B. project_phases: add Phase 10.5 ─────────────────────────────────
        cur.execute(
            "SELECT COUNT(*) FROM project_phases WHERE phase_number=?",
            (PHASE_10_5,),
        )
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO project_phases (phase_number, name, name_ar, duration, status, started_at, completed_at, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    PHASE_10_5,
                    "Phase 10.5 — TSMOM Crypto with Regime Filter (Rescue Attempt)",
                    "المرحلة 10.5 — TSMOM للكريبتو مع فلتر النظام (محاولة إنقاذ)",
                    "~7 days",
                    "PENDING_ACTIVATION",
                    None,
                    None,
                    "Activated only if step 5 confirms diversification value vs FX portfolio (it did: rho_FX=0.13, rho_SPY=0.21). Awaiting user go-ahead to start.",
                ),
            )

        # ─── C. phase_steps: seed 6 steps for Phase 10.5 (all PENDING) ─────────
        cur.execute("SELECT COUNT(*) FROM phase_steps WHERE phase_number=?", (PHASE_10_5,))
        if cur.fetchone()[0] == 0:
            seed_steps = [
                (1, "Define regime filter spec (realized-vol threshold OR correlation-spike detector)",
                    "تحديد مواصفات فلتر النظام (عتبة تقلب محقق أو كاشف ارتفاع الترابط)"),
                (2, "Implement filter as overlay on existing TSMOM LO/12w signal",
                    "تنفيذ الفلتر كطبقة فوق إشارة TSMOM LO/12w الموجودة"),
                (3, "Re-run full backtest with filter (in-sample) and compare to ungated",
                    "إعادة تشغيل الـ backtest الكامل مع الفلتر (in-sample) ومقارنتها مع بدون فلتر"),
                (4, "Re-run OOS validation on held-out 2025-01-01 → latest",
                    "إعادة تشغيل التحقق OOS على النافذة المحجوزة 2025-01-01 → الأحدث"),
                (5, "Compare gated metrics vs ungated — does filter add or subtract value?",
                    "مقارنة المقاييس مع الفلتر وبدونه — هل الفلتر يضيف أم يطرح قيمة؟"),
                (6, "Updated go/no-go decision (proceed to Phase 11 or reject v4 crypto track)",
                    "قرار go/no-go المحدث (المضي لـ Phase 11 أو رفض مسار كريبتو v4)"),
            ]
            for order, desc_en, desc_ar in seed_steps:
                cur.execute(
                    "INSERT INTO phase_steps (phase_number, step_order, description, description_ar, status) "
                    "VALUES (?, ?, ?, ?, 'PENDING')",
                    (PHASE_10_5, order, desc_en, desc_ar),
                )

        # ─── D. verify tsmom_runs has the 4 OOS rows from step 4 ───────────────
        cur.execute(
            "SELECT scope FROM tsmom_runs WHERE scope IN ('crypto_LO_12m_c10bps_train','crypto_LO_12m_c10bps_oos','crypto_LO_12w_c10bps_train','crypto_LO_12w_c10bps_oos')"
        )
        found = {r[0] for r in cur.fetchall()}
        expected = {"crypto_LO_12m_c10bps_train", "crypto_LO_12m_c10bps_oos",
                    "crypto_LO_12w_c10bps_train", "crypto_LO_12w_c10bps_oos"}
        missing = expected - found
        if missing:
            raise RuntimeError(f"tsmom_runs missing expected scopes: {missing}")

        # ─── E. create go_no_go_decisions table if missing ─────────────────────
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='go_no_go_decisions'"
        )
        if cur.fetchone() is None:
            cur.execute("""
                CREATE TABLE go_no_go_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phase_number INTEGER NOT NULL,
                    decision_date TEXT NOT NULL,
                    verdict TEXT NOT NULL CHECK (verdict IN ('GREEN', 'YELLOW', 'RED')),
                    gates_passed INTEGER,
                    gates_total INTEGER,
                    rationale_en TEXT,
                    rationale_ar TEXT,
                    decided_by TEXT,
                    next_action TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)

        # ─── F. seed Phase 10 decision row (post-step-5 adapted) ───────────────
        cur.execute("SELECT COUNT(*) FROM go_no_go_decisions WHERE phase_number=10 AND decision_date=?", (TODAY,))
        if cur.fetchone()[0] == 0:
            cur.execute("""
                INSERT INTO go_no_go_decisions
                  (phase_number, decision_date, verdict, gates_passed, gates_total,
                   rationale_en, rationale_ar, decided_by, next_action)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                10,
                TODAY,
                "RED",
                3,   # secondary LO_12w passed 3 of 4 OOS gates
                4,
                "OOS Sharpe collapsed from train 1.27 to 0.03 (12m) and 0.55 (12w). 2025-2026 bear regime exposes regime-dependence. Correlation analysis (step 5) showed rho_FX=0.13, rho_SPY=0.21, rho_BTC_OOS=0.57 — diversification case for Option 4 (rescue with regime filter) is met.",
                "انهار Sharpe خارج العينة من 1.27 (تدريب) إلى 0.03 (12m) و 0.55 (12w). نظام 2025-2026 الهابط يكشف اعتماد الاستراتيجية على النظام السوقي. تحليل الترابط (خطوة 5) أظهر rho_FX=0.13, rho_SPY=0.21, rho_BTC_OOS=0.57 — شرط التنويع للخيار 4 (إنقاذ مع فلتر نظام) محقق.",
                "Claude Code + user review",
                "Activate Phase 10.5 (regime-filter rescue). If Phase 10.5 fails, formal reject → pivot to different Phase-10 track.",
            ))

        con.commit()
        print("[OK] migration committed")

    except Exception as e:
        con.rollback()
        print(f"[FAIL] rolled back: {e}")
        sys.exit(1)
    finally:
        con.close()


def verify() -> None:
    con = sqlite3.connect(DB)
    cur = con.cursor()
    print()
    print("=== verification ===")
    print("Phase 10 steps:")
    for r in cur.execute(
        "SELECT step_order, status, completed_at, substr(description,1,55) FROM phase_steps "
        "WHERE phase_number=10 ORDER BY step_order"
    ).fetchall():
        print(f"  step {r[0]} [{r[1]:9s}] done={r[2]} -- {r[3]}")
    print()
    print("Phase 10.5 (encoded as 105):")
    for r in cur.execute(
        "SELECT phase_number, name, status FROM project_phases WHERE phase_number=?", (PHASE_10_5,)
    ).fetchall():
        print(f"  {r}")
    print("  steps:")
    for r in cur.execute(
        "SELECT step_order, status, substr(description,1,55) FROM phase_steps WHERE phase_number=? ORDER BY step_order",
        (PHASE_10_5,),
    ).fetchall():
        print(f"    step {r[0]} [{r[1]}] -- {r[2]}")
    print()
    print("go_no_go_decisions:")
    for r in cur.execute(
        "SELECT phase_number, decision_date, verdict, gates_passed, gates_total, substr(next_action,1,80) FROM go_no_go_decisions ORDER BY decision_date DESC"
    ).fetchall():
        print(f"  phase {r[0]} {r[1]} {r[2]} gates {r[3]}/{r[4]} next: {r[5]}")
    con.close()


if __name__ == "__main__":
    main()
    verify()
