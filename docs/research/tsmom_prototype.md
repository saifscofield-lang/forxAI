# TSMOM Prototype — Results

_Run: 2026-04-17T14:06:55_  
_Source: Moskowitz/Ooi/Pedersen (2012) + AQR (2017)_  
_Data: D1 → monthly close, 7 pairs, 2012-02-29 → 2026-04-30 (171 months)_  
_Parameters: 12m lookback momentum · 24m vol window · 10% target vol · 1.0× max leverage_

## Portfolio result — ❌ POOR

| Metric | Value | AQR benchmark |
|---|---:|---:|
| Sharpe ratio | **0.126** | ~0.7 |
| Annual return | +0.61% | ~10% |
| Annual volatility | 4.82% | ~10% (target) |
| Max drawdown | -15.4% | ~-25% |
| CAGR | 0.49% | — |
| Sortino | 0.198 | — |
| Hit rate | 48.5% | ~55-60% |
| Best month | +3.64% | — |
| Worst month | -5.20% | — |

## Per-pair breakdown

| Pair | Months | Ann Ret | Ann Vol | Sharpe | Max DD | Hit% | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| `EURUSD` | 171 | -0.1% | 7.3% | -0.01 | -26.0% | 51% | ❌ POOR |
| `GBPUSD` | 171 | -0.6% | 8.0% | -0.07 | -22.7% | 46% | ❌ POOR |
| `USDJPY` | 171 | +3.2% | 9.0% | +0.35 | -24.1% | 56% | ❌ MARGINAL |
| `XAUUSD` | 171 | +3.8% | 10.9% | +0.35 | -31.3% | 51% | ❌ MARGINAL |
| `USDCHF` | 171 | -2.1% | 7.6% | -0.27 | -41.0% | 47% | ❌ POOR |
| `AUDUSD` | 171 | +0.5% | 9.3% | +0.05 | -22.1% | 46% | ❌ POOR |
| `USDCAD` | 171 | -0.5% | 7.3% | -0.07 | -31.1% | 46% | ❌ POOR |

## Interpretation

**TSMOM weak on your data.** Sharpe < 0.5 is below the AQR threshold. 
Possible causes: FX has entered a lower-trending regime, your 7 pairs have 
high correlation reducing diversification. Before dropping TSMOM, try: 
(a) longer momentum lookback (9-15mo instead of 12), (b) adding non-USD 
crosses for diversification.

## v3.0 plan implications

- TSMOM may not justify its operational complexity.
- Consider: stick with the simpler Primary+Meta-Labeler (even if lift is small).
