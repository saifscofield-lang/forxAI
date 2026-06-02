# Decision — Retire `sma_crossover` (2026-06-03)

**Decision:** Retire SMA Crossover. Removed from `scripts/paper_trade.py`
(import + block commented, with a documented re-enable option).
**Status:** RETIRED — by owner decision, despite a thin positive edge.

## Why (and why this is different from RSI / ml_direct)

SMA is **not edgeless** — unlike RSI (false premise) and ml_direct (no
directional signal). The Phase 3b/3c diagnosis shows a real but thin trend edge:

| Config | R-PF (walk-forward) | Folds > 1.0 | Trades/symbol-yr |
|---|---:|---:|---:|
| Ungated (H1 20/50) | 1.10 | 2/3 | 9 |
| ADX≥20 gate | 1.18 | 3/3 | 6 |
| ADX≥25 gate | 1.36 | 3/3 | 3 |

The edge is genuine and improves monotonically with trend strength (ranging
PF 0.93 → trending 1.35), consistent with "H1 FX rewards momentum."

**But:** SMA crosses are intrinsically **rare** (~9 trades/symbol-yr ungated,
~3 when gated to strong trends). It cannot serve the trade-accumulation goal,
and its ungated 1.10 PF is fragile to spread/slippage (excluded from the sim).

**Owner decision (2026-06-03):** retire SMA and concentrate the trend edge on
MACD-M15 rather than maintain a marginal, low-volume contributor. Fewer moving
parts, cleaner evaluation.

## ⚠️ Consequence — MACD-M15 is now the ONLY active strategy

After this retirement the live book runs on a **single strategy**:

| Strategy | Status |
|---|---|
| **macd_crossover (M15)** | **ACTIVE — the only live strategy** |
| sma_crossover | RETIRED (this doc) |
| rsi_reversal | RETIRED 2026-06-03 |
| ml_direct | RETIRED 2026-06-02 |
| bollinger_bounce / ml_filtered / stop_hunt / asia | retired/archived earlier |

This is deliberate — better one validated (if thin) edge than several
negative-EV strategies diluting the book and the evaluation sample. But it is
also **concentration risk**: a single strategy is a single point of failure, and
MACD's edge is thin. The natural and recommended next step is to **build new
trend/momentum strategies** (breakout, trend-continuation) to diversify the
trend edge the evidence says exists — NOT to revive any mean-reversion approach.

## Re-enable option (kept, low priority)

If a low-volume quality contributor is later wanted, re-enable SMA with an
**ADX≥20 gate** (validated PF 1.18, all 3 walk-forward folds positive). Do NOT
re-enable ungated (spread-fragile) or at ADX≥25 (too few trades to matter).

## Operational follow-up (live)

- Record in the **live tracker DB** `decisions_log` (category STRATEGY); local
  checkout DB is stale.
- After `git pull` + engine restart, confirm the scan log registers only
  `macd_crossover`; manage any open SMA positions to close under existing
  monitor logic.

## Code change

- `scripts/paper_trade.py`: import + registration commented with dated reason and
  the ADX≥20 re-enable option. No engine/risk/model changes. Reversible.

## Cross-references
- `docs/research/rescue_phase3b_sma_diagnosis.md` — diagnosis (T1–T4)
- `docs/research/rescue_phase3c_sma_gate_validation.md` — ADX gate sweep
- `docs/research/rsi_retirement_2026_06_03.md`, `ml_direct_retirement_2026_06_02.md`
