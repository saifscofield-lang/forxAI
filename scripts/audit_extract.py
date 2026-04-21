"""Per-version extraction for system audit.

Produces:
  artifacts/v1_trades.csv  (OLD segment: pre-v2.0 + v2.0)
  artifacts/v2_trades.csv  (TRANSITION segment: v2.1-v2.3)
  artifacts/v3_trades.csv  (STABLE segment: v2.4, includes post-04-14 continuation)
  artifacts/v4_backtest_trades.csv  (Phase 10 research — TSMOM monthly returns by pair)
  artifacts/version_definitions.csv (raw export of data_segmentation_log)
  artifacts/metrics_summary.json     (computed aggregate metrics per version)
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path("data")
OUT = Path("artifacts")
OUT.mkdir(exist_ok=True)

# Segmentation boundaries from improvements.db.data_segmentation_log
# Plus the continuation rule for STABLE (no end date → ongoing)
VERSION_WINDOWS = {
    "v1": {"group": "OLD",        "start": "2026-03-18", "end": "2026-03-30", "engine": ["2.0", None]},
    "v2": {"group": "TRANSITION", "start": "2026-03-31", "end": "2026-04-09", "engine": ["2.1", "2.2", "2.3", "2.4"]},
    "v3": {"group": "STABLE",     "start": "2026-04-10", "end": None,          "engine": ["2.4"]},
}

# Actual per-version starting balances from account_snapshots.csv
# Single continuous MT5 demo account (not per-version reset). Account opened at $100,000.
STARTING_BALANCE = {
    "v1": 100_000.00,  # 2026-03-18 00:02 snapshot
    "v2": 118_310.82,  # 2026-03-31 03:52 snapshot (carries v1 gains)
    "v3":  92_165.58,  # 2026-04-10 00:05 snapshot (carries v2 losses)
}
# For the "% of starting" metric we use the version's own starting balance.
DEFAULT_STARTING_BALANCE = 100_000.0


def split_by_version(trades: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Use data_group where available; fall back to engine_version + open_time for post-segmentation rows."""
    trades = trades.copy()
    trades["open_time"] = pd.to_datetime(trades["open_time"])

    out = {}
    # v1 = OLD, v2 = TRANSITION
    out["v1"] = trades[trades["data_group"] == "OLD"].copy()
    out["v2"] = trades[trades["data_group"] == "TRANSITION"].copy()

    # v3 = STABLE + post-segmentation closed trades on engine 2.4
    stable = trades["data_group"] == "STABLE"
    # Post-segmentation: data_group is NaN AND open_time >= 2026-04-10 AND engine_version == 2.4
    post = (
        trades["data_group"].isna()
        & (trades["open_time"] >= pd.Timestamp("2026-04-10"))
        & (trades["engine_version"].astype(str) == "2.4")
    )
    out["v3"] = trades[stable | post].copy()

    return out


def compute_metrics(df: pd.DataFrame, label: str, starting_balance: float = DEFAULT_STARTING_BALANCE) -> dict:
    """Compute aggregate metrics from a trade dataframe (expects: profit, open_time, close_time, is_closed)."""
    closed = df[df.get("is_closed", 1) == 1].copy() if "is_closed" in df.columns else df.copy()

    if len(closed) == 0:
        return {"label": label, "total_trades": 0, "note": "no closed trades"}

    closed["profit_net"] = closed["profit"].fillna(0) + closed.get("swap", 0).fillna(0) + closed.get("commission", 0).fillna(0)
    closed["open_time"] = pd.to_datetime(closed["open_time"])
    closed["close_time"] = pd.to_datetime(closed["close_time"])
    closed = closed.sort_values("close_time").reset_index(drop=True)

    wins = closed[closed["profit_net"] > 0]["profit_net"]
    losses = closed[closed["profit_net"] < 0]["profit_net"]

    total_pnl = float(closed["profit_net"].sum())
    win_rate = 100.0 * len(wins) / len(closed)
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0  # negative
    gross_profit = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(-losses.sum()) if len(losses) else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0
    rr_ratio = (avg_win / -avg_loss) if avg_loss < 0 else float("inf") if avg_win > 0 else 0.0

    # Equity curve + max drawdown
    equity = starting_balance + closed["profit_net"].cumsum()
    peak = equity.cummax()
    drawdown = equity - peak
    max_dd_abs = float(drawdown.min())
    max_dd_pct = float((drawdown / peak).min() * 100)

    # Losing streak
    losing_streak = 0
    max_losing_streak = 0
    for p in closed["profit_net"]:
        if p < 0:
            losing_streak += 1
            max_losing_streak = max(max_losing_streak, losing_streak)
        else:
            losing_streak = 0

    # Daily returns for Sharpe (trading-day based)
    closed["close_date"] = closed["close_time"].dt.date
    daily = closed.groupby("close_date")["profit_net"].sum()
    # Pct returns off running equity
    daily_equity = starting_balance + daily.cumsum()
    daily_ret_pct = (daily / daily_equity.shift(1).fillna(starting_balance)).astype(float)
    if len(daily_ret_pct) > 1 and daily_ret_pct.std(ddof=0) > 0:
        sharpe = float(daily_ret_pct.mean() / daily_ret_pct.std(ddof=0) * np.sqrt(252))
        downside = daily_ret_pct[daily_ret_pct < 0]
        sortino = float(daily_ret_pct.mean() / downside.std(ddof=0) * np.sqrt(252)) if len(downside) > 1 and downside.std(ddof=0) > 0 else None
    else:
        sharpe = None
        sortino = None

    start = closed["open_time"].min()
    end = closed["close_time"].max()
    period_days = (end - start).total_seconds() / 86400.0
    # Exposure: sum of trade durations / total period duration
    durations = (closed["close_time"] - closed["open_time"]).dt.total_seconds().sum()
    exposure_pct = 100.0 * durations / (period_days * 86400.0) if period_days > 0 else None

    return {
        "label": label,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "period_days": round(period_days, 1),
        "total_trades": int(len(closed)),
        "winning_trades": int(len(wins)),
        "losing_trades": int(len(losses)),
        "win_rate_pct": round(win_rate, 2),
        "net_pnl": round(total_pnl, 2),
        "net_pnl_pct_of_start": round(100.0 * total_pnl / starting_balance, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "rr_ratio": round(rr_ratio, 3) if np.isfinite(rr_ratio) else None,
        "profit_factor": round(profit_factor, 3) if np.isfinite(profit_factor) else None,
        "max_drawdown_abs": round(max_dd_abs, 2),
        "max_drawdown_pct_of_start": round(max_dd_pct, 2),
        "longest_losing_streak": int(max_losing_streak),
        "sharpe_daily": round(sharpe, 3) if sharpe is not None else None,
        "sortino_daily": round(sortino, 3) if sortino is not None else None,
        "exposure_pct": round(exposure_pct, 2) if exposure_pct is not None else None,
        "instruments": sorted(closed["symbol"].dropna().unique().tolist()),
        "engine_versions_present": sorted(closed["engine_version"].dropna().astype(str).unique().tolist()),
    }


def main() -> None:
    # Export version definitions verbatim
    con = sqlite3.connect(DATA / "improvements.db")
    seg = pd.read_sql_query("SELECT * FROM data_segmentation_log ORDER BY date_from", con)
    seg.to_csv(OUT / "version_definitions.csv", index=False)
    print(f"[OK] version_definitions.csv ({len(seg)} rows)")

    # Full trade log
    trades = pd.read_csv(DATA / "ml_training" / "trades.csv")
    print(f"[OK] loaded trades.csv ({len(trades)} rows)")

    splits = split_by_version(trades)
    metrics = {}
    for ver, df in splits.items():
        out_path = OUT / f"{ver}_trades.csv"
        df.to_csv(out_path, index=False)
        metrics[ver] = compute_metrics(df, ver, STARTING_BALANCE.get(ver, DEFAULT_STARTING_BALANCE))
        metrics[ver]["starting_balance"] = STARTING_BALANCE.get(ver, DEFAULT_STARTING_BALANCE)
        print(f"[OK] {ver}: {len(df)} trades -> {out_path.name}")

    # v4 "trade log" = TSMOM monthly returns from research
    # We export portfolio-level monthly data as a proxy since no per-trade data exists for v4
    tsmom = pd.read_sql_query("SELECT * FROM tsmom_runs ORDER BY scope, run_time", con)
    meta = pd.read_sql_query("SELECT * FROM meta_labeler_runs ORDER BY scope, run_time", con)
    v4_df = pd.concat(
        [tsmom.assign(_source="tsmom_runs"), meta.assign(_source="meta_labeler_runs")],
        axis=0, ignore_index=True, sort=False,
    )
    v4_df.to_csv(OUT / "v4_backtest_trades.csv", index=False)
    print(f"[OK] v4_backtest_trades.csv ({len(v4_df)} rows = {len(tsmom)} tsmom + {len(meta)} meta_labeler)")

    # v4 metrics are pulled from the portfolio TSMOM row
    portfolio = tsmom[tsmom["scope"] == "portfolio_equal_weight"].iloc[0].to_dict() if (tsmom["scope"] == "portfolio_equal_weight").any() else {}
    metrics["v4_research"] = {
        "label": "v4_research",
        "note": "No executed trades. Metrics below come from TSMOM prototype (portfolio_equal_weight) on D1 forex data 2012-02-29 to 2026-04-30. No crypto/ccxt run yet.",
        "start_date": portfolio.get("start_date"),
        "end_date": portfolio.get("end_date"),
        "sharpe_monthly": portfolio.get("sharpe"),
        "sortino_monthly": portfolio.get("sortino"),
        "annual_return": portfolio.get("annual_return"),
        "annual_vol": portfolio.get("annual_vol"),
        "max_drawdown_pct": portfolio.get("max_drawdown"),
        "cagr": portfolio.get("cagr"),
        "hit_rate_monthly": portfolio.get("hit_rate_monthly"),
        "verdict_from_research": portfolio.get("verdict"),
    }

    con.close()

    (OUT / "metrics_summary.json").write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    print(f"[OK] metrics_summary.json")

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for ver, m in metrics.items():
        print(f"\n{ver}:")
        for k, v in m.items():
            if isinstance(v, list) and len(v) > 5:
                v = f"{v[:5]}...({len(v)} total)"
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
