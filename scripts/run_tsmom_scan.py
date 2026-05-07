"""Phase 6 Step 3 Tier A — daily TSMOM scanner (signal-only, no orders).

Runs once per day. For each symbol in the trimmed-4 universe
(USDJPY, XAUUSD, AUDUSD, EURUSD — see Phase 6 Step 2 follow-up,
commit 87f1df3), fetches D1 bars, computes TSMOM signal via
`strategies.tsmom.tsmom_strategy.compute_tsmom_signal`, and persists
one row to `tsmom_signal_log`.

This is the **signal-only** tier:
  - No order placement.
  - No position tracking against the broker.
  - The row records what TSMOM says the position direction + weight
    should be on this day. Tier B (separate ticket) will read these
    rows and decide whether to rebalance the live MT5 paper account.

The point of Tier A: validate the math on real broker D1 bars,
build a daily diagnostic record (which Step 4 monitoring needs
anyway), and decouple Step 3 progress from order-placement risk.

Usage:
  python scripts/run_tsmom_scan.py            # standard daily scan
  python scripts/run_tsmom_scan.py --dry-run  # compute + print only

Schedule: invoke once per day after 00:00 UTC (when D1 bar closes).
A Windows Task Scheduler entry at 00:30 UTC works."""
from __future__ import annotations

import argparse
import io
import sys
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from loguru import logger

from execution.broker_adapters.mt5_adapter import MT5Adapter
from features.technical.indicators import add_atr
from storage.database import SessionLocal, TSMOMSignalLog, init_db
from strategies.tsmom.tsmom_strategy import compute_tsmom_signal, is_rebalance_day

# Trimmed-4 universe per Phase 6 Step 2 follow-up (commit 87f1df3).
# Rationale: full 6-symbol portfolio Sharpe = 0.336 (FAIL gate);
# trimmed-4 dropping GBPUSD + USDCHF (the two negative-Sharpe
# symbols) achieves 0.554 (PASS).
TRIMMED_4_UNIVERSE = ["USDJPY", "XAUUSD", "AUDUSD", "EURUSD"]

# Need at least lookback_days + vol_window_days + 1 bars. Defaults:
# lookback=252, vol=60 → 313 minimum. Pull 400 to give headroom for
# the indicator warm-up and any missing bars.
BARS_TO_FETCH = 400

REBALANCE_FREQ = "monthly"


def fetch_last_rebalance(session, symbol: str) -> pd.Timestamp | None:
    """Most recent run_time where the prior row reported a rebalance day.

    Returns None on first-ever scan (table empty for this symbol)."""
    row = (
        session.query(TSMOMSignalLog)
        .filter(TSMOMSignalLog.symbol == symbol)
        .filter(TSMOMSignalLog.is_rebalance_day == True)  # noqa: E712 — SQLAlchemy
        .order_by(TSMOMSignalLog.run_time.desc())
        .first()
    )
    if row is None:
        return None
    return pd.Timestamp(row.run_time)


def scan_one_symbol(
    adapter: MT5Adapter,
    session,
    symbol: str,
    today: pd.Timestamp,
    *,
    dry_run: bool = False,
) -> dict | None:
    bars = adapter.get_ohlcv(symbol, "D1", BARS_TO_FETCH)
    if bars is None or bars.empty:
        logger.warning(f"  {symbol}: no D1 bars returned")
        return None

    if len(bars) < 313:
        logger.warning(f"  {symbol}: only {len(bars)} bars (need 313+); skip")
        return None

    bars = add_atr(bars, period=14)
    prices = bars["close"]
    atr_now = float(bars["atr_14"].iloc[-1]) if "atr_14" in bars.columns else None
    price_now = float(prices.iloc[-1])

    sig = compute_tsmom_signal(prices)
    if sig is None:
        logger.warning(f"  {symbol}: compute_tsmom_signal returned None")
        return None

    last_reb = fetch_last_rebalance(session, symbol)
    rebal = is_rebalance_day(today, last_reb, REBALANCE_FREQ)

    record = {
        "symbol": symbol,
        "direction": sig.direction,
        "raw_momentum": sig.raw_momentum,
        "target_weight": sig.target_weight,
        "vol_annualised": sig.vol_annualised,
        "price_now": price_now,
        "atr_14": atr_now,
        "is_rebalance_day": rebal,
        "last_rebalance": last_reb,
    }

    atr_str = f"{atr_now:.5f}" if atr_now is not None else "—"
    print(
        f"  {symbol:<7} {sig.direction:<5} mom={sig.raw_momentum:+.3f} "
        f"weight={sig.target_weight:.2f}x vol={sig.vol_annualised:.3f} "
        f"price={price_now:.5f} atr={atr_str} "
        f"rebal={'YES' if rebal else 'no'}"
    )

    if not dry_run:
        row = TSMOMSignalLog(
            run_time=today.to_pydatetime(),
            symbol=symbol,
            direction=sig.direction,
            raw_momentum=sig.raw_momentum,
            target_weight=sig.target_weight,
            vol_annualised=sig.vol_annualised,
            price_now=price_now,
            atr_14=atr_now,
            is_rebalance_day=rebal,
            last_rebalance=(last_reb.to_pydatetime() if last_reb is not None else None),
            notes=None,
        )
        session.add(row)

    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="compute + print, do not persist to DB")
    parser.add_argument("--symbols", default=",".join(TRIMMED_4_UNIVERSE),
                        help="comma-separated override of the universe")
    args = parser.parse_args()

    universe = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    today = pd.Timestamp.utcnow().normalize()

    print("=" * 78)
    print("  Phase 6 Step 3 — TSMOM daily scan")
    print(f"  Run: {datetime.now().isoformat(timespec='seconds')} (today UTC: {today.date()})")
    print(f"  Universe ({len(universe)}): {universe}")
    print(f"  Mode: {'DRY-RUN (no DB write)' if args.dry_run else 'LIVE (DB write)'}")
    print("=" * 78)

    init_db()

    adapter = MT5Adapter()
    if not adapter.connect():
        logger.error("MT5 connect failed")
        return 1

    session = SessionLocal()
    n_ok = 0
    try:
        for sym in universe:
            try:
                rec = scan_one_symbol(adapter, session, sym, today,
                                      dry_run=args.dry_run)
                if rec is not None:
                    n_ok += 1
            except Exception as e:
                logger.error(f"  {sym}: scan failed — {e}")
        if not args.dry_run:
            session.commit()
            print(f"\n  ✓ {n_ok}/{len(universe)} rows committed to tsmom_signal_log")
        else:
            print(f"\n  ✓ {n_ok}/{len(universe)} symbols scanned (dry-run)")
    except Exception as e:
        session.rollback()
        logger.error(f"scan run failed: {e}")
        return 2
    finally:
        session.close()
        adapter.disconnect()

    print("=" * 78)
    return 0 if n_ok == len(universe) else 3


if __name__ == "__main__":
    sys.exit(main())
