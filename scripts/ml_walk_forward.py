"""
ML Walk-Forward Validation.
Train LightGBM on 2010-2022, optimize hyperparams, test on 2023-2026.
Compares ML signals vs pure SMA crossover.
"""
import sys
import os
sys.path.insert(0, ".")
os.environ["PYTHONIOENCODING"] = "utf-8"

import time
import numpy as np
import pandas as pd
import yaml
from loguru import logger

from features.ml.feature_engine import build_features, get_feature_columns
from features.ml.label_engine import add_labels, label_distribution
from ml.model import ForexLGBM, optimize_lgbm
from backtest.ml_backtest import ml_backtest
from backtest.fast_backtest import fast_backtest
from backtest.gpu_indicators import GPU_AVAILABLE


# ── Config ──────────────────────────────────────────────────────────────
TRAIN_END = "2022-12-31"
TEST_START = "2023-01-01"
OPTUNA_TRIALS = 80            # Hyperparameter optimization trials
LABEL_HORIZON = 20            # Look-forward bars for labeling
ATR_SL_MULT = 1.5             # Stop loss multiplier for trades
ATR_TP_MULT = 2.0             # Symmetric barrier distance for labeling
CONFIDENCE_THRESHOLD = 0.55   # Minimum prediction confidence (high = fewer but better trades)
EMBARGO_BARS = 20             # Gap between train and test to prevent label leakage
INITIAL_BALANCE = 100_000.0


def load_config(path: str = "config/base.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_data(symbol: str, timeframe: str) -> pd.DataFrame:
    path = f"data/raw/{symbol}/{timeframe}.parquet"
    df = pd.read_parquet(path)
    return df.sort_values("time").reset_index(drop=True)


def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    """Build features + labels for ML training."""
    # Build features (uses past data only)
    df = build_features(df, dropna=False)

    # Ensure ATR is computed for labeling
    if "atr_14" not in df.columns:
        from features.technical.indicators import add_atr
        df = add_atr(df, 14)

    # Drop warmup NaN rows BEFORE labeling
    df.dropna(subset=get_feature_columns(df), inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Add labels (uses future data — only for training targets)
    df = add_labels(
        df,
        horizon=LABEL_HORIZON,
        method="triple_barrier",
        atr_sl_mult=ATR_SL_MULT,
        atr_tp_mult=ATR_TP_MULT,
        atr_col="atr_14",
    )

    return df


def run_sma_baseline(df_test, pip_value):
    """Run SMA crossover baseline on test data for comparison."""
    from features.technical.indicators import add_sma, add_rsi, add_atr
    tmp = df_test.copy()
    tmp = add_sma(tmp, 20)
    tmp = add_sma(tmp, 50)
    tmp = add_rsi(tmp, 14)
    tmp = add_atr(tmp, 14)

    close = tmp["close"].values.astype(np.float64)
    high = tmp["high"].values.astype(np.float64)
    low = tmp["low"].values.astype(np.float64)
    times = tmp["time"].values

    return fast_backtest(
        close=close, high=high, low=low, times=times,
        sma_fast=tmp["sma_20"].values,
        sma_slow=tmp["sma_50"].values,
        rsi=tmp["rsi_14"].values,
        atr=tmp["atr_14"].values,
        atr_sl_mult=ATR_SL_MULT,
        atr_tp_mult=ATR_TP_MULT,
        pip_value=pip_value,
        risk_per_trade=0.01,
        initial_balance=INITIAL_BALANCE,
        warmup=60,
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

    print()
    print("=" * 75)
    print("     ML WALK-FORWARD VALIDATION (LightGBM)")
    print(f"     Train: 2010 -> {TRAIN_END} | Test: {TEST_START} -> 2026")
    print(f"     GPU: {'ON' if GPU_AVAILABLE else 'OFF'} | Optuna trials: {OPTUNA_TRIALS}")
    print(f"     Label: triple_barrier (horizon={LABEL_HORIZON}, SL={ATR_SL_MULT}x, TP={ATR_TP_MULT}x)")
    print(f"     Confidence threshold: {CONFIDENCE_THRESHOLD}")
    print("=" * 75)

    results = []
    total_start = time.time()

    for inst in instruments:
        symbol = inst["symbol"]
        pip_value = inst.get("pip_value", 0.0001)
        sym_start = time.time()

        try:
            df_raw = load_data(symbol, timeframe)
        except FileNotFoundError:
            logger.warning(f"No data for {symbol}, skipping")
            continue

        df_raw["time"] = pd.to_datetime(df_raw["time"])

        logger.info(f"{symbol}: Building features + labels...")

        # ── 1. Prepare data ─────────────────────────────────────────
        df = prepare_data(df_raw)
        feature_cols = get_feature_columns(df)

        logger.info(f"  Features: {len(feature_cols)} | Rows: {len(df)}")

        # ── 2. Split train/test with embargo ────────────────────────
        df_train_full = df[df["time"] <= TRAIN_END].reset_index(drop=True)
        df_test = df[df["time"] >= TEST_START].reset_index(drop=True)

        # Apply embargo: remove last EMBARGO_BARS from train (labels look forward)
        if len(df_train_full) > EMBARGO_BARS:
            df_train = df_train_full.iloc[:-EMBARGO_BARS].reset_index(drop=True)
        else:
            df_train = df_train_full

        if len(df_train) < 1000 or len(df_test) < 100:
            logger.warning(f"  Not enough data: train={len(df_train)}, test={len(df_test)}")
            continue

        X_train = df_train[feature_cols].values
        y_train = df_train["label"].values
        X_test = df_test[feature_cols].values
        y_test = df_test["label"].values

        # Train/val split (last 20% for validation, with embargo)
        val_split = int(len(X_train) * 0.8)
        X_tr = X_train[:val_split - EMBARGO_BARS]
        y_tr = y_train[:val_split - EMBARGO_BARS]
        X_val = X_train[val_split:]
        y_val = y_train[val_split:]

        logger.info(
            f"  Train: {len(X_tr)} | Val: {len(X_val)} | Test: {len(X_test)}"
        )

        # Label distribution
        dist = label_distribution(y_train)
        dist_str = " | ".join(f"{k}: {v['pct']:.1f}%" for k, v in dist.items())
        logger.info(f"  Labels (train): {dist_str}")

        # ── 3. Optimize hyperparameters ─────────────────────────────
        logger.info(f"  Optimizing hyperparameters ({OPTUNA_TRIALS} trials)...")
        opt_start = time.time()
        best_params = optimize_lgbm(
            X_tr, y_tr, X_val, y_val,
            n_trials=OPTUNA_TRIALS,
            feature_names=feature_cols,
        )
        opt_time = time.time() - opt_start
        logger.info(f"  Optimization done in {opt_time:.0f}s")

        # ── 4. Train final model with best params ───────────────────
        model = ForexLGBM(**best_params)
        model.train(
            X_tr, y_tr, X_val, y_val,
            feature_names=feature_cols,
            early_stopping_rounds=50,
        )

        # ── 5. Evaluate ────────────────────────────────────────────
        eval_result = model.evaluate(X_train, y_train, X_test, y_test, feature_cols)

        logger.info(
            f"  ML Accuracy: {eval_result.accuracy:.1%} | "
            f"F1 macro: {eval_result.f1_macro:.3f}"
        )

        # ── 6. ML Backtest on test period ───────────────────────────
        predictions = model.predict(X_test)
        probabilities = model.predict_proba(X_test).max(axis=1)

        # Get ATR for test period
        atr_test = df_test["atr_14"].values if "atr_14" in df_test.columns else \
                   df_test["atr_7"].values

        ml_result = ml_backtest(
            close=df_test["close"].values.astype(np.float64),
            high=df_test["high"].values.astype(np.float64),
            low=df_test["low"].values.astype(np.float64),
            times=df_test["time"].values,
            predictions=predictions,
            probabilities=probabilities,
            atr=atr_test.astype(np.float64),
            atr_sl_mult=ATR_SL_MULT,
            atr_tp_mult=ATR_TP_MULT,
            confidence_threshold=CONFIDENCE_THRESHOLD,
            pip_value=pip_value,
            risk_per_trade=0.01,
            initial_balance=INITIAL_BALANCE,
        )

        # ── 7. SMA Baseline on test period ──────────────────────────
        df_test_raw = df_raw[df_raw["time"] >= TEST_START].reset_index(drop=True)
        sma_result = run_sma_baseline(df_test_raw, pip_value)

        sym_time = time.time() - sym_start

        results.append({
            "symbol": symbol,
            "ml_result": ml_result,
            "sma_result": sma_result,
            "eval": eval_result,
            "best_params": best_params,
            "time": sym_time,
        })

        # ── Display ─────────────────────────────────────────────────
        print()
        print(f"  {symbol} (completed in {sym_time:.0f}s)")
        print(f"  {'-' * 70}")
        print(f"  ML Model: Acc={eval_result.accuracy:.1%} | F1={eval_result.f1_macro:.3f}")
        print(f"  Top features: {', '.join(list(eval_result.feature_importance.keys())[:5])}")
        print(f"  {'-' * 70}")
        print(f"  {'':14s} {'Trades':>8s} {'Win%':>8s} {'PF':>8s} {'Sharpe':>8s} {'MaxDD':>8s} {'P&L':>14s}")
        print(f"  {'ML MODEL':14s} {ml_result.total_trades:>8d} {ml_result.win_rate:>7.1f}% "
              f"{ml_result.profit_factor:>8.3f} {ml_result.sharpe_ratio:>8.3f} "
              f"{ml_result.max_drawdown_pct:>7.1f}% ${ml_result.total_pnl:>+12,.2f}")
        print(f"  {'SMA BASELINE':14s} {sma_result.total_trades:>8d} {sma_result.win_rate:>7.1f}% "
              f"{sma_result.profit_factor:>8.3f} {sma_result.sharpe_ratio:>8.3f} "
              f"{sma_result.max_drawdown_pct:>7.1f}% ${sma_result.total_pnl:>+12,.2f}")

        # ML vs SMA comparison
        if ml_result.profit_factor > sma_result.profit_factor:
            comp = f"ML wins (PF {ml_result.profit_factor:.3f} vs {sma_result.profit_factor:.3f})"
        else:
            comp = f"SMA wins (PF {sma_result.profit_factor:.3f} vs {ml_result.profit_factor:.3f})"
        print(f"  Comparison: {comp}")

        # Verdict
        if ml_result.profit_factor > 1.0 and ml_result.sharpe_ratio > 0:
            verdict = "PASS -- ML profitable on unseen data"
        elif ml_result.profit_factor > 1.0:
            verdict = "WEAK PASS -- profitable but low Sharpe"
        else:
            verdict = "FAIL -- not profitable on unseen data"
        print(f"  Verdict:  {verdict}")

        # Save model
        model_path = f"data/models/{symbol}_lgbm.txt"
        os.makedirs("data/models", exist_ok=True)
        model.save(model_path)
        logger.info(f"  Model saved to {model_path}")

    total_time = time.time() - total_start

    # ── Final Summary ───────────────────────────────────────────────
    print()
    print("=" * 75)
    print("     ML WALK-FORWARD SUMMARY")
    print(f"     Total time: {total_time:.0f}s")
    print("=" * 75)
    print(f"  {'Symbol':8s} | {'ML PF':>8s} {'SMA PF':>8s} | "
          f"{'ML Sharpe':>10s} {'SMA Sharpe':>11s} | {'ML F1':>6s} | {'Status':>6s}")
    print(f"  {'-' * 70}")

    pass_count = 0
    ml_wins = 0
    for r in results:
        ml = r["ml_result"]
        sma = r["sma_result"]
        passed = ml.profit_factor > 1.0 and ml.sharpe_ratio > 0
        if passed:
            pass_count += 1
        if ml.profit_factor > sma.profit_factor:
            ml_wins += 1
        status = "PASS" if passed else "FAIL"
        print(f"  {r['symbol']:8s} | {ml.profit_factor:>8.3f} {sma.profit_factor:>8.3f} | "
              f"{ml.sharpe_ratio:>+10.3f} {sma.sharpe_ratio:>+11.3f} | "
              f"{r['eval'].f1_macro:>5.3f} | {status:>6s}")

    print(f"  {'-' * 70}")
    print(f"  Result: {pass_count}/{len(results)} symbols passed ML walk-forward")
    print(f"  ML beat SMA baseline: {ml_wins}/{len(results)} symbols")
    print("=" * 75)

    # Save validated ML params
    if pass_count > 0:
        validated = {}
        for r in results:
            ml = r["ml_result"]
            if ml.profit_factor > 1.0 and ml.sharpe_ratio > 0:
                validated[r["symbol"]] = {
                    "model_path": f"data/models/{r['symbol']}_lgbm.txt",
                    "best_params": r["best_params"],
                    "test_pf": round(float(ml.profit_factor), 3),
                    "test_sharpe": round(float(ml.sharpe_ratio), 3),
                    "test_trades": ml.total_trades,
                    "test_win_rate": ml.win_rate,
                    "f1_macro": round(float(r["eval"].f1_macro), 3),
                    "confidence_threshold": CONFIDENCE_THRESHOLD,
                }

        output_path = "data/ml_validated_params.yaml"
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(validated, f, default_flow_style=False, sort_keys=False)
        print(f"\n  ML validated params saved to: {output_path}")


if __name__ == "__main__":
    main()
