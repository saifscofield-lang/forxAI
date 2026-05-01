"""AI-017b Phase B backfill: apply exit_classifier to all closed trades.

Reads (open_price, close_price, stop_loss, take_profit, order_type,
atr_at_entry, exit_reason, symbol) for every closed trade in
trade_results and writes the classifier's refined verdict into
exit_reason_v2.

After backfill, prints a validation report:
- 10 known-mislabel rows (close ≈ open with profitable=1) showing
  old exit_reason, new exit_reason_v2, and price evidence
- 10 control rows (close near SL with profitable=0) — must keep
  SL_HIT, 0 false-positive tolerance
- Aggregate transition counts old → new
- Any rows the classifier returned None / NULL on
- Counts per new exit_reason_v2 value (incl. TRAILING_STOP=0
  surfaced explicitly, not as a bug)

Idempotent: re-running overwrites exit_reason_v2 with the same values
(classifier is deterministic).

Validation gate: this script does NOT commit changes to the
exit_reason column. Old labels are preserved for audit. Final
migration to exit_reason_v2 as the canonical column happens in a
separate session after spot-checks pass."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, ".")

from analysis.exit_classifier import classify_exit  # noqa: E402

DB_PATH = "data/trading.db"


def run_backfill(con: sqlite3.Connection) -> dict:
    """Apply classifier to every closed trade. Returns summary dict."""
    rows = con.execute(
        """
        SELECT t.ticket, t.symbol, t.order_type, t.open_price, t.close_price,
               t.stop_loss, t.take_profit, t.profit,
               tr.exit_reason, tr.atr_at_entry
        FROM trades t
        JOIN trade_results tr ON tr.ticket = t.ticket
        WHERE t.is_closed = 1
        """
    ).fetchall()

    if not rows:
        return {"total": 0, "transitions": {}, "nulls": [], "by_v2": {}}

    transitions: dict = {}
    nulls = []
    by_v2: dict = {}

    for r in rows:
        ticket, sym, side, op, cp, sl, tp, pnl, ex_old, atr = r
        v2 = classify_exit(
            open_price=op,
            close_price=cp,
            stop_loss=sl,
            take_profit=tp,
            order_type=side,
            atr_at_entry=atr,
            mt5_exit_tag=ex_old or "UNKNOWN",
            symbol=sym or "",
        )
        if v2 is None:
            nulls.append((ticket, sym, side, op, cp, sl, ex_old, atr))
            continue

        con.execute(
            "UPDATE trade_results SET exit_reason_v2 = ? WHERE ticket = ?",
            (v2, ticket),
        )
        key = (ex_old, v2)
        transitions[key] = transitions.get(key, 0) + 1
        by_v2[v2] = by_v2.get(v2, 0) + 1

    con.commit()
    return {
        "total": len(rows),
        "transitions": transitions,
        "nulls": nulls,
        "by_v2": by_v2,
    }


def fetch_known_mislabels(con: sqlite3.Connection, limit: int = 10) -> list:
    """Sample rows matching the empirical mislabel pattern: SL_HIT label
    + profitable + close ≈ open. These should reclassify to BE_HIT."""
    return con.execute(
        """
        SELECT t.ticket, t.symbol, t.order_type, t.open_price, t.close_price,
               t.stop_loss, t.profit, tr.exit_reason, tr.exit_reason_v2,
               tr.atr_at_entry
        FROM trades t
        JOIN trade_results tr ON tr.ticket = t.ticket
        WHERE tr.exit_reason = 'SL_HIT'
          AND tr.profitable = 1
          AND ABS(t.close_price - t.open_price) <
              0.10 * ABS(t.stop_loss - t.open_price)
        ORDER BY t.close_time DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def fetch_control_rows(con: sqlite3.Connection, limit: int = 10) -> list:
    """Sample rows that look like real adverse SL hits: SL_HIT label +
    not profitable + close near SL. Must stay SL_HIT after classifier
    runs. Zero false-positive tolerance."""
    return con.execute(
        """
        SELECT t.ticket, t.symbol, t.order_type, t.open_price, t.close_price,
               t.stop_loss, t.profit, tr.exit_reason, tr.exit_reason_v2,
               tr.atr_at_entry
        FROM trades t
        JOIN trade_results tr ON tr.ticket = t.ticket
        WHERE tr.exit_reason = 'SL_HIT'
          AND tr.profitable = 0
          AND ABS(t.close_price - t.stop_loss) <
              0.10 * ABS(t.stop_loss - t.open_price)
        ORDER BY ABS(t.profit) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def _fmt_distance(open_p, close_p, sl_p) -> str:
    move = abs(close_p - open_p) if (open_p and close_p) else 0
    sl_dist = abs(sl_p - open_p) if (sl_p and open_p) else 0
    pct = (move / sl_dist * 100) if sl_dist else 0
    return f"|close-open|={move:.4f}  |sl-open|={sl_dist:.4f}  ratio={pct:.1f}%"


def print_report(summary: dict, mislabels: list, controls: list) -> None:
    print()
    print("=" * 78)
    print(" AI-017b Phase B — Validation Report")
    print("=" * 78)
    print()
    print(f"Total closed trades classified: {summary['total']}")
    print()

    print("─── Aggregate transition counts (old exit_reason → exit_reason_v2) ───")
    if summary["transitions"]:
        sorted_t = sorted(summary["transitions"].items(),
                          key=lambda x: -x[1])
        for (old, new), n in sorted_t:
            arrow = "==" if old == new else "->"
            print(f"  {old:>10} {arrow} {new:<15}  n={n}")
    else:
        print("  (no transitions recorded)")
    print()

    print("─── Distribution of new exit_reason_v2 ───")
    expected_vals = ["SL_HIT", "TP_HIT", "BE_HIT", "TRAILING_STOP",
                     "MANUAL", "UNKNOWN"]
    for v in expected_vals:
        n = summary["by_v2"].get(v, 0)
        marker = ""
        if v == "TRAILING_STOP" and n == 0:
            marker = " (expected — see Phase A note; not a bug)"
        print(f"  {v:<15} n={n:<5}{marker}")
    print()

    if summary["nulls"]:
        print(f"─── Classifier returned None / NULL on {len(summary['nulls'])} rows ───")
        for n in summary["nulls"]:
            print(f"  ticket={n[0]} sym={n[1]} side={n[2]} "
                  f"open={n[3]} close={n[4]} sl={n[5]} ex_old={n[6]} atr={n[7]}")
        print()
    else:
        print("─── Classifier indecisions (NULL exit_reason_v2): 0 ───")
        print()

    print("─── 10 KNOWN-MISLABEL ROWS (expected to reclassify to BE_HIT) ───")
    if not mislabels:
        print("  (none found — query returned 0 rows)")
    else:
        for r in mislabels:
            ticket, sym, side, op, cp, sl, pnl, ex_old, ex_v2, atr = r
            ev = _fmt_distance(op, cp, sl)
            mark = "✓" if ex_v2 == "BE_HIT" else "✗ UNEXPECTED"
            print(f"  {mark} ticket={ticket} {sym}/{side}  pnl=${pnl:+.2f}  "
                  f"old={ex_old} -> new={ex_v2}")
            print(f"        {ev}  atr={atr}")
    print()

    print("─── 10 CONTROL ROWS (real SL hits — must stay SL_HIT) ───")
    if not controls:
        print("  (none found — query returned 0 rows)")
    else:
        false_positives = 0
        for r in controls:
            ticket, sym, side, op, cp, sl, pnl, ex_old, ex_v2, atr = r
            ev = _fmt_distance(op, cp, sl)
            ok = ex_v2 == "SL_HIT"
            mark = "✓" if ok else "✗ FALSE POSITIVE"
            if not ok:
                false_positives += 1
            print(f"  {mark} ticket={ticket} {sym}/{side}  pnl=${pnl:+.2f}  "
                  f"old={ex_old} -> new={ex_v2}")
            print(f"        {ev}  atr={atr}")
        print()
        print(f"  Control false-positive count: {false_positives} / {len(controls)}")
        if false_positives > 0:
            print("  ✗ STOP — false positives present. Adjust threshold before commit.")
        else:
            print("  ✓ Zero false positives. Validation gate cleared.")
    print()
    print("=" * 78)


def main() -> int:
    if not Path(DB_PATH).exists():
        print(f"[backfill] {DB_PATH} not found", file=sys.stderr)
        return 1

    con = sqlite3.connect(DB_PATH)
    try:
        # Verify column exists before backfill
        cols = [r[1] for r in con.execute(
            "PRAGMA table_info(trade_results)"
        ).fetchall()]
        if "exit_reason_v2" not in cols:
            print(
                "[backfill] trade_results.exit_reason_v2 missing — "
                "run scripts/migrate_add_exit_reason_v2.py first",
                file=sys.stderr,
            )
            return 1

        summary = run_backfill(con)
        mislabels = fetch_known_mislabels(con, limit=10)
        controls = fetch_control_rows(con, limit=10)
        print_report(summary, mislabels, controls)
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
