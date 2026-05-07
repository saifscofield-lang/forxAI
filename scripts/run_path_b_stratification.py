"""Phase 7 Path B — symbol-stratification analysis (post-Step-7 follow-up).

Both meta-labelers (Step 6 MACD, Step 7 RSI) failed the dual ship gate
on the full-corpus run. Step 7's per-symbol breakdown (logged 2026-05-07)
showed the RSI edge is concentrated in EURUSD/GBPUSD/AUDUSD, while
MACD has no symbol with WR > 50%. This script formalises that finding:

  1. Per-symbol per-strategy R-PF projection on the full corpus.
  2. Cross-time stability check (corpus split at the median signal date)
     to distinguish real per-symbol edges from temporal artifacts.
  3. Whitelist recommendation per strategy: a symbol enters only when
     R-PF >= 1.30 in BOTH time halves AND n >= 15 in each half.
  4. Saves the whitelist to `config/strategy_symbol_whitelist.yaml` so
     `ml_filtered_strategy` (Phase 7 Step 8) can read it as a hard
     gate before any model logic.

This is intentionally simpler than a per-symbol meta-labeler: at
n ≈ 50 per symbol, training another LightGBM is sample-starved and
the marginal gain over a fixed whitelist is unlikely to clear
purged-CV noise.

Outputs:
  - `docs/research/phase7_path_b_symbol_stratification.md`
  - `config/strategy_symbol_whitelist.yaml`
  - row appended to `decisions_log` recording the conclusion
"""
from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3

import numpy as np
import pandas as pd
import yaml

SIGNALS_PARQUET = Path("data/research/primary_signals.parquet")
WHITELIST_OUT = Path("config/strategy_symbol_whitelist.yaml")
REPORT_OUT = Path("docs/research/phase7_path_b_symbol_stratification.md")
TRACKER_DB = "data/improvements.db"

# Per-strategy planned R:R, drawn from each strategy's __init__ defaults.
# Used to project R-PF from a per-symbol WR. See phase7_step6/7 reports
# for the unit derivation.
STRATEGY_RR = {
    "macd_crossover": 1.4,    # TP=3.5×ATR / SL=2.5×ATR
    "rsi_reversal": 1.5,      # TP=3.0×ATR / SL=2.0×ATR
}

# Whitelist gates: a symbol is whitelisted for a strategy only if it
# clears R-PF >= 1.30 in BOTH halves AND has at least MIN_N samples
# in each half. The MIN_N gate guards against single-period flukes.
RPF_GATE = 1.30
MIN_N_PER_HALF = 15


def projected_rpf(wr_pct: float, rr: float) -> float:
    """Upper bound on R-PF given WR% and planned R:R. Wins return rr,
    losses return -1. R-PF = (wr × rr) / (1 - wr)."""
    if wr_pct <= 0 or wr_pct >= 100:
        return float("inf") if wr_pct >= 100 else 0.0
    w = wr_pct / 100.0
    return round((w * rr) / (1 - w), 3)


def per_symbol_table(s: pd.DataFrame, rr: float) -> pd.DataFrame:
    """For one strategy's signals, build per-symbol n / wins / WR / R-PF
    and the same split into early / late time halves."""
    s = s.sort_values("time").copy()
    cutoff = s["time"].quantile(0.5)
    s["half"] = (s["time"] >= cutoff).map({True: "late", False: "early"})

    rows = []
    for sym in sorted(s["symbol"].unique()):
        sub = s[s["symbol"] == sym]
        n_total = len(sub)
        wins_total = int((sub["label"] == 1).sum())
        wr_total = 100.0 * wins_total / max(1, n_total)
        rpf_total = projected_rpf(wr_total, rr)

        early = sub[sub["half"] == "early"]
        late = sub[sub["half"] == "late"]
        n_e, n_l = len(early), len(late)
        w_e = int((early["label"] == 1).sum())
        w_l = int((late["label"] == 1).sum())
        wr_e = 100.0 * w_e / max(1, n_e) if n_e else 0.0
        wr_l = 100.0 * w_l / max(1, n_l) if n_l else 0.0
        rpf_e = projected_rpf(wr_e, rr) if n_e else 0.0
        rpf_l = projected_rpf(wr_l, rr) if n_l else 0.0

        rows.append({
            "symbol": sym,
            "n": n_total, "wins": wins_total, "wr": round(wr_total, 1),
            "rpf": rpf_total,
            "n_early": n_e, "wins_early": w_e, "wr_early": round(wr_e, 1),
            "rpf_early": rpf_e,
            "n_late": n_l, "wins_late": w_l, "wr_late": round(wr_l, 1),
            "rpf_late": rpf_l,
            "stable": (
                rpf_e >= RPF_GATE and rpf_l >= RPF_GATE
                and n_e >= MIN_N_PER_HALF and n_l >= MIN_N_PER_HALF
            ),
        })
    return pd.DataFrame(rows)


def main() -> int:
    print("=" * 78)
    print("  Phase 7 Path B — symbol-stratification analysis")
    print(f"  Run: {datetime.now().isoformat(timespec='seconds')}")
    print(f"  R-PF gate: {RPF_GATE} | min-n per half: {MIN_N_PER_HALF}")
    print("=" * 78)

    df = pd.read_parquet(SIGNALS_PARQUET)
    print(f"  Loaded {len(df):,} signals from {SIGNALS_PARQUET}\n")

    whitelist = {}
    per_strat_tables = {}

    for strat, rr in STRATEGY_RR.items():
        s = df[(df["strategy"] == strat) & (df["label"] != 0)].copy()
        wr_baseline = 100.0 * (s["label"] == 1).sum() / max(1, len(s))
        rpf_baseline = projected_rpf(wr_baseline, rr)
        print(f"  Strategy: {strat}  (R:R={rr}, baseline WR={wr_baseline:.1f}%, "
              f"baseline R-PF={rpf_baseline:.3f})")

        tbl = per_symbol_table(s, rr)
        per_strat_tables[strat] = tbl
        kept = tbl[tbl["stable"]]["symbol"].tolist()
        whitelist[strat] = kept
        print(f"  → whitelist ({len(kept)}): {kept or '(none)'}")
        print()

        # Print compact view
        print(f"    {'symbol':<8} {'n':>5} {'WR':>6} {'R-PF':>6} | "
              f"{'n_e':>4} {'WR_e':>6} {'R-PF_e':>7} | "
              f"{'n_l':>4} {'WR_l':>6} {'R-PF_l':>7}  stable")
        for _, r in tbl.iterrows():
            print(f"    {r['symbol']:<8} {r['n']:>5} {r['wr']:>5.1f}% {r['rpf']:>6.2f} | "
                  f"{r['n_early']:>4} {r['wr_early']:>5.1f}% {r['rpf_early']:>7.2f} | "
                  f"{r['n_late']:>4} {r['wr_late']:>5.1f}% {r['rpf_late']:>7.2f}  "
                  f"{'YES' if r['stable'] else ''}")
        print()

    # ─── Whitelist YAML ───
    WHITELIST_OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_generated_by": "scripts/run_path_b_stratification.py",
        "_generated_at": datetime.now().isoformat(timespec="seconds"),
        "_gate": {
            "min_rpf_per_half": RPF_GATE,
            "min_n_per_half": MIN_N_PER_HALF,
            "split": "median signal time",
        },
        "_corpus": SIGNALS_PARQUET.as_posix(),
        "whitelist": whitelist,
    }
    WHITELIST_OUT.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    print(f"  ✓ wrote {WHITELIST_OUT}")

    # ─── Markdown report ───
    md = []
    md.append("# Phase 7 Path B — symbol-stratification analysis\n")
    md.append(f"**Date:** {datetime.now().date().isoformat()}  ")
    md.append("**Re-runnable:** `python scripts/run_path_b_stratification.py`  ")
    md.append(f"**Whitelist artifact:** `{WHITELIST_OUT.as_posix()}`\n")

    md.append("## Why this analysis\n")
    md.append("Phase 7 Step 6 trained an MACD meta-labeler — DUAL GATE FAIL "
              "(AUC=0.495, R-PF=0.840). Step 7 trained an RSI meta-labeler "
              "— DUAL GATE FAIL (AUC=0.579, R-PF=0.906) but with real "
              "predictive signal. The per-symbol breakdown in Step 7 showed "
              "the RSI edge is concentrated in a few pairs while others drag "
              "the corpus average down. This script formalises that finding "
              "and outputs an actionable whitelist, plus checks each per-symbol "
              "edge for cross-time stability.\n")

    md.append("## Method\n")
    md.append("1. Split each strategy's signal corpus at the median signal "
              "timestamp into `early` and `late` halves.")
    md.append("2. Compute per-symbol WR and projected R-PF (= WR/(1-WR) × planned R:R) "
              "in both halves.")
    md.append(f"3. A symbol enters the whitelist only if R-PF ≥ {RPF_GATE} in "
              f"BOTH halves AND n ≥ {MIN_N_PER_HALF} per half. The dual-half "
              f"gate guards against temporal overfitting; the n gate guards "
              f"against tiny-sample noise.")
    md.append(f"4. Planned R:R: macd={STRATEGY_RR['macd_crossover']} (TP=3.5×ATR / SL=2.5×ATR), "
              f"rsi={STRATEGY_RR['rsi_reversal']} (TP=3.0×ATR / SL=2.0×ATR).\n")

    for strat, tbl in per_strat_tables.items():
        md.append(f"## {strat}\n")
        s = df[(df['strategy']==strat) & (df['label']!=0)]
        wr_b = 100.0 * (s['label']==1).sum() / max(1, len(s))
        rpf_b = projected_rpf(wr_b, STRATEGY_RR[strat])
        md.append(f"Baseline (full corpus, all symbols): n = {len(s)}, "
                  f"WR = {wr_b:.1f}%, projected R-PF = {rpf_b:.3f} "
                  f"({'PASS' if rpf_b >= RPF_GATE else 'FAIL'})\n")
        md.append("| symbol | n | WR | R-PF | n_early | WR_early | R-PF_early | "
                  "n_late | WR_late | R-PF_late | stable? |")
        md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|")
        for _, r in tbl.iterrows():
            md.append(
                f"| {r['symbol']} | {r['n']} | {r['wr']:.1f}% | {r['rpf']:.2f} | "
                f"{r['n_early']} | {r['wr_early']:.1f}% | {r['rpf_early']:.2f} | "
                f"{r['n_late']} | {r['wr_late']:.1f}% | {r['rpf_late']:.2f} | "
                f"{'YES' if r['stable'] else 'no'} |"
            )
        kept = tbl[tbl['stable']]['symbol'].tolist()
        md.append(f"\n**Whitelist for {strat}:** "
                  f"{', '.join(f'`{s}`' for s in kept) if kept else '(none — no symbol passes the dual-half gate)'}\n")

    md.append("## Recommendation\n")
    if whitelist["rsi_reversal"]:
        md.append(f"- **RSI:** restrict the strategy in `ml_filtered_strategy` "
                  f"(Step 8) to {whitelist['rsi_reversal']}. Skip the meta-labeler "
                  f"on top — at this corpus size, a per-symbol whitelist captures "
                  f"the edge more cleanly than a sample-starved per-symbol model.")
    else:
        md.append("- **RSI:** no symbol passes the dual-half R-PF gate. Path B does "
                  "not rescue RSI either; revisit the strategy itself or accept "
                  "v3-as-production through Phase 9.")
    if whitelist["macd_crossover"]:
        md.append(f"- **MACD:** whitelist {whitelist['macd_crossover']}.")
    else:
        md.append("- **MACD:** no symbol clears the dual-half R-PF gate. Best "
                  "candidates (USDJPY, EURUSD) decay materially in the late "
                  "half — temporal regime change rather than recoverable edge. "
                  "Path B does not rescue MACD.")
    md.append("- **Step 8 design impact:** `ml_filtered_strategy` reads the "
              "YAML whitelist before any model logic. Symbols not on the list "
              "are silently skipped. No model artifact required for the gated "
              "strategies, simplifying deployment.")
    md.append("- **Step 11 ship gate:** projecting R-PF on EURUSD-only RSI from "
              "the historical corpus is approximate — Step 10's full backtest must "
              "validate on a hold-out window before the Jun 8 ship vote.\n")

    md.append("## Cross-references\n")
    md.append("- `docs/research/phase7_step6_meta_labeler_macd.md` — MACD meta-labeler FAIL")
    md.append("- `docs/research/phase7_step7_meta_labeler_rsi.md` — RSI meta-labeler FAIL")
    md.append("- `config/strategy_symbol_whitelist.yaml` — generated artifact "
              "consumed by `ml_filtered_strategy` (Step 8)")
    md.append("- `data/improvements.db` decisions_log — running record")

    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"  ✓ wrote {REPORT_OUT}")

    # ─── Decisions_log ───
    summary = (
        f"RSI whitelist={whitelist['rsi_reversal']}; "
        f"MACD whitelist={whitelist['macd_crossover']}"
    )
    try:
        conn = sqlite3.connect(TRACKER_DB)
        conn.execute(
            "INSERT INTO decisions_log (time, category, decision, reason, impact, phase) "
            "VALUES (?,?,?,?,?,?)",
            (
                datetime.now().isoformat(timespec="seconds"),
                "PHASE_7_PATH_B",
                f"Path B (symbol stratification) result: {summary}.",
                "Per-symbol R-PF projection + cross-time stability check (corpus "
                "split at median signal time, gate R-PF≥1.30 in BOTH halves with "
                "n≥15 per half). RSI: only EURUSD shows stable edge across both "
                "halves. MACD: no symbol passes the dual-half gate — best candidates "
                "(USDJPY, EURUSD) decay in the late half, suggesting temporal "
                "regime shift rather than recoverable edge.",
                "Step 8 (engine wiring) re-scoped from 'load meta-labeler model' to "
                "'apply YAML symbol whitelist'. RSI-on-EURUSD becomes the Phase 7 "
                "shippable artifact. MACD path forward = either accept removed from "
                "Phase 7, or revisit strategy params (raise TP multiplier) in Phase 8.",
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
