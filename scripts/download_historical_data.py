"""
سكريبت تحميل البيانات التاريخية
الاستخدام:
    python scripts/download_historical_data.py           ← تحديث تدريجي (الافتراضي)
    python scripts/download_historical_data.py --full    ← إعادة تحميل كاملة من 2010
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.progress import (
    Progress, SpinnerColumn, TextColumn,
    BarColumn, TaskProgressColumn, TimeElapsedColumn,
)
from rich import box
from loguru import logger
import time

from execution.broker_adapters.mt5_adapter import MT5Adapter
from ingestion.collectors.historical_downloader import (
    HistoricalDownloader, SYMBOLS, TIMEFRAMES
)

load_dotenv()
console = Console()

# ─── إعداد السجلات ───
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    level="INFO",
    colorize=True,
)
logger.add(
    "data/logs/download.log",
    rotation="10 MB",
    level="DEBUG",
    encoding="utf-8",
)


def main():
    # --full → إعادة تحميل كاملة
    incremental = "--full" not in sys.argv

    mode_label = "تحديث تدريجي" if incremental else "تحميل كامل من 2010"
    console.rule(f"[bold cyan]تحميل البيانات التاريخية من MT5 — {mode_label}[/bold cyan]")
    console.print(f"  الأزواج   : [yellow]{', '.join(SYMBOLS)}[/yellow]")
    console.print(f"  الأطر     : [yellow]{', '.join(TIMEFRAMES)}[/yellow]")
    console.print()

    # ─── الاتصال ───
    adapter = MT5Adapter()
    if not adapter.connect():
        console.print("[bold red]❌ فشل الاتصال بـ MT5[/bold red]")
        return

    start_time = time.time()

    # ─── التحميل ───
    downloader = HistoricalDownloader()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        total   = len(SYMBOLS) * len(TIMEFRAMES)
        task    = progress.add_task("جارٍ التحميل...", total=total)
        results = []

        for symbol in SYMBOLS:
            for tf in TIMEFRAMES:
                progress.update(
                    task,
                    description=f"[cyan]{symbol}[/cyan] [yellow]{tf}[/yellow]",
                    advance=1,
                )
                partial = downloader.run(
                    symbols=[symbol],
                    timeframes=[tf],
                    incremental=incremental,
                )
                results.extend(partial)

    elapsed = time.time() - start_time

    # ─── جدول الملخص ───
    console.print()
    table = Table(
        title="ملخص التحميل",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column("الزوج",      style="cyan",   justify="center")
    table.add_column("الإطار",     style="yellow",  justify="center")
    table.add_column("الشموع",     style="green",   justify="right")
    table.add_column("من",         style="dim",     justify="center")
    table.add_column("إلى",        style="dim",     justify="center")
    table.add_column("مُضاف جديد", style="magenta", justify="right")
    table.add_column("الحالة",     justify="center")

    total_bars     = 0
    total_inserted = 0

    for r in results:
        bars     = r.get("bars", 0)
        inserted = r.get("inserted", 0)
        total_bars     += bars
        total_inserted += inserted

        table.add_row(
            r["symbol"],
            r["timeframe"],
            f"{bars:,}",
            r["from"],
            r["to"],
            f"{inserted:,}",
            r["status"],
        )

    console.print(table)

    # ─── إحصائيات نهائية ───
    console.print()
    console.print(f"  [bold]إجمالي الشموع المحملة :[/bold] [green]{total_bars:,}[/green]")
    console.print(f"  [bold]مُضاف جديد إلى SQLite:[/bold] [magenta]{total_inserted:,}[/magenta]")
    console.print(f"  [bold]الوقت المستغرق       :[/bold] [yellow]{elapsed:.1f} ثانية[/yellow]")
    console.print(f"  [bold]ملفات Parquet        :[/bold] [dim]data/raw/<SYMBOL>/<TF>.parquet[/dim]")
    console.print()
    console.rule("[bold green]✅ اكتمل التحميل[/bold green]")

    adapter.disconnect()


if __name__ == "__main__":
    os.makedirs("data/logs", exist_ok=True)
    main()
