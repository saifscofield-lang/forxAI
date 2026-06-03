# Rescue Plan — Phase 5c: MACD-M15 + D1 Trend Filter

**Data:** 7 symbols × full M15 (~100k/symbol). Same MACD logic + ATR(1.2), ordered SL/TP, horizon=100, SL=2.5/TP=3.5×ATR, per-symbol spread+slippage charged per trade. D1 trend joined no-lookahead (prior closed daily bar).
**D1 filter:** BUY only if D1 trend up, SELL only if D1 trend down.

D1 variants: **d1a** EMA50>EMA200 · **d1b** close>EMA200 · **d1c** close>SMA50

## A. Full-sample (pooled) — baseline vs D1 filters

| Config | Trades | Win% | PF_clean | PF_net | EV_net | Trades kept |
|---|---:|---:|---:|---:|---:|---:|
| baseline (no D1) | 2,898 | 41.2% | 0.981 | 0.857 | -0.2267 | 100% |
| + D1a EMA50>200 | 1,496 | 42.2% | 1.024 | 0.898 | -0.1589 | 52% |
| + D1b close>EMA200 | 1,682 | 41.8% | 1.005 | 0.880 | -0.1882 | 58% |
| + D1c close>SMA50 | 1,775 | 40.7% | 0.960 | 0.839 | -0.2569 | 61% |

**Best D1 variant by PF_net:** `d1a` (PF_net 0.898).

## B. Per-symbol — best variant `d1a` (net of cost)

| Symbol | Trades | Win% | PF_clean | PF_net | EV_net |
|---|---:|---:|---:|---:|---:|
| AUDUSD | 148 | 37.8% | 0.852 | 0.727 | -0.4623 ❌ |
| EURUSD | 218 | 42.7% | 1.042 | 0.929 | -0.1083 ❌ |
| GBPUSD | 270 | 45.2% | 1.154 | 1.016 | +0.0232 |
| USDCAD | 208 | 36.5% | 0.806 | 0.683 | -0.5517 ❌ |
| USDCHF | 230 | 41.3% | 0.985 | 0.805 | -0.3208 ❌ |
| USDJPY | 204 | 40.7% | 0.960 | 0.889 | -0.1717 ❌ |
| XAUUSD | 218 | 49.1% | 1.350 | 1.246 | +0.3283 |

## C. Walk-forward stability — best variant `d1a` (8 folds)

| Fold (old→new) | Trades | Win% | PF_clean | PF_net | EV_net |
|---|---:|---:|---:|---:|---:|
| 1 | 186 | 51.1% | 1.462 | 1.307 | +0.3997 |
| 2 | 199 | 33.2% | 0.695 | 0.627 | -0.6613 |
| 3 | 209 | 42.6% | 1.038 | 0.914 | -0.1322 |
| 4 | 186 | 37.6% | 0.845 | 0.730 | -0.4569 |
| 5 | 217 | 44.7% | 1.132 | 0.963 | -0.0567 |
| 6 | 180 | 39.4% | 0.912 | 0.797 | -0.3320 |
| 7 | 148 | 44.6% | 1.127 | 0.998 | -0.0031 |
| 8 | 169 | 45.6% | 1.172 | 1.017 | +0.0248 |

**Fold PF_net:** min=0.627, max=1.307, profitable folds = 2/8.

## D. Per-year — best variant `d1a` (net of cost)

| Year | Trades | Win% | PF_clean | PF_net | EV_net |
|---|---:|---:|---:|---:|---:|
| 2021 | 1 | 100.0% | inf | inf | +3.3253 |
| 2022 | 333 | 43.5% | 1.080 | 0.972 | -0.0416 |
| 2023 | 394 | 39.6% | 0.918 | 0.803 | -0.3204 |
| 2024 | 398 | 41.0% | 0.971 | 0.833 | -0.2687 |
| 2025 | 311 | 45.3% | 1.161 | 1.016 | +0.0237 |
| 2026 | 59 | 44.1% | 1.103 | 0.984 | -0.0241 |

## Verdict (same gates as 5b)

- G1 Full-sample PF_net ≥ 1.05 · G2 ≥6/8 folds PF_net≥1.0 · G3 recent era (2025/26) PF_net≥1.0 · G4 ≥4/7 symbols PF_net≥1.0

Baseline (5b) PF_net was **0.857**. If the best D1 filter clears the gates, the D1-trend gate rescues the live MACD-M15 engine (cheap, no margin/holding change). If it only nudges PF_net up but still <1.0, the daily trend is not enough and the price-only-TA hypothesis is exhausted (per Phase 4a/5b).

## VERDICT — 🟡 D1 filter HELPS but does NOT clear the gates (pooled)

| Gate | Threshold | Baseline 5b | + D1a filter | Result |
|---|---|---:|---:|:--:|
| G1 Full-sample PF_net | ≥ 1.05 | 0.857 | **0.898** | ❌ FAIL |
| G2 Folds PF_net ≥ 1.0 | ≥ 6/8 | 1/8 | **2/8** | ❌ FAIL |
| G3 Recent era 2025/26 | ≥ 1.0 | 0.88/0.95 | 1.016 / 0.984 | ⚠️ split |
| G4 Symbols PF_net ≥ 1.0 | ≥ 4/7 | 1/7 | **2/7** | ❌ FAIL |

### What the D1 filter actually did

1. **It carries real information — but not enough.** The daily-trend gate (EMA50>EMA200)
   cut trades roughly in half (2,898 → 1,496, keeps 52%) and lifted **clean** PF from
   0.981 → **1.024** (now >1.0) and EV from −0.028 to a better level. So aligning with
   the daily trend genuinely improves entry quality — the signal is not noise.
2. **Costs still win.** That clean improvement is not large enough to survive the M15
   spread/slippage drag: **PF_net 0.898 < 1.0.** Halving trade count also halves the
   chances of out-running cost. Every gate moves in the right direction, none crosses.
3. **The improvement is concentrated, not broad.** Pooled-positive is carried by two
   symbols: **XAUUSD (PF_net 1.246, EV +0.33, 218 trades, WR 49%)** and GBPUSD (1.016).
   The other 5 stay net-negative; AUDUSD (0.73) and USDCAD (0.68) are badly negative and
   drag the pool below 1.0.

### Decision

- **Do NOT flip the whole live book to D1-filtered MACD-M15 on these numbers** — pooled
  PF_net is still 0.90 and fails 3 of 4 gates. The daily trend is a real but insufficient
  edge source for the FX majors here.
- **Your margin/holding concern is fully resolved on the mechanics:** the D1 *filter*
  keeps entries/exits on M15, so holding time, swap, and margin are unchanged — trades
  simply ~halve in count. (This was the right design choice vs trading D1 bars directly.)
- **One genuinely promising thread: XAUUSD.** D1-filtered MACD-M15 on gold is net-positive
  in 5b AND 5c, the only symbol consistently >1.0 with a healthy margin. This is the first
  configuration in the whole rescue that looks like a real cost-survivable edge.

### ⚠️ Mandatory caveat before chasing XAUUSD

Phase 7 already burned us once: a single-corpus symbol whitelist looked great, then
**failed walk-forward validation as an artifact** (commit 64a3507). XAUUSD here is selected
*post-hoc* from a 7-symbol sweep — exactly that trap. Before acting on it, gold needs its
own dedicated, pre-registered validation: walk-forward PF_net per fold (not pooled), an
out-of-sample hold-out, and a check that the +D1 result isn't driven by one trending
regime (2020-2024 gold bull run). If XAUUSD holds up under that, it — not the FX majors —
is the surviving engine.

Next: either (a) pre-register and run the XAUUSD-only walk-forward, or (b) accept the
Phase 4a/5b conclusion for the FX majors and pivot to non-price information there.