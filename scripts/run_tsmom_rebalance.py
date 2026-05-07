"""Phase 6 Step 3 Tier B — TSMOM rebalance executor.

Reads the latest row per symbol from `tsmom_signal_log` (written by
`scripts/run_tsmom_scan.py`), inspects current MT5 positions, and
either prints the rebalance plan (default, --dry-run) or executes
it (--execute). Default is dry-run for safety: live order placement
is opt-in.

Position identification: TSMOM positions are tagged with the
comment "TSMOM-{rebalance_date}" so the executor can find its own
positions without entangling v3 strategy positions in the same
account.

Sizing (per signal):
    notional   = balance × ALLOC_PCT × target_weight
    lots       = notional / (price × contract_size)

ALLOC_PCT defaults to 1% per symbol (4 symbols × 1% = 4% gross
exposure budget on the demo account, modulo vol-targeting which
already sized weight to the 10% vol target). This is intentionally
small for the paper-trading bootstrap.

Usage:
  python scripts/run_tsmom_rebalance.py             # dry-run print
  python scripts/run_tsmom_rebalance.py --execute   # live orders
"""
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
from storage.database import SessionLocal, TSMOMSignalLog

# Per-symbol allocation as a fraction of equity. With 4 symbols, the
# full universe gross-exposure budget is 4 × this. Conservative
# default for paper-trade bootstrap; raise via CLI when comfortable.
DEFAULT_ALLOC_PCT = 0.01      # 1% per symbol

# MT5 contract sizes for the trimmed-4 universe. Standard FX = 100k;
# XAUUSD on most retail brokers is 100 oz (notional = price × 100).
# Verified against MT5 symbol_info.trade_contract_size at load time
# rather than hard-coding here would be more robust, but for a known
# universe these values are stable.
CONTRACT_SIZES = {
    "EURUSD": 100_000,
    "AUDUSD": 100_000,
    "USDJPY": 100_000,
    "XAUUSD": 100,
}

REBAL_COMMENT_PREFIX = "TSMOM-"


def latest_signal_per_symbol(session) -> pd.DataFrame:
    """Pull the most-recent row per symbol from tsmom_signal_log."""
    rows = (
        session.query(TSMOMSignalLog)
        .order_by(TSMOMSignalLog.run_time.desc(), TSMOMSignalLog.id.desc())
        .all()
    )
    seen = {}
    for r in rows:
        if r.symbol not in seen:
            seen[r.symbol] = r
    if not seen:
        return pd.DataFrame()
    df = pd.DataFrame([{
        "symbol": r.symbol,
        "direction": r.direction,
        "raw_momentum": r.raw_momentum,
        "target_weight": r.target_weight,
        "vol_annualised": r.vol_annualised,
        "price_now": r.price_now,
        "atr_14": r.atr_14,
        "is_rebalance_day": r.is_rebalance_day,
        "run_time": r.run_time,
    } for r in seen.values()])
    return df.sort_values("symbol").reset_index(drop=True)


def existing_tsmom_position(positions: pd.DataFrame, symbol: str) -> dict | None:
    """First TSMOM-tagged position on this symbol, or None."""
    if positions.empty:
        return None
    sub = positions[
        (positions["symbol"] == symbol)
        & (positions["comment"].astype(str).str.startswith(REBAL_COMMENT_PREFIX))
    ]
    if sub.empty:
        return None
    row = sub.iloc[0]
    return {
        "ticket": int(row["ticket"]),
        "type": row["type"],
        "volume": float(row["volume"]),
        "open_price": float(row["open_price"]),
        "comment": row["comment"],
    }


def compute_lots(
    balance: float,
    alloc_pct: float,
    target_weight: float,
    price: float,
    contract_size: int,
) -> float:
    """Round to 2 decimals (standard MT5 lot precision); minimum 0.01."""
    notional = balance * alloc_pct * target_weight
    raw = notional / (price * contract_size)
    return max(0.01, round(raw, 2))


def plan_actions(
    signals: pd.DataFrame,
    positions: pd.DataFrame,
    balance: float,
    alloc_pct: float,
) -> list[dict]:
    """Compute rebalance actions per symbol. Returns plan list."""
    plan = []
    for _, sig in signals.iterrows():
        symbol = sig["symbol"]
        contract = CONTRACT_SIZES.get(symbol)
        if contract is None:
            plan.append({"symbol": symbol, "action": "SKIP",
                         "reason": "no contract size mapping"})
            continue
        lots = compute_lots(balance, alloc_pct, sig["target_weight"],
                            sig["price_now"], contract)
        existing = existing_tsmom_position(positions, symbol)

        # Bootstrap: if no existing TSMOM position on this symbol, open
        # one regardless of is_rebalance_day. The flag is only meaningful
        # once a position exists and we're deciding whether to flip it.
        if existing is None and not sig["is_rebalance_day"]:
            plan.append({"symbol": symbol, "action": "OPEN",
                         "direction": sig["direction"], "lots": lots,
                         "price": sig["price_now"],
                         "reason": "bootstrap (no existing TSMOM position)"})
            continue
        if not sig["is_rebalance_day"] and existing is not None:
            plan.append({"symbol": symbol, "action": "HOLD",
                         "reason": f"keep existing #{existing['ticket']} until next rebalance",
                         "existing": existing})
            continue

        # Rebalance day → action depends on direction vs existing
        if existing is None:
            plan.append({"symbol": symbol, "action": "OPEN",
                         "direction": sig["direction"], "lots": lots,
                         "price": sig["price_now"]})
        elif existing["type"] == sig["direction"]:
            plan.append({"symbol": symbol, "action": "NO_FLIP",
                         "reason": f"direction unchanged ({sig['direction']})",
                         "existing": existing,
                         "would_size_to": lots})
        else:
            plan.append({"symbol": symbol, "action": "FLIP",
                         "from_direction": existing["type"],
                         "to_direction": sig["direction"],
                         "lots": lots, "price": sig["price_now"],
                         "existing": existing})
    return plan


def execute_action(adapter: MT5Adapter, action: dict, today: pd.Timestamp) -> dict:
    """Execute one planned action against MT5. Returns result dict."""
    sym = action["symbol"]
    rebal_tag = f"{REBAL_COMMENT_PREFIX}{today.date().isoformat()}"

    if action["action"] in ("WAIT", "HOLD", "NO_FLIP", "SKIP"):
        return {"action": action["action"], "symbol": sym, "executed": False}

    if action["action"] == "FLIP":
        close_res = adapter.close_position(action["existing"]["ticket"])
        if not close_res.get("success"):
            return {"symbol": sym, "executed": False,
                    "error": f"close failed: {close_res.get('error')}"}

    # OPEN or FLIP-into-new
    open_res = adapter.place_order(
        symbol=sym,
        order_type=action["direction"] if action["action"] == "OPEN" else action["to_direction"],
        volume=action["lots"],
        stop_loss=0.0,
        take_profit=0.0,
        comment=rebal_tag,
    )
    return {"symbol": sym, "executed": open_res.get("success", False),
            "ticket": open_res.get("ticket"),
            "fill_price": open_res.get("filled_price"),
            "comment": rebal_tag,
            "error": open_res.get("error") if not open_res.get("success") else None}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true",
                        help="Execute the plan via MT5 (default = dry-run print only)")
    parser.add_argument("--alloc-pct", type=float, default=DEFAULT_ALLOC_PCT,
                        help=f"Per-symbol allocation as fraction of equity (default {DEFAULT_ALLOC_PCT})")
    args = parser.parse_args()

    today = pd.Timestamp.utcnow().normalize()
    print("=" * 78)
    print("  Phase 6 Step 3 Tier B — TSMOM rebalance")
    print(f"  Run: {datetime.now().isoformat(timespec='seconds')} (today UTC: {today.date()})")
    print(f"  Mode: {'EXECUTE (live MT5 orders)' if args.execute else 'DRY-RUN (print plan)'}")
    print(f"  Alloc per symbol: {args.alloc_pct*100:.2f}% of equity")
    print("=" * 78)

    session = SessionLocal()
    try:
        signals = latest_signal_per_symbol(session)
        if signals.empty:
            print("  No signals in tsmom_signal_log — run scripts/run_tsmom_scan.py first")
            return 1
        print(f"  Loaded latest signals for {len(signals)} symbols\n")
    finally:
        session.close()

    adapter = MT5Adapter()
    if not adapter.connect():
        logger.error("MT5 connect failed")
        return 2

    try:
        account = adapter.get_account_info()
        balance = float(account["balance"])
        positions = adapter.get_open_positions()
        n_tsmom_pos = 0
        if not positions.empty:
            n_tsmom_pos = int(positions["comment"].astype(str)
                              .str.startswith(REBAL_COMMENT_PREFIX).sum())
        print(f"  Account balance: ${balance:,.2f}  | "
              f"Open positions: {len(positions)}  | "
              f"TSMOM-tagged: {n_tsmom_pos}\n")

        plan = plan_actions(signals, positions, balance, args.alloc_pct)

        # Print the plan
        print("  Plan:")
        print(f"    {'symbol':<7} {'action':<8} {'detail':<60}")
        print(f"    {'-'*7} {'-'*8} {'-'*60}")
        for a in plan:
            if a["action"] == "OPEN":
                detail = f"{a['direction']} {a['lots']} lots @ ~{a['price']:.5f}"
            elif a["action"] == "FLIP":
                detail = (f"close #{a['existing']['ticket']} ({a['from_direction']}), "
                          f"open {a['to_direction']} {a['lots']} lots")
            elif a["action"] == "NO_FLIP":
                detail = f"keep #{a['existing']['ticket']} ({a.get('reason','')})"
            elif a["action"] == "HOLD":
                detail = f"keep #{a['existing']['ticket']} until next rebalance"
            elif a["action"] == "WAIT":
                detail = a.get("reason", "")
            else:
                detail = a.get("reason", "")
            print(f"    {a['symbol']:<7} {a['action']:<8} {detail}")

        if not args.execute:
            print("\n  DRY-RUN — no orders placed. Re-run with --execute to apply.")
            return 0

        print("\n  Executing...")
        n_exec = 0
        for a in plan:
            res = execute_action(adapter, a, today)
            if res.get("executed"):
                n_exec += 1
                print(f"    ✓ {res['symbol']:<7} ticket #{res['ticket']} "
                      f"@ {res.get('fill_price')} ({res.get('comment')})")
            elif res.get("error"):
                print(f"    ✗ {res['symbol']:<7} {res['error']}")
        print(f"\n  Executed {n_exec} of {len(plan)} actions")
        return 0
    finally:
        adapter.disconnect()


if __name__ == "__main__":
    sys.exit(main())
