"""One-shot migration: add trade_results.exit_reason_v2 column.

AI-017b Phase B. Additive — preserves existing exit_reason for audit.

Idempotent: detects existing column and exits cleanly. Safe to re-run.

Will be replaced with an Alembic migration once AI-003 ships."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = "data/trading.db"


def main() -> int:
    if not Path(DB_PATH).exists():
        print(f"[migrate] {DB_PATH} not found", file=sys.stderr)
        return 1

    con = sqlite3.connect(DB_PATH)
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(trade_results)").fetchall()]
        if "exit_reason_v2" in cols:
            print("[migrate] trade_results.exit_reason_v2 already exists — no-op")
            return 0
        con.execute("ALTER TABLE trade_results ADD COLUMN exit_reason_v2 VARCHAR(20)")
        con.commit()
        print("[migrate] added trade_results.exit_reason_v2 (VARCHAR(20), nullable)")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
