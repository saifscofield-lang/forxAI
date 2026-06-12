"""Phase 12b — Cross-Asset Trend Premium (CORRECTED re-test) — validation run.

Implements docs/research/phase12b_trend_prereg.md as frozen (commit d7b2910).
Differences from Phase 12 (validate_trend_premium.py):
  - UNIVERSE pruned ex-ante to remove within-class duplicates (one per sub-cluster
    by liquidity): drop NQ=F, ZB=F, ZF=F, BZ=F, GBPUSD=X. See §2.1.
    NOTE: the frozen prose says "20 instruments / removes 6" but the explicitly
    NAMED drops total 5 -> 21 instruments. We implement the named drops (the
    substantive, lowest-discretion content) and flag the arithmetic slip. GDAXI/
    N225 are distinct markets, NOT within-class duplicates, so they are KEPT.
  - GATES are the canonical G1-G8 (max-corr is NO LONGER a hard result gate; it is
    a construction diagnostic only). The verdict is computed by the trusted Guardian
    engine via scripts/guardian_assess.py — this script only produces the metrics.
  - Windows: train 2001-01..2024-06 (in-sample gates); OOS 2024-07..2026-06 (G4).

Run:  venv/Scripts/python.exe scripts/validate_trend_premium_12b.py
Outputs: data/phase12b_submission_real.json (metrics for guardian_assess.py)
         docs/research/phase12b_trend_results.md (human-readable)
"""
import json
import sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

# ---- Phase 12b pruned universe (§2.1): within-class duplicates removed ex-ante ----
# Phase 12 had 26; we drop NQ=F, ZB=F, ZF=F, BZ=F, GBPUSD=X by liquidity -> 21.
UNIVERSE = {
    "equity":  ["ES=F", "^GDAXI", "^N225"],          # drop NQ=F (corr>=0.84 w/ ES)
    "bonds":   ["ZN=F"],                              # drop ZB=F, ZF=F (US-curve dups)
    "energy":  ["CL=F", "NG=F", "HO=F"],              # drop BZ=F (Brent~WTI 0.93)
    "metals":  ["GC=F", "SI=F", "HG=F", "PL=F"],
    "ag":      ["ZC=F", "ZW=F", "ZS=F", "SB=F", "KC=F"],
    "fx":      ["EURUSD=X", "USDJPY=X", "AUDUSD=X"],  # drop GBPUSD=X (~EUR 0.74)
    "crypto":  ["BTC-USD", "ETH-USD"],
}
COST_SIDE = {"equity": 0.0002, "bonds": 0.0001, "energy": 0.0003, "metals": 0.0003,
             "ag": 0.0004, "fx": 0.00007, "crypto": 0.0010}

TRAIN_END = "2024-06-30"
OOS_START = "2024-07-01"
OOS_END   = "2026-06-30"
TARGET_VOL = 0.10
LOOKBACK_M = 12
MPY = 12
WINSOR = 0.15
MIN_MONTHS = 60
CACHE = Path("data/raw_trend")

L = []
def out(s=""):
    print(s); L.append(s)


def fetch(ticker):
    """Phase 12b reads ONLY the cached Phase 12 parquet — no new download (frozen data)."""
    safe = ticker.replace("=", "_").replace("^", "_").replace("-", "_")
    fp = CACHE / f"{safe}.parquet"
    if fp.exists():
        return pd.read_parquet(fp)["close"]
    return None


def strat_returns(daily):
    dlog = np.log(daily / daily.shift(1)).clip(-WINSOR, WINSOR)
    m_close = (dlog.cumsum()).resample("ME").last()
    m_log = m_close.diff()
    mom = m_log.rolling(LOOKBACK_M, min_periods=LOOKBACK_M).sum()
    pos = np.sign(mom)
    vol_ann = m_log.rolling(LOOKBACK_M, min_periods=LOOKBACK_M).std() * np.sqrt(MPY)
    lev = (TARGET_VOL / vol_ann).clip(upper=1.0)
    weight = (pos * lev)
    weight_prev = weight.shift(1)
    gross = weight_prev * m_log
    turnover = (weight - weight_prev).abs()
    return gross.rename("gross"), turnover.rename("turn"), m_log.rename("asset_ret")


def tstat(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    if len(x) < 3 or x.std(ddof=1) == 0:
        return 0.0
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))


def sharpe(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    if len(x) < 2 or x.std(ddof=1) == 0:
        return 0.0
    return x.mean() / x.std(ddof=1) * np.sqrt(MPY)


def pf(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    g = x[x > 0].sum(); b = -x[x < 0].sum()
    return float(g / b) if b > 0 else float("inf")


def main():
    out("# Phase 12b — Cross-Asset Trend Premium (CORRECTED re-test) — RESULTS\n")
    out("Per frozen pre-reg (commit d7b2910). Pruned 21-instrument universe, canonical G1-G8.")
    out("Verdict computed separately by scripts/guardian_assess.py (deterministic engine).\n")

    inst_net, inst_cls, bh_asset, net15 = {}, {}, {}, {}
    dropped = []
    for cls, tickers in UNIVERSE.items():
        for tk in tickers:
            d = fetch(tk)
            if d is None or len(d) < 300:
                dropped.append((tk, "no cached data")); continue
            gross, turn, aret = strat_returns(d)
            net = (gross - turn.fillna(0) * COST_SIDE[cls]).dropna()
            if len(net) < MIN_MONTHS:
                dropped.append((tk, f"only {len(net)}m")); continue
            inst_net[tk] = net; inst_cls[tk] = cls; bh_asset[tk] = aret
            net15[tk] = (gross - turn.fillna(0) * COST_SIDE[cls] * 1.5).dropna()
    out(f"## Universe\n- Included: {len(inst_net)} instruments / {len(set(inst_cls.values()))} classes")
    if dropped:
        out(f"- Dropped (no data): {dropped}")

    NET = pd.DataFrame(inst_net)
    classes = sorted(set(inst_cls.values()))
    def class_frame(df):
        return pd.DataFrame({c: df[[t for t in df.columns if inst_cls[t] == c]].mean(axis=1) for c in classes})
    CLS = class_frame(NET)
    port_full = CLS.mean(axis=1).dropna()

    # windows
    train = port_full[port_full.index <= TRAIN_END]
    oos = port_full[(port_full.index >= OOS_START) & (port_full.index <= OOS_END)]
    out(f"- Train: {train.index[0].date()}..{train.index[-1].date()} ({len(train)} mo)")
    out(f"- OOS  : {oos.index[0].date()}..{oos.index[-1].date()} ({len(oos)} mo)\n")

    # buy&hold (equal class) on train for beats_passive
    BH = pd.DataFrame(bh_asset)
    bh_port = class_frame(BH).mean(axis=1).reindex(port_full.index)
    bh_train = bh_port[bh_port.index <= TRAIN_END].dropna()

    # 1.5x cost portfolio (train)
    NET15 = pd.DataFrame(net15)
    port15_full = class_frame(NET15).mean(axis=1).dropna()
    port15_train = port15_full[port15_full.index <= TRAIN_END]

    # regimes on train (G5: all positive)
    mid = len(train) // 2
    h1, h2 = train.iloc[:mid], train.iloc[mid:]
    era1 = train[train.index < "2015-01-01"]; era2 = train[train.index >= "2015-01-01"]

    # breadth on train (G6)
    CLS_train = CLS[CLS.index <= TRAIN_END]
    cls_pos = {c: float(CLS_train[c].mean()) for c in classes}
    n_pos = sum(1 for c in classes if cls_pos[c] > 0)

    # diversification on train instrument strat returns (G8)
    R = NET[NET.index <= TRAIN_END].dropna()
    C = R.corr().values
    eig = np.linalg.eigvalsh(C); eig = eig[eig > 1e-9]
    enb = float((eig.sum()**2)/(eig**2).sum()); pc1 = float(eig.max()/eig.sum())
    maxoff = float((C - np.eye(len(C))).max()); Ninst = R.shape[1]

    # OOS drift (G4): one-sided p(OOS < train)
    tdiff, p_two = sps.ttest_ind(oos, train, equal_var=False)
    drift_p = float((p_two/2) if tdiff < 0 else 1.0)

    metrics = {
        "mean_period": float(train.mean()),
        "t_stat": float(tstat(train)),
        "sharpe_ann": float(sharpe(train)),
        "n_obs": int(len(train)),
        "mpy": MPY,
        "skew": float(sps.skew(train.dropna())),
        "kurtosis": float(sps.kurtosis(train.dropna(), fisher=False)),
        "oos": {"mean": float(oos.mean()), "sharpe": float(sharpe(oos)), "drift_p": drift_p},
        "regimes": {"half1": float(h1.mean()), "half2": float(h2.mean()),
                    "era_pre2015": float(era1.mean()), "era_2015plus": float(era2.mean())},
        "breadth": {"n_positive": int(n_pos), "n_total": len(classes)},
        "cost": {"net_mean_1x": float(train.mean()), "net_mean_1_5x": float(port15_train.mean()),
                 "pf_net": pf(train)},
        "diversification": {"enb": round(enb, 2), "pc1": round(pc1, 2),
                            "max_corr": round(maxoff, 2), "n_instruments": Ninst},
        "beats_passive": bool(sharpe(train) > sharpe(bh_train)),
    }

    out("## Metrics (train window, for canonical G1-G8)\n")
    out(f"- mean {metrics['mean_period']*100:+.4f}%/mo  t={metrics['t_stat']:+.2f}  Sharpe={metrics['sharpe_ann']:+.2f}  n={metrics['n_obs']}")
    out(f"- OOS  mean {metrics['oos']['mean']*100:+.4f}%  Sharpe={metrics['oos']['sharpe']:+.2f}  drift_p={metrics['oos']['drift_p']:.2f}")
    out(f"- regimes: " + " ".join(f"{k}:{v*100:+.3f}%" for k,v in metrics['regimes'].items()))
    out(f"- breadth: {n_pos}/{len(classes)} classes positive  [" + " ".join(f"{c}:{cls_pos[c]*100:+.3f}" for c in classes) + "]")
    out(f"- cost: net@1.5x {metrics['cost']['net_mean_1_5x']*100:+.4f}%/mo  PF={metrics['cost']['pf_net']:.2f}  beats_passive={metrics['beats_passive']} (B&H Sharpe {sharpe(bh_train):+.2f})")
    out(f"- diversification: ENB {enb:.2f}/{Ninst}  PC1 {pc1:.2f}  max|corr| {maxoff:.2f} (diagnostic only)\n")

    submission = {
        "meta": {
            "hypothesis_id": "phase12b_trend",
            "title": "Cross-asset trend premium (TSMOM) — corrected re-test (21-instr pruned, canonical G1-G8)",
            "economic_rationale": "Documented cross-asset trend/momentum risk premium (Moskowitz, Ooi, Pedersen 2012); time-series momentum across diversified asset classes earns a return not explained by conventional risk. Within-class duplicates pruned ex-ante by liquidity; canonical gates omit max-corr as a result gate.",
            "prereg_commit": "d7b2910",
        },
        "metrics": metrics,
    }
    Path("data/phase12b_submission_real.json").write_text(json.dumps(submission, indent=2), encoding="utf-8")
    Path("docs/research/phase12b_trend_results.md").write_text("\n".join(L)+"\n", encoding="utf-8")
    out("(metrics -> data/phase12b_submission_real.json ; report -> docs/research/phase12b_trend_results.md)")
    out("\nNEXT: venv/Scripts/python.exe scripts/guardian_assess.py data/phase12b_submission_real.json")


if __name__ == "__main__":
    main()
