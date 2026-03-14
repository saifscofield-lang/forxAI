"""
تشغيل الباك تست — Run Backtest
Replay SMA Crossover strategy on historical data.
"""
import sys
import os
sys.path.insert(0, ".")
os.environ["PYTHONIOENCODING"] = "utf-8"

import pandas as pd
from loguru import logger
import yaml

from strategies.sma_crossover import SMACrossoverStrategy
from backtest.backtester import Backtester
from backtest.metrics import compute_metrics, format_report


def load_config(path: str = "config/base.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_data(symbol: str, timeframe: str) -> pd.DataFrame:
    """Load historical data from Parquet."""
    path = f"data/raw/{symbol}/{timeframe}.parquet"
    df = pd.read_parquet(path)
    df = df.sort_values("time").reset_index(drop=True)
    logger.info(f"Loaded {len(df)} bars from {path}")
    return df


def main():
    # Setup logging
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        level="INFO",
        colorize=True,
    )

    config = load_config()

    # Strategy
    strategy = SMACrossoverStrategy(
        fast_period=20,
        slow_period=50,
        rsi_period=14,
        atr_period=14,
        atr_sl_multiplier=1.5,
        atr_tp_multiplier=2.0,
    )

    # Instruments from config
    instruments = config.get("instruments", [])
    timeframe = config.get("timeframes", {}).get("primary", "H1")

    all_results = []

    for inst in instruments:
        symbol = inst["symbol"]
        pip_value = inst.get("pip_value", 0.0001)

        try:
            df = load_data(symbol, timeframe)
        except FileNotFoundError:
            logger.warning(f"No data for {symbol}/{timeframe}, skipping")
            continue

        bt = Backtester(
            strategy=strategy,
            initial_balance=100_000.0,
            risk_per_trade=config.get("risk", {}).get("max_risk_per_trade", 0.01),
            max_open_positions=config.get("risk", {}).get("max_open_positions", 5),
            pip_value=pip_value,
            spread_pips=1.0,
        )

        result = bt.run(df, warmup=60)
        report = compute_metrics(result)

        print()
        print(format_report(report, result))
        all_results.append((symbol, result, report))

    # Summary across all symbols
    if len(all_results) > 1:
        print()
        print("=" * 60)
        print("           COMBINED SUMMARY")
        print("=" * 60)
        total_pnl = 0
        total_trades = 0
        total_wins = 0
        for symbol, result, report in all_results:
            total_pnl += report.total_pnl
            total_trades += report.total_trades
            total_wins += report.winning_trades
            print(
                f"  {symbol:8s} | {report.total_trades:4d} trades | "
                f"Win: {report.win_rate:5.1f}% | "
                f"PF: {report.profit_factor:6.3f} | "
                f"P&L: ${report.total_pnl:+10,.2f} | "
                f"DD: {report.max_drawdown_pct:.1f}%"
            )
        print("-" * 60)
        combined_wr = total_wins / total_trades * 100 if total_trades else 0
        print(
            f"  {'TOTAL':8s} | {total_trades:4d} trades | "
            f"Win: {combined_wr:5.1f}% | "
            f"P&L: ${total_pnl:+10,.2f}"
        )
        print("=" * 60)


if __name__ == "__main__":
    main()
