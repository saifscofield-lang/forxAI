# Comprehensive Trade Analysis Prompt — Meeting-Ready Edition

**Purpose:** Produce a defensible, evidence-based trade-by-trade analysis across all versions (v1, v2, v3) that can serve as the authoritative reference for the 2026-04-28 v3 go/no-go meeting.

**Target output quality:** Institutional-grade. Every recommendation must trace to specific trade IDs and statistical evidence. No opinions, no summaries without data, no speculation.

**How to use this file:**
Copy the entire prompt block below (between the `===` markers) and paste it into Claude Code in the `D:\forexAI\` project.

---

## THE PROMPT

===

```
COMPREHENSIVE TRADE-BY-TRADE EVOLUTION ANALYSIS
Meeting-ready diagnostic for 2026-04-28 v3 go/no-go decision.

================================================================================
MISSION
================================================================================

Produce an evidence-based, decision-grade analysis covering every trade across
v1 (OLD), v2 (TRANSITION), and v3 (STABLE). The output must be defensible in
a go/no-go meeting — every claim traces to specific trade IDs, every
recommendation cites statistical evidence, no speculation without data.

This is NOT a summary. This is the authoritative reference document. Size
expectation: 20-30 pages printed.

================================================================================
OPERATING PRINCIPLES (non-negotiable)
================================================================================

1. FULL COVERAGE — every closed trade in the database is included. No sampling.

2. EVIDENCE CHAIN — every recommendation in section 10 must reference:
   (a) specific trade IDs, (b) trade count, (c) statistical test where
   applicable, (d) cross-version consistency check.

3. HONEST UNCERTAINTY — where sample size is too small for a conclusion, say
   so explicitly. Flag findings with fewer than 10 trades as "insufficient
   sample" and do not make recommendations from them.

4. NO CODE CHANGES — this is diagnostic only. All decisions happen in the
   2026-04-28 meeting. Do not apply fixes, do not modify configs, do not
   edit strategy code.

5. VERSION TREATMENT:
   - v1 (OLD, ~132 trades): ANALYZE FULLY but label every v1-only finding
     as "context only — data polluted by lot sizes 2-10 and absent risk
     controls. Do not base decisions on v1 alone."
   - v2 (TRANSITION, ~46 trades): ANALYZE FULLY but label as "construction
     zone — 13 config changes in 10 days, segmentation log marks as invalid
     for evaluation. Use for pattern detection only, not decisions."
   - v3 (STABLE, ~68+ trades): AUTHORITATIVE — recommendations must be
     supported by v3 evidence. v1/v2 can reinforce but not substitute.

6. STATISTICAL DISCIPLINE:
   - Report win rate with its 95% confidence interval using Wilson score.
   - For any pattern claim, compute the p-value vs random (binomial test or
     Fisher's exact for 2x2 contingency).
   - Flag any claim based on <10 trades as "UNDERPOWERED".
   - Do not call something "statistically significant" if p > 0.05.

================================================================================
DATA SOURCES (verify all present before starting)
================================================================================

Required:
- data/ml_training/trades.csv (252 rows, primary trade log)
- data/ml_training/trade_results.csv (246 rows, 118 cols with ML features)
- data/ml_training/signal_logs.csv (pre-filter signals)
- data/ml_training/indicator_snapshots.csv (RSI, ATR, MA values per scan)
- data/ml_training/market_contexts.csv (regime, session, trend at signal time)
- data/ml_training/scan_details.csv (crossover flags, rejection reasons)
- data/ml_training/account_snapshots.csv (balance/equity over time)
- data/trading.db :: shadow_signals (parallel shadow predictions)
- data/trading.db :: Trade table (live engine trades)
- data/improvements.db :: data_segmentation_log (version boundaries)
- data/improvements.db :: phase_steps, improvements_log (engineering changes)

If any file is missing, STOP and report. Do not proceed with partial data.

================================================================================
PART 1 — PER-TRADE ENRICHMENT (produces the master dataset)
================================================================================

For every closed trade, build a row in artifacts/all_trades_enriched.csv with
the following columns. Where a field cannot be populated (e.g., ML confidence
for v1 trades before ML was added), write "NOT_AVAILABLE" and the reason.

IDENTITY
- trade_id (primary key)
- version (v1 / v2 / v3, from data_group; if NULL, infer from
  engine_version + open_time per audit rule)
- engine_version (2.0 / 2.1 / 2.2 / 2.3 / 2.4)
- symbol
- direction (BUY / SELL)

TIMING
- open_time_utc (ISO 8601)
- close_time_utc (ISO 8601)
- hold_duration_minutes
- session_at_entry (Asian / London / NY / London-NY-Overlap / Off-hours)
- day_of_week (Mon..Fri, Sat/Sun flagged)
- hour_of_day_utc

PRICES & SIZE
- entry_price
- exit_price
- stop_loss
- take_profit
- lot_size
- sl_distance_pips
- tp_distance_pips
- planned_rr (tp_distance / sl_distance)
- realized_rr (actual pnl / risked amount)

SIGNAL CONTEXT (join from signal_logs.csv on timestamp+symbol)
- strategy_name (which strategy fired — Stop Hunt / Breakout / RSI-Reversal / etc.)
- signal_score (raw score at entry)
- ml_prediction (BUY / SELL / NO_TRADE)
- ml_confidence_pct
- ml_class_probs (dict of BUY/SELL/NO probabilities)

MARKET CONTEXT (join from indicator_snapshots.csv + market_contexts.csv)
- rsi_at_entry
- atr_at_entry
- atr_pct_of_price
- h1_trend (UP / DOWN / SIDEWAYS)
- h4_trend (UP / DOWN / SIDEWAYS)
- trend_alignment (WITH_H4 / AGAINST_H4 / NEUTRAL)
- regime_at_entry (from regime detector if v2.1+)
- volatility_bucket (LOW / MEDIUM / HIGH based on ATR percentile)

FILTER STATE AT ENTRY (reconstruct from engine_version + scan_details)
- atr_filter_active (bool)
- atr_filter_passed (bool)
- session_filter_active (bool)
- session_filter_passed (bool)
- news_block_active (bool)
- ml_filter_active (bool)
- ml_filter_passed (bool)
- xau_blacklist_active (bool) — only True from v2.4
- any_filter_overridden (bool + which one)

OUTCOME
- pnl_absolute_usd
- pnl_pct_of_account_at_open
- exit_reason (TP_HIT / SL_HIT / MANUAL / TIMEOUT / REVERSE_SIGNAL)
- mfe_pips (max favorable excursion)
- mae_pips (max adverse excursion)
- was_profitable (bool)
- was_big_loss (bool, |pnl| > 2x avg v3 loss)
- was_big_win (bool, |pnl| > 2x avg v3 win)

SHADOW CROSS-CHECK (if shadow row exists within ±5 min)
- shadow_predicted_direction
- shadow_agreed_with_trade (bool)
- shadow_predicted_outcome (WIN / LOSS / UNKNOWN)
- divergence_note (if shadow disagreed, what did it say)

SAVE: artifacts/all_trades_enriched.csv

Also save:
- artifacts/data_completeness_report.csv — for each column above, what % of
  trades have real data vs NOT_AVAILABLE, broken down by version.

================================================================================
PART 2 — PIVOTED SUMMARY DATASETS
================================================================================

Build these for downstream analysis and charting:

A) artifacts/summary_by_version_symbol.csv
   columns: version, symbol, trades, wins, losses, wr, wr_ci_low, wr_ci_high,
            avg_win, avg_loss, rr, pf, total_pnl, max_dd_contribution

B) artifacts/summary_by_version_symbol_direction.csv
   Same as A but split by direction (BUY/SELL separately).

C) artifacts/summary_by_version_strategy.csv
   Same columns, split by strategy_name.

D) artifacts/summary_by_session.csv
   Win rate and PnL by (version, session, symbol).

E) artifacts/summary_by_trend_alignment.csv
   Win rate by (version, symbol, trend_alignment).

F) artifacts/summary_by_ml_confidence_bucket.csv
   For v2.3+ only. Buckets: <40%, 40-60%, 60-80%, >80%. Report trades, WR,
   avg PnL per bucket.

G) artifacts/filter_effectiveness.csv
   For each filter in each version: signals rejected, of which
   would-have-been-profitable (from shadow), net-value-added.

================================================================================
PART 3 — THE REPORT (docs/research/full_trade_evolution_report.md)
================================================================================

Structure the report exactly as follows. Use markdown headers as shown.

# ForexAI — Full Trade Evolution Report
*Generated: [date]*
*Scope: all closed trades, v1 through v3*
*Authority level: authoritative for v3 findings; context-only for v1/v2 findings*

## 1. Executive Summary
- Single-paragraph project-wide status.
- 3 most important findings (each with trade count and version coverage).
- Top 3 recommendations for the 04-28 meeting (each one-line, details in §10).

## 2. Project-wide Aggregates
- Trade count matrix: version × symbol (table)
- Trade count matrix: version × strategy (table)
- Trade count matrix: version × direction (table)
- Net PnL per version (from audit, restated)
- Account equity curve PNG (from account_snapshots.csv) with version
  boundaries annotated. Save to docs/research/charts/equity_curve.png.

## 3. Per-Symbol Deep Dive
One subsection per symbol actually traded. Order by total trade count descending.

### 3.X [SYMBOL]
#### 3.X.1 Overview table
| Version | Trades | BUY | SELL | WR | WR 95% CI | Avg Win | Avg Loss | R:R | PF | Net PnL |

#### 3.X.2 Direction split
- BUY stats across versions
- SELL stats across versions
- Is one direction systematically worse? (cite p-value)

#### 3.X.3 Persistent patterns
- List of patterns that appear in v1 AND v2 AND v3.
- Each pattern: description, trade count per version, combined stats.
- Examples to look for:
  * Symbol loses in counter-trend trades across all versions
  * Symbol's losses concentrated in one session across all versions
  * Symbol's SL is systematically hit at the same % distance

#### 3.X.4 Best and worst trade
Full context dump for the single best and single worst trade of this symbol
in v3 specifically. Include every column from Part 1.

#### 3.X.5 v3 viability verdict
Based ONLY on v3 data:
- Should this symbol continue trading as-is? (YES / NO / CONDITIONAL)
- If CONDITIONAL, what condition? (e.g., "BUY only", "skip London session")
- Cite trade count and statistical evidence.

## 4. Per-Strategy Deep Dive
One subsection per distinct strategy_name found in the data.

### 4.X [STRATEGY_NAME]
#### 4.X.1 Overview
- First version where this strategy appeared
- Total signals generated (from signal_logs.csv)
- Signals that became trades (post-filter)
- Signal-to-trade conversion rate per version (shows filter impact)

#### 4.X.2 Performance by version
| Version | Signals | Trades | WR | Avg PnL | Net PnL |

#### 4.X.3 Symbol affinity
- Which symbols does this strategy work on? (WR > 55% in v3 with ≥ 10 trades)
- Which symbols does it fail on? (WR < 45% in v3 with ≥ 10 trades)
- Flag "UNDERPOWERED" for symbol combos with < 10 trades.

#### 4.X.4 Evolution
- Did this strategy's performance improve, stay flat, or degrade across versions?
- Any specific engineering change that correlates with a performance shift?

#### 4.X.5 v3 verdict
- Keep / modify / retire? Cite evidence.

## 5. Context Analysis
Project-wide breakdowns (all versions combined, flagged per version where
meaningful).

### 5.1 By session
Table: session × (version × WR × avg PnL). Is one session systematically
worse? Is this consistent across versions?

### 5.2 By day of week
Same structure. Does Friday behave differently? Monday?

### 5.3 By trend alignment
With-H4 vs Against-H4. Report WR and avg PnL. Is counter-trend trading
profitable in this system?

### 5.4 By ATR regime
Low / Medium / High volatility buckets. Does the system degrade in high
volatility?

### 5.5 By ML confidence (v2.3+ only)
Bucketed analysis. Does higher ML confidence correlate with higher WR?
(If not, ML is not adding value and should be investigated.)

## 6. Filter Effectiveness (v2.3+ only)
For each filter active in v3:
- Total signals rejected by this filter
- Of those rejected, what % would have been profitable (via shadow_signals)?
- Net value: (rejected_losses_avoided) - (rejected_wins_missed)
- Verdict: filter adds value / filter costs value / inconclusive

If any filter has NEGATIVE net value in v3, flag it as a removal candidate
for the 04-28 meeting.

## 7. Evolution Narrative
Chronological story (1-2 pages max):
- v1 era: what the system did, why it appeared to work, what was missing.
- v2 era: what was attempted, what broke, key incidents from improvements_log.
- v3 era: what stabilized, what the current failure modes are, what changed
  from v2 to v3 specifically.

For each major engineering change (from improvements_log or phase_steps),
note whether trade metrics shifted in the subsequent 20+ trades.

## 8. Case Studies — Worst 10 Trades (v3 only)
For each, full context from Part 1. Plus:
- What filter SHOULD have caught this? (if any existed)
- Has any later change addressed this failure mode?
- If not, what would need to change?

## 9. Case Studies — Best 10 Trades (v3 only)
Same structure. Plus:
- Is this pattern repeatable? (look for similar context in signal_logs.csv
  that did NOT become trades — how many and why)

## 10. Persistent Issues & Recommendations
The highest-value section. Every item here must meet this bar:
- Backed by ≥ 10 v3 trades, OR
- Backed by ≥ 5 v3 trades AND consistent pattern in v1 AND v2

For each recommendation, provide:
- CLAIM: one-sentence description.
- EVIDENCE: trade IDs, counts per version, statistical test result.
- CROSS-VERSION: does this pattern appear in v1? v2? v3?
- PROPOSED ACTION: what specific config/code change would test this?
- EXPECTED IMPACT: if we applied this change to v3, projected PnL improvement
  based on the excluded trades' realized losses.
- RISK: what could go wrong if we apply this?
- VOTE_REQUIRED: (YES/NO) is this a meeting-level decision or operator-level?

Categories of recommendations to check for:
- Symbol-level blacklists (entire symbol off)
- Symbol+direction blacklists (e.g., "XAUUSD SELL off")
- Strategy-level retirements
- Strategy+symbol combinations to disable
- Session-level restrictions
- Filter threshold adjustments
- New filter candidates (e.g., "skip when ATR > X")

## 11. Methodology & Caveats
- How version boundaries were determined.
- How joins across CSV files were performed (by timestamp ± N seconds).
- Which fields were NOT_AVAILABLE and for which versions.
- Known data quality issues (from audit_report.md Section 6).
- What this analysis CANNOT answer (e.g., "will v3 be profitable over the
  next 30 days" — no amount of historical analysis answers that).

## 12. Appendix — Reference Tables
- Full Part 2 CSV files referenced here with download paths.
- Chart gallery.
- Query snippets for reproducing key numbers.

================================================================================
PART 4 — CHARTS (minimum set)
================================================================================

Save to docs/research/charts/

Required:
1. equity_curve.png — project-wide equity over time with version boundaries
2. pnl_by_symbol_by_version.png — grouped bar chart
3. wr_by_symbol_by_version.png — grouped bar chart with CI error bars
4. direction_split_by_symbol.png — BUY vs SELL PnL per symbol (v3 only)
5. strategy_performance_heatmap.png — strategy × symbol, color = v3 WR
6. ml_confidence_calibration.png — predicted vs realized WR by bucket (v2.3+)
7. filter_cascade.png — sankey or bar showing signals → filters → trades per version
8. session_heatmap.png — session × symbol, color = v3 avg PnL
9. trend_alignment_performance.png — with-trend vs counter-trend
10. worst_10_trades_timeline.png — when did the big losses happen?

================================================================================
PART 5 — QUALITY ASSURANCE BEFORE DELIVERING
================================================================================

Before declaring the report complete, verify:

[ ] Every section has data. No "TODO" or "TBD" anywhere.
[ ] Every claim in §10 cites trade IDs.
[ ] Every WR reported has its 95% CI.
[ ] Every small-sample finding is labeled UNDERPOWERED.
[ ] v1/v2 findings carry the "context only" label.
[ ] All CSV artifacts exist and are readable.
[ ] All charts render (open and visually inspect).
[ ] Total trade count in the report = total closed trades in source data
    (reconcile any difference).
[ ] The file opens cleanly in a markdown viewer (no broken formatting).

================================================================================
OUTPUT MANIFEST
================================================================================

Deliver these files:

docs/research/full_trade_evolution_report.md       (the main document)
docs/research/charts/*.png                         (all required charts)
artifacts/all_trades_enriched.csv                  (master dataset)
artifacts/data_completeness_report.csv             (field availability)
artifacts/summary_by_version_symbol.csv
artifacts/summary_by_version_symbol_direction.csv
artifacts/summary_by_version_strategy.csv
artifacts/summary_by_session.csv
artifacts/summary_by_trend_alignment.csv
artifacts/summary_by_ml_confidence_bucket.csv
artifacts/filter_effectiveness.csv
scripts/analyze_all_trades.py                      (re-runnable)

Update docs/research/decision_log.md with an entry:
"[date] Comprehensive trade evolution analysis produced. [N] trades analyzed
across v1/v2/v3. Top 3 recommendations: [...]. Full report:
docs/research/full_trade_evolution_report.md"

================================================================================
EXECUTION
================================================================================

Show brief progress as you work:
- "Loading and joining data sources..."
- "Enriching [N] trades..."
- "Building summaries..."
- "Generating charts..."
- "Writing report..."
- "Running QA checklist..."

Do NOT stop for confirmation mid-task unless you hit:
- Missing required data file
- Contradictory data between sources that cannot be resolved
- A recommendation candidate that would require a code change to test (flag
  for meeting, don't attempt)

When complete, print:
- Total trades analyzed (broken down by version)
- Number of recommendations in §10
- List of persistent issues flagged
- Paths to all output files

Do NOT queue follow-up work. The 04-28 meeting decides what happens next.

Begin.
```

===

---

## Why This Prompt Is Built This Way

### Scientific discipline
- **Wilson score confidence intervals** on all win rates — so you never cite "67% WR" without context on how certain that is
- **p-values** on pattern claims — so "XAUUSD SELL fails" is backed by statistics, not impression
- **UNDERPOWERED flag** on small samples — prevents false confidence from 5-trade "patterns"
- **Cross-version consistency** — recommendations require v3 evidence, reinforced by v1/v2 if present

### Meeting-readiness
- Every recommendation in §10 has a fixed structure (CLAIM / EVIDENCE / CROSS-VERSION / ACTION / IMPACT / RISK / VOTE)
- Worst 10 and Best 10 trade case studies give the meeting concrete examples to discuss, not abstractions
- Executive Summary in §1 lets the meeting reader scan in 2 minutes before drilling deeper

### Protection against common errors
- **"No summarization shortcuts"** — forces full coverage instead of sampled claims
- **"v1/v2 context only"** — prevents decisions based on polluted data
- **"No code changes"** — keeps investigation separate from execution
- **QA checklist before delivery** — catches missing sections, broken charts, unreconciled counts

### Size and depth
- 20-30 pages is deliberate. Shorter = risk of missing patterns. Longer = unreadable.
- 10 required charts cover every dimension a reviewer will ask about.
- 8 pivoted CSVs let you re-analyze without re-running the whole thing.

---

## What You Do After Claude Code Finishes

1. **Wait** until it completes (30-60 min expected).
2. **Open** `docs/research/full_trade_evolution_report.md` in a markdown viewer.
3. **Read the Executive Summary (§1) first** — 2 minutes.
4. **Scan §10 (Recommendations)** — these are your meeting ammunition.
5. **Open one chart** from §4 to test it renders.
6. **Bring the report back to me** if anything is unclear — I'll help you prepare the meeting agenda.

If Claude Code asks to reduce scope, respond:
> *"No. Full scope as specified. The 04-28 meeting requires comprehensive evidence, not a summary. Proceed as written."*

---

## Expected Runtime and Cost

| Aspect | Expectation |
|---|---|
| Claude Code runtime | 30-60 minutes |
| Tool calls | 40-80 |
| Output size | ~3-5 MB total (CSVs + charts + report) |
| Your active time | ~5 minutes (just paste and wait) |

---

*This prompt was designed to produce evidence a reasonable skeptic cannot dismiss. If the output doesn't meet that standard, it is not the prompt's fault — raise specific issues and I will refine it.*
