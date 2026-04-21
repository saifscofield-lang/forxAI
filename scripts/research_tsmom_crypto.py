"""Phase 10 step 3: TSMOM crypto prototype — IN-SAMPLE.

Runs 8 variants: direction (LO/LS) x lookback (12w/12m) x cost (10bps/20bps).
Universe: dynamic — BTC+ETH from 2017-08-17, BNB from 2017-11-06, SOL from 2020-08-11.
Benchmark: buy-and-hold BTC over each variant's own window.

Rebalance: weekly (Friday close). Vol target: 10% annualized.
Volatility estimator: 24-week rolling stdev of weekly returns.
Weight per asset: sign(momentum) x (target_vol / N_active) / asset_vol, capped at 1x leverage.

Outputs:
  data/research/tsmom_crypto_equity.csv      (weekly equity curves, all variants + BTC B&H)
  data/research/tsmom_crypto_positions.csv   (weekly positions by asset, primary variant)
  data/research/tsmom_crypto_metrics.csv     (all variants, all metrics)
  docs/research/tsmom_crypto_prototype.md    (human-readable report)
  docs/research/tsmom_crypto_equity_curves.png (comparison plot)
  improvements.db::tsmom_runs                (one row per variant, scope='crypto_*')
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------- config ----------

PAIRS = {"BTC/USDT": "BTC_USDT", "ETH/USDT": "ETH_USDT", "BNB/USDT": "BNB_USDT", "SOL/USDT": "SOL_USDT"}
TARGET_VOL_ANN = 0.10
VOL_WINDOW_W = 24
WEEKS_PER_YEAR = 52.0
REBAL_RULE = "W-FRI"
MAX_WEIGHT = 1.0

LOOKBACK_WEEKS = {"12w": 12, "12m": 52}
COSTS = {"c10bps": 0.001, "c20bps": 0.002}
DIRECTIONS = ("LO", "LS")  # long-only, long-short

OUT_DATA = Path("data/research")
OUT_DOCS = Path("docs/research")
OUT_DATA.mkdir(parents=True, exist_ok=True)
OUT_DOCS.mkdir(parents=True, exist_ok=True)

# ---------- load ----------

def load_weekly_close() -> pd.DataFrame:
    frames = []
    for sym, safe in PAIRS.items():
        p = Path(f"data/raw_crypto/{safe}/D1.parquet")
        df = pd.read_parquet(p)[["time", "close"]].set_index("time").rename(columns={"close": sym})
        frames.append(df)
    daily = pd.concat(frames, axis=1).sort_index()
    # Drop today's partial candle (latest date == today)
    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    daily = daily[daily.index < today]
    # Resample to weekly Friday close (last observation of the week)
    weekly = daily.resample(REBAL_RULE).last()
    return weekly


# ---------- engine ----------

def run_backtest(
    weekly_close: pd.DataFrame,
    direction: str,
    lookback_w: int,
    cost_per_side: float,
) -> dict:
    """Run one variant. Returns dict with equity, returns, positions, metrics."""
    ret = weekly_close.pct_change()  # weekly simple returns

    # Momentum signal: sum of past `lookback_w` log returns (sign determines direction)
    log_ret = np.log(1.0 + ret)
    mom = log_ret.rolling(lookback_w, min_periods=lookback_w).sum()
    sign = np.sign(mom)
    if direction == "LO":
        sign = sign.clip(lower=0.0)  # drop shorts

    # Annualized vol (weekly stdev * sqrt(52))
    vol_ann = ret.rolling(VOL_WINDOW_W, min_periods=VOL_WINDOW_W).std() * np.sqrt(WEEKS_PER_YEAR)

    # Active mask: both signal and vol available AND price known
    active = mom.notna() & vol_ann.notna() & (vol_ann > 1e-6) & ret.notna()

    # N_active per week
    n_active = active.sum(axis=1).replace(0, np.nan)

    # Raw weights (before cap and lag)
    # w_i = sign_i * (target_vol / N) / vol_i
    raw_w = sign.div(vol_ann).mul(TARGET_VOL_ANN).div(n_active, axis=0)
    raw_w = raw_w.where(active, 0.0)
    # Cap per-asset weight at MAX_WEIGHT
    weights = raw_w.clip(lower=-MAX_WEIGHT, upper=MAX_WEIGHT)

    # Lag weights by 1 week (signal computed at close of week t, earns return of week t+1)
    weights_lag = weights.shift(1).fillna(0.0)

    # Portfolio gross return (no costs)
    port_ret_gross = (weights_lag * ret).sum(axis=1)

    # Turnover = sum of |delta w| across assets
    turnover = weights_lag.diff().abs().sum(axis=1).fillna(weights_lag.abs().iloc[0].sum() if len(weights_lag) else 0.0)
    # Transaction costs per week
    tc = turnover * cost_per_side
    port_ret_net = port_ret_gross - tc

    # Keep only rows with at least one active asset (drop pre-warmup)
    valid_mask = n_active.notna()
    first_valid = port_ret_net.index[valid_mask][0] if valid_mask.any() else port_ret_net.index[0]
    port_ret_net = port_ret_net.loc[first_valid:]
    port_ret_gross = port_ret_gross.loc[first_valid:]
    turnover = turnover.loc[first_valid:]
    tc = tc.loc[first_valid:]
    weights_lag = weights_lag.loc[first_valid:]

    # First period: no prior return to earn, seed equity at 1.0 on first_valid
    equity = (1.0 + port_ret_net).cumprod()

    return {
        "equity": equity,
        "returns_net": port_ret_net,
        "returns_gross": port_ret_gross,
        "turnover": turnover,
        "costs": tc,
        "weights": weights_lag,
        "active_count": n_active.loc[first_valid:],
    }


def compute_metrics(equity: pd.Series, returns: pd.Series, turnover: pd.Series, label: str) -> dict:
    if len(returns) == 0:
        return {"label": label, "note": "empty"}
    returns = returns.dropna()
    equity = equity.dropna()
    start = equity.index[0]
    end = equity.index[-1]
    years = (end - start).days / 365.25
    total_ret = equity.iloc[-1] - 1.0
    cagr = (equity.iloc[-1]) ** (1.0 / years) - 1.0 if years > 0 else float("nan")
    ann_vol = returns.std(ddof=0) * np.sqrt(WEEKS_PER_YEAR)
    sharpe = (returns.mean() * WEEKS_PER_YEAR) / ann_vol if ann_vol > 0 else float("nan")
    downside = returns[returns < 0]
    sortino = (returns.mean() * WEEKS_PER_YEAR) / (downside.std(ddof=0) * np.sqrt(WEEKS_PER_YEAR)) if len(downside) > 1 and downside.std(ddof=0) > 0 else float("nan")
    peak = equity.cummax()
    dd = (equity / peak) - 1.0
    max_dd = dd.min()
    hit_weekly = float((returns > 0).mean())
    monthly_eq = equity.resample("ME").last().dropna()
    monthly_ret = monthly_eq.pct_change().dropna()
    hit_monthly = float((monthly_ret > 0).mean()) if len(monthly_ret) > 0 else float("nan")
    calmar = cagr / abs(max_dd) if max_dd < 0 else float("nan")
    avg_turnover = float(turnover.mean()) if len(turnover) else 0.0
    total_cost = float((turnover * 0).sum())  # placeholder, real costs accumulated in returns
    return {
        "label": label,
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "years": round(years, 2),
        "total_return_pct": round(100 * total_ret, 2),
        "cagr_pct": round(100 * cagr, 2),
        "ann_vol_pct": round(100 * ann_vol, 2),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "max_dd_pct": round(100 * max_dd, 2),
        "calmar": round(calmar, 3) if np.isfinite(calmar) else None,
        "hit_weekly_pct": round(100 * hit_weekly, 2),
        "hit_monthly_pct": round(100 * hit_monthly, 2) if np.isfinite(hit_monthly) else None,
        "avg_weekly_turnover": round(avg_turnover, 4),
        "n_weeks": int(len(returns)),
    }


def buy_and_hold(weekly_close: pd.DataFrame, sym: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Buy-and-hold equity curve aligned to the variant's start/end."""
    s = weekly_close[sym].loc[start:end].copy()
    s = s / s.iloc[0]
    return s


# ---------- main ----------

def main() -> None:
    weekly = load_weekly_close()
    print(f"[load] weekly frame: {weekly.shape} | {weekly.index.min().date()} -> {weekly.index.max().date()}")
    print(f"[load] first non-NaN per asset:")
    for col in weekly.columns:
        first = weekly[col].first_valid_index()
        print(f"         {col}: {first.date() if first is not None else 'NONE'}")

    variants = []
    for direction in DIRECTIONS:
        for lb_label, lb_weeks in LOOKBACK_WEEKS.items():
            for cost_label, cost in COSTS.items():
                name = f"crypto_{direction}_{lb_label}_{cost_label}"
                res = run_backtest(weekly, direction, lb_weeks, cost)
                m = compute_metrics(res["equity"], res["returns_net"], res["turnover"], name)
                m["direction"] = direction
                m["lookback"] = lb_label
                m["cost_bps"] = int(cost * 10000)
                variants.append({"name": name, "result": res, "metrics": m})
                print(f"[run] {name}: Sharpe {m['sharpe']} | CAGR {m['cagr_pct']}% | MaxDD {m['max_dd_pct']}% | {m['n_weeks']}w")

    # Buy-and-hold BTC benchmarks, one per variant (aligned to its window)
    bh_curves: dict[str, pd.Series] = {}
    for v in variants:
        eq = v["result"]["equity"]
        bh = buy_and_hold(weekly, "BTC/USDT", eq.index[0], eq.index[-1])
        bh_curves[v["name"]] = bh
        bh_ret = bh.pct_change().dropna()
        bh_metrics = compute_metrics(bh, bh_ret, pd.Series([0.0]), f"BH_BTC_{v['name']}")
        v["bh_metrics"] = bh_metrics

    # Save equity curves (all variants + one representative BH_BTC)
    eq_frame = pd.DataFrame({v["name"]: v["result"]["equity"] for v in variants})
    # Add longest-window BH BTC for reference
    longest = max(variants, key=lambda v: v["result"]["equity"].index[0].value * -1)  # earliest start = longest window
    longest_bh = buy_and_hold(weekly, "BTC/USDT", longest["result"]["equity"].index[0], longest["result"]["equity"].index[-1])
    eq_frame["BH_BTC"] = longest_bh
    eq_frame.to_csv(OUT_DATA / "tsmom_crypto_equity.csv")

    # Save primary variant positions (LO_12w_10bps)
    primary = next(v for v in variants if v["name"] == "crypto_LO_12w_c10bps")
    primary["result"]["weights"].to_csv(OUT_DATA / "tsmom_crypto_positions.csv")

    # Save metrics CSV
    rows = []
    for v in variants:
        rows.append({**v["metrics"], "role": "strategy"})
        rows.append({**v["bh_metrics"], "role": "benchmark"})
    metrics_df = pd.DataFrame(rows)
    metrics_df.to_csv(OUT_DATA / "tsmom_crypto_metrics.csv", index=False)

    # Equity curve plot — 4 panels by (direction, lookback) showing cost sensitivity vs BTC B&H
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), sharex=False)
    panels = [
        ("LO", "12w", axes[0, 0]),
        ("LO", "12m", axes[0, 1]),
        ("LS", "12w", axes[1, 0]),
        ("LS", "12m", axes[1, 1]),
    ]
    for direction, lb, ax in panels:
        for v in variants:
            if v["metrics"]["direction"] != direction or v["metrics"]["lookback"] != lb:
                continue
            eq = v["result"]["equity"]
            linestyle = "-" if v["metrics"]["cost_bps"] == 10 else "--"
            ax.plot(eq.index, eq.values, linestyle=linestyle, label=f"{v['name'].replace('crypto_','')}")
        # BH BTC on this panel
        ref_v = next(v for v in variants if v["metrics"]["direction"] == direction and v["metrics"]["lookback"] == lb)
        bh = bh_curves[ref_v["name"]]
        ax.plot(bh.index, bh.values, color="black", alpha=0.5, label="BH_BTC")
        ax.set_title(f"{direction} / {lb}")
        ax.set_yscale("log")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8, loc="upper left")
    fig.suptitle("TSMOM Crypto (IN-SAMPLE) — equity curves, log scale", fontsize=13)
    fig.tight_layout()
    png_path = OUT_DOCS / "tsmom_crypto_equity_curves.png"
    fig.savefig(png_path, dpi=110)
    plt.close(fig)

    # Persist to improvements.db::tsmom_runs (monthly-flavored cols approximated)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    con = sqlite3.connect("data/improvements.db")
    cur = con.cursor()
    for v in variants:
        m = v["metrics"]
        eq = v["result"]["equity"]
        monthly = eq.resample("ME").last().dropna()
        monthly_ret = monthly.pct_change().dropna()
        n_months = len(monthly_ret)
        best = float(monthly_ret.max()) if n_months > 0 else None
        worst = float(monthly_ret.min()) if n_months > 0 else None
        pos = int((monthly_ret > 0).sum())
        neg = int((monthly_ret < 0).sum())
        verdict = classify_verdict(m["sharpe"], m["cagr_pct"], m["max_dd_pct"], v["bh_metrics"]["cagr_pct"])
        notes = (
            f"IN-SAMPLE. {m['direction']} direction, {m['lookback']} lookback, "
            f"{m['cost_bps']} bps per side, weekly rebalance, 24w vol target 10% ann. "
            f"Universe dynamic (BTC+ETH from 2017, BNB from Nov-2017, SOL from 2020-08). "
            f"Benchmark BTC B&H over same window: CAGR {v['bh_metrics']['cagr_pct']}%, "
            f"Sharpe {v['bh_metrics']['sharpe']}, MaxDD {v['bh_metrics']['max_dd_pct']}%."
        )
        cur.execute("""
            INSERT INTO tsmom_runs
              (run_time, scope, n_months, start_date, end_date,
               annual_return, annual_vol, sharpe, sortino, max_drawdown,
               hit_rate_monthly, best_month, worst_month, positive_months, negative_months,
               cagr, verdict, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now, v["name"], n_months, m["start"], m["end"],
            m["cagr_pct"] / 100.0, m["ann_vol_pct"] / 100.0, m["sharpe"], m["sortino"], m["max_dd_pct"] / 100.0,
            (m["hit_monthly_pct"] or 0) / 100.0, best, worst, pos, neg,
            m["cagr_pct"] / 100.0, verdict, notes,
        ))
    con.commit()
    con.close()

    # Markdown report
    write_report(variants, png_path)

    # Terminal summary
    print()
    print("=" * 90)
    print("SUMMARY (IN-SAMPLE)")
    print("=" * 90)
    print(f"{'variant':<28} {'start':<12} {'years':>6} {'CAGR%':>8} {'Vol%':>7} {'Sharpe':>8} {'Sortino':>8} {'MaxDD%':>8} {'Calmar':>8} {'HitM%':>6}")
    for v in variants:
        m = v["metrics"]
        print(f"{m['label']:<28} {m['start']:<12} {m['years']:>6} {m['cagr_pct']:>8} {m['ann_vol_pct']:>7} {m['sharpe']:>8} {m['sortino']:>8} {m['max_dd_pct']:>8} {m['calmar'] if m['calmar'] is not None else 'nan':>8} {m['hit_monthly_pct'] if m['hit_monthly_pct'] is not None else 'nan':>6}")
    print()
    print("BUY-AND-HOLD BTC BENCHMARKS (aligned to each variant's window)")
    for v in variants:
        b = v["bh_metrics"]
        print(f"  {v['name']:<28} BH_BTC: CAGR {b['cagr_pct']}%, Sharpe {b['sharpe']}, MaxDD {b['max_dd_pct']}%")


def classify_verdict(sharpe: float, cagr_pct: float, maxdd_pct: float, bh_cagr_pct: float) -> str:
    """Reproduces the verdict-style labels used in the existing tsmom_runs table."""
    if not np.isfinite(sharpe):
        return "INSUFFICIENT"
    if sharpe >= 0.8 and cagr_pct > bh_cagr_pct:
        return "STRONG (in-sample)"
    if sharpe >= 0.4:
        return "MARGINAL (in-sample)"
    return "POOR (in-sample)"


def write_report(variants: list[dict], png_path: Path) -> None:
    lines = [
        "# TSMOM Crypto Prototype — IN-SAMPLE Results",
        "",
        f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
        "*Source: Binance D1 data (BTC/ETH/BNB/SOL USDT), resampled to weekly Friday close*",
        "",
        "> **⚠ IN-SAMPLE WARNING.** All numbers below use every available data point for parameter selection. ",
        "> Out-of-sample validation is Phase 10 step 4 (Purged K-Fold on 2017-2024, held-out test 2025-2026). ",
        "> Any Sharpe reported here is an **upper bound**; real out-of-sample performance will be lower.",
        "",
        "## Setup",
        "",
        "| Parameter | Value |",
        "|---|---|",
        "| Universe | BTC/USDT, ETH/USDT, BNB/USDT, SOL/USDT (Binance global) |",
        "| Universe policy | Dynamic — BTC+ETH from 2017-08-17, BNB from 2017-11-06, SOL from 2020-08-11 |",
        "| Frequency | D1 resampled to W-FRI close, weekly rebalance |",
        "| Vol estimator | 24-week rolling stdev × √52 |",
        "| Target portfolio vol | 10% annualized |",
        "| Per-asset weight | `sign(mom) × (target_vol / N_active) / σ_asset`, capped at ±1.0 |",
        "| Weight lag | 1 week (signal at close(t) earns return of t+1) |",
        "| Variants | direction × lookback × cost = 2 × 2 × 2 = 8 |",
        "",
        "## All Variants",
        "",
        "| Variant | Start | End | Years | CAGR % | Vol % | Sharpe | Sortino | MaxDD % | Calmar | Hit % (mo) | Weekly turnover |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for v in variants:
        m = v["metrics"]
        lines.append(
            f"| `{m['label']}` | {m['start']} | {m['end']} | {m['years']} | "
            f"{m['cagr_pct']} | {m['ann_vol_pct']} | **{m['sharpe']}** | {m['sortino']} | "
            f"{m['max_dd_pct']} | {m['calmar']} | {m['hit_monthly_pct']} | {m['avg_weekly_turnover']} |"
        )
    lines += ["", "## Buy-and-Hold BTC — benchmark over the same window", "",
              "| Variant window | BTC CAGR % | BTC Sharpe | BTC MaxDD % |",
              "|---|---:|---:|---:|"]
    seen = set()
    for v in variants:
        # dedupe by window (window only depends on lookback, not direction/cost)
        key = (v["metrics"]["lookback"], v["metrics"]["start"], v["metrics"]["end"])
        if key in seen:
            continue
        seen.add(key)
        b = v["bh_metrics"]
        lines.append(f"| {v['metrics']['lookback']} ({v['metrics']['start']} → {v['metrics']['end']}) | {b['cagr_pct']} | {b['sharpe']} | {b['max_dd_pct']} |")

    lines += [
        "",
        "## Equity curves",
        "",
        f"![TSMOM crypto IN-SAMPLE equity curves]({png_path.name})",
        "",
        "## Decisions this data supports (reviewer to confirm)",
        "",
        "- Does any variant clear the Phase-10 gate (**Sharpe ≥ 0.4 after costs**, in-sample)?",
        "- Does the strategy **beat buy-and-hold BTC** on CAGR over the same window?",
        "- Is the 12-week or 12-month lookback preferred? Does the ranking hold at 20 bps (cost stress)?",
        "- Is long-only alone competitive, or does long-short add meaningful diversification?",
        "",
        "## Known in-sample biases",
        "",
        "- **Full-period parameter selection.** Every knob (lookback, vol window, vol target, cost) is set on the same data we evaluate. Step 4 (OOS) will puncture overly optimistic numbers.",
        "- **No funding cost on shorts.** Real SOL/BNB short positions pay funding (~5-20% annual drag). LS variants are optimistic.",
        "- **No slippage model.** 10-20 bps cost covers taker fees but not market impact for larger AUM.",
        "- **Survivorship bias.** BTC/ETH/BNB/SOL all survived. Other coins that delisted are not in the universe.",
        "- **Today's candle dropped** during load; backtest ends at the most recent completed weekly bar.",
        "",
        "## Files",
        "",
        "- `data/research/tsmom_crypto_equity.csv` — weekly equity curves (all variants + BH_BTC)",
        "- `data/research/tsmom_crypto_positions.csv` — per-week positions (primary variant LO/12w/10bps)",
        "- `data/research/tsmom_crypto_metrics.csv` — metrics for all variants and benchmarks",
        "- `docs/research/tsmom_crypto_equity_curves.png` — comparison plot",
        "- `improvements.db::tsmom_runs` — one row per variant, `scope='crypto_*'`",
        "- `scripts/research_tsmom_crypto.py` — re-runnable",
        "",
    ]
    (OUT_DOCS / "tsmom_crypto_prototype.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
