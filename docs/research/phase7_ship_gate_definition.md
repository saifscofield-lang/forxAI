# Phase 7 Ship Gate — Authoritative Definition

**Status:** authoritative as of 2026-05-01.
**Inherits to:** May 4 Phase 7 kickoff meeting.
**Source:** project-lead decision logged in `docs/p.md` (2026-05-01) in response to the Checkpoint 1 finding that R-PF and $-PF can diverge meaningfully on the same dataset.

## Gate

A strategy ships out of Phase 7 when, computed on the validation cohort:

> **R-PF ≥ 1.3 AND $-PF ≥ 1.0**

Both must pass. Either alone is insufficient.

## Definitions

### R-PF (R-unit profit factor) — primary

```
R-PF = sum(realized_rr where realized_rr > 0)
       ─────────────────────────────────────────
       sum(|realized_rr| where realized_rr < 0)
```

- `realized_rr` for each trade is the signed risk-multiple computed at trade close. See `analysis/rr_calculator.py::realized_rr`.
- Positive when the trade exits in profit, negative when in loss, zero when close == open.
- Each SL hit contributes exactly −1.0 to the denominator regardless of dollar amount.
- **Property:** independent of position size. Two strategies with identical signal quality but different sizing will produce identical R-PF.

### $-PF (dollar profit factor) — secondary

```
$-PF = sum(pnl where pnl > 0)
       ──────────────────────────
       sum(|pnl| where pnl < 0)
```

- The standard dollar-weighted profit factor. Yesterday's audit cited this number (1.489 on the 76 ml_direct/v3 sample).
- Reflects actual capital outcome.

### Why both

The two metrics diverge whenever position size or SL distance varies across trades. On the audit's 76-ticket ml_direct sample volume was constant (1.0 lot) but SL distance had a 14,796× spread, producing R-PF 1.770 vs $-PF 1.489 — both above 1.0 but with markedly different headroom.

The dual-gate guards against the failure modes neither metric catches alone:

| Scenario | $-PF | R-PF | Dual gate verdict |
|---|---|---|---|
| Many small wins, one large loss in $ | 0.7 | 2.0 | **FAIL** ($-PF below 1.0) |
| Consistent +0.3R wins, occasional −1R loss, all 1-lot | 0.85 | 1.4 | **FAIL** |
| Healthy strategy | 1.5 | 1.7 | **PASS** |
| Marginal strategy | 1.05 | 1.32 | **PASS** (just) |

R-PF ≥ 1.3 is the primary academic gate (per-trade-risk normalised). $-PF ≥ 1.0 prevents shipping when capital is shrinking despite favourable R metrics.

## Implementation

`analysis/rr_calculator.py::phase7_ship_gate(pnls, rrs)` returns:

```python
{
    "pf_dollars": float,
    "pf_r": float,
    "passes_dollars_gate": bool,
    "passes_r_gate": bool,
    "passes_dual_gate": bool,
    "thresholds": {"r_min": 1.3, "dollars_min": 1.0},
}
```

Pass `pnls` and `rrs` aligned by trade ticket. None values are skipped on each side independently.

## Validation cohort

Phase 7's plan calls for a 6-month out-of-sample window. The implementation must:

1. Filter `trade_results` to `engine_version='2.4'` (v3) trades.
2. Window by `close_time` covering the 6-month OOS period.
3. Pull `pnl` and `risk_reward_actual` per trade.
4. Pass to `phase7_ship_gate()`.

**Caveat — relevant to the May 4 kickoff:** the SL_HIT/profitable mislabel bug (Phase 7 Blocker #1b, see `ai017_supplemental_findings_2026_05_01.md`) corrupts `exit_reason` on roughly 27% of v3 SL_HIT trades. It does NOT affect `pnl` or `risk_reward_actual` directly — those are computed from price fields, not from `exit_reason`. So this dual-gate computation is correct even on the affected data. Filters that depend on `exit_reason` (e.g., "exclude SL_HIT trades from training") would NOT be safe until #1b ships.

## Cross-references

- `analysis/rr_calculator.py` — implementation.
- `tests/test_rr_calculator.py` — smoke tests + CSV roundtrip test.
- `docs/research/ai017_rr_audit.md` (2026-04-30) — original audit (cited only $-PF).
- `docs/research/ai017_supplemental_findings_2026_05_01.md` — corrections + new findings.
