"""Phase 12 — Cross-Asset Trend Premium — DISCOVERY validation run.

Implements docs/research/phase12_trend_premium_prereg.md EXACTLY as frozen
(commit 9fa6ee2). Gates D1-D6 fixed before this run. No tuning, no post-hoc subset.

Run:  venv/Scripts/python.exe scripts/validate_trend_premium.py
Outputs: docs/research/phase12_trend_premium_results.md (+ cached data under data/raw_trend/)
"""
import sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats as sps

# ---- frozen universe (§3.1): class -> instruments, selected by liquidity/class ----
UNIVERSE = {
    "equity":  ["ES=F", "NQ=F", "^GDAXI", "^N225"],
    "bonds":   ["ZN=F", "ZB=F", "ZF=F"],
    "energy":  ["CL=F", "BZ=F", "NG=F", "HO=F"],
    "metals":  ["GC=F", "SI=F", "HG=F", "PL=F"],
    "ag":      ["ZC=F", "ZW=F", "ZS=F", "SB=F", "KC=F"],
    "fx":      ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X"],
    "crypto":  ["BTC-USD", "ETH-USD"],
}
# per-class cost per side, return units (§5)
COST_SIDE = {"equity": 0.0002, "bonds": 0.0001, "energy": 0.0003, "metals": 0.0003,
             "ag": 0.0004, "fx": 0.00007, "crypto": 0.0010}

START = "2000-01-01"
TARGET_VOL = 0.10
LOOKBACK_M = 12
MPY = 12
WINSOR = 0.15           # §5b daily log-return winsorization
MIN_MONTHS = 60         # §3.1 minimum history to enter
CACHE = Path("data/raw_trend"); CACHE.mkdir(parents=True, exist_ok=True)

L = []
def out(s=""):
    print(s); L.append(s)


def fetch(ticker):
    safe = ticker.replace("=", "_").replace("^", "_").replace("-", "_")
    fp = CACHE / f"{safe}.parquet"
    if fp.exists():
        return pd.read_parquet(fp)["close"]
    df = yf.download(ticker, start=START, auto_adjust=True, progress=False)
    if df is None or len(df) == 0:
        return None
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = close.dropna()
    close.to_frame("close").to_parquet(fp)
    return close


def strat_returns(daily):
    """Canonical monthly TSMOM net+gross return series for one instrument."""
    dlog = np.log(daily / daily.shift(1)).clip(-WINSOR, WINSOR)          # §5b winsorize
    m_close = (dlog.cumsum()).resample("ME").last()                     # winsorized cum-log price
    m_log = m_close.diff()
    mom = m_log.rolling(LOOKBACK_M, min_periods=LOOKBACK_M).sum()
    pos = np.sign(mom)
    vol_ann = m_log.rolling(LOOKBACK_M, min_periods=LOOKBACK_M).std() * np.sqrt(MPY)
    lev = (TARGET_VOL / vol_ann).clip(upper=1.0)
    weight = (pos * lev)
    weight_prev = weight.shift(1)                                       # LAG — no lookahead
    gross = weight_prev * m_log
    turnover = (weight - weight_prev).abs()                            # rebalance at month t
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


def main():
    out("# Phase 12 — Cross-Asset Trend Premium — DISCOVERY RESULTS\n")
    out("Per frozen pre-reg (commit 9fa6ee2). Gates fixed before run.\n")

    # ---- build per-instrument strategy returns ----
    inst_net = {}       # ticker -> net monthly strat return series
    inst_cls = {}       # ticker -> class
    bh_asset = {}       # ticker -> asset monthly return (for buy&hold benchmark)
    dropped = []
    out("## Data / inclusion\n")
    for cls, tickers in UNIVERSE.items():
        for tk in tickers:
            d = fetch(tk)
            if d is None or len(d) < 300:
                dropped.append((tk, "no data")); continue
            gross, turn, aret = strat_returns(d)
            cost = turn.fillna(0) * COST_SIDE[cls]
            net = (gross - cost).dropna()
            if len(net) < MIN_MONTHS:
                dropped.append((tk, f"only {len(net)}m")); continue
            inst_net[tk] = net; inst_cls[tk] = cls; bh_asset[tk] = aret
    out(f"- Included: {len(inst_net)} instruments across {len(set(inst_cls.values()))} classes")
    if dropped:
        out(f"- Dropped: {dropped}")

    # ---- equal-asset-CLASS weighted portfolio (§4) ----
    NET = pd.DataFrame(inst_net)
    classes = sorted(set(inst_cls.values()))
    # class monthly return = mean of active instruments in class
    class_ret = {}
    for c in classes:
        cols = [t for t in NET.columns if inst_cls[t] == c]
        class_ret[c] = NET[cols].mean(axis=1)
    CLS = pd.DataFrame(class_ret)
    port = CLS.mean(axis=1).dropna()        # equal class weight
    out(f"- Portfolio window: {port.index[0].date()} .. {port.index[-1].date()} ({len(port)} months)\n")

    # ---- buy & hold benchmark (equal-class-weight long) ----
    BH = pd.DataFrame(bh_asset)
    bh_class = {c: BH[[t for t in BH.columns if inst_cls[t] == c]].mean(axis=1) for c in classes}
    bh_port = pd.DataFrame(bh_class).mean(axis=1).reindex(port.index).dropna()

    out("## Portfolio summary (net of cost)\n")
    out(f"- Mean monthly net : {port.mean()*100:+.4f}%  (t = {tstat(port):+.2f})")
    out(f"- Sharpe (ann)     : {sharpe(port):+.2f}")
    out(f"- Buy&hold Sharpe   : {sharpe(bh_port):+.2f}")
    eq = (1+port).cumprod(); mdd = (eq/eq.cummax()-1).min()
    out(f"- Max drawdown     : {mdd*100:.1f}%\n")

    # ============ GATES ============
    out("## Gates\n")

    # D1 significance
    d1 = (port.mean() > 0) and (tstat(port) >= 2.0)
    out(f"- **D1 Significance** {'PASS' if d1 else 'FAIL'} — mean {port.mean()*100:+.4f}%/mo, t={tstat(port):+.2f} (need >0 & t>=2.0)")

    # D2 OOS hold-out 70/30
    n = len(port); split = int(n*0.70)
    tr, oos = port.iloc[:split], port.iloc[split:]
    # drift: OOS not significantly worse than train (one-sided Welch)
    tstat_diff, p_two = sps.ttest_ind(oos, tr, equal_var=False)
    oos_worse_p = (p_two/2) if tstat_diff < 0 else 1.0   # one-sided p that OOS<train
    d2 = (oos.mean() > 0) and (sharpe(oos) >= 0.30) and (oos_worse_p > 0.05)
    out(f"- **D2 OOS hold-out** {'PASS' if d2 else 'FAIL'} — OOS({oos.index[0].date()}..) mean {oos.mean()*100:+.4f}%, "
        f"Sharpe {sharpe(oos):+.2f} (need>0 & >=0.30); drift p(OOS<train)={oos_worse_p:.2f} (need>0.05) | train Sharpe {sharpe(tr):+.2f}")

    # D3 regime: both halves + two macro eras all net positive
    mid = n//2
    h1, h2 = port.iloc[:mid], port.iloc[mid:]
    era1 = port[port.index < "2015-01-01"]; era2 = port[port.index >= "2015-01-01"]
    halves_ok = (h1.mean() > 0) and (h2.mean() > 0)
    eras_ok = (era1.mean() > 0) and (era2.mean() > 0)
    d3 = halves_ok and eras_ok
    out(f"- **D3 Regime** {'PASS' if d3 else 'FAIL'} — halves {h1.mean()*100:+.3f}/{h2.mean()*100:+.3f}; "
        f"eras pre2015 {era1.mean()*100:+.3f} / 2015+ {era2.mean()*100:+.3f} (all must be >0)")

    # D4 breadth: >=4/7 classes positive net premium full sample
    cls_pos = {c: CLS[c].mean() for c in classes}
    n_pos = sum(1 for c in classes if cls_pos[c] > 0)
    d4 = n_pos >= 4
    out(f"- **D4 Breadth** {'PASS' if d4 else 'FAIL'} — {n_pos}/{len(classes)} classes net-positive (need >=4)")
    out("    " + " ".join(f"{c}:{cls_pos[c]*100:+.3f}%" for c in classes))

    # D5 diversification validity on instrument strategy returns
    R = NET.dropna()
    C = R.corr().values
    eig = np.linalg.eigvalsh(C); eig = eig[eig > 1e-9]
    enb = (eig.sum()**2)/(eig**2).sum(); pc1 = eig.max()/eig.sum()
    maxoff = (C - np.eye(len(C))).max()
    Ninst = R.shape[1]
    d5 = (enb >= 0.4*Ninst) and (pc1 < 0.50) and (maxoff < 0.70)
    out(f"- **D5 Diversification** {'PASS' if d5 else 'FAIL'} — ENB {enb:.2f} (need>={0.4*Ninst:.1f}), "
        f"PC1 {pc1:.2f} (need<0.50), max|corr| {maxoff:.2f} (need<0.70) over {Ninst} instr")

    # D6 cost stress 1.5x + beats passive
    # recompute net at 1.5x cost
    net15 = {}
    for tk in inst_net:
        d = fetch(tk); gross, turn, _ = strat_returns(d)
        cost = turn.fillna(0) * COST_SIDE[inst_cls[tk]] * 1.5
        net15[tk] = (gross - cost).dropna()
    NET15 = pd.DataFrame(net15)
    cls15 = {c: NET15[[t for t in NET15.columns if inst_cls[t]==c]].mean(axis=1) for c in classes}
    port15 = pd.DataFrame(cls15).mean(axis=1).reindex(port.index).dropna()
    beats = sharpe(port) > sharpe(bh_port)
    d6 = (port15.mean() > 0) and beats
    out(f"- **D6 Cost+passive** {'PASS' if d6 else 'FAIL'} — net@1.5x {port15.mean()*100:+.4f}%/mo (need>0); "
        f"trend Sharpe {sharpe(port):+.2f} vs B&H {sharpe(bh_port):+.2f} (must beat)")

    gates = {"D1": d1, "D2": d2, "D3": d3, "D4": d4, "D5": d5, "D6": d6}
    npass = sum(gates.values())
    allp = all(gates.values())
    out(f"\n## VERDICT: {npass}/6 gates — {'PASS (proceed to Execution layer)' if allp else 'FAIL'}\n")
    if not allp:
        out(f"Failed: {[k for k,v in gates.items() if not v]}. Per §10: no gate relaxation, no re-tuning.")
        out("Per §8 matrix (Discovery FAIL): direction-level result — the most-evidenced premise")
        out("fails even on the broadest powered universe. Systematic alpha on accessible instruments")
        out("under review; pivot the goal rather than add another price hypothesis.")

    Path("docs/research/phase12_trend_premium_results.md").write_text("\n".join(L)+"\n", encoding="utf-8")
    out("\n(written to docs/research/phase12_trend_premium_results.md)")


if __name__ == "__main__":
    main()
