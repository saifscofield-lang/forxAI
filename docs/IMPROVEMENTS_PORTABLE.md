# SynthAI Improvements — Portable Reference for ForexAI
### Generated: 2026-03-29 | Engine v3.3 | 10 improvements (IMP-014 to IMP-023)

---

## Quick Summary

| Code | Component | Change | Forex Compatible? |
|------|-----------|--------|-------------------|
| IMP-014 | spike_catcher v1.1 | Fix dead code + wick cap | YES - same logic |
| IMP-015 | macd_crossover v2.0 | EMA50/200 trend + histogram | YES - even more important for forex |
| IMP-016 | bollinger_bounce v2.0 | Bounce confirmation + RSI + BB width | YES with adjustments |
| IMP-017 | volatility_scalper v1.1 | R:R fix (TP 1.0->1.5) | PARTIAL - forex volatility differs |
| IMP-018 | rsi_reversal v1.1 | 2-bar confirmation + price check | YES - same logic |
| IMP-019 | ema_scalper v1.1 | Slope check + ATR filter | YES with different thresholds |
| IMP-020 | range_breakout v1.1 | False breakout + distance filter | YES - critical for forex |
| IMP-021 | Engine filter | H1 trend exemptions | ADAPT - forex needs H1 filter more |
| IMP-022 | Engine risk | Disable daily limits (demo) | NO for live, YES for demo |
| IMP-023 | Engine risk | R:R minimum 0.3->0.2 | CAREFUL - forex needs stricter R:R |

---

## 1. Database Schema: Strategy Version Tracking

### New Table: `strategy_improvements`

```python
class StrategyImprovement(Base):
    __tablename__ = "strategy_improvements"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    improvement_code  = Column(String(20), unique=True, nullable=False)
    strategy_name     = Column(String(50), nullable=False)
    version_before    = Column(String(10), nullable=False)
    version_after     = Column(String(10), nullable=False)
    description       = Column(String(500), nullable=False)
    changes_summary   = Column(Text, nullable=True)
    expected_impact   = Column(String(200), nullable=True)
    applied_at        = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_imp_strategy", "strategy_name"),
    )
```

### New Columns (add to existing tables)

```python
# SignalLog
strategy_version = Column(String(10), nullable=True)

# Trade
strategy_version = Column(String(10), nullable=True)

# TradeResult
strategy_version = Column(String(10), nullable=True)
```

### Migration SQL

```python
migrations = {
    "signal_logs": [("strategy_version", "TEXT")],
    "trades": [("strategy_version", "TEXT")],
    "trade_results": [("strategy_version", "TEXT")],
}
```

### How each strategy reports its version

```python
class SomeStrategy:
    VERSION = "2.0"

    def generate_signal(self, df):
        # ... signal logic ...
        return {
            "action": signal_action,
            "strategy": self.name,
            "strategy_version": self.VERSION,  # <-- NEW
            # ... rest of signal dict ...
        }
```

### Engine saves version to DB

```python
# _log_signal():
log = SignalLog(
    # ... existing fields ...
    strategy_version=signal.get("strategy_version"),
)

# _save_trade():
trade = Trade(
    # ... existing fields ...
    strategy_version=signal.get("strategy_version"),
)

# TradeResult (from SignalLog):
result.strategy_version = signal_log.strategy_version
```

### ML Training Data Queries

```sql
-- Clean data: only post-improvement trades
SELECT * FROM trade_results WHERE strategy_version IS NOT NULL;

-- Compare before/after per strategy
SELECT strategy, strategy_version,
       COUNT(*) trades, AVG(pnl) avg_pnl,
       SUM(CASE WHEN profitable THEN 1 ELSE 0 END) * 100.0 / COUNT(*) win_rate
FROM trade_results
GROUP BY strategy, strategy_version;

-- Improvement history
SELECT * FROM strategy_improvements ORDER BY applied_at;
```

---

## 2. Strategy Improvements (Code)

---

### IMP-014: Spike Catcher v1.0 -> v1.1

**Problem:** 3 lines overwriting the same `lower_wick` variable (dead code).

**Before:**
```python
lower_wick = open_price - low if price < open_price else price - low  # line 1
lower_wick = low - min(price, open_price)   # line 2: OVERWRITES (gives negative!)
lower_wick = abs(min(price, open_price) - low)  # line 3: OVERWRITES again
```

**After:**
```python
if price > open_price:  # bullish candle
    upper_wick = high - price
    wick_ratio = upper_wick / candle_range
    if wick_ratio >= self.min_wick_ratio:
        signal_action = "SELL"
else:  # bearish candle
    lower_wick = min(price, open_price) - low  # single correct calculation
    wick_ratio = lower_wick / candle_range
    if wick_ratio >= self.min_wick_ratio:
        signal_action = "BUY"

# NEW: reject extreme wick (data artifact)
if wick_ratio > 0.8:
    return None
```

**Forex adaptation:** Same logic applies. Add the 0.8 cap.

---

### IMP-015: MACD Crossover v1.0 -> v2.0

**Problem:** MACD crossover fires BUY even in strong downtrend. Caused -$1,028 loss.

**Before:**
```python
if prev_macd <= prev_sig and macd > macd_sig:
    signal_action = "BUY"   # no trend check
```

**After:**
```python
from features.technical.indicators import add_ema

tmp = add_ema(tmp, 50)
tmp = add_ema(tmp, 200)

# BUY: only in confirmed uptrend
if prev_macd <= prev_sig and macd > macd_sig:
    if price > ema_50 and ema_50 > ema_200:
        signal_action = "BUY"

# SELL: only in confirmed downtrend
elif prev_macd >= prev_sig and macd < macd_sig:
    if price < ema_50 and ema_50 < ema_200:
        signal_action = "SELL"

# Histogram momentum must be increasing
hist = float(curr["macd_hist"])
prev_hist = float(prev["macd_hist"])
if signal_action == "BUY" and hist <= prev_hist:
    return None
if signal_action == "SELL" and hist >= prev_hist:
    return None
```

**Forex adaptation:**
- EVEN MORE IMPORTANT for forex (news spikes cause false crossovers)
- Consider adding EMA100 as intermediate filter
- On H1/H4, the EMA200 filter is very strong — keep it
- On M15, may be too restrictive during ranging sessions — consider relaxing to EMA50 only

---

### IMP-016: Bollinger Bounce v1.0 -> v2.0

**Problem:** Enters immediately when price touches band, no confirmation of reversal.

**Before:**
```python
if price <= bb_lower:
    signal_action = "BUY"   # instant, no confirmation
```

**After:**
```python
prev_price = float(prev["close"])
prev_bb_lower = float(prev["bb_lower"])
prev_bb_upper = float(prev["bb_upper"])

# Confirmation: prev candle was OUTSIDE band, current closed BACK INSIDE
if prev_price <= prev_bb_lower and price > bb_lower:
    signal_action = "BUY"
elif prev_price >= prev_bb_upper and price < bb_upper:
    signal_action = "SELL"

# RSI must confirm the reversal
if signal_action == "BUY" and rsi > 45:
    return None
if signal_action == "SELL" and rsi < 55:
    return None

# BB Width filter: don't counter strong momentum
bb_width = bb_upper - bb_lower
bb_width_avg = float((clean["bb_upper"] - clean["bb_lower"]).tail(20).mean())
if bb_width > bb_width_avg * 1.5:
    return None
```

**Forex adaptation:**
- BB Width filter is MORE important for forex (expanding bands during news)
- RSI thresholds: use 40/60 for forex (more extreme confirmation needed)
- Consider adding volume confirmation if available
- During Asian session, BB bounce works better — consider session-aware thresholds

---

### IMP-017: Volatility Scalper v1.0 -> v1.1

**Problem:** R:R = 1:3 (TP=1.0 ATR, SL=3.0 ATR). Needs WR > 75% to be profitable.

**After:**
```python
compression_threshold: float = 0.7   # was 0.8 (stricter = fewer but better signals)
atr_tp_multiplier: float = 1.5       # was 1.0 (R:R improves from 1:3 to 1:2)
atr_sl_multiplier: float = 3.0       # unchanged
```

**Forex adaptation:**
- DO NOT use this strategy as-is for forex
- Forex volatility is NOT mean-reverting like synthetics
- If adapting: use session-based ATR (Asian session compression -> London breakout)
- Use compression_threshold = 0.6 for forex (need stronger compression signal)
- Consider using it only during Asian session (21:00-07:00 UTC)

---

### IMP-018: RSI Reversal v1.0 -> v1.1

**Problem:** Single candle RSI bounce triggers entry. In volatile markets, one bounce is not enough.

**Before:**
```python
if rsi < self.oversold and rsi > rsi_prev:  # 1 candle
    signal_action = "BUY"
```

**After:**
```python
rsi_2bars = float(prev2[rsi_col])  # need 3rd bar

# 2-bar RSI confirmation
if rsi < self.oversold and rsi > rsi_prev and rsi_prev > rsi_2bars:
    signal_action = "BUY"
elif rsi > self.overbought and rsi < rsi_prev and rsi_prev < rsi_2bars:
    signal_action = "SELL"

# Price must confirm reversal direction
prev_close = float(prev["close"])
if signal_action == "BUY" and price < prev_close:
    return None
if signal_action == "SELL" and price > prev_close:
    return None
```

**Forex adaptation:**
- Same logic applies perfectly
- For forex H1/H4: consider 3-bar confirmation instead of 2
- Per-pair thresholds matter more: USDJPY oversold=25, EURUSD oversold=30
- Add divergence check: RSI making higher low while price makes lower low = strong BUY

---

### IMP-019: EMA Scalper v1.0 -> v1.1

**Problem:** EMA50 trend filter is flat/slow, doesn't confirm trend direction actively.

**After (new filters added):**
```python
# Slope check: EMA50 must be clearly trending
ema_trend_prev5 = float(clean.iloc[-6][trend_col])
trend_slope = (ema_trend - ema_trend_prev5) / ema_trend_prev5 * 100

if signal_action == "BUY" and trend_slope < 0.02:
    return None  # trend not rising enough
if signal_action == "SELL" and trend_slope > -0.02:
    return None  # trend not falling enough

# ATR activity filter: skip quiet markets
atr_avg = float(clean[atr_col].tail(20).mean())
if atr_avg > 0 and atr < atr_avg * 0.7:
    return None  # too quiet for scalping
```

**Forex adaptation:**
- Slope threshold should be HIGHER for forex: 0.05% (forex trends are slower)
- ATR filter is critical — skip Asian session for EUR/GBP pairs
- Consider adding spread filter: if spread > 2x normal, skip (forex spreads widen)
- M5/M15 only — do not use on H1+ for scalping

---

### IMP-020: Range Breakout v1.0 -> v1.1

**Problem:** Price spike (wick) through range = false breakout. Also entering too late after breakout.

**After (new filters added):**
```python
# False breakout filter: candle body must align with direction
candle_body = price - open_price
if signal_action == "BUY" and candle_body < 0:
    return None  # bearish candle broke upward = suspicious
if signal_action == "SELL" and candle_body > 0:
    return None  # bullish candle broke downward = suspicious

# Distance filter: don't enter if breakout happened too far ago
if signal_action == "BUY":
    distance = price - range_high
    if distance > atr * 0.5:
        return None  # missed the train
else:
    distance = range_low - price
    if distance > atr * 0.5:
        return None
```

**Forex adaptation:**
- FALSE BREAKOUT is the #1 problem in forex range trading — this filter is critical
- Lower distance threshold to 0.3x ATR for forex (forex breakouts move fast)
- Add volume confirmation if available (breakout with low volume = fake)
- Add London session filter: breakouts during Asian session are often false
- Consider per-pair min_range_atr: GBPJPY=2.0 (volatile), EURCHF=5.0 (tight ranges)

---

## 3. Engine Filter Changes

---

### IMP-021: H1 Trend Filter Exemptions

**Problem:** H1 trend filter blocks strategies that already have internal trend logic.

```python
# BEFORE: all strategies checked against H1 trend
if secondary_trend == "UP" and signal["action"] == "SELL":
    reject()

# AFTER: exempt strategies with internal filters
h1_exempt = {"volatility_scalper", "ema_scalper", "macd_crossover"}
if strat_name not in h1_exempt and secondary_trend and secondary_trend != "RANGE":
    if secondary_trend == "UP" and signal["action"] == "SELL":
        reject()
```

**Forex adaptation:**
- BE CAREFUL: forex H1 trend is more meaningful than synthetic
- For forex, only exempt `macd_crossover` (has EMA50/200 internal filter now)
- Keep H1 filter for `ema_scalper` on forex (M15 EMA50 slope is weak for forex)
- Keep H1 filter for `volatility_scalper` on forex (session-dependent volatility)
- Recommended forex exempt list: `{"macd_crossover"}` only

---

### IMP-022: Disable Daily Loss Limits (Demo Only)

```python
# BEFORE:
if self.is_daily_loss_limit_hit():
    return False

# AFTER (demo account):
# Commented out — demo account does not need loss protection
return True
```

**Forex adaptation:**
- KEEP ENABLED for live forex accounts
- For forex demo: can disable, but consider keeping 10% drawdown limit
- When switching demo -> live: RE-ENABLE immediately

---

### IMP-023: R:R Minimum 0.3 -> 0.2

```python
# BEFORE:
if reward / risk < 0.3:
    return False, f"Risk/reward {reward/risk:.2f} below 0.3 minimum"

# AFTER:
if reward / risk < 0.2:
    return False, f"Risk/reward {reward/risk:.2f} below 0.2 minimum"
```

**Forex adaptation:**
- For forex: KEEP at 0.3 or raise to 0.5
- Forex spreads are wider and more variable, so R:R gets eroded more
- Only lower to 0.2 for specific high-WR strategies with proven backtests
- Consider per-strategy R:R minimums instead of global

---

## 4. Forex-Specific Notes

### What to ADD for Forex (not needed for Synthetics)

1. **News filter** — skip trading 30min before/after high-impact events
2. **Session filter** — only trade London/NY overlap for most pairs
3. **Correlation filter** — don't open EURUSD BUY + GBPUSD BUY simultaneously
4. **Spread filter** — reject if current spread > 2x normal
5. **Swap awareness** — consider overnight costs for swing trades
6. **Pip value** — forex needs pip_value conversion (not tick_value directly)

### What to CHANGE for Forex

| Parameter | Synthetics | Forex |
|-----------|-----------|-------|
| Scan interval | 15 min | 60 min (H1 primary) |
| Primary timeframe | M15 | H1 |
| Confirmation TF | M5 | M15 |
| Trend TF | H1 | H4 or D1 |
| Rounding | 2 decimals | 5 decimals (or 3 for JPY) |
| EMA slope threshold | 0.02% | 0.05% |
| BB Width multiplier | 1.5x | 2.0x |
| Compression threshold | 0.7 | 0.6 |
| R:R minimum | 0.2 | 0.5 |

---

## 5. Implementation Checklist for ForexAI

- [ ] Add `StrategyImprovement` table to database.py
- [ ] Add `strategy_version` column to SignalLog, Trade, TradeResult
- [ ] Add migration code for existing DB
- [ ] Add `VERSION` class attribute to each strategy
- [ ] Pass `strategy_version` in signal dict -> engine -> DB
- [ ] Apply IMP-014 (spike_catcher dead code fix)
- [ ] Apply IMP-015 (MACD trend filter) — most impactful
- [ ] Apply IMP-016 (Bollinger confirmation) — with forex RSI thresholds 40/60
- [ ] Apply IMP-018 (RSI 2-bar confirmation)
- [ ] Apply IMP-019 (EMA slope) — with 0.05% threshold
- [ ] Apply IMP-020 (false breakout filter) — critical for forex
- [ ] Review IMP-021 (H1 exemptions) — only exempt macd_crossover for forex
- [ ] SKIP IMP-022 for live accounts (keep daily loss limits)
- [ ] SKIP IMP-023 for forex (keep R:R >= 0.3 or 0.5)
- [ ] Seed improvement records in DB
- [ ] Run backtests to verify improvements
