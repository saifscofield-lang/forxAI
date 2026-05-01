"""AI-017b Phase B — manual verification samples.

Prints 5 deterministic TRAILING_STOP samples, 3 BE_HIT samples, and 2
highest-loss SL_HIT controls. Each row shows original SL (from
signal_logs), close-time SL (from trades), distances, time held, and
classifier verdict. Flags any row where original_sl is missing.

Used at the AI-017b validation gate to spot-check the 137-trade
reclassification before commit."""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, ".")

DB_PATH = "data/trading.db"


def deterministic_sample(con: sqlite3.Connection, where: str, n: int) -> list:
    """Pick `n` evenly-spaced tickets matching `where` (after
    is_closed=1 + the join). Reproducible across runs."""
    all_t = con.execute(
        f"""SELECT t.ticket FROM trades t
            JOIN trade_results tr ON tr.ticket = t.ticket
            WHERE t.is_closed = 1 AND {where}
            ORDER BY t.ticket"""
    ).fetchall()
    if not all_t:
        return []
    tickets = [r[0] for r in all_t]
    if len(tickets) <= n:
        picked = tickets
    else:
        step = len(tickets) // n
        picked = [tickets[i * step] for i in range(n)]
    placeholders = ",".join("?" * len(picked))
    return con.execute(
        f"""SELECT t.ticket, t.symbol, t.order_type, t.strategy,
                   t.open_time, t.close_time, t.open_price, t.close_price,
                   t.stop_loss AS sl_at_close, t.take_profit, t.profit,
                   tr.atr_at_entry, tr.exit_reason, tr.exit_reason_v2,
                   sl.stop_loss AS sl_at_signal
            FROM trades t
            JOIN trade_results tr ON tr.ticket = t.ticket
            LEFT JOIN signal_logs sl ON sl.ticket = t.ticket
            WHERE t.ticket IN ({placeholders})
            ORDER BY t.ticket""",
        picked,
    ).fetchall()


def render(rows: list, expected: str) -> None:
    for r in rows:
        (ticket, sym, side, strat, open_t, close_t, op, cp, sl_close, tp,
         pnl, atr, ex_old, ex_v2, sl_signal) = r

        # Time held
        try:
            t1 = datetime.fromisoformat(str(open_t).split(".")[0])
            t2 = datetime.fromisoformat(str(close_t).split(".")[0])
            held = str(t2 - t1)
        except Exception:
            held = "?"

        move = abs(cp - op) if (cp is not None and op is not None) else None
        sl_dist_orig = (
            abs(sl_signal - op) if (sl_signal is not None and op is not None) else None
        )
        sl_to_close_orig = (
            abs(sl_signal - cp) if (sl_signal is not None and cp is not None) else None
        )

        if side and op is not None and cp is not None:
            signed_move = (cp - op) if side.upper() == "BUY" else (op - cp)
            if signed_move > 0:
                fav = "FAVORABLE"
            elif signed_move < 0:
                fav = "ADVERSE"
            else:
                fav = "NEUTRAL"
        else:
            signed_move = None
            fav = "?"

        ratio_orig = (
            (move / sl_dist_orig * 100) if (move is not None and sl_dist_orig)
            else None
        )
        ratio_at_orig_sl = (
            (sl_to_close_orig / sl_dist_orig * 100)
            if (sl_to_close_orig is not None and sl_dist_orig)
            else None
        )

        sl_modified = "?"
        if sl_signal is not None and sl_close is not None:
            sl_modified = "yes" if abs(sl_signal - sl_close) > 1e-9 else "no"

        pnl_str = f"USD {pnl:+.2f}" if pnl is not None else "USD ?"
        ratio_str = f"{ratio_orig:.1f}%" if ratio_orig is not None else "?"
        ratio_to_sl_str = (
            f"{ratio_at_orig_sl:.1f}%" if ratio_at_orig_sl is not None else "?"
        )

        print(f"  ticket={ticket}  {sym}/{side}  strategy={strat}")
        print(f"    times:  open={open_t}  close={close_t}  held={held}")
        print(f"    prices: open={op}  close={cp}  tp={tp}")
        print(f"    SL:     at_signal={sl_signal}  at_close={sl_close}  modified={sl_modified}")
        print(
            f"    move:   |close-open|={move}  |sl_orig-open|={sl_dist_orig}  "
            f"ratio={ratio_str}  direction={fav}"
        )
        print(
            f"    sl_gap: |close-sl_orig|={sl_to_close_orig}  "
            f"ratio_to_orig_sl={ratio_to_sl_str}  "
            f"(0% = trade hit original SL; high% = trade did NOT reach original SL)"
        )
        print(f"    pnl: {pnl_str}    atr_at_entry={atr}")
        print(f"    verdict: old={ex_old} -> new={ex_v2}    expected={expected}")
        if sl_signal is None:
            print(
                "    !! FLAG: original_sl unavailable from signal_logs — classifier "
                "decision was based on close-to-open distance alone."
            )
        print()


def main() -> int:
    if not Path(DB_PATH).exists():
        print(f"{DB_PATH} not found", file=sys.stderr)
        return 1
    con = sqlite3.connect(DB_PATH)
    try:
        print("=" * 82)
        print(" SAMPLE 1 - TRAILING_STOP verification (5 deterministic samples)")
        print("=" * 82)
        print()
        render(
            deterministic_sample(con, "tr.exit_reason_v2 = 'TRAILING_STOP'", 5),
            "TRAILING_STOP - favorable + close NOT at original_sl",
        )

        print("=" * 82)
        print(" SAMPLE 2 - BE_HIT verification (3 deterministic samples)")
        print("=" * 82)
        print()
        render(
            deterministic_sample(con, "tr.exit_reason_v2 = 'BE_HIT'", 3),
            "BE_HIT - close near entry, small pnl",
        )

        print("=" * 82)
        print(" SAMPLE 3 - SL_HIT control (2 highest-loss samples)")
        print("=" * 82)
        print()
        controls = con.execute(
            """SELECT t.ticket, t.symbol, t.order_type, t.strategy,
                      t.open_time, t.close_time, t.open_price, t.close_price,
                      t.stop_loss, t.take_profit, t.profit,
                      tr.atr_at_entry, tr.exit_reason, tr.exit_reason_v2,
                      sl.stop_loss
               FROM trades t JOIN trade_results tr ON tr.ticket = t.ticket
               LEFT JOIN signal_logs sl ON sl.ticket = t.ticket
               WHERE tr.exit_reason_v2 = 'SL_HIT'
               ORDER BY t.profit ASC LIMIT 2"""
        ).fetchall()
        render(controls, "SL_HIT - close at original_sl, real loss")

        print("=" * 82)
        print(" SUMMARY")
        print("=" * 82)
        n = 5 + 3 + 2
        n_unavail = 0
        for r in controls:
            if r[14] is None:
                n_unavail += 1
        # Plus the trailing/be samples — re-fetch quickly for accurate count
        for label, where, k in [
            ("trail", "tr.exit_reason_v2 = 'TRAILING_STOP'", 5),
            ("be", "tr.exit_reason_v2 = 'BE_HIT'", 3),
        ]:
            for r in deterministic_sample(con, where, k):
                if r[14] is None:
                    n_unavail += 1
        print(f" Total samples shown: {n}")
        print(f" Rows with original_sl unavailable: {n_unavail} / {n}")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
