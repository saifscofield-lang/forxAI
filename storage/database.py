"""
إدارة قاعدة البيانات SQLite
جداول شاملة للتداول، التقارير، الأخبار، وتدريب ML
"""
from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer, Boolean, UniqueConstraint, Index, Text
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from contextlib import contextmanager
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/trading.db")

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    execution_options={"compiled_cache": {}},
)
SessionLocal = sessionmaker(bind=engine)


@contextmanager
def get_db_session():
    """Context manager for safe database sessions with auto commit/rollback."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class Base(DeclarativeBase):
    pass


class OHLCVBar(Base):
    """جدول تخزين بيانات الشموع"""
    __tablename__ = "ohlcv_bars"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    symbol    = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    time      = Column(DateTime, nullable=False)
    open      = Column(Float, nullable=False)
    high      = Column(Float, nullable=False)
    low       = Column(Float, nullable=False)
    close     = Column(Float, nullable=False)
    volume    = Column(Float, nullable=False)
    spread    = Column(Float, default=0.0)

    __table_args__ = (
        # منع التكرار + سرعة الاستعلام
        UniqueConstraint("symbol", "timeframe", "time", name="uq_bar"),
        Index("ix_symbol_tf_time", "symbol", "timeframe", "time"),
    )


class Trade(Base):
    """جدول تسجيل الصفقات"""
    __tablename__ = "trades"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    ticket        = Column(Integer, unique=True, index=True)
    symbol        = Column(String(20), nullable=False)
    order_type    = Column(String(10))         # BUY | SELL
    volume        = Column(Float)
    open_price    = Column(Float)
    close_price   = Column(Float, nullable=True)
    open_time     = Column(DateTime)
    close_time    = Column(DateTime, nullable=True)
    profit        = Column(Float, default=0.0)
    swap          = Column(Float, default=0.0)
    commission    = Column(Float, default=0.0)
    stop_loss     = Column(Float, nullable=True)
    take_profit   = Column(Float, nullable=True)
    strategy      = Column(String(50), nullable=True)
    is_closed     = Column(Boolean, default=False)
    comment       = Column(String(100), nullable=True)
    engine_version = Column(String(10), nullable=True)   # e.g. "2.0" — for filtering ML training data
    strategy_version = Column(String(10), nullable=True)  # e.g. "2.0" — strategy version at trade time


class SignalLog(Base):
    """Log every signal: taken, filtered by ML, rejected by risk manager."""
    __tablename__ = "signal_logs"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    time            = Column(DateTime, default=datetime.utcnow)
    symbol          = Column(String(20), nullable=False)
    action          = Column(String(10))              # BUY | SELL
    price           = Column(Float)
    stop_loss       = Column(Float, nullable=True)
    take_profit     = Column(Float, nullable=True)
    atr             = Column(Float, nullable=True)
    rsi             = Column(Float, nullable=True)
    strategy        = Column(String(50))
    status          = Column(String(20))              # EXECUTED | ML_FILTERED | RISK_REJECTED | ERROR
    reason          = Column(String(200), nullable=True)
    ml_confidence   = Column(Float, nullable=True)    # ML probability (0-1)
    ml_threshold    = Column(Float, nullable=True)    # Required threshold
    ticket          = Column(Integer, nullable=True)  # MT5 ticket if executed
    features_json   = Column(String, nullable=True)   # Feature snapshot (JSON)
    strategy_version = Column(String(10), nullable=True)  # Strategy version at signal time

    __table_args__ = (
        Index("ix_signal_symbol_time", "symbol", "time"),
    )


class TradeResult(Base):
    """Final result of each closed trade — for ML retraining."""
    __tablename__ = "trade_results"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    ticket          = Column(Integer, unique=True, index=True)
    symbol          = Column(String(20), nullable=False)
    action          = Column(String(10))
    open_price      = Column(Float)
    close_price     = Column(Float)
    open_time       = Column(DateTime)
    close_time      = Column(DateTime)
    pnl             = Column(Float)                   # Profit/Loss in $
    pnl_pips        = Column(Float)                   # Profit/Loss in pips
    exit_reason     = Column(String(20))              # SL_HIT | TP_HIT | MANUAL | TIMEOUT
    profitable      = Column(Boolean)                 # True if pnl > 0
    ml_confidence   = Column(Float, nullable=True)    # ML confidence at entry
    strategy        = Column(String(50))
    features_json   = Column(String, nullable=True)   # Features at entry time

    # ── Enhanced fields for comprehensive reporting ──
    volume          = Column(Float, nullable=True)              # Lot size
    swap            = Column(Float, default=0.0)                # Swap fees
    commission      = Column(Float, default=0.0)                # Commission fees
    slippage_pips   = Column(Float, nullable=True)              # Entry slippage (requested vs filled)
    trade_duration_minutes = Column(Integer, nullable=True)     # How long trade was open
    max_favorable_pips  = Column(Float, nullable=True)          # Max favorable excursion (MFE)
    max_adverse_pips    = Column(Float, nullable=True)          # Max adverse excursion (MAE)
    risk_reward_planned = Column(Float, nullable=True)          # Planned R:R ratio
    risk_reward_actual  = Column(Float, nullable=True)          # Actual R:R ratio

    # ── Market context at entry ──
    h1_trend        = Column(String(10), nullable=True)         # UP / DOWN / RANGE
    h4_trend        = Column(String(10), nullable=True)         # UP / DOWN / RANGE
    volatility_regime = Column(String(10), nullable=True)       # LOW / NORMAL / HIGH
    spread_at_entry = Column(Float, nullable=True)              # Spread in pips at entry
    atr_at_entry    = Column(Float, nullable=True)              # ATR value at entry
    rsi_at_entry    = Column(Float, nullable=True)              # RSI value at entry

    # ── News context ──
    news_nearby     = Column(Boolean, default=False)            # High-impact news within ±1 hour
    news_event_name = Column(String(200), nullable=True)        # Nearest news event name
    news_impact     = Column(String(10), nullable=True)         # LOW / MEDIUM / HIGH
    engine_version  = Column(String(10), nullable=True)         # e.g. "2.0" — for filtering ML training data
    strategy_version = Column(String(10), nullable=True)        # Strategy version at trade time


class AccountSnapshot(Base):
    """Periodic account snapshots."""
    __tablename__ = "account_snapshots"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    time       = Column(DateTime, default=datetime.utcnow)
    balance    = Column(Float)
    equity     = Column(Float)
    margin     = Column(Float)
    free_margin = Column(Float)
    profit     = Column(Float)


class MarketContext(Base):
    """لقطة حالة السوق عند كل فحص — لتدريب ML على ظروف السوق."""
    __tablename__ = "market_contexts"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    time            = Column(DateTime, default=datetime.utcnow)
    symbol          = Column(String(20), nullable=False)

    # ── H1 data (primary) ──
    h1_close        = Column(Float)
    h1_atr          = Column(Float, nullable=True)
    h1_rsi          = Column(Float, nullable=True)
    h1_sma_fast     = Column(Float, nullable=True)
    h1_sma_slow     = Column(Float, nullable=True)
    h1_macd         = Column(Float, nullable=True)
    h1_macd_signal  = Column(Float, nullable=True)
    h1_bb_position  = Column(Float, nullable=True)      # 0-1 scale

    # ── H4 data (trend confirmation) ──
    h4_close        = Column(Float, nullable=True)
    h4_atr          = Column(Float, nullable=True)
    h4_rsi          = Column(Float, nullable=True)
    h4_sma_50       = Column(Float, nullable=True)
    h4_sma_200      = Column(Float, nullable=True)
    h4_trend        = Column(String(10), nullable=True)  # UP / DOWN / RANGE

    # ── M15 data (entry confirmation) ──
    m15_close       = Column(Float, nullable=True)
    m15_rsi         = Column(Float, nullable=True)
    m15_atr         = Column(Float, nullable=True)

    # ── Volatility regime ──
    volatility_regime = Column(String(10), nullable=True)  # LOW / NORMAL / HIGH
    spread          = Column(Float, nullable=True)          # Current spread in pips

    # ── Signal info (if any) ──
    signal_action   = Column(String(10), nullable=True)     # BUY / SELL / None
    signal_status   = Column(String(20), nullable=True)     # ACTIVE / ML_FILTERED / NEWS_FILTERED / None

    __table_args__ = (
        Index("ix_market_ctx_symbol_time", "symbol", "time"),
    )


class NewsEvent(Base):
    """أحداث اقتصادية من تقويم MT5 — لتدريب ML على تأثير الأخبار."""
    __tablename__ = "news_events"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    event_id        = Column(Integer, nullable=True)         # MT5 calendar event ID
    time            = Column(DateTime, nullable=False)       # Event time (UTC)
    country         = Column(String(10), nullable=True)      # Country code (US, GB, JP, EU)
    currency        = Column(String(10), nullable=True)      # Affected currency (USD, GBP, JPY, EUR)
    event_name      = Column(String(200), nullable=False)    # Event name
    impact          = Column(String(10), nullable=False)     # LOW / MEDIUM / HIGH
    actual          = Column(Float, nullable=True)           # Actual value
    forecast        = Column(Float, nullable=True)           # Forecast value
    previous        = Column(Float, nullable=True)           # Previous value
    surprise        = Column(Float, nullable=True)           # actual - forecast
    fetched_at      = Column(DateTime, default=datetime.utcnow)  # When we fetched it

    __table_args__ = (
        Index("ix_news_currency_time", "currency", "time"),
        Index("ix_news_impact_time", "impact", "time"),
    )


class ScanLog(Base):
    """سجل كل دورة فحص — لتتبع أداء النظام."""
    __tablename__ = "scan_logs"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    time            = Column(DateTime, default=datetime.utcnow)
    scan_number     = Column(Integer)
    duration_ms     = Column(Integer, nullable=True)         # Scan duration in ms
    symbols_scanned = Column(Integer)                        # How many symbols checked
    signals_total   = Column(Integer, default=0)             # Total signals generated
    signals_active  = Column(Integer, default=0)             # Signals that passed all filters
    signals_ml_filtered = Column(Integer, default=0)         # Blocked by ML
    signals_news_filtered = Column(Integer, default=0)       # Blocked by news
    signals_risk_rejected = Column(Integer, default=0)       # Blocked by risk
    signals_executed = Column(Integer, default=0)            # Successfully executed
    open_positions  = Column(Integer, default=0)             # Current open positions
    balance         = Column(Float, nullable=True)
    equity          = Column(Float, nullable=True)
    news_blocked    = Column(Boolean, default=False)         # Was trading blocked by news?
    news_event_name = Column(String(200), nullable=True)     # Which news event blocked
    details_json    = Column(Text, nullable=True)            # JSON: per-symbol scan details


class SymbolScanDetail(Base):
    """تفاصيل المسح لكل زوج — لتشخيص سبب عدم توليد إشارة."""
    __tablename__ = "symbol_scan_details"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    time            = Column(DateTime, default=datetime.utcnow)
    scan_number     = Column(Integer)
    symbol          = Column(String(20), nullable=False)

    # ── SMA state ──
    sma_fast        = Column(Float, nullable=True)
    sma_slow        = Column(Float, nullable=True)
    sma_gap_pct     = Column(Float, nullable=True)           # (fast-slow)/slow * 100
    sma_prev_fast   = Column(Float, nullable=True)
    sma_prev_slow   = Column(Float, nullable=True)
    crossover       = Column(String(20), nullable=True)      # BULLISH / BEARISH / NONE
    cross_distance  = Column(Float, nullable=True)           # How far from crossing (pips)

    # ── Indicators ──
    price           = Column(Float, nullable=True)
    rsi             = Column(Float, nullable=True)
    atr             = Column(Float, nullable=True)
    macd            = Column(Float, nullable=True)
    macd_signal     = Column(Float, nullable=True)
    bb_position     = Column(Float, nullable=True)

    # ── Trends ──
    h1_trend        = Column(String(10), nullable=True)
    h4_trend        = Column(String(10), nullable=True)
    volatility      = Column(String(10), nullable=True)

    # ── Signal outcome ──
    signal_generated = Column(Boolean, default=False)
    signal_action   = Column(String(10), nullable=True)
    signal_status   = Column(String(20), nullable=True)
    rejection_reason = Column(String(300), nullable=True)    # Why no signal

    # ── News context ──
    news_blocked    = Column(Boolean, default=False)
    news_event      = Column(String(200), nullable=True)
    upcoming_news   = Column(Text, nullable=True)            # JSON list of upcoming events

    __table_args__ = (
        Index("ix_scan_detail_symbol_time", "symbol", "time"),
    )


class IndicatorSnapshot(Base):
    """لقطة كاملة للمؤشرات عند كل فحص — لتدريب ML حتى بدون إشارات."""
    __tablename__ = "indicator_snapshots"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    time            = Column(DateTime, default=datetime.utcnow)
    scan_number     = Column(Integer)
    symbol          = Column(String(20), nullable=False)
    timeframe       = Column(String(10), default="M15")
    features_json   = Column(Text, nullable=True)    # Full build_features output as JSON
    price           = Column(Float, nullable=True)
    rsi_14          = Column(Float, nullable=True)
    atr_14          = Column(Float, nullable=True)
    macd            = Column(Float, nullable=True)
    macd_signal     = Column(Float, nullable=True)
    bb_position     = Column(Float, nullable=True)
    sma_20          = Column(Float, nullable=True)
    sma_50          = Column(Float, nullable=True)
    ema_12          = Column(Float, nullable=True)
    ema_26          = Column(Float, nullable=True)
    volatility_10   = Column(Float, nullable=True)
    return_1        = Column(Float, nullable=True)
    return_5        = Column(Float, nullable=True)
    volume_ratio    = Column(Float, nullable=True)
    h1_trend        = Column(String(10), nullable=True)
    h4_trend        = Column(String(10), nullable=True)
    signal_fired    = Column(Boolean, default=False)
    signal_action   = Column(String(10), nullable=True)
    signal_strategy = Column(String(50), nullable=True)

    __table_args__ = (
        Index("ix_snap_symbol_time", "symbol", "time"),
    )


class StrategyImprovement(Base):
    """سجل التحسينات المطبقة على الاستراتيجيات — لتتبع أي نسخة أنتجت كل صفقة."""
    __tablename__ = "strategy_improvements"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    improvement_code  = Column(String(20), unique=True, nullable=False)   # e.g. IMP-62
    strategy_name     = Column(String(50), nullable=False)
    version_before    = Column(String(10), nullable=False)
    version_after     = Column(String(10), nullable=False)
    description       = Column(String(500), nullable=False)
    changes_summary   = Column(Text, nullable=True)
    expected_impact   = Column(String(200), nullable=True)
    applied           = Column(Boolean, default=False)                    # هل تم التنفيذ؟
    applied_at        = Column(DateTime, nullable=True)                   # تاريخ التنفيذ
    created_at        = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_imp_strategy", "strategy_name"),
    )


class MonitorState(Base):
    """حالة المونيتور لكل صفقة مفتوحة — تُحفظ لمنع فقدان الحالة عند إعادة التشغيل."""
    __tablename__ = "monitor_states"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    ticket          = Column(Integer, unique=True, nullable=False, index=True)
    symbol          = Column(String(20), nullable=False)
    phase           = Column(Integer, default=0)              # 0-4
    tp1_closed      = Column(Boolean, default=False)          # Was 50% partial close done?
    original_volume = Column(Float, nullable=True)            # Volume at entry
    original_tp     = Column(Float, nullable=True)            # TP at entry
    entry_atr       = Column(Float, nullable=True)            # ATR at entry time
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def init_db():
    """إنشاء جداول قاعدة البيانات"""
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(engine)

    # Add missing columns to existing tables (migration)
    import sqlite3
    db_path = DATABASE_URL.replace("sqlite:///", "")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        # Check and add details_json to scan_logs if missing
        c.execute("PRAGMA table_info(scan_logs)")
        cols = [r[1] for r in c.fetchall()]
        if "details_json" not in cols:
            c.execute("ALTER TABLE scan_logs ADD COLUMN details_json TEXT")
            conn.commit()

        # Add engine_version to trades and trade_results if missing
        for table in ("trades", "trade_results"):
            c.execute(f"PRAGMA table_info({table})")
            cols = [r[1] for r in c.fetchall()]
            if cols and "engine_version" not in cols:
                c.execute(f"ALTER TABLE {table} ADD COLUMN engine_version TEXT")
                conn.commit()

        # Add strategy_version to trades, trade_results, signal_logs if missing
        for table in ("trades", "trade_results", "signal_logs"):
            c.execute(f"PRAGMA table_info({table})")
            cols = [r[1] for r in c.fetchall()]
            if cols and "strategy_version" not in cols:
                c.execute(f"ALTER TABLE {table} ADD COLUMN strategy_version TEXT")
                conn.commit()

        conn.close()

    print("Database ready")


def get_session():
    """الحصول على جلسة قاعدة البيانات"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
