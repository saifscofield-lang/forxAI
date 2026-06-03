# Rescue Plan — Phase 5b: MACD-M15 Edge Re-Validation

**Data:** 7 symbols × FULL M15 history (~100k bars/symbol, 2022→2026). MACD logic + ATR(1.2) filter, one-position-at-a-time, ordered SL/TP, horizon=100. SL=2.5×ATR, TP=3.5×ATR.
**Costs:** per-symbol spread+slippage charged once per trade, in ATR units (see table). PF_clean = (W×TP)/(L×SL); PF_net is after costs.

## Cost assumptions (price units, charged once per trade)

| Symbol | Spread | Slippage | Total | ~Total / median ATR |
|---|---:|---:|---:|---:|
| AUDUSD | 0.00011 | 0.00004 | 0.00015 | 26.4% |
| EURUSD | 0.00009 | 0.00003 | 0.00012 | 18.6% |
| GBPUSD | 0.00013 | 0.00004 | 0.00017 | 20.6% |
| USDCAD | 0.00015 | 0.00005 | 0.00020 | 30.5% |
| USDCHF | 0.00015 | 0.00005 | 0.00020 | 34.6% |
| USDJPY | 0.00900 | 0.00300 | 0.01200 | 11.0% |
| XAUUSD | 0.28000 | 0.10000 | 0.38000 | 14.3% |

## 1. Full-sample (pooled, all symbols, all years)

| Trades | Win% | PF_clean | PF_net | EV_net (ATR/trade) |
|---:|---:|---:|---:|---:|
| 2,898 | 41.2% | 0.981 | 0.857 | -0.2267 |

## 2. Per-symbol (full sample, net of cost)

| Symbol | Trades | Win% | PF_clean | PF_net | EV_net |
|---|---:|---:|---:|---:|---:|
| AUDUSD | 303 | 37.6% | 0.844 | 0.722 | -0.4720 ❌ |
| EURUSD | 452 | 41.6% | 0.997 | 0.888 | -0.1742 ❌ |
| GBPUSD | 505 | 43.8% | 1.089 | 0.959 | -0.0618 ❌ |
| USDCAD | 436 | 37.6% | 0.844 | 0.711 | -0.4952 ❌ |
| USDCHF | 456 | 39.7% | 0.921 | 0.747 | -0.4280 ❌ |
| USDJPY | 350 | 43.1% | 1.062 | 0.990 | -0.0146 ❌ |
| XAUUSD | 396 | 44.2% | 1.109 | 1.021 | +0.0308 |

## 3. Walk-forward stability (8 contiguous folds, pooled)

Each symbol's bars split into equal contiguous time-folds; trades from the same fold index pooled across symbols. A real edge holds its sign across folds.

| Fold (old→new) | Trades | Win% | PF_clean | PF_net | EV_net |
|---|---:|---:|---:|---:|---:|
| 1 | 336 | 47.0% | 1.243 | 1.111 | +0.1564 |
| 2 | 375 | 34.4% | 0.734 | 0.664 | -0.5829 |
| 3 | 397 | 41.3% | 0.985 | 0.865 | -0.2135 |
| 4 | 413 | 41.9% | 1.009 | 0.871 | -0.2036 |
| 5 | 405 | 41.2% | 0.982 | 0.830 | -0.2739 |
| 6 | 351 | 40.7% | 0.963 | 0.838 | -0.2604 |
| 7 | 297 | 39.1% | 0.897 | 0.793 | -0.3389 |
| 8 | 319 | 44.2% | 1.109 | 0.952 | -0.0736 |

**Fold PF_net:** min=0.664, max=1.111, profitable folds = 1/8. EV_net sign flips: 1 pos / 7 neg.

## 4. Per-year era breakdown (net of cost)

| Year | Trades | Win% | PF_clean | PF_net | EV_net |
|---|---:|---:|---:|---:|---:|
| 2021 | 3 | 100.0% | inf | inf | +3.3251 |
| 2022 | 601 | 40.6% | 0.957 | 0.863 | -0.2164 |
| 2023 | 804 | 41.3% | 0.985 | 0.861 | -0.2195 |
| 2024 | 760 | 40.4% | 0.949 | 0.809 | -0.3109 |
| 2025 | 620 | 41.9% | 1.011 | 0.881 | -0.1859 |
| 2026 | 110 | 43.6% | 1.084 | 0.947 | -0.0802 |

## 5. Cost sensitivity (full sample, PF_net)

| Cost multiple | PF_net | EV_net |
|---|---:|---:|
| 0.0× (clean) | 0.981 | -0.0280 |
| 1.0× (base) | 0.857 | -0.2267 |
| 1.5× | 0.802 | -0.3261 |
| 2.0× | 0.750 | -0.4254 |

## Verdict (gates)

- **G1 Full-sample PF_net ≥ 1.05** (a real, cost-survivable edge)
- **G2 Walk-forward: ≥ 6/8 folds PF_net ≥ 1.0** (stable across time, no sign flips)
- **G3 Recent era (2025-2026) PF_net ≥ 1.0** (edge is not only historical)
- **G4 Majority of symbols PF_net ≥ 1.0** (not carried by one pair)

If G1-G4 fail, MACD-M15's edge is NOT confirmed under live costs → stop layering machinery on it; per the Phase 4a meta-finding, no price-only H1/M15 technical strategy in this project has a reliable edge.

## VERDICT — 🔴 EDGE NOT CONFIRMED. All four gates FAIL.

| Gate | Threshold | Actual | Result |
|---|---|---|:--:|
| G1 Full-sample PF_net | ≥ 1.05 | **0.857** | ❌ FAIL |
| G2 Walk-forward folds PF_net ≥ 1.0 | ≥ 6/8 | **1/8** | ❌ FAIL |
| G3 Recent era (2025/2026) PF_net | ≥ 1.0 | 0.881 / 0.947 | ❌ FAIL |
| G4 Symbols PF_net ≥ 1.0 | ≥ 4/7 | **1/7** (XAUUSD only, 1.021) | ❌ FAIL |

### What the numbers say

1. **No edge even before costs.** Over the FULL ~100k-bar sample the *clean* PF is
   **0.981 < 1.0** (EV −0.028 ATR/trade). The earlier "PF 1.03" was a **tail
   artifact** of the recent 30k bars — Phase 5a's suspicion is confirmed: the edge
   flips sign with the window because there is no edge, only noise around 0.98.

2. **Costs turn a non-edge clearly negative.** Spread+slippage is **11–35% of median
   ATR** on M15 (vs a far smaller share on H1). That drag drops PF 0.981 → **0.857**
   and EV to **−0.227 ATR/trade**. At 1.5× cost it is 0.802; this is not close.

3. **Not stable, not recent, not broad.** Only **1 of 8** time-folds is profitable
   net (fold 1, the oldest); 7 of 8 lose. Every calendar year 2022–2026 is net
   negative. **6 of 7 symbols** lose net; only XAUUSD scrapes PF 1.02 — i.e. the
   whole "edge" is one instrument at break-even, indistinguishable from luck.

### Decision

- **MACD-M15 has no confirmed, cost-survivable edge.** Do not ship vol-scaled
  sizing (Phase 5a) or any other machinery on top of it — there is no edge to
  protect or amplify.
- **This directly affects the live engine.** MACD-M15 is the strategy shipped on
  2026-06-02 (unfreeze decision) as the running STABLE_v3-M15 signal source. This
  re-validation says that source is **break-even-to-negative under realistic
  costs**. Continuing to collect paper trades on it is fine for *process*
  evidence, but it should NOT be a candidate for capital scaling at the Phase 8/9
  gates on these results.
- **Confirms the Phase 4a meta-finding in full:** across MACD, SMA, RSI, Donchian
  breakout, and ml_direct, **no price-only H1/M15 technical strategy in this
  project has a reliable edge.** The rescue has now exhausted the price-only-TA
  hypothesis space.

### Recommended next move (beyond price-only H1/M15 TA)

Stop adding TA variants on the same bars. The two information-bearing directions
the evidence has *not* ruled out:
- **(a) Higher timeframe / different horizon** — D1 trend or swing structure is
  different information, less spread-sensitive, and not yet tested rigorously here.
- **(b) Non-price information** — carry/rate differentials, cross-asset signals,
  session/seasonality. The TSMOM crypto-momentum line (v4 Phase 10) was a step in
  this direction; it diversifies (ρ=0.13) even if its own OOS was marginal.

Caveats: clean ATR-exit sim (no intrabar path within a bar, no partial fills, no
trade-management/breakeven/trailing that the live engine applies). Management
could move PF a few points, but cannot manufacture an edge from a 0.86 base across
2,898 trades and 8 folds.