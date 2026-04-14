"""
Data Segmentation Script — tags all trades into OLD/TRANSITION/STABLE groups
and logs detailed reasoning for each group to improvements.db.
Run once: python scripts/segment_data.py
"""
import sys
import os
sys.path.insert(0, ".")
os.environ["PYTHONIOENCODING"] = "utf-8"

import sqlite3
from datetime import datetime

IMP_DB = "data/improvements.db"
TRADING_DB = "data/trading.db"


def main():
    # ═══════════════════════════════════════════════════════
    # 1. Create data_segmentation_log table
    # ═══════════════════════════════════════════════════════
    conn_i = sqlite3.connect(IMP_DB)
    ci = conn_i.cursor()

    ci.execute("""CREATE TABLE IF NOT EXISTS data_segmentation_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT NOT NULL,
        group_name TEXT NOT NULL,
        date_from TEXT NOT NULL,
        date_to TEXT NOT NULL,
        engine_versions TEXT,
        trade_count INTEGER,
        total_pnl REAL,
        win_rate REAL,
        description TEXT NOT NULL,
        why_segmented TEXT NOT NULL,
        valid_for TEXT NOT NULL,
        not_valid_for TEXT NOT NULL,
        config_changes TEXT,
        notes TEXT
    )""")
    conn_i.commit()
    print("Created data_segmentation_log table")

    # ═══════════════════════════════════════════════════════
    # 2. Add data_group column to all relevant tables
    # ═══════════════════════════════════════════════════════
    conn_t = sqlite3.connect(TRADING_DB)
    ct = conn_t.cursor()

    for table in ["trades", "trade_results", "shadow_signals"]:
        ct.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in ct.fetchall()]
        if "data_group" not in cols:
            ct.execute(f"ALTER TABLE {table} ADD COLUMN data_group TEXT")
            print(f"Added data_group to {table}")

    conn_t.commit()

    # ═══════════════════════════════════════════════════════
    # 3. Tag trades by group
    # ═══════════════════════════════════════════════════════
    # OLD: before 2026-03-31
    ct.execute("UPDATE trades SET data_group = 'OLD' WHERE open_time < '2026-03-31'")
    print(f"Tagged OLD: {ct.rowcount} trades")

    # TRANSITION: 2026-03-31 to 2026-04-09
    ct.execute("UPDATE trades SET data_group = 'TRANSITION' WHERE open_time >= '2026-03-31' AND open_time < '2026-04-10'")
    print(f"Tagged TRANSITION: {ct.rowcount} trades")

    # STABLE: 2026-04-10+
    ct.execute("UPDATE trades SET data_group = 'STABLE' WHERE open_time >= '2026-04-10'")
    print(f"Tagged STABLE: {ct.rowcount} trades")

    # Same for trade_results
    ct.execute("UPDATE trade_results SET data_group = 'OLD' WHERE open_time < '2026-03-31'")
    ct.execute("UPDATE trade_results SET data_group = 'TRANSITION' WHERE open_time >= '2026-03-31' AND open_time < '2026-04-10'")
    ct.execute("UPDATE trade_results SET data_group = 'STABLE' WHERE open_time >= '2026-04-10'")

    # Shadow signals
    ct.execute("UPDATE shadow_signals SET data_group = 'TRANSITION' WHERE time < '2026-04-10'")
    ct.execute("UPDATE shadow_signals SET data_group = 'STABLE' WHERE time >= '2026-04-10'")

    conn_t.commit()

    # ═══════════════════════════════════════════════════════
    # 4. Collect stats per group
    # ═══════════════════════════════════════════════════════
    groups = {}
    for group in ["OLD", "TRANSITION", "STABLE"]:
        ct.execute(
            "SELECT COUNT(*), SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END), "
            "ROUND(SUM(profit), 2) FROM trades WHERE is_closed = 1 AND data_group = ?",
            (group,),
        )
        r = ct.fetchone()
        count = r[0] or 0
        wins = r[1] or 0
        pnl = r[2] or 0
        wr = round((wins / count * 100), 1) if count > 0 else 0
        groups[group] = {"count": count, "wins": wins, "pnl": pnl, "wr": wr}
        print(f"  {group}: {count} trades | WR {wr}% | P&L ${pnl:+,.2f}")

    conn_t.close()

    # ═══════════════════════════════════════════════════════
    # 5. Log segmentation with full reasoning
    # ═══════════════════════════════════════════════════════
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # OLD group
    ci.execute(
        "INSERT INTO data_segmentation_log "
        "(time, group_name, date_from, date_to, engine_versions, trade_count, total_pnl, win_rate, "
        "description, why_segmented, valid_for, not_valid_for, config_changes, notes) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            now, "OLD", "2026-03-18", "2026-03-30", "v? (no version), v2.0",
            groups["OLD"]["count"], groups["OLD"]["pnl"], groups["OLD"]["wr"],
            # description
            "First trades before Strategy Lab. Old code without filters, "
            "lot sizes 2-10, no ATR filter, no regime detector, no shadow tracker. "
            "Strategies used default parameters without optimization.",
            # why_segmented
            "Code changed fundamentally after this period. Lot sizes were 2-10 (now 1.0 max). "
            "No engine_version recorded. Strategies had default params without Optuna optimization. "
            "No session filter, no circuit breaker, no shadow tracking. "
            "Mixing this with current data would poison ML training.",
            # valid_for
            "Historical reference only. General strategy behavior analysis. "
            "Regime labeling was done retroactively and is valid for regime analysis.",
            # not_valid_for
            "ML training (different lot sizes and no filters). "
            "Performance comparison (different code). "
            "Strategy evaluation (params changed). "
            "Baseline measurement (inconsistent conditions).",
            # config_changes
            "No ATR filter, no regime detector, no session filter, "
            "lot size 2-10, no circuit breaker, no shadow tracker, "
            "no timezone fix, no strategy blacklist",
            None,
        ),
    )

    # TRANSITION group
    ci.execute(
        "INSERT INTO data_segmentation_log "
        "(time, group_name, date_from, date_to, engine_versions, trade_count, total_pnl, win_rate, "
        "description, why_segmented, valid_for, not_valid_for, config_changes, notes) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            now, "TRANSITION", "2026-03-31", "2026-04-09", "v2.1, v2.2, v2.3, v2.4",
            groups["TRANSITION"]["count"], groups["TRANSITION"]["pnl"], groups["TRANSITION"]["wr"],
            # description
            "Intensive building period. Daily code changes: ATR filter added, "
            "regime detector built, scoring system created, circuit breaker added, "
            "shadow tracker built, session filter added, 8 strategies enabled, "
            "lot size capped, daily limits toggled on/off.",
            # why_segmented
            "13 config changes in 10 days. ATR threshold changed from 1.5x to 1.2x. "
            "Lot size cap changed from 2.0 to 1.0. Daily limits added then removed. "
            "Session filter added. IMP-15 session filter active then disabled. "
            "Each day had different code. XAUUSD ML not yet blacklisted. "
            "Timezone bug present (close times in local time not UTC).",
            # valid_for
            "Understanding impact of each change. Shadow signals (from Apr 2) "
            "are valid for filter effectiveness analysis. Learning what works.",
            # not_valid_for
            "ML training (conditions changed daily). "
            "Stable performance evaluation. "
            "Strategy comparison (different filters active on different days). "
            "Baseline measurement.",
            # config_changes
            "ATR 1.5->1.2, lot 2.0->1.0, circuit breaker log-only added, "
            "shadow tracker added Apr 2, session filter added Apr 3, "
            "all 8 strategies enabled, demo limits removed, "
            "IMP-15 session filter toggled, timezone bug present",
            None,
        ),
    )

    # STABLE group
    ci.execute(
        "INSERT INTO data_segmentation_log "
        "(time, group_name, date_from, date_to, engine_versions, trade_count, total_pnl, win_rate, "
        "description, why_segmented, valid_for, not_valid_for, config_changes, notes) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            now, "STABLE", "2026-04-10", "ongoing", "v2.4",
            groups["STABLE"]["count"], groups["STABLE"]["pnl"], groups["STABLE"]["wr"],
            # description
            "Stable period. Fixed code with timezone fix + XAUUSD blacklist. "
            "All filters active and consistent. Shadow tracker records everything "
            "with accurate lot size, spread, and UTC timestamps. "
            "This is the ONLY data valid for ML training and evaluation.",
            # why_segmented
            "First period without daily code changes. Engine v2.4 stable. "
            "All filters consistent: ATR 1.2x, session hours 8/15/23 blocked, "
            "XAUUSD ML blacklisted, lot size max 1.0, timezone UTC correct, "
            "shadow with lot+spread tracking. "
            "This group grows daily and is the foundation for all future analysis.",
            # valid_for
            "ML training (consistent conditions). "
            "Strategy performance evaluation. "
            "Shadow vs executed comparison. "
            "Filter accuracy measurement. "
            "Baseline for future comparison. "
            "All analytical purposes.",
            # not_valid_for
            "Nothing. This data is valid for all uses.",
            # config_changes
            "v2.4 stable, ATR 1.2x, lot max 1.0, session filter (8,15,23), "
            "XAUUSD ML blacklisted, timezone UTC fixed, "
            "shadow with lot+spread, circuit breaker log-only, "
            "IMP-15 session filter disabled in demo",
            None,
        ),
    )

    # ═══════════════════════════════════════════════════════
    # 6. Log the decision
    # ═══════════════════════════════════════════════════════
    ci.execute(
        "INSERT INTO decisions_log (time, category, decision, reason, impact, phase) "
        "VALUES (?,?,?,?,?,?)",
        (
            "2026-04-14", "DATA",
            "Segment all trades into OLD/TRANSITION/STABLE groups with documented reasoning",
            "211 trades from 5 engine versions with 13 config changes. "
            "Mixing all data for ML = guaranteed overfitting on noise. "
            "Each group has different lot sizes, filters, and code. "
            "Only STABLE (Apr 10+) data has consistent conditions for training.",
            "All trades tagged with data_group column. "
            "Detailed reasoning logged in data_segmentation_log table. "
            "ML training will use STABLE group only. "
            "OLD and TRANSITION preserved for historical reference.",
            1,
        ),
    )

    conn_i.commit()
    conn_i.close()
    print("\nAll segmentation logged to improvements.db")


if __name__ == "__main__":
    main()
