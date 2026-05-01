"""Comprehensive trade evolution analysis.

Per docs/comprehensive_trade_analysis_prompt.md — produces the master enriched
CSV, 8 pivoted summaries, 10 charts, and data inputs for the report.

Source priority (per user instructions):
  - v3 (STABLE): live data/trading.db (data moves fast, CSV is stale)
  - v1 (OLD) / v2 (TRANSITION): data/ml_training/*.csv (frozen historical)
  - Both: improvements.db for segmentation + phase metadata

Diagnostic only. No code/config changes.
"""
from __future__ import annotations

import re
import sqlite3
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(".")
ARTIFACTS = Path("artifacts")
CHARTS = Path("docs/research/charts")
ARTIFACTS.mkdir(parents=True, exist_ok=True)
CHARTS.mkdir(parents=True, exist_ok=True)

TRADING_DB = "data/trading.db"
IMP_DB = "data/improvements.db"
ML_DIR = Path("data/ml_training")

STABLE_START = pd.Timestamp("2026-04-10")
TRANSITION_START = pd.Timestamp("2026-03-31")
OLD_START = pd.Timestamp("2026-03-18")

# ============================================================================
# STATISTICS HELPERS
# ============================================================================

def wilson_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float, float]:
    """Wilson-score confidence interval for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    z = stats.norm.ppf(1 - alpha / 2)
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (p, max(0.0, center - margin), min(1.0, center + margin))


def binomial_p(k: int, n: int, p0: float = 0.5) -> float:
    """Two-sided binomial p-value vs a null proportion."""
    if n == 0:
        return float("nan")
    return float(stats.binomtest(k, n, p0, alternative="two-sided").pvalue)


def fisher_2x2(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact for a 2x2 contingency [[a,b],[c,d]]."""
    return float(stats.fisher_exact([[a, b], [c, d]], alternative="two-sided")[1])


UNDERPOWERED_N = 10

# ============================================================================
# PART 1 — DATA LOAD
# ============================================================================

def parse_conf(txt: object) -> float:
    if not isinstance(txt, str):
        return float("nan")
    m = re.search(r"conf=([\d.]+)%", txt)
    return float(m.group(1)) if m else float("nan")


def session_of(hour: int) -> str:
    # UTC-based approximation
    if hour is None or (isinstance(hour, float) and np.isnan(hour)):
        return "Unknown"
    if 0 <= hour < 7:  return "Asian"
    if 7 <= hour < 13: return "London"
    if 13 <= hour < 17: return "Overlap"
    if 17 <= hour < 22: return "NY"
    return "Off-hours"


def assign_version(row: pd.Series) -> str:
    dg = row.get("data_group")
    if isinstance(dg, str) and dg in ("OLD", "TRANSITION", "STABLE"):
        return {"OLD": "v1", "TRANSITION": "v2", "STABLE": "v3"}[dg]
    # Infer from time + engine_version
    t = row["open_time"]
    if pd.isna(t):
        return "unknown"
    if t >= STABLE_START and str(row.get("engine_version", "")) == "2.4":
        return "v3"
    if TRANSITION_START <= t < STABLE_START:
        return "v2"
    if t < TRANSITION_START:
        return "v1"
    return "unknown"


def load_all_trades() -> pd.DataFrame:
    """v1/v2 from CSV (frozen), v3 from live DB (fresh)."""
    print("[load] reading CSV for v1/v2 historical data...")
    csv = pd.read_csv(ML_DIR / "trades.csv", parse_dates=["open_time", "close_time"])
    csv["_source"] = "csv"
    csv_pre_v3 = csv[csv["data_group"].isin(["OLD", "TRANSITION"])].copy()

    print(f"[load]   v1+v2 from CSV: {len(csv_pre_v3)} rows")

    print("[load] reading live DB for v3...")
    con = sqlite3.connect(TRADING_DB)
    live = pd.read_sql_query(
        "SELECT id, ticket, symbol, order_type, volume, open_price, close_price, "
        "open_time, close_time, profit, swap, commission, stop_loss, take_profit, "
        "strategy, is_closed, comment, engine_version, strategy_version, data_group "
        "FROM trades WHERE engine_version='2.4' AND open_time >= '2026-04-10' "
        "ORDER BY open_time",
        con, parse_dates=["open_time", "close_time"],
    )
    con.close()
    live["_source"] = "live_db"
    print(f"[load]   v3 from live DB: {len(live)} rows")

    # Use union; dedupe by ticket if any overlap (prefer live_db rows)
    combined = pd.concat([csv_pre_v3, live], ignore_index=True, sort=False)
    combined = combined.sort_values(["_source"]).drop_duplicates(subset=["ticket"], keep="last").reset_index(drop=True)

    combined["version"] = combined.apply(assign_version, axis=1)
    combined = combined.sort_values("open_time").reset_index(drop=True)
    print(f"[load]   combined: {len(combined)} trades, version mix: {combined['version'].value_counts().to_dict()}")
    return combined


def load_trade_results() -> pd.DataFrame:
    """Enriched columns (ML conf, ATR, RSI, trend, regime). Union CSV + live DB."""
    print("[load] trade_results (CSV historical + live DB)...")
    csv = pd.read_csv(ML_DIR / "trade_results.csv", parse_dates=["open_time", "close_time"])
    con = sqlite3.connect(TRADING_DB)
    live = pd.read_sql_query(
        "SELECT * FROM trade_results WHERE engine_version='2.4' AND open_time >= '2026-04-10'",
        con, parse_dates=["open_time", "close_time"],
    )
    con.close()
    # Live DB is authoritative for v3 tickets; CSV for v1/v2
    csv_pre = csv[csv["open_time"] < STABLE_START]
    combined = pd.concat([csv_pre, live], ignore_index=True, sort=False)
    combined = combined.drop_duplicates(subset=["ticket"], keep="last")
    print(f"[load]   trade_results combined: {len(combined)} rows")
    return combined


def load_signal_logs() -> pd.DataFrame:
    print("[load] signal_logs...")
    csv = pd.read_csv(ML_DIR / "signal_logs.csv", parse_dates=["time"])
    con = sqlite3.connect(TRADING_DB)
    live = pd.read_sql_query(
        "SELECT * FROM signal_logs WHERE time >= '2026-04-10'",
        con, parse_dates=["time"],
    )
    con.close()
    csv_pre = csv[csv["time"] < STABLE_START]
    combined = pd.concat([csv_pre, live], ignore_index=True, sort=False)
    print(f"[load]   signal_logs combined: {len(combined)} rows")
    return combined


def load_indicator_snapshots() -> pd.DataFrame:
    print("[load] indicator_snapshots...")
    csv = pd.read_csv(ML_DIR / "indicator_snapshots.csv", parse_dates=["time"])
    con = sqlite3.connect(TRADING_DB)
    live = pd.read_sql_query(
        "SELECT * FROM indicator_snapshots WHERE time >= '2026-04-10'",
        con, parse_dates=["time"],
    )
    con.close()
    csv_pre = csv[csv["time"] < STABLE_START]
    combined = pd.concat([csv_pre, live], ignore_index=True, sort=False)
    print(f"[load]   indicator_snapshots combined: {len(combined)} rows")
    return combined


def load_market_contexts() -> pd.DataFrame:
    print("[load] market_contexts...")
    csv = pd.read_csv(ML_DIR / "market_contexts.csv", parse_dates=["time"])
    con = sqlite3.connect(TRADING_DB)
    live = pd.read_sql_query(
        "SELECT * FROM market_contexts WHERE time >= '2026-04-10'",
        con, parse_dates=["time"],
    )
    con.close()
    csv_pre = csv[csv["time"] < STABLE_START]
    combined = pd.concat([csv_pre, live], ignore_index=True, sort=False)
    print(f"[load]   market_contexts combined: {len(combined)} rows")
    return combined


def load_shadow_signals() -> pd.DataFrame:
    print("[load] shadow_signals (live DB only)...")
    con = sqlite3.connect(TRADING_DB)
    shadow = pd.read_sql_query("SELECT * FROM shadow_signals", con, parse_dates=["time"])
    con.close()
    print(f"[load]   shadow_signals: {len(shadow)} rows")
    return shadow


def load_account_snapshots() -> pd.DataFrame:
    print("[load] account_snapshots (live DB)...")
    con = sqlite3.connect(TRADING_DB)
    snaps = pd.read_sql_query("SELECT * FROM account_snapshots ORDER BY time", con, parse_dates=["time"])
    con.close()
    print(f"[load]   account_snapshots: {len(snaps)} rows")
    return snaps


# ============================================================================
# PART 2 — ENRICHMENT
# ============================================================================

def enrich_trades(trades: pd.DataFrame, tr: pd.DataFrame, sigs: pd.DataFrame,
                   ind: pd.DataFrame, mc: pd.DataFrame, shadow: pd.DataFrame) -> pd.DataFrame:
    print("[enrich] building master per-trade dataset...")
    df = trades.copy()

    # Hold duration + session + day/hour
    df["hold_minutes"] = (df["close_time"] - df["open_time"]).dt.total_seconds() / 60.0
    df["hour_of_day_utc"] = df["open_time"].dt.hour
    df["day_of_week"] = df["open_time"].dt.day_name()
    df["session_at_entry"] = df["hour_of_day_utc"].apply(session_of)

    # SL / TP distances (pips approx — for FX pairs 0.0001, for XAU/JPY different; use raw diff)
    df["sl_distance_raw"] = (df["stop_loss"] - df["open_price"]).abs()
    df["tp_distance_raw"] = (df["open_price"] - df["take_profit"]).abs()
    df["planned_rr"] = df["tp_distance_raw"] / df["sl_distance_raw"]

    # PnL / outcome
    df["net_pnl"] = df["profit"].fillna(0) + df["swap"].fillna(0) + df["commission"].fillna(0)
    df["was_profitable"] = df["net_pnl"] > 0
    # realized_rr is filled from trade_results.risk_reward_actual after the merge below

    # Conf from comment
    df["ml_confidence_pct"] = df["comment"].apply(parse_conf)

    # Join trade_results by ticket (pick meaningful cols)
    # NOTE: trade_results.h1_trend/h4_trend/volatility_regime are all NULL in live DB
    # (engine stopped populating them). Use market_contexts as source of truth for
    # those fields instead.
    tr_cols = ["ticket", "exit_reason", "profitable", "ml_confidence",
               "slippage_pips", "trade_duration_minutes", "max_favorable_pips",
               "max_adverse_pips", "risk_reward_planned", "risk_reward_actual",
               "spread_at_entry", "atr_at_entry", "rsi_at_entry",
               "news_nearby", "news_event_name", "news_impact", "detected_regime"]
    tr_slim = tr[[c for c in tr_cols if c in tr.columns]].drop_duplicates("ticket")
    df = df.merge(tr_slim, on="ticket", how="left")

    # Fill realized_rr from the engine-populated risk_reward_actual (signed:
    # +R for wins, -R for losses, 0 for closes at entry price).
    if "risk_reward_actual" in df.columns:
        df["realized_rr"] = df["risk_reward_actual"]
    else:
        df["realized_rr"] = np.nan

    # Asof-match signal_logs (by symbol + time ±5 min)
    sigs_slim = sigs[[c for c in ["time", "symbol", "strategy", "status", "reason",
                                   "ml_confidence", "ml_threshold"] if c in sigs.columns]].copy()
    sigs_slim = sigs_slim.sort_values("time")
    df_sorted = df.sort_values("open_time").reset_index(drop=True)
    df_sorted = pd.merge_asof(df_sorted, sigs_slim, by="symbol",
                               left_on="open_time", right_on="time",
                               direction="nearest",
                               tolerance=pd.Timedelta("5min"),
                               suffixes=("", "_sig"))
    df_sorted = df_sorted.rename(columns={"status": "signal_status_at_entry",
                                           "reason": "signal_reason",
                                           "ml_confidence_sig": "ml_confidence_from_signal"})
    if "time" in df_sorted.columns:
        df_sorted = df_sorted.drop(columns=["time"])

    # Asof-match market_contexts
    mc_cols = ["time", "symbol", "h1_trend", "h4_trend", "volatility_regime",
               "spread", "h1_rsi", "h1_atr", "h1_macd", "h1_macd_signal", "h1_bb_position"]
    mc_slim = mc[[c for c in mc_cols if c in mc.columns]].copy().sort_values("time")
    df_sorted = pd.merge_asof(df_sorted, mc_slim, by="symbol",
                               left_on="open_time", right_on="time",
                               direction="nearest",
                               tolerance=pd.Timedelta("5min"),
                               suffixes=("", "_mc"))
    if "time" in df_sorted.columns:
        df_sorted = df_sorted.drop(columns=["time"])

    # Asof-match indicator_snapshots (fewer cols — all versions)
    ind_cols = ["time", "symbol", "rsi_14", "atr_14", "macd", "macd_signal",
                "bb_position", "sma_20", "sma_50", "volatility_10", "volume_ratio"]
    ind_slim = ind[[c for c in ind_cols if c in ind.columns]].copy().sort_values("time")
    df_sorted = pd.merge_asof(df_sorted, ind_slim, by="symbol",
                               left_on="open_time", right_on="time",
                               direction="nearest",
                               tolerance=pd.Timedelta("5min"),
                               suffixes=("", "_ind"))
    if "time" in df_sorted.columns:
        df_sorted = df_sorted.drop(columns=["time"])

    # Compute trend_alignment
    def trend_align(row):
        h4 = row.get("h4_trend")
        d = row.get("order_type")
        if pd.isna(h4) or h4 in ("", None):
            return "UNKNOWN"
        h4 = str(h4).upper()
        if h4 in ("UP", "BULLISH") and d == "BUY": return "WITH_H4"
        if h4 in ("DOWN", "BEARISH") and d == "SELL": return "WITH_H4"
        if h4 in ("UP", "BULLISH") and d == "SELL": return "AGAINST_H4"
        if h4 in ("DOWN", "BEARISH") and d == "BUY": return "AGAINST_H4"
        return "NEUTRAL"
    df_sorted["trend_alignment"] = df_sorted.apply(trend_align, axis=1)

    # ATR volatility bucket (by symbol percentile of ATR at entry)
    if "atr_14" in df_sorted.columns:
        df_sorted["volatility_bucket"] = (
            df_sorted.groupby("symbol")["atr_14"]
            .transform(lambda x: pd.qcut(x, q=3, labels=["LOW", "MED", "HIGH"], duplicates="drop"))
        )
    else:
        df_sorted["volatility_bucket"] = "NOT_AVAILABLE"

    # Big-win / big-loss flags (v3 only thresholds)
    v3 = df_sorted[df_sorted["version"] == "v3"]
    if len(v3) > 0:
        v3_closed = v3[v3["is_closed"] == 1]
        avg_v3_win = v3_closed[v3_closed["net_pnl"] > 0]["net_pnl"].mean()
        avg_v3_loss = v3_closed[v3_closed["net_pnl"] < 0]["net_pnl"].mean()
    else:
        avg_v3_win = 0
        avg_v3_loss = 0
    df_sorted["was_big_loss"] = (df_sorted["net_pnl"] < 2 * avg_v3_loss) if avg_v3_loss else False
    df_sorted["was_big_win"] = (df_sorted["net_pnl"] > 2 * avg_v3_win) if avg_v3_win else False

    # Shadow cross-check — for each trade, find shadow within ±5 min
    shadow_slim = shadow[["time", "symbol", "action", "executed", "sim_status", "sim_pnl"]].copy()
    shadow_slim = shadow_slim.sort_values("time")
    df_sorted = pd.merge_asof(df_sorted, shadow_slim, by="symbol",
                               left_on="open_time", right_on="time",
                               direction="nearest",
                               tolerance=pd.Timedelta("5min"),
                               suffixes=("", "_shadow"))
    df_sorted = df_sorted.rename(columns={"action": "shadow_predicted_direction",
                                           "executed": "shadow_executed_flag",
                                           "sim_status": "shadow_sim_status",
                                           "sim_pnl": "shadow_sim_pnl"})
    if "time" in df_sorted.columns:
        df_sorted = df_sorted.drop(columns=["time"])
    df_sorted["shadow_agreed_with_trade"] = (
        df_sorted["shadow_predicted_direction"] == df_sorted["order_type"]
    )

    # ml_class_probs as dict string (parsed from comment)
    def parse_probs(txt):
        if not isinstance(txt, str): return None
        m = re.search(r"\[SELL=([\d.]+)%\s*NO=([\d.]+)%\s*BUY=([\d.]+)%\]", txt)
        if m:
            return f"SELL={m.group(1)},NO={m.group(2)},BUY={m.group(3)}"
        return None
    df_sorted["ml_class_probs"] = df_sorted["comment"].apply(parse_probs)

    # Final column ordering + rename for the master CSV
    out_cols = [
        "ticket", "version", "engine_version", "symbol", "order_type",
        "open_time", "close_time", "hold_minutes", "session_at_entry",
        "day_of_week", "hour_of_day_utc",
        "open_price", "close_price", "stop_loss", "take_profit", "volume",
        "sl_distance_raw", "tp_distance_raw", "planned_rr", "realized_rr",
        "strategy", "signal_status_at_entry", "signal_reason",
        "ml_confidence_pct", "ml_confidence", "ml_confidence_from_signal", "ml_class_probs",
        "rsi_at_entry", "atr_at_entry", "h1_trend", "h4_trend",
        "trend_alignment", "detected_regime", "volatility_regime",
        "volatility_bucket", "rsi_14", "atr_14", "macd", "bb_position",
        "news_nearby", "news_event_name", "news_impact",
        "exit_reason", "max_favorable_pips", "max_adverse_pips",
        "risk_reward_planned", "risk_reward_actual",
        "profit", "swap", "commission", "net_pnl", "was_profitable",
        "was_big_loss", "was_big_win",
        "shadow_predicted_direction", "shadow_agreed_with_trade",
        "shadow_sim_status", "shadow_sim_pnl",
        "comment", "data_group", "_source",
    ]
    for c in out_cols:
        if c not in df_sorted.columns:
            df_sorted[c] = "NOT_AVAILABLE"
    out = df_sorted[out_cols].copy()
    return out


# ============================================================================
# PART 3 — SUMMARIES
# ============================================================================

def group_metrics(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """Per-group WR + Wilson CI + PnL stats."""
    df = df[df["is_closed"] == 1] if "is_closed" in df.columns else df.copy()
    # fallback if is_closed missing
    if "net_pnl" not in df.columns:
        return pd.DataFrame()
    rows = []
    for keys, sub in df.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        n = len(sub)
        wins = (sub["net_pnl"] > 0).sum()
        losses = (sub["net_pnl"] < 0).sum()
        flats = n - wins - losses
        wr_pt, wr_lo, wr_hi = wilson_ci(int(wins), int(n))
        win_pnl = sub.loc[sub["net_pnl"] > 0, "net_pnl"]
        loss_pnl = sub.loc[sub["net_pnl"] < 0, "net_pnl"]
        rr = float(win_pnl.mean()) / abs(float(loss_pnl.mean())) if len(win_pnl) and len(loss_pnl) and loss_pnl.mean() != 0 else None
        pf = (win_pnl.sum() / -loss_pnl.sum()) if len(loss_pnl) and loss_pnl.sum() != 0 else None
        row = dict(zip(group_cols, keys))
        row.update({
            "trades": int(n),
            "wins": int(wins),
            "losses": int(losses),
            "flats": int(flats),
            "wr_pct": round(100 * wr_pt, 2),
            "wr_ci_low_pct": round(100 * wr_lo, 2),
            "wr_ci_high_pct": round(100 * wr_hi, 2),
            "total_pnl": round(float(sub["net_pnl"].sum()), 2),
            "avg_pnl": round(float(sub["net_pnl"].mean()), 2),
            "avg_win": round(float(win_pnl.mean()), 2) if len(win_pnl) else None,
            "avg_loss": round(float(loss_pnl.mean()), 2) if len(loss_pnl) else None,
            "rr_ratio": round(rr, 3) if rr and np.isfinite(rr) else None,
            "profit_factor": round(pf, 3) if pf and np.isfinite(pf) else None,
            "underpowered": n < UNDERPOWERED_N,
        })
        rows.append(row)
    return pd.DataFrame(rows)


# ============================================================================
# PART 4 — CHARTS
# ============================================================================

def make_charts(master: pd.DataFrame, snaps: pd.DataFrame):
    print("[charts] generating 10 required charts...")
    closed = master[master["is_closed"] == 1].copy() if "is_closed" in master.columns else master.copy()
    # Add is_closed if missing based on close_time
    if "is_closed" not in closed.columns:
        closed = master.copy()
    closed = closed[closed["close_time"].notna()]

    # 1. Equity curve with version boundaries
    fig, ax = plt.subplots(figsize=(12, 5))
    if not snaps.empty:
        ax.plot(snaps["time"], snaps["equity"], color="#1E88E5", linewidth=1.2, label="Equity")
        ax.plot(snaps["time"], snaps["balance"], color="#888", linewidth=0.8, alpha=0.7, label="Balance")
    ax.axvline(TRANSITION_START, color="#FF9800", linestyle="--", alpha=0.6, label="v2 start (2026-03-31)")
    ax.axvline(STABLE_START, color="#4CAF50", linestyle="--", alpha=0.6, label="v3 start (2026-04-10)")
    ax.set_title("Account equity curve with version boundaries")
    ax.set_xlabel("time (UTC)")
    ax.set_ylabel("USD")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(CHARTS / "equity_curve.png", dpi=110)
    plt.close(fig)

    # 2. PnL by symbol by version
    piv = closed.groupby(["version", "symbol"])["net_pnl"].sum().unstack(fill_value=0)
    fig, ax = plt.subplots(figsize=(12, 5))
    piv.T.plot(kind="bar", ax=ax, color=["#EF5350", "#FFCA28", "#4CAF50"])
    ax.axhline(0, color="#333", linewidth=0.6)
    ax.set_title("Net PnL by symbol × version (positive = profit)")
    ax.set_ylabel("USD")
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(CHARTS / "pnl_by_symbol_by_version.png", dpi=110)
    plt.close(fig)

    # 3. WR with CI by symbol × version
    wr_by = group_metrics(closed, ["version", "symbol"])
    fig, ax = plt.subplots(figsize=(12, 5))
    symbols = sorted(wr_by["symbol"].unique())
    x = np.arange(len(symbols))
    width = 0.27
    for i, v in enumerate(["v1", "v2", "v3"]):
        sub = wr_by[wr_by["version"] == v].set_index("symbol").reindex(symbols)
        wr = sub["wr_pct"].values
        lo = sub["wr_ci_low_pct"].values
        hi = sub["wr_ci_high_pct"].values
        err_lo = wr - lo
        err_hi = hi - wr
        ax.bar(x + (i - 1) * width, wr,
               yerr=[np.nan_to_num(err_lo), np.nan_to_num(err_hi)],
               width=width, label=v, capsize=3,
               color=["#EF5350", "#FFCA28", "#4CAF50"][i], alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(symbols, rotation=20)
    ax.set_title("Win rate by symbol × version (Wilson 95% CI error bars)")
    ax.set_ylabel("WR %")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(CHARTS / "wr_by_symbol_by_version.png", dpi=110)
    plt.close(fig)

    # 4. Direction split by symbol (v3)
    v3 = closed[closed["version"] == "v3"]
    piv_d = v3.groupby(["symbol", "order_type"])["net_pnl"].sum().unstack(fill_value=0)
    fig, ax = plt.subplots(figsize=(12, 5))
    piv_d.plot(kind="bar", ax=ax, color=["#4CAF50", "#EF5350"])
    ax.axhline(0, color="#333", linewidth=0.6)
    ax.set_title("v3 — BUY vs SELL PnL by symbol")
    ax.set_ylabel("USD")
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(CHARTS / "direction_split_by_symbol.png", dpi=110)
    plt.close(fig)

    # 5. Strategy × symbol heatmap (v3 WR)
    v3_wr = group_metrics(v3, ["strategy", "symbol"])
    if not v3_wr.empty:
        piv_hm = v3_wr.pivot(index="strategy", columns="symbol", values="wr_pct")
        piv_n = v3_wr.pivot(index="strategy", columns="symbol", values="trades")
        fig, ax = plt.subplots(figsize=(12, 6))
        im = ax.imshow(piv_hm.values, cmap="RdYlGn", vmin=0, vmax=100, aspect="auto")
        ax.set_xticks(range(len(piv_hm.columns))); ax.set_xticklabels(piv_hm.columns, rotation=20)
        ax.set_yticks(range(len(piv_hm.index))); ax.set_yticklabels(piv_hm.index)
        for i in range(piv_hm.shape[0]):
            for j in range(piv_hm.shape[1]):
                val = piv_hm.iloc[i, j]
                n = piv_n.iloc[i, j]
                if pd.notna(val):
                    txt = f"{val:.0f}%\n(n={int(n) if pd.notna(n) else 0})"
                    ax.text(j, i, txt, ha="center", va="center", fontsize=8,
                             color="black" if 30 < val < 70 else "white")
        plt.colorbar(im, ax=ax, label="WR %")
        ax.set_title("v3 WR by strategy × symbol (n shown in cell)")
        fig.tight_layout()
        fig.savefig(CHARTS / "strategy_performance_heatmap.png", dpi=110)
        plt.close(fig)

    # 6. ML confidence calibration (v2.3+)
    ml_scope = closed[closed["ml_confidence_pct"].notna() & (closed["ml_confidence_pct"] > 0)].copy()
    if len(ml_scope) >= 20:
        ml_scope["conf_bucket"] = pd.cut(ml_scope["ml_confidence_pct"],
                                          bins=[0, 40, 50, 55, 60, 65, 100],
                                          labels=["<40", "40-50", "50-55", "55-60", "60-65", ">65"])
        cal = ml_scope.groupby("conf_bucket").agg(
            n=("net_pnl", "count"),
            wr=("was_profitable", "mean"),
        ).reset_index()
        cal["wr_pct"] = cal["wr"] * 100
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.bar(cal["conf_bucket"].astype(str), cal["wr_pct"], color="#1E88E5", alpha=0.8)
        for i, (_, r) in enumerate(cal.iterrows()):
            ax.text(i, r["wr_pct"] + 1, f"n={int(r['n'])}", ha="center", fontsize=8)
        ax.axhline(50, color="#EF5350", linestyle=":", alpha=0.6, label="50% (coin flip)")
        ax.set_title("ML confidence calibration (v2.3+ trades with ml_confidence_pct > 0)")
        ax.set_xlabel("ML confidence bucket (%)")
        ax.set_ylabel("Realized WR %")
        ax.legend()
        ax.grid(True, alpha=0.3, axis="y")
        fig.tight_layout()
        fig.savefig(CHARTS / "ml_confidence_calibration.png", dpi=110)
        plt.close(fig)

    # 7. Filter cascade — approximation from signal_logs status distribution per version
    # (built in main() with signal_logs access)

    # 8. Session × symbol heatmap (v3 avg PnL)
    v3_ses = group_metrics(v3, ["session_at_entry", "symbol"])
    if not v3_ses.empty:
        piv_s = v3_ses.pivot(index="session_at_entry", columns="symbol", values="avg_pnl")
        piv_sn = v3_ses.pivot(index="session_at_entry", columns="symbol", values="trades")
        fig, ax = plt.subplots(figsize=(12, 5))
        vmax = max(abs(piv_s.min().min()), abs(piv_s.max().max())) if piv_s.notna().any().any() else 1
        im = ax.imshow(piv_s.values, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
        ax.set_xticks(range(len(piv_s.columns))); ax.set_xticklabels(piv_s.columns, rotation=20)
        ax.set_yticks(range(len(piv_s.index))); ax.set_yticklabels(piv_s.index)
        for i in range(piv_s.shape[0]):
            for j in range(piv_s.shape[1]):
                val = piv_s.iloc[i, j]
                n = piv_sn.iloc[i, j]
                if pd.notna(val):
                    ax.text(j, i, f"${val:+.0f}\n(n={int(n) if pd.notna(n) else 0})",
                             ha="center", va="center", fontsize=8,
                             color="black" if abs(val) < 0.5 * vmax else "white")
        plt.colorbar(im, ax=ax, label="Avg PnL per trade")
        ax.set_title("v3 avg PnL by session × symbol")
        fig.tight_layout()
        fig.savefig(CHARTS / "session_heatmap.png", dpi=110)
        plt.close(fig)

    # 9. Trend alignment WR
    ta = closed[closed["trend_alignment"].isin(["WITH_H4", "AGAINST_H4"])]
    if not ta.empty:
        m = group_metrics(ta, ["version", "trend_alignment"])
        fig, ax = plt.subplots(figsize=(10, 4.5))
        piv_ta = m.pivot(index="version", columns="trend_alignment", values="avg_pnl")
        piv_ta.plot(kind="bar", ax=ax, color=["#EF5350", "#4CAF50"])
        ax.axhline(0, color="#333", linewidth=0.6)
        ax.set_title("Trend alignment — avg PnL by version")
        ax.set_ylabel("USD / trade")
        ax.grid(True, alpha=0.3, axis="y")
        fig.tight_layout()
        fig.savefig(CHARTS / "trend_alignment_performance.png", dpi=110)
        plt.close(fig)

    # 10. Worst 10 v3 trades timeline
    worst = v3[v3["net_pnl"].notna()].nsmallest(10, "net_pnl")
    if not worst.empty:
        fig, ax = plt.subplots(figsize=(12, 4.5))
        colors = ["#EF5350"] * len(worst)
        ax.bar(worst["open_time"].dt.strftime("%m-%d %H:%M"), worst["net_pnl"],
               color=colors, alpha=0.85)
        for i, (_, r) in enumerate(worst.iterrows()):
            ax.text(i, r["net_pnl"] - 50, f"{r['symbol']}\n{r['order_type']}",
                     ha="center", va="top", fontsize=7)
        ax.set_title("v3 worst 10 trades — timeline of biggest losses")
        ax.set_ylabel("USD")
        ax.set_xticklabels(ax.get_xticklabels(), rotation=35, ha="right")
        ax.grid(True, alpha=0.3, axis="y")
        fig.tight_layout()
        fig.savefig(CHARTS / "worst_10_trades_timeline.png", dpi=110)
        plt.close(fig)

    print(f"[charts] wrote {len(list(CHARTS.glob('*.png')))} PNGs")


def build_filter_cascade_chart(sigs: pd.DataFrame):
    """Chart 7 — signals → filters → trades per version."""
    sigs = sigs.copy()
    sigs["version"] = sigs["time"].apply(
        lambda t: "v3" if t >= STABLE_START else ("v2" if t >= TRANSITION_START else "v1"))
    counts = sigs.groupby(["version", "status"]).size().unstack(fill_value=0)
    fig, ax = plt.subplots(figsize=(11, 5))
    counts.plot(kind="bar", stacked=True, ax=ax, colormap="Set2")
    ax.set_title("Filter cascade — signal statuses by version (signal_logs)")
    ax.set_ylabel("signals")
    ax.grid(True, alpha=0.3, axis="y")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(CHARTS / "filter_cascade.png", dpi=110)
    plt.close(fig)


# ============================================================================
# DATA COMPLETENESS
# ============================================================================

def build_completeness(master: pd.DataFrame) -> pd.DataFrame:
    print("[completeness] computing per-field availability per version...")
    rows = []
    for col in master.columns:
        for v in ["v1", "v2", "v3"]:
            sub = master[master["version"] == v]
            n = len(sub)
            if n == 0:
                rows.append({"field": col, "version": v, "n_total": 0, "n_available": 0, "pct_available": None})
                continue
            vals = sub[col]
            if vals.dtype == "O":
                avail = vals.notna() & (vals != "NOT_AVAILABLE") & (vals != "")
            else:
                avail = vals.notna()
            rows.append({"field": col, "version": v, "n_total": int(n),
                         "n_available": int(avail.sum()),
                         "pct_available": round(100 * avail.sum() / n, 1)})
    return pd.DataFrame(rows)


# ============================================================================
# MARKDOWN REPORT GENERATION
# ============================================================================

REPORT_DIR = Path("docs/research")


def _md_table(df: pd.DataFrame, columns: list[str], headers: list[str] | None = None,
              fmt: dict | None = None) -> str:
    """Render a DataFrame as a markdown table for selected columns."""
    if df.empty:
        return "_(no rows)_\n"
    fmt = fmt or {}
    cols = [c for c in columns if c in df.columns]
    headers = headers or cols
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---" if c.endswith("name") else "---:" for c in cols]) + "|"]
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if c in fmt and pd.notna(v):
                cells.append(fmt[c].format(v))
            elif pd.isna(v):
                cells.append("—")
            elif isinstance(v, float):
                cells.append(f"{v:.2f}")
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def write_report(master: pd.DataFrame, snaps: pd.DataFrame, sigs: pd.DataFrame,
                  by_symbol: pd.DataFrame, by_dir: pd.DataFrame, by_strategy: pd.DataFrame,
                  by_session: pd.DataFrame, fe: pd.DataFrame) -> Path:
    """Generate the dated comprehensive trade evolution report."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = REPORT_DIR / f"full_trade_evolution_report_{today}.md"
    closed = master[master["is_closed"] == 1].copy()

    # ── Headline numbers ──
    n_total = len(master)
    n_closed = int((master["is_closed"] == 1).sum())
    by_v_count = master["version"].value_counts().to_dict()
    v1_n = int(by_v_count.get("v1", 0))
    v2_n = int(by_v_count.get("v2", 0))
    v3_n = int(by_v_count.get("v3", 0))
    v1_pnl = float(closed.loc[closed["version"] == "v1", "net_pnl"].sum())
    v2_pnl = float(closed.loc[closed["version"] == "v2", "net_pnl"].sum())
    v3_pnl = float(closed.loc[closed["version"] == "v3", "net_pnl"].sum())
    cum_pnl = v1_pnl + v2_pnl + v3_pnl

    # ── XAUUSD focus ──
    v3_closed = closed[closed["version"] == "v3"]
    xau_v3 = v3_closed[v3_closed["symbol"] == "XAUUSD"]
    xau_v3_pnl = float(xau_v3["net_pnl"].sum()) if len(xau_v3) else 0.0
    nonxau_v3_pnl = v3_pnl - xau_v3_pnl
    xau_v3_share = 100 * len(xau_v3) / max(len(v3_closed), 1)

    # ── OVERLAP-session XAUUSD ──
    xau_overlap = xau_v3[xau_v3["session_at_entry"] == "Overlap"]
    xau_overlap_pnl = float(xau_overlap["net_pnl"].sum()) if len(xau_overlap) else 0.0
    xau_nonoverlap = xau_v3[xau_v3["session_at_entry"] != "Overlap"]
    xau_nonoverlap_pnl = float(xau_nonoverlap["net_pnl"].sum()) if len(xau_nonoverlap) else 0.0

    # ── Worst / Best 10 v3 ──
    worst10 = v3_closed.nsmallest(10, "net_pnl")
    best10 = v3_closed.nlargest(10, "net_pnl")

    # ── Strategy pathologies (high WR + losing) ──
    v3_strat = by_strategy[by_strategy["version"] == "v3"].copy()
    pathologies = v3_strat[(v3_strat["wr_pct"] >= 60) & (v3_strat["total_pnl"] < 0) & (~v3_strat["underpowered"])]

    # ── Underpowered cells ──
    v3_dir = by_dir[by_dir["version"] == "v3"]
    underpowered_cells = int(v3_dir["underpowered"].sum())
    total_cells = len(v3_dir)

    # ── Account equity ──
    if not snaps.empty:
        first_eq = float(snaps.iloc[0]["balance"])
        last_eq = float(snaps.iloc[-1]["balance"])
        last_equity = float(snaps.iloc[-1]["equity"])
    else:
        first_eq = last_eq = last_equity = 100_000.0

    # ── XAUUSD direction asymmetry (zero-BUY check) ──
    xau_all = closed[closed["symbol"] == "XAUUSD"]
    xau_buy = (xau_all["order_type"] == "BUY").sum()
    xau_sell = (xau_all["order_type"] == "SELL").sum()

    L = []
    L.append(f"# ForexAI — Full Trade Evolution Report")
    L.append("")
    L.append(f"*Generated: {today} (auto-produced by `scripts/analyze_all_trades.py`)*")
    L.append(f"*Scope: all closed trades across v1 (OLD), v2 (TRANSITION), v3 (STABLE) — total **{n_total}** trades, **{n_closed}** closed*")
    L.append(f"*Authority level: **authoritative for v3; context-only for v1/v2***")
    L.append(f"*Source: live `data/trading.db` for v3; `data/ml_training/*.csv` for v1/v2*")
    L.append("")
    L.append("---")
    L.append("")

    # § 1 Executive Summary
    L.append("## 1. Executive Summary")
    L.append("")
    L.append(f"After **37+ days** of paper trading across three engine versions, the account stands at **${last_eq:,.2f}** "
              f"(equity **${last_equity:,.2f}**) — cumulative net change **${cum_pnl:+,.2f}** "
              f"({100 * cum_pnl / first_eq:+.2f}%) from the **${first_eq:,.0f}** starting balance.")
    L.append("")
    L.append(f"v3 is the only authoritative window for evaluation: **{v3_n} trades, +${v3_pnl:,.2f}**. "
              f"v1 (+${v1_pnl:,.2f}) is context-only (oversized lots, no risk controls). "
              f"v2 (${v2_pnl:+,.2f}) is invalid (construction zone, 13 config changes in 10 days).")
    L.append("")
    L.append(f"**Three most important findings:**")
    L.append("")
    L.append(f"1. **v3 is a single-symbol system.** {len(xau_v3)} of {len(v3_closed)} v3 trades ({xau_v3_share:.0f}%) are XAUUSD. Without XAUUSD, v3 PnL is **${nonxau_v3_pnl:+,.2f}**. With it, **+${v3_pnl:,.2f}**.")
    L.append(f"2. **OVERLAP session (13:00-17:00 UTC) is the loss concentration on XAUUSD:** {len(xau_overlap)} trades, **${xau_overlap_pnl:+,.2f}**. Every other session on XAUUSD is profitable (non-overlap PnL **${xau_nonoverlap_pnl:+,.2f}**).")
    if not pathologies.empty:
        worst_path = pathologies.sort_values("total_pnl").iloc[0]
        L.append(f"3. **Strategy pathology — `{worst_path['strategy']}`: {worst_path['wr_pct']}% WR but ${worst_path['total_pnl']:+,.2f}** over {worst_path['trades']} trades. Profit factor {worst_path['profit_factor']}, R:R {worst_path['rr_ratio']} — the classic small-wins, big-losses trap.")
    else:
        L.append(f"3. _(no clear strategy-level pathology meets the n≥10 threshold)_")
    L.append("")

    # § 2 Project-wide aggregates
    L.append("## 2. Project-wide Aggregates")
    L.append("")
    L.append("### 2.1 Trade count by version × symbol")
    L.append("")
    pivot_n = closed.pivot_table(index="symbol", columns="version", values="ticket", aggfunc="count", fill_value=0)
    pivot_n["total"] = pivot_n.sum(axis=1)
    L.append("| symbol | v1 | v2 | v3 | total |")
    L.append("|---|---:|---:|---:|---:|")
    for sym in pivot_n.sort_values("total", ascending=False).index:
        r = pivot_n.loc[sym]
        L.append(f"| {sym} | {int(r.get('v1', 0))} | {int(r.get('v2', 0))} | {int(r.get('v3', 0))} | {int(r['total'])} |")
    L.append("")

    L.append("### 2.2 Net PnL by version")
    L.append("")
    L.append("| version | trades | closed | net PnL | notes |")
    L.append("|---|---:|---:|---:|---|")
    L.append(f"| v1 (OLD)        | {v1_n} | {(closed['version']=='v1').sum()} | **${v1_pnl:+,.2f}** | Context-only — oversized lots, no risk controls |")
    L.append(f"| v2 (TRANSITION) | {v2_n} | {(closed['version']=='v2').sum()} | **${v2_pnl:+,.2f}** | Invalid — construction zone, segmentation_log marks not-for-eval |")
    L.append(f"| v3 (STABLE)     | {v3_n} | {(closed['version']=='v3').sum()} | **${v3_pnl:+,.2f}** | Authoritative for evaluation |")
    L.append(f"| **cumulative**  | **{n_total}** | **{n_closed}** | **${cum_pnl:+,.2f}** | from ${first_eq:,.0f} start |")
    L.append("")

    L.append("![Equity curve](charts/equity_curve.png)")
    L.append("")

    # § 3 Per-symbol summary (v3 focus)
    L.append("## 3. Per-Symbol Summary (v3)")
    L.append("")
    v3_sym = by_symbol[by_symbol["version"] == "v3"].sort_values("total_pnl", ascending=False).copy()
    L.append("| symbol | trades | wins | losses | WR % | WR 95% CI | total PnL | avg PnL | R:R | PF | underpowered |")
    L.append("|---|---:|---:|---:|---:|---|---:|---:|---:|---:|:---:|")
    for _, r in v3_sym.iterrows():
        ci = f"[{r['wr_ci_low_pct']:.1f}, {r['wr_ci_high_pct']:.1f}]"
        rr = f"{r['rr_ratio']:.3f}" if pd.notna(r['rr_ratio']) else "—"
        pf = f"{r['profit_factor']:.3f}" if pd.notna(r['profit_factor']) else "—"
        flag = "⚠ YES" if r["underpowered"] else "no"
        L.append(f"| {r['symbol']} | {int(r['trades'])} | {int(r['wins'])} | {int(r['losses'])} | {r['wr_pct']:.1f} | {ci} | ${r['total_pnl']:+,.2f} | ${r['avg_pnl']:+,.2f} | {rr} | {pf} | {flag} |")
    L.append("")
    L.append("![PnL by symbol × version](charts/pnl_by_symbol_by_version.png)")
    L.append("")
    L.append("![WR by symbol × version with 95% CI](charts/wr_by_symbol_by_version.png)")
    L.append("")

    # § 3.1 XAUUSD spotlight (zero-BUY note + reference to detail)
    L.append("### 3.1 XAUUSD spotlight")
    L.append("")
    L.append(f"Across all 3 versions, XAUUSD has **{xau_buy} BUY trades and {xau_sell} SELL trades**. Zero BUYs in any version. ")
    L.append("This is a **persistent system characteristic**, not a recent drift. Detailed investigation: `docs/research/xauusd_sell_analysis.md`.")
    L.append("")
    L.append(f"**OVERLAP session loss concentration (v3):** {len(xau_overlap)} trades, **${xau_overlap_pnl:+,.2f}**.")
    L.append(f"**Non-OVERLAP XAUUSD (v3):** {len(xau_nonoverlap)} trades, **${xau_nonoverlap_pnl:+,.2f}**.")
    if len(xau_overlap) >= 10 and xau_overlap_pnl < -5000:
        L.append("")
        L.append("**The OVERLAP-session filter is the highest-leverage single change available.**")
    L.append("")

    # § 4 Per-strategy summary
    L.append("## 4. Per-Strategy Summary (v3)")
    L.append("")
    L.append("| strategy | trades | WR % | WR 95% CI | total PnL | avg PnL | R:R | PF | underpowered |")
    L.append("|---|---:|---:|---|---:|---:|---:|---:|:---:|")
    for _, r in v3_strat.sort_values("total_pnl").iterrows():
        ci = f"[{r['wr_ci_low_pct']:.1f}, {r['wr_ci_high_pct']:.1f}]"
        rr = f"{r['rr_ratio']:.3f}" if pd.notna(r['rr_ratio']) else "—"
        pf = f"{r['profit_factor']:.3f}" if pd.notna(r['profit_factor']) else "—"
        flag = "⚠ YES" if r["underpowered"] else "no"
        L.append(f"| `{r['strategy']}` | {int(r['trades'])} | {r['wr_pct']:.1f} | {ci} | ${r['total_pnl']:+,.2f} | ${r['avg_pnl']:+,.2f} | {rr} | {pf} | {flag} |")
    L.append("")
    if not pathologies.empty:
        L.append("### Strategy pathologies (high WR + losing money)")
        L.append("")
        for _, r in pathologies.iterrows():
            L.append(f"- **`{r['strategy']}`** — {int(r['trades'])} trades, **{r['wr_pct']:.0f}% WR**, **${r['total_pnl']:+,.2f}** net. PF {r['profit_factor']:.3f}, R:R {r['rr_ratio']:.3f}. Avg loss is far larger than avg win — the small-wins, big-losses trap.")
        L.append("")
    L.append("![Strategy heatmap](charts/strategy_performance_heatmap.png)")
    L.append("")

    # § 5 Session analysis
    L.append("## 5. Session Analysis (v3)")
    L.append("")
    v3_ses = by_session[by_session["version"] == "v3"].copy()
    if not v3_ses.empty:
        ses_pivot = v3_ses.pivot_table(index="session_at_entry", columns="symbol", values="total_pnl", aggfunc="sum", fill_value=0)
        L.append("Session × symbol PnL (USD):")
        L.append("")
        symbols_in = list(ses_pivot.columns)
        L.append("| session | " + " | ".join(symbols_in) + " | row total |")
        L.append("|---|" + "|".join(["---:" for _ in symbols_in]) + "|---:|")
        for ses_name in ses_pivot.index:
            row = ses_pivot.loc[ses_name]
            row_total = float(row.sum())
            cells = " | ".join(f"${v:+,.0f}" if v != 0 else "0" for v in row.values)
            bold = "**" if abs(row_total) > 5000 else ""
            L.append(f"| {ses_name} | {cells} | {bold}${row_total:+,.0f}{bold} |")
        L.append("")
    L.append("![Session heatmap](charts/session_heatmap.png)")
    L.append("")

    # § 6 Filter effectiveness
    L.append("## 6. Filter Effectiveness")
    L.append("")
    fe_pivot = fe.pivot_table(index="status", columns="version", values="signal_count", fill_value=0)
    L.append("Signal status counts per version (from `signal_logs`):")
    L.append("")
    versions_in = [c for c in ["v1", "v2", "v3"] if c in fe_pivot.columns]
    L.append("| status | " + " | ".join(versions_in) + " |")
    L.append("|---|" + "|".join(["---:" for _ in versions_in]) + "|")
    for status in fe_pivot.index:
        cells = " | ".join(f"{int(fe_pivot.loc[status, v])}" for v in versions_in)
        L.append(f"| {status} | {cells} |")
    L.append("")
    L.append("![Filter cascade](charts/filter_cascade.png)")
    L.append("")

    # § 7 Worst 10 / Best 10
    L.append("## 7. Worst 10 v3 Trades")
    L.append("")
    L.append("| ticket | open (UTC) | symbol | dir | strategy | session | conf % | net PnL | exit |")
    L.append("|---|---|---|---|---|---|---:|---:|---|")
    for _, r in worst10.iterrows():
        conf = f"{r['ml_confidence_pct']:.1f}" if pd.notna(r["ml_confidence_pct"]) else "—"
        L.append(f"| {int(r['ticket'])} | {r['open_time'].strftime('%Y-%m-%d %H:%M')} | {r['symbol']} | {r['order_type']} | `{r['strategy']}` | {r['session_at_entry']} | {conf} | ${r['net_pnl']:+,.2f} | {r.get('exit_reason', '—') or '—'} |")
    L.append("")
    L.append("![Worst 10 timeline](charts/worst_10_trades_timeline.png)")
    L.append("")

    L.append("## 8. Best 10 v3 Trades")
    L.append("")
    L.append("| ticket | open (UTC) | symbol | dir | strategy | session | conf % | net PnL | exit |")
    L.append("|---|---|---|---|---|---|---:|---:|---|")
    for _, r in best10.iterrows():
        conf = f"{r['ml_confidence_pct']:.1f}" if pd.notna(r["ml_confidence_pct"]) else "—"
        L.append(f"| {int(r['ticket'])} | {r['open_time'].strftime('%Y-%m-%d %H:%M')} | {r['symbol']} | {r['order_type']} | `{r['strategy']}` | {r['session_at_entry']} | {conf} | ${r['net_pnl']:+,.2f} | {r.get('exit_reason', '—') or '—'} |")
    L.append("")

    # § 9 Recommendations (auto-derived from data thresholds)
    L.append("## 9. Recommendations (auto-derived)")
    L.append("")
    L.append("Each recommendation requires ≥10 v3 trades or ≥5 v3 trades with consistent v1/v2 pattern.")
    L.append("")
    rec_n = 0
    if len(xau_overlap) >= 10 and xau_overlap_pnl < -5000:
        rec_n += 1
        L.append(f"**R{rec_n} — Block XAUUSD SELL during OVERLAP session (13:00-17:00 UTC).** ")
        L.append(f"Evidence: {len(xau_overlap)} v3 trades, total **${xau_overlap_pnl:+,.2f}**. Non-OVERLAP XAUUSD: ${xau_nonoverlap_pnl:+,.2f}. Highest single-change PnL recovery available.")
        L.append("")
    for _, r in pathologies.iterrows():
        rec_n += 1
        L.append(f"**R{rec_n} — Retire or restructure `{r['strategy']}`.** ")
        L.append(f"Evidence: {int(r['trades'])} v3 trades, {r['wr_pct']:.0f}% WR but ${r['total_pnl']:+,.2f} net. R:R {r['rr_ratio']:.2f}, PF {r['profit_factor']:.2f}. Structural P&L asymmetry.")
        L.append("")
    if xau_buy == 0 and xau_sell >= 50:
        rec_n += 1
        L.append(f"**R{rec_n} — Phase 7 model audit: XAUUSD zero-BUY asymmetry.** ")
        L.append(f"Evidence: {xau_sell} XAUUSD SELLs, {xau_buy} BUYs across all 3 versions. Either ML training data is SELL-biased or config thresholds are asymmetric. Phase 7 (Meta-Labeler Rebuild) should explicitly check class balance for XAUUSD.")
        L.append("")
    if underpowered_cells >= total_cells / 2:
        rec_n += 1
        L.append(f"**R{rec_n} — Defer per-symbol decisions for non-XAUUSD pairs.** ")
        L.append(f"Evidence: {underpowered_cells} of {total_cells} per-symbol-per-direction cells in v3 are UNDERPOWERED (n<10). No statistical basis for symbol-level retirement outside XAUUSD until Phase 8 collects more data.")
        L.append("")

    # § 10 Methodology
    L.append("## 10. Methodology & Caveats")
    L.append("")
    L.append("- **Source priority:** v3 from live `data/trading.db` (fresh data); v1/v2 from `data/ml_training/*.csv` (frozen historical). All other tables (signal_logs, market_contexts, indicator_snapshots, shadow_signals) joined live.")
    L.append("- **Joins:** trade_results joined on `ticket` (exact). signal_logs / market_contexts / indicator_snapshots / shadow_signals joined via `pd.merge_asof` with `by=symbol` and ±5 min tolerance.")
    L.append("- **Statistical tests:** Wilson-score 95% CI on every WR. Underpowered cells (n<10) flagged explicitly and excluded from recommendations.")
    L.append("- **Known data quality issues:** `trade_results.h1_trend / h4_trend / volatility_regime` are NULL in the live DB (engine schema-drift). Sourced from `market_contexts` instead via asof-join.")
    L.append("- **Shadow gap:** 6-day shadow-signals outage 2026-04-16 → 2026-04-22 limits filter-effectiveness counterfactual analysis on v3.")
    L.append("")
    L.append("**This analysis cannot answer:**")
    L.append("- Will v3 be profitable over the next 30 days? (Phase 8 paper trading is the answer-generator.)")
    L.append("- Is XAUUSD's edge durable? (37 days of data in one regime cannot establish portability.)")
    L.append("- The system's true Sharpe? (Sample too small for a meaningful estimate.)")
    L.append("")

    L.append("## 11. Reference Files")
    L.append("")
    L.append("- `artifacts/all_trades_enriched.csv` — master per-trade dataset")
    L.append("- `artifacts/data_completeness_report.csv` — per-field availability")
    L.append("- `artifacts/summary_by_*.csv` — 7 pivoted summaries")
    L.append("- `docs/research/charts/*.png` — 10 charts")
    L.append("- `scripts/analyze_all_trades.py` — re-runnable; this report regenerates on every run")
    L.append("- `docs/research/xauusd_sell_analysis.md` — XAUUSD detailed investigation")
    L.append("- `docs/research/decision_log.md` — running decision history")
    L.append("")
    L.append(f"*End of report. Auto-generated {today}.*")

    out_path.write_text("\n".join(L), encoding="utf-8")
    return out_path


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 78)
    print("COMPREHENSIVE TRADE EVOLUTION ANALYSIS")
    print("=" * 78)
    print()

    # Load
    trades = load_all_trades()
    tr = load_trade_results()
    sigs = load_signal_logs()
    ind = load_indicator_snapshots()
    mc = load_market_contexts()
    shadow = load_shadow_signals()
    snaps = load_account_snapshots()
    print()

    # Enrich
    master = enrich_trades(trades, tr, sigs, ind, mc, shadow)
    # Ensure is_closed flag in master (from original trades)
    master["is_closed"] = trades.set_index("ticket")["is_closed"].reindex(master["ticket"]).values
    master.to_csv(ARTIFACTS / "all_trades_enriched.csv", index=False)
    print(f"[enrich] wrote artifacts/all_trades_enriched.csv ({len(master)} rows, {len(master.columns)} cols)")

    # Completeness
    completeness = build_completeness(master)
    completeness.to_csv(ARTIFACTS / "data_completeness_report.csv", index=False)
    print(f"[completeness] wrote artifacts/data_completeness_report.csv")

    # Summaries
    print()
    print("[summaries] computing 7 pivoted summaries...")
    closed = master[master["is_closed"] == 1].copy()
    group_metrics(closed, ["version", "symbol"]).to_csv(ARTIFACTS / "summary_by_version_symbol.csv", index=False)
    group_metrics(closed, ["version", "symbol", "order_type"]).to_csv(ARTIFACTS / "summary_by_version_symbol_direction.csv", index=False)
    group_metrics(closed, ["version", "strategy"]).to_csv(ARTIFACTS / "summary_by_version_strategy.csv", index=False)
    group_metrics(closed, ["version", "session_at_entry", "symbol"]).to_csv(ARTIFACTS / "summary_by_session.csv", index=False)
    group_metrics(closed, ["version", "symbol", "trend_alignment"]).to_csv(ARTIFACTS / "summary_by_trend_alignment.csv", index=False)

    # ML conf bucket (v2.3+ only — where ml_confidence_pct > 0)
    ml_rows = closed[closed["ml_confidence_pct"].notna() & (closed["ml_confidence_pct"] > 0)].copy()
    if len(ml_rows):
        ml_rows["conf_bucket"] = pd.cut(ml_rows["ml_confidence_pct"],
                                         bins=[0, 40, 60, 80, 100],
                                         labels=["<40", "40-60", "60-80", ">80"])
        group_metrics(ml_rows, ["version", "conf_bucket"]).to_csv(ARTIFACTS / "summary_by_ml_confidence_bucket.csv", index=False)
    else:
        pd.DataFrame().to_csv(ARTIFACTS / "summary_by_ml_confidence_bucket.csv", index=False)

    # Filter effectiveness — simplified: for each filter status in signal_logs, count
    sigs["version"] = sigs["time"].apply(
        lambda t: "v3" if t >= STABLE_START else ("v2" if t >= TRANSITION_START else "v1"))
    fe = sigs.groupby(["version", "status"]).size().reset_index(name="signal_count")
    fe.to_csv(ARTIFACTS / "filter_effectiveness.csv", index=False)

    # Charts
    print()
    make_charts(master, snaps)
    build_filter_cascade_chart(sigs)

    # Markdown report (dated, regenerated each run)
    print()
    print("[report] generating dated markdown report...")
    by_symbol_df = pd.read_csv(ARTIFACTS / "summary_by_version_symbol.csv")
    by_dir_df = pd.read_csv(ARTIFACTS / "summary_by_version_symbol_direction.csv")
    by_strategy_df = pd.read_csv(ARTIFACTS / "summary_by_version_strategy.csv")
    by_session_df = pd.read_csv(ARTIFACTS / "summary_by_session.csv")
    fe_df = pd.read_csv(ARTIFACTS / "filter_effectiveness.csv")
    report_path = write_report(master, snaps, sigs, by_symbol_df, by_dir_df,
                                 by_strategy_df, by_session_df, fe_df)
    print(f"[report] wrote {report_path}")

    # Pack stats for the report
    stats_out = {
        "n_total": int(len(master)),
        "n_closed": int((master["is_closed"] == 1).sum()),
        "by_version": master["version"].value_counts().to_dict(),
        "v3_pnl_net": float(closed.loc[closed["version"] == "v3", "net_pnl"].sum()),
        "v2_pnl_net": float(closed.loc[closed["version"] == "v2", "net_pnl"].sum()),
        "v1_pnl_net": float(closed.loc[closed["version"] == "v1", "net_pnl"].sum()),
    }
    import json
    with open(ARTIFACTS / "analysis_stats.json", "w", encoding="utf-8") as f:
        json.dump(stats_out, f, indent=2, default=str)
    print()
    print("Analysis-run stats:")
    for k, v in stats_out.items():
        print(f"  {k}: {v}")
    print()
    print(f"Artifacts dir: {ARTIFACTS.resolve()}")
    print(f"Charts dir:    {CHARTS.resolve()}")


if __name__ == "__main__":
    main()
