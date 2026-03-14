"""
تشغيل محرك التداول — Run Trading Engine
يقوم بمسح واحد للأسواق وتنفيذ الإشارات
"""
import sys
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table

from engine.trading_engine import TradingEngine
from strategies.sma_crossover import SMACrossoverStrategy

console = Console()


def main():
    console.print("\n[bold cyan]═══ ForexAI Trading Engine ═══[/bold cyan]\n")

    # Initialize engine
    engine = TradingEngine()
    engine.add_strategy(SMACrossoverStrategy())

    # Connect
    console.print("[yellow]Connecting to MT5...[/yellow]")
    if not engine.start():
        console.print("[red]Failed to start engine[/red]")
        return

    try:
        # Run one scan cycle
        console.print("\n[yellow]Scanning for signals...[/yellow]\n")
        executed = engine.run_once()

        # Report
        if executed:
            table = Table(title="Executed Trades")
            table.add_column("Symbol")
            table.add_column("Action")
            table.add_column("Price", justify="right")
            table.add_column("SL", justify="right")
            table.add_column("TP", justify="right")
            table.add_column("Reason")

            for sig in executed:
                table.add_row(
                    sig["symbol"],
                    sig["action"],
                    f"{sig['price']:.5f}",
                    f"{sig['stop_loss']:.5f}",
                    f"{sig['take_profit']:.5f}",
                    sig["reason"],
                )
            console.print(table)
        else:
            console.print("[dim]No signals generated in this scan[/dim]")

        # Show account status
        account = engine.adapter.get_account_info()
        console.print(f"\n[bold]Account Status:[/bold]")
        console.print(f"  Balance:     ${account['balance']:,.2f}")
        console.print(f"  Equity:      ${account['equity']:,.2f}")
        console.print(f"  Open P&L:    ${account['profit']:,.2f}")

        positions = engine.adapter.get_open_positions()
        console.print(f"  Positions:   {len(positions)}")

    finally:
        engine.stop()
        console.print("\n[green]Engine stopped.[/green]")


if __name__ == "__main__":
    main()
