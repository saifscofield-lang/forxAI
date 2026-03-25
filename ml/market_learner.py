"""
Market-Driven Strategy Discovery — MarketLearner
بدل كتابة قواعد يدوية، السوق نفسه يعلّمنا متى نشتري ومتى نبيع.

Pipeline:
1. Load historical H1 data for all symbols
2. Compute 80+ features per bar (via feature_engine)
3. Label each bar: BUY / SELL / NO_TRADE based on future price movement
4. Train LightGBM per symbol with walk-forward validation
5. Export model for use in MLDirectStrategy

Usage:
    python ml/market_learner.py                # Train all symbols
    python ml/market_learner.py --symbol EURUSD  # Train one symbol
"""
import sys
sys.path.insert(0, ".")

import os
import json
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from loguru import logger

from features.ml.feature_engine import build_features, get_feature_columns

try:
    import lightgbm as lgb
except ImportError:
    raise ImportError("pip install lightgbm  (in requirements_ml.txt)")


# ── Configuration ─────────────────────────────────────────────────────
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "AUDUSD", "USDCAD", "USDCHF"]
TIMEFRAME = "H1"
DATA_DIR = Path("data/raw")
MODEL_DIR = Path("models/market_learner")

# Labeling params
FORWARD_HOURS = 6           # Look N hours ahead
MIN_MOVE_PIPS = {           # Minimum move to count as signal (in price units)
    "EURUSD": 0.0020,
    "GBPUSD": 0.0025,
    "USDJPY": 0.25,
    "XAUUSD": 8.0,
    "AUDUSD": 0.0020,
    "USDCAD": 0.0020,
    "USDCHF": 0.0020,
    "NZDUSD": 0.0020,
}

# Walk-forward params
TRAIN_YEARS = 10            # Use 10 years for training
VAL_YEARS = 2               # 2 years for validation
TEST_YEARS = 2              # 2 years for testing (most recent)


def load_data(symbol: str) -> pd.DataFrame:
    """Load H1 parquet data for a symbol."""
    path = DATA_DIR / symbol / f"{TIMEFRAME}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"No data: {path}")

    df = pd.read_parquet(path)
    df = df.sort_values("time").reset_index(drop=True)
    logger.info(f"[{symbol}] Loaded {len(df):,} bars ({df['time'].iloc[0]} to {df['time'].iloc[-1]})")
    return df


def create_labels(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    Label each bar based on future price movement.

    Labels:
        1 = BUY  (price goes up by MIN_MOVE within FORWARD_HOURS)
        -1 = SELL (price goes down by MIN_MOVE within FORWARD_HOURS)
        0 = NO_TRADE (neither threshold reached)
    """
    close = df["close"].values
    high_cols = []
    low_cols = []

    # Get max high and min low over next N bars
    for i in range(1, FORWARD_HOURS + 1):
        high_cols.append(df["high"].shift(-i))
        low_cols.append(df["low"].shift(-i))

    future_high = pd.concat(high_cols, axis=1).max(axis=1).values
    future_low = pd.concat(low_cols, axis=1).min(axis=1).values

    min_move = MIN_MOVE_PIPS.get(symbol, 0.0020)
    labels = np.zeros(len(df), dtype=np.int8)

    up_move = future_high - close
    down_move = close - future_low

    # If both thresholds met, pick the larger move
    buy_signal = up_move >= min_move
    sell_signal = down_move >= min_move

    labels[buy_signal & ~sell_signal] = 1
    labels[~buy_signal & sell_signal] = -1
    labels[buy_signal & sell_signal] = np.where(
        up_move[buy_signal & sell_signal] >= down_move[buy_signal & sell_signal], 1, -1
    )

    df["label"] = labels

    # Stats
    n = len(df) - FORWARD_HOURS  # exclude last bars (no future data)
    n_buy = (labels[:n] == 1).sum()
    n_sell = (labels[:n] == -1).sum()
    n_no = (labels[:n] == 0).sum()
    logger.info(
        f"[{symbol}] Labels: BUY={n_buy} ({n_buy/n*100:.1f}%), "
        f"SELL={n_sell} ({n_sell/n*100:.1f}%), "
        f"NO_TRADE={n_no} ({n_no/n*100:.1f}%)"
    )
    return df


def split_data(df: pd.DataFrame):
    """
    Walk-forward split: Train on oldest data, validate on middle, test on newest.
    No future data leaks into training.
    """
    times = pd.to_datetime(df["time"])
    max_time = times.max()

    test_start = max_time - pd.DateOffset(years=TEST_YEARS)
    val_start = test_start - pd.DateOffset(years=VAL_YEARS)

    train_mask = times < val_start
    val_mask = (times >= val_start) & (times < test_start)
    test_mask = times >= test_start

    train_df = df[train_mask].copy()
    val_df = df[val_mask].copy()
    test_df = df[test_mask].copy()

    logger.info(
        f"  Split: train={len(train_df):,} | val={len(val_df):,} | test={len(test_df):,}"
    )
    return train_df, val_df, test_df


def train_model(symbol: str, train_df: pd.DataFrame, val_df: pd.DataFrame, feature_cols: list):
    """Train LightGBM multiclass model (BUY=1, NO_TRADE=0, SELL=-1)."""

    # Remap labels: -1 -> 0, 0 -> 1, 1 -> 2 (LightGBM needs 0-based)
    label_map = {-1: 0, 0: 1, 1: 2}
    y_train = train_df["label"].map(label_map).values
    y_val = val_df["label"].map(label_map).values
    X_train = train_df[feature_cols].values
    X_val = val_df[feature_cols].values

    train_data = lgb.Dataset(X_train, label=y_train, feature_name=feature_cols)
    val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

    params = {
        "objective": "multiclass",
        "num_class": 3,
        "metric": "multi_logloss",
        "learning_rate": 0.05,
        "num_leaves": 63,
        "max_depth": 8,
        "min_child_samples": 50,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 0.1,
        "n_jobs": -1,
        "verbose": -1,
        "seed": 42,
    }

    callbacks = [
        lgb.early_stopping(50, verbose=False),
        lgb.log_evaluation(0),
    ]

    model = lgb.train(
        params,
        train_data,
        num_boost_round=1000,
        valid_sets=[val_data],
        callbacks=callbacks,
    )

    logger.info(f"[{symbol}] Best iteration: {model.best_iteration}")
    return model


def evaluate_model(symbol: str, model, test_df: pd.DataFrame, feature_cols: list) -> dict:
    """Evaluate model on test set. Return metrics."""
    label_map = {-1: 0, 0: 1, 1: 2}
    reverse_map = {0: "SELL", 1: "NO_TRADE", 2: "BUY"}

    y_true = test_df["label"].map(label_map).values
    X_test = test_df[feature_cols].values
    proba = model.predict(X_test)
    y_pred = proba.argmax(axis=1)

    # Overall accuracy
    accuracy = (y_pred == y_true).mean()

    # Per-class metrics
    results = {}
    for cls_id, cls_name in reverse_map.items():
        mask_true = y_true == cls_id
        mask_pred = y_pred == cls_id
        tp = (mask_true & mask_pred).sum()
        precision = tp / mask_pred.sum() if mask_pred.sum() > 0 else 0
        recall = tp / mask_true.sum() if mask_true.sum() > 0 else 0
        results[cls_name] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "count_true": int(mask_true.sum()),
            "count_pred": int(mask_pred.sum()),
        }

    # Simulated trading: only trade when model says BUY or SELL with high confidence
    trade_mask = y_pred != 1  # Not NO_TRADE
    if trade_mask.sum() > 0:
        trade_accuracy = (y_pred[trade_mask] == y_true[trade_mask]).mean()
        results["trade_signals"] = int(trade_mask.sum())
        results["trade_accuracy"] = round(trade_accuracy, 3)
    else:
        results["trade_signals"] = 0
        results["trade_accuracy"] = 0.0

    # High confidence trades (>= 60% probability)
    max_proba = proba.max(axis=1)
    high_conf_mask = trade_mask & (max_proba >= 0.60)
    if high_conf_mask.sum() > 0:
        hc_accuracy = (y_pred[high_conf_mask] == y_true[high_conf_mask]).mean()
        results["high_conf_signals"] = int(high_conf_mask.sum())
        results["high_conf_accuracy"] = round(hc_accuracy, 3)
    else:
        results["high_conf_signals"] = 0
        results["high_conf_accuracy"] = 0.0

    results["overall_accuracy"] = round(accuracy, 3)

    logger.info(
        f"[{symbol}] Test: accuracy={accuracy:.1%} | "
        f"trades={results['trade_signals']} ({results['trade_accuracy']:.1%}) | "
        f"high_conf={results['high_conf_signals']} ({results['high_conf_accuracy']:.1%})"
    )
    for cls_name, m in results.items():
        if isinstance(m, dict) and "precision" in m:
            logger.info(f"  {cls_name}: precision={m['precision']:.1%} recall={m['recall']:.1%} (n={m['count_true']})")

    return results


def get_feature_importance(model, feature_cols: list, top_n: int = 20) -> list:
    """Get top N most important features."""
    importance = model.feature_importance(importance_type="gain")
    pairs = sorted(zip(feature_cols, importance), key=lambda x: -x[1])
    return pairs[:top_n]


def train_symbol(symbol: str) -> dict | None:
    """Full pipeline for one symbol: load → features → label → split → train → evaluate."""
    logger.info(f"\n{'='*60}\n  Training: {symbol}\n{'='*60}")

    # 1. Load data
    df = load_data(symbol)

    # 2. Create labels
    df = create_labels(df, symbol)

    # 3. Build features
    df = build_features(df, dropna=False)

    # 4. Remove rows without labels (last FORWARD_HOURS bars) and NaN features
    df = df.iloc[:-FORWARD_HOURS]  # No future data for these
    df = df.dropna().reset_index(drop=True)

    feature_cols = get_feature_columns(df)
    logger.info(f"[{symbol}] Features: {len(feature_cols)} | Samples: {len(df):,}")

    # 5. Walk-forward split
    train_df, val_df, test_df = split_data(df)

    if len(train_df) < 1000 or len(val_df) < 100:
        logger.warning(f"[{symbol}] Not enough data for training, skipping")
        return None

    # 6. Train
    model = train_model(symbol, train_df, val_df, feature_cols)

    # 7. Evaluate
    metrics = evaluate_model(symbol, model, test_df, feature_cols)

    # 8. Feature importance
    top_features = get_feature_importance(model, feature_cols)
    logger.info(f"[{symbol}] Top features:")
    for fname, fval in top_features[:10]:
        logger.info(f"  {fname}: {fval:.0f}")

    # 9. Save model
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / f"{symbol}_model.pkl"
    meta = {
        "symbol": symbol,
        "timeframe": TIMEFRAME,
        "forward_hours": FORWARD_HOURS,
        "min_move": MIN_MOVE_PIPS.get(symbol),
        "feature_cols": feature_cols,
        "train_samples": len(train_df),
        "val_samples": len(val_df),
        "test_samples": len(test_df),
        "metrics": metrics,
        "top_features": top_features[:20],
        "trained_at": datetime.now().isoformat(),
        "best_iteration": model.best_iteration,
    }

    with open(model_path, "wb") as f:
        pickle.dump({"model": model, "meta": meta}, f)
    logger.info(f"[{symbol}] Model saved: {model_path}")

    # Save metrics JSON
    metrics_path = MODEL_DIR / f"{symbol}_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(meta, f, indent=2, default=str)

    return meta


def train_all():
    """Train models for all symbols."""
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>",
        level="INFO",
    )
    logger.add(
        "logs/market_learner.log",
        rotation="10 MB",
        retention="30 days",
        level="DEBUG",
    )

    Path("logs").mkdir(exist_ok=True)
    results = {}

    for symbol in SYMBOLS:
        try:
            meta = train_symbol(symbol)
            if meta:
                results[symbol] = meta["metrics"]
        except Exception as e:
            logger.error(f"[{symbol}] Failed: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    logger.info(f"\n{'='*60}\n  SUMMARY\n{'='*60}")
    for symbol, metrics in results.items():
        logger.info(
            f"  {symbol}: accuracy={metrics['overall_accuracy']:.1%} | "
            f"trades={metrics['trade_signals']} ({metrics['trade_accuracy']:.1%}) | "
            f"high_conf={metrics['high_conf_signals']} ({metrics['high_conf_accuracy']:.1%})"
        )

    # Save summary
    summary_path = MODEL_DIR / "training_summary.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"\nSummary saved: {summary_path}")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Market-Driven Strategy Discovery")
    parser.add_argument("--symbol", type=str, help="Train single symbol")
    args = parser.parse_args()

    if args.symbol:
        train_symbol(args.symbol.upper())
    else:
        train_all()
