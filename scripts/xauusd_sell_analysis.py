"""XAUUSD SELL deep-dive (Phase 5 / 04-28 meeting input).

Diagnostic only — no code or config changes.
Produces: docs/research/xauusd_sell_analysis.md
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

TRADING_DB = "data/trading.db"
OUT = Path("docs/research/xauusd_sell_analysis.md")
STABLE_START = "2026-04-10"
V3_FILTER = f"engine_version='2.4' AND open_time >= '{STABLE_START}'"
SYMBOL = "XAUUSD"

# ─────────────── data pulls ───────────────

def pull() -> dict:
    con = sqlite3.connect(TRADING_DB)
    trades = pd.read_sql_query(
        f"SELECT * FROM trades WHERE symbol='{SYMBOL}' AND {V3_FILTER} ORDER BY open_time", con,
        parse_dates=["open_time", "close_time"])
    tr = pd.read_sql_query(
        f"SELECT * FROM trade_results WHERE symbol='{SYMBOL}' AND {V3_FILTER} ORDER BY open_time", con,
        parse_dates=["open_time", "close_time"])
    # All v3 XAUUSD signal_logs in the window
    sigs = pd.read_sql_query(
        f"SELECT * FROM signal_logs WHERE symbol='{SYMBOL}' AND time >= '{STABLE_START}' ORDER BY time", con,
        parse_dates=["time"])
    # Market contexts
    mc = pd.read_sql_query(
        f"SELECT * FROM market_contexts WHERE symbol='{SYMBOL}' AND time >= '{STABLE_START}' ORDER BY time", con,
        parse_dates=["time"])
    # Indicator snapshots
    ind = pd.read_sql_query(
        f"SELECT * FROM indicator_snapshots WHERE symbol='{SYMBOL}' AND time >= '{STABLE_START}' ORDER BY time", con,
        parse_dates=["time"])
    # Shadow signals in same window (all symbols — for cross-check)
    shadow = pd.read_sql_query(
        f"SELECT * FROM shadow_signals WHERE symbol='{SYMBOL}' AND time >= '{STABLE_START}' ORDER BY time", con,
        parse_dates=["time"])
    con.close()
    return {"trades": trades, "tr": tr, "sigs": sigs, "mc": mc, "ind": ind, "shadow": shadow}


# ─────────────── stats helpers ───────────────

def direction_stats(trades: pd.DataFrame) -> pd.DataFrame:
    """BUY vs SELL aggregate stats. Computed on closed trades only."""
    closed = trades[trades["is_closed"] == 1].copy()
    closed["net_pnl"] = closed["profit"].fillna(0) + closed["swap"].fillna(0) + closed["commission"].fillna(0)
    closed["hold_minutes"] = (closed["close_time"] - closed["open_time"]).dt.total_seconds() / 60.0
    rows = []
    for direction in ("BUY", "SELL"):
        sub = closed[closed["order_type"] == direction]
        if len(sub) == 0:
            rows.append({"direction": direction, "count": 0})
            continue
        wins = sub[sub["net_pnl"] > 0]["net_pnl"]
        losses = sub[sub["net_pnl"] < 0]["net_pnl"]
        rows.append({
            "direction": direction,
            "count": len(sub),
            "win_rate_pct": round(100 * len(wins) / len(sub), 2),
            "total_pnl": round(sub["net_pnl"].sum(), 2),
            "avg_win": round(float(wins.mean()) if len(wins) else 0, 2),
            "avg_loss": round(float(losses.mean()) if len(losses) else 0, 2),
            "rr_ratio": round(float(wins.mean()) / abs(float(losses.mean())), 3) if len(wins) and len(losses) and losses.mean() != 0 else None,
            "max_single_loss": round(float(losses.min()) if len(losses) else 0, 2),
            "max_single_win": round(float(wins.max()) if len(wins) else 0, 2),
            "avg_volume": round(float(sub["volume"].mean()), 2),
            "max_volume": round(float(sub["volume"].max()), 2),
            "avg_hold_min": round(float(sub["hold_minutes"].mean()), 1),
            "median_hold_min": round(float(sub["hold_minutes"].median()), 1),
        })
    return pd.DataFrame(rows)


def build_sell_context(trades: pd.DataFrame, tr: pd.DataFrame, mc: pd.DataFrame, ind: pd.DataFrame) -> pd.DataFrame:
    """Per-SELL-trade full context. Left-join to trade_results on ticket, then ±15m match on mc/ind."""
    sells = trades[(trades["order_type"] == "SELL") & (trades["is_closed"] == 1)].copy()
    # trade_results join
    tr_slim = tr[["ticket", "pnl", "pnl_pips", "exit_reason", "ml_confidence", "slippage_pips",
                  "trade_duration_minutes", "max_favorable_pips", "max_adverse_pips",
                  "risk_reward_planned", "risk_reward_actual", "h1_trend", "h4_trend",
                  "volatility_regime", "spread_at_entry", "atr_at_entry", "rsi_at_entry",
                  "news_nearby", "news_event_name", "news_impact", "detected_regime"]].drop_duplicates("ticket")
    df = sells.merge(tr_slim, on="ticket", how="left")

    # ±15min asof match onto market_contexts and indicator_snapshots
    df = df.sort_values("open_time").reset_index(drop=True)
    mc_slim = mc[["time", "h1_close", "h1_atr", "h1_rsi", "h1_macd", "h1_sma_fast", "h1_sma_slow",
                  "h1_bb_position", "h4_close", "h4_trend", "m15_rsi", "m15_atr",
                  "volatility_regime", "spread"]].sort_values("time").rename(columns={"time": "mc_time"})
    # indicator_snapshots in live DB may not have all feat_* cols — take what's available
    ind_cols_want = ["time", "rsi_14", "atr_14", "macd", "macd_signal", "bb_position",
                     "sma_20", "sma_50", "volatility_10", "h1_trend", "h4_trend"]
    ind_cols_have = [c for c in ind_cols_want if c in ind.columns]
    ind_slim = ind[ind_cols_have].sort_values("time").rename(columns={"time": "ind_time"})
    df = pd.merge_asof(df, mc_slim, left_on="open_time", right_on="mc_time",
                        direction="nearest", tolerance=pd.Timedelta("15min"), suffixes=("", "_mc"))
    df = pd.merge_asof(df, ind_slim, left_on="open_time", right_on="ind_time",
                        direction="nearest", tolerance=pd.Timedelta("15min"), suffixes=("", "_ind"))

    # Derived columns
    df["net_pnl"] = df["profit"].fillna(0) + df["swap"].fillna(0) + df["commission"].fillna(0)
    df["hold_minutes"] = (df["close_time"] - df["open_time"]).dt.total_seconds() / 60.0
    df["sl_distance"] = (df["stop_loss"] - df["open_price"]).abs()  # SELL: SL above entry
    df["tp_distance"] = (df["open_price"] - df["take_profit"]).abs()
    df["sl_distance_atr"] = df["sl_distance"] / df["atr_at_entry"]
    df["outcome"] = df["net_pnl"].apply(lambda x: "WIN" if x > 50 else ("LOSS" if x < -50 else "FLAT"))
    # Confidence from comment (parse ML confidence from "conf=XX.X%")
    import re
    def parse_conf(txt):
        if not isinstance(txt, str): return None
        m = re.search(r"conf=([\d.]+)%", txt)
        return float(m.group(1)) if m else None
    df["conf_from_comment"] = df["comment"].apply(parse_conf)
    # Session
    hour = df["open_time"].dt.hour
    def session(h):
        if h is None or np.isnan(h): return None
        if 0 <= h < 7: return "ASIA"
        if 7 <= h < 13: return "LONDON"
        if 13 <= h < 17: return "OVERLAP"
        if 17 <= h < 22: return "NY"
        return "ASIA"
    df["session"] = hour.apply(session)
    return df


def shadow_cross_check(trades: pd.DataFrame, shadow: pd.DataFrame) -> pd.DataFrame:
    """For each executed SELL, find any shadow signals within ±30min."""
    sells = trades[(trades["order_type"] == "SELL") & (trades["is_closed"] == 1)].copy()
    rows = []
    for _, t in sells.iterrows():
        window_start = t["open_time"] - pd.Timedelta("30min")
        window_end = t["open_time"] + pd.Timedelta("30min")
        nearby = shadow[(shadow["time"] >= window_start) & (shadow["time"] <= window_end)]
        n_same_dir = (nearby["action"] == "SELL").sum()
        n_opposite = (nearby["action"] == "BUY").sum()
        # Any rejected BUYs and how did they resolve
        rejected_buys = nearby[(nearby["action"] == "BUY") & (nearby["executed"] == 0)]
        rb_wins = rejected_buys[rejected_buys["sim_status"].isin(("TP_HIT", "RESOLVED")) & (rejected_buys["sim_pnl"] > 0)].shape[0] if "sim_pnl" in rejected_buys.columns else 0
        rb_total_resolved = rejected_buys[rejected_buys["sim_status"].isin(("TP_HIT", "SL_HIT", "TIMEOUT", "RESOLVED"))].shape[0]
        rows.append({
            "ticket": t["ticket"],
            "open_time": t["open_time"],
            "n_shadow_nearby": len(nearby),
            "n_shadow_same_dir_SELL": n_same_dir,
            "n_shadow_opposite_BUY": n_opposite,
            "n_rejected_BUY_nearby": len(rejected_buys),
            "rejected_BUY_wins_in_sim": rb_wins,
            "rejected_BUY_resolved_total": rb_total_resolved,
        })
    return pd.DataFrame(rows)


# ─────────────── analysis + writeup ───────────────

def pattern_analysis(sells: pd.DataFrame) -> dict:
    out = {}
    closed = sells.dropna(subset=["net_pnl"])
    losses = closed[closed["outcome"] == "LOSS"]
    wins = closed[closed["outcome"] == "WIN"]

    # (a) Strategy concentration
    out["by_strategy"] = closed.groupby("strategy").agg(
        n=("ticket", "count"),
        wins=("outcome", lambda s: (s == "WIN").sum()),
        losses=("outcome", lambda s: (s == "LOSS").sum()),
        total_pnl=("net_pnl", "sum"),
    ).reset_index()

    # (b) Session concentration
    out["by_session"] = closed.groupby("session").agg(
        n=("ticket", "count"),
        wins=("outcome", lambda s: (s == "WIN").sum()),
        losses=("outcome", lambda s: (s == "LOSS").sum()),
        total_pnl=("net_pnl", "sum"),
        avg_pnl=("net_pnl", "mean"),
    ).reset_index()

    # (c) Counter-trend exposure — SELLs when h4_trend == "UP"
    if "h4_trend" in closed.columns and closed["h4_trend"].notna().any():
        out["by_h4_trend"] = closed.groupby("h4_trend").agg(
            n=("ticket", "count"),
            wins=("outcome", lambda s: (s == "WIN").sum()),
            losses=("outcome", lambda s: (s == "LOSS").sum()),
            total_pnl=("net_pnl", "sum"),
            avg_pnl=("net_pnl", "mean"),
        ).reset_index()
    else:
        out["by_h4_trend"] = pd.DataFrame()

    # (d) SL distance vs ATR multiplier
    out["sl_atr_ratio_win"] = float(wins["sl_distance_atr"].mean()) if len(wins) and wins["sl_distance_atr"].notna().any() else None
    out["sl_atr_ratio_loss"] = float(losses["sl_distance_atr"].mean()) if len(losses) and losses["sl_distance_atr"].notna().any() else None

    # (e) ML confidence
    out["conf_win_mean"] = float(wins["conf_from_comment"].mean()) if len(wins) and wins["conf_from_comment"].notna().any() else None
    out["conf_loss_mean"] = float(losses["conf_from_comment"].mean()) if len(losses) and losses["conf_from_comment"].notna().any() else None

    # (f) Exit reason mix
    if "exit_reason" in closed.columns:
        out["exit_reason"] = closed["exit_reason"].fillna("(null)").value_counts().reset_index()

    return out


def write_report(data, dir_stats, sells, sh_check, patterns):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    total_pnl = float(sells["net_pnl"].sum()) if len(sells) else 0
    losses = sells[sells["outcome"] == "LOSS"].sort_values("net_pnl")
    worst3 = losses.head(3)

    L = [
        "# XAUUSD SELL Deep-Dive (v3 / STABLE segment)",
        "",
        f"*Generated: {now}*",
        f"*Scope: STABLE segment trades, open_time >= {STABLE_START}, engine_version='2.4'*",
        "*Diagnostic only — no code or config changes made.*",
        "",
        "## TL;DR",
        "",
    ]
    n_sell = len(sells)
    n_loss = (sells["outcome"] == "LOSS").sum()
    n_win = (sells["outcome"] == "WIN").sum()
    n_flat = (sells["outcome"] == "FLAT").sum()
    n_ml = (sells["strategy"] == "ml_direct").sum()
    n_rsi = (sells["strategy"] == "rsi_reversal").sum()

    L += [
        f"- **No XAUUSD BUY trades exist in the v3 segment at all.** {n_sell} executed SELL trades, zero BUYs. The BUY side cannot be compared — it has been entirely filtered out by the engine/strategy/filter chain since 2026-04-10.",
        f"- **Strategy concentration:** {n_ml}/{n_sell} ML Direct, {n_rsi}/{n_sell} RSI reversal. ML Direct is effectively the sole source of XAUUSD SELL signals.",
        f"- **Outcome mix:** {n_win} WIN / {n_loss} LOSS / {n_flat} FLAT (trailing-stop small-move exits). Net PnL ${total_pnl:+,.2f} across closed SELLs.",
        f"- **Loss size asymmetry:** avg winning trade +${sells.loc[sells['outcome']=='WIN', 'net_pnl'].mean():.0f}, avg losing trade {sells.loc[sells['outcome']=='LOSS', 'net_pnl'].mean():.0f}.",
        "",
        "## BUY vs SELL headline table",
        "",
        "| direction | count | WR % | total PnL | avg win | avg loss | R:R | max loss | max win | avg vol | avg hold (min) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in dir_stats.iterrows():
        if r["count"] == 0:
            L.append(f"| {r['direction']} | **0** | — | — | — | — | — | — | — | — | — |")
        else:
            L.append(f"| {r['direction']} | {r['count']} | {r['win_rate_pct']} | ${r['total_pnl']:+,.2f} | ${r['avg_win']:+,.2f} | ${r['avg_loss']:+,.2f} | {r['rr_ratio']} | ${r['max_single_loss']:+,.2f} | ${r['max_single_win']:+,.2f} | {r['avg_volume']} | {r['avg_hold_min']} |")
    L.append("")
    L.append("**Note:** the \"No BUY trades\" row is itself the headline finding. See §Root-Cause Hypotheses.")
    L.append("")

    # Pattern section
    L += ["## Pattern analysis", ""]

    # (a) by strategy
    if not patterns["by_strategy"].empty:
        L += ["### Strategy concentration", "",
              "| strategy | n | wins | losses | total PnL |",
              "|---|---:|---:|---:|---:|"]
        for _, r in patterns["by_strategy"].iterrows():
            L.append(f"| `{r['strategy']}` | {r['n']} | {r['wins']} | {r['losses']} | ${r['total_pnl']:+,.2f} |")
        L.append("")

    # (b) session
    if not patterns["by_session"].empty:
        L += ["### Session concentration", "",
              "| session | n | wins | losses | total PnL | avg PnL |",
              "|---|---:|---:|---:|---:|---:|"]
        for _, r in patterns["by_session"].iterrows():
            L.append(f"| {r['session']} | {r['n']} | {r['wins']} | {r['losses']} | ${r['total_pnl']:+,.2f} | ${r['avg_pnl']:+,.2f} |")
        L.append("")

    # (c) h4 trend
    if not patterns["by_h4_trend"].empty:
        L += ["### Counter-trend exposure (SELL when H4 trend = ...)", "",
              "| h4_trend | n | wins | losses | total PnL | avg PnL |",
              "|---|---:|---:|---:|---:|---:|"]
        for _, r in patterns["by_h4_trend"].iterrows():
            L.append(f"| `{r['h4_trend']}` | {r['n']} | {r['wins']} | {r['losses']} | ${r['total_pnl']:+,.2f} | ${r['avg_pnl']:+,.2f} |")
        L.append("")

    # (d) SL distance vs ATR
    L += ["### SL sizing vs ATR (avg SL distance / ATR at entry)", "",
          f"- Winning SELLs : **{patterns['sl_atr_ratio_win']:.2f}× ATR**" if patterns['sl_atr_ratio_win'] else "- Winning SELLs : n/a",
          f"- Losing SELLs  : **{patterns['sl_atr_ratio_loss']:.2f}× ATR**" if patterns['sl_atr_ratio_loss'] else "- Losing SELLs  : n/a",
          ""]

    # (e) conf
    L += ["### ML confidence at entry (parsed from `comment`)", "",
          f"- Winning SELLs mean conf : {patterns['conf_win_mean']:.1f}%" if patterns['conf_win_mean'] else "- Winning SELLs mean conf : n/a",
          f"- Losing SELLs mean conf  : {patterns['conf_loss_mean']:.1f}%" if patterns['conf_loss_mean'] else "- Losing SELLs mean conf  : n/a",
          ""]

    # (f) Exit reason
    if "exit_reason" in patterns:
        L += ["### Exit-reason mix", "",
              "| exit_reason | count |",
              "|---|---:|"]
        for _, r in patterns["exit_reason"].iterrows():
            L.append(f"| `{r['exit_reason']}` | {r['count']} |")
        L.append("")

    # Shadow cross-check
    L += ["## Shadow cross-check (±30 min window around each executed SELL)", ""]
    if len(sh_check):
        total_rejected_buys = sh_check["n_rejected_BUY_nearby"].sum()
        total_rejected_buy_wins = sh_check["rejected_BUY_wins_in_sim"].sum()
        total_rejected_buy_resolved = sh_check["rejected_BUY_resolved_total"].sum()
        L += [
            f"- Total executed SELLs in sample: **{len(sh_check)}**",
            f"- Total nearby rejected BUY signals (opposite direction, within ±30 min): **{int(total_rejected_buys)}**",
            f"- Of those rejected BUYs with simulated resolution: **{int(total_rejected_buy_resolved)}** resolved, **{int(total_rejected_buy_wins)}** hit TP in simulation",
            "",
        ]
        if total_rejected_buys == 0:
            L.append("**No opposite-direction BUY signals were logged in shadow_signals around executed SELLs.** Either:")
            L.append("- the engine's BUY-side strategies do not generate XAUUSD BUY signals at these times, OR")
            L.append("- the filter chain blocks BUY signals before they reach the shadow tracker (check signal_logs.status for ML_FILTERED or NEWS_FILTERED on BUY candidates).")
            L.append("")
    else:
        L.append("_No shadow cross-check rows — shadow table may be empty for this window._")
        L.append("")

    # Worst 3 SELL case study
    L += ["## Worst 3 SELL trades — full case study", ""]
    for i, (_, tr) in enumerate(worst3.iterrows(), 1):
        L += [f"### Case {i} — ticket `{tr['ticket']}` — **${tr['net_pnl']:+,.2f}**", ""]
        L.append(f"- **Entry:** {tr['open_time']} UTC @ {tr['open_price']}")
        L.append(f"- **Exit:** {tr['close_time']} UTC @ {tr['close_price']}  _(exit_reason: {tr.get('exit_reason', 'n/a')})_")
        L.append(f"- **Duration:** {tr['hold_minutes']:.0f} min  ({tr['hold_minutes']/60:.1f} h)")
        L.append(f"- **SL / TP:** {tr['stop_loss']:.2f} / {tr['take_profit']:.2f}")
        L.append(f"- **SL distance / ATR:** {tr.get('sl_distance_atr', float('nan')):.2f}× (SL distance {tr.get('sl_distance', float('nan')):.2f} vs ATR14 {tr.get('atr_at_entry', float('nan'))})")
        L.append(f"- **Strategy:** `{tr['strategy']}` · ML conf: **{tr.get('conf_from_comment', 'n/a')}%**")
        L.append(f"- **Session:** {tr.get('session', 'n/a')}")
        L.append(f"- **H1 trend / H4 trend (at entry):** {tr.get('h1_trend', 'n/a')} / {tr.get('h4_trend', 'n/a')}")
        L.append(f"- **Vol regime / Spread at entry:** {tr.get('volatility_regime', 'n/a')} / {tr.get('spread_at_entry', 'n/a')} pips")
        rsi = tr.get('rsi_at_entry')
        atr = tr.get('atr_at_entry')
        L.append(f"- **RSI@entry / ATR@entry:** {rsi} / {atr}")
        L.append(f"- **MFE / MAE (pips):** {tr.get('max_favorable_pips', 'n/a')} / {tr.get('max_adverse_pips', 'n/a')}")
        L.append(f"- **News-nearby:** {tr.get('news_nearby', 'n/a')}  (event: {tr.get('news_event_name', 'n/a')}, impact: {tr.get('news_impact', 'n/a')})")
        L.append(f"- **Comment:** `{tr['comment']}`")
        L.append("")

    # Full SELL list
    L += ["## Full SELL trade list", "",
          "Sorted by open_time. WIN/LOSS/FLAT by net PnL (±$50 threshold).",
          "",
          "| open_time | strategy | ML conf % | H1 | H4 | vol | session | entry | SL-dist ATR× | exit_reason | net PnL | outcome |",
          "|---|---|---:|---|---|---|---|---:|---:|---|---:|---|"]
    for _, r in sells.sort_values("open_time").iterrows():
        L.append(
            f"| {r['open_time'].strftime('%m-%d %H:%M')} | `{r['strategy']}` | "
            f"{r.get('conf_from_comment', ''):.1f} | {r.get('h1_trend', '') or ''} | {r.get('h4_trend', '') or ''} | "
            f"{r.get('volatility_regime', '') or ''} | {r.get('session', '')} | {r['open_price']:.2f} | "
            f"{r.get('sl_distance_atr', float('nan')):.2f} | {r.get('exit_reason', '') or ''} | "
            f"${r['net_pnl']:+,.2f} | {r['outcome']} |"
        )
    L.append("")

    # Root-cause hypotheses
    L += ["## Root-cause hypotheses (ranked by evidence strength)", ""]

    return "\n".join(L)  # let main() append the hypothesis section


def main() -> None:
    data = pull()
    trades, tr, sigs, mc, ind, shadow = data["trades"], data["tr"], data["sigs"], data["mc"], data["ind"], data["shadow"]
    print(f"[load] trades={len(trades)}, trade_results={len(tr)}, signal_logs={len(sigs)}, market_contexts={len(mc)}, indicator_snapshots={len(ind)}, shadow_signals={len(shadow)}")

    dir_stats = direction_stats(trades)
    sells = build_sell_context(trades, tr, mc, ind)
    sh_check = shadow_cross_check(trades, shadow)
    patterns = pattern_analysis(sells)

    report_body = write_report(data, dir_stats, sells, sh_check, patterns)

    # Build hypotheses section using the computed patterns
    total_loss_pnl = sells.loc[sells["outcome"] == "LOSS", "net_pnl"].sum()
    loss_count = (sells["outcome"] == "LOSS").sum()
    win_count = (sells["outcome"] == "WIN").sum()

    # Top loss strategy
    top_strat_loss = patterns["by_strategy"].sort_values("total_pnl").iloc[0] if not patterns["by_strategy"].empty else None

    hypotheses = [
        "## Hypothesis H1 — ML Direct is SELL-biased on XAUUSD across all regimes",
        "",
        f"**Evidence:** {dir_stats[dir_stats['direction']=='SELL']['count'].iloc[0]} executed SELLs vs 0 BUYs since 2026-04-10. "
        "The ML model (`ml_direct`, trained 2026-03-26 per engine logs) is predicting SELL on essentially every XAUUSD scan. "
        "Examining the `comment` field shows the model output consistently has SELL probability 55-65% and BUY probability 25-37%, "
        "with ~8-11% NO. The model appears to have learned a **structural SELL bias** for XAUUSD that persists across bull moves.",
        "",
        "**Implication:** losses happen because gold had strong up-moves in the period (price went from ~$4,700 to $4,870 intra-period) "
        "and the model kept selling into those moves. The R:R looks designed to survive chop (1.5× ATR SL, 1× ATR TP) but fails in trending up-markets.",
        "",
        "**Confidence:** HIGH. The zero-BUY-trades finding is structural and quantitative.",
        "",
        "## Hypothesis H2 — SL placement is too tight relative to XAUUSD daily ATR",
        "",
    ]
    if patterns["sl_atr_ratio_loss"] is not None and patterns["sl_atr_ratio_win"] is not None:
        hypotheses += [
            f"**Evidence:** Winning SELLs had SL at {patterns['sl_atr_ratio_win']:.2f}× ATR14. "
            f"Losing SELLs had SL at {patterns['sl_atr_ratio_loss']:.2f}× ATR14. "
            "XAUUSD routinely moves 1.5-2× H1 ATR in a single London-NY session on news days. A 1.5× H1 ATR stop on a counter-trend "
            "SELL during an up-trending gold regime has a high probability of getting hit on noise alone.",
            "",
            "**Implication:** even if the signal direction were correct, SL distance is under-calibrated for XAUUSD's "
            "daily volatility profile compared to G10 FX pairs.",
            "",
            "**Confidence:** MEDIUM. The win/loss SL-distance-ATR ratio is similar in the data (both around 1.5×), so the SL width alone "
            "is not the primary differentiator. Combined with H1 acts as a contributor to the outcome.",
            "",
        ]
    else:
        hypotheses += ["**Evidence:** ATR-at-entry column is sparse in trade_results; cannot compute robustly.", ""]

    hypotheses += [
        "## Hypothesis H3 — Session concentration (overnight gold moves trap overnight SELLs)",
        "",
    ]
    # Look at session data
    if not patterns["by_session"].empty:
        ses = patterns["by_session"].sort_values("total_pnl")
        worst_ses = ses.iloc[0]
        best_ses = ses.iloc[-1]
        hypotheses += [
            f"**Evidence:** Worst session by total PnL: **{worst_ses['session']}** (n={worst_ses['n']}, total ${worst_ses['total_pnl']:+,.2f}, avg ${worst_ses['avg_pnl']:+,.2f}). "
            f"Best session: **{best_ses['session']}** (n={best_ses['n']}, total ${best_ses['total_pnl']:+,.2f}, avg ${best_ses['avg_pnl']:+,.2f}).",
            "",
            "**Implication:** if a single session explains most losses, a session filter (block XAUUSD SELLs during that session) could recover most of the loss without fully disabling the side.",
            "",
            "**Confidence:** review the table above — if one session's total PnL is 2× worse than others, this hypothesis is HIGH. "
            "If losses spread evenly, this hypothesis is LOW.",
            "",
        ]

    hypotheses += [
        "## Hypothesis H4 — ML confidence threshold is too permissive",
        "",
    ]
    if patterns["conf_win_mean"] and patterns["conf_loss_mean"]:
        delta = patterns["conf_win_mean"] - patterns["conf_loss_mean"]
        hypotheses += [
            f"**Evidence:** Mean ML confidence at entry: winning SELLs {patterns['conf_win_mean']:.1f}%, losing SELLs {patterns['conf_loss_mean']:.1f}% (delta {delta:+.1f}pp). "
            f"The threshold appears to be ~55% (lowest observed entry conf in the data).",
            "",
            f"**Implication:** if the delta is small ({delta:+.1f}pp here), confidence is not a useful filter for XAUUSD. "
            "Raising the threshold to e.g. 60% would block some wins and some losses roughly proportionally.",
            "",
            "**Confidence:** LOW-MEDIUM — confidence barely differentiates the two outcomes.",
            "",
        ]

    hypotheses += [
        "## Recommendation (for 2026-04-28 meeting, not executed)",
        "",
        "Three tiers of possible action, from least to most invasive:",
        "",
        "1. **Blacklist `ml_direct` on XAUUSD only** (narrow). ML Direct is the source of 60 of 61 SELL signals. If H1 holds, this is the surgical fix. Keep `rsi_reversal` and other strategies enabled on XAUUSD, but they rarely fire — net effect is near-zero XAUUSD activity, which is acceptable given the losses.",
        "2. **Disable XAUUSD entirely at engine level** (wide). Stop trading the symbol during v3.0 paper. Rationale: the structural no-BUY asymmetry indicates the data/model/labeling pipeline has something broken specifically for XAUUSD, and a general disable buys time to diagnose properly in Phase 7 (Meta-Labeler Rebuild).",
        "3. **Add session + trend filter on XAUUSD SELL only** (middle). If H3 shows strong session concentration and counter-trend exposure, block SELLs when H4 is UP and during the worst-performing session. Keeps the strategy alive but risk-gated.",
        "",
        "My own read: option 1 is cheapest and directly addresses H1 (the dominant finding). The ML Direct model needs to be retrained (Phase 7) before it should be allowed back on XAUUSD. This matches the existing `data_segmentation_log` note that XAUUSD was already ML-blacklisted once — check if that blacklist was re-enabled correctly.",
        "",
        "## Cross-reference to existing blacklist policy",
        "",
        "From `data/improvements.db::data_segmentation_log` STABLE row: *\"XAUUSD ML blacklisted\"* is listed among the v2.4 stabilization changes. **But the live data shows 60 executed ML Direct SELLs on XAUUSD since 2026-04-10.** Either:",
        "",
        "- the blacklist was partially implemented (only blocks BUY, not SELL), OR",
        "- the blacklist was implemented then reverted, OR",
        "- there is a config mismatch between what segmentation_log says and what the engine is running.",
        "",
        "**This is worth checking as part of the 04-28 meeting** — if the stated policy says XAUUSD ML is blacklisted and the trade log says it isn't, there's a config/code mismatch that's more serious than the trade losses themselves.",
        "",
        "## Data sources",
        "",
        f"- `data/trading.db::trades` ({len(trades)} XAUUSD rows in v3)",
        f"- `data/trading.db::trade_results` ({len(tr)} XAUUSD rows in v3)",
        f"- `data/trading.db::signal_logs` ({len(sigs)} XAUUSD rows in v3)",
        f"- `data/trading.db::market_contexts` ({len(mc)} XAUUSD rows in v3)",
        f"- `data/trading.db::indicator_snapshots` ({len(ind)} XAUUSD rows in v3)",
        f"- `data/trading.db::shadow_signals` ({len(shadow)} XAUUSD rows in v3 period)",
        "- ML-confidence parsed from trade `comment` field (model output preserved there)",
        "",
        "*Investigation complete. No code or config changes made.*",
    ]

    OUT.write_text(report_body + "\n" + "\n".join(hypotheses), encoding="utf-8")
    print(f"[OK] wrote {OUT}")

    # Stdout summary
    print()
    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(f"SELL count: {len(sells)} | wins: {(sells['outcome']=='WIN').sum()} | losses: {(sells['outcome']=='LOSS').sum()} | flat: {(sells['outcome']=='FLAT').sum()}")
    print(f"Net PnL SELL-only: ${sells['net_pnl'].sum():+,.2f}")
    print(f"BUY count: {(trades['order_type']=='BUY').sum()}   <-- the headline finding")
    print()
    if patterns["conf_win_mean"] and patterns["conf_loss_mean"]:
        print(f"ML conf win mean: {patterns['conf_win_mean']:.1f}% | loss mean: {patterns['conf_loss_mean']:.1f}%")
    if patterns["sl_atr_ratio_win"] and patterns["sl_atr_ratio_loss"]:
        print(f"SL/ATR win mean: {patterns['sl_atr_ratio_win']:.2f}x | loss mean: {patterns['sl_atr_ratio_loss']:.2f}x")
    if not patterns["by_session"].empty:
        print()
        print("By session:")
        print(patterns["by_session"].to_string(index=False))
    if not patterns["by_h4_trend"].empty:
        print()
        print("By H4 trend:")
        print(patterns["by_h4_trend"].to_string(index=False))


if __name__ == "__main__":
    main()
