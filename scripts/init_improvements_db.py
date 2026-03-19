"""
قاعدة بيانات التحسينات — ForexAI Improvements Tracker
تتبع جميع التحسينات المطلوبة، حالتها، أولويتها، وتفاصيل التنفيذ
"""
import sys
sys.path.insert(0, ".")

import sqlite3
import json
from datetime import datetime

DB_PATH = "data/improvements.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Main improvements table
    c.execute("""
    CREATE TABLE IF NOT EXISTS improvements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,           -- e.g. IMP-01, IMP-02
        title TEXT NOT NULL,
        title_ar TEXT,                       -- Arabic title
        category TEXT NOT NULL,              -- RISK, STRATEGY, EXECUTION, INFRASTRUCTURE, MONITORING, CONFIG
        priority TEXT NOT NULL,              -- CRITICAL, HIGH, MEDIUM, LOW
        status TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING, IN_PROGRESS, DONE, SKIPPED, PARTIAL
        problem TEXT NOT NULL,               -- What's wrong
        solution TEXT NOT NULL,              -- Proposed fix
        affected_files TEXT,                 -- JSON list of files to modify
        estimated_impact TEXT,               -- Expected improvement
        actual_impact TEXT,                  -- Measured after implementation
        depends_on TEXT,                     -- JSON list of dependency IMP codes
        notes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT,
        evidence TEXT                        -- Data/stats that justify this improvement
    )
    """)

    # Implementation log — track what was actually changed
    c.execute("""
    CREATE TABLE IF NOT EXISTS implementation_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        improvement_id TEXT NOT NULL,
        action TEXT NOT NULL,                -- What was done
        files_changed TEXT,                  -- JSON list
        commit_hash TEXT,
        timestamp TEXT NOT NULL,
        FOREIGN KEY (improvement_id) REFERENCES improvements(code)
    )
    """)

    # Status history
    c.execute("""
    CREATE TABLE IF NOT EXISTS status_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        improvement_id TEXT NOT NULL,
        old_status TEXT,
        new_status TEXT NOT NULL,
        reason TEXT,
        timestamp TEXT NOT NULL,
        FOREIGN KEY (improvement_id) REFERENCES improvements(code)
    )
    """)

    conn.commit()
    return conn


def insert_improvement(conn, data):
    now = datetime.now().isoformat()
    c = conn.cursor()
    c.execute("""
    INSERT OR REPLACE INTO improvements
    (code, title, title_ar, category, priority, status, problem, solution,
     affected_files, estimated_impact, depends_on, notes, created_at, updated_at, evidence)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["code"], data["title"], data.get("title_ar"), data["category"],
        data["priority"], data["status"], data["problem"], data["solution"],
        json.dumps(data.get("affected_files", []), ensure_ascii=False),
        data.get("estimated_impact"), json.dumps(data.get("depends_on", []), ensure_ascii=False),
        data.get("notes"), now, now, data.get("evidence"),
    ))
    conn.commit()


def populate():
    conn = init_db()

    improvements = [
        # ══════════════════════════════════════════
        # CRITICAL — Red
        # ══════════════════════════════════════════
        {
            "code": "IMP-01",
            "title": "Fix per-symbol position sizing (pip_value validation)",
            "title_ar": "إصلاح Position Sizing لكل زوج على حدة",
            "category": "RISK",
            "priority": "CRITICAL",
            "status": "PARTIAL",
            "problem": "NZDUSD loses $536/trade while XAUUSD loses $7.7. pip_value for XAUUSD=0.01 and JPY pairs=0.01 may not correctly reflect actual dollar risk. The formula `pip_value * 100_000` assumes standard forex lots but XAUUSD has contract size of 100 oz, not 100,000 units. Risk per trade is NOT equal across symbols.",
            "solution": "1) Add detailed risk logging per trade: symbol, pip_value, lot, sl_pips, risk_$\n2) Query MT5 symbol_info() for contract_size and trade_tick_value to compute real pip cost\n3) Use mt5.symbol_info(symbol).trade_tick_value instead of hardcoded pip_value * 100_000\n4) Verify that 1% risk = same dollar amount across all 8 symbols",
            "affected_files": ["risk/risk_manager.py", "config/base.yaml", "engine/trading_engine.py"],
            "estimated_impact": "Equalizes risk across all symbols — fixes the #1 data distortion",
            "depends_on": [],
            "notes": "Lot cap already fixed to 2.0 in commit b134470. But pip_value calculation may still be wrong for non-standard instruments.",
            "evidence": "Report: NZDUSD -$536/trade avg, XAUUSD -$7.7/trade avg — 70x difference",
        },
        {
            "code": "IMP-02",
            "title": "One position per symbol (prevent duplicates)",
            "title_ar": "قاعدة صفقة واحدة لكل زوج",
            "category": "RISK",
            "priority": "CRITICAL",
            "status": "DONE",
            "problem": "Multiple strategies could open trades on the same symbol simultaneously.",
            "solution": "Check open positions before executing — block if symbol already has a position.",
            "affected_files": ["engine/trading_engine.py"],
            "estimated_impact": "Eliminates conflicting trades",
            "notes": "IMPLEMENTED in execute_signal() lines 469-481. Checks MT5 open positions and blocks both conflicting directions AND duplicate same-direction trades.",
            "evidence": "Code verified: trading_engine.py:469-481",
        },
        {
            "code": "IMP-03",
            "title": "Disable SMA Crossover strategy",
            "title_ar": "إيقاف SMA Crossover فوراً",
            "category": "STRATEGY",
            "priority": "CRITICAL",
            "status": "PENDING",
            "problem": "SMA Crossover has 33% win rate and -$1,522 net loss from 9 trades. Lagging indicator enters after move is over. Lost on XAUUSD (3x) and NZDUSD (2x) repeatedly.",
            "solution": "Remove SMACrossoverStrategy from paper_trade.py create_strategies(). Keep the file — just don't register it. Re-enable only after adding H4 trend filter + backtesting.",
            "affected_files": ["scripts/paper_trade.py"],
            "estimated_impact": "Saves ~$1,500 estimated, raises Net PnL from $4,523 to ~$6,045",
            "depends_on": [],
            "evidence": "50-trade report: 33% WR, -$1,522 net from 9 trades",
        },
        {
            "code": "IMP-04",
            "title": "Disable ML Filtered SMA (no models exist)",
            "title_ar": "إيقاف ML Filtered SMA حتى تدريب النماذج",
            "category": "STRATEGY",
            "priority": "CRITICAL",
            "status": "DONE",
            "problem": "ML models don't exist for most symbols. Running ML strategy without models = plain SMA with no advantage.",
            "solution": "ML Filtered SMA is NOT registered in paper_trade.py — already disabled for data collection mode.",
            "affected_files": ["scripts/paper_trade.py"],
            "estimated_impact": "No random ML losses",
            "notes": "ALREADY DISABLED — paper_trade.py only registers: SMA, RSI, MACD, BB. ml_filtered_strategy.py exists but is not imported.",
            "evidence": "Code verified: paper_trade.py imports only 4 strategies, no ML",
        },
        {
            "code": "IMP-05",
            "title": "Add retry logic for MT5 operations",
            "title_ar": "إضافة Retry Logic عند فشل MT5",
            "category": "EXECUTION",
            "priority": "CRITICAL",
            "status": "PENDING",
            "problem": "No retry logic anywhere. If MT5 disconnects for 1 second during order execution, the order fails silently. System may think trade is open when it's not, or vice versa.",
            "solution": "1) Add retry decorator: 3 attempts, 2s delay between\n2) Apply to: place_order(), get_ohlcv(), get_account_info()\n3) After 3 failures: send Telegram alert and pause trading\n4) paper_trade.py already has reconnect logic (line 116) but only for get_account_info, not for order execution",
            "affected_files": ["execution/broker_adapters/mt5_adapter.py"],
            "estimated_impact": "Prevents silent execution failures",
            "depends_on": [],
            "notes": "paper_trade.py:113-118 has basic reconnect check but mt5_adapter.py has zero retry logic",
        },
        {
            "code": "IMP-06",
            "title": "Indicator warm-up validation",
            "title_ar": "مشكلة Warm-Up للمؤشرات",
            "category": "STRATEGY",
            "priority": "CRITICAL",
            "status": "DONE",
            "problem": "SMA200 needs 200 bars, MACD needs 35. If not enough bars, first values are NaN and system may generate signals on incomplete data.",
            "solution": "Config already sets history_bars=1000, which is 5x more than SMA200 needs. All strategies dropna() before generating signals.",
            "affected_files": [],
            "estimated_impact": "N/A — already handled",
            "notes": "ALREADY HANDLED: config/base.yaml history_bars=1000. All 4 strategies call dropna() on required indicator columns before generating signals. H4 fetches 200 bars (line 98). Safe.",
            "evidence": "Code: base.yaml:52 history_bars=1000, all strategies use dropna()",
        },

        # ══════════════════════════════════════════
        # HIGH — Orange
        # ══════════════════════════════════════════
        {
            "code": "IMP-07",
            "title": "Trade monitor loop (breakeven + trailing stop)",
            "title_ar": "نظام متابعة الصفقات المفتوحة — Monitor Loop",
            "category": "MONITORING",
            "priority": "HIGH",
            "status": "PENDING",
            "problem": "100% of losses are SL_HIT, 100% of profits are TP_HIT. System opens trade and abandons it. Misses opportunities to protect profits or cut losses early.",
            "solution": "Phase 1: Breakeven stop — when price moves +1x ATR in favor, move SL to entry\nPhase 2: Trailing stop — after breakeven, SL follows price at 1x ATR distance\nPhase 3: Partial TP — close 50% at TP1, trail remainder\nImplement as monitor_positions() called every 5 minutes via APScheduler",
            "affected_files": ["engine/trading_engine.py", "scripts/paper_trade.py", "execution/broker_adapters/mt5_adapter.py"],
            "estimated_impact": "Could convert -$840 losses to -$200, maximize winners beyond fixed TP",
            "depends_on": [],
            "notes": "MT5Adapter already has modify_position capability needed. Need to add SL modification method.",
            "evidence": "Report: 100% SL_HIT losses, 100% TP_HIT profits — no dynamic management",
        },
        {
            "code": "IMP-08",
            "title": "Link ML walk-forward results to config (per-symbol enable/disable)",
            "title_ar": "ربط ML Walk-Forward Results بالـ Config",
            "category": "CONFIG",
            "priority": "HIGH",
            "status": "PENDING",
            "problem": "Dashboard shows ML hurts USDJPY (PF drops 1.28→0.99) but system doesn't act on this. ML filter should be per-symbol configurable.",
            "solution": "Add to config/base.yaml:\nml_filter:\n  EURUSD: true  # PF 1.33→1.48\n  GBPUSD: true  # PF 1.13→1.23\n  USDJPY: false # PF 1.28→0.99\n  XAUUSD: true  # PF 1.40→1.60\nStrategies read this config before applying ML filter.",
            "affected_files": ["config/base.yaml", "strategies/ml_filtered_strategy.py"],
            "estimated_impact": "Prevents ML from degrading USDJPY performance",
            "depends_on": ["IMP-24"],
            "notes": "Only relevant after ML models are trained (IMP-24)",
        },
        {
            "code": "IMP-09",
            "title": "Load Optuna optimized params into live config",
            "title_ar": "ربط Optuna Parameters بالـ Live Config",
            "category": "CONFIG",
            "priority": "HIGH",
            "status": "PARTIAL",
            "problem": "Optuna found optimal SL/TP multipliers per symbol, but live uses same params for all symbols. Optimization exists but is decorative.",
            "solution": "Per-symbol SL/TP multipliers in config. data/optimized_params.yaml already has some params — ensure they include atr_sl_mult and atr_tp_mult per symbol.",
            "affected_files": ["config/base.yaml", "data/optimized_params.yaml", "scripts/paper_trade.py"],
            "estimated_impact": "Better SL/TP tuned to each symbol's volatility profile",
            "notes": "paper_trade.py already loads optimized_params.yaml for SMA periods. But SL/TP multipliers may not be per-symbol. Check optimized_params.yaml content.",
            "evidence": "paper_trade.py:47-50 loads opt_params, uses fast_period/slow_period but defaults sl/tp multipliers",
        },
        {
            "code": "IMP-10",
            "title": "H4 trend filter to block counter-trend entries",
            "title_ar": "H4 Trend Filter لمنع Counter-Trend Entries",
            "category": "STRATEGY",
            "priority": "HIGH",
            "status": "DONE",
            "problem": "USDJPY lost 3/4 trades all BUY while market was in clear downtrend. Reversal indicators fail in trending markets.",
            "solution": "Block trades against H4 trend direction.",
            "affected_files": ["engine/trading_engine.py"],
            "estimated_impact": "Eliminates counter-trend losses",
            "notes": "IMPLEMENTED in execute_signal() lines 483-490. Checks h4_trend from market context. Blocks SELL if H4=UP, blocks BUY if H4=DOWN. Allows RANGE.",
            "evidence": "Code verified: trading_engine.py:483-490",
        },
        {
            "code": "IMP-11",
            "title": "Correlated pairs exposure limit",
            "title_ar": "الأزواج المترابطة — مخاطرة مضاعفة خفية",
            "category": "RISK",
            "priority": "HIGH",
            "status": "PARTIAL",
            "problem": "System trades EURUSD+GBPUSD+AUDUSD+NZDUSD simultaneously — all correlated with USD. One USD news event = 4 losses at once.",
            "solution": "Calculate correlation between open positions. If correlation > 0.7 between two pairs, allow only 1 from the group. MAX_CORRELATED_POSITIONS=3 already in config but NOT enforced in code.",
            "affected_files": ["risk/risk_manager.py", "engine/trading_engine.py"],
            "estimated_impact": "Prevents 4x same-direction exposure",
            "depends_on": [],
            "notes": "Config has max_correlated_positions=3 (base.yaml:48) and RiskManager reads it (line 20) but NEVER uses it. No enforcement code exists.",
            "evidence": "risk_manager.py:20 reads max_correlated but no method uses it",
        },
        {
            "code": "IMP-12",
            "title": "Integrate news filter into main pipeline",
            "title_ar": "دمج News Filter في Pipeline الأساسي",
            "category": "STRATEGY",
            "priority": "HIGH",
            "status": "DONE",
            "problem": "Need to block trading around high-impact news events.",
            "solution": "News filter integrated in trading pipeline.",
            "affected_files": ["engine/trading_engine.py", "news/news_filter.py", "scripts/paper_trade.py"],
            "estimated_impact": "Avoids major news spikes",
            "notes": "FULLY IMPLEMENTED: news/news_filter.py exists, paper_trade.py:278-283 initializes NewsFilter(block_minutes_before=30, block_minutes_after=30, min_impact='HIGH'). trading_engine.py:104-160 checks news before execution, marks signals as NEWS_FILTERED.",
            "evidence": "Code verified across all 3 files",
        },
        {
            "code": "IMP-13",
            "title": "Minimum SL = 1.5x ATR for all strategies",
            "title_ar": "توسيع Stop Loss إلى 1.5x ATR كحد أدنى",
            "category": "RISK",
            "priority": "HIGH",
            "status": "PENDING",
            "problem": "USDCHF lost 3 trades with Bollinger Bounce: SL was ~2.4-2.9 pips while ATR ~2.5 pips. Normal noise hits SL then price reverses in right direction. Some strategies use SL < 1.5x ATR.",
            "solution": "Add minimum SL enforcement in execute_signal() or in RiskManager.validate_trade():\nmin_sl_atr = 1.5\nif sl_pips < atr_pips * min_sl_atr: sl = entry +/- atr * min_sl_atr\nPer-symbol override: GBPUSD needs 2.0x ATR (volatile).",
            "affected_files": ["engine/trading_engine.py", "risk/risk_manager.py"],
            "estimated_impact": "Saves USDCHF losses from tight stops, fewer noise stop-outs",
            "depends_on": [],
            "notes": "Current SL multipliers: SMA=2.0x, RSI=2.0x, MACD=2.5x, BB=2.0x. Most are >=1.5x already. But the enforcement should be in RiskManager as a safety net.",
            "evidence": "USDCHF 3 losses with BB, SL ~= ATR (too tight)",
        },
        {
            "code": "IMP-14",
            "title": "Restart protection — check MT5 positions on startup",
            "title_ar": "حماية عند إعادة تشغيل النظام",
            "category": "EXECUTION",
            "priority": "HIGH",
            "status": "DONE",
            "problem": "On restart, system might open duplicate positions on symbols that already have trades on MT5.",
            "solution": "Check MT5 open positions on startup and log them.",
            "affected_files": ["engine/trading_engine.py"],
            "estimated_impact": "Prevents duplicate positions on restart",
            "notes": "ALREADY HANDLED: execute_signal() checks MT5 open positions via adapter.get_open_positions() EVERY TIME before executing. This works regardless of restart — it always checks live MT5 state, not internal memory. Line 464: open_positions = self.adapter.get_open_positions()",
            "evidence": "Code: trading_engine.py:464-481 checks live MT5 positions before every trade",
        },

        # ══════════════════════════════════════════
        # MEDIUM — Yellow
        # ══════════════════════════════════════════
        {
            "code": "IMP-15",
            "title": "Session filter — block low-liquidity hours",
            "title_ar": "Session Filter — منع التداول في أوقات السيولة المنخفضة",
            "category": "STRATEGY",
            "priority": "MEDIUM",
            "status": "PENDING",
            "problem": "Most small XAUUSD losses ($6-$9) happen during low-liquidity hours. Price drifts randomly and hits SL.",
            "solution": "Add session check before signal execution:\nLondon: 07:00-16:00 UTC\nNew York: 12:00-20:00 UTC\nBlock: 20:00-07:00 UTC for EUR/GBP/CHF pairs\nException: USDJPY works in Tokyo 00:00-08:00 UTC",
            "affected_files": ["engine/trading_engine.py"],
            "estimated_impact": "Reduces noise trades in dead hours",
            "depends_on": [],
        },
        {
            "code": "IMP-16",
            "title": "Bollinger Bounce only in range markets (ADX filter)",
            "title_ar": "تخصيص Bollinger Bounce لأسواق Range فقط",
            "category": "STRATEGY",
            "priority": "MEDIUM",
            "status": "PENDING",
            "problem": "Bollinger Bounce lost on GBPUSD (-$410), USDCHF (3 losses), EURUSD (-$410) during trending conditions. Mean-reversion strategy fails in trends.",
            "solution": "Before BB signal: check ADX or BB Width.\nif ADX > 25: trending → block BB signal\nOr: if bb_width > threshold: trending → block\nAlternatively use volatility_regime from market context (already computed).",
            "affected_files": ["strategies/bollinger_bounce.py", "engine/trading_engine.py"],
            "estimated_impact": "Filters out BB signals in trending markets",
            "depends_on": [],
            "notes": "Market context already computes volatility_regime (HIGH/NORMAL/LOW). Could use this as proxy for trend vs range.",
        },
        {
            "code": "IMP-17",
            "title": "Daily loss limit — auto-pause trading",
            "title_ar": "Daily Loss Limit — حماية رأس المال",
            "category": "RISK",
            "priority": "MEDIUM",
            "status": "PARTIAL",
            "problem": "One bad day could stack losses: NZDUSD ($530+$550+$600) = $1,680 in one day. Need hard daily limit.",
            "solution": "MAX_DAILY_LOSS = balance * 0.02 (2%)\nBlock all new trades when hit. Send Telegram alert. Reset at UTC 00:00.",
            "affected_files": ["risk/risk_manager.py", "engine/trading_engine.py"],
            "estimated_impact": "Caps worst-case daily loss",
            "notes": "PARTIALLY IMPLEMENTED: RiskManager has max_daily_drawdown=0.05 (5%) and checks in can_open_trade(). BUT it uses self.daily_pnl which is set from account profit (unrealized), not from realized daily losses. Also 5% is too loose — should be 2%. The check works but the threshold and calculation need tuning.",
            "evidence": "risk_manager.py:73-79 checks drawdown but uses floating P&L not daily realized",
        },
        {
            "code": "IMP-18",
            "title": "Portfolio-level risk cap (total open risk)",
            "title_ar": "Portfolio-Level Risk — حد أقصى للخطر الكلي",
            "category": "RISK",
            "priority": "MEDIUM",
            "status": "PENDING",
            "problem": "Each trade risks 1% individually. 5 open trades = 5% at risk simultaneously, especially with correlated pairs.",
            "solution": "MAX_TOTAL_RISK = 3% of account\nBefore opening: sum risk of all open positions\nif current_total_risk + new_risk > MAX_TOTAL_RISK: block",
            "affected_files": ["risk/risk_manager.py", "engine/trading_engine.py"],
            "estimated_impact": "Limits aggregate exposure",
            "depends_on": ["IMP-11"],
        },
        {
            "code": "IMP-19",
            "title": "Account for spread in SL/TP calculations",
            "title_ar": "احتساب Spread في حسابات SL وTP",
            "category": "EXECUTION",
            "priority": "MEDIUM",
            "status": "PENDING",
            "problem": "XAUUSD has 30-50 pip spread sometimes. SL/TP calculated without spread offset. Real R:R is worse than displayed.",
            "solution": "Effective SL = SL + spread, Effective TP = TP - spread\nGet spread from MT5: symbol_info.spread * point\nAdjust automatically in execute_signal() before placing order.",
            "affected_files": ["engine/trading_engine.py", "execution/broker_adapters/mt5_adapter.py"],
            "estimated_impact": "More accurate R:R, prevents premature SL hits from spread",
            "notes": "Market context already captures spread (trading_engine.py:346-351). Just need to use it in SL/TP adjustment.",
        },
        {
            "code": "IMP-20",
            "title": "Dynamic allocation based on symbol performance",
            "title_ar": "زيادة Allocation لـ AUDUSD وEURUSD وGBPUSD",
            "category": "RISK",
            "priority": "MEDIUM",
            "status": "SKIPPED",
            "problem": "AUDUSD 100% WR, EURUSD 60% WR — these perform better. USDJPY underperforms.",
            "solution": "SKIPPED — 50 trades is too small a sample to adjust allocation. Risk of overfitting to noise. Revisit after 200+ trades.",
            "affected_files": [],
            "estimated_impact": "Potentially higher returns from better-performing pairs",
            "notes": "SKIPPED for now. 50 trades insufficient for reliable allocation decisions. Would need 6+ months of data.",
        },
        {
            "code": "IMP-21",
            "title": "Dynamic confidence scoring for strategies",
            "title_ar": "نظام Dynamic Confidence للاستراتيجيات",
            "category": "STRATEGY",
            "priority": "MEDIUM",
            "status": "SKIPPED",
            "problem": "System uses fixed params regardless of recent strategy performance.",
            "solution": "SKIPPED — over-engineering at this stage. Adds complexity without proven benefit. The same effect is achieved by periodically reviewing and disabling underperformers manually (which we're already doing with IMP-03).",
            "affected_files": [],
            "estimated_impact": "Marginal",
            "notes": "SKIPPED: Not needed with manual monthly reviews. Revisit if system scales to 20+ strategies.",
        },
        {
            "code": "IMP-22",
            "title": "Increase scan frequency to 15 minutes",
            "title_ar": "فحص كل 15 دقيقة",
            "category": "INFRASTRUCTURE",
            "priority": "MEDIUM",
            "status": "SKIPPED",
            "problem": "H1 scan may miss mid-hour opportunities.",
            "solution": "SKIPPED — We trade on H1 timeframe. Scanning every 15 minutes would generate signals on incomplete H1 candles, leading to false crossovers and noise. H1 scan at :05 past the hour is correct for H1 strategy.",
            "affected_files": [],
            "estimated_impact": "Negative — would increase noise",
            "notes": "SKIPPED: Counter-productive for H1-based strategies.",
        },

        # ══════════════════════════════════════════
        # LOW — Blue (Infrastructure)
        # ══════════════════════════════════════════
        {
            "code": "IMP-23",
            "title": "Trailing stop for winning trades",
            "title_ar": "Trailing Stop للصفقات الرابحة",
            "category": "MONITORING",
            "priority": "LOW",
            "status": "PENDING",
            "problem": "100% of profits exit at fixed TP. Winning trades that could run further are capped.",
            "solution": "Implement as part of IMP-07 (Monitor Loop). trailing_distance = 1.0x ATR. Start trailing after breakeven is activated.",
            "affected_files": ["engine/trading_engine.py"],
            "estimated_impact": "Maximizes winners beyond fixed TP",
            "depends_on": ["IMP-07"],
        },
        {
            "code": "IMP-24",
            "title": "Train ML models and re-enable ML filtered strategy",
            "title_ar": "تدريب ML Models وإعادة تفعيل ml_filtered_sma",
            "category": "STRATEGY",
            "priority": "LOW",
            "status": "PENDING",
            "problem": "Walk-forward shows ML improves PF by +0.15 to +0.20 on EURUSD/XAUUSD. But models don't exist in data/models/.",
            "solution": "1) Collect 200+ trades (need ~150 more)\n2) Run training pipeline\n3) Validate with walk-forward\n4) Enable only for symbols where ML improves PF (per IMP-08)",
            "affected_files": ["scripts/train_ml_models.py", "data/models/"],
            "estimated_impact": "+0.15 to +0.20 Profit Factor improvement",
            "depends_on": [],
            "notes": "Need more trade data first. Currently at ~50 trades, need 200+. Target: June 2026.",
        },
        {
            "code": "IMP-25",
            "title": "Unified decision logging for every signal",
            "title_ar": "Log موحد لكل قرار في النظام",
            "category": "INFRASTRUCTURE",
            "priority": "LOW",
            "status": "PARTIAL",
            "problem": "Hard to trace why a trade was taken or rejected. Each signal should have a complete audit trail.",
            "solution": "Format: [SIGNAL] EURUSD | MACD | BUY | H4=UP OK | ATR=0.0008 | ML=72% | lot=0.10 | EXECUTED",
            "affected_files": ["engine/trading_engine.py"],
            "estimated_impact": "Much easier post-analysis",
            "notes": "PARTIALLY DONE: SignalLog table exists and records signals with status (EXECUTED, ML_FILTERED, NEWS_FILTERED, RISK_REJECTED). But the log format is fragmented across multiple logger.info() calls, not a single structured line. ScanLog and SymbolScanDetail also capture context.",
            "evidence": "trading_engine.py:591-617 _log_signal(), lines 813-816 logger.info()",
        },
        {
            "code": "IMP-26",
            "title": "External alerts (Telegram bot)",
            "title_ar": "نظام Alerts خارج الداشبورد",
            "category": "INFRASTRUCTURE",
            "priority": "LOW",
            "status": "DONE",
            "problem": "Need notifications outside the dashboard.",
            "solution": "Telegram bot for trade alerts.",
            "affected_files": ["observability/telegram_notifier.py"],
            "estimated_impact": "Real-time awareness",
            "notes": "FULLY IMPLEMENTED: observability/telegram_notifier.py exists. Called in paper_trade.py for bot_started, scan_report, and in trading_engine.py for signal_executed, signal_filtered, trade_closed.",
            "evidence": "Code verified across multiple files",
        },
        {
            "code": "IMP-27",
            "title": "Separate config for paper vs live trading",
            "title_ar": "فصل Config بين بيئة Paper وLive",
            "category": "CONFIG",
            "priority": "LOW",
            "status": "PENDING",
            "problem": "Single config/base.yaml for both modes. When switching to live, one config mistake could trade real money with wrong params.",
            "solution": "config/paper.yaml — higher lots, more risk for testing\nconfig/live.yaml — smaller lots, tighter limits\n.env TRADING_MODE selects config automatically.",
            "affected_files": ["config/paper.yaml", "config/live.yaml", "engine/trading_engine.py"],
            "estimated_impact": "Safety when transitioning to live",
            "depends_on": [],
            "notes": "Not urgent — still in paper mode. Do before going live.",
        },
        {
            "code": "IMP-28",
            "title": "Verify no look-ahead bias in walk-forward",
            "title_ar": "فحص Look-Ahead Bias في Walk-Forward",
            "category": "INFRASTRUCTURE",
            "priority": "LOW",
            "status": "DONE",
            "problem": "If indicators are computed on full dataset before train/test split, ML 'sees the future'.",
            "solution": "Indicators are stateless rolling functions. Each takes a DataFrame and computes rolling windows — no future data leakage.",
            "affected_files": [],
            "estimated_impact": "N/A — no issue found",
            "notes": "VERIFIED: All indicator functions in features/technical/indicators.py are stateless rolling calculations (add_sma, add_rsi, add_atr, etc.). They only look backward. Walk-forward should be safe as long as train/test split happens before feature computation in the ML pipeline.",
            "evidence": "indicators.py uses pd.rolling() which is backward-looking only",
        },

        # ══════════════════════════════════════════
        # NEW — Additional improvements found during code review
        # ══════════════════════════════════════════
        {
            "code": "IMP-29",
            "title": "Add modify_position method to MT5Adapter",
            "title_ar": "إضافة تعديل الصفقة (SL/TP) في MT5Adapter",
            "category": "EXECUTION",
            "priority": "HIGH",
            "status": "PENDING",
            "problem": "MT5Adapter has place_order() and close_position() but no method to modify SL/TP of an open position. This is required for IMP-07 (trailing stop/breakeven).",
            "solution": "Add modify_position(ticket, sl, tp) using mt5.TRADE_ACTION_SLTP.",
            "affected_files": ["execution/broker_adapters/mt5_adapter.py"],
            "estimated_impact": "Prerequisite for trailing stops",
            "depends_on": [],
            "notes": "Blocking dependency for IMP-07 and IMP-23.",
        },
        {
            "code": "IMP-30",
            "title": "Enforce max_correlated_positions in code",
            "title_ar": "تفعيل حد الأزواج المترابطة في الكود",
            "category": "RISK",
            "priority": "HIGH",
            "status": "PENDING",
            "problem": "Config has max_correlated_positions=3 and RiskManager reads it (line 20) but NEVER enforces it. The value is loaded and ignored.",
            "solution": "Define correlation groups:\nUSD_LONG = [EURUSD-SELL, GBPUSD-SELL, AUDUSD-SELL, NZDUSD-SELL]\nUSD_SHORT = [EURUSD-BUY, GBPUSD-BUY, AUDUSD-BUY, NZDUSD-BUY]\nBefore opening: count open positions in same group. Block if >= max_correlated.",
            "affected_files": ["risk/risk_manager.py", "engine/trading_engine.py"],
            "estimated_impact": "Prevents 4x USD exposure in same direction",
            "depends_on": [],
            "notes": "Simpler than computing live correlation — use static groups based on known forex correlations.",
        },
        {
            "code": "IMP-31",
            "title": "Strategy priority when multiple signals on same symbol",
            "title_ar": "ترتيب أولوية الاستراتيجيات عند تعدد الإشارات",
            "category": "STRATEGY",
            "priority": "MEDIUM",
            "status": "PENDING",
            "problem": "4 strategies per symbol can generate conflicting signals (e.g., MACD says BUY, BB says SELL). Current code executes the first valid one. No priority ordering.",
            "solution": "Rank strategies by historical performance or confidence:\n1. MACD Crossover (best PF)\n2. RSI Reversal\n3. Bollinger Bounce\n4. SMA Crossover (worst — disabled)\nIf multiple signals on same symbol, take highest-priority only.",
            "affected_files": ["engine/trading_engine.py"],
            "estimated_impact": "Ensures best strategy wins per symbol",
            "depends_on": ["IMP-02"],
            "notes": "IMP-02 already prevents multiple positions per symbol, but strategy execution order in scan_signals() determines which gets executed first.",
        },
        {
            "code": "IMP-32",
            "title": "Log risk details per trade (risk $, lot calc, pip value)",
            "title_ar": "تسجيل تفاصيل المخاطرة لكل صفقة",
            "category": "INFRASTRUCTURE",
            "priority": "HIGH",
            "status": "PENDING",
            "problem": "Cannot verify if position sizing is correct without seeing the calculation. RiskManager only logs debug-level with partial info.",
            "solution": "In execute_signal(), after calculate_position_size():\nlogger.info(f'[RISK] {symbol} | pip_value={pip_value} | sl_pips={sl_pips:.1f} | risk_$={risk_amount:.2f} | lot={lot_size}')\nAlso save to SignalLog or a new RiskLog table.",
            "affected_files": ["engine/trading_engine.py", "risk/risk_manager.py"],
            "estimated_impact": "Full transparency on position sizing — validates IMP-01",
            "depends_on": [],
        },
    ]

    for imp in improvements:
        insert_improvement(conn, imp)
        print(f"  {imp['code']} [{imp['status']:>10}] {imp['title']}")

    # Print summary
    c = conn.cursor()
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for status in ["DONE", "PARTIAL", "PENDING", "SKIPPED"]:
        c.execute("SELECT COUNT(*) FROM improvements WHERE status = ?", (status,))
        count = c.fetchone()[0]
        print(f"  {status:>10}: {count}")

    print()
    for priority in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        c.execute("SELECT COUNT(*) FROM improvements WHERE priority = ? AND status NOT IN ('DONE', 'SKIPPED')", (priority,))
        count = c.fetchone()[0]
        if count > 0:
            print(f"  {priority:>10} remaining: {count}")

    print()
    c.execute("SELECT code, title FROM improvements WHERE priority = 'CRITICAL' AND status = 'PENDING'")
    pending_critical = c.fetchall()
    if pending_critical:
        print("ACTION NEEDED (Critical + Pending):")
        for code, title in pending_critical:
            print(f"  {code}: {title}")

    conn.close()
    print(f"\nDatabase saved to: {DB_PATH}")


if __name__ == "__main__":
    populate()
