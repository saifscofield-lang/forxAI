"""Schema-drift CI guard (AI-003).

Compares declared SQLAlchemy ORM columns (storage/database.py) against
actual on-disk SQLite columns (data/trading.db) and exits non-zero on
any divergence. Run before every commit (pre-commit hook) or as a
CI step.

Same root-cause class as the 2026-04-22 shadow-signals incident:
silent schema divergence between code and database. AI-003's brief
explicitly suggested this approach: "CI guard should compare
inspect.get_columns() to Model.__table__.columns on every commit".

Output (non-empty stderr → drift detected, exit 1):

  [drift] trade_results: extra in DB: {sentiment_score}
  [drift] trade_results: missing from DB: {regime_v2}

Categories surfaced:
  missing_in_db: column declared on the model but not present on disk.
                 This is the dangerous direction — code may try to
                 INSERT / SELECT a column the DB doesn't have, raising
                 OperationalError at runtime.
  extra_in_db:   column on disk but not on the model. Less dangerous
                 but still drift — may indicate a migration that
                 wasn't reflected back to the ORM (e.g. ALTER TABLE
                 from a one-off script).

Usage:
    python scripts/check_schema_drift.py
    python scripts/check_schema_drift.py --db data/other.db
    python scripts/check_schema_drift.py --quiet           # exit code only

Idempotent. Read-only. Safe to run repeatedly.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, ".")

from sqlalchemy import inspect, create_engine

import storage.database as _db  # noqa: E402

# Models to verify. Add new ORM classes here when introduced. The list
# is explicit (not auto-discovered from Base.metadata.tables) so a typo
# or accidental rename in the model module surfaces here as a clear
# import error rather than silent skip.
_MODELS = [
    _db.OHLCVBar,
    _db.Trade,
    _db.SignalLog,
    _db.TradeResult,
    _db.AccountSnapshot,
    _db.MarketContext,
    _db.NewsEvent,
    _db.ScanLog,
    _db.SymbolScanDetail,
    _db.IndicatorSnapshot,
    _db.StrategyImprovement,
    _db.MonitorState,
    _db.RegimeLog,
    _db.StrategyScorecard,
    _db.StrategyLineage,
    _db.RejectedArchive,
    _db.CircuitBreakerLog,
    _db.ShadowSignal,
]


def collect_drift(db_path: str) -> dict:
    """Return drift report keyed by table name.

    Each entry has 'missing_in_db' and 'extra_in_db' as sorted lists.
    Tables with neither are omitted from the result so callers can do
    a simple `if drift:` check."""
    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    on_disk_tables = set(inspector.get_table_names())
    drift: dict = {}

    for model in _MODELS:
        table = model.__tablename__
        declared = {c.name for c in model.__table__.columns}
        if table not in on_disk_tables:
            drift[table] = {
                "missing_in_db": sorted(declared),
                "extra_in_db": [],
                "table_missing": True,
            }
            continue
        actual = {c["name"] for c in inspector.get_columns(table)}
        missing = sorted(declared - actual)
        extra = sorted(actual - declared)
        if missing or extra:
            drift[table] = {
                "missing_in_db": missing,
                "extra_in_db": extra,
                "table_missing": False,
            }

    engine.dispose()
    return drift


def format_report(drift: dict) -> str:
    """Human-readable lines, one per drift instance."""
    if not drift:
        return ""
    lines = []
    for table, info in sorted(drift.items()):
        if info.get("table_missing"):
            lines.append(
                f"[drift] {table}: ENTIRE TABLE missing from DB "
                f"(declared: {', '.join(info['missing_in_db'])})"
            )
            continue
        if info["missing_in_db"]:
            lines.append(
                f"[drift] {table}: declared on model but not in DB: "
                f"{{{', '.join(info['missing_in_db'])}}}"
            )
        if info["extra_in_db"]:
            lines.append(
                f"[drift] {table}: in DB but not on model: "
                f"{{{', '.join(info['extra_in_db'])}}}"
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect SQLAlchemy ORM ↔ SQLite schema drift."
    )
    parser.add_argument(
        "--db", default="data/trading.db",
        help="Path to the sqlite DB to inspect. Default: data/trading.db",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress all output; exit code only.",
    )
    args = parser.parse_args()

    if not Path(args.db).exists():
        if not args.quiet:
            print(f"[error] database not found: {args.db}", file=sys.stderr)
        return 2

    drift = collect_drift(args.db)
    if not drift:
        if not args.quiet:
            print(f"[ok] no schema drift detected in {args.db} "
                  f"({len(_MODELS)} models checked)")
        return 0

    if not args.quiet:
        print(format_report(drift), file=sys.stderr)
        print(
            f"\n[fail] {len(drift)} table(s) drifted. Fix the model "
            "(storage/database.py) or apply a migration to the DB.",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
