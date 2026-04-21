"""Phase 10 step 4: out-of-sample validation of TSMOM crypto.

Two variants evaluated (both long-only, 0.1% cost):
  Primary:   LO / 12m lookback
  Secondary: LO / 12w lookback

Splits:
  Training window: 2017-08-17 -> 2024-12-31 (~7.4 years)
  Held-out OOS:    2025-01-01 -> latest completed week (~16 months)
  Purged K-fold:   K=5 on the training window, 4-week embargo between folds

The strategy is rule-based (no parameters fit on the data), so K-fold is used
as a *stability diagnostic* (are fold metrics consistent?), not as a CV-for-
model-selection procedure. The held-out window is the true OOS test.

Outputs:
  data/research/tsmom_crypto_oos_metrics.csv
  docs/research/tsmom_crypto_oos_report.md
  docs/research/tsmom_crypto_oos_equity.png
  improvements.db::tsmom_runs  (new rows, scope='crypto_<variant>_{train|oos}')
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

from research_tsmom_crypto import (
    compute_metrics,
    load_weekly_close,
    run_backtest,
    WEEKS_PER_YEAR,
)

VARIANTS = [
    {"name": "LO_12m_c10bps", "direction": "LO", "lookback_w": 52, "cost": 0.001, "role": "primary"},
    {"name": "LO_12w_c10bps", "direction": "LO", "lookback_w": 12, "cost": 0.001, "role": "secondary"},
]

TRAIN_START = pd.Timestamp("2017-08-17")
TRAIN_END = pd.Timestamp("2024-12-31")
OOS_START = pd.Timestamp("2025-01-01")
K_FOLDS = 5
EMBARGO_WEEKS = 4  # short embargo; signal warmup is baked into first_valid already

OUT_DATA = Path("data/research")
OUT_DOCS = Path("docs/research")
OUT_DATA.mkdir(parents=True, exist_ok=True)
OUT_DOCS.mkdir(parents=True, exist_ok=True)


def slice_metrics(returns: pd.Series, turnover: pd.Series, start: pd.Timestamp, end: pd.Timestamp, label: str) -> dict:
    r = returns.loc[(returns.index >= start) & (returns.index <= end)].dropna()
    if len(r) == 0:
        return {"label": label, "note": "empty slice", "n_weeks": 0}
    eq = (1.0 + r).cumprod()
    t = turnover.loc[r.index] if len(turnover) else pd.Series([0.0])
    return compute_metrics(eq, r, t, label)


def purged_kfold_indices(index: pd.DatetimeIndex, k: int, embargo: int) -> list[dict]:
    """Split a sorted DatetimeIndex into k chronological folds with embargo weeks removed at fold boundaries.
    Returns list of {fold, test_start, test_end, test_idx, train_idx}."""
    n = len(index)
    bounds = np.linspace(0, n, k + 1, dtype=int)
    folds = []
    for i in range(k):
        t0, t1 = bounds[i], bounds[i + 1]
        test_idx = index[t0:t1]
        # Embargo: drop `embargo` weeks before and after the test block from the train set
        left_cut = index[max(0, t0 - embargo):t0]
        right_cut = index[t1:min(n, t1 + embargo)]
        cut = left_cut.union(right_cut)
        train_idx = index.difference(test_idx).difference(cut)
        folds.append({
            "fold": i + 1,
            "test_start": test_idx[0],
            "test_end": test_idx[-1],
            "test_idx": test_idx,
            "train_idx": train_idx,
        })
    return folds


def go_no_go(oos_m: dict, train_m: dict, bh_oos_m: dict) -> dict:
    checks = {}
    sh_oos = oos_m.get("sharpe")
    sh_train = train_m.get("sharpe")
    dd_oos = oos_m.get("max_dd_pct")  # negative
    sh_bh = bh_oos_m.get("sharpe")

    checks["oos_sharpe_gte_0.4"] = (sh_oos is not None and np.isfinite(sh_oos) and sh_oos >= 0.4)
    checks["oos_maxdd_lte_25"] = (dd_oos is not None and np.isfinite(dd_oos) and dd_oos >= -25.0)
    if sh_train not in (None, 0) and np.isfinite(sh_train) and np.isfinite(sh_oos):
        drift = (sh_train - sh_oos) / abs(sh_train)
        checks["oos_within_30pct_of_is"] = drift <= 0.30
        checks["_drift_metric"] = round(drift, 3)
    else:
        checks["oos_within_30pct_of_is"] = False
        checks["_drift_metric"] = None
    checks["oos_beats_bh_btc_sharpe"] = (np.isfinite(sh_oos) and np.isfinite(sh_bh) and sh_oos > sh_bh)
    checks["_all_pass"] = all(v is True for k, v in checks.items() if not k.startswith("_"))
    return checks


def main() -> None:
    weekly = load_weekly_close()
    print(f"[load] weekly frame {weekly.shape}, {weekly.index.min().date()} -> {weekly.index.max().date()}")

    # Clamp OOS end to the latest observed weekly bar
    oos_end = weekly.index.max()
    print(f"[split] train: {TRAIN_START.date()} -> {TRAIN_END.date()} | oos: {OOS_START.date()} -> {oos_end.date()}\n")

    btc_weekly = weekly["BTC/USDT"]
    all_rows = []
    variant_payloads = []

    for v in VARIANTS:
        print(f"--- {v['name']} (role={v['role']}) ---")
        res = run_backtest(weekly, v["direction"], v["lookback_w"], v["cost"])
        ret = res["returns_net"]
        turn = res["turnover"]

        # Full-period (step-3 comparable)
        full = slice_metrics(ret, turn, ret.index.min(), ret.index.max(), f"{v['name']}_full")
        # Train window
        train = slice_metrics(ret, turn, TRAIN_START, TRAIN_END, f"{v['name']}_train")
        # OOS window
        oos = slice_metrics(ret, turn, OOS_START, oos_end, f"{v['name']}_oos")

        # Per-fold metrics on train window
        train_idx = ret.loc[(ret.index >= TRAIN_START) & (ret.index <= TRAIN_END)].index
        folds = purged_kfold_indices(train_idx, K_FOLDS, EMBARGO_WEEKS)
        fold_rows = []
        for f in folds:
            fm = slice_metrics(ret, turn, f["test_start"], f["test_end"], f"{v['name']}_fold{f['fold']}")
            fm["fold"] = f["fold"]
            fold_rows.append(fm)

        # BH BTC on OOS window
        bh_slice = btc_weekly.loc[OOS_START:oos_end].dropna()
        bh_eq = bh_slice / bh_slice.iloc[0]
        bh_ret = bh_eq.pct_change().dropna()
        bh_oos = compute_metrics(bh_eq, bh_ret, pd.Series([0.0], index=[bh_eq.index[0]]), "BH_BTC_oos")

        # BH BTC on train window (for comparison)
        bh_train_slice = btc_weekly.loc[TRAIN_START:TRAIN_END].dropna()
        bh_train_eq = bh_train_slice / bh_train_slice.iloc[0]
        bh_train_ret = bh_train_eq.pct_change().dropna()
        bh_train = compute_metrics(bh_train_eq, bh_train_ret, pd.Series([0.0], index=[bh_train_eq.index[0]]), "BH_BTC_train")

        checks = go_no_go(oos, train, bh_oos)

        # Print
        print(f"  full  Sharpe {full['sharpe']}  CAGR {full['cagr_pct']}%  MaxDD {full['max_dd_pct']}%")
        print(f"  train Sharpe {train['sharpe']}  CAGR {train['cagr_pct']}%  MaxDD {train['max_dd_pct']}%")
        print(f"  OOS   Sharpe {oos['sharpe']}  CAGR {oos['cagr_pct']}%  MaxDD {oos['max_dd_pct']}%  ({oos['n_weeks']}w)")
        print(f"  BH_BTC OOS Sharpe {bh_oos['sharpe']}  CAGR {bh_oos['cagr_pct']}%  MaxDD {bh_oos['max_dd_pct']}%")
        print(f"  fold Sharpes: {[f['sharpe'] for f in fold_rows]}")
        print(f"  checks: {checks}")
        print()

        variant_payloads.append({
            "v": v,
            "full": full, "train": train, "oos": oos,
            "folds": fold_rows,
            "bh_oos": bh_oos, "bh_train": bh_train,
            "checks": checks,
            "returns": ret,
        })

        # Accumulate rows for CSV
        for slice_name, m in [("full", full), ("train", train), ("oos", oos), ("bh_oos", bh_oos), ("bh_train", bh_train)]:
            all_rows.append({"variant": v["name"], "slice": slice_name, **m})
        for fm in fold_rows:
            all_rows.append({"variant": v["name"], "slice": f"fold{fm['fold']}", **fm})

    # Save metrics CSV
    pd.DataFrame(all_rows).to_csv(OUT_DATA / "tsmom_crypto_oos_metrics.csv", index=False)

    # Plot: 2x1 panels — one per variant, showing train + OOS equity + BH_BTC OOS overlay
    fig, axes = plt.subplots(2, 1, figsize=(13, 9))
    for ax, payload in zip(axes, variant_payloads):
        ret = payload["returns"]
        v = payload["v"]
        # Train equity (from ret start -> train end)
        train_ret = ret.loc[(ret.index >= TRAIN_START) & (ret.index <= TRAIN_END)].dropna()
        oos_ret = ret.loc[(ret.index >= OOS_START) & (ret.index <= oos_end)].dropna()

        # Use unified equity series so the OOS picks up where train ended for display
        full_ret = pd.concat([train_ret, oos_ret])
        eq_full = (1.0 + full_ret).cumprod()
        ax.plot(eq_full.loc[TRAIN_START:TRAIN_END].index, eq_full.loc[TRAIN_START:TRAIN_END].values,
                color="tab:blue", label=f"{v['name']} (train)")
        ax.plot(eq_full.loc[OOS_START:oos_end].index, eq_full.loc[OOS_START:oos_end].values,
                color="tab:orange", label=f"{v['name']} (OOS)", linewidth=2)

        # BH BTC scaled to join at OOS_START with strategy equity
        bh_slice = btc_weekly.loc[OOS_START:oos_end].dropna()
        bh_eq = bh_slice / bh_slice.iloc[0]
        # Scale BH to start at the strategy's equity at OOS_START
        join_level = eq_full.loc[eq_full.index <= OOS_START].iloc[-1] if (eq_full.index <= OOS_START).any() else 1.0
        ax.plot(bh_eq.index, bh_eq.values * join_level, color="black", linestyle="--", alpha=0.6, label="BH BTC (OOS)")

        # Shade OOS region
        ax.axvspan(OOS_START, oos_end, color="tab:orange", alpha=0.08)
        ax.set_yscale("log")
        ax.set_title(f"{v['name']}  ({v['role']})")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper left", fontsize=9)
    fig.suptitle("TSMOM Crypto — train vs out-of-sample", fontsize=13)
    fig.tight_layout()
    png_path = OUT_DOCS / "tsmom_crypto_oos_equity.png"
    fig.savefig(png_path, dpi=110)
    plt.close(fig)

    # Persist OOS and train rows to improvements.db::tsmom_runs
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    con = sqlite3.connect("data/improvements.db")
    cur = con.cursor()
    for payload in variant_payloads:
        v = payload["v"]
        for slice_name in ("train", "oos"):
            m = payload[slice_name]
            eq_ret = payload["returns"].loc[
                (payload["returns"].index >= (TRAIN_START if slice_name == "train" else OOS_START))
                & (payload["returns"].index <= (TRAIN_END if slice_name == "train" else oos_end))
            ].dropna()
            eq = (1.0 + eq_ret).cumprod()
            monthly = eq.resample("ME").last().dropna()
            monthly_ret = monthly.pct_change().dropna()
            n_months = len(monthly_ret)
            best = float(monthly_ret.max()) if n_months > 0 else None
            worst = float(monthly_ret.min()) if n_months > 0 else None
            pos = int((monthly_ret > 0).sum())
            neg = int((monthly_ret < 0).sum())
            if slice_name == "oos":
                checks = payload["checks"]
                verdict = "GREEN (OOS all gates pass)" if checks["_all_pass"] else "RED (OOS at least one gate failed)"
            else:
                verdict = "TRAIN window (no gate)"
            notes = (
                f"{slice_name.upper()} slice. Direction LO, lookback {v['lookback_w']}w, cost 10bps, "
                f"weekly rebalance, 24w vol target 10%. "
                f"Universe dynamic (BTC/ETH from 2017, BNB from Nov-2017, SOL from 2020-08)."
            )
            cur.execute("""
                INSERT INTO tsmom_runs
                  (run_time, scope, n_months, start_date, end_date,
                   annual_return, annual_vol, sharpe, sortino, max_drawdown,
                   hit_rate_monthly, best_month, worst_month, positive_months, negative_months,
                   cagr, verdict, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now, f"crypto_{v['name']}_{slice_name}",
                n_months, m["start"], m["end"],
                m["cagr_pct"] / 100.0, m["ann_vol_pct"] / 100.0, m["sharpe"], m["sortino"], m["max_dd_pct"] / 100.0,
                (m["hit_monthly_pct"] or 0) / 100.0, best, worst, pos, neg,
                m["cagr_pct"] / 100.0, verdict, notes,
            ))
    con.commit()
    con.close()

    write_report(variant_payloads, png_path, oos_end)

    # Summary to stdout
    print("=" * 100)
    print("OOS GATE CHECK SUMMARY")
    print("=" * 100)
    for payload in variant_payloads:
        v = payload["v"]; c = payload["checks"]
        verdict = "GREEN" if c["_all_pass"] else "RED"
        print(f"\n{v['name']} ({v['role']}): {verdict}")
        for k, val in c.items():
            if k.startswith("_"):
                continue
            mark = "OK " if val else "FAIL"
            print(f"  [{mark}] {k}")


def write_report(payloads: list[dict], png_path: Path, oos_end: pd.Timestamp) -> None:
    def fmt(x):
        return f"{x:+.2f}" if isinstance(x, (int, float)) and x is not None and np.isfinite(x) else "nan"
    L = []
    L += [
        "# TSMOM Crypto — Out-of-Sample Validation (Phase 10 step 4)",
        "",
        f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
        "",
        "## Setup",
        "",
        f"| Item | Value |",
        f"|---|---|",
        f"| Training window | 2017-08-17 -> 2024-12-31 |",
        f"| Held-out OOS    | 2025-01-01 -> {oos_end.date()} |",
        f"| Variants        | LO/12m/10bps (primary), LO/12w/10bps (secondary) |",
        f"| K-fold          | K=5 on training window, {EMBARGO_WEEKS}-week embargo at boundaries |",
        f"| Strategy params | Same as step 3 (no refitting) |",
        "",
        "## Gate thresholds (from evaluation_report.md §7.3)",
        "",
        "| Gate | Threshold | Direction |",
        "|---|---|---|",
        "| OOS Sharpe | >= 0.4 | absolute |",
        "| OOS Max DD | <= 25% | absolute (>= -25%) |",
        "| OOS vs IS Sharpe drift | within 30% of train Sharpe | (train - OOS) / train <= 0.30 |",
        "| OOS vs BH BTC | Sharpe > BH BTC Sharpe in OOS window | absolute |",
        "",
        "All four must pass for GREEN.",
        "",
    ]

    for payload in payloads:
        v = payload["v"]
        L.append(f"## {v['name']}  ({v['role']})")
        L.append("")

        # Headline comparison
        L.append("### Headline")
        L.append("")
        L.append("| Slice | Start | End | Weeks | Sharpe | Sortino | CAGR % | Vol % | MaxDD % | Hit monthly % |")
        L.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
        for lbl_key, lbl in [("full", "Full (IS, step 3)"), ("train", "Train"), ("oos", "**OOS**"), ("bh_oos", "BH BTC OOS"), ("bh_train", "BH BTC train")]:
            m = payload[lbl_key]
            L.append(
                f"| {lbl} | {m.get('start', '-')} | {m.get('end', '-')} | {m.get('n_weeks', 0)} | "
                f"{m.get('sharpe', 'nan')} | {m.get('sortino', 'nan')} | {m.get('cagr_pct', 'nan')} | "
                f"{m.get('ann_vol_pct', 'nan')} | {m.get('max_dd_pct', 'nan')} | {m.get('hit_monthly_pct', 'nan')} |"
            )
        L.append("")

        # Gate check
        c = payload["checks"]
        verdict = "🟢 **GREEN — all gates pass**" if c["_all_pass"] else "🔴 **RED — at least one gate failed**"
        L.append("### Gate check")
        L.append("")
        L.append(f"{verdict}")
        L.append("")
        L.append("| Gate | Result |")
        L.append("|---|---|")
        L.append(f"| OOS Sharpe >= 0.4 | {'PASS' if c['oos_sharpe_gte_0.4'] else 'FAIL'}  ({payload['oos']['sharpe']}) |")
        L.append(f"| OOS MaxDD >= -25% | {'PASS' if c['oos_maxdd_lte_25'] else 'FAIL'}  ({payload['oos']['max_dd_pct']}%) |")
        drift = c.get("_drift_metric")
        L.append(f"| OOS within 30% of train Sharpe | {'PASS' if c['oos_within_30pct_of_is'] else 'FAIL'}  (drift = {drift if drift is not None else 'n/a'}) |")
        L.append(f"| OOS Sharpe > BH BTC OOS Sharpe | {'PASS' if c['oos_beats_bh_btc_sharpe'] else 'FAIL'}  (strat {payload['oos']['sharpe']} vs BH {payload['bh_oos']['sharpe']}) |")
        L.append("")

        # Fold diagnostics
        L.append("### Purged K-fold diagnostics (training window only)")
        L.append("")
        L.append("| Fold | Start | End | Weeks | Sharpe | CAGR % | MaxDD % |")
        L.append("|---:|---|---|---:|---:|---:|---:|")
        fold_sharpes = []
        for fm in payload["folds"]:
            L.append(f"| {fm['fold']} | {fm.get('start')} | {fm.get('end')} | {fm.get('n_weeks')} | "
                     f"{fm.get('sharpe')} | {fm.get('cagr_pct')} | {fm.get('max_dd_pct')} |")
            if fm.get("sharpe") is not None and np.isfinite(fm.get("sharpe", float("nan"))):
                fold_sharpes.append(fm["sharpe"])
        if fold_sharpes:
            arr = np.array(fold_sharpes)
            L.append("")
            L.append(f"Fold Sharpe stats: mean **{arr.mean():.3f}**, std **{arr.std(ddof=0):.3f}**, min {arr.min():.3f}, max {arr.max():.3f}.")
        L.append("")

    L += [
        "## Equity plot",
        "",
        f"![train vs OOS equity]({png_path.name})",
        "",
        "## Caveats",
        "",
        "- The held-out window is ~16 months. Annualized Sharpe from ~60-70 weekly observations has wide confidence intervals (rough std error of Sharpe ~ sqrt(1/n_weeks * 52) = 0.9 for a single observation — so OOS Sharpe measurements are noisy).",
        "- Strategy parameters (12m lookback, 24w vol, 10% target) come from AQR conventions, not fit on this data. That makes the OOS test cleaner than it would be for a ML-fit model — but the cost knob (10 bps) and rebalance rule *were* chosen after seeing step 3.",
        "- K-fold is used as a stability diagnostic here, not for parameter selection. A large Sharpe spread across folds indicates regime-dependent performance; a tight spread indicates consistency.",
        "- No funding cost on any short (we dropped shorts, so not applicable).",
        "- Today's partial candle dropped during load; OOS ends at the last fully completed weekly Friday.",
        "",
        "## Files",
        "",
        "- `data/research/tsmom_crypto_oos_metrics.csv` — every slice, every variant, row per fold",
        f"- `docs/research/{png_path.name}` — train vs OOS equity curves + BH BTC overlay",
        "- `improvements.db::tsmom_runs` — new rows with scope `crypto_<variant>_train` and `crypto_<variant>_oos`",
        "- `scripts/research_tsmom_crypto_oos.py` — re-runnable (reuses step-3 backtest engine)",
        "",
    ]
    (OUT_DOCS / "tsmom_crypto_oos_report.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
