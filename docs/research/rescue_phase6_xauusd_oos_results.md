# Rescue Plan — Phase 6: XAUUSD + D1 Filter — OOS Results

**Pre-registered:** docs/research/rescue_phase6_xauusd_prereg.md (gates fixed before run).
**Data:** XAUUSD 99,967 M15 bars, D1-filtered MACD-M15 (EMA50>EMA200), ATR(1.2), SL/TP 2.5/3.5×ATR, horizon 100, base cost 0.38 price/trade. PF_net = after cost.

## X1 — Chronological 70/30 split

| Segment | Trades | Win% | PF_clean | PF_net | EV_net |
|---|---:|---:|---:|---:|---:|
| Train (first 70%) | 158 | 46.8% | 1.233 | 1.126 | +0.1760 |
| **OOS (last 30%)** | 60 | 55.0% | 1.711 | **1.629** | +0.7294 |

**X1 gate:** OOS PF_net 1.629 ≥ 1.05 → ✅ PASS

## X2 — Walk-forward (8 contiguous folds)

| Fold (old→new) | Trades | Win% | PF_clean | PF_net | EV_net |
|---|---:|---:|---:|---:|---:|
| 1 | 26 | 61.5% | 2.240 | 2.017 | +1.0346 |
| 2 | 29 | 34.5% | 0.737 | 0.670 | -0.5713 |
| 3 | 27 | 44.4% | 1.120 | 1.024 | +0.0345 |
| 4 | 21 | 42.9% | 1.050 | 0.937 | -0.0957 |
| 5 | 37 | 54.1% | 1.647 | 1.526 | +0.6312 |
| 6 | 35 | 42.9% | 1.050 | 0.979 | -0.0318 |
| 7 | 22 | 59.1% | 2.022 | 1.928 | +0.9777 |
| 8 | 21 | 57.1% | 1.867 | 1.810 | +0.8844 |

**X2 gate:** 5/8 folds PF_net ≥ 1.0 (need ≥6/8) → ❌ FAIL

## X3 — Regime robustness

| Era | Trades | Win% | PF_clean | PF_net | EV_net |
|---|---:|---:|---:|---:|---:|
| 2022-2024 (gold bull) | 161 | 46.6% | 1.221 | 1.115 | +0.1620 |
| 2025-2026 (recent) | 56 | 55.4% | 1.736 | 1.655 | +0.7531 |

**X3 gate:** both PF_net ≥ 1.0 (1.115 & 1.655) → ✅ PASS

## X4 — Cost stress (full sample)

| Cost multiple | Trades | PF_net | EV_net |
|---|---:|---:|---:|
| 1.0× | 218 | 1.246 | +0.3283 |
| 1.5× | 218 | 1.198 | +0.2700 |
| 2.0× | 218 | 1.152 | +0.2117 |

**X4 gate:** PF_net at 1.5× cost = 1.198 ≥ 1.0 → ✅ PASS

## X5 — D1 filter adds value (OOS segment)

| OOS config | Trades | Win% | PF_net |
|---|---:|---:|---:|
| Unfiltered MACD-M15 | 93 | 47.3% | 1.200 |
| + D1 filter | 60 | 55.0% | 1.629 |

**X5 gate:** filtered 1.629 > unfiltered 1.200 → ✅ PASS

## VERDICT

| Gate | Result |
|---|:--:|
| X1 | ✅ PASS |
| X2 | ❌ FAIL |
| X3 | ✅ PASS |
| X4 | ✅ PASS |
| X5 | ✅ PASS |

**4/5 gates passed.** Overall: 🔴 FAIL — price-only-TA hypothesis closed; pivot to non-price information

Per the pre-registered decision rule, any single failure closes the price-only-TA hypothesis. Do NOT add more TA variants on the same bars; pivot to non-price info (carry/rate-differential, cross-asset, higher-TF structure).

## Honest interpretation (post-hoc — does NOT change the verdict)

**The verdict stands: FAIL by the rule we committed to before running.** We do not
relax X2 now — moving a gate after seeing the result is exactly the Phase 7
mistake (commit 64a3507) this pre-registration existed to prevent.

That said, this fail is **qualitatively different** from the FX majors:
- The FX majors failed 3-4 gates *badly* (pooled PF_net 0.86-0.90, 1-2/8 folds).
- XAUUSD passed **4 of 5** and is strongly positive on aggregate: OOS PF_net
  **1.629**, both regimes positive (1.12 bull / 1.66 recent), survives **2× cost**
  (1.15), and the D1 filter clearly adds value (1.63 vs 1.20 OOS).
- It failed X2 by a single fold (**5/8**, need 6/8) — and 2 of the 3 "failing"
  folds are break-even (0.937, 0.979), not losses. Only fold 2 (0.670) is a real
  drawdown period.

**Why X2 is the right gate to have failed on, and why we still don't relax it:**
the per-fold samples are tiny (n≈21-37 trades) because gold is one symbol at M15
frequency. Small samples make per-fold PF noisy — which is *precisely* why
walk-forward stability is the honest test and why a near-miss on it is not a pass.
A genuinely robust edge would clear 6/8 even with noise; this one doesn't, yet.

**Resolution (not goalpost-moving):** the missing ingredient is *more independent
data*, not a looser gate. Therefore:
1. **For capital/go-no-go decisions, treat price-only TA as CLOSED** (per the
   pre-registered rule). XAUUSD+D1 is NOT confirmed and is NOT capital-eligible.
2. **Gold may be carried as a forward-paper WATCH-ITEM only** — observe it live
   (no real risk scaled to it) to accumulate out-of-sample trades. This is
   monitoring an already-built config, not "adding more TA variants." If, after a
   meaningful forward sample, it clears the SAME gates (especially X2) on the new
   data, re-open the question then.
3. **Primary direction pivots to non-price information** (carry/rate differential,
   cross-asset, higher-TF structure) — the hypothesis space the rescue has shown
   is the only one not yet falsified.