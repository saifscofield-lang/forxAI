"""
GPU-accelerated indicator computation using CuPy.
Computes indicators for multiple parameter sets in batch on the GPU.
"""
try:
    import cupy as cp
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False

import numpy as np


def _ewm_gpu(data: cp.ndarray, alpha: float, min_periods: int) -> cp.ndarray:
    """Exponential weighted mean on GPU (sequential, but data transfer is fast)."""
    n = len(data)
    out = cp.empty(n, dtype=cp.float64)
    out[:min_periods - 1] = cp.nan

    # Initialize
    valid = data[~cp.isnan(data[:min_periods])]
    if len(valid) == 0:
        return cp.full(n, cp.nan)
    out[min_periods - 1] = valid.mean()

    for i in range(min_periods, n):
        out[i] = alpha * data[i] + (1 - alpha) * out[i - 1]

    return out


def compute_sma_gpu(close: cp.ndarray, period: int) -> cp.ndarray:
    """Simple Moving Average on GPU using cumsum trick."""
    n = len(close)
    out = cp.full(n, cp.nan)
    cumsum = cp.cumsum(close)
    out[period - 1:] = (cumsum[period - 1:] - cp.concatenate([cp.array([0.0]), cumsum[:-period]])) / period
    return out


def compute_rsi_gpu(close: cp.ndarray, period: int) -> cp.ndarray:
    """RSI on GPU."""
    delta = cp.diff(close, prepend=close[0])
    delta[0] = 0

    gain = cp.where(delta > 0, delta, 0.0)
    loss = cp.where(delta < 0, -delta, 0.0)

    alpha = 1.0 / period
    avg_gain = _ewm_gpu(gain, alpha, period)
    avg_loss = _ewm_gpu(loss, alpha, period)

    rs = avg_gain / cp.where(avg_loss == 0, cp.nan, avg_loss)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def compute_atr_gpu(high: cp.ndarray, low: cp.ndarray, close: cp.ndarray, period: int) -> cp.ndarray:
    """ATR on GPU."""
    prev_close = cp.roll(close, 1)
    prev_close[0] = close[0]

    tr1 = high - low
    tr2 = cp.abs(high - prev_close)
    tr3 = cp.abs(low - prev_close)

    true_range = cp.maximum(cp.maximum(tr1, tr2), tr3)

    alpha = 1.0 / period
    atr = _ewm_gpu(true_range, alpha, period)
    return atr


def compute_all_gpu(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    fast_period: int,
    slow_period: int,
    rsi_period: int,
    atr_period: int,
) -> dict[str, np.ndarray]:
    """
    Compute all indicators on GPU for one parameter set.
    Returns numpy arrays (moved back from GPU).
    """
    if not GPU_AVAILABLE:
        raise RuntimeError("CuPy not installed — GPU not available")

    # Transfer to GPU
    close_gpu = cp.asarray(close, dtype=cp.float64)
    high_gpu = cp.asarray(high, dtype=cp.float64)
    low_gpu = cp.asarray(low, dtype=cp.float64)

    # Compute on GPU
    sma_fast = compute_sma_gpu(close_gpu, fast_period)
    sma_slow = compute_sma_gpu(close_gpu, slow_period)
    rsi = compute_rsi_gpu(close_gpu, rsi_period)
    atr = compute_atr_gpu(high_gpu, low_gpu, close_gpu, atr_period)

    # Transfer back to CPU
    return {
        "sma_fast": cp.asnumpy(sma_fast),
        "sma_slow": cp.asnumpy(sma_slow),
        "rsi": cp.asnumpy(rsi),
        "atr": cp.asnumpy(atr),
    }


def batch_compute_indicators_gpu(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    param_sets: list[dict],
) -> list[dict[str, np.ndarray]]:
    """
    Compute indicators for multiple parameter sets using GPU.
    Each param_set: {fast_period, slow_period, rsi_period, atr_period}
    """
    results = []

    # Transfer data to GPU once
    if GPU_AVAILABLE:
        close_gpu = cp.asarray(close, dtype=cp.float64)
        high_gpu = cp.asarray(high, dtype=cp.float64)
        low_gpu = cp.asarray(low, dtype=cp.float64)
    else:
        raise RuntimeError("CuPy not installed — GPU not available")

    # Cache computed indicators to avoid recomputation
    sma_cache = {}
    rsi_cache = {}
    atr_cache = {}

    for params in param_sets:
        fp = params["fast_period"]
        sp = params["slow_period"]
        rp = params["rsi_period"]
        ap = params["atr_period"]

        if fp not in sma_cache:
            sma_cache[fp] = cp.asnumpy(compute_sma_gpu(close_gpu, fp))
        if sp not in sma_cache:
            sma_cache[sp] = cp.asnumpy(compute_sma_gpu(close_gpu, sp))
        if rp not in rsi_cache:
            rsi_cache[rp] = cp.asnumpy(compute_rsi_gpu(close_gpu, rp))
        if ap not in atr_cache:
            atr_cache[ap] = cp.asnumpy(compute_atr_gpu(high_gpu, low_gpu, close_gpu, ap))

        results.append({
            "sma_fast": sma_cache[fp],
            "sma_slow": sma_cache[sp],
            "rsi": rsi_cache[rp],
            "atr": atr_cache[ap],
        })

    return results
