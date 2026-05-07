"""GAP-FID-01 migration: add Trade.requested_price + Trade.slippage_pips.

Idempotent ALTER TABLE for two new nullable columns on `trades`. Used
by the engine to capture filled-vs-requested price information that
was previously discarded inside execution/broker_adapters/mt5_adapter.py
(returned only the requested price; never logged the broker fill).

Replaces with Alembic when AI-003 / migration system shippinh more
broadly. For now, plain ALTER TABLE per project convention."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = "data/trading.db"

ADDS = [
    ("requested_price", "FLOAT"),
    ("slippage_pips", "FLOAT"),
]


def main() -> int:
    if not Path(DB_PATH).exists():
        print(f"[migrate] {DB_PATH} not found", file=sys.stderr)
        return 1

    con = sqlite3.connect(DB_PATH)
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(trades)").fetchall()]
        added = []
        for name, sql_type in ADDS:
            if name in cols:
                continue
            con.execute(f"ALTER TABLE trades ADD COLUMN {name} {sql_type}")
            added.append(name)
        if added:
            con.commit()
            print(f"[migrate] added trades.{{ {', '.join(added)} }}")
        else:
            print("[migrate] both columns already present — no-op")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
