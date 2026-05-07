"""Phase 7 Path B — walk-forward validation of the symbol whitelist.

The single-corpus Path B run (`scripts/run_path_b_stratification.py`)
selected the whitelist by checking R-PF stability in BOTH time halves.
The "late half" was therefore in-sample for the gate selection, so the
final 1.85 R-PF reading on EURUSD-RSI is over-fit-tinted by construction.

This script does proper walk-forward:

  - For each cutoff date in a quarterly grid, derive the whitelist
    from signals BEFORE the cutoff using the same dual-half R-PF
    gate as `run_path_b_stratification.py`.
  - Apply that frozen whitelist to signals in the next 6 months
    (the OOS window). Record n / wins / WR per (cutoff, strategy).
  - Aggregate OOS predictions across all cutoffs and compute the
    overall R-PF — that is the honest validation number.

The trade-off vs single hold-out: walk-forward uses each year of
data ~once as test and ~once as train, so the OOS sample size is
the largest the corpus can support. The cost is methodological
complexity and a slight bias from earlier cutoffs having less
training data than later ones.

Outputs:
  - `docs/research/phase7_path_b_walkforward.md`
  - decisions_log entry recording the validation verdict
"""
from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3

import pandas as pd

SIGNALS_PARQUET = Path("data/research/primary_signals.parquet")
REPORT_OUT = Path("docs/research/phase7_path_b_walkforward.md")
TRACKER_DB = "data/improvements.db"

STRATEGY_RR = {
    "macd_crossover": 1.4,
    "rsi_reversal": 1.5,
}

# Walk-forward parameters. CUTOFF_GRID is the set of dates at which
# we freeze the whitelist for the next OOS_MONTHS-month window.
# MIN_TRAIN_YEARS guards against using cutoffs so early there's
# barely any training data.
CUTOFF_GRID = [
    "2024-01-01",
    "2024-04-01",
    "2024-07-01",
    "2024-10-01",
    "2025-01-01",
    "2025-04-01",
    "2025-07-01",
    "2025-10-01",
]
OOS_MONTHS = 6
MIN_TRAIN_YEARS = 2.0
RPF_GATE = 1.30
MIN_N_PER_HALF = 15


def projected_rpf(wr_pct: float, rr: float) -> float:
    if wr_pct <= 0 or wr_pct >= 100:
        return float("inf") if wr_pct >= 100 else 0.0
    w = wr_pct / 100.0
    return round((w * rr) / (1 - w), 3)


def realised_rpf(wins: int, losses: int, rr: float) -> float:
    """R-PF for a window: wins each contribute +rr, losses each -1."""
    pos = wins * rr
    neg = losses * 1.0
    if neg == 0:
        return float("inf") if pos > 0 else 0.0
    return round(pos / neg, 3)


def derive_whitelist(train_df: pd.DataFrame, strategy: str, rr: float) -> list[str]:
    """Same dual-half + min-n gate as run_path_b_stratification.py, but
    applied only to a subset of the corpus (the training window)."""
    s = train_df[(train_df["strategy"] == strategy) & (train_df["label"] != 0)].copy()
    if s.empty:
        return []
    s = s.sort_values("time")
    cutoff = s["time"].quantile(0.5)
    s["half"] = (s["time"] >= cutoff).map({True: "late", False: "early"})

    whitelist = []
    for sym in sorted(s["symbol"].unique()):
        sub = s[s["symbol"] == sym]
        for_half = {}
        ok = True
        for half in ("early", "late"):
            h = sub[sub["half"] == half]
            n_h = len(h)
            wins_h = int((h["label"] == 1).sum())
            wr_h = 100.0 * wins_h / max(1, n_h) if n_h else 0.0
            rpf_h = projected_rpf(wr_h, rr)
            for_half[half] = (n_h, wr_h, rpf_h)
            if n_h < MIN_N_PER_HALF or rpf_h < RPF_GATE:
                ok = False
        if ok:
            whitelist.append(sym)
    return whitelist


def main() -> int:
    print("=" * 78)
    print("  Phase 7 Path B — walk-forward validation")
    print(f"  Run: {datetime.now().isoformat(timespec='seconds')}")
    print(f"  OOS window: {OOS_MONTHS} months  | min train: {MIN_TRAIN_YEARS} years")
    print(f"  Gate: R-PF ≥ {RPF_GATE} in both halves, n ≥ {MIN_N_PER_HALF} per half")
    print("=" * 78)

    df = pd.read_parquet(SIGNALS_PARQUET)
    df = df[df["label"] != 0].copy()
    df["time"] = pd.to_datetime(df["time"])
    earliest = df["time"].min()
    print(f"  Corpus: {len(df):,} signals, {earliest.date()} → {df['time'].max().date()}\n")

    rows = []
    oos_predictions = {strat: [] for strat in STRATEGY_RR}

    for cutoff_str in CUTOFF_GRID:
        cutoff = pd.Timestamp(cutoff_str)
        if (cutoff - earliest).days / 365.25 < MIN_TRAIN_YEARS:
            print(f"  cutoff {cutoff.date()}: < {MIN_TRAIN_YEARS}y train data — skip")
            continue

        train_end = cutoff
        oos_end = cutoff + pd.DateOffset(months=OOS_MONTHS)

        train = df[df["time"] < train_end]
        oos = df[(df["time"] >= train_end) & (df["time"] < oos_end)]

        print(f"  cutoff {cutoff.date()} (train n={len(train)}, OOS n={len(oos)}):")
        for strat, rr in STRATEGY_RR.items():
            whitelist = derive_whitelist(train, strat, rr)
            oos_strat = oos[(oos["strategy"] == strat) & (oos["symbol"].isin(whitelist))]
            n_oos = len(oos_strat)
            wins_oos = int((oos_strat["label"] == 1).sum())
            losses_oos = n_oos - wins_oos
            wr_oos = 100.0 * wins_oos / n_oos if n_oos else 0.0
            rpf_oos = realised_rpf(wins_oos, losses_oos, rr) if n_oos else 0.0
            print(f"    {strat:<20} whitelist={whitelist or '[]':<28} "
                  f"OOS n={n_oos:3d} wins={wins_oos} WR={wr_oos:5.1f}% R-PF={rpf_oos:.2f}")
            rows.append({
                "cutoff": cutoff_str,
                "strategy": strat,
                "whitelist": whitelist,
                "oos_n": n_oos,
                "oos_wins": wins_oos,
                "oos_losses": losses_oos,
                "oos_wr": wr_oos,
                "oos_rpf": rpf_oos,
            })
            for _, sig in oos_strat.iterrows():
                oos_predictions[strat].append({
                    "cutoff": cutoff_str,
                    "time": sig["time"],
                    "symbol": sig["symbol"],
                    "label": int(sig["label"]),
                    "win": int(sig["label"] == 1),
                })
        print()

    # Aggregate OOS R-PF per strategy
    print("-" * 78)
    print("  Aggregate OOS verdict")
    aggregate = {}
    for strat, rr in STRATEGY_RR.items():
        preds = oos_predictions[strat]
        n = len(preds)
        wins = sum(p["win"] for p in preds)
        losses = n - wins
        wr = 100.0 * wins / n if n else 0.0
        rpf = realised_rpf(wins, losses, rr) if n else 0.0
        passes = rpf >= RPF_GATE and n >= 10  # require ≥ 10 OOS predictions to call it
        print(f"    {strat:<20}  n={n:3d}  WR={wr:5.1f}%  R-PF={rpf:.3f}  "
              f"{'PASS (≥1.30)' if passes else 'FAIL or insufficient n'}")
        aggregate[strat] = {
            "n": n, "wins": wins, "losses": losses,
            "wr": wr, "rpf": rpf, "passes": passes,
        }

    # ─── Markdown report ───
    md = []
    md.append("# Phase 7 Path B — walk-forward validation\n")
    md.append(f"**Date:** {datetime.now().date().isoformat()}  ")
    md.append("**Re-runnable:** `python scripts/run_path_b_walkforward.py`\n")

    md.append("## Why walk-forward\n")
    md.append("`run_path_b_stratification.py` picked the whitelist by checking "
              "R-PF stability in BOTH time halves of the full corpus. The late "
              "half was therefore in-sample for the gate selection itself — "
              "so the headline 'EURUSD-RSI R-PF=1.85 in late half' is over-fit-tinted "
              "by construction. This script fixes that: at each quarterly cutoff, "
              "the whitelist is derived from train-only data and applied to the "
              "next 6 months of OOS signals. The aggregate of all OOS predictions "
              f"is the honest validation number.\n")

    md.append("## Method\n")
    md.append(f"- Cutoff grid: {CUTOFF_GRID}")
    md.append(f"- OOS window per cutoff: {OOS_MONTHS} months")
    md.append(f"- Skip cutoffs with < {MIN_TRAIN_YEARS} years of train data")
    md.append(f"- Gate (re-applied per cutoff): R-PF ≥ {RPF_GATE} in BOTH "
              f"halves of train data AND n ≥ {MIN_N_PER_HALF} per half")
    md.append("- OOS R-PF: each win contributes +planned_rr (1.4 MACD / 1.5 RSI), "
              "each loss contributes -1.0\n")

    md.append("## Per-cutoff results\n")
    md.append("| cutoff | strategy | whitelist | OOS n | wins | WR | R-PF |")
    md.append("|---|---|---|---:|---:|---:|---:|")
    for r in rows:
        wl = ', '.join(r['whitelist']) if r['whitelist'] else '—'
        md.append(f"| {r['cutoff']} | {r['strategy']} | {wl} | "
                  f"{r['oos_n']} | {r['oos_wins']} | "
                  f"{r['oos_wr']:.1f}% | {r['oos_rpf']:.2f} |")

    md.append("\n## Aggregate OOS verdict\n")
    md.append("| strategy | OOS n | wins | losses | WR | R-PF | verdict |")
    md.append("|---|---:|---:|---:|---:|---:|:---:|")
    for strat, agg in aggregate.items():
        verdict = ("PASS" if agg["passes"]
                   else ("FAIL" if agg["n"] >= 10 else "INSUFFICIENT_N"))
        md.append(f"| {strat} | {agg['n']} | {agg['wins']} | {agg['losses']} | "
                  f"{agg['wr']:.1f}% | {agg['rpf']:.3f} | {verdict} |")

    md.append("\n## Honest reading\n")
    rsi_agg = aggregate["rsi_reversal"]
    macd_agg = aggregate["macd_crossover"]
    if rsi_agg["passes"]:
        md.append(f"- **RSI:** OOS R-PF = {rsi_agg['rpf']:.3f} on {rsi_agg['n']} "
                  f"out-of-sample predictions — clears the 1.30 gate. The whitelist "
                  f"selection holds up walk-forward.")
    elif rsi_agg["n"] >= 10:
        md.append(f"- **RSI:** OOS R-PF = {rsi_agg['rpf']:.3f} on {rsi_agg['n']} "
                  f"OOS predictions — FAILS the 1.30 gate. The single-corpus "
                  f"finding (R-PF=1.70 on full corpus) was over-fit; walk-forward "
                  f"shows the EURUSD-RSI edge does not survive when the late half "
                  f"is no longer used to validate the gate selection.")
    else:
        md.append(f"- **RSI:** only {rsi_agg['n']} OOS predictions — insufficient "
                  f"signal cadence for walk-forward to produce a reliable verdict. "
                  f"This is itself a finding: even on a 6-year corpus, EURUSD-RSI "
                  f"fires too rarely to validate cleanly.")

    if macd_agg["passes"]:
        md.append(f"- **MACD:** OOS R-PF = {macd_agg['rpf']:.3f} on {macd_agg['n']} "
                  f"predictions — passes the gate (unexpected; revisit Path B "
                  f"single-corpus result).")
    elif macd_agg["n"] >= 10:
        md.append(f"- **MACD:** OOS R-PF = {macd_agg['rpf']:.3f} on {macd_agg['n']} "
                  f"predictions — FAILS the gate, consistent with the single-corpus "
                  f"finding that no symbol passes the dual-half gate.")
    else:
        md.append(f"- **MACD:** only {macd_agg['n']} OOS predictions reached the "
                  f"whitelist — consistent with the single-corpus finding that "
                  f"no symbol consistently clears the gate.")

    md.append("")
    md.append("## What this means for Phase 7 Step 8\n")
    if rsi_agg["passes"]:
        md.append("- The single-corpus whitelist is OOS-validated. Step 8 "
                  "wiring proceeds with `config/strategy_symbol_whitelist.yaml` "
                  "as the source of truth.")
    else:
        md.append("- The single-corpus whitelist did NOT survive walk-forward "
                  "validation. Building Step 8 wiring on it would ship an "
                  "unvalidated edge. Options:")
        md.append("  1. Accept v3 as production through Phase 9 — defer the "
                  "Phase 7 architecture change.")
        md.append("  2. Look outside the H1 corpus (different timeframe, "
                  "different signal generators) for a strategy with enough "
                  "signal cadence to validate cleanly.")
        md.append("  3. Re-design the gate threshold — current R-PF ≥ 1.30 "
                  "is the documented bar. Lower bars may admit more strategies "
                  "but undermine the project's edge claim.")

    md.append("\n## Cross-references\n")
    md.append("- `docs/research/phase7_path_b_symbol_stratification.md` — single-corpus run")
    md.append("- `docs/research/phase7_step6_meta_labeler_macd.md` — Step 6 FAIL")
    md.append("- `docs/research/phase7_step7_meta_labeler_rsi.md` — Step 7 FAIL")
    md.append("- `data/improvements.db` decisions_log — running record")

    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"\n  ✓ wrote {REPORT_OUT}")

    # ─── decisions_log ───
    rsi_v = "PASS" if rsi_agg["passes"] else ("FAIL" if rsi_agg["n"] >= 10 else "INSUFFICIENT_N")
    macd_v = "PASS" if macd_agg["passes"] else ("FAIL" if macd_agg["n"] >= 10 else "INSUFFICIENT_N")
    try:
        conn = sqlite3.connect(TRACKER_DB)
        conn.execute(
            "INSERT INTO decisions_log (time, category, decision, reason, impact, phase) "
            "VALUES (?,?,?,?,?,?)",
            (
                datetime.now().isoformat(timespec="seconds"),
                "PHASE_7_PATH_B_VALIDATION",
                f"Walk-forward validation: RSI={rsi_v} (R-PF={rsi_agg['rpf']:.3f} on n={rsi_agg['n']}); "
                f"MACD={macd_v} (R-PF={macd_agg['rpf']:.3f} on n={macd_agg['n']}).",
                "Quarterly cutoffs through 2024-2025; whitelist re-derived from "
                "train-only data at each cutoff and applied to next 6 months OOS. "
                "All OOS predictions aggregated for the headline R-PF.",
                f"{'Step 8 (whitelist wiring) green-lit' if rsi_agg['passes'] else 'Step 8 wiring on hold; whitelist not OOS-validated'}",
                7,
            ),
        )
        conn.commit()
        conn.close()
        print("  ✓ decisions_log row appended")
    except Exception as e:
        print(f"  WARN: decisions_log append failed: {e}")

    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
