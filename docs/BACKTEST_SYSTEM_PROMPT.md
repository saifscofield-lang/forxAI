# Prompt: تطبيق نظام الباك تست + الإشعارات على مشروع تداول

## السياق
لدي مشروع تداول آلي يعمل بالبنية التالية:
- استراتيجيات تولّد إشارات BUY/SELL عبر `generate_signal(df)` تُرجع dict أو None
- محرك تداول ينفّذ الإشارات
- قاعدة بيانات SQLite لتسجيل الصفقات
- بيانات تاريخية محفوظة (Parquet أو CSV)
- Telegram bot للإشعارات

أريد تطبيق نظام باك تست شامل مع إشعارات ذكية وربط النتائج بالتداول الحي.

---

## المطلوب تنفيذه (8 أجزاء)

---

### الجزء 1: Universal Backtester

أنشئ `backtest/universal_backtester.py`:

```python
class UniversalBacktester:
    """
    يعمل مع أي استراتيجية تملك generate_signal(df).
    لا يعتمد على مؤشر معين — يمرر DataFrame slice للاستراتيجية.
    """
    def __init__(self, strategy, initial_balance, risk_per_trade, max_open_positions, pip_value, spread_pips)
    def run(self, df: DataFrame, warmup: int) -> BacktestResult
```

المتطلبات:
- Bar-by-bar simulation: عند كل شمعة i، يمرر `df[0:i+1]` لـ `strategy.generate_signal()`
- يفحص SL/TP exits على كل شمعة (high/low)
- Position sizing: `risk_amount / (sl_pips * pip_value_per_lot)`
- يطبق spread على سعر الدخول
- يسجل equity curve كل 5 شموع
- يحسب لكل صفقة: pnl, pnl_pips, rr_planned, rr_actual, duration_minutes
- BacktestTrade dataclass مع: id, symbol, action, entry/exit price/time, sl, tp, lot_size, strategy, strategy_version, exit_reason, pnl, pnl_pips, rr_planned, rr_actual, duration_minutes
- BacktestResult dataclass مع: symbol, timeframe, strategy, strategy_version, start/end_date, initial/final_balance, trades[], equity_curve[]

---

### الجزء 2: Backtest Results Database

أنشئ `data/backtest_results.db` بـ 4 جداول:

**backtest_runs** — ملخص كل اختبار:
```sql
run_id, run_time, symbol, timeframe, strategy, strategy_version,
period_start, period_end, total_bars,
initial_balance, final_balance, total_pnl, total_return_pct,
total_trades, winning_trades, losing_trades,
win_rate, profit_factor, sharpe_ratio,
max_drawdown_pct, max_drawdown_dollar,
avg_win, avg_loss, avg_pnl_per_trade,
avg_win_pips, avg_loss_pips, avg_trade_bars,
max_consecutive_wins, max_consecutive_losses,
expectancy, spread_pips, risk_per_trade, verdict (PASS/FAIL)
```

**backtest_trades** — كل صفقة:
```sql
run_id, trade_num, symbol, action, strategy, strategy_version,
entry_price, exit_price, stop_loss, take_profit,
entry_time, exit_time, exit_reason, lot_size,
pnl, pnl_pips, rr_planned, rr_actual, duration_minutes
```

**backtest_equity** — منحنى الرصيد:
```sql
run_id, time, balance, equity, open_trades
```

**backtest_log** — سجل الأحداث:
```sql
run_id, time, level, message
```

---

### الجزء 3: ثلاث معايير للنجاح (Risk Profiles)

```python
RISK_PROFILES = {
    "strict": {       # للتداول الحقيقي
        "name": "صارم (Live)",
        "min_trades": 50,
        "min_profit_factor": 1.3,
        "max_drawdown_pct": 8.0,
        "min_win_rate": 45.0,
        "min_sharpe": 0.5,
    },
    "moderate": {      # للتداول التجريبي — الافتراضي
        "name": "متوسط (Paper)",
        "min_trades": 30,
        "min_profit_factor": 1.15,
        "max_drawdown_pct": 10.0,
        "min_win_rate": 40.0,
        "min_sharpe": 0.3,
    },
    "aggressive": {    # تجريبي — صفقات أكثر مع مخاطرة
        "name": "مجازف (تجريبي)",
        "min_trades": 15,
        "min_profit_factor": 1.05,
        "max_drawdown_pct": 15.0,
        "min_win_rate": 35.0,
        "min_sharpe": 0.0,
    },
}
```

الحكم (verdict):
```python
passed = (
    trades >= min_trades
    and profit_factor >= min_profit_factor
    and max_drawdown_pct <= max_drawdown_pct
    and win_rate >= min_win_rate
    and sharpe_ratio >= min_sharpe
    and total_pnl > 0
)
verdict = "PASS" if passed else "FAIL"
```

---

### الجزء 4: سكريبت التشغيل (run_backtest_all.py)

أنشئ `scripts/run_backtest_all.py` مع arguments:
```
--strategy    اختبار استراتيجية محددة
--symbol      اختبار زوج محدد
--timeframe   إطار زمني محدد (أو الكل: M15, H1, H4, D1)
--profile     معيار النجاح (strict / moderate / aggressive)
```

الآلية:
1. يقرأ config ويحدد الأزواج والاستراتيجيات
2. لكل زوج × إطار × استراتيجية:
   - يحمل البيانات التاريخية
   - يشغّل UniversalBacktester
   - يحسب metrics (من backtest/metrics.py)
   - يحكم PASS/FAIL حسب profile
   - يحفظ كل شيء في backtest_results.db
3. يُنشئ `data/backtest_approved.yaml`:

```yaml
generated_at: "2026-03-29 14:00:00 UTC"
run_id: "20260329_140000"
profile: moderate
profile_name: "متوسط (Paper)"
criteria:
  min_trades: 30
  min_profit_factor: 1.15
  max_drawdown_pct: 10.0
  min_win_rate: 40.0
  min_sharpe: 0.3
approved:
  EURUSD_macd_crossover:
    symbol: EURUSD
    strategy: macd_crossover
    version: "2.0"
    timeframe: H1
    trades: 87
    win_rate: 52.3
    profit_factor: 1.340
    total_pnl: 12340.00
    max_drawdown_pct: 4.2
    sharpe: 0.845
```

4. يرسل إشعارات Telegram (البداية والنهاية)

---

### الجزء 5: إشعارات Telegram للباك تست

**عند البدء:**
```
🧪 بدء الباك تست الشامل
━━━━━━━━━━━━━━━━━━
🆔 Run: 20260329_140000
⚙️ المعيار: متوسط (Paper)
📊 الأزواج: EURUSD, GBPUSD, ...
⏱ الأطر: M15, H1, H4, D1
🔢 إجمالي الاختبارات: 84
📋 PF>1.15 | DD<10% | WR>40% | Sharpe>0.3 | Trades>30
━━━━━━━━━━━━━━━━━━
⏳ الوقت المتوقع: ~1680s
```

**عند الانتهاء:**
```
🏁 الباك تست انتهى
━━━━━━━━━━━━━━━━━━
🆔 Run: 20260329_140000
⚙️ المعيار: متوسط (Paper)
⏱ المدة: 950s
✅ نجح: 12 | ❌ فشل: 9

━━ النتائج ━━
  ✅ EURUSD/H1 macd_crossover v2.0
    87 صفقة | WR 52% | PF 1.34 | $+12,340
  ❌ EURUSD/H1 bollinger_bounce v2.0
    62 صفقة | WR 41% | PF 0.87 | $-1,200
  ...

📁 معتمدة للتداول: 12 استراتيجية-زوج
```

---

### الجزء 6: ربط الباك تست بالتداول الحي

في `create_strategies()` داخل سكريبت التداول:

```python
def create_strategies(config):
    # 1. حاول قراءة backtest_approved.yaml
    approved = _load_approved()  # returns dict or None

    for symbol in instruments:
        # 2. لكل استراتيجية: تحقق هل هي معتمدة
        def is_approved(strat_name):
            if approved is None:
                # لا يوجد باك تست — استخدم الإعدادات القديمة
                return legacy_default(strat_name, symbol)
            # يوجد باك تست — فقط PASS
            return f"{symbol}_{strat_name}" in approved

        if is_approved("macd_crossover"):
            strategies.append(MACDStrategy(symbol=...))
        if is_approved("rsi_reversal"):
            strategies.append(RSIStrategy(symbol=...))
        # ... etc

        logger.info(f"  {symbol}: {count} strategies [{source}]")
        # source = "backtest" إذا approved موجود، "default" إذا لا
```

---

### الجزء 7: تتبع إصدارات الاستراتيجيات

لكل استراتيجية:
```python
class MACDStrategy:
    VERSION = "2.0"  # يتغير عند كل تحسين

    def generate_signal(self, df):
        # ...
        return {
            "action": "BUY",
            "strategy": self.name,
            "strategy_version": self.VERSION,  # ← جديد
            # ...
        }
```

في قاعدة البيانات أضف عمود `strategy_version` لـ:
- جدول الصفقات (trades)
- جدول الإشارات (signal_logs)
- جدول النتائج (trade_results)

المحرك يمرر الإصدار من الإشارة إلى قاعدة البيانات.

جدول جديد `strategy_improvements`:
```sql
improvement_code  TEXT UNIQUE    -- مثل IMP-63
strategy_name     TEXT           -- macd_crossover
version_before    TEXT           -- 1.0
version_after     TEXT           -- 2.0
description       TEXT
applied           BOOLEAN       -- هل تم التنفيذ؟
applied_at        DATETIME      -- متى تم التنفيذ
```

---

### الجزء 8: backtest.bat (ملف التشغيل)

```batch
@echo off
title Project Backtest
cd /d PROJECT_PATH

echo  -- Risk Profile --
echo  [S] Strict    (PF>1.3  DD<8%  WR>45%  Sharpe>0.5  Trades>50)
echo  [M] Moderate  (PF>1.15 DD<10% WR>40%  Sharpe>0.3  Trades>30)
echo  [A] Aggressive(PF>1.05 DD<15% WR>35%  Sharpe>0    Trades>15)

set /p profile="  Profile (S/M/A) [M]: "

echo  -- Scope --
echo  [1] ALL (full)
echo  [2] Specific strategy
echo  [3] Specific symbol

set /p choice="  Choose: "

REM يشغّل السكريبت مع البارامترات المختارة
venv\Scripts\python scripts\run_backtest_all.py --profile %prof% ...

echo  Results: data\backtest_results.db
echo  Approved: data\backtest_approved.yaml
echo  Now run start.bat
pause
```

---

## ملاحظات التطبيق

1. **لا تعدّل قاعدة بيانات التداول** — الباك تست في DB منفصلة
2. **backtest_approved.yaml هو الرابط الوحيد** بين الباك تست والتداول الحي
3. **بدون الملف** = النظام يعمل بالإعدادات الافتراضية (backward compatible)
4. **كل استراتيجية يجب أن تملك VERSION** كـ class attribute
5. **المعايير قابلة للتعديل** — غيّر RISK_PROFILES حسب طبيعة السوق
6. **عدّل الـ warmup** حسب الإطار الزمني (250 لـ H1, 100 لـ D1)
7. **عدّل الـ spread** حسب الأداة (أعلى للذهب والعملات النادرة)

---

## الملفات المطلوب إنشاؤها

```
backtest/universal_backtester.py   — المحرك العام
scripts/run_backtest_all.py        — سكريبت التشغيل الشامل
backtest.bat                       — واجهة المستخدم
data/backtest_results.db           — يُنشأ تلقائياً
data/backtest_approved.yaml        — يُنشأ تلقائياً
```

## الملفات المطلوب تعديلها

```
storage/database.py                — إضافة strategy_version + StrategyImprovement
engine/trading_engine.py           — تمرير strategy_version للـ DB
strategies/*.py                    — إضافة VERSION + strategy_version في return
scripts/paper_trade.py             — قراءة approved.yaml في create_strategies()
observability/telegram_notifier.py — strategy_version + R:R في الرسائل
```
