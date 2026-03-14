"""
التحقق من صحة البيانات المحمَّلة
python scripts/verify_data.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from pathlib import Path
from sqlalchemy import text
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from storage.database import engine
from ingestion.collectors.historical_downloader import SYMBOLS, TIMEFRAMES

console = Console()
RAW_DIR = Path("data/raw")


def check_sqlite() -> pd.DataFrame:
    """إحصائيات SQLite"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                symbol,
                timeframe,
                COUNT(*)            AS bars,
                MIN(time)           AS date_from,
                MAX(time)           AS date_to,
                ROUND(AVG(close),5) AS avg_close
            FROM ohlcv_bars
            GROUP BY symbol, timeframe
            ORDER BY symbol, timeframe
        """))
        rows = result.fetchall()

    return pd.DataFrame(rows, columns=[
        "symbol","timeframe","bars","date_from","date_to","avg_close"
    ])


def check_parquet() -> dict:
    """فحص ملفات Parquet"""
    info = {}
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            path = RAW_DIR / symbol / f"{tf}.parquet"
            if path.exists():
                size_kb = path.stat().st_size / 1024
                df      = pd.read_parquet(path)
                info[f"{symbol}_{tf}"] = {
                    "exists":   True,
                    "size_kb":  round(size_kb, 1),
                    "rows":     len(df),
                }
            else:
                info[f"{symbol}_{tf}"] = {"exists": False}
    return info


def check_gaps(symbol: str, timeframe: str) -> int:
    """عدد الفجوات غير الطبيعية في البيانات"""
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT time FROM ohlcv_bars
                WHERE symbol=:s AND timeframe=:t
                ORDER BY time
            """),
            {"s": symbol, "t": timeframe},
        )
        times = [r[0] for r in result.fetchall()]

    if len(times) < 2:
        return 0

    times = pd.to_datetime(times)
    diffs = times.diff().dropna()

    # الفارق الطبيعي (وسيط الفوارق)
    normal_gap = diffs.median()

    # فجوات أكبر من 3x الفارق الطبيعي (مع استثناء عطل نهاية الأسبوع)
    big_gaps = diffs[diffs > normal_gap * 3]

    # استثناء فجوات نهاية الأسبوع (جمعة → إثنين ≈ 60 ساعة)
    weekend_threshold = pd.Timedelta(hours=60)
    real_gaps = big_gaps[big_gaps > weekend_threshold]

    return len(real_gaps)


def main():
    console.print()
    console.rule("[bold cyan]التحقق من البيانات المحمَّلة[/bold cyan]")

    # ─── 1. SQLite ───
    console.print("\n[bold yellow]1. إحصائيات SQLite[/bold yellow]")
    df = check_sqlite()

    if df.empty:
        console.print("[red]❌ لا توجد بيانات في قاعدة البيانات![/red]")
        console.print("[dim]شغّل: python scripts/download_historical_data.py[/dim]")
        return

    # ترتيب الأطر الزمنية
    tf_order = {"M5":0,"M15":1,"H1":2,"H4":3,"D1":4,"W1":5}
    df["tf_sort"] = df["timeframe"].map(tf_order)
    df = df.sort_values(["symbol","tf_sort"]).drop("tf_sort", axis=1)

    table = Table(box=box.ROUNDED, show_lines=True)
    table.add_column("الزوج",     style="cyan",   justify="center")
    table.add_column("الإطار",    style="yellow",  justify="center")
    table.add_column("الشموع",    style="green",   justify="right")
    table.add_column("من",        style="dim",     justify="center")
    table.add_column("إلى",       style="dim",     justify="center")
    table.add_column("السنوات",   style="magenta", justify="center")
    table.add_column("الحالة",    justify="center")

    total_bars = 0
    for _, row in df.iterrows():
        bars       = int(row["bars"])
        total_bars += bars
        d_from     = pd.to_datetime(row["date_from"])
        d_to       = pd.to_datetime(row["date_to"])
        years      = round((d_to - d_from).days / 365, 1)

        # تقييم الكمية
        if bars > 5000:
            status = "✅ ممتاز"
        elif bars > 500:
            status = "⚠️ قليل"
        else:
            status = "❌ ضعيف"

        table.add_row(
            row["symbol"],
            row["timeframe"],
            f"{bars:,}",
            d_from.strftime("%Y-%m-%d"),
            d_to.strftime("%Y-%m-%d"),
            f"{years}y",
            status,
        )

    console.print(table)
    console.print(f"\n  [bold]إجمالي الشموع في SQLite:[/bold] [green]{total_bars:,}[/green]")

    # ─── 2. Parquet ───
    console.print("\n[bold yellow]2. ملفات Parquet[/bold yellow]")
    parquet_info = check_parquet()

    p_table = Table(box=box.SIMPLE)
    p_table.add_column("الملف",    style="cyan")
    p_table.add_column("الحجم",    style="yellow", justify="right")
    p_table.add_column("الصفوف",   style="green",  justify="right")
    p_table.add_column("الحالة",   justify="center")

    total_size = 0
    for key, info in parquet_info.items():
        if info["exists"]:
            total_size += info["size_kb"]
            p_table.add_row(
                key.replace("_", " "),
                f"{info['size_kb']:,.0f} KB",
                f"{info['rows']:,}",
                "✅",
            )
        else:
            p_table.add_row(key.replace("_", " "), "—", "—", "❌ مفقود")

    console.print(p_table)
    console.print(f"  [bold]إجمالي حجم Parquet:[/bold] [yellow]{total_size/1024:.1f} MB[/yellow]")

    # ─── 3. فحص الفجوات ───
    console.print("\n[bold yellow]3. فحص الفجوات في البيانات[/bold yellow]")

    gap_table = Table(box=box.SIMPLE)
    gap_table.add_column("الزوج",  style="cyan",   justify="center")
    gap_table.add_column("الإطار", style="yellow",  justify="center")
    gap_table.add_column("فجوات",  style="red",    justify="center")
    gap_table.add_column("الحالة", justify="center")

    for _, row in df.iterrows():
        gaps = check_gaps(row["symbol"], row["timeframe"])
        status = "✅ نظيف" if gaps == 0 else f"⚠️ {gaps} فجوة"
        gap_table.add_row(row["symbol"], row["timeframe"], str(gaps), status)

    console.print(gap_table)

    # ─── ملخص نهائي ───
    console.print()
    missing = sum(1 for v in parquet_info.values() if not v["exists"])
    console.print(Panel(
        f"  الشموع الكلية  : [green]{total_bars:,}[/green]\n"
        f"  حجم Parquet    : [yellow]{total_size/1024:.1f} MB[/yellow]\n"
        f"  ملفات مفقودة  : [{'red' if missing else 'green'}]{missing}[/{'red' if missing else 'green'}]\n"
        f"  قاعدة البيانات : [cyan]data/trading.db[/cyan]",
        title="[bold]الملخص النهائي[/bold]",
        border_style="green" if missing == 0 else "yellow",
    ))


if __name__ == "__main__":
    main()
