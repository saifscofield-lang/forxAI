"""
Rejected-Signal Evidence Audit  (Rescue Plan — Phase 1, READ-ONLY)
==================================================================
Goal: quantify which filters block PROFITABLE signals vs which protect us.

For every signal in signal_logs (EXECUTED + REJECTED) we reconstruct the
forward outcome from the market_contexts h1_close path and check whether the
signal's own TP or SL would have been hit FIRST. Then we group by the reason
a signal was rejected (the "filter bucket") and report would-win rates.

This does NOT touch any trading code or live state. It only reads trading.db
and writes a markdown report. Safe to run during the freeze.

Limitation: market_contexts stores hourly CLOSES only (no high/low), so a
barrier "touch" is approximated by a close crossing the level. This UNDER-
counts touches vs real high/low, but applies equally to all buckets, so the
relative comparison between filters remains valid.

Usage:
    python scripts/audit_rejected_signals.py
"""
import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, ".")

DB = Path("data/trading.db")
OUT = Path("docs/research/rescue_phase1_signal_audit.md")
HORIZON_BARS = 24  # how many forward hourly closes to evaluate (~1 trading day)


def bucket_for(status, reason):
    """Classify each signal into a filter bucket."""
    if status == "EXECUTED":
        return "EXECUTED"
    if status == "NEWS_FILTERED":
        return "NEWS"
    r = (reason or "")
    if r.startswith("H4 trend"):
        return "H4_TREND"
    if r.startswith("Session filter"):
        return "SESSION"
    if r.startswith("Position already open"):
        return "DEDUP_SAME"
    if r.startswith("Conflicting"):
        return "DEDUP_CONFLICT"
    if r.startswith("Max positions"):
        return "MAX_POS_DD"
    if ("filling mode" in r) or r.startswith("AutoTrading") or r.startswith("No money"):
        return "EXEC_ERROR"
    return "OTHER"


def load_price_paths(cur):
    """symbol -> sorted list of (time_str, h1_close)."""
    paths = defaultdict(list)
    for sym, t, c in cur.execute(
        "SELECT symbol, time, h1_close FROM market_contexts "
        "WHERE h1_close IS NOT NULL ORDER BY symbol, time"
    ):
        paths[sym].append((t, c))
    return paths


def outcome(action, entry, sl, tp, path, t_signal):
    """
    Walk forward through closes after t_signal. Return:
      'WIN'  if TP reached before SL
      'LOSS' if SL reached before TP
      'TIMEOUT' if neither within HORIZON_BARS
      None if no forward data / bad inputs
    """
    if entry is None or sl is None or tp is None:
        return None
    fwd = [c for (t, c) in path if t > t_signal][:HORIZON_BARS]
    if not fwd:
        return None
    for c in fwd:
        if action == "BUY":
            if c >= tp:
                return "WIN"
            if c <= sl:
                return "LOSS"
        else:  # SELL
            if c <= tp:
                return "WIN"
            if c >= sl:
                return "LOSS"
    return "TIMEOUT"


def main():
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    paths = load_price_paths(cur)

    rows = cur.execute(
        "SELECT time, symbol, action, price, stop_loss, take_profit, status, reason, strategy "
        "FROM signal_logs ORDER BY time"
    ).fetchall()

    stats = defaultdict(lambda: {"WIN": 0, "LOSS": 0, "TIMEOUT": 0, "NODATA": 0, "total": 0})
    for t, sym, action, price, sl, tp, status, reason, strat in rows:
        b = bucket_for(status, reason)
        stats[b]["total"] += 1
        if action not in ("BUY", "SELL"):
            stats[b]["NODATA"] += 1
            continue
        res = outcome(action, price, sl, tp, paths.get(sym, []), t)
        stats[b][res or "NODATA"] += 1

    # ── Build report ────────────────────────────────────────────────
    lines = []
    lines.append("# Rescue Plan — Phase 1: Rejected-Signal Evidence Audit\n")
    lines.append("**Data window:** trading.db (2026-03-17 → 2026-03-27, pre-freeze)")
    lines.append(f"**Method:** forward h1_close path, horizon={HORIZON_BARS} bars, "
                 "signal's own SL/TP as barriers (close-cross proxy).\n")
    lines.append("> Win% = of signals with a decided outcome (WIN+LOSS), how many hit TP first.\n")

    lines.append("| Bucket | Signals | Decided | WIN | LOSS | Timeout | NoData | **Win% (decided)** |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    order = ["EXECUTED", "H4_TREND", "SESSION", "DEDUP_SAME", "DEDUP_CONFLICT",
             "MAX_POS_DD", "NEWS", "EXEC_ERROR", "OTHER"]
    for b in order:
        if b not in stats:
            continue
        s = stats[b]
        decided = s["WIN"] + s["LOSS"]
        wr = f"{100*s['WIN']/decided:.0f}%" if decided else "—"
        lines.append(f"| {b} | {s['total']} | {decided} | {s['WIN']} | {s['LOSS']} | "
                     f"{s['TIMEOUT']} | {s['NODATA']} | **{wr}** |")

    # Interpretation helper
    lines.append("\n## Reading this table\n")
    lines.append("- **EXECUTED** is the baseline: the win-rate of trades we actually took "
                 "(by this close-proxy measure). Compare every filtered bucket against it.")
    lines.append("- A filtered bucket with **Win% >= EXECUTED** means that filter is "
                 "**blocking trades as good as the ones we keep** → candidate to LOOSEN.")
    lines.append("- A filtered bucket with **Win% well below EXECUTED** means the filter is "
                 "**protecting us** → KEEP.")
    lines.append("- **EXEC_ERROR** are NOT strategy decisions — they are broker/config "
                 "failures (filling mode, AutoTrading off, No money). Any win% here is lost "
                 "P&L from bugs, not risk policy → FIX regardless of win%.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    con.close()

    # Also print to console
    print("\n".join(lines))
    print(f"\nReport written: {OUT}")


if __name__ == "__main__":
    main()
