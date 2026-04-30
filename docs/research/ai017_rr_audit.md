# AI-017: R:R Pathology Audit — Pre-Phase-7 Gate

**Date:** 2026-04-30
**Author:** automated audit (Claude Code)
**Source action item:** `AI-017` (BLOCKING, blocking Phase 7)
**Trigger:** 2026-04-28 meeting Vote 4 + Vote 5 — bollinger_bounce and ml_filtered_sma both retired with identical pathology (WR ~68%, R:R ~0.11, PF 0.23–0.26). Project lead flagged the pattern as plausibly system-wide and required an audit before Phase 7 kickoff (2026-05-04) so the meta-labeler does not train on contaminated data.

## Pathology gate

| Component | Threshold | Rationale |
|---|---|---|
| WR | >= 60% | Compulsion to “feel right” via small-target captures |
| Realized R:R | < 0.5 | Inverted reward structure |
| PF | < 1.0 | Net unprofitable despite high WR |

A strategy hitting all three = **strict pathology**. A strategy hitting WR + R:R but PF >= 1.0 = **fragile pathology pattern** — profitable only while WR holds.

## Strategies in scope (post Phase 7 Step 3 archive)

After archiving `bollinger_bounce`, `stop_hunt_reversal`, `asia_breakout` (this commit's predecessor), the surviving active set is:

- `sma_crossover`
- `rsi_reversal`
- `macd_crossover`
- `ml_direct_strategy` (live on XAUUSD, the only ML signal source in v3)
- `ml_filtered_strategy` (file retained, paper_trade.py code path commented out since 2026-04-28 Vote 5)

Data source: `artifacts/summary_by_version_strategy.csv` and `artifacts/all_trades_enriched.csv` (v3 segment, 137 trades).

## Per-strategy verdict — v3 segment

| Strategy | n | WR % | R:R | PF | Verdict |
|---|---:|---:|---:|---:|---|
| `sma_crossover` | 2 | 0 | n/a | n/a | **INSUFFICIENT DATA** — only 2 v3 trades, both losses |
| `rsi_reversal` | 2 | 100 | n/a | n/a | **INSUFFICIENT DATA** — only 2 v3 trades, both wins |
| `macd_crossover` | 0 | n/a | n/a | n/a | **NO SIGNALS** — silent for entire v3 segment |
| `ml_direct` | 76 | 76.3 | 0.46 | 1.49 | **FRAGILE PATHOLOGY PATTERN** — currently profitable but only because WR is exceptionally high |
| `ml_filtered_sma` | 22 | 68.2 | 0.11 | 0.23 | **STRICT PATHOLOGY** (already retired 2026-04-28) |

## Key finding 1 — `ml_direct` carries the pattern

`ml_direct` v3 metrics (76 trades, 75 of them on XAUUSD, 1 on AUDUSD):
- WR 76.3% — very high, in the same band as the retired strategies
- avg_win = $1,227.72, avg_loss = -$2,656.62 → R:R 0.462
- PF = (58 × 1227.72) / (18 × 2656.62) = 71,208 / 47,819 = **1.49**

PF sensitivity to WR drop:
- WR 76% → PF 1.49 (current)
- WR 70% → PF 1.08 (marginal)
- WR 65% → PF 0.86 (loss-making)
- WR 60% → PF 0.69 (bad)

Any sustained WR regression below 70% turns it net-negative. This matches AI-017’s warning that high WR can mask inverted R:R until WR mean-reverts.

History also supports the fragility view: in v2, ml_direct had **WR 75%, R:R 0.10, PF 0.29** — strict pathology. The recovery to PF 1.49 in v3 came not from R:R repair but from holding higher WR; structural risk is unchanged.

## Key finding 2 — planned-vs-realized R:R drift

`all_trades_enriched.csv` has both `planned_rr` (from SL/TP distances at order time) and `realized_rr` columns.

For v3 `ml_direct`: planned R:R **median 1.16**, **mean 1.27**.
For v3 `ml_direct`: realized R:R from avg_win/avg_loss = **0.46**.

That is a ~2.5x drift between what the strategy designs and what actually realizes. Hypotheses (in priority order):

1. SL slippage on XAUUSD (large adverse excursions blow through the planned SL price). This is the symptom GAP-FID-01 already tracks: slippage isn't captured in OrderSend response, so we can't quantify which leg of the drift is slippage vs. early-close.
2. Early closes (manual close, time-based exit, or opposite-signal close before TP is reached) — would deflate avg_win.
3. Asymmetric fill quality between SL stops (slippage-prone) and TP limits (fill-or-no-fill).

The drift is real and large enough that any Phase 7 ship gate stated in **planned** R:R terms will be unreliable.

## Key finding 3 — `realized_rr` column is NaN across all v3 trades

`artifacts/all_trades_enriched.csv` defines a `realized_rr` column. Every v3 row reads `NaN`. The pipeline computes `planned_rr` at order time but never backfills realized R:R from `open_price`/`close_price`/`stop_loss`/`take_profit` after the trade closes. Without this, automated R:R drift detection cannot run, and the meta-labeler in Phase 7 has no R:R label to train on.

## Key finding 4 — designed R:R < 1.0 by symbol in `optimized_params.yaml`

Inspecting `data/optimized_params.yaml` directly:

| Symbol | SL mult | TP mult | Designed R:R |
|---|---:|---:|---:|
| EURUSD | 3.00 | 4.75 | 1.58 |
| GBPUSD | 0.75 | 3.50 | 4.67 |
| USDJPY | 0.50 | 3.75 | 7.50 |
| XAUUSD | 0.50 | 1.75 | 3.50 |
| **AUDUSD** | **2.50** | **1.50** | **0.60** |
| **USDCAD** | **2.00** | **1.25** | **0.625** |
| USDCHF | 2.75 | 3.50 | 1.27 |

Two symbols have **TP < SL by design**: AUDUSD and USDCAD. Every surviving strategy passes these multipliers through to its SL/TP construction (`paper_trade.py` lines around the strategy instantiation block). On these two symbols, no surviving strategy can achieve R:R >= 1 without overriding the params. This is upstream of every strategy and predates the Phase 7 build — likely an artifact of an optimizer that maximized PF or WR rather than expected value.

## Key finding 5 — three surviving strategies cannot be audited empirically

`macd_crossover` (0 v3 trades), `sma_crossover` (2), `rsi_reversal` (2) are too sparse for empirical assessment. Their v1 results were healthy (`macd_crossover` v1: 39 trades, R:R 1.78, PF 4.0; `rsi_reversal` v1: 24 trades, R:R 3.23, PF 3.23; `sma_crossover` v1: 17 trades, R:R 2.09, PF 1.14) but the surrounding pipeline (filters, gating, ML overlay) has changed since v1, so v1 numbers don't generalise. **Code-level R:R defaults are healthy** (1.40–1.67 in their constructors), but they are then overridden by `optimized_params.yaml` per-symbol multipliers above.

## Recommendations — must clear before Phase 7 starts (2026-05-04)

| # | Action | Severity | Owner |
|---|---|---|---|
| 1 | Populate `realized_rr` retroactively (compute from open/close/SL/TP) and add to the live trade-write pipeline. Without it, Phase 7's R:R-based ship gate (`PF >= 1.3 on 6mo OOS`) is uninstrumented. | **BLOCKER** | engineering |
| 2 | Resolve AUDUSD and USDCAD designed R:R < 1.0 in `optimized_params.yaml` — either correct the multipliers or document the symbol-specific exclusion. | **BLOCKER** | strategy |
| 3 | Add a WR-floor monitor on `ml_direct/XAUUSD`: alert if rolling 30-trade WR drops below 70% (current 76% has only 6pp of head-room before PF goes marginal). | WATCH | observability |
| 4 | Phase 7 meta-labeler trains on MACD + RSI signals (per Phase 7 plan steps 6–7). v3 has 0 MACD + 2 RSI trades. Decide before May 4: (a) backfill from v1/v2 raw signals with regime caveats, (b) accept reduced training set, or (c) shift training to strategies with v3 data (but those carry the pathology pattern). Without this decision the meta-labeler will train on whatever data exists, which is dominated by the `ml_direct/XAUUSD` high-WR/low-R:R pattern → meta-labeler learns to **amplify** the pathology. | **BLOCKER** | strategy |
| 5 | Investigate the `ml_direct` planned-vs-realized R:R drift (1.16 → 0.46). Likely root cause overlaps with `GAP-FID-01` (slippage uncaptured) — close those two together. | HIGH | engineering |

## Verdict on AI-017

**Pathology pattern is system-wide, not strategy-specific.** Three concrete root causes identified:

1. Optimizer-produced symbol params with TP < SL on two pairs (`AUDUSD`, `USDCAD`).
2. Realized R:R drifts ~2.5x worse than planned R:R, and the column that would measure this is never populated.
3. `ml_direct` carries the pattern but is masked by exceptional WR — fragile, not safe.

The 2026-04-28 Vote 4 + Vote 5 retirements removed the surface symptoms. The plumbing that produced them is still in place. **Phase 7 should not start before Recommendations 1, 2, and 4 are cleared.**

## Cross-references

- `docs/research/decision_log.md` (2026-04-28 entry) — Vote 4 / Vote 5 retirements
- `docs/research/expectancy_report.md` — prior R:R analysis
- `docs/research/strategy_keep_kill.md` — strategy retention framework
- `data/optimized_params.yaml` — symbol params source
- `artifacts/summary_by_version_strategy.csv` — empirical metrics source
- `artifacts/all_trades_enriched.csv` — trade-level source
- Action item `GAP-FID-01` — slippage instrumentation (overlaps with Recommendation 5)
