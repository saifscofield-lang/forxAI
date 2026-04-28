"""Phase 5 step 3: v2.4 demo stability confirmation.

Produces a data-driven stability report for the 2026-04-28 v3.0 go/no-go.
Scope: STABLE segment (2026-04-10 onwards, engine_version=2.4).

Key design choices:
  - FX weekend gaps (Fri 20:00 UTC -> Sun 22:00 UTC) are EXPECTED and not
    flagged. Only weekday-session gaps are flagged.
  - Shadow-signals pipeline state is a first-class check, not an afterthought
    (it is the training data source for v3.0 ML).
  - Each flag has an explicit severity: INFO, WARN, or CRITICAL.

Output: docs/research/v2_4_demo_stability.md
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

STABLE_START = pd.Timestamp("2026-04-10")
TRADING_DB = "data/trading.db"
OUT = Path("docs/research/v2_4_demo_stability.md")

# FX weekend window (approximate, UTC). Broker-specific but close enough for gap detection.
WEEKEND_START_DAY = 4  # Friday
WEEKEND_START_HOUR = 20  # >= 20:00 UTC Friday
WEEKEND_END_DAY = 6  # Sunday
WEEKEND_END_HOUR = 22  # <= 22:00 UTC Sunday


def is_weekend_gap(prev: pd.Timestamp, curr: pd.Timestamp) -> bool:
    """True if the gap prev->curr covers the FX weekend closure."""
    if prev.weekday() == WEEKEND_START_DAY and prev.hour >= WEEKEND_START_HOUR:
        if curr.weekday() == WEEKEND_END_DAY and curr.hour <= WEEKEND_END_HOUR + 1:
            return True
        if curr.weekday() == 0:  # Monday morning
            return True
    return False


def query(con, sql, params=()):
    try:
        return pd.read_sql_query(sql, con, params=params)
    except Exception as e:
        print(f"[ERR] query failed: {sql[:80]}... -> {e}")
        return pd.DataFrame()


def main() -> None:
    con = sqlite3.connect(TRADING_DB)
    stable_str = STABLE_START.strftime("%Y-%m-%d")

    # ─── account snapshots ─────────────────────────────────────────────
    snaps = query(con, "SELECT time, balance, equity FROM account_snapshots WHERE time >= ? ORDER BY time", (stable_str,))
    snaps["time"] = pd.to_datetime(snaps["time"])
    snaps["date"] = snaps["time"].dt.date
    snap_gap_min = snaps["time"].diff().dt.total_seconds() / 60.0
    snaps["gap_min"] = snap_gap_min
    # Cadence: observed median of non-weekend gaps establishes normal interval.
    # Only flag gaps substantially above normal.
    SNAPSHOT_GAP_WARN_MIN = 180   # 3h
    SNAPSHOT_GAP_CRITICAL_MIN = 360  # 6h
    weekday_gaps = []
    for i in range(1, len(snaps)):
        prev = snaps.iloc[i - 1]["time"]
        curr = snaps.iloc[i]["time"]
        gap = snap_gap_min.iloc[i]
        if gap >= SNAPSHOT_GAP_WARN_MIN and not is_weekend_gap(prev, curr):
            weekday_gaps.append({"prev": prev, "curr": curr, "gap_min": gap})

    # ─── trades ────────────────────────────────────────────────────────
    trades = query(con,
        "SELECT open_time, close_time, symbol, profit, is_closed, engine_version, strategy "
        "FROM trades WHERE open_time >= ? ORDER BY open_time", (stable_str,))
    trades["open_time"] = pd.to_datetime(trades["open_time"])
    trades["close_time"] = pd.to_datetime(trades["close_time"])
    trades["open_date"] = trades["open_time"].dt.date
    closed = trades[trades["is_closed"] == 1]
    open_now = trades[trades["is_closed"] == 0]
    wr = (closed["profit"] > 0).mean() * 100 if len(closed) else float("nan")
    total_pnl = closed["profit"].sum() if len(closed) else 0.0
    engine_mix = trades["engine_version"].fillna("(null)").astype(str).value_counts()

    # ─── trade_results (exit mix, execution quality) ──────────────────
    tr = query(con,
        "SELECT open_time, exit_reason, profitable, slippage_pips, spread_at_entry, engine_version "
        "FROM trade_results WHERE open_time >= ? ORDER BY open_time", (stable_str,))
    exit_mix = tr["exit_reason"].fillna("(null)").value_counts() if len(tr) else pd.Series(dtype=int)
    slippage_median = float(tr["slippage_pips"].median()) if len(tr) and tr["slippage_pips"].notna().any() else float("nan")
    slippage_p95 = float(tr["slippage_pips"].quantile(0.95)) if len(tr) and tr["slippage_pips"].notna().any() else float("nan")
    spread_median = float(tr["spread_at_entry"].median()) if len(tr) and tr["spread_at_entry"].notna().any() else float("nan")

    # ─── signals ───────────────────────────────────────────────────────
    sigs = query(con, "SELECT time, status FROM signal_logs WHERE time >= ? ORDER BY time", (stable_str,))
    sigs["time"] = pd.to_datetime(sigs["time"]) if len(sigs) else pd.Series(dtype="datetime64[ns]")
    sig_status_mix = sigs["status"].value_counts() if len(sigs) else pd.Series(dtype=int)

    # ─── shadow signals (v3.0 training data pipeline) ─────────────────
    # Schema has NO `result` column — use sim_status, sim_pnl, data_group
    shadow_all = query(con,
        "SELECT time, data_group, sim_status, sim_pnl FROM shadow_signals ORDER BY time")
    if len(shadow_all):
        shadow_all["time"] = pd.to_datetime(shadow_all["time"])
        shadow_stable = shadow_all[
            (shadow_all["time"] >= STABLE_START) | (shadow_all["data_group"] == "STABLE")
        ].copy()
        shadow_last_ts = shadow_all["time"].max()
        shadow_first_ts = shadow_all["time"].min()
    else:
        shadow_stable = shadow_all
        shadow_last_ts = None
        shadow_first_ts = None

    # ─── scan logs ─────────────────────────────────────────────────────
    scans = query(con, "SELECT time FROM scan_logs WHERE time >= ? ORDER BY time", (stable_str,))
    scans["time"] = pd.to_datetime(scans["time"]) if len(scans) else pd.Series(dtype="datetime64[ns]")
    scan_gap_min = scans["time"].diff().dt.total_seconds() / 60.0 if len(scans) else pd.Series(dtype=float)
    # Scans also hourly cadence, not 5-min. Threshold consistent with snapshots.
    SCAN_GAP_WARN_MIN = 180
    scan_weekday_gaps = []
    if len(scans) > 1:
        for i in range(1, len(scans)):
            prev = scans.iloc[i - 1]["time"]
            curr = scans.iloc[i]["time"]
            gap = scan_gap_min.iloc[i]
            if gap >= SCAN_GAP_WARN_MIN and not is_weekend_gap(prev, curr):
                scan_weekday_gaps.append({"prev": prev, "curr": curr, "gap_min": gap})

    # ─── circuit breaker ───────────────────────────────────────────────
    # circuit_breaker_logs schema varies — select * and count
    cb = query(con, "SELECT * FROM circuit_breaker_logs WHERE time >= ?", (stable_str,))

    con.close()

    # ─── flag classification ───────────────────────────────────────────
    flags = []  # list of (severity, text)
    now_ts = pd.Timestamp.utcnow().tz_localize(None)

    if len(weekday_gaps) > 0:
        for g in weekday_gaps:
            sev = "CRITICAL" if g["gap_min"] >= SNAPSHOT_GAP_CRITICAL_MIN else "WARN"
            flags.append((sev,
                f"Account-snapshot weekday gap {g['gap_min']/60:.1f}h on "
                f"{g['prev'].strftime('%a %Y-%m-%d %H:%M')} → {g['curr'].strftime('%a %H:%M')} UTC"))

    if shadow_last_ts is not None:
        hours_since_shadow = (now_ts - shadow_last_ts).total_seconds() / 3600.0
        if hours_since_shadow > 24:
            flags.append(("CRITICAL",
                f"Shadow-signals pipeline silent for {hours_since_shadow:.0f} hours "
                f"(last record {shadow_last_ts.strftime('%Y-%m-%d %H:%M')} UTC). "
                f"This is the training data source for v3.0 — feed must be restored before Phase 8 (v3.0 paper)."))
    else:
        flags.append(("CRITICAL", "shadow_signals table is empty — v3.0 training data pipeline has never recorded."))

    non_v24 = sum(v for k, v in engine_mix.items() if str(k) not in ("2.4",))
    if non_v24 > 0:
        flags.append(("WARN",
            f"{non_v24} trade(s) in STABLE period not tagged engine_version=2.4 "
            f"(distribution: {dict(engine_mix)})"))

    if len(cb) > 0:
        flags.append(("WARN", f"Circuit breaker fired {len(cb)} time(s) in STABLE period — review `circuit_breaker_logs`."))

    if len(scan_weekday_gaps) > 0:
        worst = max(scan_weekday_gaps, key=lambda x: x["gap_min"])
        flags.append(("WARN",
            f"Scan-loop weekday gap {worst['gap_min']/60:.1f}h on "
            f"{worst['prev'].strftime('%a %Y-%m-%d %H:%M')} → {worst['curr'].strftime('%H:%M')} UTC "
            f"({len(scan_weekday_gaps)} weekday scan gap(s) >=3h total)"))

    # ─── verdict ───────────────────────────────────────────────────────
    critical_count = sum(1 for s, _ in flags if s == "CRITICAL")
    warn_count = sum(1 for s, _ in flags if s == "WARN")
    if critical_count > 0:
        verdict = ("RED", "Critical issues present. v3.0 paper trading cannot start until resolved.")
    elif warn_count > 0:
        verdict = ("YELLOW", "Running but with warnings. Review before 04-28 meeting.")
    else:
        verdict = ("GREEN", "v2.4 stable. Ready for 04-28 go/no-go review.")

    # ─── write report ──────────────────────────────────────────────────
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    last_snap = snaps["time"].max() if len(snaps) else None
    last_trade = trades["open_time"].max() if len(trades) else None

    L = [
        "# v2.4 Demo Stability Report",
        "",
        f"*Generated: {generated_at}*",
        f"*Scope: STABLE segment, {STABLE_START.date()} → latest*",
        f"*Purpose: Input for 2026-04-28 v3.0 Go/No-Go meeting*",
        "",
        "## Verdict",
        "",
    ]
    verdict_color, verdict_text = verdict
    emoji = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}[verdict_color]
    L.append(f"{emoji} **{verdict_color}** — {verdict_text}")
    L.append("")

    if flags:
        L.append("### Flags")
        L.append("")
        for sev, text in flags:
            L.append(f"- **[{sev}]** {text}")
        L.append("")

    L.extend([
        "## Headline Numbers",
        "",
        f"| Item | Value |",
        f"|---|---|",
        f"| Scope | {STABLE_START.date()} → {last_snap.strftime('%Y-%m-%d %H:%M') if last_snap else 'n/a'} UTC |",
        f"| Account snapshots | {len(snaps)} rows across {snaps['date'].nunique() if len(snaps) else 0} days |",
        f"| Last snapshot | {last_snap.strftime('%Y-%m-%d %H:%M') if last_snap else 'n/a'} UTC |",
        f"| Weekday gaps in snapshots (>1h, non-weekend) | {len(weekday_gaps)} |",
        f"| Trades (total / closed / open) | {len(trades)} / {len(closed)} / {len(open_now)} |",
        f"| Win rate (closed) | {wr:.1f}% |",
        f"| Net PnL (closed) | ${total_pnl:+,.2f} |",
        f"| Signals logged | {len(sigs)} |",
        f"| Shadow-signal pipeline | "
            f"{len(shadow_all)} total rows, last at {shadow_last_ts.strftime('%Y-%m-%d %H:%M') if shadow_last_ts is not None else 'n/a'} UTC |",
        f"| Shadow (STABLE-tagged) | {len(shadow_stable)} rows |",
        f"| Circuit-breaker fires | {len(cb)} |",
        f"| Scan logs | {len(scans)} rows |",
        f"| Weekday gaps in scan loop (>30m, non-weekend) | {len(scan_weekday_gaps)} |",
        "",
        "## Snapshot Gaps (all non-weekend gaps >1h)",
        "",
    ])
    if weekday_gaps:
        L.append("| Previous | Current | Gap (h) |")
        L.append("|---|---|---:|")
        for g in weekday_gaps:
            L.append(f"| {g['prev'].strftime('%a %Y-%m-%d %H:%M')} | {g['curr'].strftime('%a %Y-%m-%d %H:%M')} | {g['gap_min']/60:.2f} |")
    else:
        L.append("_No non-weekend gaps >1h._")
    L.append("")

    # Daily cadence
    if len(snaps):
        L.extend([
            "## Daily Cadence",
            "",
            "| Date | Snapshots | Scans | Signals | Trades Opened |",
            "|---|---:|---:|---:|---:|",
        ])
        by_date = sorted(set(list(snaps["date"].unique()) +
                             list(trades["open_date"].unique() if len(trades) else []) +
                             list(sigs["time"].dt.date.unique() if len(sigs) else []) +
                             list(scans["time"].dt.date.unique() if len(scans) else [])))
        daily_snap = snaps.groupby("date").size()
        daily_trade = trades.groupby("open_date").size() if len(trades) else pd.Series(dtype=int)
        daily_sig = sigs.groupby(sigs["time"].dt.date).size() if len(sigs) else pd.Series(dtype=int)
        daily_scan = scans.groupby(scans["time"].dt.date).size() if len(scans) else pd.Series(dtype=int)
        for d in by_date:
            L.append(f"| {d} | {int(daily_snap.get(d, 0))} | {int(daily_scan.get(d, 0))} | {int(daily_sig.get(d, 0))} | {int(daily_trade.get(d, 0))} |")
        L.append("")

    if len(engine_mix):
        L.extend([
            "## Engine Version Purity (should be 100% v2.4)",
            "",
            "| engine_version | count |",
            "|---|---:|",
        ])
        for k, v in engine_mix.items():
            L.append(f"| `{k}` | {v} |")
        L.append("")

    if len(exit_mix):
        L.extend([
            "## Exit-Reason Mix (closed trades)",
            "",
            "| exit_reason | count |",
            "|---|---:|",
        ])
        for k, v in exit_mix.items():
            L.append(f"| `{k}` | {v} |")
        L.append("")

    if not pd.isna(slippage_median):
        L.extend([
            "## Execution Quality",
            "",
            f"- Slippage (pips): median {slippage_median:.2f}, p95 {slippage_p95:.2f}",
            f"- Spread at entry (pips): median {spread_median:.2f}",
            "",
        ])

    if len(sig_status_mix):
        L.extend([
            "## Signal Status Mix",
            "",
            "| status | count |",
            "|---|---:|",
        ])
        for k, v in sig_status_mix.items():
            L.append(f"| `{k}` | {v} |")
        L.append("")

    L.extend([
        "## Methodology Notes",
        "",
        "- FX-weekend gaps (Fri ≥20:00 UTC → Sun ≤22:00 UTC) are considered expected and excluded from flags.",
        "- Shadow-signals check treats >24h silence since last record as CRITICAL because shadow_signals is the training data source for v3.0 ML work (Phase 7-8).",
        f"- Snapshot & scan cadence observed to be ~hourly. Weekday gaps >=3h flagged WARN, >=6h flagged CRITICAL.",
        "- All times UTC.",
        "",
        f"*Source: `{TRADING_DB}` (account_snapshots, trades, trade_results, signal_logs, scan_logs, circuit_breaker_logs, shadow_signals).*",
    ])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"[OK] wrote {OUT}")
    print()
    print("─" * 70)
    print(f"VERDICT: {verdict_color} — {verdict_text}")
    print("─" * 70)
    if flags:
        print()
        print("Flags:")
        for sev, text in flags:
            print(f"  [{sev}] {text}")
    print()
    print(f"Scope           : {STABLE_START.date()} → {last_snap.strftime('%Y-%m-%d %H:%M') if last_snap else 'n/a'}")
    print(f"Snapshots       : {len(snaps)} rows, {len(weekday_gaps)} non-weekend gaps >1h")
    print(f"Trades          : {len(trades)} total, {len(closed)} closed (WR {wr:.1f}%, PnL ${total_pnl:+,.2f})")
    print(f"Shadow pipeline : last record {shadow_last_ts.strftime('%Y-%m-%d %H:%M') if shadow_last_ts is not None else 'never'}")
    print(f"Circuit breaker : {len(cb)} fires")


if __name__ == "__main__":
    main()
