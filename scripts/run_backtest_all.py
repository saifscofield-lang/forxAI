"""
Universal Backtest Runner — اختبار شامل لجميع الاستراتيجيات × الأزواج × الأطر الزمنية
النتائج تُحفظ في data/backtest_results.db + إشعارات Telegram
يُنتج ملف data/backtest_approved.yaml يُقرأ من paper_trade.py

Usage:
    python scripts/run_backtest_all.py                        # الكل
    python scripts/run_backtest_all.py --strategy macd_crossover
    python scripts/run_backtest_all.py --symbol EURUSD
    python scripts/run_backtest_all.py --timeframe M15
"""
import sys
import os
sys.path.insert(0, ".")
os.environ["PYTHONIOENCODING"] = "utf-8"

from dotenv import load_dotenv
load_dotenv()

import argparse
import sqlite3
import time as _time
import yaml
from datetime import datetime, timezone
import pandas as pd
from loguru import logger

from backtest.universal_backtester import UniversalBacktester, BacktestResult
from backtest.metrics import compute_metrics, format_report
from strategies.rsi_reversal import RSIReversalStrategy
from strategies.macd_crossover import MACDCrossoverStrategy
from strategies.bollinger_bounce import BollingerBounceStrategy
from strategies.sma_crossover import SMACrossoverStrategy
from strategies.stop_hunt_reversal import StopHuntReversalStrategy
from strategies.asia_breakout import AsiaBreakoutStrategy
from observability.telegram_notifier import TelegramNotifier
from engine.scoring import compute_score, format_score, grade_from_score

# ML strategies — optional (need trained models)
try:
    from strategies.ml_direct_strategy import MLDirectStrategy
    ML_DIRECT_AVAILABLE = True
except ImportError:
    ML_DIRECT_AVAILABLE = False

try:
    from strategies.ml_filtered_strategy import MLFilteredStrategy
    ML_FILTERED_AVAILABLE = True
except ImportError:
    ML_FILTERED_AVAILABLE = False

DB_PATH = "data/backtest_results.db"
APPROVED_PATH = "data/backtest_approved.yaml"

# ── Risk Profiles ──
RISK_PROFILES = {
    "strict": {
        "name": "صارم (Live)",
        "min_trades": 50,
        "min_profit_factor": 1.3,
        "max_drawdown_pct": 8.0,
        "min_win_rate": 45.0,
        "min_sharpe": 0.5,
    },
    "moderate": {
        "name": "متوسط (Paper)",
        "min_trades": 30,
        "min_profit_factor": 1.15,
        "max_drawdown_pct": 10.0,
        "min_win_rate": 40.0,
        "min_sharpe": 0.3,
    },
    "aggressive": {
        "name": "مجازف (تجريبي)",
        "min_trades": 15,
        "min_profit_factor": 1.05,
        "max_drawdown_pct": 15.0,
        "min_win_rate": 35.0,
        "min_sharpe": 0.0,
    },
}

DEFAULT_PROFILE = "moderate"

# ── All available strategy names ──
ALL_STRATEGY_NAMES = [
    "sma_crossover", "rsi_reversal", "macd_crossover", "bollinger_bounce",
    "ml_direct", "ml_filtered_sma",
]


def preflight_check(config_path: str = "config/base.yaml") -> bool:
    """
    فحص المتطلبات قبل تشغيل الباك تست
    Check all requirements before running backtest. Returns True if ready.
    """
    print()
    print("=" * 60)
    print("     PRE-FLIGHT CHECK")
    print("=" * 60)

    errors = []
    warnings = []

    # 1. Check required packages
    print("\n  [1/5] Checking packages...")
    required_packages = {
        "pandas": "pandas",
        "numpy": "numpy",
        "yaml": "pyyaml",
        "loguru": "loguru",
        "dotenv": "python-dotenv",
        "sqlalchemy": "sqlalchemy",
    }
    for import_name, pip_name in required_packages.items():
        try:
            __import__(import_name)
            print(f"        [OK] {pip_name}")
        except ImportError:
            errors.append(f"Missing package: {pip_name} (pip install {pip_name})")
            print(f"        [X]  {pip_name} -- NOT INSTALLED")

    # 2. Check config file
    print("\n  [2/5] Checking config...")
    if not os.path.exists(config_path):
        errors.append(f"Config file missing: {config_path}")
        print(f"        [X]  {config_path} -- NOT FOUND")
    else:
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            instruments = config.get("instruments", [])
            if not instruments:
                errors.append("No instruments defined in config")
                print("        [X]  No instruments in config")
            else:
                symbols = [i["symbol"] for i in instruments]
                print(f"        [OK] {config_path} -- {len(instruments)} instruments: {', '.join(symbols)}")
        except Exception as e:
            errors.append(f"Config parse error: {e}")
            print(f"        [X]  Config error: {e}")

    # 3. Check historical data (parquet files)
    print("\n  [3/5] Checking historical data...")
    data_dir = "data/raw"
    if not os.path.exists(data_dir):
        errors.append(
            f"No historical data directory: {data_dir}\n"
            "        -> Run: python scripts/download_historical_data.py"
        )
        print(f"        [X]  {data_dir}/ -- NOT FOUND")
        print("              -> Run: python scripts/download_historical_data.py")
    else:
        timeframes_to_check = ["M15", "H1", "H4", "D1"]
        total_files = 0
        missing_data = []
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            instruments = config.get("instruments", [])
        except Exception:
            instruments = []

        for inst in instruments:
            sym = inst["symbol"]
            sym_dir = os.path.join(data_dir, sym)
            if not os.path.exists(sym_dir):
                missing_data.append(f"{sym} (no folder)")
                continue
            found_tfs = []
            for tf in timeframes_to_check:
                path = os.path.join(sym_dir, f"{tf}.parquet")
                if os.path.exists(path):
                    size_mb = os.path.getsize(path) / (1024 * 1024)
                    found_tfs.append(f"{tf}({size_mb:.1f}MB)")
                    total_files += 1
                else:
                    missing_data.append(f"{sym}/{tf}")
            if found_tfs:
                print(f"        [OK] {sym}: {', '.join(found_tfs)}")

        if missing_data:
            for m in missing_data:
                print(f"        [!!] {m} -- MISSING")
            if total_files == 0:
                errors.append(
                    "No historical data files found!\n"
                    "        -> Run: python scripts/download_historical_data.py"
                )
            else:
                warnings.append(f"Missing data for: {', '.join(missing_data)}")

    # 4. Check strategies
    print("\n  [4/5] Checking strategies...")
    strategy_status = {
        "sma_crossover": ("SMACrossoverStrategy", True),
        "rsi_reversal": ("RSIReversalStrategy", True),
        "macd_crossover": ("MACDCrossoverStrategy", True),
        "bollinger_bounce": ("BollingerBounceStrategy", True),
        "stop_hunt_reversal": ("StopHuntReversalStrategy", True),
        "asia_breakout": ("AsiaBreakoutStrategy", True),
        "ml_direct": ("MLDirectStrategy", ML_DIRECT_AVAILABLE),
        "ml_filtered_sma": ("MLFilteredStrategy", ML_FILTERED_AVAILABLE),
    }
    available_count = 0
    for name, (cls_name, available) in strategy_status.items():
        if available:
            print(f"        [OK] {name} ({cls_name})")
            available_count += 1
        else:
            print(f"        [!!] {name} ({cls_name}) -- import failed (optional)")
            warnings.append(f"Strategy {name} not available (missing dependencies)")

    # Check ML models if ML strategies are available
    if ML_DIRECT_AVAILABLE or ML_FILTERED_AVAILABLE:
        model_dir = "models/market_learner"
        if os.path.exists(model_dir):
            models = [f for f in os.listdir(model_dir) if f.endswith("_model.pkl")]
            model_symbols = [f.replace("_model.pkl", "") for f in models]
            print(f"        [OK] ML models: {', '.join(model_symbols)}")
        else:
            warnings.append("ML models directory not found -- ML strategies will skip symbols without models")
            print(f"        [!!] {model_dir}/ -- NOT FOUND (ML strategies need trained models)")

    if available_count == 0:
        errors.append("No strategies available!")

    # 5. Check backtest engine
    print("\n  [5/5] Checking backtest engine...")
    try:
        from backtest.universal_backtester import UniversalBacktester
        print("        [OK] UniversalBacktester")
    except ImportError as e:
        errors.append(f"Backtest engine import failed: {e}")
        print(f"        [X]  UniversalBacktester -- {e}")
    try:
        from backtest.metrics import compute_metrics, format_report
        print("        [OK] Metrics module")
    except ImportError as e:
        errors.append(f"Metrics import failed: {e}")
        print(f"        [X]  Metrics -- {e}")

    # -- Summary --
    print()
    print("-" * 60)
    if errors:
        print(f"  [FAILED] {len(errors)} error(s), {len(warnings)} warning(s)")
        print()
        for i, err in enumerate(errors, 1):
            print(f"  ERROR {i}: {err}")
        if warnings:
            print()
            for w in warnings:
                print(f"  WARNING: {w}")
        print()
        print("  Fix the errors above, then run again.")
        print("=" * 60)
        return False
    else:
        if warnings:
            print(f"  [READY] with {len(warnings)} warning(s)")
            for w in warnings:
                print(f"     [!!] {w}")
        else:
            print("  [OK] ALL CHECKS PASSED -- Ready to backtest!")
        print("=" * 60)
        print()
        return True


def init_backtest_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS backtest_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        run_time TEXT NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        strategy TEXT NOT NULL,
        strategy_version TEXT,
        period_start TEXT,
        period_end TEXT,
        total_bars INTEGER,
        initial_balance REAL,
        final_balance REAL,
        total_pnl REAL,
        total_return_pct REAL,
        total_trades INTEGER,
        winning_trades INTEGER,
        losing_trades INTEGER,
        win_rate REAL,
        profit_factor REAL,
        sharpe_ratio REAL,
        max_drawdown_pct REAL,
        max_drawdown_dollar REAL,
        avg_win REAL,
        avg_loss REAL,
        avg_pnl_per_trade REAL,
        avg_win_pips REAL,
        avg_loss_pips REAL,
        avg_trade_bars REAL,
        max_consecutive_wins INTEGER,
        max_consecutive_losses INTEGER,
        expectancy REAL,
        spread_pips REAL,
        risk_per_trade REAL,
        verdict TEXT DEFAULT 'PENDING',
        score REAL DEFAULT 0,
        grade TEXT DEFAULT 'F',
        ev_score REAL,
        pf_score REAL,
        dd_score REAL,
        trades_score REAL,
        wr_score REAL,
        fatal_reasons TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS backtest_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        trade_num INTEGER,
        symbol TEXT,
        action TEXT,
        strategy TEXT,
        strategy_version TEXT,
        entry_price REAL,
        exit_price REAL,
        stop_loss REAL,
        take_profit REAL,
        entry_time TEXT,
        exit_time TEXT,
        exit_reason TEXT,
        lot_size REAL,
        pnl REAL,
        pnl_pips REAL,
        rr_planned REAL,
        rr_actual REAL,
        duration_minutes INTEGER
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS backtest_equity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        time TEXT,
        balance REAL,
        equity REAL,
        open_trades INTEGER
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS backtest_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        time TEXT NOT NULL,
        level TEXT NOT NULL,
        message TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def is_already_tested(symbol: str, timeframe: str, strategy_name: str, strategy_version: str) -> dict | None:
    """Check if this exact strategy version was already backtested. Returns the existing run or None."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT run_id, total_trades, win_rate, profit_factor, total_pnl,
                   max_drawdown_pct, sharpe_ratio, verdict
            FROM backtest_runs
            WHERE symbol = ? AND timeframe = ? AND strategy = ? AND strategy_version = ?
            ORDER BY run_time DESC LIMIT 1
        """, (symbol, timeframe, strategy_name, strategy_version))
        row = c.fetchone()
        conn.close()
        if row:
            return {
                "run_id": row[0], "total_trades": row[1], "win_rate": row[2],
                "profit_factor": row[3], "total_pnl": row[4],
                "max_drawdown_pct": row[5], "sharpe_ratio": row[6], "verdict": row[7],
            }
    except Exception:
        pass
    return None


def log_event(run_id: str, level: str, message: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO backtest_log (run_id, time, level, message) VALUES (?,?,?,?)",
            (run_id, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), level, message)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def save_results(run_id: str, result: BacktestResult, report, spread_pips: float, risk_per_trade: float, profile: dict = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Compute score and grade
    score_breakdown = compute_score(report)

    # Verdict: grade S or A = PASS, B = REVIEW, C/F = FAIL
    # Also check profile minimums for backwards compatibility
    p = profile or RISK_PROFILES[DEFAULT_PROFILE]
    profile_pass = (
        report.total_trades >= p["min_trades"]
        and report.profit_factor >= p["min_profit_factor"]
        and report.max_drawdown_pct <= p["max_drawdown_pct"]
        and report.win_rate >= p["min_win_rate"]
        and report.sharpe_ratio >= p["min_sharpe"]
        and report.total_pnl > 0
    )
    if score_breakdown.grade in ("S", "A"):
        verdict = "PASS"
    elif score_breakdown.grade == "B" and profile_pass:
        verdict = "PASS"
    else:
        verdict = "FAIL"

    c.execute("""
    INSERT INTO backtest_runs (
        run_id, run_time, symbol, timeframe, strategy, strategy_version,
        period_start, period_end, total_bars, initial_balance, final_balance,
        total_pnl, total_return_pct, total_trades, winning_trades, losing_trades,
        win_rate, profit_factor, sharpe_ratio, max_drawdown_pct, max_drawdown_dollar,
        avg_win, avg_loss, avg_pnl_per_trade, avg_win_pips, avg_loss_pips,
        avg_trade_bars, max_consecutive_wins, max_consecutive_losses, expectancy,
        spread_pips, risk_per_trade, verdict,
        score, grade, ev_score, pf_score, dd_score, trades_score, wr_score, fatal_reasons
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        run_id, now, result.symbol, result.timeframe, result.strategy,
        result.strategy_version, str(result.start_date), str(result.end_date),
        len(result.equity_curve) * 5,
        result.initial_balance, result.final_balance,
        report.total_pnl, report.total_return_pct,
        report.total_trades, report.winning_trades, report.losing_trades,
        report.win_rate, report.profit_factor, report.sharpe_ratio,
        report.max_drawdown_pct, report.max_drawdown_dollar,
        report.avg_win, report.avg_loss, report.avg_pnl_per_trade,
        report.avg_win_pips, report.avg_loss_pips, report.avg_trade_bars,
        report.max_consecutive_wins, report.max_consecutive_losses,
        report.expectancy, spread_pips, risk_per_trade, verdict,
        score_breakdown.total_score, score_breakdown.grade,
        score_breakdown.ev_score, score_breakdown.pf_score,
        score_breakdown.dd_score, score_breakdown.trades_score,
        score_breakdown.wr_score, "; ".join(score_breakdown.fatal_reasons) if score_breakdown.fatal_reasons else None,
    ))

    for t in result.trades:
        c.execute("""
        INSERT INTO backtest_trades (
            run_id, trade_num, symbol, action, strategy, strategy_version,
            entry_price, exit_price, stop_loss, take_profit,
            entry_time, exit_time, exit_reason, lot_size,
            pnl, pnl_pips, rr_planned, rr_actual, duration_minutes
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            run_id, t.id, t.symbol, t.action, t.strategy, t.strategy_version,
            t.entry_price, t.exit_price, t.stop_loss, t.take_profit,
            str(t.entry_time), str(t.exit_time), t.exit_reason, t.lot_size,
            t.pnl, t.pnl_pips, t.rr_planned, t.rr_actual, t.duration_minutes,
        ))

    for eq in result.equity_curve:
        c.execute(
            "INSERT INTO backtest_equity (run_id, time, balance, equity, open_trades) VALUES (?,?,?,?,?)",
            (run_id, str(eq["time"]), eq["balance"], eq["equity"], eq["open_trades"]))

    conn.commit()
    conn.close()
    return verdict, score_breakdown


def generate_approved_yaml(master_run_id: str, profile_name: str = DEFAULT_PROFILE):
    """Generate backtest_approved.yaml from latest PASS results per strategy-symbol pair."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Get the latest PASS result for each symbol+strategy combo (not just this run)
    c.execute("""
        SELECT symbol, strategy, strategy_version, timeframe,
               total_trades, win_rate, profit_factor, total_pnl,
               max_drawdown_pct, sharpe_ratio, verdict,
               COALESCE(score, 0), COALESCE(grade, '?')
        FROM backtest_runs
        WHERE verdict = 'PASS'
        AND id IN (
            SELECT MAX(id) FROM backtest_runs
            WHERE verdict = 'PASS'
            GROUP BY symbol, strategy, strategy_version, timeframe
        )
        ORDER BY score DESC, symbol, strategy
    """)
    rows = c.fetchall()
    conn.close()

    p = RISK_PROFILES[profile_name]
    approved = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "run_id": master_run_id,
        "profile": profile_name,
        "profile_name": p["name"],
        "criteria": {
            "min_trades": p["min_trades"],
            "min_profit_factor": p["min_profit_factor"],
            "max_drawdown_pct": p["max_drawdown_pct"],
            "min_win_rate": p["min_win_rate"],
            "min_sharpe": p["min_sharpe"],
        },
        "approved": {},
    }

    for row in rows:
        symbol, strategy, version, tf, trades, wr, pf, pnl, dd, sharpe, verdict = row[:11]
        score = row[11] if len(row) > 11 else 0
        grade = row[12] if len(row) > 12 else "?"
        key = f"{symbol}_{strategy}"
        approved["approved"][key] = {
            "symbol": symbol,
            "strategy": strategy,
            "version": version,
            "timeframe": tf,
            "trades": trades,
            "win_rate": round(wr, 1),
            "profit_factor": round(pf, 3),
            "total_pnl": round(pnl, 2),
            "max_drawdown_pct": round(dd, 1),
            "sharpe": round(sharpe, 3),
            "score": round(score, 1),
            "grade": grade,
        }

    with open(APPROVED_PATH, "w", encoding="utf-8") as f:
        yaml.dump(approved, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return approved


def load_data(symbol: str, timeframe: str) -> pd.DataFrame:
    path = f"data/raw/{symbol}/{timeframe}.parquet"
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    df = df.sort_values("time").reset_index(drop=True)
    return df


def create_all_strategies(symbol: str, config: dict):
    try:
        with open("data/optimized_params.yaml", "r") as f:
            opt_params = yaml.safe_load(f) or {}
    except FileNotFoundError:
        opt_params = {}

    params = opt_params.get(symbol, {})
    sl_mult = float(params.get("atr_sl_mult", 2.0))
    tp_mult = float(params.get("atr_tp_mult", 3.0))

    strategies = [
        SMACrossoverStrategy(
            symbol=symbol,
            atr_sl_multiplier=sl_mult, atr_tp_multiplier=tp_mult,
        ),
        RSIReversalStrategy(
            symbol=symbol, rsi_period=14,
            oversold=30.0, overbought=70.0,
            atr_sl_multiplier=sl_mult, atr_tp_multiplier=tp_mult,
        ),
        MACDCrossoverStrategy(
            symbol=symbol,
            atr_sl_multiplier=sl_mult * 1.25,
            atr_tp_multiplier=tp_mult * 1.15,
        ),
        BollingerBounceStrategy(
            symbol=symbol,
            atr_sl_multiplier=sl_mult, atr_tp_multiplier=tp_mult,
        ),
        StopHuntReversalStrategy(
            symbol=symbol,
            atr_sl_multiplier=sl_mult, atr_tp_multiplier=tp_mult,
            pip_value=0.01 if ("JPY" in symbol or "XAU" in symbol) else 0.0001,
        ),
        AsiaBreakoutStrategy(
            symbol=symbol,
            atr_sl_multiplier=sl_mult, atr_tp_multiplier=tp_mult,
            pip_value=0.01 if ("JPY" in symbol or "XAU" in symbol) else 0.0001,
        ),
    ]

    # ML Direct — only if available and model exists for this symbol
    if ML_DIRECT_AVAILABLE:
        model_path = f"models/market_learner/{symbol}_model.pkl"
        if os.path.exists(model_path):
            try:
                strategies.append(MLDirectStrategy(
                    symbol=symbol,
                    atr_sl_multiplier=sl_mult, atr_tp_multiplier=tp_mult,
                ))
            except Exception as e:
                logger.warning(f"Could not load MLDirectStrategy for {symbol}: {e}")

    # ML Filtered SMA — only if available and model exists
    if ML_FILTERED_AVAILABLE:
        model_path = f"models/market_learner/{symbol}_model.pkl"
        if os.path.exists(model_path):
            try:
                import pickle
                with open(model_path, "rb") as f:
                    model = pickle.load(f)
                strategies.append(MLFilteredStrategy(
                    symbol=symbol, model=model,
                    atr_sl_multiplier=sl_mult, atr_tp_multiplier=tp_mult,
                ))
            except Exception as e:
                logger.warning(f"Could not load MLFilteredStrategy for {symbol}: {e}")

    return strategies


def main():
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        level="INFO", colorize=True,
    )
    os.makedirs("data/logs", exist_ok=True)
    logger.add(
        "data/logs/backtest.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
        level="INFO", rotation="10 MB",
    )

    parser = argparse.ArgumentParser(description="ForexAI Universal Backtest")
    parser.add_argument("--strategy", type=str)
    parser.add_argument("--symbol", type=str)
    parser.add_argument("--timeframe", type=str, default=None,
                        help="Specific timeframe, or omit to test all available")
    parser.add_argument("--profile", type=str, default=DEFAULT_PROFILE,
                        choices=list(RISK_PROFILES.keys()),
                        help="Risk profile: strict, moderate, aggressive")
    parser.add_argument("--force", action="store_true",
                        help="Force re-run all tests (ignore cache)")
    parser.add_argument("--skip-check", action="store_true",
                        help="Skip pre-flight checks")
    args = parser.parse_args()

    # ── Pre-flight check ──
    if not args.skip_check:
        if not preflight_check():
            sys.exit(1)

    profile_name = args.profile
    profile = RISK_PROFILES[profile_name]

    init_backtest_db()
    notifier = TelegramNotifier()

    with open("config/base.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    instruments = config.get("instruments", [])
    risk_per_trade = config.get("risk", {}).get("max_risk_per_trade", 0.01)

    if args.symbol:
        instruments = [i for i in instruments if i["symbol"] == args.symbol]

    # Timeframes to test
    if args.timeframe:
        timeframes = [args.timeframe]
    else:
        timeframes = ["M15", "H1", "H4", "D1"]

    master_run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    all_results = []

    # Count total tests
    total_tests = 0
    for inst in instruments:
        sym = inst["symbol"]
        for tf in timeframes:
            if os.path.exists(f"data/raw/{sym}/{tf}.parquet"):
                strats = create_all_strategies(sym, config)
                if args.strategy:
                    strats = [s for s in strats if s.name == args.strategy]
                total_tests += len(strats)

    # ── Telegram: START ──
    symbols_list = ", ".join(i["symbol"] for i in instruments)
    start_msg = (
        f"🧪 <b>بدء الباك تست الشامل</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Run: <code>{master_run_id}</code>\n"
        f"⚙️ المعيار: <b>{profile['name']}</b>\n"
        f"📊 الأزواج: {symbols_list}\n"
        f"⏱ الأطر: {', '.join(timeframes)}\n"
        f"🔢 إجمالي الاختبارات: {total_tests}\n"
        f"📋 PF>{profile['min_profit_factor']} | DD<{profile['max_drawdown_pct']}% | "
        f"WR>{profile['min_win_rate']}% | Sharpe>{profile['min_sharpe']} | "
        f"Trades>{profile['min_trades']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏳ الوقت المتوقع: ~{total_tests * 20}s"
    )
    notifier.send(start_msg)
    log_event(master_run_id, "INFO", f"Backtest started: {total_tests} tests")

    print()
    print("=" * 70)
    print("     ForexAI Universal Backtest")
    print(f"     Run ID: {master_run_id}")
    print(f"     Timeframes: {', '.join(timeframes)}")
    print(f"     Tests: {total_tests}")
    print("=" * 70)
    print()

    global_start = _time.time()
    completed = 0
    passed_count = 0
    failed_count = 0
    skipped_count = 0

    for inst in instruments:
        symbol = inst["symbol"]
        pip_value = inst.get("pip_value", 0.0001)
        spread = 2.0 if symbol == "XAUUSD" else 1.5

        for tf in timeframes:
            df = load_data(symbol, tf)
            if df is None:
                continue

            logger.info(f"Loaded {len(df)} bars for {symbol}/{tf}")

            strategies = create_all_strategies(symbol, config)
            if args.strategy:
                strategies = [s for s in strategies if s.name == args.strategy]

            for strategy in strategies:
                strategy.symbol = symbol
                version = getattr(strategy, 'VERSION', '?')

                # Skip if already tested with same version (unless --force)
                existing = None if args.force else is_already_tested(symbol, tf, strategy.name, version)
                if existing:
                    completed += 1
                    verdict = existing["verdict"]
                    if verdict == "PASS":
                        passed_count += 1
                    else:
                        failed_count += 1
                    icon = "✅" if verdict == "PASS" else "❌"
                    logger.info(
                        f"[{completed}/{total_tests}] ⏭ {symbol}/{tf} {strategy.name} v{version} | "
                        f"ALREADY TESTED | {existing['total_trades']} trades | "
                        f"WR {existing['win_rate']:.0f}% | PF {existing['profit_factor']:.2f} | "
                        f"${existing['total_pnl']:+,.0f} | [{verdict}]"
                    )
                    all_results.append((symbol, tf, strategy.name, version, None, existing, verdict))
                    skipped_count += 1
                    continue

                test_start = _time.time()

                bt = UniversalBacktester(
                    strategy=strategy,
                    initial_balance=100_000.0,
                    risk_per_trade=risk_per_trade,
                    max_open_positions=1,
                    pip_value=pip_value,
                    spread_pips=spread,
                )

                warmup = 250 if tf in ("M15", "H1") else 100
                result = bt.run(df, warmup=warmup)
                report = compute_metrics(result)

                test_run_id = f"{master_run_id}_{symbol}_{tf}_{strategy.name}"
                verdict, score_bd = save_results(test_run_id, result, report, spread, risk_per_trade, profile)
                elapsed = _time.time() - test_start

                completed += 1
                if verdict == "PASS":
                    passed_count += 1
                else:
                    failed_count += 1

                icon = "✅" if verdict == "PASS" else "❌"
                log_msg = (
                    f"[{completed}/{total_tests}] {icon} {symbol}/{tf} {strategy.name} v{strategy.VERSION} | "
                    f"{report.total_trades} trades | WR {report.win_rate:.0f}% | "
                    f"PF {report.profit_factor:.2f} | ${report.total_pnl:+,.0f} | "
                    f"DD {report.max_drawdown_pct:.1f}% | [{score_bd.grade}]{score_bd.total_score:.0f} | "
                    f"{elapsed:.0f}s | {verdict}"
                )
                logger.info(log_msg)
                log_event(master_run_id, "RESULT", log_msg)

                print(format_report(report, result))
                print(format_score(score_bd))
                print()

                all_results.append((symbol, tf, strategy.name, strategy.VERSION, result, report, verdict, score_bd))

    total_elapsed = _time.time() - global_start

    # ── Combined Summary ──
    if all_results:
        print()
        print("=" * 100)
        print("     COMBINED SUMMARY")
        print("=" * 100)
        print(f"  {'Symbol':<10} {'TF':<5} {'Strategy':<20} {'Ver':<5} {'Trades':>6} {'WR%':>6} {'PF':>7} {'P&L':>12} {'DD%':>7} {'Score':>6} {'Grade':>6} {'Result':>8}")
        print("-" * 110)

        total_pnl = 0
        total_trades = 0

        for entry in all_results:
            # Handle both 7-element (cached) and 8-element (fresh) tuples
            if len(entry) == 8:
                symbol, tf, strat_name, version, result, report_or_cache, verdict, score_bd = entry
                score_val = score_bd.total_score if score_bd else 0
                grade_val = score_bd.grade if score_bd else "?"
            else:
                symbol, tf, strat_name, version, result, report_or_cache, verdict = entry
                score_val = 0
                grade_val = "?"

            icon = "+" if verdict == "PASS" else "-"
            if isinstance(report_or_cache, dict):
                r = report_or_cache
                trades = r["total_trades"]
                wr = r["win_rate"]
                pf = r["profit_factor"]
                pnl = r["total_pnl"]
                dd = r["max_drawdown_pct"]
                cached = " (cached)"
            else:
                r = report_or_cache
                trades = r.total_trades
                wr = r.win_rate
                pf = r.profit_factor
                pnl = r.total_pnl
                dd = r.max_drawdown_pct
                cached = ""
            total_pnl += pnl
            total_trades += trades
            print(
                f"  {symbol:<10} {tf:<5} {strat_name:<20} {version:<5} "
                f"{trades:>6} {wr:>5.1f}% "
                f"{pf:>7.3f} ${pnl:>+10,.2f} "
                f"{dd:>6.1f}% {score_val:>5.1f} "
                f"  [{grade_val}] [{icon} {verdict}]{cached}"
            )

        print("-" * 100)
        print(f"  {'TOTAL':<10} {'':<5} {'':<20} {'':<5} {total_trades:>6} {'':>6} {'':>7} ${total_pnl:>+10,.2f}")
        skip_text = f" | SKIPPED (cached): {skipped_count}" if skipped_count else ""
        print(f"\n  PASSED: {passed_count} | FAILED: {failed_count}{skip_text} | Time: {total_elapsed:.0f}s")
        print("=" * 100)

    # ── Generate approved.yaml ──
    approved = generate_approved_yaml(master_run_id, profile_name)
    approved_count = len(approved.get("approved", {}))
    logger.info(f"Generated {APPROVED_PATH} with {approved_count} approved pairs [{profile['name']}]")

    # ── Telegram: RESULTS ──
    result_lines = [
        f"🏁 <b>الباك تست انتهى</b>",
        f"━━━━━━━━━━━━━━━━━━",
        f"🆔 Run: <code>{master_run_id}</code>",
        f"⚙️ المعيار: <b>{profile['name']}</b>",
        f"⏱ المدة: {int(total_elapsed)}s",
        f"✅ نجح: {passed_count} | ❌ فشل: {failed_count} | ⏭ محفوظ: {skipped_count}",
        f"",
    ]

    if all_results:
        result_lines.append("━━ <b>النتائج</b> ━━")
        for entry in all_results:
            if len(entry) == 8:
                symbol, tf, strat_name, version, result, report_or_cache, verdict, score_bd = entry
                grade_str = f" [{score_bd.grade}]{score_bd.total_score:.0f}" if score_bd else ""
            else:
                symbol, tf, strat_name, version, result, report_or_cache, verdict = entry
                grade_str = ""
            icon = "✅" if verdict == "PASS" else "❌"
            if isinstance(report_or_cache, dict):
                r = report_or_cache
                trades, wr, pf, pnl = r["total_trades"], r["win_rate"], r["profit_factor"], r["total_pnl"]
            else:
                trades, wr, pf, pnl = report_or_cache.total_trades, report_or_cache.win_rate, report_or_cache.profit_factor, report_or_cache.total_pnl
            result_lines.append(
                f"  {icon} {symbol}/{tf} {strat_name} v{version}{grade_str}\n"
                f"    {trades} صفقة | WR {wr:.0f}% | "
                f"PF {pf:.2f} | ${pnl:+,.0f}"
            )

    result_lines.append("")
    result_lines.append(f"📁 معتمدة للتداول: <b>{approved_count}</b> استراتيجية-زوج")
    result_lines.append(f"📋 الملف: {APPROVED_PATH}")

    result_msg = "\n".join(result_lines)
    if len(result_msg) > 4000:
        result_msg = result_msg[:4000] + "\n... (مقتطع)"
    notifier.send(result_msg)

    log_event(master_run_id, "INFO", f"Backtest complete: {passed_count} PASS, {failed_count} FAIL, {total_elapsed:.0f}s")

    print()
    print(f"  Results DB: {DB_PATH}")
    print(f"  Approved:   {APPROVED_PATH} ({approved_count} pairs)")
    print()


if __name__ == "__main__":
    main()
