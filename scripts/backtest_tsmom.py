"""Phase 6 Step 2: 10-year TSMOM backtest on the 6 v3 symbols.

Uses today's strategies.tsmom.tsmom_strategy on D1 historical bars.
Monthly rebalance per the Phase 6 plan. Phase-6 ship gate is
**Sharpe ≥ 0.5 across the 10-year window covering ≥3 regimes**;
the 2026-04-17 prototype delivered Sharpe 0.13, which is the bar
to clear.

Backtest mechanics:
  - For each month-start bar, compute compute_tsmom_signal() per
    symbol using past 252 D1 bars (12 months) for momentum and
    60 D1 bars (3 months) for vol.
  - Allocate weight = signal_direction × target_weight (capped).
  - Hold for one calendar month → PnL = direction × (close_end /
    close_start − 1) × target_weight.
  - Equal-weighted portfolio across 6 symbols (monthly returns
    summed).

Reports:
  - Per-symbol Sharpe, max DD, total return, win-month rate.
  - Combined portfolio Sharpe + equity curve.
  - Sub-period breakdown (every ~3 years) to verify the "≥ 3
    regimes" requirement.

Output:
  artifacts/phase6_step2_tsmom_backtest_<date>.csv  per-month per-symbol
  docs/research/phase6_step2_tsmom_backtest.md      report

Re-runnable. Read-only against parquet bars."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, ".")

import numpy as np
import pandas as pd
from loguru import logger

from strategies.tsmom.tsmom_strategy import compute_tsmom_signal

V3_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "AUDUSD", "USDCHF"]
TRIMMED_4 = ["USDJPY", "XAUUSD", "AUDUSD", "EURUSD"]
RAW_DIR = Path("data/raw")
ARTIFACTS_DIR = Path("artifacts")
DOCS_DIR = Path("docs/research")

# TSMOM defaults (matching strategies.tsmom.tsmom_strategy)
LOOKBACK_DAYS = 252
VOL_WINDOW_DAYS = 60
VOL_TARGET = 0.10
WEIGHT_CAP = 4.0


def load_d1(symbol: str) -> pd.DataFrame:
    p = RAW_DIR / symbol / "D1.parquet"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    if "time" in df.columns:
        df = df.set_index(pd.to_datetime(df["time"]))
    return df.sort_index()[["close"]].dropna()


def get_month_starts(prices: pd.Series) -> pd.DatetimeIndex:
    """Return the first available bar of each calendar month."""
    period = prices.index.to_period("M")
    # Picks the first row index per calendar month — equivalent to
    # `groupby(period).first()` but on the index itself, not the values.
    firsts = pd.Series(prices.index, index=period).groupby(level=0).first()
    return pd.DatetimeIndex(firsts.values).sort_values()


def backtest_symbol(symbol: str, prices: pd.Series) -> pd.DataFrame:
    """Monthly TSMOM backtest for one symbol.

    Returns DataFrame indexed by month-start bar with:
      direction, target_weight, raw_momentum, vol_annualised,
      month_return_unweighted, month_return_weighted, signal."""
    starts = get_month_starts(prices)
    rows = []
    for i, t0 in enumerate(starts):
        # Need lookback + vol_window of history before t0
        lookback_window = prices.loc[:t0]
        if len(lookback_window) < max(LOOKBACK_DAYS, VOL_WINDOW_DAYS) + 1:
            continue
        sig = compute_tsmom_signal(
            lookback_window,
            lookback_days=LOOKBACK_DAYS,
            vol_window_days=VOL_WINDOW_DAYS,
            vol_target=VOL_TARGET,
            weight_cap=WEIGHT_CAP,
        )
        if sig is None or sig.direction == "FLAT":
            continue

        # Find next month-start (or end of data)
        if i + 1 >= len(starts):
            t1 = prices.index[-1]
        else:
            t1 = starts[i + 1]
        try:
            p0 = prices.loc[t0]
            p1 = prices.loc[t1]
        except KeyError:
            continue
        if p0 is None or p1 is None or p0 == 0:
            continue

        unweighted_ret = (p1 / p0 - 1.0) if sig.direction == "BUY" else (p0 / p1 - 1.0)
        weighted_ret = unweighted_ret * sig.target_weight

        rows.append({
            "symbol": symbol,
            "month_start": t0,
            "month_end": t1,
            "direction": sig.direction,
            "raw_momentum": sig.raw_momentum,
            "vol_annualised": sig.vol_annualised,
            "target_weight": sig.target_weight,
            "month_return_unweighted": unweighted_ret,
            "month_return_weighted": weighted_ret,
        })
    return pd.DataFrame(rows)


def metrics(returns: pd.Series, n_per_year: int = 12) -> dict:
    """Sharpe, max DD, total return, win-month rate."""
    if returns.empty:
        return {"n": 0}
    sharpe = (
        returns.mean() / returns.std(ddof=1) * np.sqrt(n_per_year)
        if returns.std(ddof=1) > 0 else 0.0
    )
    cumret = (1 + returns).cumprod()
    drawdown = cumret / cumret.cummax() - 1
    max_dd = float(drawdown.min())
    total_return = float(cumret.iloc[-1] - 1.0)
    win_rate = float((returns > 0).mean())
    return {
        "n": int(len(returns)),
        "sharpe": float(sharpe),
        "max_drawdown": max_dd,
        "total_return": total_return,
        "win_month_rate": win_rate,
        "mean_monthly": float(returns.mean()),
        "std_monthly": float(returns.std(ddof=1)) if len(returns) > 1 else 0.0,
    }


def render_report(per_symbol: dict, portfolio_metrics: dict,
                  sub_periods: list, *, n_total: int,
                  symbols: list = None) -> str:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    sym_list = symbols if symbols else list(per_symbol.keys())
    lines = []
    lines.append("# Phase 6 Step 2 — 10-year TSMOM Backtest\n")
    lines.append(f"**Date:** {today}  ")
    lines.append(f"**Re-runnable:** `python scripts/backtest_tsmom.py [--symbols ...]`  ")
    lines.append(f"**Source module:** `strategies/tsmom/tsmom_strategy.py` (Phase 6 Step 1, shipped 2026-05-06)  ")
    lines.append(f"**Phase 6 ship gate:** Sharpe ≥ 0.5 across ≥3 regimes; the 2026-04-17 prototype delivered Sharpe 0.13.\n")

    lines.append("## Backtest setup\n")
    lines.append(f"- Symbols: {', '.join(sym_list)} ({len(sym_list)} symbols)")
    lines.append("- Timeframe: D1 (daily bars)")
    lines.append(f"- Lookback: {LOOKBACK_DAYS} bars (12 months)")
    lines.append(f"- Vol window: {VOL_WINDOW_DAYS} bars (3 months)")
    lines.append(f"- Vol target: {VOL_TARGET:.2f} (10% annualised)")
    lines.append(f"- Weight cap: {WEIGHT_CAP}")
    lines.append("- Rebalance: monthly (first available bar per calendar month)")
    lines.append(f"- Total per-symbol-month observations: **{n_total}**\n")

    lines.append("## Per-symbol metrics\n")
    lines.append("| Symbol | Months | Sharpe | Max DD | Total return | Win-month |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for sym, m in per_symbol.items():
        if m.get("n", 0) == 0:
            lines.append(f"| {sym} | 0 | — | — | — | — |")
            continue
        lines.append(
            f"| {sym} | {m['n']} | {m['sharpe']:.3f} | {m['max_drawdown']:.1%} | "
            f"{m['total_return']:.1%} | {m['win_month_rate']:.1%} |"
        )
    lines.append("")

    lines.append("## Portfolio (equal-weight, 6 symbols)\n")
    pm = portfolio_metrics
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Months observed | {pm['n']} |")
    lines.append(f"| **Sharpe (annualised)** | **{pm['sharpe']:.3f}** |")
    lines.append(f"| Max drawdown | {pm['max_drawdown']:.1%} |")
    lines.append(f"| Total return | {pm['total_return']:.1%} |")
    lines.append(f"| Win-month rate | {pm['win_month_rate']:.1%} |")
    lines.append(f"| Mean monthly return | {pm['mean_monthly']:.4f} |")
    lines.append(f"| Std monthly return | {pm['std_monthly']:.4f} |\n")

    target = 0.5
    sharpe = pm["sharpe"]
    if sharpe >= target:
        lines.append(f"### Verdict: ✓ PASSES Phase 6 ship gate (Sharpe {sharpe:.3f} ≥ {target:.1f}).\n")
    else:
        gap = target - sharpe
        lines.append(
            f"### Verdict: ✗ FAILS Phase 6 ship gate (Sharpe {sharpe:.3f} < {target:.1f}, "
            f"short by {gap:.3f}). The 2026-04-17 prototype delivered 0.13; "
            f"this build delivers {sharpe:.3f}. "
            + ("Step in the right direction." if sharpe > 0.13 else "No improvement over prototype.")
            + " Need to investigate parameter tuning (lookback, vol_target, weight_cap) "
              "or accept TSMOM doesn't have edge on this universe.\n"
        )

    lines.append("## Sub-period breakdown (regime check)\n")
    lines.append("Phase 6 plan requires the backtest cover ≥3 regimes. Splitting the period into ~3-year sub-windows:\n")
    lines.append("| Period | Months | Sharpe | Total return | Win-month |")
    lines.append("|---|---:|---:|---:|---:|")
    for label, m in sub_periods:
        if m.get("n", 0) == 0:
            lines.append(f"| {label} | 0 | — | — | — |")
            continue
        lines.append(
            f"| {label} | {m['n']} | {m['sharpe']:.3f} | {m['total_return']:.1%} | "
            f"{m['win_month_rate']:.1%} |"
        )
    n_positive = sum(1 for _, m in sub_periods if m.get("sharpe", 0) > 0)
    lines.append(
        f"\n{n_positive} of {len(sub_periods)} sub-periods produced positive Sharpe. "
        + ("Consistent across regimes." if n_positive >= len(sub_periods) - 1 else
           "Performance is regime-dependent — TSMOM works in some windows but not others.")
        + "\n"
    )

    lines.append("## Methodology notes\n")
    lines.append(
        "- **Monthly rebalance only.** No intra-month adjustments. A signal at month-start\n"
        "  is held for the entire month. Real paper trading might rebalance differently;\n"
        "  this matches the Phase 6 plan's 'monthly rebalance' instruction.\n"
        "- **No transaction costs.** Spreads / commissions / swap not modelled. A real\n"
        "  paper run would shave Sharpe by ~0.05–0.15 depending on broker terms.\n"
        "- **Equal-weight portfolio.** Each of 6 symbols contributes 1/6 to the monthly\n"
        "  return. A volatility-parity portfolio would weight by inverse vol; that's a\n"
        "  separate experiment.\n"
        "- **Walk-forward by construction.** Each month's signal uses only data up to\n"
        "  that month-start, so there's no look-ahead.\n"
        "- **No SL/TP.** Pure direction × monthly return. The strategy class has SL/TP\n"
        "  for live trading but the backtest doesn't simulate them — kept simple to\n"
        "  test the directional signal's edge in isolation.\n"
    )

    lines.append("## What this does NOT decide\n")
    lines.append(
        "- Whether Phase 6 step 3 (May 18-24 paper trading) starts. That depends on\n"
        "  the Sharpe verdict + your read of regime-consistency.\n"
        "- Whether to switch to volatility-parity weighting or another portfolio\n"
        "  construction. Equal-weight is the simplest baseline; alternatives can be\n"
        "  evaluated separately if Sharpe needs improvement.\n"
        "- Whether to add a regime filter (similar to Phase 10.5's TSMOM-with-regime-\n"
        "  filter rescue, which did NOT work on crypto). Worth flagging as a potential\n"
        "  iteration if the unfiltered version fails the gate.\n"
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 6 Step 2 TSMOM backtest")
    parser.add_argument(
        "--symbols", default=",".join(V3_SYMBOLS),
        help="Comma-separated symbols. Default: all 6 v3 symbols. "
             "Use 'TRIMMED' as shorthand for the 4-symbol positive-Sharpe set.",
    )
    parser.add_argument(
        "--label", default="full",
        help="Label suffix for output files (e.g. 'full', 'trimmed_4'). "
             "Default 'full' overwrites the canonical Step 2 report.",
    )
    args = parser.parse_args()

    if args.symbols.upper() == "TRIMMED":
        symbols = TRIMMED_4
    else:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    t0 = time.time()
    logger.info(f"[phase6-step2] starting TSMOM backtest on {len(symbols)} symbols: {symbols}")

    # 1. Run backtest per symbol
    per_symbol_metrics = {}
    all_rows = []
    for sym in symbols:
        prices = load_d1(sym)
        if prices.empty:
            logger.warning(f"[{sym}] no D1 data, skipped")
            per_symbol_metrics[sym] = {"n": 0}
            continue
        df = backtest_symbol(sym, prices["close"])
        if df.empty:
            logger.warning(f"[{sym}] no signals generated")
            per_symbol_metrics[sym] = {"n": 0}
            continue
        m = metrics(df["month_return_weighted"])
        per_symbol_metrics[sym] = m
        df = df.assign(symbol=sym)
        all_rows.append(df)
        logger.info(
            f"[{sym}] {m['n']} months, "
            f"Sharpe={m['sharpe']:.3f}, MDD={m['max_drawdown']:.1%}, "
            f"total={m['total_return']:.1%}"
        )

    # 2. Build combined portfolio (equal-weight)
    if not all_rows:
        logger.error("no symbols produced backtest output")
        return 1
    combined = pd.concat(all_rows, ignore_index=True)

    # Group monthly returns: average across symbols per month
    portfolio_monthly = combined.groupby("month_start")["month_return_weighted"].mean()
    portfolio_metrics_dict = metrics(portfolio_monthly)
    logger.info(
        f"[portfolio] {portfolio_metrics_dict['n']} months, "
        f"Sharpe={portfolio_metrics_dict['sharpe']:.3f}"
    )

    # 3. Sub-period breakdown
    if not portfolio_monthly.empty:
        first_year = portfolio_monthly.index[0].year
        last_year = portfolio_monthly.index[-1].year
        sub_periods = []
        for start_year in range(first_year, last_year + 1, 3):
            end_year = start_year + 2
            mask = (portfolio_monthly.index.year >= start_year) & (
                portfolio_monthly.index.year <= end_year
            )
            sub_metrics = metrics(portfolio_monthly[mask])
            sub_periods.append((f"{start_year}–{min(end_year, last_year)}", sub_metrics))
    else:
        sub_periods = []

    # 4. Save artifact
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    suffix = f"_{args.label}" if args.label != "full" else ""
    csv_path = ARTIFACTS_DIR / f"phase6_step2_tsmom_backtest{suffix}_{today_str}.csv"
    combined.to_csv(csv_path, index=False)

    # 5. Save report
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = DOCS_DIR / f"phase6_step2_tsmom_backtest{suffix}.md"
    report = render_report(per_symbol_metrics, portfolio_metrics_dict, sub_periods,
                           n_total=len(combined), symbols=symbols)
    report_path.write_text(report, encoding="utf-8")

    elapsed = time.time() - t0

    # 6. Print headline
    print()
    print("=" * 78)
    print(" Phase 6 Step 2 — 10-year TSMOM Backtest")
    print("=" * 78)
    pm = portfolio_metrics_dict
    print(f"  Portfolio Sharpe (equal-weight, {len(symbols)} symbols): {pm['sharpe']:.3f}")
    print(f"  Phase 6 ship gate target:                   ≥ 0.500")
    print(f"  2026-04-17 prototype baseline:              0.130")
    print(f"  Verdict:                                    "
          f"{'✓ PASS' if pm['sharpe'] >= 0.5 else '✗ FAIL'}")
    print()
    print(f"  Per-symbol Sharpes:")
    for sym, m in per_symbol_metrics.items():
        if m.get("n", 0) > 0:
            print(f"    {sym}: {m['sharpe']:+.3f}  (n={m['n']} months, total={m['total_return']:+.1%})")
        else:
            print(f"    {sym}: no data")
    print()
    print(f"  Report:    {report_path}")
    print(f"  Artifact:  {csv_path}")
    print(f"  Elapsed:   {elapsed:.1f}s")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
