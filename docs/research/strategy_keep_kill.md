# Phase 5 Step 8 — Strategy Keep/Kill Decision (v3.0)

**Decision date**: 2026-04-17
**Signed off by**: Saif (user) — pending final review at Apr 28 Go/No-Go
**Evidence base**: 1,144 labeled primary signals (Option D) + 211 live trades on v2.4 demo

---

## Executive summary

| Category | Count | Details |
|---|---:|---|
| **Keep (production)** | 2 strategies × 10 pair combos | MACD all-pairs, RSI 3-pair subset |
| **Keep (meta-filtered only)** | 0 | Both keepers require meta-labeler before live |
| **Kill (remove from repo)** | 4 strategies | ml_direct, bollinger_bounce, asia_breakout, stop_hunt_reversal |
| **Kill (by pair)** | 4 RSI combos | RSI on JPY/XAU/CHF/CAD — structurally loses |
| **Archive (not delete)** | 2 strategies | sma_crossover, ml_filtered_sma — reference only |

v3.0 production surface reduces from **8 strategies × 7 pairs = 56 combos** to **2 strategies × 10 combos = 10 combos**. 82% reduction in surface area.

---

## Evidence-based ranking (data from today's research)

### Live trade evidence (v2.4 demo, 211 trades closed)

| Strategy | Pair | Trades | WR | PnL | Verdict |
|---|---|---:|---:|---:|---|
| macd_crossover | XAUUSD | 7 | 71.4% | **+$11,954** | ⭐ KEEP |
| macd_crossover | EURUSD | 4 | 100.0% | +$2,388 | ⭐ KEEP |
| macd_crossover | AUDUSD | 5 | 100.0% | +$1,893 | ⭐ KEEP |
| macd_crossover | GBPUSD | 4 | 75.0% | +$1,480 | ⭐ KEEP |
| macd_crossover | USDCHF | 6 | 66.7% | +$701 | ✅ KEEP |
| macd_crossover | USDCAD | 7 | 57.1% | -$102 | ⚠️ KEEP w/meta-filter |
| macd_crossover | USDJPY | 2 | 100.0% | +$45 | ⚠️ LOW-N, KEEP |
| macd_crossover | NZDUSD | 4 | 0.0% | **-$2,030** | ❌ BLACKLIST |
| rsi_reversal | AUDUSD | 3 | 100.0% | +$3,850 | ✅ KEEP |
| rsi_reversal | USDCHF | 2 | 100.0% | +$686 | ⚠️ LOW-N, reconsider |
| rsi_reversal | XAUUSD | 7 | 0.0% | -$256 | ❌ KILL |
| rsi_reversal | GBPUSD | 3 | 33.3% | -$646 | ❌ BLACKLIST |
| ml_direct | XAUUSD | 48 | 60.4% | **-$33,907** | ☠️ KILL STRATEGY |
| bollinger_bounce | NZDUSD | 6 | 16.7% | -$2,562 | ☠️ KILL STRATEGY |
| ml_filtered_sma | XAUUSD | 4 | 0.0% | -$3,591 | ☠️ KILL STRATEGY |
| sma_crossover | USDCAD | 2 | 0.0% | -$1,532 | ☠️ KILL STRATEGY |

Note: `ml_direct × XAUUSD` now at -$33,907 (was -$17,627 when plan was written). Damage grew before it was blacklisted in decision #13 on 2026-04-10.

### Backtest evidence (1,144 signals, 6 years, Option D)

**MACD per-pair WR** — uniform (32–46%):
```
EURUSD 45.2%  USDJPY 45.8%  USDCHF 43.6%  XAUUSD 42.7%
AUDUSD 37.5%  USDCAD 33.9%  GBPUSD 31.6%
```

**RSI per-pair WR** — sharply bimodal:
```
EURUSD 53.1% ← strong    AUDUSD 47.1% ← good
GBPUSD 45.7% ← acceptable
──────────────────────── cutoff at 40% ────────────────────────
USDCAD 30.6%  USDCHF 30.2%  ← lose in range-bound pairs
XAUUSD 23.2%  USDJPY 22.4%  ← structurally wrong regime
```

The >30-point WR gap between best and worst RSI pair is not noise — it's a structural mismatch between RSI reversal logic and the market character of JPY/XAU (strong trending, low mean-reversion).

---

## Final keep/kill decisions

### ✅ KEEP — MACD Crossover v2.0

Train meta-labeler on MACD signals across all 7 pairs (except NZDUSD — too few trades to characterize).

| Pair | Production status | Reason |
|---|---|---|
| EURUSD | KEEP | Live +$2,388 · Backtest WR 45% |
| GBPUSD | KEEP | Live +$1,480 · Backtest WR 32% (low) but live works |
| AUDUSD | KEEP | Live +$1,893 · Backtest WR 38% |
| USDCAD | KEEP | Live -$102 marginal · Backtest WR 34% — meta-filter required |
| USDCHF | KEEP | Live +$701 · Backtest WR 44% |
| USDJPY | KEEP | Live only 2 trades (+$45) · Backtest WR 46% strongest |
| XAUUSD | KEEP | Live **+$11,954** (71% WR) · Backtest WR 43% |
| NZDUSD | **BLACKLIST** | Live -$2,030 on 4 trades (0% WR) · No backtest data |

Training: **815 backtest primary signals** → meta-labeler target ≥ 60% WR after filtering.

### ✅ KEEP (restricted) — RSI Reversal v1.1

Restrict RSI to 3 pairs with structural fit. Train meta-labeler only on those 3.

| Pair | Production status | Reason |
|---|---|---|
| EURUSD | KEEP | Backtest WR 53.1% — best meta-labeling candidate |
| AUDUSD | KEEP | Backtest WR 47.1% + Live 100% on 3 trades |
| GBPUSD | KEEP | Backtest WR 45.7% |
| USDCAD | **BLACKLIST** | Backtest WR 30.6% — bottom cluster |
| USDCHF | **BLACKLIST** | Backtest WR 30.2% + Live low-N (only 2 trades) |
| XAUUSD | **KILL** | Live 0% WR on 7 trades · Backtest WR 23.2% |
| USDJPY | **KILL** | Backtest WR 22.4% · Live +$55 on 6 trades (barely positive, won't survive real costs) |

Training: **~240 backtest primary signals** on the 3 kept pairs. This is thin — meta-labeler will have high variance. Consider ensemble or wider confidence interval on predictions.

### ☠️ KILL (remove from production)

| Strategy | Evidence | Action |
|---|---|---|
| ml_direct | -$33,907 on XAUUSD alone; fundamental thesis (ML predicts direction) disproven by step 6 (all AUC 0.5) | `git rm` on May 4 |
| bollinger_bounce | Net negative across 6 pairs; NZDUSD -$2,562 standout loss; no backtest PASS in 274 runs | `git rm` on May 4 |
| asia_breakout | 2 live trades (1 win, 1 loss), no backtest edge, session-based thesis unverified | `git rm` on May 4 |
| stop_hunt_reversal | 1 live trade only, no statistical significance | `git rm` on May 4 |

### 📦 ARCHIVE (keep in repo for reference, move to `strategies/archive/`)

| Strategy | Why archived |
|---|---|
| sma_crossover | Positive on AUDUSD (+$2,500) but unreliable elsewhere; the MACD crossover is its stronger cousin. Keep code for future A/B reference. |
| ml_filtered_sma | S-grade backtest on AUDUSD D1 was genuine (PF 1.58, 73.4% WR, 79 trades) but v3.0 replaces ML-filter concept with meta-labeler. Archive the code. |

---

## Production surface after v3.0 ships (Jun 8 paper / Sep 1 live)

```
Layer 1 (primary signals):
  macd_crossover × [EURUSD, GBPUSD, AUDUSD, USDCAD, USDCHF, USDJPY, XAUUSD]   = 7 combos
  rsi_reversal   × [EURUSD, AUDUSD, GBPUSD]                                    = 3 combos
  ─────────────────────────────────────────────────────────────────────────────
  Total primary combos                                                         = 10

Layer 2 (meta-labeler):
  1 binary model trained per strategy (2 models total: MACD, RSI)
  OR 1 model per (strategy, pair-cluster) — decide in Phase 7

Layer 3 (TSMOM, parallel):
  6 pairs × 1 signal/month = ~6 signals/month
  (unchanged by this decision — TSMOM operates on monthly timeframe)
```

---

## Confidence in this decision

**High confidence KILLs** (both live + backtest agree):
- ml_direct × XAUUSD: -$33,907 live + plan already flagged
- RSI × XAUUSD: 0% WR on 7 live trades + 23% backtest
- RSI × USDJPY: 22% backtest, essentially random
- bollinger_bounce: net negative across portfolio

**Medium confidence KEEPs** (backtest strong, live low-N):
- MACD × USDJPY: only 2 live trades, relying on 46% backtest WR
- RSI × GBPUSD: backtest 45.7%, live -$646 (3 trades) — meta-labeler must correct

**Low confidence KEEPs** (requires meta-filter to be profitable):
- MACD × USDCAD: live -$102, backtest 34% WR
- MACD × AUDUSD: live +$1,893 but backtest 38% (below 40% rule of thumb)

---

## What this decision is NOT

- **Not a performance target**. These are the signals we'll try to improve with meta-labeling. If the meta-labeler fails to lift any of these above PF 1.1, we'll re-evaluate at the Apr 28 Go/No-Go.
- **Not a commitment to live trading**. This is the *paper* trading production set for Jun 8 onward.
- **Not permanent**. New evidence (more STABLE trades, Phase 7 walk-forward results) can revise any line.

---

## Action items (executed on May 4, not before)

1. `git mv strategies/ml_direct_strategy.py strategies/archive/` (if not already done)
2. `git mv strategies/bollinger_bounce.py strategies/archive/`
3. `git mv strategies/asia_breakout.py strategies/archive/`
4. `git mv strategies/stop_hunt_reversal.py strategies/archive/`
5. `git mv strategies/sma_crossover.py strategies/archive/`
6. `git mv strategies/ml_filtered_strategy.py strategies/archive/` (replaced by meta-labeler wrapper)
7. Update `scripts/run_engine.py` to register only macd + rsi
8. Add `PAIR_WHITELIST` dict to each remaining strategy so meta-labeler can short-circuit blacklisted pairs fast

All freeze-violating — do NOT execute before May 4.
