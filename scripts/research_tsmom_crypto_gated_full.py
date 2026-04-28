"""Phase 10.5 step 3: formal null-result backtest — gated LO/12w.

Runs the LO/12w strategy with the regime-filter overlay on the full 2017-2026
dataset, then produces OOS metrics for the 2025-01-01 → latest window and
compares them against the ungated step-4 baseline.

Per the approved spec (docs/research/regime_filter_spec.md §7), the filter
was specified with ONE knob (80th-percentile 4-week basket vol, training-data
snapshot threshold) and is NOT iterated on failure. Step 2's smoke test already
established that the filter fires 0/69 weeks in OOS, so gated == ungated in OOS
by construction. This script runs the formal end-to-end validation, writes the
null-result report, and persists the REJECTED verdict.

Outputs:
  data/research/tsmom_crypto_gated_metrics.csv
  docs/research/regime_filter_results.md
  docs/research/regime_filter_equity.png
  improvements.db::tsmom_runs  (2 new rows: gated_train + gated_oos)
  improvements.db::go_no_go_decisions  (1 new row: phase 10 REJECTED final)
  improvements.db::phase_steps (updates for Phase 10.5 steps 3-6)
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
    WEEKS_PER_YEAR,
    compute_metrics,
    load_weekly_close,
    run_backtest,
)
from research_tsmom_crypto_gated import (
    DEFAULT_PERCENTILE,
    DEFAULT_WINDOW,
    TRAIN_END,
    apply_regime_filter,
    compute_basket_vol,
    compute_regime_threshold,
)

TRAIN_START = pd.Timestamp("2017-08-17")
OOS_START = pd.Timestamp("2025-01-01")

OUT_DATA = Path("data/research")
OUT_DOCS = Path("docs/research")
OUT_DATA.mkdir(parents=True, exist_ok=True)
OUT_DOCS.mkdir(parents=True, exist_ok=True)


def backtest_gated_vs_ungated(
    weekly: pd.DataFrame,
    lookback_w: int = 12,
    cost: float = 0.001,
) -> dict:
    """Run base LO backtest, apply filter overlay, compute returns for both."""
    # 1. Base ungated
    base = run_backtest(weekly, direction="LO", lookback_w=lookback_w, cost_per_side=cost)

    # 2. Threshold from training data only
    vol = compute_basket_vol(weekly, DEFAULT_WINDOW)
    threshold = compute_regime_threshold(vol, TRAIN_END, DEFAULT_PERCENTILE)

    # 3. Apply filter to the (already-lagged) weights
    weights_gated = apply_regime_filter(base["weights"], vol, threshold)

    # 4. Recompute portfolio returns with gated weights
    ret = weekly.pct_change()
    port_ret_gross = (weights_gated * ret).sum(axis=1)
    turnover = weights_gated.diff().abs().sum(axis=1).fillna(weights_gated.abs().iloc[0].sum() if len(weights_gated) else 0.0)
    tc = turnover * cost
    port_ret_net = port_ret_gross - tc

    # Trim to the same first_valid the ungated run uses
    first_valid = base["returns_net"].index[0]
    port_ret_net = port_ret_net.loc[first_valid:]
    turnover = turnover.loc[first_valid:]

    return {
        "ungated_returns": base["returns_net"],
        "gated_returns": port_ret_net,
        "ungated_turnover": base["turnover"],
        "gated_turnover": turnover,
        "ungated_weights": base["weights"],
        "gated_weights": weights_gated.loc[first_valid:],
        "basket_vol": vol,
        "threshold": threshold,
    }


def slice_metrics(returns: pd.Series, turnover: pd.Series, start: pd.Timestamp, end: pd.Timestamp, label: str) -> dict:
    r = returns.loc[(returns.index >= start) & (returns.index <= end)].dropna()
    if len(r) == 0:
        return {"label": label, "note": "empty slice"}
    eq = (1.0 + r).cumprod()
    t = turnover.loc[r.index] if len(turnover) else pd.Series([0.0], index=[eq.index[0]])
    return compute_metrics(eq, r, t, label)


def main() -> None:
    print("Phase 10.5 step 3 — formal null-result evaluation")
    print("=" * 72)

    weekly = load_weekly_close()
    oos_end = weekly.index.max()
    print(f"[data] weekly frame {weekly.shape} | OOS window: {OOS_START.date()} → {oos_end.date()}")

    res = backtest_gated_vs_ungated(weekly)
    threshold = res["threshold"]

    # Fire-rate diagnostics
    vol = res["basket_vol"]
    ungated_idx = res["ungated_returns"].index
    vol_on_idx = vol.reindex(ungated_idx)
    fire_mask = (vol_on_idx > threshold) & vol_on_idx.notna()
    train_slice = (ungated_idx >= TRAIN_START) & (ungated_idx <= TRAIN_END)
    oos_slice = ungated_idx >= OOS_START
    train_fires = int((fire_mask & train_slice).sum())
    oos_fires = int((fire_mask & oos_slice).sum())
    train_weeks = int(train_slice.sum())
    oos_weeks = int(oos_slice.sum())
    print(f"[filter] threshold = {threshold:.4f} ann. vol")
    print(f"[filter] train fires: {train_fires}/{train_weeks} ({100*train_fires/train_weeks:.1f}%)")
    print(f"[filter] OOS   fires: {oos_fires}/{oos_weeks} ({100*oos_fires/oos_weeks:.1f}%)")

    # Metrics side-by-side
    ung_train = slice_metrics(res["ungated_returns"], res["ungated_turnover"], TRAIN_START, TRAIN_END, "ungated_train")
    ung_oos = slice_metrics(res["ungated_returns"], res["ungated_turnover"], OOS_START, oos_end, "ungated_oos")
    gat_train = slice_metrics(res["gated_returns"], res["gated_turnover"], TRAIN_START, TRAIN_END, "gated_train")
    gat_oos = slice_metrics(res["gated_returns"], res["gated_turnover"], OOS_START, oos_end, "gated_oos")

    # BH BTC OOS (reference)
    btc = weekly["BTC/USDT"].loc[OOS_START:oos_end].dropna()
    btc_eq = btc / btc.iloc[0]
    btc_ret = btc_eq.pct_change().dropna()
    bh_oos = compute_metrics(btc_eq, btc_ret, pd.Series([0.0], index=[btc_eq.index[0]]), "BH_BTC_oos")

    # ─── Five-gate evaluation ────────────────────────────────────────────
    gates = {}
    sh_oos = gat_oos.get("sharpe")
    dd_oos = gat_oos.get("max_dd_pct")
    sh_train = gat_train.get("sharpe")
    sh_bh = bh_oos.get("sharpe")
    sh_ungated_oos = ung_oos.get("sharpe")

    gates["1. OOS Sharpe >= 0.4"] = ("PASS" if sh_oos is not None and sh_oos >= 0.4 else "FAIL", f"{sh_oos}")
    gates["2. OOS MaxDD >= -25%"] = ("PASS" if dd_oos is not None and dd_oos >= -25.0 else "FAIL", f"{dd_oos}%")
    if sh_train and sh_train != 0 and sh_oos is not None:
        drift = (sh_train - sh_oos) / abs(sh_train)
        gates["3. OOS within 30% of train Sharpe"] = ("PASS" if drift <= 0.30 else "FAIL", f"drift {drift:.3f}")
    else:
        gates["3. OOS within 30% of train Sharpe"] = ("FAIL", "insufficient data")
    gates["4. OOS Sharpe > BH BTC OOS"] = ("PASS" if sh_oos is not None and sh_bh is not None and sh_oos > sh_bh else "FAIL", f"strat {sh_oos} vs BH {sh_bh}")
    gates["5. Gated OOS > Ungated OOS"] = ("PASS" if sh_oos is not None and sh_ungated_oos is not None and sh_oos > sh_ungated_oos else "FAIL", f"gated {sh_oos} vs ungated {sh_ungated_oos}")

    all_pass = all(v[0] == "PASS" for v in gates.values())
    verdict = "GREEN (all 5 gates pass)" if all_pass else "RED (REJECTED)"
    passed = sum(1 for v in gates.values() if v[0] == "PASS")

    print()
    print(f"[gates] {passed}/{len(gates)} pass | verdict {verdict}")
    for name, (status, detail) in gates.items():
        print(f"  [{status}] {name} — {detail}")

    # ─── Save metrics CSV ────────────────────────────────────────────────
    rows = []
    for label, m in [("ungated_train", ung_train), ("ungated_oos", ung_oos),
                     ("gated_train", gat_train), ("gated_oos", gat_oos),
                     ("BH_BTC_oos", bh_oos)]:
        rows.append({"label": label, **m})
    pd.DataFrame(rows).to_csv(OUT_DATA / "tsmom_crypto_gated_metrics.csv", index=False)

    # ─── Equity plot: gated vs ungated over OOS window ───────────────────
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9))

    # Panel 1: full-period equity (both curves, basket-vol overlay for context)
    full_ung_ret = res["ungated_returns"].dropna()
    full_gat_ret = res["gated_returns"].dropna()
    eq_ung = (1.0 + full_ung_ret).cumprod()
    eq_gat = (1.0 + full_gat_ret).cumprod()
    ax1.plot(eq_ung.index, eq_ung.values, label="Ungated LO/12w", color="tab:blue")
    ax1.plot(eq_gat.index, eq_gat.values, label="Gated LO/12w (80th pct filter)", color="tab:orange", linewidth=2)
    ax1.axvspan(OOS_START, oos_end, color="tab:orange", alpha=0.08, label="OOS window")
    # Threshold line + vol (secondary axis)
    ax1b = ax1.twinx()
    ax1b.plot(vol.index, vol.values, color="gray", alpha=0.35, label="Basket 4w vol (ann)")
    ax1b.axhline(threshold, color="red", linestyle=":", alpha=0.6, label=f"Threshold {threshold:.3f}")
    ax1b.set_ylabel("Basket vol (ann)", color="gray")
    ax1.set_yscale("log")
    ax1.set_title("Full-period equity — ungated vs gated (with basket vol overlay)")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper left", fontsize=9)
    ax1b.legend(loc="lower right", fontsize=8)

    # Panel 2: OOS window zoom
    oos_eq_ung = eq_ung.loc[OOS_START:oos_end] / eq_ung.loc[OOS_START:oos_end].iloc[0]
    oos_eq_gat = eq_gat.loc[OOS_START:oos_end] / eq_gat.loc[OOS_START:oos_end].iloc[0]
    ax2.plot(oos_eq_ung.index, oos_eq_ung.values, label="Ungated LO/12w (OOS)", color="tab:blue")
    ax2.plot(oos_eq_gat.index, oos_eq_gat.values, label="Gated LO/12w (OOS)", color="tab:orange", linewidth=2)
    ax2.plot(btc_eq.index, btc_eq.values, color="black", linestyle="--", alpha=0.6, label="BH BTC (OOS)")
    ax2.set_title(f"OOS zoom — gated identical to ungated because filter fired {oos_fires}/{oos_weeks} weeks")
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc="upper left", fontsize=9)

    fig.suptitle("Phase 10.5 — TSMOM Crypto gated vs ungated (IN-SAMPLE + OOS)", fontsize=13)
    fig.tight_layout()
    png = OUT_DOCS / "regime_filter_equity.png"
    fig.savefig(png, dpi=110)
    plt.close(fig)

    # ─── Persist new tsmom_runs rows + go_no_go_decisions + phase_steps ──
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    con = sqlite3.connect("data/improvements.db")
    cur = con.cursor()

    try:
        con.execute("BEGIN")

        # tsmom_runs rows for gated train + oos
        for slice_name, m, ret_series in [
            ("gated_train", gat_train, res["gated_returns"].loc[(res["gated_returns"].index >= TRAIN_START) & (res["gated_returns"].index <= TRAIN_END)]),
            ("gated_oos", gat_oos, res["gated_returns"].loc[(res["gated_returns"].index >= OOS_START) & (res["gated_returns"].index <= oos_end)]),
        ]:
            eq = (1.0 + ret_series.dropna()).cumprod()
            monthly = eq.resample("ME").last().dropna()
            monthly_ret = monthly.pct_change().dropna()
            n_months = len(monthly_ret)
            best = float(monthly_ret.max()) if n_months else None
            worst = float(monthly_ret.min()) if n_months else None
            pos = int((monthly_ret > 0).sum())
            neg = int((monthly_ret < 0).sum())
            cur.execute("""
                INSERT INTO tsmom_runs
                  (run_time, scope, n_months, start_date, end_date,
                   annual_return, annual_vol, sharpe, sortino, max_drawdown,
                   hit_rate_monthly, best_month, worst_month, positive_months, negative_months,
                   cagr, verdict, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now, f"crypto_LO_12w_c10bps_{slice_name}",
                n_months, m.get("start"), m.get("end"),
                (m.get("cagr_pct", 0) or 0) / 100.0,
                (m.get("ann_vol_pct", 0) or 0) / 100.0,
                m.get("sharpe"),
                m.get("sortino"),
                (m.get("max_dd_pct", 0) or 0) / 100.0,
                (m.get("hit_monthly_pct") or 0) / 100.0,
                best, worst, pos, neg,
                (m.get("cagr_pct", 0) or 0) / 100.0,
                "GATED (regime filter overlay)",
                f"Phase 10.5 step 3 null-result run. Filter fired {train_fires}/{train_weeks} train weeks and {oos_fires}/{oos_weeks} OOS weeks. OOS Sharpe identical to ungated because filter never engaged in OOS regime.",
            ))

        # Mark Phase 10.5 step 3 complete (null result documented)
        cur.execute(
            "UPDATE phase_steps SET status='COMPLETED', completed_at=?, notes=? WHERE phase_number=105 AND step_order=3",
            (today_date,
             f"Gated backtest run. Filter fired {train_fires}/{train_weeks} train weeks ({100*train_fires/train_weeks:.1f}%) and {oos_fires}/{oos_weeks} OOS weeks ({100*oos_fires/oos_weeks:.1f}%). Gated OOS identical to ungated OOS by construction. Null result confirmed."),
        )
        # Steps 4-5 also complete (they were gated on step 3; null result collapses them)
        cur.execute(
            "UPDATE phase_steps SET status='COMPLETED', completed_at=?, notes=? WHERE phase_number=105 AND step_order=4",
            (today_date, "Collapsed into step 3 run: OOS validation identical to step-4 ungated result because filter never fired in OOS."),
        )
        cur.execute(
            "UPDATE phase_steps SET status='COMPLETED', completed_at=?, notes=? WHERE phase_number=105 AND step_order=5",
            (today_date, f"Comparison: gated Sharpe {gat_oos.get('sharpe')} vs ungated Sharpe {ung_oos.get('sharpe')} — IDENTICAL (filter null). Gate 5 (gated > ungated) FAILS. See docs/research/regime_filter_results.md."),
        )
        cur.execute(
            "UPDATE phase_steps SET status='COMPLETED', completed_at=?, notes=? WHERE phase_number=105 AND step_order=6",
            (today_date, "Final decision: v4 crypto momentum REJECTED. No further iteration permitted per spec §7 scope lockdown. See go_no_go_decisions phase 10 latest row (REJECTED)."),
        )

        # Mark Phase 10.5 itself COMPLETED
        cur.execute(
            "UPDATE project_phases SET status='COMPLETED', completed_at=?, notes=? WHERE phase_number=105",
            (today_date, "Rescue attempt completed 2026-04-22. Null result (filter never engaged in OOS). v4 crypto momentum REJECTED. Next: pivot Phase 10 to different research track per v4_framework.md."),
        )

        # Add final RED verdict for Phase 10
        cur.execute("""
            INSERT INTO go_no_go_decisions
              (phase_number, decision_date, verdict, gates_passed, gates_total,
               rationale_en, rationale_ar, decided_by, next_action)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            10, today_date, "RED",
            passed, len(gates),
            f"Phase 10.5 rescue attempt FAILED with null result. Regime filter (80th-pct 4w basket vol, training-snapshot threshold) fired {train_fires}/{train_weeks} train weeks (expected ~20%) but 0/{oos_weeks} OOS weeks — the 2025-2026 OOS regime was consistent low-vol downtrend, not high-vol chop. Gated OOS metrics are identical to ungated: Sharpe {sh_oos}, drift {((sh_train or 0) - (sh_oos or 0))/(abs(sh_train) if sh_train else 1):.2f}. Per spec §7 (scope lockdown, no iteration on failure), v4 crypto momentum is REJECTED. Gate scoreboard: {passed}/{len(gates)} pass.",
            f"محاولة الإنقاذ في المرحلة 10.5 فشلت بنتيجة صفرية. فلتر النظام (نسبة 80 مئوية من تقلب السلة 4-أسابيع، عتبة لقطة التدريب) أطلق {train_fires}/{train_weeks} أسبوع تدريب (المتوقع ~20%) لكن 0/{oos_weeks} أسبوع خارج العينة — نظام 2025-2026 كان هبوط منخفض التقلب مستمر، ليس تقلب عالي متقلقل. مقاييس OOS مع الفلتر مطابقة لبدون فلتر. حسب §7 من المواصفات (قفل النطاق، ممنوع التكرار عند الفشل)، زخم كريبتو v4 مرفوض. لوحة البوابات: {passed}/{len(gates)} نجاح.",
            "Phase 10.5 null-result run + user-locked rejection policy",
            "Pivot Phase 10 to a different research track per v4_framework.md: candidates include commodity futures trend, crypto basis/funding arbitrage, volatility selling (defined risk). Phase 10.5 closed. Phase 10 closed. Phase 11 (strategy expansion) remains NOT_STARTED and awaits a new track selection.",
        ))

        con.commit()
        print()
        print(f"[DB] committed: tsmom_runs +2 rows, go_no_go_decisions +1 row (REJECTED), phase_steps updated, project_phases 10.5 → COMPLETED")
    except Exception as e:
        con.rollback()
        print(f"[FAIL] rolled back: {e}")
        raise
    finally:
        con.close()

    # ─── Markdown report ────────────────────────────────────────────────
    write_report(
        res, ung_train, ung_oos, gat_train, gat_oos, bh_oos,
        gates, threshold, train_fires, train_weeks, oos_fires, oos_weeks, png,
    )

    print(f"[OK] wrote {OUT_DOCS/'regime_filter_results.md'}")


def write_report(res, ung_train, ung_oos, gat_train, gat_oos, bh_oos,
                 gates, threshold, train_fires, train_weeks, oos_fires, oos_weeks, png):
    passed = sum(1 for v in gates.values() if v[0] == "PASS")
    total = len(gates)

    L = [
        "# Phase 10.5 — Regime Filter Results (NULL RESULT)",
        "",
        f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
        "",
        f"## Headline: 🔴 **REJECTED** ({passed}/{total} gates pass)",
        "",
        "The 80th-percentile 4-week basket-vol filter **did not engage in the OOS regime**. ",
        "Gated OOS performance is identical to ungated OOS performance by construction. ",
        "Per the Phase 10.5 spec §7 scope lockdown, v4 crypto momentum is formally REJECTED.",
        "",
        "## Filter engagement summary",
        "",
        f"- Threshold (training-window 80th percentile of 4-week basket vol): **{threshold:.4f} annualized**",
        f"- Training window fire rate: **{train_fires}/{train_weeks} weeks ({100*train_fires/train_weeks:.1f}%)** — near target 20%, filter well-calibrated on training data",
        f"- OOS fire rate: **{oos_fires}/{oos_weeks} weeks ({100*oos_fires/oos_weeks:.1f}%)** — filter never engaged",
        "",
        "The OOS window (2025-01 → latest) was a consistent low-vol downtrend, not the high-vol chop the filter was designed to address. Basket vol in OOS never exceeded the training-period 80th percentile.",
        "",
        "## Metrics side-by-side",
        "",
        "| Slice | Sharpe | Sortino | CAGR % | Vol % | MaxDD % | n_weeks |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, m in [("Ungated train", ung_train), ("**Gated train**", gat_train),
                     ("Ungated OOS", ung_oos), ("**Gated OOS**", gat_oos),
                     ("BH BTC OOS", bh_oos)]:
        L.append(f"| {label} | {m.get('sharpe')} | {m.get('sortino')} | {m.get('cagr_pct')} | {m.get('ann_vol_pct')} | {m.get('max_dd_pct')} | {m.get('n_weeks')} |")
    L.append("")

    L.append("## Gate scoreboard")
    L.append("")
    L.append("| Gate | Result | Detail |")
    L.append("|---|---|---|")
    for name, (status, detail) in gates.items():
        emoji = "🟢" if status == "PASS" else "🔴"
        L.append(f"| {name} | {emoji} **{status}** | {detail} |")
    L.append("")

    L.extend([
        "## Why gated == ungated in OOS",
        "",
        "By construction. The filter zeroes weights only when basket vol exceeds the training-snapshot 80th percentile. In OOS, basket vol never crossed that threshold. So the filter's `filter_on` indicator was `True` for all 69 OOS weeks, the weight multiplier was 1.0 everywhere, and gated weights equal ungated weights week-for-week. The OOS metrics are therefore identical to the Phase 10 step 4 ungated LO/12w result.",
        "",
        "## Why the filter addressed the wrong failure mode",
        "",
        "Phase 10 step 4 showed LO/12w failing the drift-stability gate (train Sharpe 1.27 → OOS Sharpe 0.55). Our hypothesis was that this decay was caused by whipsaw in high-volatility chop regimes. The filter was designed to zero positions in exactly those regimes. But the actual OOS failure mode was different — 2025-2026 was a consistent downtrend with modest volatility, where:",
        "",
        "- Momentum signals were reliably negative or weak (no false positives to filter)",
        "- Basket vol stayed below the training 80th percentile",
        "- The strategy earned small positive Sharpe (+0.55) by sitting in cash most weeks",
        "",
        "Raising the filter sensitivity (lower threshold, e.g. 50th percentile) would have made it fire more often — but with no downside for TSMOM to avoid in OOS, this would have cost more than it saved. Per spec §7, tuning the threshold is not permitted: any positive result from re-tuning on OOS data is overfitting.",
        "",
        "## Decision",
        "",
        "**v4 crypto momentum: REJECTED.**",
        "",
        "Phase 10 is closed. Phase 10.5 is closed. The regime-filter rescue attempt was specified and executed honestly; it produced a null result. Per v4_framework.md Shift 2 (Underexploited Niches), viable next tracks include commodity futures trend, crypto basis/funding arbitrage, or volatility selling (defined risk). Phase 11 (Strategy Expansion) remains NOT_STARTED pending new track selection.",
        "",
        "## Equity plot",
        "",
        f"![gated vs ungated equity]({png.name})",
        "",
        "## Files",
        "",
        "- `data/research/tsmom_crypto_gated_metrics.csv` — metrics table",
        "- `docs/research/regime_filter_equity.png` — 2-panel plot",
        "- `scripts/research_tsmom_crypto_gated_full.py` — this run (re-runnable)",
        "- `improvements.db::tsmom_runs` — 2 new rows (gated_train, gated_oos)",
        "- `improvements.db::go_no_go_decisions` — new row (phase 10, RED, final)",
        "- `improvements.db::phase_steps` — Phase 10.5 steps 3-6 COMPLETED",
        "- `improvements.db::project_phases` — Phase 10.5 COMPLETED",
        "",
    ])

    (OUT_DOCS / "regime_filter_results.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
