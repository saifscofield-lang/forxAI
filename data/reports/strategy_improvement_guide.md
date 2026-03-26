# ForexAI Strategy Improvement Guide
### Based on 119 Trades & 358 Signals Analysis (March 18-27, 2026)

---

## 1. Executive Summary

| Metric | Value |
|---|---|
| Total Trades | 119 |
| Win Rate | 47.1% (56W / 63L) |
| Total PnL | +$17,458 |
| Avg Win | +$756 |
| Avg Loss | -$395 |
| Risk/Reward | 1.91:1 |
| Best Trade | +$11,916 (XAUUSD MACD) |
| Worst Trade | -$1,040 (EURUSD BB) |
| Signals Generated | 358 |
| Execution Rate | 33.2% (119/358) |

**Warning:** One XAUUSD trade (+$11,916) represents 68% of total profit. Without it, PnL = +$5,542.

---

## 2. Strategy Performance

### MACD Crossover — BEST PERFORMER
| Metric | Value |
|---|---|
| Trades | 32 |
| Win Rate | 62.5% |
| PnL | +$15,372 |
| R:R | 2.29:1 |
| TP Hit Rate | 41% |

- Strongest on XAUUSD (+$11,954) and AUDUSD (+$1,610)
- Works better in **high ATR** (volatile) conditions: winners ATR=3.59 vs losers ATR=1.18
- **Recommendation:** Add minimum ATR filter — only trade when ATR > 1.5x average

### RSI Reversal — GOOD R:R
| Metric | Value |
|---|---|
| Trades | 23 |
| Win Rate | 47.8% |
| PnL | +$4,499 |
| R:R | 3.50:1 (BEST) |
| TP Hit Rate | 48% (BEST) |

- Best risk/reward ratio of all strategies
- Winners had RSI=56.4, losers had RSI=34.6
- **Key insight:** Extreme RSI entries (< 35) tend to LOSE. Moderate RSI (45-65) wins more
- Strong on AUDUSD (+$3,850) and USDJPY (+$169)
- **Recommendation:** Avoid entries when RSI < 35 or > 75 — the "deep reversal" trades fail

### SMA Crossover — WEAK (DISABLED)
| Metric | Value |
|---|---|
| Trades | 17 |
| Win Rate | 35.3% |
| PnL | +$619 |
| R:R | 2.09:1 |

- Marginally profitable but low win rate
- Status: Currently disabled — correct decision

### Bollinger Bounce — LOSING (DISABLED)
| Metric | Value |
|---|---|
| Trades | 44 |
| Win Rate | 40.9% |
| PnL | -$3,127 |
| R:R | 1.09:1 |

- Most active strategy but worst performer
- R:R nearly 1:1 — with 41% WR this guarantees losses
- Status: Currently disabled — correct decision
- **If re-enabling:** Needs R:R of at least 2:1 or WR above 55%

### ML Strategies — INSUFFICIENT DATA
- ml_direct: 1 trade, +$156 (100% WR) — too few to judge
- ml_filtered_sma: 2 trades, -$61 (0% WR)
- ml_confidence not being logged for ml_filtered_sma (possible bug)
- **Action:** Fix confidence logging, collect more data before evaluating

---

## 3. Symbol Performance

| Symbol | Trades | WR | PnL | Verdict |
|---|---|---|---|---|
| AUDUSD | 18 | 77.8% | +$7,030 | STAR — best overall |
| XAUUSD | 25 | 32.0% | +$11,625 | High risk, high reward (1 trade = $11.9K) |
| EURUSD | 9 | 55.6% | +$2,340 | Good, stable |
| GBPUSD | 12 | 41.7% | +$1,572 | Acceptable |
| USDCHF | 10 | 50.0% | +$900 | Neutral |
| USDJPY | 17 | 58.8% | -$675 | Wins often but losses are big |
| USDCAD | 11 | 36.4% | -$1,998 | Problem — consider reducing |
| NZDUSD | 17 | 29.4% | -$3,336 | REMOVED (correct decision) |

### Symbol Insights:
- **AUDUSD** is profitable across ALL strategies — increase allocation
- **XAUUSD** profits come almost entirely from MACD — restrict to MACD only
- **USDCAD** loses consistently — 7-trade losing streak recorded, 64% loss rate
- **USDJPY** wins often (59%) but losses are larger than wins — SL too wide

---

## 4. Time Patterns

### Best Hours (UTC)
| Hour | WR | PnL | Note |
|---|---|---|---|
| 07:00 | 100% | +$1,640 | Early London |
| 10:00 | 60% | +$2,843 | London session |
| 11:00 | 67% | +$2,179 | London session |
| 16:00 | 65% | +$3,322 | London/NY overlap |
| 17:00 | 67% | +$11,928 | NY session (includes big XAUUSD trade) |

### Worst Hours (UTC)
| Hour | WR | PnL | Note |
|---|---|---|---|
| 08:00 | 0% | -$1,226 | Early London volatility |
| 15:00 | 31% | -$3,711 | BIGGEST LOSER — 13 trades, mostly losses |
| 13:00 | 20% | -$1,806 | Post-news volatility |
| 23:00 | 0% | -$945 | Late session, low liquidity |

### Day of Week
| Day | Trades | WR | PnL |
|---|---|---|---|
| Monday | 4 | 75% | +$332 |
| Wednesday | 91 | 47% | +$9,024 |
| Thursday | 21 | 38% | -$3,092 |
| Friday | 3 | 67% | +$11,193 |

- **Thursday is the worst day** — consider reducing position size or tightening filters
- Most activity is on Wednesday (91/119 trades)

### Recommendation:
- Avoid or reduce trading at 08:00, 15:00, 23:00 UTC
- Consider a "golden hours" filter: prioritize 07:00, 10:00-11:00, 16:00-17:00

---

## 5. Signal Quality — RSI & ATR Patterns

### RSI at Entry
| Condition | Avg RSI Winners | Avg RSI Losers | Insight |
|---|---|---|---|
| Overall | 49.1 | 43.1 | Winners enter at moderate RSI |
| RSI Reversal | 56.4 | 34.6 | Deep reversals fail |
| USDJPY | 61.1 | 33.6 | Biggest RSI gap |
| XAUUSD | 47.3 | 33.0 | Low RSI entries lose |

**Key Rule:** RSI between 40-65 at entry = higher probability of winning

### ATR at Entry
| Condition | Avg ATR Winners | Avg ATR Losers | Insight |
|---|---|---|---|
| Overall | 1.88 | 3.63 | Lower volatility wins more |
| MACD | 3.59 | 1.18 | EXCEPTION — MACD needs volatility |
| RSI Reversal | 0.04 | 11.89 | High ATR = loss |

**Key Rules:**
- For RSI Reversal: reject signals when ATR > 2x its 20-period average
- For MACD: require minimum ATR > 1x average (needs volatility to work)
- These are opposite — strategy-specific ATR filters needed

---

## 6. Filter Analysis

### H4 Trend Filter — 79 Signals Blocked
| Symbol | Direction Blocked | Justified? |
|---|---|---|
| USDCHF | 17 SELL blocked | NO — USDCHF SELL is profitable (+$90 avg) |
| GBPUSD | 13 BUY blocked | NO — GBPUSD BUY is profitable (+$131 avg) |
| XAUUSD | 11 BUY blocked | NO — XAUUSD BUY is profitable (+$465 avg) |
| NZDUSD | 9 BUY blocked | YES — NZDUSD is a loser |
| USDCAD | 9 SELL blocked | YES — USDCAD is a loser |
| EURUSD | 8 BUY blocked | MIXED |
| USDJPY | 6 SELL blocked | MIXED |

**Verdict:** H4 filter is blocking profitable trades on XAUUSD, GBPUSD, USDCHF. It was already disabled (commit b818034) — this data confirms that was the right decision.

### Session Filter — 18 Signals Lost
Low impact. Working correctly — blocks low-liquidity hours.

### News Filter — 18 Signals Blocked
Working correctly. Blocks around high-impact events (PPI, BOC Rate, ECB). Keep as-is.

### Other Rejections
| Reason | Count | Action Needed |
|---|---|---|
| Max positions/drawdown limit | 32 | Normal — risk controls working |
| Unsupported filling mode | 24 | IMP-50 fallback exists but still failing |
| AutoTrading disabled | 21 | IMP-61 now skips cycle when disabled |
| Position already open | 11 | Normal — duplicate prevention |
| No money | 10 | Hit risk limits — working correctly |

---

## 7. Concrete Improvements to Existing Strategies

### IMP-A: RSI Entry Band Filter
- **Problem:** RSI Reversal loses when RSI < 35 at entry
- **Solution:** Only enter when RSI is between 38-72 (not extreme values)
- **Expected impact:** Eliminate ~40% of losing RSI trades
- **File:** `strategies/rsi_reversal.py`

### IMP-B: MACD Minimum Volatility Filter
- **Problem:** MACD loses in low-volatility conditions (ATR < 1.18)
- **Solution:** Add ATR threshold — only trade when ATR > 1.2x its 20-period average
- **Expected impact:** Filter out low-conviction MACD signals
- **File:** `strategies/macd_crossover.py`

### IMP-C: USDCAD Position Size Reduction
- **Problem:** USDCAD has 64% loss rate, -$1,998 total
- **Solution:** Reduce to 0.5% risk (half normal) or remove entirely
- **Expected impact:** Cut USDCAD losses by 50%
- **File:** `config/base.yaml`

### IMP-D: Thursday Caution Mode
- **Problem:** Thursday has 38% WR and -$3,092
- **Solution:** Tighten entry criteria on Thursdays (require 2+ confirmations)
- **Expected impact:** Reduce Thursday losses
- **File:** `scripts/paper_trade.py` or strategy files

### IMP-E: Hour 15:00 Block
- **Problem:** 15:00 UTC is the worst hour (-$3,711, 31% WR, 13 trades)
- **Solution:** Add 15:00 to session filter or reduce position size
- **Expected impact:** Eliminate biggest loss cluster
- **File:** `config/base.yaml` (session_filter settings)

### IMP-F: XAUUSD Strategy Restriction
- **Problem:** XAUUSD only profits with MACD (other strategies lose on gold)
- **Solution:** Restrict XAUUSD to MACD Crossover only
- **Expected impact:** Eliminate XAUUSD losses from RSI/BB/SMA
- **File:** `scripts/paper_trade.py`

---

## 8. New Strategy Proposals

### Strategy 1: Volatility Breakout (XAUUSD Specialist)
**Rationale:** XAUUSD produces the biggest wins but also big losses. A dedicated volatility-breakout strategy for gold could capture these moves better.

**Logic:**
1. Calculate ATR(14) and Bollinger Bands(20, 2.5)
2. Wait for price to consolidate (BB Width < 1.5%)
3. Enter on breakout above upper BB (BUY) or below lower BB (SELL)
4. SL: 1.5x ATR below/above entry
5. TP: 3x ATR (R:R = 2:1)
6. Only trade during hours 09:00-17:00 UTC

**Why it could work:** XAUUSD's best trades were breakout moves. Current strategies catch them sometimes by luck — a dedicated breakout strategy would be more systematic.

### Strategy 2: AUDUSD Momentum Rider
**Rationale:** AUDUSD has 77.8% WR across all strategies. A momentum strategy specifically tuned for AUDUSD could capitalize on its strong trending behavior.

**Logic:**
1. EMA(8) crosses above EMA(21) = BUY momentum
2. RSI between 45-65 (not overbought)
3. ADX > 25 (trending market)
4. Enter on pullback to EMA(8)
5. SL: 1.5x ATR
6. TP: 2.5x ATR
7. Trailing stop after 1x ATR profit

**Why it could work:** AUDUSD wins consistently — a momentum strategy would ride its natural trends instead of trying reversals.

### Strategy 3: London Open Scalper
**Rationale:** Hours 07:00-11:00 UTC show the best win rates. A session-specific strategy could exploit this window.

**Logic:**
1. Active only 07:00-11:00 UTC
2. Wait for first 30-min range to form (07:00-07:30)
3. Enter on breakout of this range
4. Confirm with RSI > 50 for BUY, RSI < 50 for SELL
5. SL: range height (or 1x ATR, whichever is smaller)
6. TP: 2x range height
7. Max 2 trades per session

**Why it could work:** The data shows 07:00 at 100% WR and 10:00-11:00 consistently profitable. London open creates predictable volatility patterns.

### Strategy 4: Anti-Thursday Filter + Thursday Reversal
**Rationale:** Thursday has 38% WR. Instead of avoiding it, trade the reversal.

**Logic:**
1. On Thursdays, REVERSE the normal signal direction
2. If MACD says BUY, go SELL (and vice versa)
3. Only apply to symbols that lose on Thursdays
4. Use tighter SL (1x ATR instead of 1.5x)

**Why it could work:** If strategies consistently lose on Thursday, the opposite direction might be profitable. Needs backtesting to validate.

### Strategy 5: RSI-ATR Confluence
**Rationale:** Data shows winning trades have specific RSI+ATR combinations.

**Logic:**
1. RSI between 40-60 (neutral zone)
2. ATR below 20-period average (low volatility, about to expand)
3. Wait for RSI to break above 60 or below 40
4. Enter in direction of RSI break
5. SL: 1.5x ATR
6. TP: 2.5x ATR

**Why it could work:** Winners enter at moderate RSI with lower ATR. This strategy explicitly targets that combination, entering just as volatility begins to expand.

---

## 9. Action Plan (Prioritized)

### Immediate (This Week)
| # | Action | Expected Impact | Effort |
|---|---|---|---|
| 1 | IMP-E: Block hour 15:00 | Save -$3,711 | Low |
| 2 | IMP-F: XAUUSD = MACD only | Reduce XAUUSD losses | Low |
| 3 | IMP-A: RSI entry band (38-72) | Improve RSI WR by ~10% | Medium |

### Short Term (Next 2 Weeks)
| # | Action | Expected Impact | Effort |
|---|---|---|---|
| 4 | IMP-B: MACD ATR filter | Better MACD signal quality | Medium |
| 5 | IMP-C: Reduce USDCAD risk | Cut -$1,998 losses | Low |
| 6 | Build Strategy 2 (AUDUSD Momentum) | Exploit best symbol | High |

### Medium Term (Next Month)
| # | Action | Expected Impact | Effort |
|---|---|---|---|
| 7 | Build Strategy 1 (XAUUSD Breakout) | Systematic gold trading | High |
| 8 | Build Strategy 3 (London Scalper) | Exploit best hours | High |
| 9 | Collect 200+ trades for ML training | Enable IMP-24 | Time |

### Long Term (After 200+ Trades)
| # | Action | Expected Impact | Effort |
|---|---|---|---|
| 10 | Train ML models (IMP-24) | Smart signal filtering | High |
| 11 | Strategy 5 (RSI-ATR Confluence) | Data-driven entries | High |
| 12 | IMP-27: Paper vs Live config split | Required for live trading | Medium |

---

## Key Takeaways

1. **MACD is your money maker** — protect and optimize it, don't dilute with weak strategies
2. **AUDUSD is your best symbol** — consider building a dedicated strategy for it
3. **Avoid 15:00 UTC and Thursdays** — data clearly shows these are losing periods
4. **RSI works when not extreme** — moderate RSI entries (40-65) win more than extreme entries
5. **Volatility is strategy-dependent** — MACD needs it, RSI Reversal doesn't
6. **One trade risk** — $11,916 XAUUSD trade masks overall mediocre performance. Without it, the system barely profits

---

*Generated: 2026-03-27 | Data: 119 trades, 358 signals | Period: March 18-27, 2026*
