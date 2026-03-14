"""
اختبار المؤشرات الفنية — Test Technical Indicators
يقرأ بيانات من قاعدة البيانات ويحسب المؤشرات
"""
import sys
import os
sys.path.insert(0, ".")
os.environ["PYTHONIOENCODING"] = "utf-8"

import pandas as pd
from rich.console import Console
from rich.table import Table
from sqlalchemy import text

from storage.database import SessionLocal
from features.technical.indicators import add_all_indicators

console = Console()


def test_indicators():
    console.print("\n[bold cyan]═══ اختبار المؤشرات الفنية ═══[/bold cyan]\n")

    session = SessionLocal()
    try:
        # Load EURUSD H1 data
        query = text(
            "SELECT time, open, high, low, close, volume "
            "FROM ohlcv_bars "
            "WHERE symbol = 'EURUSD' AND timeframe = 'H1' "
            "ORDER BY time DESC LIMIT 200"
        )
        df = pd.read_sql(query, session.bind)

        if df.empty:
            console.print("[red]No data found for EURUSD H1[/red]")
            return

        df = df.sort_values("time").reset_index(drop=True)
        console.print(f"[green]Loaded {len(df)} bars of EURUSD H1[/green]\n")

        # Apply all indicators
        df = add_all_indicators(df)

        # Show last 10 rows with key indicators
        last = df.tail(10)

        table = Table(title="EURUSD H1 — Last 10 Bars with Indicators")
        table.add_column("Time", style="dim")
        table.add_column("Close", justify="right")
        table.add_column("SMA20", justify="right")
        table.add_column("SMA50", justify="right")
        table.add_column("RSI14", justify="right")
        table.add_column("MACD", justify="right")
        table.add_column("ATR14", justify="right")
        table.add_column("BB Upper", justify="right")
        table.add_column("BB Lower", justify="right")

        for _, row in last.iterrows():
            rsi = row.get("rsi_14", 0)
            rsi_color = "red" if rsi > 70 else ("green" if rsi < 30 else "white")

            table.add_row(
                str(row["time"])[:16],
                f"{row['close']:.5f}",
                f"{row['sma_20']:.5f}" if pd.notna(row.get("sma_20")) else "-",
                f"{row['sma_50']:.5f}" if pd.notna(row.get("sma_50")) else "-",
                f"[{rsi_color}]{rsi:.1f}[/{rsi_color}]",
                f"{row.get('macd_line', 0):.5f}",
                f"{row.get('atr_14', 0):.5f}",
                f"{row.get('bb_upper', 0):.5f}",
                f"{row.get('bb_lower', 0):.5f}",
            )

        console.print(table)

        # Summary
        latest = df.iloc[-1]
        console.print(f"\n[bold]Latest Bar Summary:[/bold]")
        console.print(f"  Close:    {latest['close']:.5f}")
        console.print(f"  SMA20:    {latest.get('sma_20', 0):.5f}")
        console.print(f"  SMA50:    {latest.get('sma_50', 0):.5f}")

        sma20 = latest.get("sma_20", 0)
        sma50 = latest.get("sma_50", 0)
        if sma20 > sma50:
            console.print(f"  Trend:    [green]BULLISH[/green] (SMA20 > SMA50)")
        else:
            console.print(f"  Trend:    [red]BEARISH[/red] (SMA20 < SMA50)")

        rsi = latest.get("rsi_14", 50)
        if rsi > 70:
            console.print(f"  RSI:      [red]{rsi:.1f} (Overbought)[/red]")
        elif rsi < 30:
            console.print(f"  RSI:      [green]{rsi:.1f} (Oversold)[/green]")
        else:
            console.print(f"  RSI:      {rsi:.1f} (Neutral)")

        console.print(f"  ATR:      {latest.get('atr_14', 0):.5f}")
        console.print(f"  MACD:     {latest.get('macd_line', 0):.5f}")
        console.print(f"  Signal:   {latest.get('macd_signal', 0):.5f}")

        # Count non-NaN indicator values
        indicator_cols = ["sma_20", "sma_50", "ema_12", "ema_26", "rsi_14",
                         "macd_line", "macd_signal", "macd_hist",
                         "atr_14", "bb_upper", "bb_lower", "bb_width"]
        valid = df[indicator_cols].notna().sum()
        console.print(f"\n[bold]Indicator Coverage:[/bold]")
        for col in indicator_cols:
            pct = valid[col] / len(df) * 100
            console.print(f"  {col:15s}: {valid[col]:3d}/{len(df)} ({pct:.0f}%)")

        console.print("\n[bold green]All indicators computed successfully![/bold green]")

    finally:
        session.close()


if __name__ == "__main__":
    test_indicators()
