# v4 Framework — From Signal Hunting to Portfolio Engineering

_Strategic blueprint for the next iteration after v3.0_  
_Date: 2026-04-19_

---

## Executive Summary

**v3.0 verdict:** Methodologically sound, results within realistic range for retail FX algo trading, but ceiling is structurally limited. Best-case Sharpe ~0.5-0.7, with brittle edge concentrated in narrow combos.

**v4 thesis:** The path forward is not better signals on the same playing field. It is a **different playing field entirely** — multi-asset, multi-strategy, alternative data, with portfolio construction as the primary edge rather than signal quality.

**Realistic v4 target:** Sharpe 0.8-1.0, max DD -15% to -20%, low correlation to S&P 500. This places the system in the top 5% of retail algorithmic traders.

---

## Why v3.0 Has a Ceiling

| Constraint | v3.0 Reality | Structural Limit |
|---|---|---|
| Asset class | FX spot only | Most efficient market on Earth |
| Timeframe | H1 | Most crowded retail timeframe |
| Data source | OHLC + indicators | Same data 10M traders see |
| Strategy count | 2 (MACD, RSI) | High concentration risk |
| Edge source | Pattern detection | Decayed by HFT decades ago |
| Counterparty | Banks + HFT funds | Strongest opponents in finance |

v3.0's results (35-50% WR on MACD/RSI, +7pp meta-labeler lift on RSI) match academic benchmarks. The ceiling is the **playing field itself**, not the implementation.

---

## v4 Philosophy: Five Paradigm Shifts

### Shift 1: From "Find Signals" to "Build Portfolios"

The pros do not chase magic signals. They build portfolios where mediocre individual strategies combine into a strong system through low correlation.

**Mathematical insight:**  
Two strategies with Sharpe 0.5 and correlation 0.0 → combined Sharpe ≈ 0.7  
Two strategies with Sharpe 0.5 and correlation -0.3 → combined Sharpe ≈ 0.85  
Adding a 0.3 Sharpe uncorrelated strategy can lift the portfolio Sharpe.

**v4 implication:** Stop searching for the perfect WR 60% strategy. Start searching for 5 mediocre strategies that hate each other.

### Shift 2: From "FX H1" to "Underexploited Niches"

| Niche | Why Underexploited | Realistic Edge |
|---|---|---|
| Crypto momentum (D1/W1) | Pros still cautious post-2022 | Sharpe 0.8-1.5 documented |
| Small-cap equity drift | Too small for institutions | 5-10% annual alpha |
| Commodity futures trend | Requires capital + expertise | Sharpe 0.6-1.0 |
| Crypto basis/funding | New market, evolving | Risk-free 5-15% APR windows |
| Volatility selling (defined risk) | Tail risk scares retail | Sharpe 0.7-1.2 |
| FX EM carry | Operational complexity | Sharpe 0.5-0.8 |

The rule: if a space has 1000 papers and 10 quant funds, you are 20 years late. Find spaces with 5 papers and 0 funds.

### Shift 3: From "OHLC Indicators" to "Alternative Data"

What retail can actually access (with technical skill, not capital):

| Data Source | Cost | Edge Potential |
|---|---|---|
| On-chain crypto data (Glassnode free tier, Dune) | Free-$50/mo | Whale tracking, exchange flows |
| Funding rates across exchanges | Free (ccxt) | Basis arbitrage signals |
| Reddit/Twitter sentiment (modern NLP) | $20-100/mo | Event-driven equity |
| Google Trends API | Free | Macro nowcasting |
| SEC EDGAR filings (real-time) | Free | Insider transactions, 8-K events |
| Options open interest unusual activity | $50-200/mo | Smart money flow |
| Order book imbalance (crypto) | Free via WebSockets | Microstructure edge |

You have the technical skills. This is your real edge over 95% of retail.

### Shift 4: From "Static Models" to "Regime-Aware Systems"

v3.0 trains a model once on 6 years of data. v4 acknowledges that markets have regimes:

```
Regime Detection Layer:
  ├─ Trend regime: HMM on rolling returns
  ├─ Volatility regime: GARCH on realized vol
  ├─ Correlation regime: rolling corr matrix
  └─ Macro regime: nowcast indicators

Strategy Activation:
  Bull trend  → momentum strategies fully on, mean-rev off
  Bear trend  → defensive: short vol off, trend on
  Range-bound → mean-rev on, momentum reduced
  Crisis      → all off, cash position
```

### Shift 5: From "Optimization" to "Robustness"

Most retail backtests overfit. v4 enforces:

- **Walk-forward only** (no full-sample optimization)
- **Combinatorial purged cross-validation** (López de Prado)
- **Deflated Sharpe ratio** to penalize multiple testing
- **Out-of-sample period must equal at least 30% of total data**
- **Each strategy stress-tested across regimes (2008, 2020, 2022)**

A strategy that loses money in 2008 but makes money in 2010-2019 is rejected, not celebrated.

---

## v4 Architecture (Concrete)

### Layer 1: Strategy Stack (5-7 uncorrelated strategies)

```
Asset Class       Strategy Type         Timeframe   Expected Sharpe
─────────────────────────────────────────────────────────────────
Crypto            Momentum (D/W)        Daily       0.8-1.2
Crypto            Funding rate basis    8h          0.5-0.9
FX majors         RSI mean-reversion    H1-H4       0.3-0.6 (v3.0 carryover)
Commodity futures Trend following       Daily       0.4-0.8
Small-cap equity  Earnings drift        Event       0.5-0.9
VIX futures       Vol risk premium      Daily       0.6-1.0
EM FX             Carry trade           Weekly      0.4-0.7
```

Target portfolio Sharpe: 0.9-1.2 after correlation benefits.

### Layer 2: Risk Parity Allocation

```python
# Pseudo-code
weights = {}
for strategy in strategies:
    vol = strategy.realized_vol(window=60)
    weights[strategy] = 1 / vol

# Normalize to sum to 1
total = sum(weights.values())
weights = {s: w/total for s, w in weights.items()}

# Cap individual exposure
weights = {s: min(w, 0.30) for s, w in weights.items()}

# Rebalance monthly
```

This ensures no single strategy dominates risk. A high-vol strategy gets less capital, even if its expected return is higher.

### Layer 3: Regime Overlay

```python
def adjust_exposure(base_weights, regime):
    if regime == 'crisis':
        return {s: 0 for s in base_weights}  # Cash
    elif regime == 'high_vol':
        return {s: w * 0.5 for s, w in base_weights.items()}
    elif regime == 'normal':
        return base_weights
    elif regime == 'low_vol_trending':
        return {s: w * 1.2 for s, w in base_weights.items()}
```

### Layer 4: Drawdown Circuit Breakers

```
Portfolio DD <  5%:  Normal operation
Portfolio DD  5-10%: Reduce leverage 25%
Portfolio DD 10-15%: Reduce leverage 50%
Portfolio DD 15-20%: Pause new entries, manage existing
Portfolio DD >  20%: Full stop, mandatory 30-day review
```

### Layer 5: Continuous Learning

- Online learning for ML components (incremental updates, not full retrains)
- Bayesian updating of strategy priors based on live performance
- A/B testing framework: every change runs in shadow mode for 30 days before going live
- Performance attribution: which strategy contributed what to PnL each month

---

## Infrastructure Requirements

### From (v3.0)
- MetaTrader 5
- Python scripts on local machine
- CSV/Parquet data
- Manual backtest runs

### To (v4)
- **Brokerage:** Interactive Brokers (multi-asset) + crypto exchange (Binance/Bybit)
- **Data:** Polygon.io ($79/mo) or Tiingo ($30/mo) + free crypto via ccxt
- **Backtesting:** vectorbt (Python) or zipline-reloaded
- **Execution:** IBKR API + ccxt for crypto, async event loop
- **Database:** TimescaleDB or DuckDB for time-series
- **Monitoring:** Grafana dashboards + alerting (Telegram/Discord)
- **Deployment:** VPS (DigitalOcean droplet $20/mo) for 24/7 execution
- **Version control:** Git + DVC for data versioning

Total monthly cost: ~$130-250/mo. Justified only if portfolio > $20k.

---

## Roadmap (Realistic Timeline)

| Quarter | Focus | Deliverable |
|---|---|---|
| **Q2 2026** (now) | Finish v3.0 honestly | Paper trading results, lessons learned |
| **Q3 2026** | v4 research + niche selection | Pick 3 asset classes, prototype 1 strategy each |
| **Q4 2026** | Build infrastructure | IBKR connection, backtest framework, regime detection |
| **Q1 2027** | Strategy development | 5 strategies prototyped, walk-forward tested |
| **Q2 2027** | Integration | Risk parity layer, regime overlay, paper trading start |
| **Q3 2027** | Paper trading | Minimum 90 days live paper, all systems exercised |
| **Q4 2027** | Live deployment | Small capital ($5-10k), validate execution quality |
| **2028+** | Scale | Add capital gradually as live Sharpe confirms backtest |

**Total time to live v4: ~18 months.** This is the honest timeline. Anything faster is shortcut-taking that will cost more later.

---

## Honest Expectations

### What v4 Can Realistically Achieve

- **Sharpe 0.8-1.0** (top 5% of retail algo)
- **12-18% annual returns** with disciplined risk management
- **Max drawdown -15% to -20%**
- **Low correlation to traditional assets** (good portfolio diversifier)
- **Resilience across regimes** (won't blow up in 2008-style events)

### What v4 Cannot Achieve

- **Sharpe > 2** (Renaissance territory, not retail)
- **No drawdowns** (impossible)
- **Quick riches** (it's a 5-10 year compounding game)
- **Replacement of full-time income immediately** (capital constraint)
- **Beating Medallion Fund** (don't even try)

### Honest Capital Math

With Sharpe 0.9 and 15% annual return:
- $10k capital → +$1,500/year average
- $50k capital → +$7,500/year average  
- $200k capital → +$30,000/year average
- $1M capital → +$150,000/year average

**The system needs capital to matter.** A perfect system on $5k is intellectually satisfying but financially trivial. Plan capital growth alongside system development.

---

## The Five Edges That Compound

### Edge 1: Niche Selection
You play where giants cannot fit. Renaissance cannot trade $50k positions in small-cap stocks — you can.

### Edge 2: Alternative Data
You use data sources retail ignores and institutions cannot scale. On-chain crypto data is free and underexploited.

### Edge 3: Portfolio Construction
You combine mediocre strategies into a strong system through correlation engineering, not signal hunting.

### Edge 4: Operational Discipline
You follow your system through drawdowns. 99% of retail abandons systems in drawdown. The 1% who don't, compound.

### Edge 5: Time
You have 10-30 year horizons. Funds need monthly reports. This asymmetry is your largest structural advantage.

**These five edges compound. None alone makes you rich. Together, over a decade, they place you in the top percentile of retail outcomes.**

---

## What This Document Is Not

- **Not a guarantee.** Markets evolve. v4 may need v5 by 2030.
- **Not financial advice.** Run your own validation.
- **Not a get-rich path.** This is a 5-10 year discipline.
- **Not a replacement for v3.0 immediately.** Finish v3.0 first to extract its lessons.

---

## The Honest Question to Ask Yourself

Before committing to v4, answer truthfully:

1. Do I have 5+ years of patience for this to compound?
2. Am I willing to study new asset classes (crypto, equities, options)?
3. Can I tolerate -20% drawdowns without abandoning the system?
4. Is my capital growth plan realistic alongside system development?
5. Am I doing this because it's intellectually right, or because I want to "beat" something?

If the answers are honest yeses, v4 is worth pursuing.

If you find yourself rationalizing, the index fund route is not failure — it is wisdom.

---

## Final Note

**The pros do not have a magic strategy.** They have:
- Discipline
- Diversification
- Patience
- Capital
- Time

You can develop four of these five. Capital comes from elsewhere (job, business, savings). Build the four, deploy them when capital arrives, and let compounding do its work.

**v4 is not about being smarter than the market. It is about being more disciplined than other retail traders, in spaces the institutions cannot reach, over timeframes they cannot honor.**

That is the only path. There is no other.

---

## Status Log

| Date | Entry |
|---|---|
| 2026-04-21 | Phase 10 steps 1-5 complete. Step 3 (8 in-sample variants): best LO/12m Sharpe 1.06, all variants clear 0.4 gate IS. Step 4 (OOS) RED: primary 2/4 gates, secondary (LO/12w) 3/4 gates — drift-stability gate failed on both (train 1.27 → OOS 0.03/0.55) due to 2025-2026 bear regime. Step 5 correlations: ρ(FX)=0.13, ρ(SPY)=0.21, ρ(BTC OOS)=0.57 — Option-4 diversification threshold met. Phase 10.5 (regime-filter rescue) seeded as conditional phase, PENDING_ACTIVATION. Formal go/no-go deferred pending Phase 10.5 results. |
