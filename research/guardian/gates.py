"""Guardian gate primitives — pure, deterministic.

Each gate kind is a function (metrics, spec) -> (passed: bool, detail: str).
No I/O, no randomness, no LLM. See docs/research/guardian_gate_spec.md.
"""
from __future__ import annotations

import math
from typing import Any

# Euler-Mascheroni constant (DSR expected-max-Sharpe).
GAMMA = 0.5772156649015329


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def get_path(metrics: dict, path: str) -> Any:
    """Fetch a dotted path (e.g. 'diversification.enb'). Returns _MISSING if absent."""
    cur: Any = metrics
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur


_MISSING = object()

_OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
}


def _cmp(value: Any, op: str, th: float) -> bool:
    if value is _MISSING or value is None:
        return False
    return _OPS[op](value, th)


# --------------------------------------------------------------------------- #
# Deflated Sharpe Ratio  (the multiple-testing gate)
# --------------------------------------------------------------------------- #
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Inverse normal CDF (Acklam's rational approximation). p in (0,1)."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def expected_max_sharpe(k: int, sr_var: float) -> float:
    """Expected maximum per-period Sharpe under K independent trials (Lopez de Prado)."""
    k = max(int(k), 1)
    if k == 1:
        return 0.0
    z1 = _norm_ppf(1.0 - 1.0 / k)
    z2 = _norm_ppf(1.0 - 1.0 / (k * math.e))
    return math.sqrt(max(sr_var, 0.0)) * ((1.0 - GAMMA) * z1 + GAMMA * z2)


def deflated_sharpe(metrics: dict, k: int) -> dict:
    """Deflated Sharpe Ratio. Returns {value, sr, sr0, K, var}. value=Prob(true SR>SR0)."""
    mpy = metrics.get("mpy", 12) or 12
    sr_ann = metrics.get("sharpe_ann", 0.0) or 0.0
    sr = sr_ann / math.sqrt(mpy)                       # per-period Sharpe
    n = max(int(metrics.get("n_obs", 0) or 0), 2)
    skew = metrics.get("skew", 0.0) or 0.0
    kurt = metrics.get("kurtosis", 3.0) or 3.0

    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    denom = max(denom, 1e-9)
    sr_var = denom / (n - 1)                            # estimator-variance proxy (spec §4)
    sr0 = expected_max_sharpe(k, sr_var)

    stat = (sr - sr0) * math.sqrt(n - 1) / math.sqrt(denom)
    return {"value": _norm_cdf(stat), "sr": sr, "sr0": sr0, "K": k, "var": sr_var}


# --------------------------------------------------------------------------- #
# gate kinds
# --------------------------------------------------------------------------- #
def gate_threshold(metrics, spec):
    v = get_path(metrics, spec["path"])
    if v is _MISSING:
        return False, f"{spec['path']} missing"
    ok = _cmp(v, spec["op"], spec["th"])
    return ok, f"{spec['path']}={_fmt(v)} {spec['op']} {spec['th']} -> {ok}"


def gate_all_of(metrics, spec):
    parts, ok_all = [], True
    for sub in spec["subs"]:
        v = get_path(metrics, sub["path"])
        ok = _cmp(v, sub["op"], sub["th"])
        ok_all &= ok
        parts.append(f"{sub['path']}={_fmt(v)}{sub['op']}{sub['th']}:{'Y' if ok else 'N'}")
    return ok_all, " & ".join(parts)


def gate_any_of(metrics, spec):
    parts, ok_any = [], False
    for sub in spec["subs"]:
        v = get_path(metrics, sub["path"])
        ok = _cmp(v, sub["op"], sub["th"])
        ok_any |= ok
        parts.append(f"{sub['path']}={_fmt(v)}{sub['op']}{sub['th']}:{'Y' if ok else 'N'}")
    return ok_any, " | ".join(parts)


def gate_all_positive(metrics, spec):
    d = get_path(metrics, spec["path"])
    if d is _MISSING or not isinstance(d, dict) or not d:
        return False, f"{spec['path']} missing/empty"
    items = {k: float(v) for k, v in d.items()}
    ok = all(v > 0 for v in items.values())
    detail = ", ".join(f"{k}:{_fmt(v)}" for k, v in items.items())
    return ok, f"all>0? {ok} [{detail}]"


def gate_n_positive(metrics, spec):
    d = get_path(metrics, spec["path"])
    th = spec["th"]
    if d is _MISSING or not isinstance(d, dict):
        return False, f"{spec['path']} missing"
    npos = sum(1 for v in d.values() if float(v) > 0)
    return npos >= th, f"{npos} positive (need >={th})"


def gate_dsr(metrics, spec, k):
    alpha = spec.get("alpha", 0.95)
    d = deflated_sharpe(metrics, k)
    ok = d["value"] >= alpha
    return ok, (f"DSR={d['value']:.3f} (need>={alpha}) | SR={d['sr']:.3f} "
                f"SR0={d['sr0']:.3f} K={d['K']}"), d


_KINDS = {
    "threshold": gate_threshold,
    "all_of": gate_all_of,
    "any_of": gate_any_of,
    "all_positive": gate_all_positive,
    "n_positive": gate_n_positive,
}


def evaluate_gate(metrics: dict, spec: dict, k: int):
    """Dispatch one declared gate. Returns (passed, detail, extra|None)."""
    kind = spec["kind"]
    if kind == "dsr":
        return gate_dsr(metrics, spec, k)
    if kind not in _KINDS:
        return False, f"unknown gate kind '{kind}'", None
    passed, detail = _KINDS[kind](metrics, spec)
    return passed, detail, None


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)
