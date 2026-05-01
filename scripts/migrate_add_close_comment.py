"""One-shot migration: add trade_results.close_comment column.

Part of AI-017b (Phase A). Captures the raw MT5 close-deal comment so any
future exit-reason investigation has direct evidence — closes the gap
that yesterday's audit hit (couldn't verify the substring-vs-modified-SL
hypothesis from DB alone because we don't store the close comment).

Idempotent: detects existing column and exits cleanly. Safe to re-run.

Will be replaced with an Alembic migration once AI-003 ships. For now,
plain ALTER TABLE via sqlite3 per project lead instruction (docs/p.md
2026-05-01)."""
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
        if "close_comment" in cols:
            print("[migrate] trade_results.close_comment already exists — no-op")
            return 0
        con.execute("ALTER TABLE trade_results ADD COLUMN close_comment TEXT")
        con.commit()
        print("[migrate] added trade_results.close_comment (TEXT, nullable)")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
