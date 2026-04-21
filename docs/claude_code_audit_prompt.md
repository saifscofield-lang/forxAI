# Claude Code Prompt — Comprehensive System Audit & Data Collection

> **How to use this file:**
> Copy the entire prompt block below (Section A) and paste it into Claude Code in your `D:\forexAI\` project. Claude Code will audit the system, collect all per-version data from logs, and produce a single structured output file (`audit_report.md`) that you bring back here for evaluation.

---

## A. PROMPT TO PASTE INTO CLAUDE CODE

```
You are performing a COMPREHENSIVE SYSTEM AUDIT of this forex AI project. The goal is
to collect all per-version performance data from logs, backtests, and code, then save
the results in a single structured file that a human reviewer will evaluate against a
weighted multi-criteria framework.

DO NOT evaluate, grade, or judge the system yourself. Your job is to COLLECT and
ORGANIZE data faithfully. The reviewer will do the evaluation.

================================================================================
PART 1 — DISCOVERY (map the project before extracting anything)
================================================================================

1. Read CLAUDE.md and any README files to understand project structure.

2. List all version-related artifacts:
   - Code folders or branches named v1, v2, v3, v4 (or equivalent)
   - Log directories, backtest output folders, results/, reports/, archive/
   - Any changelog, CHANGELOG.md, VERSION, or release notes
   - docs/v4_framework.md and docs/research/research.rar (unpack the rar if needed)

3. Produce a short "project map" at the top of the report: folder tree (2 levels deep),
   the file types found, and the time range covered by the logs.

4. If the version boundaries are unclear from folder names, infer them from:
   - Git history (git log --all --oneline, tags, branch names)
   - Timestamps on log files
   - Config changes (strategy parameters, timeframe, indicators)
   Document how you inferred each boundary.

================================================================================
PART 2 — PER-VERSION DATA EXTRACTION
================================================================================

For EACH version (v1, v2, v3, and v4 if it has run any backtest), extract:

A) METADATA
   - Version label
   - Start date and end date of the version's active period
   - Core change introduced vs the previous version (one line: indicator swap,
     timeframe change, stop-loss logic, risk sizing, etc.)
   - Data source (live trading? paper? backtest on which dataset?)
   - Instruments traded (pairs/symbols)
   - Timeframe (M15, H1, H4, D1, etc.)
   - Starting capital and position-sizing rule

B) TRADE LOG (if available)
   - Parse all trade records from logs/CSVs/databases
   - For each trade: entry time, exit time, symbol, direction, entry price, exit price,
     size, PnL (absolute and %), reason for exit (TP/SL/manual/timeout)
   - Save the full trade log per version as CSV under artifacts/

C) AGGREGATE METRICS (compute from trade log, OR extract from existing reports)
   - Total trades
   - Winning trades / losing trades
   - Win rate (%)
   - Total net PnL (absolute currency and % of starting capital)
   - Average win / average loss
   - Risk/Reward ratio (avg win / avg loss)
   - Profit factor (gross profit / gross loss)
   - Max drawdown (absolute and %)
   - Longest losing streak
   - Sharpe ratio (if daily/periodic returns are available; state period used)
   - Sortino ratio (if computable)
   - Exposure time (% of period in market)

D) ASSUMPTIONS & GAPS
   - Any metric you could not compute → say WHY (missing data, ambiguous log format, etc.)
   - Any guess or interpolation → flag it explicitly with [ASSUMPTION: ...]

================================================================================
PART 3 — v4 READINESS CHECK (if v4 code exists but has not fully run)
================================================================================

Report the current state of v4:
   - Files present, entry points, dependencies
   - Is ccxt integration implemented? Which exchanges configured?
   - Are BTC/ETH/SOL the targets? Any others?
   - Backtest window configured (start/end dates)?
   - Out-of-sample split implemented? (train/test ratio)
   - Transaction cost model present? (fees + slippage values)
   - Benchmark comparison (vs buy-and-hold BTC) implemented?
   - What is BLOCKING v4 from producing its first backtest result?

================================================================================
PART 4 — OUTPUT FORMAT (strict — do not deviate)
================================================================================

Create the file: D:\forexAI\docs\audit_report.md

Use EXACTLY this structure:

    # ForexAI — System Audit Report
    *Generated: <YYYY-MM-DD>*
    *Auditor: Claude Code (data collection only — no evaluation)*

    ## 1. Project Map
    <folder tree, file inventory, time range covered>

    ## 2. Version Boundaries
    | Version | Start date | End date | How boundary was determined |
    |---|---|---|---|
    ...

    ## 3. Per-Version Data

    ### 3.1 v1
    **Metadata:** ...
    **Core change vs prior:** (none — baseline)
    **Aggregate metrics:**
    | Metric | Value |
    |---|---|
    | Total trades | ... |
    | Win rate | ... |
    | Net PnL | ... |
    | Avg R:R | ... |
    | Profit factor | ... |
    | Max drawdown | ... |
    | Sharpe | ... |
    | Exposure time | ... |

    **Trade log location:** artifacts/v1_trades.csv
    **Gaps / assumptions:** ...

    ### 3.2 v2
    (same structure)

    ### 3.3 v3
    (same structure)

    ### 3.4 v4 (if applicable)
    (same structure, plus readiness section from Part 3)

    ## 4. Cross-Version Comparison
    | Metric | v1 | v2 | v3 | v4 |
    |---|---|---|---|---|
    ...

    ## 5. v4 Readiness Summary
    <bullet list of what's ready, what's blocking>

    ## 6. Data Quality Notes
    <anything the reviewer must know before trusting the numbers — missing logs,
    inconsistent formats, time gaps, suspected bugs in older logging code, etc.>

    ## 7. Files Produced
    - docs/audit_report.md (this file)
    - artifacts/v1_trades.csv
    - artifacts/v2_trades.csv
    - artifacts/v3_trades.csv
    - artifacts/v4_backtest_trades.csv (if applicable)
    - any other supporting files

================================================================================
RULES
================================================================================

- Use ENGLISH throughout the report.
- Do NOT fabricate numbers. If data is missing, say "NOT AVAILABLE" and explain.
- Do NOT rate the system as "good" or "bad". Collect and present only.
- Show your work: list the exact files/logs you read to derive each metric.
- If you need to install a package (pandas, python-docx, etc.), do it and note it.
- If a log file is huge, sample or aggregate — do not dump raw logs into the report.
- All dates in ISO format (YYYY-MM-DD).
- All PnL in the account's base currency AND as % of starting capital.
- When finished, print a short summary to the terminal: how many versions covered,
  total trades extracted, and the path to audit_report.md.

Begin with Part 1 now.
```

---

## B. What to Do After Claude Code Finishes

1. Claude Code will create `D:\forexAI\docs\audit_report.md` and supporting CSV files in `D:\forexAI\artifacts\`.
2. **Upload `audit_report.md` to this chat** (and the CSV files if small enough).
3. I will then:
   - Apply the weighted scoring (PnL 30%, R/R 20%, Sharpe 20%, Win Rate 15%, Drawdown 15%) to each version
   - Compute the improvement curve (v1 → v2 → v3 → v4)
   - Give a final verdict on the **latest version only** (not the mixed historical average)
   - Produce a go / no-go recommendation for deploying real capital on v4

---

## C. If Claude Code Asks Questions

It probably will. Typical questions and recommended answers:

| Likely question | Recommended answer |
|---|---|
| *"Which folder contains v1 logs?"* | Tell it the actual path, or say *"search the whole project and infer from timestamps"* |
| *"Starting capital?"* | Give the real number you used, e.g. *"$10,000 per version"* |
| *"Base currency?"* | Tell it (USD, EUR, etc.) |
| *"Should I unpack research.rar?"* | **Yes** — if it has relevant logs |
| *"Git history goes back only to v2 — how to reconstruct v1?"* | Say *"use log file timestamps and any commit messages available; flag gaps honestly"* |

---

## D. Why This Approach

- **Separation of concerns:** Claude Code has direct filesystem access to your project — it collects data faithfully. I have the evaluation framework — I judge fairly.
- **No mixed-version averaging:** the report structure forces per-version isolation.
- **Auditability:** every number traces back to a source file listed in the report.
- **Reproducibility:** if you run v4 later, Claude Code can re-run the same audit and the report stays comparable.

---

*This prompt was designed to produce evaluation-ready data — not opinions.*
