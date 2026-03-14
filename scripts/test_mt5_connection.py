"""
اختبار الاتصال بـ MT5
شغّل هذا الملف للتحقق أن كل شيء يعمل
python scripts/test_mt5_connection.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from loguru import logger
from rich.console import Console
from rich.table import Table
from rich import box
from execution.broker_adapters.mt5_adapter import MT5Adapter
from storage.database import init_db

load_dotenv()
console = Console()


def main():
    console.rule("[bold cyan]اختبار الاتصال بـ MT5[/bold cyan]")

    # 1. تهيئة قاعدة البيانات
    init_db()

    # 2. الاتصال بـ MT5
    adapter = MT5Adapter()
    if not adapter.connect():
        console.print("[bold red]❌ فشل الاتصال بـ MT5[/bold red]")
        console.print("[yellow]تأكد أن:[/yellow]")
        console.print("  • تطبيق MT5 مفتوح على جهازك")
        console.print("  • أنت مسجّل الدخول في MT5")
        return

    # 3. معلومات الحساب
    info = adapter.get_account_info()
    table = Table(title="معلومات الحساب", box=box.ROUNDED, style="cyan")
    table.add_column("الحقل", style="bold")
    table.add_column("القيمة", style="green")

    table.add_row("رقم الحساب",  str(info.get("login")))
    table.add_row("الوسيط",      info.get("company", "—"))
    table.add_row("السيرفر",      info.get("server", "—"))
    table.add_row("الرصيد",      f"{info.get('balance', 0):,.2f} {info.get('currency')}")
    table.add_row("الإكويتي",    f"{info.get('equity', 0):,.2f} {info.get('currency')}")
    table.add_row("الهامش الحر", f"{info.get('free_margin', 0):,.2f} {info.get('currency')}")
    table.add_row("الرافعة",     f"1:{info.get('leverage', 0)}")
    console.print(table)

    # 4. جلب بيانات EURUSD
    console.print("\n[bold]جلب بيانات EURUSD H1...[/bold]")
    df = adapter.get_ohlcv("EURUSD", timeframe="H1", bars=10)

    if not df.empty:
        console.print(f"[green]✅ تم جلب {len(df)} شمعة[/green]")
        bar_table = Table(title="آخر 5 شموع EURUSD H1", box=box.SIMPLE)
        for col in ["time", "open", "high", "low", "close", "volume"]:
            bar_table.add_column(col)
        for _, row in df.tail(5).iterrows():
            bar_table.add_row(
                str(row["time"]),
                f"{row['open']:.5f}",
                f"{row['high']:.5f}",
                f"{row['low']:.5f}",
                f"{row['close']:.5f}",
                str(int(row["volume"])),
            )
        console.print(bar_table)
    else:
        console.print("[red]❌ فشل جلب البيانات[/red]")

    # 5. السعر الفوري
    tick = adapter.get_tick("EURUSD")
    if tick:
        console.print(
            f"\n[bold]السعر الفوري EURUSD:[/bold] "
            f"Bid=[green]{tick['bid']:.5f}[/green]  "
            f"Ask=[red]{tick['ask']:.5f}[/red]  "
            f"Spread=[yellow]{tick['spread']}[/yellow] pips"
        )

    # 6. الصفقات المفتوحة
    positions = adapter.get_open_positions()
    if positions.empty:
        console.print("\n[dim]لا توجد صفقات مفتوحة حالياً[/dim]")
    else:
        console.print(f"\n[bold]الصفقات المفتوحة:[/bold] {len(positions)}")
        console.print(positions.to_string())

    adapter.disconnect()
    console.rule("[bold green]✅ الاختبار اكتمل بنجاح[/bold green]")


if __name__ == "__main__":
    main()
