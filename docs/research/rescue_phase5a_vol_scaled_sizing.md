# Rescue Plan — Phase 5a: Volatility-Scaled Sizing — Build & Verify

**Trades:** 2618 MACD-M15 (real ordered TP/SL, R:R=1.40). Sizing fraction scaled by atr_ratio = ATR/mean(ATR,100).

## T-A — Outcome by volatility tercile (are high-vol trades worse?)

| Vol tercile | Trades | Win% | R-PF |
|---|---:|---:|---:|
| LOW vol (calm) | 873 | 40% | 0.93 |
| MID vol | 872 | 40% | 0.92 |
| HIGH vol | 873 | 42% | 1.02 |

(atr_ratio tercile cuts ≈ 1.07 / 1.37)

## T-B — Equity-curve comparison (fixed 1% vs vol-scaled)

| Scheme | Total return | **Max drawdown** | Return/MaxDD | Worst trade | P&L std |
|---|---:|---:|---:|---:|---:|
| Fixed 1% | -57.2% | **72.4%** | -0.79 | -1.00% | 1.179% |
| Vol-scaled (defensive, cap 1.0) | -55.8% | **68.9%** | -0.81 | -0.99% | 0.975% |
| Vol-scaled (symmetric, cap 1.5) | -55.6% | **70.1%** | -0.79 | -1.21% | 1.029% |

## Robustness — max drawdown per time block (fixed vs defensive)

| Block | Fixed MaxDD | Vol-scaled MaxDD |
|---|---:|---:|
| 1 | 60.8% | 56.3% |
| 2 | 44.4% | 39.1% |
| 3 | 35.2% | 28.9% |

## Acceptance (defensive variant — matches the 'avoid big losses' goal)

- A1 max drawdown reduced: 72.4% → 68.9% (+5%) → PASS
- A2 return/MaxDD not worse: -0.79 → -0.81 → FAIL
- A3 retains ≥80% of return: 97% → PASS
- A4 worst single trade smaller: -1.00% → -0.99% (+1%) → PASS

## VERDICT: MIXED — see notes

Caveat: clean sim excludes gaps/slippage, so the real high-vol protection is LARGER than shown — this drawdown reduction is a conservative lower bound. If shipped: scale max_risk_per_trade by clip(1/atr_ratio, 0.33, 1.0) in RiskManager.calculate_position_size.

## 🔴 BIGGER FINDING — vol-scaling is moot because MACD-M15 has no robust edge

The numbers above expose something more important than sizing:

- Over this **90k-bar** sample, MACD-M15 has **base win-rate 40.6% → R-PF ≈ 0.96
  and total return −57%** (a near-random walk with slight NEGATIVE drift; that is
  why the drawdown is ~72%, not because of sizing).
- T-A shows high-vol trades are **NOT worse** (42% vs 40%) — so the premise that
  big losses come from high volatility does not hold here. Vol-scaling has almost
  nothing to work with: it trims maxDD by only ~5% and slightly worsens
  return/DD. **Sizing cannot fix a strategy that has no edge.**

**Sample dependence is the real issue.** Phase 1f measured MACD-M15 at PF 1.03 on
the recent 30k bars; over 90k it is ~0.96. The "edge" straddles break-even and
flips sign with the window → it is **within noise, not a confirmed edge.** The
per-block drawdowns (60% → 44% → 35%, oldest → newest) hint performance is merely
*less bad* recently, not reliably positive.

### Honest conclusion
1. **Do NOT ship vol-scaled sizing as a fix** — it is a ~5% cosmetic on a
   non-edge; it does not address the owner's loss concern in any material way.
2. **MACD-M15's edge is unconfirmed.** Before relying on it (or layering sizing/
   management on it), it must be re-validated rigorously: walk-forward R-PF across
   the full sample, recent-vs-old eras, and WITH spread/slippage. If it is truly
   break-even-to-negative, then — consistent with the Phase 4a meta-finding —
   **no price-only H1/M15 technical strategy in this project has a reliable edge**,
   and the right move is to stop adding machinery and reconsider the data/approach
   (or accept paper-only evaluation with no live deployment).