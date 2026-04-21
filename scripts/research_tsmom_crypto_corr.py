"""Phase 10 step 5: correlation + diversification analysis of LO/12w crypto portfolio.

Compares crypto LO/12w weekly returns against:
  - Individual cryptos (BTC, ETH, BNB, SOL)
  - S&P 500 (SPY, downloaded via yfinance)
  - Buy-and-hold BTC (subset of individual cryptos)
  - FX TSMOM portfolio (weekly LO/12w/24w/10%, 7 FX pairs) — matches crypto methodology

Windows analyzed:
  - Full: intersection of all series (starts when all are available)
  - OOS:  2025-01-01 onwards

Outputs:
  data/research/tsmom_crypto_corr_matrix_full.csv
  data/research/tsmom_crypto_corr_matrix_oos.csv
  data/research/tsmom_crypto_corr_diversification.csv
  docs/research/tsmom_crypto_corr_report.md
  docs/research/tsmom_crypto_corr_heatmap.png
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

from research_tsmom_crypto import (
    load_weekly_close,
    run_backtest,
    TARGET_VOL_ANN,
    VOL_WINDOW_W,
    WEEKS_PER_YEAR,
    REBAL_RULE,
    MAX_WEIGHT,
)

OUT_DATA = Path("data/research")
OUT_DOCS = Path("docs/research")
OUT_DATA.mkdir(parents=True, exist_ok=True)
OUT_DOCS.mkdir(parents=True, exist_ok=True)

FX_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "USDCHF", "AUDUSD", "USDCAD"]
OOS_START = pd.Timestamp("2025-01-01")


def load_fx_weekly_close() -> pd.DataFrame:
    frames = []
    for sym in FX_PAIRS:
        p = Path(f"data/raw/{sym}/D1.parquet")
        df = pd.read_parquet(p)[["time", "close"]].set_index("time").rename(columns={"close": sym})
        frames.append(df)
    daily = pd.concat(frames, axis=1).sort_index()
    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    daily = daily[daily.index < today]
    weekly = daily.resample(REBAL_RULE).last()
    return weekly


def load_spy_weekly() -> pd.Series:
    spy = yf.download("SPY", start="2017-08-01", end=(datetime.now() + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                       auto_adjust=True, progress=False)
    # yfinance may return MultiIndex columns if multi-ticker; we passed single
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    close = spy["Close"].copy()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    # Resample to W-FRI close
    return close.resample(REBAL_RULE).last().rename("SPY")


def div_ratio(portfolio_ret: pd.Series, asset_rets: pd.DataFrame, weights_frame: pd.DataFrame) -> dict:
    """Diversification ratio = weighted avg asset vol / portfolio vol.
    Uses absolute weights and time-average |weight| for static approximation."""
    common = portfolio_ret.index.intersection(asset_rets.index)
    p = portfolio_ret.loc[common].dropna()
    a = asset_rets.loc[common]
    # Per-asset annualized vol over the shared window
    asset_vols = a.std(ddof=0) * np.sqrt(WEEKS_PER_YEAR)
    # Time-averaged absolute weights (only when weights available; assume 0 elsewhere)
    w_common = weights_frame.reindex(common).fillna(0.0)
    avg_abs_w = w_common.abs().mean()
    # Normalize average weights so they reflect mean gross exposure
    weighted_asset_vol = float((avg_abs_w * asset_vols).sum())
    port_vol = float(p.std(ddof=0) * np.sqrt(WEEKS_PER_YEAR))
    return {
        "portfolio_vol_ann": round(port_vol, 4),
        "weighted_asset_vol_ann": round(weighted_asset_vol, 4),
        "diversification_ratio": round(weighted_asset_vol / port_vol, 3) if port_vol > 0 else None,
        "mean_gross_exposure": round(float(avg_abs_w.sum()), 3),
    }


def main() -> None:
    # ---------------- data sources ----------------
    print("[load] crypto weekly ...")
    crypto_weekly = load_weekly_close()

    print("[load] FX weekly ...")
    fx_weekly = load_fx_weekly_close()

    print("[load] SPY weekly (yfinance) ...")
    spy_weekly = load_spy_weekly()

    # ---------------- strategy returns ----------------
    print("[build] crypto LO/12w/10bps ...")
    crypto_res = run_backtest(crypto_weekly, direction="LO", lookback_w=12, cost_per_side=0.001)

    print("[build] FX TSMOM LO/12w/10bps (apples-to-apples with crypto) ...")
    fx_res = run_backtest(fx_weekly, direction="LO", lookback_w=12, cost_per_side=0.001)

    # Individual crypto weekly returns (buy-and-hold)
    crypto_asset_ret = crypto_weekly.pct_change()

    # SPY weekly returns
    spy_ret = spy_weekly.pct_change()

    # ---------------- build correlation frame ----------------
    returns_frame = pd.DataFrame({
        "strategy_LO_12w": crypto_res["returns_net"],
        "BH_BTC":          crypto_asset_ret["BTC/USDT"],
        "BH_ETH":          crypto_asset_ret["ETH/USDT"],
        "BH_BNB":          crypto_asset_ret["BNB/USDT"],
        "BH_SOL":          crypto_asset_ret["SOL/USDT"],
        "SPY":             spy_ret,
        "FX_TSMOM_weekly": fx_res["returns_net"],
    })

    # ---------------- full window correlation ----------------
    full = returns_frame.dropna()
    print(f"[corr] full window: {len(full)} weeks ({full.index.min().date()} -> {full.index.max().date()})")
    corr_full = full.corr()
    corr_full.to_csv(OUT_DATA / "tsmom_crypto_corr_matrix_full.csv")

    # ---------------- OOS window correlation ----------------
    oos = returns_frame.loc[OOS_START:].dropna()
    print(f"[corr] OOS window : {len(oos)} weeks ({oos.index.min().date()} -> {oos.index.max().date()})")
    corr_oos = oos.corr()
    corr_oos.to_csv(OUT_DATA / "tsmom_crypto_corr_matrix_oos.csv")

    # ---------------- diversification ratio ----------------
    w = crypto_res["weights"]  # DataFrame, cols = crypto symbols
    # For full window
    div_full = div_ratio(crypto_res["returns_net"], crypto_asset_ret, w)
    # For OOS window
    oos_ret = crypto_res["returns_net"].loc[OOS_START:]
    oos_asset = crypto_asset_ret.loc[OOS_START:]
    oos_w = w.loc[OOS_START:]
    div_oos = div_ratio(oos_ret, oos_asset, oos_w)

    div_df = pd.DataFrame([
        {"window": "full", **div_full},
        {"window": "oos",  **div_oos},
    ])
    div_df.to_csv(OUT_DATA / "tsmom_crypto_corr_diversification.csv", index=False)

    # ---------------- heatmap plot ----------------
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for ax, corr, title in [(axes[0], corr_full, f"Full ({full.index.min().date()} - {full.index.max().date()}, {len(full)}w)"),
                             (axes[1], corr_oos, f"OOS ({oos.index.min().date()} - {oos.index.max().date()}, {len(oos)}w)")]:
        im = ax.imshow(corr.values, vmin=-1, vmax=1, cmap="RdBu_r")
        ax.set_xticks(range(len(corr.columns)))
        ax.set_yticks(range(len(corr.index)))
        ax.set_xticklabels(corr.columns, rotation=45, ha="right", fontsize=9)
        ax.set_yticklabels(corr.index, fontsize=9)
        for i in range(len(corr.index)):
            for j in range(len(corr.columns)):
                val = corr.values[i, j]
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        color="white" if abs(val) > 0.5 else "black", fontsize=8)
        ax.set_title(title, fontsize=11)
        plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.suptitle("Weekly return correlations — crypto LO/12w vs alternatives", fontsize=13)
    fig.tight_layout()
    png = OUT_DOCS / "tsmom_crypto_corr_heatmap.png"
    fig.savefig(png, dpi=110)
    plt.close(fig)

    # ---------------- report ----------------
    write_report(corr_full, corr_oos, div_full, div_oos, full, oos, png)

    # ---------------- stdout summary ----------------
    print()
    print("=" * 90)
    print("CORRELATION (weekly, Pearson) — strategy_LO_12w row only")
    print("=" * 90)
    row = "strategy_LO_12w"
    cols = [c for c in corr_full.columns if c != row]
    print(f"\n{'pair':<20} {'full':>10} {'oos':>10}")
    for c in cols:
        print(f"{c:<20} {corr_full.loc[row, c]:>10.3f} {corr_oos.loc[row, c]:>10.3f}")
    print()
    print(f"Diversification ratio (full): {div_full['diversification_ratio']}  (mean gross exposure {div_full['mean_gross_exposure']})")
    print(f"Diversification ratio (OOS) : {div_oos['diversification_ratio']}  (mean gross exposure {div_oos['mean_gross_exposure']})")


def write_report(corr_full: pd.DataFrame, corr_oos: pd.DataFrame,
                 div_full: dict, div_oos: dict,
                 full_ret: pd.DataFrame, oos_ret: pd.DataFrame, png: Path) -> None:
    row = "strategy_LO_12w"
    L = [
        "# TSMOM Crypto — Correlation & Diversification (Phase 10 step 5)",
        "",
        f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
        "",
        "## Purpose",
        "",
        "Determine whether **crypto LO/12w** (the only step-4 variant that cleared the absolute OOS Sharpe gate of 0.4) adds real diversification to an existing book. Binary decision driver for the Phase-10 go/no-go between Option 1 (reject) and Option 4 (rescue with regime filter).",
        "",
        "## Setup",
        "",
        "| Item | Value |",
        "|---|---|",
        "| Strategy    | Crypto LO/12w/10bps (from Phase 10 step 3) |",
        "| Frequency   | Weekly returns (W-FRI close) |",
        "| Full window | Intersection of all series — starts when all have data |",
        "| OOS window  | 2025-01-01 onwards (same as step 4) |",
        "| SPY source  | yfinance, auto-adjusted, resampled W-FRI |",
        "| FX TSMOM    | Rebuilt at weekly LO/12w/24w/10%/10bps (matches crypto methodology) — **NOT** the published monthly LS baseline (Sharpe 0.126). See caveats. |",
        "",
        "## Correlation — full window",
        "",
        f"Window: {full_ret.index.min().date()} to {full_ret.index.max().date()} ({len(full_ret)} weeks)",
        "",
        _corr_md(corr_full),
        "",
        "## Correlation — OOS window",
        "",
        f"Window: {oos_ret.index.min().date()} to {oos_ret.index.max().date()} ({len(oos_ret)} weeks)",
        "",
        _corr_md(corr_oos),
        "",
        "## Headline — crypto strategy row only",
        "",
        "| Counterparty | Full-window ρ | OOS ρ | Verdict (low=diversifying, high=proxy) |",
        "|---|---:|---:|---|",
    ]
    for c in corr_full.columns:
        if c == row:
            continue
        r_full = corr_full.loc[row, c]
        r_oos = corr_oos.loc[row, c] if c in corr_oos.columns else float("nan")
        label = _rho_verdict(r_full, r_oos)
        L.append(f"| `{c}` | {r_full:+.3f} | {r_oos:+.3f} | {label} |")
    L.append("")

    # Diversification
    L += [
        "## Diversification ratio",
        "",
        "DR = (time-averaged weighted avg of individual asset vols) / (portfolio vol). Higher = more diversification benefit realized.",
        "",
        "| Window | Portfolio vol (ann) | Weighted asset vol | DR | Mean gross exposure |",
        "|---|---:|---:|---:|---:|",
        f"| Full | {div_full['portfolio_vol_ann']} | {div_full['weighted_asset_vol_ann']} | **{div_full['diversification_ratio']}** | {div_full['mean_gross_exposure']} |",
        f"| OOS  | {div_oos['portfolio_vol_ann']} | {div_oos['weighted_asset_vol_ann']} | **{div_oos['diversification_ratio']}** | {div_oos['mean_gross_exposure']} |",
        "",
        "## Decision grid (from your Phase-10 rules)",
        "",
        "| Condition | Implication | Status (OOS) |",
        "|---|---|---|",
    ]
    rho_fx_oos = corr_oos.loc[row, "FX_TSMOM_weekly"] if "FX_TSMOM_weekly" in corr_oos.columns else float("nan")
    rho_spy_oos = corr_oos.loc[row, "SPY"] if "SPY" in corr_oos.columns else float("nan")
    rho_btc_oos = corr_oos.loc[row, "BH_BTC"] if "BH_BTC" in corr_oos.columns else float("nan")
    rho_eth_oos = corr_oos.loc[row, "BH_ETH"] if "BH_ETH" in corr_oos.columns else float("nan")
    diversify_case = (abs(rho_fx_oos) < 0.3) and (abs(rho_spy_oos) < 0.3)
    proxy_case = rho_btc_oos > 0.7
    L.append(f"| ρ(FX) < 0.3 AND ρ(SPY) < 0.3 | → Option 4 (rescue with regime filter) | {'MET' if diversify_case else 'NOT MET'}  (FX={rho_fx_oos:+.2f}, SPY={rho_spy_oos:+.2f}) |")
    L.append(f"| ρ(BTC) > 0.7 | → Option 1 (reject, pivot) | {'MET' if proxy_case else 'NOT MET'}  (BTC={rho_btc_oos:+.2f}) |")
    mixed = not diversify_case and not proxy_case
    L.append(f"| Mixed signals | → discuss | {'APPLIES' if mixed else 'n/a'} |")
    L.append("")
    L += [
        "## Heatmap",
        "",
        f"![correlation heatmap]({png.name})",
        "",
        "## Caveats",
        "",
        "- **FX_TSMOM_weekly is NOT the published monthly baseline.** The audit-report baseline (+0.61% ann, Sharpe 0.126) used **monthly rebalance + long-short + 12-month lookback** on 7 FX pairs. For correlation at weekly frequency, we rebuilt FX TSMOM using the **same methodology as the crypto strategy** (weekly rebalance, 12w lookback, LO, 10bps). This is an apples-to-apples comparison for correlation purposes; the weekly-FX strategy's Sharpe will differ from the monthly baseline.",
        "- **SPY stale-fill effect:** SPY doesn't trade weekends, but crypto does. Resampling both to W-FRI close minimizes this, but occasional FX/crypto Friday closes before SPY close can create 1-day misalignment. Correlation interpretation is qualitative.",
        "- **OOS sample size is 69 weeks.** Pearson ρ from ~70 observations has a rough 95% CI of ±0.23 around the point estimate (via Fisher z). Treat OOS correlation as directional, not precise.",
        "- **Correlations are mean-centered by design.** A strategy that's flat (like LO/12m OOS with Sharpe 0.03) will correlate low with everything almost by construction — not because it's diversifying, but because it's barely moving.",
        "",
        "## Files",
        "",
        "- `data/research/tsmom_crypto_corr_matrix_full.csv`",
        "- `data/research/tsmom_crypto_corr_matrix_oos.csv`",
        "- `data/research/tsmom_crypto_corr_diversification.csv`",
        f"- `docs/research/{png.name}`",
        "- `scripts/research_tsmom_crypto_corr.py` (re-runnable)",
        "",
    ]
    (OUT_DOCS / "tsmom_crypto_corr_report.md").write_text("\n".join(L), encoding="utf-8")


def _rho_verdict(r_full: float, r_oos: float) -> str:
    r = r_oos if np.isfinite(r_oos) else r_full
    if abs(r) < 0.20: return "**near-zero** — diversifying"
    if abs(r) < 0.40: return "low — mild diversification"
    if abs(r) < 0.60: return "moderate"
    if abs(r) < 0.80: return "**high** — correlated"
    return "**very high** — near-proxy"


def _corr_md(corr: pd.DataFrame) -> str:
    cols = list(corr.columns)
    header = "| | " + " | ".join(f"`{c}`" for c in cols) + " |"
    sep = "|---|" + "|".join(["---:"] * len(cols)) + "|"
    rows = []
    for r in corr.index:
        vals = " | ".join(f"{corr.loc[r, c]:+.3f}" for c in cols)
        rows.append(f"| `{r}` | {vals} |")
    return "\n".join([header, sep] + rows)


if __name__ == "__main__":
    main()
