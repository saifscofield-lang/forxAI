# Phase 8 — Quantitative Success Criteria

**Status:** AI-010 closure document (was OPEN, now DONE 2026-05-08)
**Audience:** project owner + reviewers at the Phase 8 → Phase 9 gate
**Author:** automated session report (Claude Code)

> Phase 8 is the formal v3 paper-trading validation window — six weeks
> of operation with frozen code, ending in a go/no-go vote on Phase 9
> (live $2,000 capital). Without explicit, written, quantitative
> criteria, "pass" devolves into a vibes check. This document fixes
> that.
>
> The criteria below were drafted as an external-review follow-up
> (AI-010, source = `external_review_claude_web_2026_04_28`). They
> also incorporate caveats surfaced by today's Phase 7 verdict and
> last week's GAP-FID instrumentation.

## Hard gates (any failure → DEFER Phase 9)

The following are **non-negotiable**. Each gate has a measurable
threshold; the gate-review meeting cannot wave them.

| # | Metric | Threshold | Window | Source |
|---|---|---|---|---|
| H1 | Profit Factor (R-units) | ≥ 1.30 | Final 30 trades | `analysis.rr_calculator.profit_factor_r` |
| H2 | Profit Factor ($-units) | ≥ 1.00 | Final 30 trades | `analysis.rr_calculator.profit_factor_dollars` |
| H3 | Max drawdown | < 10% of peak equity | Whole window | equity-curve query |
| H4 | Total trades | ≥ 30 | Whole window | `count(*) where is_closed=1` |
| H5 | Active symbols | ≥ 3 of v3 universe | Whole window | distinct symbols with ≥ 5 trades |
| H6 | Active directions per symbol | both BUY and SELL on ≥ 2 symbols | Whole window | per-symbol-per-direction count, AI-013 widget |
| H7 | Code freeze | zero commits to `engine/`, `strategies/`, `risk/` | Final 14 days | `git log --since` per directory |
| H8 | Slippage budget | mean abs slippage_pips ≤ 1.5 (FX) / ≤ 5 (XAUUSD) | Whole window | `trades.slippage_pips` (GAP-FID-01) |

## Soft criteria (failure → discussion, not auto-fail)

| # | Metric | Target | Note |
|---|---|---|---|
| S1 | Sharpe (daily, annualised) | ≥ 0.5 | Comparable to Phase 6 TSMOM gate |
| S2 | Worst single-trade loss | ≤ 2× planned R | Catches stop-jump / gap risk |
| S3 | Concentration | no single symbol > 40% of total absolute PnL | Diversification check |
| S4 | News-window adherence | < 3% trades opened within ±30 min of HIGH-impact event | `news_filter` correctness check |
| S5 | Engine uptime | ≥ 95% during forex market hours | `paper_trading.log` heartbeat analysis |

## Halt conditions (immediate stop, gate review re-scheduled)

The engine **must halt** and an emergency review must be called if:

- **HC1.** Drawdown exceeds **15%** of peak equity (CIRCUIT_BREAKER trigger)
- **HC2.** Any single day PnL < −5% of starting balance
- **HC3.** Three consecutive losing trades on the same (symbol, direction) cell
- **HC4.** Slippage anomaly: any single trade with `slippage_pips` > 10 (FX) or > 50 (XAUUSD)
- **HC5.** Connectivity outage > 6 hours during market open (engine watchdog AI-018 should already alert)
- **HC6.** Schema drift detected (`scripts/check_schema_drift.py` non-zero exit)
- **HC7.** Configuration parity break (AI-004b: `[CONFIG PARITY MISMATCH]` log line)

## Success criteria — explicit "pass" definition

Phase 8 → Phase 9 advance **iff**:

```
ALL hard gates H1–H8 pass
AND no halt condition (HC1–HC7) was triggered during the window
AND ≥ 4 of 5 soft criteria (S1–S5) are met or have a documented justification
AND the gate-review meeting (1 reviewer minimum) records explicit yes
```

If any halt condition triggered but was investigated and resolved
(e.g., HC4 traced to a known broker glitch), the gate review may
proceed with the incident logged in `decisions_log`.

## Fail definition

Phase 8 fails (Phase 9 deferred) if:

- Any hard gate misses
- A halt condition triggered and the root cause was not isolated
- 2+ soft criteria miss without justification

A failed Phase 8 does not auto-restart. The reviewer decides:
- Re-run Phase 8 with adjustments (different universe, different
  filter, etc.) — typical 3+ week deferral
- Drop to Phase 8.5 (smaller scope, shorter window)
- Escalate to architectural review (Phase 7-style)

## Sample-size discipline — Phase 9 graduation criterion (added 2026-05-09)

The Phase 8 H4 gate requires ≥ 30 closed trades. **30 trades is a
sufficiency check, not a confidence check.** Statistically, the
standard error on win rate at n=30 is roughly ±9 percentage points,
and profit factor estimates have heavy-tailed noise. A system passing
the 30-trade gate could still be edge-neutral or net-negative in
true expectation.

This is acceptable for Phase 8 because Phase 9.1 launches with
**small capital** ($2,000) — the live phase IS the longer evaluation.
But to prevent escalating capital on under-validated evidence, the
following Phase 9 graduation rule is added:

### Phase 9 graduation gate (between 9.1 → 9.2 / 9.3)

| Stage | Capital | Risk per trade | Trade count required to advance |
|---|---|---|---|
| 9.1 | $2,000 | 0.3% | open |
| 9.2 | $2,000 → up | 0.5% | **≥ 100 cumulative closed trades since 9.1 start** with R-PF ≥ 1.30 across them |
| 9.3 (scaling) | $5K+ | per plan | **≥ 200 cumulative closed trades** with R-PF ≥ 1.30 + Sharpe ≥ 0.5 |

The 100-trade bar is roughly the inflection point where the WR
standard error drops below ±5pp and a directional claim about edge
becomes meaningfully supported. The 200-trade bar approaches stable
profit-factor estimation territory.

**This is not a Phase 8 gate.** It only governs scaling decisions
after live trading begins. Phase 8 keeps the 30-trade H4 gate.

If trade frequency is low (e.g., 30 trades took 6 weeks → 100 trades
projects ~5 months), capital advancement is delayed accordingly.
Don't lower the trade-count bar to fit a calendar.

## Caveats noted today (2026-05-08)

1. **GAP-FID-01/02/04** plumbing for slippage / commission / swap
   was shipped 2026-05-07 but only takes effect on trades opened
   after engine restart. Ensure restart precedes the formal Phase 8
   start so H8 (slippage budget) has full coverage from day 1.

2. **AI-001 (zero-BUY XAUUSD)** was originally tagged Path-D
   dependent on Phase 7 meta-labeler. Phase 7 is now exhausted
   (2026-05-07 verdict). H6 (active directions per symbol) requires
   ≥ 2 symbols with both BUY and SELL — XAUUSD's BUY-side will not
   contribute unless AI-001 is resolved by another path. Watch for
   H6 risk.

3. **Phase 6 TSMOM** opened 4 BUY positions on demo 2026-05-08.
   These do NOT count toward Phase 8 trade count (H4) — TSMOM is
   a parallel layer, not the v3 strategy stack under test in
   Phase 8. Reconciliation: filter `trades.strategy IN ('rsi_reversal',
   'macd_crossover', 'sma_crossover', 'ml_direct')` for the H4 count.

4. **Per-symbol per-direction counts** (H6) are surfaced by the
   new AI-013 dashboard widget (Trading > Analytics tab) — gate
   review should screenshot this.

5. **News-window adherence** (S4) backfilled into trade_results
   2026-05-07 via GAP-FID-03. Forward going, the engine writes it
   live. Use `trade_results.news_nearby` as the canonical column.

## Cross-references

- `analysis/rr_calculator.py::phase7_ship_gate` — same R-PF / $-PF
  helpers Phase 7 used; Phase 8 H1/H2 reuse them
- `dashboard/pages/4_trading.py` — AI-013 per-symbol per-direction
  widget surfaces H5/H6
- `docs/research/phase7_ship_gate_definition.md` — sister document
  for Phase 7's now-rescoped gate; useful precedent for the
  dual-PF rationale
- `data/improvements.db` `decisions_log` — record of gate-review outcomes
