"""
Label Generation for ML Models.
Creates forward-looking labels from price data.
Labels represent what WILL happen — used as training targets.
"""
import numpy as np
import pandas as pd


def add_labels(
    df: pd.DataFrame,
    horizon: int = 10,
    method: str = "triple_barrier",
    atr_sl_mult: float = 1.5,
    atr_tp_mult: float = 2.5,
    atr_col: str = "atr_14",
    min_return_pct: float = 0.0,
) -> pd.DataFrame:
    """
    Add trading labels to DataFrame.

    Parameters
    ----------
    df : DataFrame with close, high, low, and ATR columns
    horizon : max bars to look forward
    method : 'triple_barrier' or 'fixed_horizon'
    atr_sl_mult : ATR multiplier for stop loss barrier
    atr_tp_mult : ATR multiplier for take profit barrier
    atr_col : name of ATR column to use
    min_return_pct : minimum return to classify as signal (for fixed_horizon)

    Returns
    -------
    DataFrame with 'label' column: 1=BUY, -1=SELL, 0=HOLD
    """
    df = df.copy()

    if method == "triple_barrier":
        df["label"] = _triple_barrier_labels(
            close=df["close"].values,
            high=df["high"].values,
            low=df["low"].values,
            atr=df[atr_col].values,
            horizon=horizon,
            sl_mult=atr_sl_mult,
            tp_mult=atr_tp_mult,
        )
    elif method == "fixed_horizon":
        df["label"] = _fixed_horizon_labels(
            close=df["close"].values,
            horizon=horizon,
            min_return_pct=min_return_pct,
        )
    else:
        raise ValueError(f"Unknown method: {method}")

    # Drop rows with NaN labels (end of series where we can't look forward)
    df.dropna(subset=["label"], inplace=True)
    df["label"] = df["label"].astype(int)
    df.reset_index(drop=True, inplace=True)

    return df


def _triple_barrier_labels(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    atr: np.ndarray,
    horizon: int,
    sl_mult: float,
    tp_mult: float,
) -> np.ndarray:
    """
    Symmetric triple barrier labeling (Lopez de Prado).

    Uses SAME distance for upper and lower barriers to avoid label imbalance.
    barrier_dist = atr * tp_mult (symmetric both sides).

    For each bar, look forward up to `horizon` bars:
    - If upper barrier hit first -> BUY (1)
    - If lower barrier hit first -> SELL (-1)
    - If neither hit within horizon -> HOLD (0)
    """
    n = len(close)
    labels = np.full(n, np.nan)

    for i in range(n):
        if np.isnan(atr[i]) or atr[i] <= 0:
            continue

        entry = close[i]
        barrier = atr[i] * tp_mult  # Symmetric distance
        upper = entry + barrier
        lower = entry - barrier

        end = min(i + horizon + 1, n)
        hit_upper = False
        hit_lower = False
        upper_bar = end
        lower_bar = end

        for j in range(i + 1, end):
            if not hit_upper and high[j] >= upper:
                hit_upper = True
                upper_bar = j
            if not hit_lower and low[j] <= lower:
                hit_lower = True
                lower_bar = j
            if hit_upper and hit_lower:
                break

        if hit_upper and hit_lower:
            if upper_bar <= lower_bar:
                labels[i] = 1
            else:
                labels[i] = -1
        elif hit_upper:
            labels[i] = 1
        elif hit_lower:
            labels[i] = -1
        else:
            labels[i] = 0

    return labels


def _fixed_horizon_labels(
    close: np.ndarray,
    horizon: int,
    min_return_pct: float,
) -> np.ndarray:
    """Simple fixed-horizon labeling: return after N bars."""
    n = len(close)
    labels = np.full(n, np.nan)

    for i in range(n - horizon):
        ret = (close[i + horizon] - close[i]) / close[i] * 100
        if ret > min_return_pct:
            labels[i] = 1
        elif ret < -min_return_pct:
            labels[i] = -1
        else:
            labels[i] = 0

    return labels


def label_distribution(labels: np.ndarray) -> dict:
    """Return label counts and percentages."""
    unique, counts = np.unique(labels[~np.isnan(labels)], return_counts=True)
    total = counts.sum()
    dist = {}
    for u, c in zip(unique, counts):
        name = {1: "BUY", 0: "HOLD", -1: "SELL"}.get(int(u), str(int(u)))
        dist[name] = {"count": int(c), "pct": round(c / total * 100, 1)}
    return dist
