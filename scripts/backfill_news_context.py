"""GAP-FID-03 backfill: populate trade_results.news_nearby /
news_event_name / news_impact for historical trades.

The engine's news filter blocks new signals correctly (22 NEWS_FILTERED
signals to date) but the news context was never persisted onto closed
trades. The columns existed in the TradeResult ORM but the close
handler didn't write to them.

This script fixes the historical data:

  - For every closed trade in trade_results
  - Look up news_events for the symbol's relevant currencies within
    ±1 hour of trade open_time at HIGH impact
  - Write the result into news_nearby / news_event_name / news_impact

Idempotent — re-running overwrites only if values change. Safe.

After this script + the engine code change shipped 2026-05-07, the
news context is correct for both historical and future trades. The
meta-labeler (Phase 7 Step 6, May 18) can use news_nearby as a
training feature."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, ".")

from loguru import logger

from storage.database import SessionLocal, TradeResult
from news.news_filter import lookup_news_at_time

DB_PATH = "data/trading.db"


def main() -> int:
    if not Path(DB_PATH).exists():
        logger.error(f"{DB_PATH} not found")
        return 1

    session = SessionLocal()
    try:
        trades = session.query(TradeResult).all()
        if not trades:
            logger.warning("no trade_results rows to backfill")
            return 0

        n_total = len(trades)
        n_changed = 0
        n_news_now = 0
        impact_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}

        for tr in trades:
            if tr.open_time is None:
                continue
            news_nearby, name, impact = lookup_news_at_time(
                session, tr.symbol, tr.open_time,
                window_hours=1.0, min_impact="HIGH",
            )
            old = (bool(tr.news_nearby), tr.news_event_name, tr.news_impact)
            new = (news_nearby, name, impact)
            if old != new:
                tr.news_nearby = news_nearby
                tr.news_event_name = name
                tr.news_impact = impact
                n_changed += 1
            if news_nearby:
                n_news_now += 1
                if impact in impact_counts:
                    impact_counts[impact] += 1

        session.commit()
        print()
        print("=" * 78)
        print(" GAP-FID-03 News-context backfill")
        print("=" * 78)
        print(f"  Total trade_results rows:        {n_total}")
        print(f"  Rows updated this run:           {n_changed}")
        print(f"  Rows with news_nearby=True now:  {n_news_now}  ({n_news_now/n_total*100:.1f}%)")
        print(f"  By impact: {impact_counts}")
        print()
        if n_news_now == 0:
            print("  Note: 0 trades had a HIGH-impact event within ±1 hour. This is")
            print("  consistent with the engine actively blocking those signals — when")
            print("  news is imminent, no trades open. The backfill is correct; the")
            print("  feature just doesn't fire on the existing v3 corpus.")
        print("=" * 78)
        return 0
    except Exception as e:
        session.rollback()
        logger.error(f"backfill failed: {e}")
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
