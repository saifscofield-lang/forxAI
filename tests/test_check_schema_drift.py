"""Unit tests for scripts/check_schema_drift.py.

Builds a synthetic sqlite DB, populates it with copies of the real
ORM tables minus or plus deliberate columns, runs the drift detector
against it, and asserts the report matches.

Pytest-free runner at the bottom (matches the rest of the project).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

from sqlalchemy import create_engine

import storage.database as _db
from scripts.check_schema_drift import collect_drift, format_report


# ── Fixtures ─────────────────────────────────────────────────────────────────

def make_synthetic_db(path: str, schemas: dict[str, list[str]]) -> None:
    """Create a sqlite DB with hand-rolled tables.

    `schemas` maps table name → list of column-definition strings, e.g.
    {"trade_results": ["id INTEGER", "ticket INTEGER", ...]}."""
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        for table, columns in schemas.items():
            from sqlalchemy import text
            conn.execute(text(f"CREATE TABLE {table} ({', '.join(columns)})"))
    engine.dispose()


def expected_columns_for(model) -> list[str]:
    """Return the list of column names the ORM declares for a model."""
    return [c.name for c in model.__table__.columns]


# ── Tests ───────────────────────────────────────────────────────────────────

def test_no_drift_when_db_matches_models():
    """Build synthetic DB with all 18 ORM tables matching declared columns
    exactly. Detector should report no drift."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "match.db"
        # Use SQLAlchemy's create_all() against a fresh engine — the
        # canonical "ORM == DB" baseline.
        engine = create_engine(f"sqlite:///{db}")
        _db.Base.metadata.create_all(engine)
        engine.dispose()

        drift = collect_drift(str(db))
        assert drift == {}, f"expected no drift, got: {drift}"


def test_detects_missing_column():
    """Hand-build a DB where trade_results lacks a declared column.
    Detector should report it under missing_in_db."""
    declared = expected_columns_for(_db.TradeResult)
    # Drop the close_comment column on disk (it's nullable so we can
    # safely omit it for the synthetic test).
    cols_minus_one = [c for c in declared if c != "close_comment"]
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "missing.db"
        # Use SQLAlchemy.create_all to set up baseline, then drop+recreate
        # trade_results without close_comment.
        engine = create_engine(f"sqlite:///{db}")
        _db.Base.metadata.create_all(engine)
        with engine.begin() as conn:
            from sqlalchemy import text
            conn.execute(text("DROP TABLE trade_results"))
            conn.execute(text(
                "CREATE TABLE trade_results (" + ", ".join(
                    f"{c} TEXT" for c in cols_minus_one
                ) + ")"
            ))
        engine.dispose()

        drift = collect_drift(str(db))
        assert "trade_results" in drift, f"expected trade_results drift, got: {drift}"
        assert "close_comment" in drift["trade_results"]["missing_in_db"]
        assert drift["trade_results"]["extra_in_db"] == []


def test_detects_extra_column():
    """Hand-build a DB where trade_results has an unexpected extra
    column. Detector should report it under extra_in_db."""
    declared = expected_columns_for(_db.TradeResult)
    cols_plus_one = list(declared) + ["sentiment_score"]
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "extra.db"
        engine = create_engine(f"sqlite:///{db}")
        _db.Base.metadata.create_all(engine)
        with engine.begin() as conn:
            from sqlalchemy import text
            conn.execute(text("DROP TABLE trade_results"))
            conn.execute(text(
                "CREATE TABLE trade_results (" + ", ".join(
                    f"{c} TEXT" for c in cols_plus_one
                ) + ")"
            ))
        engine.dispose()

        drift = collect_drift(str(db))
        assert "trade_results" in drift
        assert "sentiment_score" in drift["trade_results"]["extra_in_db"]
        assert drift["trade_results"]["missing_in_db"] == []


def test_detects_entirely_missing_table():
    """Hand-build a DB where the ohlcv_bars table is missing. Detector
    should report table_missing=True with all declared columns."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "no_table.db"
        engine = create_engine(f"sqlite:///{db}")
        _db.Base.metadata.create_all(engine)
        with engine.begin() as conn:
            from sqlalchemy import text
            conn.execute(text("DROP TABLE ohlcv_bars"))
        engine.dispose()

        drift = collect_drift(str(db))
        assert "ohlcv_bars" in drift
        assert drift["ohlcv_bars"]["table_missing"] is True
        # All declared columns appear under missing_in_db
        declared = set(expected_columns_for(_db.OHLCVBar))
        assert set(drift["ohlcv_bars"]["missing_in_db"]) == declared


def test_format_report_empty():
    assert format_report({}) == ""


def test_format_report_renders_drift():
    drift = {
        "trade_results": {
            "missing_in_db": ["close_comment"],
            "extra_in_db": ["sentiment_score"],
            "table_missing": False,
        },
    }
    out = format_report(drift)
    assert "trade_results" in out
    assert "close_comment" in out
    assert "sentiment_score" in out


def test_format_report_renders_missing_table():
    drift = {
        "ohlcv_bars": {
            "missing_in_db": ["id", "symbol"],
            "extra_in_db": [],
            "table_missing": True,
        },
    }
    out = format_report(drift)
    assert "ohlcv_bars" in out
    assert "ENTIRE TABLE missing" in out


# ── Pytest-free runner ─────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    fail = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            fail += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            fail += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print()
    print(f"{len(tests) - fail}/{len(tests)} pass")
    sys.exit(0 if fail == 0 else 1)
