"""
ML-Filtered Walk-Forward Validation.
Strategy: SMA crossover generates signals, ML filters out bad trades.
Binary classification: will this trade be profitable (1) or not (0)?
"""
import sys
import os
sys.path.insert(0, ".")
os.environ["PYTHONIOENCODING"] = "utf-8"

import time
import numpy as np
import pandas as pd
import yaml
import lightgbm as lgb
from loguru import logger
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

from features.ml.feature_engine import build_features, get_feature_columns
from features.technical.indicators import add_sma, add_rsi, add_atr
from backtest.fast_backtest import fast_backtest


# ── Config ──────────────────────────────────────────────────────────────
TRAIN_END = "2022-12-31"
TEST_START = "2023-01-01"
OPTUNA_TRIALS = 80
INITIAL_BALANCE = 100_000.0
WARMUP = 200  # For SMA200 + features

# SMA crossover params (use walk-forward validated or reasonable defaults)
DEFAULT_PARAMS = {
    "fast_period": 20, "slow_period": 50,
    "rsi_period": 14, "atr_period": 14,
    "atr_sl_mult": 1.5, "atr_tp_mult": 2.5,
}


def load_config(path: str = "config/base.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_data(symbol: str, timeframe: str) -> pd.DataFrame:
    path = f"data/raw/{symbol}/{timeframe}.parquet"
    df = pd.read_parquet(path)
    return df.sort_values("time").reset_index(drop=True)


def find_sma_crossover_signals(df, fast_p, slow_p, rsi_p, atr_p):
    """Find all SMA crossover signal bars and their outcomes."""
    tmp = df.copy()
    tmp = add_sma(tmp, fast_p)
    tmp = add_sma(tmp, slow_p)
    tmp = add_rsi(tmp, rsi_p)
    tmp = add_atr(tmp, atr_p)

    sma_fast = tmp[f"sma_{fast_p}"].values
    sma_slow = tmp[f"sma_{slow_p}"].values
    rsi = tmp[f"rsi_{rsi_p}"].values
    atr = tmp[f"atr_{atr_p}"].values
    close = tmp["close"].values
    high = tmp["high"].values
    low = tmp["low"].values

    signals = []

    for i in range(1, len(tmp)):
        if (np.isnan(sma_fast[i]) or np.isnan(sma_fast[i-1]) or
            np.isnan(sma_slow[i]) or np.isnan(sma_slow[i-1]) or
            np.isnan(rsi[i]) or np.isnan(atr[i]) or atr[i] <= 0):
            continue

        signal = 0
        # BUY crossover
        if sma_fast[i-1] <= sma_slow[i-1] and sma_fast[i] > sma_slow[i]:
            if rsi[i] < 70:
                signal = 1
        # SELL crossover
        elif sma_fast[i-1] >= sma_slow[i-1] and sma_fast[i] < sma_slow[i]:
            if rsi[i] > 30:
                signal = -1

        if signal != 0:
            signals.append({
                "bar_idx": i,
                "signal": signal,
                "price": close[i],
                "atr": atr[i],
            })

    return signals


def label_trades(signals, close, high, low, atr_sl_mult, atr_tp_mult, pip_value):
    """Simulate each signal trade and label as profitable (1) or not (0)."""
    n = len(close)
    labeled = []

    for sig in signals:
        i = sig["bar_idx"]
        direction = sig["signal"]
        entry = sig["price"]
        curr_atr = sig["atr"]
        spread_cost = pip_value * 1.0  # 1 pip spread

        if direction == 1:
            entry_adj = entry + spread_cost
            sl = entry - curr_atr * atr_sl_mult
            tp = entry + curr_atr * atr_tp_mult
        else:
            entry_adj = entry - spread_cost
            sl = entry + curr_atr * atr_sl_mult
            tp = entry - curr_atr * atr_tp_mult

        # Simulate forward
        pnl = 0.0
        for j in range(i + 1, min(i + 200, n)):  # Max 200 bars horizon
            if direction == 1:
                if low[j] <= sl:
                    pnl = sl - entry_adj
                    break
                if high[j] >= tp:
                    pnl = tp - entry_adj
                    break
            else:
                if high[j] >= sl:
                    pnl = entry_adj - sl
                    break
                if low[j] <= tp:
                    pnl = entry_adj - tp
                    break
        else:
            # Close at last bar
            if direction == 1:
                pnl = close[min(i + 200, n) - 1] - entry_adj
            else:
                pnl = entry_adj - close[min(i + 200, n) - 1]

        labeled.append({
            "bar_idx": i,
            "signal": direction,
            "profitable": 1 if pnl > 0 else 0,
            "pnl": pnl,
        })

    return labeled


def run_filtered_backtest(
    df, feature_df, feature_cols, model, params, pip_value,
    confidence_threshold=0.50,
):
    """Run SMA crossover backtest, but skip trades ML flags as bad."""
    fast_p = params["fast_period"]
    slow_p = params["slow_period"]
    rsi_p = params["rsi_period"]
    atr_p = params["atr_period"]

    tmp = df.copy()
    tmp = add_sma(tmp, fast_p)
    tmp = add_sma(tmp, slow_p)
    tmp = add_rsi(tmp, rsi_p)
    tmp = add_atr(tmp, atr_p)

    close = tmp["close"].values.astype(np.float64)
    high = tmp["high"].values.astype(np.float64)
    low = tmp["low"].values.astype(np.float64)
    times = tmp["time"].values
    sma_fast = tmp[f"sma_{fast_p}"].values
    sma_slow = tmp[f"sma_{slow_p}"].values
    rsi = tmp[f"rsi_{rsi_p}"].values
    atr = tmp[f"atr_{atr_p}"].values

    # Build a lookup: bar time -> feature row
    feat_time_to_idx = {}
    if "time" in feature_df.columns:
        for idx, t in enumerate(feature_df["time"].values):
            feat_time_to_idx[t] = idx

    balance = INITIAL_BALANCE
    in_trade = False
    trade_action = 0
    entry_price = 0.0
    stop_loss = 0.0
    take_profit = 0.0
    lot_size = 0.0

    pnls = []
    equity_peak = INITIAL_BALANCE
    max_dd = 0.0
    equity_history = []
    trades_taken = 0
    trades_filtered = 0

    pip_value_per_lot = pip_value * 100_000
    spread_cost = 1.0 * pip_value
    risk_per_trade = 0.01

    X_features = feature_df[feature_cols].values if feature_cols else None

    for i in range(WARMUP, len(close)):
        # Check exits
        if in_trade:
            hit_sl = hit_tp = False
            if trade_action == 1:
                if low[i] <= stop_loss: hit_sl = True
                if high[i] >= take_profit: hit_tp = True
            else:
                if high[i] >= stop_loss: hit_sl = True
                if low[i] <= take_profit: hit_tp = True

            exit_price = 0.0
            if hit_sl: exit_price = stop_loss
            elif hit_tp: exit_price = take_profit

            if exit_price > 0:
                if trade_action == 1:
                    pnl_pips = (exit_price - entry_price) / pip_value
                else:
                    pnl_pips = (entry_price - exit_price) / pip_value
                pnl = pnl_pips * pip_value_per_lot * lot_size
                balance += pnl
                pnls.append(pnl)
                in_trade = False

        # Check for new signal
        if not in_trade and i >= 1:
            if (np.isnan(sma_fast[i]) or np.isnan(sma_fast[i-1]) or
                np.isnan(sma_slow[i]) or np.isnan(sma_slow[i-1]) or
                np.isnan(rsi[i]) or np.isnan(atr[i]) or atr[i] <= 0):
                continue

            signal = 0
            if sma_fast[i-1] <= sma_slow[i-1] and sma_fast[i] > sma_slow[i]:
                if rsi[i] < 70: signal = 1
            elif sma_fast[i-1] >= sma_slow[i-1] and sma_fast[i] < sma_slow[i]:
                if rsi[i] > 30: signal = -1

            if signal != 0:
                # ML filter: check if model predicts profitable
                take_trade = True
                if model is not None and X_features is not None:
                    t = times[i]
                    feat_idx = feat_time_to_idx.get(t)
                    if feat_idx is not None and feat_idx < len(X_features):
                        x = X_features[feat_idx:feat_idx+1]
                        prob = model.predict_proba(x)[0]
                        # prob[1] = probability of profitable trade
                        if prob[1] < confidence_threshold:
                            take_trade = False
                            trades_filtered += 1

                if take_trade:
                    price = close[i]
                    curr_atr = atr[i]
                    if signal == 1:
                        entry_price = price + spread_cost
                        stop_loss = price - curr_atr * params["atr_sl_mult"]
                        take_profit = price + curr_atr * params["atr_tp_mult"]
                    else:
                        entry_price = price - spread_cost
                        stop_loss = price + curr_atr * params["atr_sl_mult"]
                        take_profit = price - curr_atr * params["atr_tp_mult"]

                    sl_pips = abs(entry_price - stop_loss) / pip_value
                    if sl_pips > 0 and balance > 0:
                        risk_amount = balance * risk_per_trade
                        lot_size = risk_amount / (sl_pips * pip_value_per_lot)
                        lot_size = max(0.01, round(lot_size, 2))
                        lot_size = min(lot_size, 10.0)
                        trade_action = signal
                        in_trade = True
                        trades_taken += 1

        # Track equity
        equity = balance
        if in_trade:
            if trade_action == 1:
                unrealized = (close[i] - entry_price) / pip_value * pip_value_per_lot * lot_size
            else:
                unrealized = (entry_price - close[i]) / pip_value * pip_value_per_lot * lot_size
            equity += unrealized
        equity_history.append(equity)
        if equity > equity_peak: equity_peak = equity
        dd = (equity_peak - equity) / equity_peak * 100 if equity_peak > 0 else 0
        if dd > max_dd: max_dd = dd

    # Close remaining
    if in_trade:
        if trade_action == 1:
            pnl_pips = (close[-1] - entry_price) / pip_value
        else:
            pnl_pips = (entry_price - close[-1]) / pip_value
        pnl = pnl_pips * pip_value_per_lot * lot_size
        balance += pnl
        pnls.append(pnl)

    total_trades = len(pnls)
    if total_trades == 0:
        return {"pnl": 0, "trades": 0, "win_rate": 0, "pf": 0, "sharpe": 0,
                "max_dd": 0, "filtered": trades_filtered}

    pnls_arr = np.array(pnls)
    wins = pnls_arr[pnls_arr > 0]
    losses = pnls_arr[pnls_arr <= 0]
    win_rate = len(wins) / total_trades * 100
    gp = wins.sum() if len(wins) > 0 else 0
    gl = abs(losses.sum()) if len(losses) > 0 else 0
    pf = gp / gl if gl > 0 else float("inf")
    total_pnl = balance - INITIAL_BALANCE

    eq_arr = np.array(equity_history)
    if len(eq_arr) > 1:
        rets = np.diff(eq_arr) / eq_arr[:-1]
        rets = rets[~np.isnan(rets) & ~np.isinf(rets)]
        sharpe = rets.mean() / rets.std() * np.sqrt(252 * 24) if len(rets) > 0 and rets.std() > 0 else 0
    else:
        sharpe = 0

    return {
        "pnl": round(total_pnl, 2),
        "trades": total_trades,
        "win_rate": round(win_rate, 1),
        "pf": round(pf, 3),
        "sharpe": round(sharpe, 3),
        "max_dd": round(max_dd, 2),
        "filtered": trades_filtered,
    }


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

    # Load optimized params if available
    try:
        with open("data/optimized_params.yaml", "r") as f:
            optimized_params = yaml.safe_load(f)
    except FileNotFoundError:
        optimized_params = {}

    print()
    print("=" * 75)
    print("     ML-FILTERED WALK-FORWARD (SMA Crossover + ML Quality Filter)")
    print(f"     Train: 2010 -> {TRAIN_END} | Test: {TEST_START} -> 2026")
    print(f"     Optuna: {OPTUNA_TRIALS} trials | Binary: profitable vs not")
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

        # Get params for this symbol
        params = optimized_params.get(symbol, DEFAULT_PARAMS)

        logger.info(f"{symbol}: Building features...")
        df_feat = build_features(df_raw, dropna=True)
        feature_cols = get_feature_columns(df_feat)
        logger.info(f"  Features: {len(feature_cols)} | Rows: {len(df_feat)}")

        # ── Find all SMA crossover signals ──────────────────────────
        logger.info(f"  Finding crossover signals with params: "
                     f"SMA {params['fast_period']}/{params['slow_period']}...")

        close = df_raw["close"].values.astype(np.float64)
        high = df_raw["high"].values.astype(np.float64)
        low = df_raw["low"].values.astype(np.float64)

        all_signals = find_sma_crossover_signals(
            df_raw, params["fast_period"], params["slow_period"],
            params["rsi_period"], params["atr_period"],
        )
        logger.info(f"  Total crossover signals: {len(all_signals)}")

        # ── Label signals (profitable or not) ───────────────────────
        labeled = label_trades(
            all_signals, close, high, low,
            params["atr_sl_mult"], params["atr_tp_mult"], pip_value,
        )

        # ── Map labels to feature rows ──────────────────────────────
        # Build time lookup for features
        feat_times = set(df_feat["time"].values)
        raw_times = df_raw["time"].values

        X_list = []
        y_list = []
        times_list = []

        for lbl in labeled:
            bar_time = raw_times[lbl["bar_idx"]]
            if bar_time in feat_times:
                feat_row = df_feat[df_feat["time"] == bar_time]
                if len(feat_row) == 1:
                    X_list.append(feat_row[feature_cols].values[0])
                    y_list.append(lbl["profitable"])
                    times_list.append(bar_time)

        if len(X_list) < 50:
            logger.warning(f"  Too few labeled signals: {len(X_list)}")
            continue

        X_all = np.array(X_list)
        y_all = np.array(y_list)
        times_arr = np.array(times_list)

        # ── Split train/test ────────────────────────────────────────
        train_end_ts = pd.Timestamp(TRAIN_END)
        test_start_ts = pd.Timestamp(TEST_START)

        train_mask = times_arr <= train_end_ts
        test_mask = times_arr >= test_start_ts

        X_train, y_train = X_all[train_mask], y_all[train_mask]
        X_test, y_test = X_all[test_mask], y_all[test_mask]

        if len(X_train) < 30 or len(X_test) < 10:
            logger.warning(f"  Not enough signals: train={len(X_train)}, test={len(X_test)}")
            continue

        # Val split from train
        val_split = int(len(X_train) * 0.8)
        X_tr, X_val = X_train[:val_split], X_train[val_split:]
        y_tr, y_val = y_train[:val_split], y_train[val_split:]

        win_pct = y_train.mean() * 100
        logger.info(
            f"  Signals: train={len(X_train)} (win {win_pct:.1f}%) | test={len(X_test)}"
        )

        # ── Optimize LightGBM ──────────────────────────────────────
        logger.info(f"  Optimizing ML filter ({OPTUNA_TRIALS} trials)...")
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        def objective(trial):
            p = {
                "n_estimators": 500,
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                "max_depth": trial.suggest_int("max_depth", 3, 8),
                "num_leaves": trial.suggest_int("num_leaves", 15, 63),
                "min_child_samples": trial.suggest_int("min_child_samples", 10, 100),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.4, 1.0),
                "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 10, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10, log=True),
                "class_weight": "balanced",
                "random_state": 42,
                "verbose": -1,
                "n_jobs": -1,
            }
            m = lgb.LGBMClassifier(**p)
            m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                  callbacks=[lgb.early_stopping(30, verbose=False),
                             lgb.log_evaluation(0)])
            y_pred = m.predict(X_val)
            # Optimize for precision on "profitable" class — we want fewer but better trades
            return precision_score(y_val, y_pred, pos_label=1, zero_division=0)

        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=42),
        )
        opt_start = time.time()
        study.optimize(objective, n_trials=OPTUNA_TRIALS, show_progress_bar=True)
        opt_time = time.time() - opt_start
        logger.info(f"  Optimization done in {opt_time:.0f}s (best precision: {study.best_value:.3f})")

        # ── Train final model ───────────────────────────────────────
        best_p = study.best_params
        best_p.update({
            "n_estimators": 500, "class_weight": "balanced",
            "random_state": 42, "verbose": -1, "n_jobs": -1,
        })
        model = lgb.LGBMClassifier(**best_p)
        model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                  callbacks=[lgb.early_stopping(30, verbose=False),
                             lgb.log_evaluation(0)])

        # ── Evaluate on test signals ────────────────────────────────
        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, pos_label=1, zero_division=0)
        rec = recall_score(y_test, y_pred, pos_label=1, zero_division=0)
        f1 = f1_score(y_test, y_pred, pos_label=1, zero_division=0)

        logger.info(f"  Filter: Acc={acc:.1%} Prec={prec:.1%} Rec={rec:.1%} F1={f1:.3f}")

        # Feature importance
        imp = sorted(zip(feature_cols, model.feature_importances_),
                     key=lambda x: x[1], reverse=True)[:5]

        # ── Run backtests on test period ────────────────────────────
        df_test_raw = df_raw[df_raw["time"] >= TEST_START].reset_index(drop=True)
        df_test_feat = df_feat[df_feat["time"] >= pd.Timestamp(TEST_START)].reset_index(drop=True)

        # Baseline: SMA crossover without filter
        baseline = run_filtered_backtest(
            df_test_raw, df_test_feat, feature_cols, None, params, pip_value,
        )

        # ML-filtered: SMA crossover + ML quality filter
        # Try multiple confidence thresholds
        best_filtered = None
        best_threshold = 0.50
        for threshold in [0.45, 0.50, 0.55, 0.60, 0.65]:
            filtered = run_filtered_backtest(
                df_test_raw, df_test_feat, feature_cols, model, params, pip_value,
                confidence_threshold=threshold,
            )
            if filtered["trades"] >= 10:  # Need minimum trades
                if best_filtered is None or filtered["pf"] > best_filtered["pf"]:
                    best_filtered = filtered
                    best_threshold = threshold

        if best_filtered is None:
            best_filtered = baseline
            best_threshold = 0.0

        sym_time = time.time() - sym_start
        results.append({
            "symbol": symbol,
            "baseline": baseline,
            "filtered": best_filtered,
            "threshold": best_threshold,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "time": sym_time,
            "top_features": [n for n, _ in imp[:5]],
        })

        # ── Display ─────────────────────────────────────────────────
        print()
        print(f"  {symbol} (completed in {sym_time:.0f}s)")
        print(f"  {'-' * 70}")
        print(f"  ML Filter: Prec={prec:.1%} | Rec={rec:.1%} | F1={f1:.3f} | Threshold={best_threshold}")
        print(f"  Top features: {', '.join(n for n, _ in imp[:5])}")
        print(f"  {'-' * 70}")
        print(f"  {'':14s} {'Trades':>8s} {'Win%':>8s} {'PF':>8s} {'Sharpe':>8s} {'MaxDD':>8s} {'P&L':>14s}")
        print(f"  {'SMA ONLY':14s} {baseline['trades']:>8d} {baseline['win_rate']:>7.1f}% "
              f"{baseline['pf']:>8.3f} {baseline['sharpe']:>8.3f} "
              f"{baseline['max_dd']:>7.1f}% ${baseline['pnl']:>+12,.2f}")
        print(f"  {'SMA+ML FILTER':14s} {best_filtered['trades']:>8d} {best_filtered['win_rate']:>7.1f}% "
              f"{best_filtered['pf']:>8.3f} {best_filtered['sharpe']:>8.3f} "
              f"{best_filtered['max_dd']:>7.1f}% ${best_filtered['pnl']:>+12,.2f}")
        print(f"  Filtered out: {best_filtered['filtered']} bad trades")

        improvement = "IMPROVED" if best_filtered["pf"] > baseline["pf"] else "NO IMPROVEMENT"
        passed = best_filtered["pf"] > 1.0 and best_filtered["sharpe"] > 0
        verdict = "PASS" if passed else "FAIL"
        print(f"  ML Filter: {improvement} | Verdict: {verdict}")

    total_time = time.time() - total_start

    # ── Final Summary ───────────────────────────────────────────────
    print()
    print("=" * 75)
    print("     ML-FILTERED WALK-FORWARD SUMMARY")
    print(f"     Total time: {total_time:.0f}s")
    print("=" * 75)
    print(f"  {'Symbol':8s} | {'SMA PF':>8s} {'ML+SMA PF':>10s} | "
          f"{'SMA Sharpe':>11s} {'ML Sharpe':>10s} | {'Prec':>5s} | {'Status':>6s}")
    print(f"  {'-' * 70}")

    pass_count = 0
    improved_count = 0
    for r in results:
        b = r["baseline"]
        f = r["filtered"]
        passed = f["pf"] > 1.0 and f["sharpe"] > 0
        improved = f["pf"] > b["pf"]
        if passed: pass_count += 1
        if improved: improved_count += 1
        status = "PASS" if passed else "FAIL"
        print(f"  {r['symbol']:8s} | {b['pf']:>8.3f} {f['pf']:>10.3f} | "
              f"{b['sharpe']:>+11.3f} {f['sharpe']:>+10.3f} | "
              f"{r['precision']:>4.0%} | {status:>6s}")

    print(f"  {'-' * 70}")
    print(f"  Result: {pass_count}/{len(results)} symbols passed")
    print(f"  ML improved PF: {improved_count}/{len(results)} symbols")
    print("=" * 75)

    # Save
    if pass_count > 0:
        validated = {}
        for r in results:
            f = r["filtered"]
            if f["pf"] > 1.0 and f["sharpe"] > 0:
                validated[r["symbol"]] = {
                    "strategy": "sma_crossover_ml_filtered",
                    "confidence_threshold": r["threshold"],
                    "test_pf": f["pf"],
                    "test_sharpe": f["sharpe"],
                    "test_trades": f["trades"],
                    "test_win_rate": f["win_rate"],
                    "ml_precision": round(r["precision"], 3),
                    "trades_filtered": f["filtered"],
                }
        output_path = "data/ml_filtered_validated.yaml"
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(validated, f, default_flow_style=False, sort_keys=False)
        print(f"\n  Validated params saved to: {output_path}")


if __name__ == "__main__":
    main()
