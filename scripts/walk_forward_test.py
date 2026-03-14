"""
Walk-Forward Validation — اختبار المشي للأمام
Train on 2010-2022, test on 2023-2026 (unseen data).
Proves whether optimized params generalize or are overfit.
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
from loguru import logger

from backtest.gpu_indicators import GPU_AVAILABLE
from backtest.fast_backtest import fast_backtest


# ── Config ──────────────────────────────────────────────────────────────
TRAIN_END = "2022-12-31"      # Train: 2010 → 2022
TEST_START = "2023-01-01"     # Test:  2023 → 2026
N_TRIALS = 300                # Optuna trials for training period
INITIAL_BALANCE = 100_000.0
WARMUP = 60


def load_config(path: str = "config/base.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_data(symbol: str, timeframe: str) -> pd.DataFrame:
    path = f"data/raw/{symbol}/{timeframe}.parquet"
    df = pd.read_parquet(path)
    return df.sort_values("time").reset_index(drop=True)


def compute_indicators_cpu(df, fast_p, slow_p, rsi_p, atr_p):
    """Compute indicators using existing CPU functions."""
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


def compute_indicators(close, high, low, df, fast_p, slow_p, rsi_p, atr_p):
    """Compute indicators, GPU if available, CPU fallback."""
    if GPU_AVAILABLE:
        try:
            from backtest.gpu_indicators import compute_all_gpu
            return compute_all_gpu(close, high, low, fast_p, slow_p, rsi_p, atr_p)
        except Exception:
            pass
    return compute_indicators_cpu(df, fast_p, slow_p, rsi_p, atr_p)


def optimize_on_train(df_train, pip_value, risk_per_trade):
    """Run Optuna optimization on training data only."""
    close = df_train["close"].values.astype(np.float64)
    high = df_train["high"].values.astype(np.float64)
    low = df_train["low"].values.astype(np.float64)
    times = df_train["time"].values

    indicator_cache = {}

    def get_indicators(fp, sp, rp, ap):
        key = (fp, sp, rp, ap)
        if key not in indicator_cache:
            indicator_cache[key] = compute_indicators(
                close, high, low, df_train, fp, sp, rp, ap
            )
        return indicator_cache[key]

    def objective(trial):
        fast_period = trial.suggest_int("fast_period", 5, 50, step=5)
        slow_period = trial.suggest_int("slow_period", 30, 200, step=10)
        rsi_period = trial.suggest_int("rsi_period", 7, 28, step=7)
        atr_period = trial.suggest_int("atr_period", 7, 28, step=7)
        atr_sl_mult = trial.suggest_float("atr_sl_mult", 0.5, 3.0, step=0.25)
        atr_tp_mult = trial.suggest_float("atr_tp_mult", 1.0, 5.0, step=0.25)

        if fast_period >= slow_period:
            return float("-inf")

        indicators = get_indicators(fast_period, slow_period, rsi_period, atr_period)

        result = fast_backtest(
            close=close, high=high, low=low, times=times,
            sma_fast=indicators["sma_fast"],
            sma_slow=indicators["sma_slow"],
            rsi=indicators["rsi"],
            atr=indicators["atr"],
            atr_sl_mult=atr_sl_mult,
            atr_tp_mult=atr_tp_mult,
            pip_value=pip_value,
            risk_per_trade=risk_per_trade,
            initial_balance=INITIAL_BALANCE,
            warmup=WARMUP,
        )

        if result.total_trades < 30:
            return float("-inf")

        score = result.sharpe_ratio
        if result.max_drawdown_pct > 50:
            score -= (result.max_drawdown_pct - 50) * 0.05
        return score

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=N_TRIALS, show_progress_bar=True)

    return study.best_params


def backtest_with_params(df, params, pip_value, risk_per_trade):
    """Run backtest with specific parameters."""
    close = df["close"].values.astype(np.float64)
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    times = df["time"].values

    indicators = compute_indicators(
        close, high, low, df,
        params["fast_period"], params["slow_period"],
        params["rsi_period"], params["atr_period"],
    )

    return fast_backtest(
        close=close, high=high, low=low, times=times,
        sma_fast=indicators["sma_fast"],
        sma_slow=indicators["sma_slow"],
        rsi=indicators["rsi"],
        atr=indicators["atr"],
        atr_sl_mult=params["atr_sl_mult"],
        atr_tp_mult=params["atr_tp_mult"],
        pip_value=pip_value,
        risk_per_trade=risk_per_trade,
        initial_balance=INITIAL_BALANCE,
        warmup=WARMUP,
    )


def main():
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        level="INFO",
        colorize=True,
    )

    config = load_config()
    instruments = config.get("instruments", [])
    timeframe = config.get("timeframes", {}).get("primary", "H1")
    risk_per_trade = config.get("risk", {}).get("max_risk_per_trade", 0.01)

    print()
    print("=" * 70)
    print("     WALK-FORWARD VALIDATION")
    print(f"     Train: 2010 -> {TRAIN_END} | Test: {TEST_START} -> 2026")
    print(f"     GPU: {'ON' if GPU_AVAILABLE else 'OFF'} | Trials: {N_TRIALS}")
    print("=" * 70)

    results = []
    total_start = time.time()

    for inst in instruments:
        symbol = inst["symbol"]
        pip_value = inst.get("pip_value", 0.0001)

        try:
            df = load_data(symbol, timeframe)
        except FileNotFoundError:
            logger.warning(f"No data for {symbol}, skipping")
            continue

        # Split into train/test
        df["time"] = pd.to_datetime(df["time"])
        df_train = df[df["time"] <= TRAIN_END].reset_index(drop=True)
        df_test = df[df["time"] >= TEST_START].reset_index(drop=True)

        logger.info(
            f"{symbol}: Train={len(df_train)} bars "
            f"({df_train['time'].iloc[0].date()} -> {df_train['time'].iloc[-1].date()}) | "
            f"Test={len(df_test)} bars "
            f"({df_test['time'].iloc[0].date()} -> {df_test['time'].iloc[-1].date()})"
        )

        # Step 1: Optimize on training data
        start = time.time()
        best_params = optimize_on_train(df_train, pip_value, risk_per_trade)
        opt_time = time.time() - start

        # Step 2: Backtest on training data (in-sample)
        train_result = backtest_with_params(df_train, best_params, pip_value, risk_per_trade)

        # Step 3: Backtest on test data (out-of-sample)
        test_result = backtest_with_params(df_test, best_params, pip_value, risk_per_trade)

        results.append((symbol, best_params, train_result, test_result))

        # Display
        print()
        print(f"  {symbol} (optimized in {opt_time:.0f}s)")
        print(f"  {'-' * 62}")
        print(f"  Params: SMA {best_params['fast_period']}/{best_params['slow_period']} | "
              f"RSI {best_params['rsi_period']} | ATR {best_params['atr_period']} | "
              f"SL {best_params['atr_sl_mult']}x | TP {best_params['atr_tp_mult']}x")
        print(f"  {'-' * 62}")
        print(f"  {'':12s} {'Trades':>8s} {'Win%':>8s} {'PF':>8s} {'Sharpe':>8s} {'MaxDD':>8s} {'P&L':>14s}")
        print(f"  {'TRAIN':12s} {train_result.total_trades:>8d} {train_result.win_rate:>7.1f}% "
              f"{train_result.profit_factor:>8.3f} {train_result.sharpe_ratio:>8.3f} "
              f"{train_result.max_drawdown_pct:>7.1f}% ${train_result.total_pnl:>+12,.2f}")
        print(f"  {'TEST':12s} {test_result.total_trades:>8d} {test_result.win_rate:>7.1f}% "
              f"{test_result.profit_factor:>8.3f} {test_result.sharpe_ratio:>8.3f} "
              f"{test_result.max_drawdown_pct:>7.1f}% ${test_result.total_pnl:>+12,.2f}")

        # Verdict
        if test_result.profit_factor > 1.0 and test_result.sharpe_ratio > 0:
            verdict = "PASS — profitable on unseen data"
        elif test_result.profit_factor > 1.0:
            verdict = "WEAK PASS — profitable but low Sharpe"
        else:
            verdict = "FAIL — overfit, not profitable on unseen data"
        print(f"  Verdict:  {verdict}")

    total_time = time.time() - total_start

    # Final summary
    print()
    print("=" * 70)
    print("     WALK-FORWARD SUMMARY")
    print(f"     Total time: {total_time:.0f}s")
    print("=" * 70)
    print(f"  {'Symbol':8s} | {'Train PF':>9s} {'Test PF':>9s} | "
          f"{'Train Sharpe':>13s} {'Test Sharpe':>12s} | {'Status':>6s}")
    print(f"  {'-' * 62}")

    pass_count = 0
    for symbol, params, train_r, test_r in results:
        passed = test_r.profit_factor > 1.0 and test_r.sharpe_ratio > 0
        if passed:
            pass_count += 1
        status = "PASS" if passed else "FAIL"
        print(f"  {symbol:8s} | {train_r.profit_factor:>9.3f} {test_r.profit_factor:>9.3f} | "
              f"{train_r.sharpe_ratio:>+12.3f} {test_r.sharpe_ratio:>+12.3f} | {status:>6s}")

    print(f"  {'-' * 62}")
    print(f"  Result: {pass_count}/{len(results)} symbols passed walk-forward validation")
    print("=" * 70)

    # Save validated params
    if pass_count > 0:
        validated = {}
        for symbol, params, train_r, test_r in results:
            if test_r.profit_factor > 1.0 and test_r.sharpe_ratio > 0:
                validated[symbol] = {
                    "params": {k: float(v) if isinstance(v, (np.floating,)) else v
                               for k, v in params.items()},
                    "train_pf": round(float(train_r.profit_factor), 3),
                    "test_pf": round(float(test_r.profit_factor), 3),
                    "train_sharpe": round(float(train_r.sharpe_ratio), 3),
                    "test_sharpe": round(float(test_r.sharpe_ratio), 3),
                }

        output_path = "data/validated_params.yaml"
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(validated, f, default_flow_style=False, sort_keys=False)
        print(f"\n  Validated params saved to: {output_path}")


if __name__ == "__main__":
    main()
