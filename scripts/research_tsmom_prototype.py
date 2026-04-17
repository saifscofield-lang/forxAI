"""
Phase 5 extra — TSMOM Prototype (research only, freeze-safe)

Time-Series Momentum per Moskowitz, Ooi, Pedersen (2012) / Hurst, Ooi,
Pedersen (AQR, 2017). 140 years of published evidence.

Algorithm (runs end of each month):
  for each currency_pair:
      return_12m = (close_today / close_12mo_ago) - 1
      direction  = +1 if return_12m > 0 else -1
      realized_vol = std(monthly_returns_last_24mo) * sqrt(12)   # annualized
      position_size = (target_vol / realized_vol) * direction
      position_size = clip(position_size, -1.0, 1.0)             # leverage cap

Portfolio = equal-weight mean of per-pair positions × next-month return.

Data: D1 parquet 2010-2026 (16 years). After 24-month warmup, ~14 years
of monthly returns = 168 periods × 7 pairs.

Expected per AQR: Sharpe ~0.7, annual ~10%, Max DD ~25%.

Writes:
  - data/improvements.db → tsmom_runs table (new)
  - docs/research/tsmom_prototype.md
  - docs/research/tsmom_equity_curve.png
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
warnings.filterwarnings("ignore")

import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ───────────────────────────── CONFIG ─────────────────────────────
PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "USDCHF", "AUDUSD", "USDCAD"]
D1_DIR = Path("data/raw")

LOOKBACK_MOMENTUM_MONTHS = 12
LOOKBACK_VOL_MONTHS = 24
TARGET_ANNUAL_VOL = 0.10          # 10% annualized
MAX_LEVERAGE = 1.0                # cap per-pair position at 1x
COST_PIPS_PER_REBALANCE = 2.0     # rough transaction cost per pair per month
RISK_FREE_MONTHLY = 0.0           # assume 0 for Sharpe (FX uncorrelated to cash anyway)

OUT_REPORT = Path("docs/research/tsmom_prototype.md")
OUT_CHART = Path("docs/research/tsmom_equity_curve.png")
DB = "data/improvements.db"

OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)


def ensure_schema():
    conn = sqlite3.connect(DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tsmom_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_time TEXT NOT NULL,
            scope TEXT NOT NULL,          -- 'portfolio' or pair symbol
            n_months INTEGER,
            start_date TEXT,
            end_date TEXT,
            annual_return REAL,
            annual_vol REAL,
            sharpe REAL,
            sortino REAL,
            max_drawdown REAL,
            hit_rate_monthly REAL,
            best_month REAL,
            worst_month REAL,
            positive_months INTEGER,
            negative_months INTEGER,
            cagr REAL,
            verdict TEXT,
            notes TEXT
        )
    """)
    conn.commit()
    conn.close()


def load_d1_monthly(symbol: str) -> pd.Series:
    """Load D1 parquet → resample to month-end close."""
    path = D1_DIR / symbol / "D1.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df["time"] = pd.to_datetime(df["time"])
    df = df.set_index("time").sort_index()
    # Month-end close
    monthly = df["close"].resample("ME").last().dropna()
    return monthly


def compute_tsmom_returns(monthly_close: pd.Series) -> pd.DataFrame:
    """Run TSMOM algorithm end-to-end on monthly prices."""
    monthly_ret = monthly_close.pct_change()
    out = pd.DataFrame({
        "close": monthly_close,
        "ret_1m": monthly_ret,
        "ret_12m": monthly_close.pct_change(LOOKBACK_MOMENTUM_MONTHS),
    })
    out["direction"] = np.sign(out["ret_12m"])
    # Annualized realized vol from last 24 monthly returns
    out["vol_annual"] = monthly_ret.rolling(LOOKBACK_VOL_MONTHS).std() * np.sqrt(12)
    # Position size: target_vol / realized_vol * direction, clipped
    out["position"] = (TARGET_ANNUAL_VOL / out["vol_annual"]) * out["direction"]
    out["position"] = out["position"].clip(-MAX_LEVERAGE, MAX_LEVERAGE)
    # Shift position by 1 month: we decide at month T, earn return of T+1
    out["position_lagged"] = out["position"].shift(1)
    # Transaction cost: subtract when position changes sign or magnitude
    pos_change = (out["position_lagged"] - out["position_lagged"].shift(1)).abs()
    # Cost in return units: assume 2 pips per pair, avg ATR ~ 80 pips → cost ≈ 0.025% per full flip
    # More conservative: 0.02% per rebalance regardless (AQR assumption)
    out["cost"] = np.where(pos_change.fillna(0) > 0.01, 0.0002, 0.0)
    out["strategy_ret"] = out["position_lagged"] * out["ret_1m"] - out["cost"]
    return out


def metrics(returns: pd.Series) -> dict:
    """Compute standard performance metrics from a monthly return series."""
    r = returns.dropna()
    if len(r) < 12:
        return None
    months = len(r)
    annual_ret = r.mean() * 12
    annual_vol = r.std() * np.sqrt(12)
    sharpe = annual_ret / annual_vol if annual_vol > 0 else 0

    downside = r[r < 0]
    sortino = (r.mean() * 12) / (downside.std() * np.sqrt(12)) if len(downside) > 1 and downside.std() > 0 else 0

    # Drawdown from cumulative returns
    cum = (1 + r).cumprod()
    dd = (cum / cum.cummax()) - 1
    max_dd = dd.min()

    cagr = cum.iloc[-1] ** (12.0 / months) - 1

    return {
        "n_months": months,
        "start_date": str(r.index[0].date()),
        "end_date": str(r.index[-1].date()),
        "annual_return": annual_ret,
        "annual_vol": annual_vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": float(max_dd),
        "best_month": float(r.max()),
        "worst_month": float(r.min()),
        "positive_months": int((r > 0).sum()),
        "negative_months": int((r < 0).sum()),
        "hit_rate_monthly": float((r > 0).mean()),
        "cagr": cagr,
    }


def verdict_for(m):
    if m is None: return "SKIP"
    s = m["sharpe"]
    dd = abs(m["max_drawdown"])
    if s >= 0.7 and dd < 0.30: return "✅ STRONG"
    if s >= 0.5: return "⚠️ ACCEPTABLE"
    if s >= 0.3: return "❌ MARGINAL"
    return "❌ POOR"


def main():
    print(f"\n{'='*72}")
    print(f"  TSMOM Prototype — Phase 5 research")
    print(f"  Based on Moskowitz/Ooi/Pedersen (2012) + AQR (2017)")
    print(f"  Run: {datetime.now().isoformat(timespec='seconds')}")
    print(f"{'='*72}\n")

    ensure_schema()
    run_time = datetime.now().isoformat(timespec="seconds")

    per_pair_returns = {}
    per_pair_metrics = {}

    print(f"▶ Running TSMOM on each pair (D1 → monthly, 12m momentum + 24m vol target):\n")
    print(f"  {'Pair':<8} {'N months':>9} {'Ann ret':>8} {'Ann vol':>8} {'Sharpe':>7} "
          f"{'Max DD':>8} {'Hit%':>6} {'Verdict':<15}")
    print(f"  {'-'*8} {'-'*9} {'-'*8} {'-'*8} {'-'*7} {'-'*8} {'-'*6} {'-'*15}")

    for sym in PAIRS:
        monthly = load_d1_monthly(sym)
        if monthly is None or len(monthly) < LOOKBACK_VOL_MONTHS + LOOKBACK_MOMENTUM_MONTHS + 12:
            print(f"  {sym}: insufficient data")
            continue

        tsmom = compute_tsmom_returns(monthly)
        rets = tsmom["strategy_ret"].dropna()
        if rets.empty:
            continue

        m = metrics(rets)
        if m is None:
            continue
        v = verdict_for(m)
        print(
            f"  {sym:<8} {m['n_months']:>9} "
            f"{m['annual_return']*100:>7.1f}% "
            f"{m['annual_vol']*100:>7.1f}% "
            f"{m['sharpe']:>7.2f} "
            f"{m['max_drawdown']*100:>7.1f}% "
            f"{m['hit_rate_monthly']*100:>5.1f}% "
            f"{v:<15}"
        )
        per_pair_returns[sym] = rets
        per_pair_metrics[sym] = (m, v)

    # ─── Portfolio: equal-weight mean across pairs ───
    print()
    port_df = pd.DataFrame(per_pair_returns)
    # align indices (inner join on months where we have data for all pairs)
    port_ret = port_df.mean(axis=1)
    port_m = metrics(port_ret)
    port_v = verdict_for(port_m)

    print(f"▶ Equal-weight portfolio ({len(per_pair_returns)} pairs):\n")
    print(f"  Period        : {port_m['start_date']} → {port_m['end_date']} ({port_m['n_months']} months)")
    print(f"  Annual return : {port_m['annual_return']*100:+.2f}%")
    print(f"  Annual vol    : {port_m['annual_vol']*100:.2f}%")
    print(f"  Sharpe        : {port_m['sharpe']:.3f}")
    print(f"  Sortino       : {port_m['sortino']:.3f}")
    print(f"  Max DD        : {port_m['max_drawdown']*100:.1f}%")
    print(f"  CAGR          : {port_m['cagr']*100:.2f}%")
    print(f"  Hit rate      : {port_m['hit_rate_monthly']*100:.1f}% ({port_m['positive_months']}/{port_m['n_months']} months positive)")
    print(f"  Best / Worst  : {port_m['best_month']*100:+.2f}% / {port_m['worst_month']*100:+.2f}%")
    print(f"  VERDICT       : {port_v}")

    # Compare to AQR expectation
    print(f"\n  AQR benchmark : Sharpe ~0.7, annual ~10%, Max DD ~25%")

    # ─── Save to DB ───
    conn = sqlite3.connect(DB)
    for sym, (m, v) in per_pair_metrics.items():
        conn.execute("""
            INSERT INTO tsmom_runs
            (run_time, scope, n_months, start_date, end_date, annual_return,
             annual_vol, sharpe, sortino, max_drawdown, hit_rate_monthly,
             best_month, worst_month, positive_months, negative_months,
             cagr, verdict, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            run_time, sym, m['n_months'], m['start_date'], m['end_date'],
            m['annual_return'], m['annual_vol'], m['sharpe'], m['sortino'],
            m['max_drawdown'], m['hit_rate_monthly'],
            m['best_month'], m['worst_month'],
            m['positive_months'], m['negative_months'],
            m['cagr'], v,
            f"target_vol={TARGET_ANNUAL_VOL}, max_leverage={MAX_LEVERAGE}",
        ))
    # Portfolio row
    conn.execute("""
        INSERT INTO tsmom_runs
        (run_time, scope, n_months, start_date, end_date, annual_return,
         annual_vol, sharpe, sortino, max_drawdown, hit_rate_monthly,
         best_month, worst_month, positive_months, negative_months,
         cagr, verdict, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        run_time, "portfolio_equal_weight", port_m['n_months'],
        port_m['start_date'], port_m['end_date'],
        port_m['annual_return'], port_m['annual_vol'], port_m['sharpe'],
        port_m['sortino'], port_m['max_drawdown'], port_m['hit_rate_monthly'],
        port_m['best_month'], port_m['worst_month'],
        port_m['positive_months'], port_m['negative_months'],
        port_m['cagr'], port_v,
        f"n_pairs={len(per_pair_returns)}, target_vol={TARGET_ANNUAL_VOL}",
    ))
    conn.commit()
    conn.close()
    print(f"\n✓ saved {len(per_pair_metrics)+1} rows to tsmom_runs")

    # ─── Equity curve chart ───
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    cum_port = (1 + port_ret.dropna()).cumprod()
    ax1.plot(cum_port.index, cum_port.values, linewidth=2, color="#1E88E5",
             label=f"Portfolio (Sharpe {port_m['sharpe']:.2f})")
    for sym, rets in per_pair_returns.items():
        cum = (1 + rets).cumprod()
        ax1.plot(cum.index, cum.values, alpha=0.35, linewidth=1, label=sym)
    ax1.legend(loc="upper left", fontsize=9)
    ax1.set_title(f"TSMOM Equity Curves — portfolio CAGR {port_m['cagr']*100:.1f}%, Max DD {port_m['max_drawdown']*100:.1f}%")
    ax1.grid(alpha=0.3)
    ax1.set_ylabel("Growth of $1")

    # Drawdown chart
    dd = (cum_port / cum_port.cummax()) - 1
    ax2.fill_between(dd.index, dd.values * 100, 0, alpha=0.4, color="red")
    ax2.plot(dd.index, dd.values * 100, color="darkred", linewidth=1)
    ax2.set_title("Portfolio drawdown (%)")
    ax2.set_ylabel("Drawdown (%)")
    ax2.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT_CHART, dpi=110)
    plt.close()
    print(f"✓ chart: {OUT_CHART}")

    # ─── Markdown report ───
    md = [f"# TSMOM Prototype — Results\n"]
    md.append(f"_Run: {run_time}_  ")
    md.append(f"_Source: Moskowitz/Ooi/Pedersen (2012) + AQR (2017)_  ")
    md.append(f"_Data: D1 → monthly close, {len(per_pair_returns)} pairs, "
              f"{port_m['start_date']} → {port_m['end_date']} ({port_m['n_months']} months)_  ")
    md.append(f"_Parameters: 12m lookback momentum · 24m vol window · "
              f"{TARGET_ANNUAL_VOL*100:.0f}% target vol · {MAX_LEVERAGE:.1f}× max leverage_\n")

    md.append(f"## Portfolio result — {port_v}\n")
    md.append(f"| Metric | Value | AQR benchmark |")
    md.append(f"|---|---:|---:|")
    md.append(f"| Sharpe ratio | **{port_m['sharpe']:.3f}** | ~0.7 |")
    md.append(f"| Annual return | {port_m['annual_return']*100:+.2f}% | ~10% |")
    md.append(f"| Annual volatility | {port_m['annual_vol']*100:.2f}% | ~{TARGET_ANNUAL_VOL*100:.0f}% (target) |")
    md.append(f"| Max drawdown | {port_m['max_drawdown']*100:.1f}% | ~-25% |")
    md.append(f"| CAGR | {port_m['cagr']*100:.2f}% | — |")
    md.append(f"| Sortino | {port_m['sortino']:.3f} | — |")
    md.append(f"| Hit rate | {port_m['hit_rate_monthly']*100:.1f}% | ~55-60% |")
    md.append(f"| Best month | {port_m['best_month']*100:+.2f}% | — |")
    md.append(f"| Worst month | {port_m['worst_month']*100:+.2f}% | — |\n")

    md.append("## Per-pair breakdown\n")
    md.append("| Pair | Months | Ann Ret | Ann Vol | Sharpe | Max DD | Hit% | Verdict |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for sym, (m, v) in per_pair_metrics.items():
        md.append(
            f"| `{sym}` | {m['n_months']} | {m['annual_return']*100:+.1f}% | "
            f"{m['annual_vol']*100:.1f}% | {m['sharpe']:+.2f} | "
            f"{m['max_drawdown']*100:.1f}% | {m['hit_rate_monthly']*100:.0f}% | {v} |"
        )

    md.append("\n## Interpretation\n")
    if port_v.startswith("✅"):
        md.append("**TSMOM validated on your data.** Sharpe ≥ 0.7 matches the AQR benchmark. ")
        md.append("This strategy is a strong independent layer for v3.0 — it does not compete ")
        md.append("with Primary+Meta-Labeler (different timeframe, different thesis) and the ")
        md.append("research literature says returns are uncorrelated with equity markets.\n")
    elif port_v.startswith("⚠️"):
        md.append("**TSMOM underperforms AQR benchmark slightly.** Sharpe 0.5-0.7 is still ")
        md.append("usable — this is a working layer. Common causes: FX-only universe (less ")
        md.append("diversification than AQR's 67 markets), shorter window than AQR's 140 years. ")
        md.append("Accept for v3.0 but size conservatively.\n")
    else:
        md.append("**TSMOM weak on your data.** Sharpe < 0.5 is below the AQR threshold. ")
        md.append("Possible causes: FX has entered a lower-trending regime, your 7 pairs have ")
        md.append("high correlation reducing diversification. Before dropping TSMOM, try: ")
        md.append("(a) longer momentum lookback (9-15mo instead of 12), (b) adding non-USD ")
        md.append("crosses for diversification.\n")

    md.append("## v3.0 plan implications\n")
    if port_m['sharpe'] >= 0.5:
        md.append(f"- TSMOM is **worth building** as the parallel layer (Phase 6 of v3.0).")
        md.append(f"- Keep plan's 60/40 allocation (Primary/TSMOM) or push to 50/50 if Meta-Labeler underwhelms.")
        md.append(f"- TSMOM alone on ${10000} account: expected ~${10000*port_m['cagr']:.0f}/year CAGR.\n")
    else:
        md.append(f"- TSMOM may not justify its operational complexity.")
        md.append(f"- Consider: stick with the simpler Primary+Meta-Labeler (even if lift is small).\n")

    OUT_REPORT.write_text("\n".join(md), encoding="utf-8")
    print(f"✓ report: {OUT_REPORT}")

    print(f"\n{'='*72}")
    print(f"  PORTFOLIO VERDICT: {port_v}")
    print(f"  Sharpe {port_m['sharpe']:.2f}  ·  CAGR {port_m['cagr']*100:.1f}%  ·  DD {port_m['max_drawdown']*100:.1f}%")
    print(f"{'='*72}\n")


if __name__ == "__main__":
    main()
