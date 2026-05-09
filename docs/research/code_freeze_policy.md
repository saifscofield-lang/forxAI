# Code Freeze Policy — STABLE_v2 window

**Effective:** 2026-05-09
**Target gate review:** ~2026-06-20 (6 weeks of frozen-code paper trading)
**Authority:** project owner direct decision 2026-05-09

> The single most important discipline of this project right now: **stop
> changing the trading code so the system can finally be evaluated on a
> clean dataset**. Each prior code change invalidated everything before
> it for evaluation purposes. STABLE_v1 (Apr 10 → May 8) is closed.
> STABLE_v2 starts today.

## The rule

For 6 weeks (or until the gate-review meeting, whichever is later),
**zero changes** to:

| Path | Reason |
|---|---|
| `engine/trading_engine.py` | Trade decision, order placement, monitor logic |
| `engine/shadow_tracker.py` | Trade outcome accounting |
| `engine/circuit_breaker.py` | Risk halts |
| `strategies/*.py` (active strategies only) | Signal generation |
| `risk/*.py` | Position sizing, stop logic |
| `execution/broker_adapters/*.py` | MT5 order routing |
| `news/news_filter.py` | Trade-time filter |
| `features/regime_detector.py` | Regime gate |
| `config/paper.yaml` `instruments`, `risk`, `strategy_blacklist`, `session_filter` keys | Trade-affecting config |

## What's still allowed during the freeze

| Type | Examples |
|---|---|
| Documentation | RFCs, decision logs, research notes, this doc |
| Dashboard | New widgets, filters, alerts, reorganisation |
| Telegram reports | Daily summaries, status pings |
| Read-only investigation | AI-022 shadow-write follow-up (look but don't fix) |
| Schema diagnostics | `scripts/check_schema_drift.py` and similar |
| Observability | New log lines, metrics, alerts that don't change trade behaviour |
| Phase 8 prep | Backtest comparators, gate-review tooling |
| Memory + tracker housekeeping | `data/improvements.db` non-trade fields |

## What clearly resets the freeze clock

If any of these happen, STABLE_v2 ends and a new window opens (which
delays the gate review by at least 6 weeks from the new date):

- Any commit that touches the paths in the rule table above
- Adding or removing strategies from production rotation
- Changing strategy parameters (ATR multipliers, RSI thresholds, etc.)
- Changing `risk_per_trade`, `max_open_positions`, `max_lot_size`
- Editing `strategy_blacklist` entries
- Changing `blocked_hours_utc` or `golden_hours_utc`
- Changing the news-filter window or impact threshold
- Switching brokers or accounts (Phase 9 transition is its own event)

## What IS allowed even though it touches restricted paths

There is one narrow exception: **emergency bug fixes**. Definition:

- A bug producing **wrong trade direction** (e.g., BUY signal opens SELL)
- A bug producing **runaway lot size** (e.g., 10× intended size)
- A crash that prevents the engine from running at all
- A data-corruption bug that breaks the trade ledger

If one of these is hit:
1. Fix it minimally
2. Document the bug in `decisions_log` immediately
3. Restart the freeze clock — open STABLE_v3 in `data_segmentation_log`
4. Accept the gate review pushes 6 weeks from the new freeze date

"I noticed I could improve X" is **not** an emergency. Write it in
the post-freeze backlog (`docs/research/post_freeze_backlog.md`)
and forget about it until after the gate.

## How to evaluate during and after the freeze

- **Phase 8 ship-gate metrics** (`docs/research/phase8_success_criteria.md`)
  compute from `STABLE_v2` trades only. SQL filter:
  `WHERE open_time >= '2026-05-09 00:00:00'`
- The dashboard's home and trading tabs should show a "since freeze"
  toggle so you can see clean numbers.
- Old data (`OLD`, `TRANSITION`, `STABLE_v1`) stays in the DB for
  diagnostics, ML training, audit trail. **Never** for performance
  evaluation under STABLE_v2.

## How long is "the freeze"

Minimum: **6 weeks of trading**, ending on or after 2026-06-20.
Hard requirement: **≥ 30 closed trades from STABLE_v2** (Phase 8 H4 gate).
If trade count is short of 30 by 2026-06-20, the window extends until
H4 is met.

The freeze also requires Phase 8 H7: zero commits to engine/strategies/risk
in the **final 14 days** before the gate. Combined: any restricted
commit in the 14 days before the planned gate date pushes the gate
14 days forward automatically.

## Why this is hard to follow

Coding instinct says "fix it now." Six weeks of watching a system you
know has flaws is uncomfortable. But the alternative — endless
sub-evaluations of ever-changing code — is what produced the +$2,283
nominal / −$27,311 honest reading on the v3 ledger: a number nobody
trusts.

The freeze ends when the system has been evaluated. Then the
post-freeze backlog opens and we iterate.

## Cross-references

- `docs/research/post_freeze_backlog.md` — what to do after the gate
- `docs/research/phase8_success_criteria.md` — gate-review criteria
- `data/improvements.db` `data_segmentation_log` row 4 (STABLE_v2)
- `docs/meetings/2026_06_08_phase7_ship_gate.md` — Jun 8 path-selection vote (no code change implied)
