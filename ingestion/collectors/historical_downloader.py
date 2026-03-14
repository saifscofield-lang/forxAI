"""
محمّل البيانات التاريخية من MT5
نسخة محسّنة — Pagination + Bulk Insert
يجلب كامل البيانات المتاحة بدون حد 99,999 شمعة
"""
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger
from sqlalchemy import text

from storage.database import engine, init_db
from execution.broker_adapters.mt5_adapter import TIMEFRAME_MAP


# ─────────────────────────────────────────────────────
# الإعدادات
# ─────────────────────────────────────────────────────

SYMBOLS = [
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "XAUUSD",
    "USDCHF",
    "AUDUSD",
    "USDCAD",
]

TIMEFRAMES = ["M5", "M15", "H1", "H4", "D1", "W1"]

# تاريخ البداية الافتراضي (أقصى ما يوفره MetaQuotes-Demo)
DEFAULT_START = datetime(2010, 1, 1, tzinfo=timezone.utc)

# حجم كل دفعة (أقل من حد MT5 الأقصى 99,999)
BATCH_SIZE = 50_000

RAW_DIR = Path("data/raw")


# ─────────────────────────────────────────────────────
# دوال مساعدة
# ─────────────────────────────────────────────────────

def _normalize(df: pd.DataFrame, symbol: str, timeframe: str) -> pd.DataFrame:
    """تطبيع أعمدة DataFrame من MT5"""
    df = df.copy()
    df["time"]      = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_localize(None)
    df["symbol"]    = symbol
    df["timeframe"] = timeframe
    df = df.rename(columns={"tick_volume": "volume"})
    df["volume"] = df["volume"].astype("int64")
    df["spread"] = df["spread"].astype("float64")
    return df[["symbol", "timeframe", "time", "open", "high", "low", "close", "volume", "spread"]]


def fetch_bars_full(symbol: str, timeframe: str,
                    start: datetime = None) -> pd.DataFrame:
    """
    جلب كامل البيانات المتاحة من MT5 بالـ Pagination.
    يحل مشكلة الحد 99,999 شمعة لكل استعلام.

    الخوارزمية:
      1. ابدأ من آخر وقت مخزَّن (أو DEFAULT_START إذا لم تكن هناك بيانات)
      2. اجلب BATCH_SIZE شمعة بعد ذلك الوقت
      3. كرّر حتى لا تأتي شموع جديدة
    """
    tf = TIMEFRAME_MAP.get(timeframe)
    if tf is None:
        return pd.DataFrame()

    if start is None:
        start = DEFAULT_START

    # تأكد أن start بدون timezone (MT5 يعمل بـ UTC naive)
    if start.tzinfo is not None:
        start = start.replace(tzinfo=None)

    end = datetime.utcnow()
    all_frames = []
    current_from = start

    while True:
        rates = mt5.copy_rates_range(symbol, tf, current_from, end)

        if rates is None or len(rates) == 0:
            break

        df = pd.DataFrame(rates)
        df = _normalize(df, symbol, timeframe)

        all_frames.append(df)

        last_time = df["time"].max()
        fetched   = len(df)

        logger.debug(
            f"  {symbol} {timeframe}: +{fetched:,} شمعة "
            f"حتى {last_time.strftime('%Y-%m-%d')}"
        )

        # إذا جاء أقل من BATCH_SIZE → وصلنا للنهاية
        if fetched < BATCH_SIZE:
            break

        # انتقل لما بعد آخر شمعة
        current_from = last_time.to_pydatetime()

        # حماية: إذا لم يتقدم الوقت نوقف
        if len(all_frames) >= 2:
            prev_last = all_frames[-2]["time"].max()
            if last_time <= prev_last:
                break

    if not all_frames:
        return pd.DataFrame()

    combined = pd.concat(all_frames, ignore_index=True)
    combined = (
        combined
        .drop_duplicates(subset=["symbol", "timeframe", "time"])
        .sort_values("time")
        .reset_index(drop=True)
    )
    return combined


def get_last_stored_time(symbol: str, timeframe: str):
    """آخر وقت مخزَّن في SQLite لهذا الزوج والإطار"""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT MAX(time) FROM ohlcv_bars WHERE symbol=:s AND timeframe=:t"),
            {"s": symbol, "t": timeframe},
        )
        return result.scalar()


def bulk_insert(df: pd.DataFrame) -> int:
    """
    إدخال جماعي سريع باستخدام pandas to_sql
    يتجاهل الصفوف المكررة تلقائياً
    """
    if df.empty:
        return 0

    tmp_table = "ohlcv_bars_tmp"

    with engine.begin() as conn:
        # chunksize=100 → 100×9 أعمدة = 900 < حد SQLite (999)
        df.to_sql(
            tmp_table,
            conn,
            if_exists="replace",
            index=False,
            method="multi",
            chunksize=100,
        )

        result = conn.execute(text("""
            INSERT OR IGNORE INTO ohlcv_bars
                (symbol, timeframe, time, open, high, low, close, volume, spread)
            SELECT
                symbol, timeframe, time, open, high, low, close, volume, spread
            FROM ohlcv_bars_tmp
        """))
        inserted = result.rowcount

        conn.execute(text(f"DROP TABLE IF EXISTS {tmp_table}"))

    return inserted


def save_to_parquet(df: pd.DataFrame, symbol: str, timeframe: str) -> Path:
    """حفظ أو تحديث ملف Parquet"""
    folder = RAW_DIR / symbol
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{timeframe}.parquet"

    if path.exists():
        existing = pd.read_parquet(path)
        df = pd.concat([existing, df]).drop_duplicates(
            subset=["symbol", "timeframe", "time"]
        ).sort_values("time").reset_index(drop=True)

    df.to_parquet(path, index=False)
    return path


# ─────────────────────────────────────────────────────
# المحمّل الرئيسي
# ─────────────────────────────────────────────────────

class HistoricalDownloader:

    def run(self, symbols: list = None, timeframes: list = None,
            incremental: bool = True) -> list:
        """
        تحميل البيانات التاريخية.

        incremental=True  → يبدأ من آخر وقت مخزَّن (تحديث تدريجي)
        incremental=False → يبدأ من DEFAULT_START (إعادة تحميل كاملة)
        """
        symbols    = symbols    or SYMBOLS
        timeframes = timeframes or TIMEFRAMES

        init_db()
        RAW_DIR.mkdir(parents=True, exist_ok=True)

        total   = len(symbols) * len(timeframes)
        done    = 0
        summary = []

        for symbol in symbols:
            info = mt5.symbol_info(symbol)
            if info is None:
                logger.warning(f"⚠️  {symbol} غير متاح — تم التخطي")
                continue
            if not info.visible:
                mt5.symbol_select(symbol, True)

            for tf in timeframes:
                done += 1
                label = f"[{done}/{total}] {symbol} {tf}"

                # تحديد نقطة البداية
                start = DEFAULT_START
                if incremental:
                    last = get_last_stored_time(symbol, tf)
                    if last is not None:
                        start = pd.to_datetime(last).to_pydatetime()
                        logger.debug(f"{label} ← استئناف من {start.date()}")

                # جلب البيانات (pagination كاملة)
                df = fetch_bars_full(symbol, tf, start=start)

                if df.empty:
                    logger.warning(f"{label} ← لا بيانات جديدة")
                    summary.append({
                        "symbol": symbol, "timeframe": tf,
                        "bars": 0, "from": "—", "to": "—",
                        "inserted": 0, "status": "⚠️",
                    })
                    continue

                bars      = len(df)
                date_from = df["time"].min().strftime("%Y-%m-%d")
                date_to   = df["time"].max().strftime("%Y-%m-%d")

                inserted = bulk_insert(df)
                save_to_parquet(df, symbol, tf)

                logger.success(
                    f"{label} ← {bars:,} شمعة | "
                    f"{date_from} → {date_to} | "
                    f"جديد: +{inserted:,}"
                )

                summary.append({
                    "symbol":    symbol,
                    "timeframe": tf,
                    "bars":      bars,
                    "from":      date_from,
                    "to":        date_to,
                    "inserted":  inserted,
                    "status":    "✅",
                })

        return summary
