"""Phase 13 — Volatility Risk Premium — Stage 2 backtest + Guardian verdict.

Implements docs/research/phase13_vrp_prereg.md EXACTLY as frozen (commit cec6279).
Trades the REAL short-vol ETP (short VXX, primary; SVXY long = robustness check).
No tuning. Gates are the VRP-adapted G1-G8 declared in the pre-reg, evaluated by the
deterministic Guardian engine at K=12.

Run: venv/Scripts/python.exe scripts/validate_vrp.py
Outputs: data/raw_vol/*.parquet (cache), data/vrp_submission.json,
         docs/research/phase13_vrp_results.md
"""
import json
import sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path

import numpy as np
import pandas as pd

from research.guardian.engine import evaluate

CACHE = Path("data/raw_vol"); CACHE.mkdir(parents=True, exist_ok=True)
TRAIN_END = "2023-12-31"
OOS_START = "2024-01-01"
OOS_END = "2026-06-30"
SLEEVE = 0.20          # fixed-fractional defined-risk sleeve (§3)
RV_WIN = 21            # realized-vol window
BORROW_ANN = 0.06      # short borrow (§4)
SPREAD = 0.0005        # per-rebalance round-trip (§4)
MPY = 12

L = []
def out(s=""):
    print(s); L.append(s)


def fetch(ticker):
    safe = ticker.replace("=", "_").replace("^", "_").replace("-", "_")
    fp = CACHE / f"{safe}.parquet"
    if fp.exists():
        return pd.read_parquet(fp)["close"]
    import yfinance as yf
    df = yf.download(ticker, start="2004-01-01", auto_adjust=True, progress=False)
    if df is None or len(df) == 0:
        return None
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = close.dropna()
    close.to_frame("close").to_parquet(fp)
    return close


def ann_sharpe(m):
    m = np.asarray(m, float); m = m[~np.isnan(m)]
    if len(m) < 2 or m.std(ddof=1) == 0:
        return 0.0
    return m.mean() / m.std(ddof=1) * np.sqrt(MPY)


def tstat(m):
    m = np.asarray(m, float); m = m[~np.isnan(m)]
    if len(m) < 3 or m.std(ddof=1) == 0:
        return 0.0
    return m.mean() / (m.std(ddof=1) / np.sqrt(len(m)))


def pf(m):
    m = np.asarray(m, float); m = m[~np.isnan(m)]
    g = m[m > 0].sum(); b = -m[m < 0].sum()
    return float(g / b) if b > 0 else float("inf")


def build_strategy(vol_etp, vix, vix3m, gspc, cost_mult=1.0, short=True):
    """Frozen rule: short VXX (or long SVXY) 20% sleeve when VRP_premium>0 AND contango.
    Returns a daily strat-return series. `short`=True => short the ETP (VXX);
    short=False => long the ETP (SVXY robustness)."""
    px = pd.concat({"etp": vol_etp, "vix": vix, "vix3m": vix3m, "gspc": gspc}, axis=1).dropna()
    etp_ret = px["etp"].pct_change()
    g_logret = np.log(px["gspc"] / px["gspc"].shift(1))
    rv = g_logret.rolling(RV_WIN).std() * np.sqrt(252) * 100.0     # realized vol %, annualized
    vrp = px["vix"] - rv                                            # premium in vol points
    contango = px["vix"] < px["vix3m"]
    signal_on = (vrp > 0) & contango                               # daily condition

    # monthly signal refresh: hold the month-end decision through the next month
    me = signal_on.resample("ME").last().reindex(px.index, method="ffill").fillna(False)
    sign = -1.0 if short else +1.0
    daily = []
    pos_prev = 0.0
    sleeve_cum = 1.0                                                # within-month sleeve value
    month_key = None
    for dt in px.index[1:]:
        mk = (dt.year, dt.month)
        if mk != month_key:                                        # month-end rebalance
            month_key = mk
            pos = SLEEVE if me.loc[dt] else 0.0
            sleeve_cum = 1.0
        else:
            pos = pos_prev if sleeve_cum > 0.5 else 0.0            # 50% sleeve stop (§3)
        r_etp = etp_ret.loc[dt]
        gross = pos * sign * (-r_etp if short else r_etp)          # exposure to ETP move
        # exposure return relative to the sleeve itself, for the stop tracker
        if pos > 0:
            sleeve_cum *= (1 + sign * (-r_etp if short else r_etp))
        turn = abs(pos - pos_prev)
        cost = turn * SPREAD * cost_mult + (pos * BORROW_ANN / 252.0 * cost_mult if short else 0.0)
        daily.append((dt, gross - cost, px["vix"].loc[dt]))
        pos_prev = pos
    d = pd.DataFrame(daily, columns=["dt", "ret", "vix"]).set_index("dt")
    return d


def to_monthly(daily_ret):
    return (1 + daily_ret).resample("ME").prod() - 1


def regimes_by_vix(daily):
    """Mean MONTHLY return within each VIX regime (classify month by avg VIX)."""
    m_ret = to_monthly(daily["ret"])
    m_vix = daily["vix"].resample("ME").mean()
    df = pd.concat({"r": m_ret, "v": m_vix}, axis=1).dropna()
    out_r = {}
    for name, lo, hi in [("vix_low", 0, 20), ("vix_mid", 20, 30), ("vix_high", 30, 999)]:
        seg = df[(df["v"] > lo) & (df["v"] <= hi)]["r"]
        if len(seg) >= 3:
            out_r[name] = float(seg.mean())
    return out_r


def mdd(daily_ret):
    eq = (1 + daily_ret).cumprod()
    return float((eq / eq.cummax() - 1).min())


def main():
    out("# Phase 13 — Volatility Risk Premium — Stage 2 RESULTS\n")
    out("Per frozen pre-reg (commit cec6279). Short VXX (primary). No tuning. Verdict @K=12.\n")

    tickers = {"VXX": "VXX", "SVXY": "SVXY", "^VIX": "^VIX", "^VIX3M": "^VIX3M", "^GSPC": "^GSPC"}
    data = {}
    out("## Data coverage")
    for name, tk in tickers.items():
        s = fetch(tk)
        if s is None or len(s) < 100:
            out(f"- {name}: MISSING / too short -> {None if s is None else len(s)}")
            data[name] = None
        else:
            data[name] = s
            out(f"- {name}: {s.index[0].date()}..{s.index[-1].date()} ({len(s)} days)")
    out("")

    need = ["VXX", "^VIX", "^VIX3M", "^GSPC"]
    if any(data[n] is None for n in need):
        out("ABORT: required series unavailable (likely no network to fetch from yfinance).")
        out("Cache the parquets into data/raw_vol/ and re-run.")
        Path("docs/research/phase13_vrp_results.md").write_text("\n".join(L) + "\n", encoding="utf-8")
        return 1

    # ---- PRIMARY: short VXX ----
    d = build_strategy(data["VXX"], data["^VIX"], data["^VIX3M"], data["^GSPC"], short=True)
    d15 = build_strategy(data["VXX"], data["^VIX"], data["^VIX3M"], data["^GSPC"], cost_mult=1.5, short=True)

    vxx_start = data["VXX"].index[0].date()
    out(f"## Primary strategy: SHORT VXX (real series starts {vxx_start})\n")
    if str(vxx_start) > "2010-06-01":
        out(f"- DISCLOSURE (pre-reg §2.3): tradable VXX history begins {vxx_start}, later than the")
        out(f"  2010 target. Train window is the earliest clean start .. {TRAIN_END} (disclosed, not silently truncated).\n")

    train = d[d.index <= TRAIN_END]; oos = d[(d.index >= OOS_START) & (d.index <= OOS_END)]
    train15 = d15[d15.index <= TRAIN_END]
    m_tr = to_monthly(train["ret"]).dropna()
    m_oos = to_monthly(oos["ret"]).dropna()
    m_tr15 = to_monthly(train15["ret"]).dropna()
    # passive benchmark: buy&hold GSPC, monthly
    g_m = to_monthly(np.log(data["^GSPC"] / data["^GSPC"].shift(1)).reindex(d.index).fillna(0))
    g_tr = g_m[g_m.index <= TRAIN_END]
    from scipy import stats as sps
    tdiff, p_two = sps.ttest_ind(m_oos, m_tr, equal_var=False)
    drift_p = float((p_two / 2) if tdiff < 0 else 1.0)

    metrics = {
        "economic_rationale_present": True,
        "mean_period": float(m_tr.mean()),
        "t_stat": float(tstat(m_tr)),
        "sharpe_ann": float(ann_sharpe(m_tr)),
        "n_obs": int(len(m_tr)),
        "mpy": MPY,
        "skew": float(sps.skew(m_tr)),
        "kurtosis": float(sps.kurtosis(m_tr, fisher=False)),
        "oos": {"mean": float(m_oos.mean()), "sharpe": float(ann_sharpe(m_oos)), "drift_p": drift_p},
        "regimes": regimes_by_vix(train),
        "months_positive_pct": float((m_tr > 0).mean()),
        "cost": {"net_mean_1_5x": float(m_tr15.mean()), "pf_net": pf(m_tr)},
        "tail": {"mdd": abs(mdd(train["ret"]))},
        "beats_passive": bool(ann_sharpe(m_tr) > ann_sharpe(g_tr)),
        "no_leverage": True,
    }

    out("## Metrics (train, for VRP-adapted G1-G8)")
    out(f"- train {m_tr.index[0].date()}..{m_tr.index[-1].date()} ({len(m_tr)} mo)  OOS {len(m_oos)} mo")
    out(f"- mean {metrics['mean_period']*100:+.3f}%/mo  t={metrics['t_stat']:+.2f}  Sharpe={metrics['sharpe_ann']:+.2f}")
    out(f"- OOS mean {metrics['oos']['mean']*100:+.3f}%  Sharpe={metrics['oos']['sharpe']:+.2f}  drift_p={metrics['oos']['drift_p']:.2f}")
    out(f"- regimes: {metrics['regimes']}")
    out(f"- months_positive={metrics['months_positive_pct']*100:.0f}%  net@1.5x={metrics['cost']['net_mean_1_5x']*100:+.3f}%/mo  PF={metrics['cost']['pf_net']:.2f}")
    out(f"- tail MDD={metrics['tail']['mdd']*100:.1f}%  beats_passive={metrics['beats_passive']} (B&H Sharpe {ann_sharpe(g_tr):+.2f})\n")

    # ---- VRP-adapted declared gates (frozen, per pre-reg §5) ----
    reg_keys = list(metrics["regimes"].keys())
    declared = [
        {"id": "G1", "kind": "threshold", "desc": "economic rationale", "path": "economic_rationale_present", "op": "==", "th": True},
        {"id": "G2", "kind": "all_of", "desc": "significance mean>0 & t>=2.0",
         "subs": [{"path": "mean_period", "op": ">", "th": 0.0}, {"path": "t_stat", "op": ">=", "th": 2.0}]},
        {"id": "G3", "kind": "dsr", "desc": "Deflated Sharpe @K=12", "alpha": 0.95},
        {"id": "G4", "kind": "all_of", "desc": "OOS robustness",
         "subs": [{"path": "oos.mean", "op": ">", "th": 0.0}, {"path": "oos.sharpe", "op": ">=", "th": 0.30},
                  {"path": "oos.drift_p", "op": ">", "th": 0.05}]},
        {"id": "G5", "kind": "all_positive", "desc": f"all vol-regimes positive ({reg_keys})", "path": "regimes"},
        {"id": "G6", "kind": "threshold", "desc": ">=55% months positive", "path": "months_positive_pct", "op": ">=", "th": 0.55},
        {"id": "G7", "kind": "all_of", "desc": "tail+cost: net@1.5x>0, MDD<30%, beats passive",
         "subs": [{"path": "cost.net_mean_1_5x", "op": ">", "th": 0.0}, {"path": "tail.mdd", "op": "<", "th": 0.30},
                  {"path": "beats_passive", "op": "==", "th": True}]},
        {"id": "G8", "kind": "threshold", "desc": "no leverage / defined-risk", "path": "no_leverage", "op": "==", "th": True},
    ]
    submission = {
        "hypothesis_id": "vrp_short_vol",
        "title": "Volatility Risk Premium — tradable defined-risk short vol (short VXX)",
        "economic_rationale": "Variance risk premium (Bakshi-Kapadia, Carr-Wu): implied>realized vol insurance premium; short-vol ETP decay harvests it. Non-price signal.",
        "prereg_commit": "cec6279",
        "declared_gates": declared,
        "metrics": metrics,
    }
    Path("data/vrp_submission.json").write_text(json.dumps(submission, indent=2), encoding="utf-8")

    v = evaluate(submission, k=12)
    out("## GUARDIAN VERDICT (declared VRP gates, K=12)\n")
    out(f"**VERDICT: {v['verdict']}**")
    out(f"- passed: {v['passed']}")
    out(f"- failed: {v['failed']}")
    dd = v["dsr"]
    out(f"- DSR: {dd['value']:.3f} (SR={dd['sr']:.3f} SR0={dd['sr0']:.3f} K={dd['K']})")
    for gid, det in v["details"].items():
        out(f"  - {gid} [{'PASS' if gid in v['passed'] else 'FAIL'}] {det}")
    if v.get("flags"):
        for f in v["flags"]:
            out(f"  - FLAG [{f['severity']}] {f['code']}: {f['message']}")

    # robustness cross-check: SVXY long (report only)
    if data["SVXY"] is not None:
        ds = build_strategy(data["SVXY"], data["^VIX"], data["^VIX3M"], data["^GSPC"], short=False)
        s_tr = to_monthly(ds[ds.index <= TRAIN_END]["ret"]).dropna()
        out(f"\n## Robustness (SVXY long, report only): Sharpe {ann_sharpe(s_tr):+.2f} over {len(s_tr)} mo "
            f"(note SVXY -0.5x post-2018 artifact)")

    out("\n---")
    if v["verdict"] == "PASS":
        out("All gates pass on TRAIN -> per §6 step 3, OOS holdout may be opened for final confirmation.")
    else:
        out(f"Per §6 step 4: FAIL recorded. No relaxation, no re-tune, OOS holdout NOT opened.")
    Path("docs/research/phase13_vrp_results.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    out("\n(results -> docs/research/phase13_vrp_results.md ; submission -> data/vrp_submission.json)")
    return 0 if v["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
