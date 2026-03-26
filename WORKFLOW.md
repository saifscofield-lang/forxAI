# ForexAI Strategy Lifecycle & Continuous Improvement Workflow
### Version 1.0 — March 27, 2026

---

## Overview

This document defines the systematic process for evaluating, improving, freezing, and building trading strategies. It eliminates ad-hoc decision-making and ensures every change is data-driven.

---

## 1. Strategy Lifecycle

Every strategy follows this pipeline:

```
BACKTEST → PAPER → ACTIVE → FROZEN / RETIRED
```

| Stage | Description | Exit Criteria |
|---|---|---|
| **BACKTEST** | Test on historical data only | Profit Factor > 1.3 AND WR > 35% AND 200+ simulated trades |
| **PAPER** | Live on demo account, small size | 30+ trades AND Expected Value > 0 |
| **ACTIVE** | Full position sizing on live | Ongoing monitoring |
| **FROZEN** | Temporarily stopped (poor performance) | Review after 2 weeks or market regime change |
| **RETIRED** | Permanently removed | After 2 freeze cycles with no improvement |

**Note:** Shadow mode is skipped while on demo account. Re-introduce when moving to live.

---

## 2. Real-Time Auto-Freeze (Circuit Breaker)

The trading engine monitors every strategy in real-time and auto-freezes when:

| Trigger | Condition | Action |
|---|---|---|
| **Losing Streak** | 5 consecutive losses | Freeze strategy immediately |
| **Negative EV** | Expected Value < 0 on last 20 trades | Freeze strategy |
| **Drawdown** | Strategy drawdown > 3% of account | Freeze strategy |
| **Daily Loss** | Strategy loses > $500 in one day | Freeze for rest of day |

### Expected Value Formula:
```
EV = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
```
If EV < 0, the strategy is expected to lose money over time regardless of WR.

### When Frozen:
- Strategy stops generating signals immediately
- Telegram notification sent with reason
- Entry added to improvements.db
- Review scheduled in 2 weeks

### Unfreeze Criteria:
- Market regime changed (trending ↔ ranging)
- Parameters adjusted based on analysis
- Backtested on recent data with EV > 0

---

## 3. Performance Metrics (What We Measure)

### Primary Metrics (Decision-Making):
| Metric | Formula | Good | Bad |
|---|---|---|---|
| **Expected Value** | (WR × AvgWin) - (LR × AvgLoss) | > 0 | < 0 → freeze |
| **Profit Factor** | Gross Profit / Gross Loss | > 1.3 | < 1.0 → freeze |
| **Max Drawdown** | Largest peak-to-trough | < 3% | > 5% → freeze |

### Secondary Metrics (Analysis):
| Metric | Purpose |
|---|---|
| Win Rate | Context only — meaningless without R:R |
| Risk/Reward Ratio | Avg Win / Avg Loss |
| Sharpe Ratio | Risk-adjusted return |
| TP Hit Rate | Percentage of trades reaching take profit |
| Time to SL | How fast losing trades hit stop loss |

### Benchmark Comparison:
Every strategy is compared against:
- **Baseline:** Account balance with zero trading (0% return)
- **Best strategy:** MACD Crossover (current champion)
- If a strategy underperforms baseline for 30+ trades → retire

---

## 4. Weekly Review Process

**When:** Every Sunday before market opens
**Duration:** 30 minutes
**Output:** Telegram report + improvements.db entries

### Review Checklist:

**A. Performance Summary (per strategy):**
- [ ] Trades this week / Total trades
- [ ] PnL this week / Cumulative PnL
- [ ] EV, Profit Factor, WR, R:R
- [ ] Any auto-freeze triggers hit?

**B. Symbol Health:**
- [ ] PnL per symbol this week
- [ ] Any symbol with 3+ consecutive losses?
- [ ] Worst symbol action: reduce risk / disable / keep

**C. Time Patterns:**
- [ ] Any new bad hours discovered?
- [ ] Session filter effectiveness
- [ ] News filter blocks count

**D. ML Model Health (when active):**
- [ ] Prediction accuracy vs actual outcomes
- [ ] Confidence distribution (too many low-confidence signals?)
- [ ] Drift detection: is model degrading?

**E. Decisions:**
- [ ] Strategies to freeze/unfreeze
- [ ] Parameter adjustments needed
- [ ] New strategy ideas to backtest

---

## 5. Market Regime Detection

The market operates in different regimes. Strategies perform differently in each:

| Regime | Characteristics | Best Strategies |
|---|---|---|
| **Trending** | ADX > 25, clear direction | MACD, Momentum |
| **Ranging** | ADX < 20, price in channel | RSI Reversal, Bollinger |
| **Volatile** | ATR > 1.5x average | Breakout strategies |
| **Quiet** | ATR < 0.7x average | Avoid trading or tight ranges |

### Detection Method:
```
1. ADX(14) on H4 timeframe
2. ATR(14) vs ATR(14) 20-period SMA
3. Bollinger Band Width trend
```

### Application:
- Each scan cycle determines current regime
- Only strategies suited for current regime generate signals
- Log regime with every trade for post-analysis

### Implementation Priority: Phase 2 (after ML training)

---

## 6. Strategy Improvement Process

### When to Improve (not rebuild):
- EV > 0 but declining over last 30 trades
- WR dropped 10%+ from historical average
- Specific pattern found (bad hours, bad symbol, RSI zone)

### Improvement Steps:
1. **Identify** — Which metric is declining? Since when?
2. **Hypothesize** — What changed? (Market regime? Spread? Volatility?)
3. **Backtest** — Test proposed fix on last 3 months of data
4. **Compare** — New params vs old params on same data
5. **Apply** — If improvement > 10%, update parameters
6. **Monitor** — Track for 20 trades, compare to baseline

### Parameter Changes to Consider:
- SL/TP multipliers (from MFE/MAE analysis)
- RSI entry bands (from winner/loser RSI distribution)
- ATR filters (minimum/maximum volatility)
- Session hours (from hourly performance data)
- Symbol allocation (concentrate on winners)

---

## 7. New Strategy Development

### When to Build New:
- Gap in regime coverage (no ranging strategy active)
- Consistent pattern in data not captured by existing strategies
- Best symbol (AUDUSD) doesn't have a dedicated strategy

### Development Process:
1. **Data-Driven Idea** — Must come from trade analysis, not theory
2. **Define Rules** — Entry, exit, SL, TP, filters (all must be specific)
3. **Backtest** — Minimum 200 trades on 6+ months of data
4. **Walk-Forward** — Out-of-sample validation on last month
5. **Paper Trade** — 30+ live trades on demo
6. **Evaluate** — Meets lifecycle criteria? → ACTIVE or RETIRED

### Current Pipeline:
| Strategy Idea | Source | Status | Priority |
|---|---|---|---|
| AUDUSD Momentum Rider | 77.8% WR on AUDUSD | Idea | High |
| XAUUSD Volatility Breakout | Big wins on XAUUSD breakouts | Idea | High |
| London Open Scalper | 07:00-11:00 UTC best hours | Idea | Medium |
| RSI-ATR Confluence | Winner RSI/ATR patterns | Idea | Medium |

---

## 8. ML Training Pipeline

### First Training:
- **Trigger:** 200+ closed trades collected
- **Target:** June 2026
- **Model:** LightGBM classifier (profitable yes/no)
- **Features:** RSI, ATR, MACD, BB Width, hour, day, spread, regime

### Retraining Triggers (not time-based):
| Trigger | Condition |
|---|---|
| **Performance Decay** | ML-filtered WR drops 10%+ from baseline |
| **Data Growth** | 100+ new trades since last training |
| **Regime Shift** | Market regime changed for 2+ weeks |
| **New Features** | New indicators or data sources added |

### Training Process:
1. Export all trades with features from DB
2. Split: 70% train, 15% validation, 15% test (time-ordered, no shuffle)
3. Walk-forward: train on months 1-3, test on month 4, slide window
4. Compare new model vs current model on last 30 days
5. Deploy only if new model has higher Profit Factor AND lower drawdown
6. Keep old model as fallback for 2 weeks

### ML Model Health Monitoring:
- Track prediction accuracy weekly
- If accuracy < 55% for 2 consecutive weeks → retrain
- If retrained model also < 55% → disable ML filter, use rule-based only

---

## 9. Configuration Management

### Current Active Config:
```yaml
strategies:
  macd_crossover:  ACTIVE (all 7 symbols)
  rsi_reversal:    ACTIVE (5 symbols, excluded: XAUUSD, USDCAD)
  bollinger_bounce: RETIRED (IMP-49: -$3,127)
  sma_crossover:   RETIRED (IMP-03: -$1,522)
  ml_direct:       PAPER (insufficient data)

symbols:
  AUDUSD:  ACTIVE (star performer)
  EURUSD:  ACTIVE
  GBPUSD:  ACTIVE
  USDCHF:  ACTIVE
  USDJPY:  ACTIVE
  USDCAD:  ACTIVE (under watch: -$1,998)
  XAUUSD:  ACTIVE (MACD only)
  NZDUSD:  RETIRED (IMP-48: -$3,336)
```

### Before Going Live (IMP-27):
- [ ] Separate paper vs live config files
- [ ] Live config starts with 50% position size
- [ ] 30-day parallel run: paper + live
- [ ] Kill switch: one command stops all live trading

---

## 10. Decision Tree — Quick Reference

```
Every Week:
  └─ Run weekly review
      ├─ Strategy EV < 0 on last 20 trades?
      │   └─ YES → FREEZE immediately
      ├─ Symbol lost 3+ in a row?
      │   └─ YES → Reduce risk to 0.5% or disable
      ├─ New bad hour pattern?
      │   └─ YES → Add to session filter
      ├─ ML accuracy < 55%?
      │   └─ YES → Retrain or disable ML
      └─ 200+ trades collected?
          └─ YES → Train/retrain ML models

Every Trade:
  └─ Check circuit breakers
      ├─ 5 consecutive losses? → FREEZE
      ├─ Daily loss > $500? → FREEZE for today
      └─ Strategy drawdown > 3%? → FREEZE
```

---

## Appendix: File Locations

| File | Purpose |
|---|---|
| `config/base.yaml` | Active instruments, risk params, session hours |
| `data/optimized_params.yaml` | Per-symbol SL/TP/indicator parameters |
| `data/improvements.db` | All improvements tracked with status |
| `data/trading.db` | Trade results, signals, account snapshots |
| `data/reports/strategy_improvement_guide.md` | Latest analysis report |
| `scripts/paper_trade.py` | Main trading loop |
| `WORKFLOW.md` | This file — the process guide |

---

*Last Updated: 2026-03-27 | Next Review: 2026-04-03*
