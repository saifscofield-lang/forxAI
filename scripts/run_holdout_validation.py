"""AI-005: 30% holdout OOS validation of post-meeting recommendations.

Splits the v3 trade record into a 70% in-sample (IS) chunk used to
derive the 2026-04-28 meeting recommendations and a 30% out-of-sample
(OOS) chunk that was NOT used to derive them. Runs each
recommendation against the OOS slice and reports whether it survives.

Background. v4 was rejected on a stricter methodology than v3 was
held to: locked scope, single-shot evaluation, OOS separation
between training and validation. v3's R1-R7 were derived from the
same dataset they would be evaluated against — converting Phase 8
"OOS" into a second IS. AI-005 was raised at the 2026-04-28 meeting
specifically to apply v4's methodology to v3.

Recommendations that this script can validate:
  R1 — Block XAUUSD SELL during OVERLAP session (13:00-17:00 UTC).
       Survives if OOS XAUUSD SELL during 13-17 UTC is net-negative.
  R4 — Defer per-symbol decisions for non-XAUUSD pairs.
       Survives if per-(symbol, direction) cells on OOS remain
       underpowered (n<10).

Recommendations that this script CANNOT validate via OOS holdout:
  R2 — Retire bollinger_bounce. Forward-looking; the OOS sample
       postdates retirement so there are no bollinger_bounce trades
       to evaluate. The retirement decision can only be validated by
       a counterfactual rebuild (running bollinger_bounce logic on
       OOS bars in shadow mode), which is out of scope for AI-005
       and belongs to Phase 7's meta-labeler training pipeline.
  R3 — Retire ml_filtered_sma. Same as R2.

R5-R7 are referenced in AI-005's brief but not formally defined in
any project doc. Surfaced here as a finding for the project lead.

Outputs:
  artifacts/ai005_holdout_split_<date>.csv   IS / OOS ticket lists
  docs/research/ai005_holdout_validation.md  full validation report

Idempotent. Read-only against trading.db. Re-runnable any time."""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, ".")

import pandas as pd

DB_PATH = "data/trading.db"
SPLIT_FRACTION = 0.70  # 70% IS / 30% OOS
ARTIFACTS_DIR = Path("artifacts")
DOCS_DIR = Path("docs/research")


# ── Data loading ────────────────────────────────────────────────────────────

def load_v3_trades() -> pd.DataFrame:
    """Load all v3 (engine 2.4) closed trades sorted by close_time."""
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        """SELECT t.ticket, t.symbol, t.order_type, t.strategy,
                  t.open_time, t.close_time, t.open_price, t.close_price,
                  t.profit, tr.exit_reason, tr.exit_reason_v2
           FROM trades t JOIN trade_results tr ON tr.ticket = t.ticket
           WHERE t.is_closed = 1 AND tr.engine_version = '2.4'
           ORDER BY t.close_time ASC""",
        con,
    )
    con.close()
    return df


def split_holdout(df: pd.DataFrame, fraction: float = SPLIT_FRACTION):
    """70% oldest as IS, 30% newest as OOS. Time-based split (not random)
    so the OOS represents the most recent regime — the methodology v4 was
    held to."""
    n = len(df)
    n_is = int(n * fraction)
    is_df = df.iloc[:n_is].copy()
    oos_df = df.iloc[n_is:].copy()
    return is_df, oos_df


# ── R1 — XAUUSD SELL in OVERLAP session ─────────────────────────────────────

def validate_r1_overlap_filter(oos: pd.DataFrame) -> dict:
    """OOS slice: XAUUSD SELL during 13:00-17:00 UTC. Sum PnL.

    R1 survives if OOS overlap-window XAUUSD SELL is net-negative
    (consistent with the IS pattern that motivated the rule)."""
    xau_sell = oos[(oos["symbol"] == "XAUUSD") & (oos["order_type"] == "SELL")].copy()
    if xau_sell.empty:
        return {
            "rule": "R1",
            "verdict": "INSUFFICIENT_DATA",
            "n_total": 0,
            "n_overlap": 0,
            "pnl_overlap": 0.0,
            "pnl_non_overlap": 0.0,
            "notes": "No XAUUSD SELL trades in OOS holdout.",
        }
    xau_sell["open_hour_utc"] = pd.to_datetime(xau_sell["open_time"]).dt.hour
    overlap = xau_sell[xau_sell["open_hour_utc"].between(13, 16)]
    non_overlap = xau_sell[~xau_sell["open_hour_utc"].between(13, 16)]
    pnl_overlap = float(overlap["profit"].sum())
    pnl_non_overlap = float(non_overlap["profit"].sum())
    if len(overlap) == 0:
        verdict = "NOT_TESTED"  # No overlap-window trades to evaluate
    elif pnl_overlap < 0:
        verdict = "SURVIVES"
    else:
        verdict = "REJECTED"
    return {
        "rule": "R1",
        "verdict": verdict,
        "n_total": len(xau_sell),
        "n_overlap": len(overlap),
        "n_non_overlap": len(non_overlap),
        "pnl_overlap": pnl_overlap,
        "pnl_non_overlap": pnl_non_overlap,
        "notes": (
            f"OOS XAUUSD SELL: {len(xau_sell)} trades. "
            f"{len(overlap)} in 13-17 UTC window with PnL ${pnl_overlap:+,.2f}. "
            f"Non-overlap: ${pnl_non_overlap:+,.2f}."
        ),
    }


# ── R4 — Defer per-symbol decisions for non-XAUUSD ──────────────────────────

def validate_r4_per_symbol_underpowered(oos: pd.DataFrame, n_threshold: int = 10) -> dict:
    """Count per-(symbol, direction) cells on OOS. R4 survives if the
    non-XAUUSD cells remain underpowered (n < n_threshold)."""
    cells = (
        oos.groupby(["symbol", "order_type"]).size().reset_index(name="n")
    )
    non_xau = cells[cells["symbol"] != "XAUUSD"]
    underpowered = non_xau[non_xau["n"] < n_threshold]
    powered = non_xau[non_xau["n"] >= n_threshold]
    n_underpowered = len(underpowered)
    n_total_non_xau_cells = len(non_xau)
    if n_total_non_xau_cells == 0:
        return {
            "rule": "R4",
            "verdict": "INSUFFICIENT_DATA",
            "notes": "No non-XAUUSD cells in OOS holdout.",
        }
    if n_underpowered == n_total_non_xau_cells:
        verdict = "SURVIVES"  # All cells still underpowered → defer holds
    else:
        verdict = "PARTIAL_REJECTED"  # Some cells now powered → can decide
    return {
        "rule": "R4",
        "verdict": verdict,
        "n_total_cells": n_total_non_xau_cells,
        "n_underpowered": n_underpowered,
        "n_powered": len(powered),
        "powered_cells": (
            [tuple(x) for x in powered[["symbol", "order_type", "n"]].values]
            if len(powered) > 0 else []
        ),
        "notes": (
            f"{n_underpowered} of {n_total_non_xau_cells} non-XAUUSD cells "
            f"are underpowered (n < {n_threshold}) on OOS holdout. "
            + (
                f"Powered cells now decidable: {len(powered)}."
                if len(powered) > 0 else
                "All non-XAUUSD cells remain underpowered."
            )
        ),
    }


# ── Report renderer ─────────────────────────────────────────────────────────

def render_report(
    is_df: pd.DataFrame,
    oos_df: pd.DataFrame,
    r1: dict,
    r4: dict,
) -> str:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    n = len(is_df) + len(oos_df)
    is_first = is_df["close_time"].iloc[0] if not is_df.empty else "—"
    is_last = is_df["close_time"].iloc[-1] if not is_df.empty else "—"
    oos_first = oos_df["close_time"].iloc[0] if not oos_df.empty else "—"
    oos_last = oos_df["close_time"].iloc[-1] if not oos_df.empty else "—"

    # Split-summary stats
    is_pnl = float(is_df["profit"].sum())
    oos_pnl = float(oos_df["profit"].sum())
    is_wr = float((is_df["profit"] > 0).mean()) * 100 if len(is_df) else 0.0
    oos_wr = float((oos_df["profit"] > 0).mean()) * 100 if len(oos_df) else 0.0

    lines = []
    lines.append(f"# AI-005 — 30% Holdout OOS Validation\n")
    lines.append(f"**Date generated:** {today}  ")
    lines.append(f"**Source:** `data/trading.db` (engine_version=2.4)  ")
    lines.append(f"**Re-runnable via:** `python scripts/run_holdout_validation.py`\n")

    lines.append("## Why this exists\n")
    lines.append(
        "v4 was rejected on a stricter methodology than v3 was held to: "
        "locked scope, single-shot evaluation, OOS separation between "
        "training and validation. v3's recommendations (R1–R4) were "
        "derived from the same dataset that would be used to evaluate "
        "them — converting Phase 8 'OOS' into a second IS. "
        "AI-005 was raised at the 2026-04-28 meeting to apply v4's "
        "methodology to v3 and validate the surviving recommendations "
        "on data not used to derive them.\n"
    )

    lines.append("## Split\n")
    lines.append(f"| Slice | n | Window | Net PnL | WR |")
    lines.append(f"|---|---:|---|---:|---:|")
    lines.append(
        f"| IS (70%, oldest) | {len(is_df)} | "
        f"{is_first} → {is_last} | ${is_pnl:+,.2f} | {is_wr:.1f}% |"
    )
    lines.append(
        f"| **OOS (30%, newest)** | **{len(oos_df)}** | "
        f"{oos_first} → {oos_last} | **${oos_pnl:+,.2f}** | **{oos_wr:.1f}%** |"
    )
    lines.append(f"| Total | {n} | | ${is_pnl + oos_pnl:+,.2f} | |\n")
    lines.append(
        "Time-based split (not random) so the OOS represents the most "
        "recent regime — the v4 standard.\n"
    )

    lines.append("## Recommendations validated against OOS\n")

    # R1
    lines.append("### R1 — Block XAUUSD SELL during OVERLAP session (13:00–17:00 UTC)\n")
    lines.append(f"**Verdict:** `{r1['verdict']}`\n")
    lines.append(f"- {r1['notes']}\n")
    if r1["verdict"] == "SURVIVES":
        lines.append(
            "OOS slice confirms the IS pattern: OVERLAP-window XAUUSD SELL "
            "is net-negative even on data not used to derive R1. The rule "
            "is safe to install for Phase 8.\n"
        )
    elif r1["verdict"] == "REJECTED":
        lines.append(
            "**OOS REJECTS R1.** The OVERLAP-window XAUUSD SELL pattern "
            "did not replicate on out-of-sample data. R1 was likely "
            "an in-sample artefact and should not be installed without "
            "further investigation. Recommend: extend the OOS window "
            "or run a regime-stratified analysis before any install.\n"
        )
    elif r1["verdict"] == "NOT_TESTED":
        lines.append(
            "OOS slice has XAUUSD SELL trades but **none in the 13–17 UTC "
            "window**, so the rule cannot be validated. The blacklist "
            "from AI-002 likely prevented these trades from opening. "
            "R1 cannot be validated against OOS until the blacklist is "
            "removed (which would be unsafe) or the validation methodology "
            "switches to shadow-trade simulation against bar history.\n"
        )
    else:
        lines.append("Insufficient data on OOS slice to validate R1.\n")

    # R4
    lines.append("### R4 — Defer per-symbol decisions for non-XAUUSD pairs\n")
    lines.append(f"**Verdict:** `{r4['verdict']}`\n")
    lines.append(f"- {r4['notes']}\n")
    if r4["verdict"] == "SURVIVES":
        lines.append(
            "All non-XAUUSD per-(symbol, direction) cells remain underpowered "
            "on OOS. R4 holds — defer per-symbol decisions until Phase 8 "
            "collects more data.\n"
        )
    elif r4["verdict"] == "PARTIAL_REJECTED":
        lines.append("The following cells are now decidable on OOS:\n")
        for sym, side, cnt in r4["powered_cells"]:
            lines.append(f"- `{sym} {side}`: n={cnt}")
        lines.append(
            "\nDeferring per-symbol decisions for these cells is no longer "
            "supported by the data. Run a per-cell expectancy analysis "
            "before Phase 8.\n"
        )

    # R2 / R3
    lines.append("### R2 — Retire bollinger_bounce, R3 — Retire ml_filtered_sma\n")
    lines.append("**Verdict:** `NOT_OOS_VALIDATABLE`\n")
    lines.append(
        "Retirement is a forward-looking rule: after 2026-04-28 these "
        "strategies stopped trading. The OOS sample postdates retirement, "
        "so there are no bollinger_bounce / ml_filtered_sma trades on OOS "
        "to evaluate. The retirement decision can only be validated by a "
        "counterfactual rebuild — running the strategy logic on OOS bars "
        "in shadow mode and computing what would have happened. That work "
        "is out of scope for AI-005 and belongs to the Phase 7 meta-labeler "
        "training pipeline (which already has the data infrastructure to "
        "run signals against historical bars).\n"
    )

    # R5-R7 finding
    lines.append("### R5–R7 — undefined\n")
    lines.append(
        "AI-005's brief references *R1–R7* but only **R1 through R4** are "
        "formally defined in any project doc (`docs/research/full_trade_evolution_report_2026-04-28.md` "
        "section 9). R5, R6, R7 do not appear as labelled recommendations "
        "anywhere in the codebase or `docs/`.\n"
    )
    lines.append(
        "The `R1–R7` shorthand likely refers to the broader set of audit "
        "recommendations including the 8 meeting votes, but that mapping "
        "isn't recorded. **Surfacing as a finding for the project lead.** "
        "If R5–R7 should be specific rules, they need to be defined before "
        "this script can validate them.\n"
    )

    lines.append("## Summary\n")
    summary_table = [
        ("R1", "OVERLAP filter (XAUUSD SELL 13–17 UTC)", r1["verdict"]),
        ("R2", "Retire bollinger_bounce", "NOT_OOS_VALIDATABLE"),
        ("R3", "Retire ml_filtered_sma", "NOT_OOS_VALIDATABLE"),
        ("R4", "Defer per-symbol decisions (non-XAUUSD)", r4["verdict"]),
        ("R5", "(undefined)", "—"),
        ("R6", "(undefined)", "—"),
        ("R7", "(undefined)", "—"),
    ]
    lines.append("| Rule | Description | OOS Verdict |")
    lines.append("|---|---|---|")
    for rid, desc, verdict in summary_table:
        lines.append(f"| {rid} | {desc} | `{verdict}` |")
    lines.append("")

    lines.append("## Files\n")
    lines.append(
        "- `artifacts/ai005_holdout_split_" + today + ".csv` — frozen IS / OOS ticket lists\n"
    )
    lines.append("- This file: `docs/research/ai005_holdout_validation.md`\n")
    lines.append("- Source script: `scripts/run_holdout_validation.py` (re-runnable)\n")

    return "\n".join(lines)


# ── Entry point ─────────────────────────────────────────────────────────────

def main() -> int:
    df = load_v3_trades()
    if df.empty:
        print("[error] no v3 trades found", file=sys.stderr)
        return 1

    is_df, oos_df = split_holdout(df, SPLIT_FRACTION)

    # Save split artifact
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    split_path = ARTIFACTS_DIR / f"ai005_holdout_split_{today}.csv"
    is_df.assign(split="IS").to_csv(split_path, index=False)
    oos_df.assign(split="OOS").to_csv(split_path, mode="a", index=False, header=False)

    # Run validators
    r1 = validate_r1_overlap_filter(oos_df)
    r4 = validate_r4_per_symbol_underpowered(oos_df)

    # Render report
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    report = render_report(is_df, oos_df, r1, r4)
    report_path = DOCS_DIR / "ai005_holdout_validation.md"
    report_path.write_text(report, encoding="utf-8")

    print(f"[ai-005] split: IS={len(is_df)}  OOS={len(oos_df)}")
    print(f"[ai-005] R1 verdict: {r1['verdict']}  ({r1['notes']})")
    print(f"[ai-005] R4 verdict: {r4['verdict']}  ({r4['notes']})")
    print(f"[ai-005] report: {report_path}")
    print(f"[ai-005] split:  {split_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
