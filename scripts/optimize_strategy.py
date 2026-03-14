"""
Parameter optimizer for SMA Crossover strategy.
GPU-accelerated indicators + Optuna Bayesian search + multiprocessing.
"""
import sys
import os
sys.path.insert(0, ".")
os.environ["PYTHONIOENCODING"] = "utf-8"

import time
import numpy as np
import pandas as pd
import yaml
import optuna
from concurrent.futures import ProcessPoolExecutor, as_completed
from loguru import logger

from backtest.gpu_indicators import batch_compute_indicators_gpu, GPU_AVAILABLE
from backtest.fast_backtest import fast_backtest, FastResult


# ── Config ──────────────────────────────────────────────────────────────
N_TRIALS = 500           # Optuna trials per symbol
N_WORKERS = 8            # Parallel backtest workers
INITIAL_BALANCE = 100_000.0
WARMUP = 60


def load_config(path: str = "config/base.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_data(symbol: str, timeframe: str) -> pd.DataFrame:
    path = f"data/raw/{symbol}/{timeframe}.parquet"
    df = pd.read_parquet(path)
    return df.sort_values("time").reset_index(drop=True)


# ── Single backtest worker (for multiprocessing) ────────────────────────
def run_single_backtest(args: dict) -> FastResult:
    """Run one backtest with given indicators and parameters."""
    return fast_backtest(
        close=args["close"],
        high=args["high"],
        low=args["low"],
        times=args["times"],
        sma_fast=args["sma_fast"],
        sma_slow=args["sma_slow"],
        rsi=args["rsi"],
        atr=args["atr"],
        atr_sl_mult=args["atr_sl_mult"],
        atr_tp_mult=args["atr_tp_mult"],
        pip_value=args["pip_value"],
        spread_pips=args.get("spread_pips", 1.0),
        risk_per_trade=args.get("risk_per_trade", 0.01),
        initial_balance=INITIAL_BALANCE,
        warmup=WARMUP,
    )


def optimize_symbol(symbol: str, timeframe: str, pip_value: float, config: dict):
    """Run Optuna optimization for one symbol."""
    logger.info(f"Optimizing {symbol} {timeframe}...")

    df = load_data(symbol, timeframe)
    close = df["close"].values.astype(np.float64)
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    times = df["time"].values

    risk_per_trade = config.get("risk", {}).get("max_risk_per_trade", 0.01)

    # Pre-compute indicators for all unique periods on GPU
    # Cache to avoid recomputation
    indicator_cache = {}

    def _compute_cpu(fast_p, slow_p, rsi_p, atr_p):
        from features.technical.indicators import add_sma, add_rsi, add_atr
        tmp = df.copy()
        tmp = add_sma(tmp, fast_p)
        tmp = add_sma(tmp, slow_p)
        tmp = add_rsi(tmp, rsi_p)
        tmp = add_atr(tmp, atr_p)
        return {
            "sma_fast": tmp[f"sma_{fast_p}"].values,
            "sma_slow": tmp[f"sma_{slow_p}"].values,
            "rsi": tmp[f"rsi_{rsi_p}"].values,
            "atr": tmp[f"atr_{atr_p}"].values,
        }

    def get_indicators(fast_p, slow_p, rsi_p, atr_p):
        key = (fast_p, slow_p, rsi_p, atr_p)
        if key not in indicator_cache:
            if GPU_AVAILABLE:
                try:
                    from backtest.gpu_indicators import compute_all_gpu
                    indicator_cache[key] = compute_all_gpu(
                        close, high, low, fast_p, slow_p, rsi_p, atr_p
                    )
                except Exception:
                    indicator_cache[key] = _compute_cpu(fast_p, slow_p, rsi_p, atr_p)
            else:
                indicator_cache[key] = _compute_cpu(fast_p, slow_p, rsi_p, atr_p)
        return indicator_cache[key]

    def objective(trial):
        # Sample parameters
        fast_period = trial.suggest_int("fast_period", 5, 50, step=5)
        slow_period = trial.suggest_int("slow_period", 30, 200, step=10)
        rsi_period = trial.suggest_int("rsi_period", 7, 28, step=7)
        atr_period = trial.suggest_int("atr_period", 7, 28, step=7)
        atr_sl_mult = trial.suggest_float("atr_sl_mult", 0.5, 3.0, step=0.25)
        atr_tp_mult = trial.suggest_float("atr_tp_mult", 1.0, 5.0, step=0.25)

        # Ensure fast < slow
        if fast_period >= slow_period:
            return float("-inf")

        # Get pre-computed indicators
        indicators = get_indicators(fast_period, slow_period, rsi_period, atr_period)

        result = fast_backtest(
            close=close,
            high=high,
            low=low,
            times=times,
            sma_fast=indicators["sma_fast"],
            sma_slow=indicators["sma_slow"],
            rsi=indicators["rsi"],
            atr=indicators["atr"],
            atr_sl_mult=atr_sl_mult,
            atr_tp_mult=atr_tp_mult,
            pip_value=pip_value,
            spread_pips=1.0,
            risk_per_trade=risk_per_trade,
            initial_balance=INITIAL_BALANCE,
            warmup=WARMUP,
        )

        # Optimize for Sharpe ratio (penalize few trades)
        if result.total_trades < 50:
            return float("-inf")

        # Multi-objective score: Sharpe + profit_factor bonus - drawdown penalty
        score = result.sharpe_ratio
        if result.max_drawdown_pct > 50:
            score -= (result.max_drawdown_pct - 50) * 0.05

        return score

    # Suppress Optuna logs
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=N_TRIALS, show_progress_bar=True)

    # Get best trial
    best = study.best_trial
    best_params = best.params

    # Run final backtest with best params to get full metrics
    indicators = get_indicators(
        best_params["fast_period"],
        best_params["slow_period"],
        best_params["rsi_period"],
        best_params["atr_period"],
    )
    best_result = fast_backtest(
        close=close, high=high, low=low, times=times,
        sma_fast=indicators["sma_fast"],
        sma_slow=indicators["sma_slow"],
        rsi=indicators["rsi"],
        atr=indicators["atr"],
        atr_sl_mult=best_params["atr_sl_mult"],
        atr_tp_mult=best_params["atr_tp_mult"],
        pip_value=pip_value,
        spread_pips=1.0,
        risk_per_trade=risk_per_trade,
        initial_balance=INITIAL_BALANCE,
        warmup=WARMUP,
    )

    return symbol, best_params, best_result, best.value


def main():
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        level="INFO",
        colorize=True,
    )

    logger.info(f"GPU: {'RTX 5070 (CuPy)' if GPU_AVAILABLE else 'Not available (CPU mode)'}")

    config = load_config()
    instruments = config.get("instruments", [])
    timeframe = config.get("timeframes", {}).get("primary", "H1")

    print()
    print("=" * 70)
    print("     SMA CROSSOVER PARAMETER OPTIMIZER")
    print(f"     GPU: {'ON' if GPU_AVAILABLE else 'OFF'} | Trials: {N_TRIALS} per symbol")
    print("=" * 70)

    all_results = []
    total_start = time.time()

    for inst in instruments:
        symbol = inst["symbol"]
        pip_value = inst.get("pip_value", 0.0001)

        try:
            start = time.time()
            symbol, best_params, best_result, score = optimize_symbol(
                symbol, timeframe, pip_value, config
            )
            elapsed = time.time() - start

            all_results.append((symbol, best_params, best_result, score))

            print()
            print(f"  {symbol} (optimized in {elapsed:.1f}s)")
            print(f"  {'─' * 60}")
            print(f"  Best parameters:")
            print(f"    SMA Fast:     {best_params['fast_period']}")
            print(f"    SMA Slow:     {best_params['slow_period']}")
            print(f"    RSI Period:   {best_params['rsi_period']}")
            print(f"    ATR Period:   {best_params['atr_period']}")
            print(f"    ATR SL Mult:  {best_params['atr_sl_mult']}")
            print(f"    ATR TP Mult:  {best_params['atr_tp_mult']}")
            print(f"  Results:")
            print(f"    P&L:          ${best_result.total_pnl:+,.2f}")
            print(f"    Trades:       {best_result.total_trades}")
            print(f"    Win Rate:     {best_result.win_rate:.1f}%")
            print(f"    Profit Factor:{best_result.profit_factor:.3f}")
            print(f"    Sharpe Ratio: {best_result.sharpe_ratio:.3f}")
            print(f"    Max Drawdown: {best_result.max_drawdown_pct:.1f}%")
            print(f"    Score:        {score:.3f}")

        except FileNotFoundError:
            logger.warning(f"No data for {symbol}/{timeframe}, skipping")
        except Exception as e:
            logger.error(f"Error optimizing {symbol}: {e}")

    total_elapsed = time.time() - total_start

    # Final summary
    print()
    print("=" * 70)
    print("     OPTIMIZATION SUMMARY")
    print(f"     Total time: {total_elapsed:.1f}s")
    print("=" * 70)

    for symbol, params, result, score in all_results:
        status = "OK" if result.profit_factor > 1.0 else "WEAK"
        print(
            f"  {symbol:8s} | PF: {result.profit_factor:5.3f} | "
            f"Sharpe: {result.sharpe_ratio:+6.3f} | "
            f"DD: {result.max_drawdown_pct:5.1f}% | "
            f"P&L: ${result.total_pnl:+12,.2f} | "
            f"[{status}]"
        )

    print("=" * 70)

    # Save best params to YAML
    output = {}
    for symbol, params, result, score in all_results:
        output[symbol] = {
            "params": params,
            "metrics": {
                "total_pnl": result.total_pnl,
                "total_trades": result.total_trades,
                "win_rate": result.win_rate,
                "profit_factor": result.profit_factor,
                "sharpe_ratio": result.sharpe_ratio,
                "max_drawdown_pct": result.max_drawdown_pct,
            },
        }

    output_path = "data/optimized_params.yaml"
    os.makedirs("data", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(output, f, default_flow_style=False, sort_keys=False)
    print(f"\n  Best parameters saved to: {output_path}")


if __name__ == "__main__":
    main()
