"""Trend-premium SMOKE TEST (pre-pre-registration plumbing check).

NOT the real experiment. Purpose: on 3-5 maximally-different instruments, verify
(a) data quality, (b) result stability, (c) no time-series artifacts, and preview
(d) statistical independence (ENB / PC1 share) — BEFORE committing to a basket or
writing the pre-registration.

Trend rule (canonical TSMOM, NO tuning): monthly rebalanced; position =
sign(trailing 12-month log return), lagged 1 month; vol-scaled to 10% target by
trailing 12-month realized vol; capped at 1x. This is a fixed, public-textbook
rule — chosen before seeing any result, no knobs fit here.

Run:  venv/Scripts/python.exe scripts/trend_smoke_test.py
"""
import sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
import yfinance as yf

# 5 instruments, maximally different asset classes (chosen by class, not by trend history)
TICKERS = {
    "ES=F": "equity_index",
    "CL=F": "energy",
    "GC=F": "metal",
    "ZN=F": "bonds",
    "EURUSD=X": "fx",
}
START = "2001-01-01"
TARGET_VOL = 0.10
LOOKBACK_M = 12
MONTHS_PER_YEAR = 12


def fetch(ticker):
    df = yf.download(ticker, start=START, auto_adjust=True, progress=False)
    if df is None or len(df) == 0:
        return None
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.dropna()


def data_quality(name, daily):
    """Return a dict of data-quality diagnostics on the DAILY series."""
    idx = daily.index
    span_days = (idx[-1] - idx[0]).days
    # business-day coverage
    bdays = pd.bdate_range(idx[0], idx[-1])
    missing_frac = 1 - len(idx.intersection(bdays)) / len(bdays)
    dups = int(idx.duplicated().sum())
    dlog = np.log(daily / daily.shift(1)).dropna()
    extreme = int((dlog.abs() > 0.10).sum())          # >10% daily = possible roll artifact
    # longest stale (constant) run
    stale = (daily.diff() == 0)
    longest_stale = int(stale.groupby((~stale).cumsum()).sum().max() or 0)
    return {
        "rows": len(daily), "start": idx[0].date(), "end": idx[-1].date(),
        "years": round(span_days / 365.25, 1), "missing_bday_%": round(missing_frac * 100, 1),
        "dup_ts": dups, "extreme_>10%_days": extreme, "longest_stale_run": longest_stale,
    }


def monthly_trend_returns(daily):
    """Canonical monthly TSMOM strategy return series (vol-scaled, lagged, capped)."""
    m_close = daily.resample("ME").last().dropna()
    m_logret = np.log(m_close / m_close.shift(1))
    mom = m_logret.rolling(LOOKBACK_M, min_periods=LOOKBACK_M).sum()
    pos = np.sign(mom)
    # vol-scale by trailing realized vol (annualized), capped at 1x leverage
    vol_ann = m_logret.rolling(LOOKBACK_M, min_periods=LOOKBACK_M).std() * np.sqrt(MONTHS_PER_YEAR)
    lev = (TARGET_VOL / vol_ann).clip(upper=1.0)
    pos_prev = (pos * lev).shift(1)          # LAG 1 month — no lookahead
    strat_ret = pos_prev * m_logret          # realised next-month return
    return strat_ret.dropna()


def tstat(x):
    x = np.asarray(x, float)
    if len(x) < 3 or x.std(ddof=1) == 0:
        return 0.0
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))


def main():
    print("=" * 72)
    print("TREND SMOKE TEST — 5 instruments, 5 asset classes")
    print("=" * 72)

    daily_data, strat = {}, {}
    print("\n## (a) DATA QUALITY\n")
    hdr = f"{'instr':10} {'class':13} {'rows':>5} {'years':>6} {'miss%':>6} {'dup':>4} {'>10%d':>6} {'stale':>6}"
    print(hdr)
    for tk, cls in TICKERS.items():
        d = fetch(tk)
        if d is None:
            print(f"{tk:10} {cls:13}  FETCH FAILED")
            continue
        daily_data[tk] = d
        q = data_quality(tk, d)
        print(f"{tk:10} {cls:13} {q['rows']:>5} {q['years']:>6} {q['missing_bday_%']:>6} "
              f"{q['dup_ts']:>4} {q['extreme_>10%_days']:>6} {q['longest_stale_run']:>6}")
        strat[tk] = monthly_trend_returns(d)

    # cross-check yfinance GC=F vs existing MT5 XAUUSD D1
    print("\n## cross-check: yfinance GC=F vs local MT5 XAUUSD (D1)\n")
    try:
        xau = pd.read_parquet("data/raw/XAUUSD/D1.parquet").sort_values("time")
        xau_s = xau.set_index(pd.DatetimeIndex(xau["time"]))["close"].resample("ME").last()
        gc = daily_data["GC=F"].resample("ME").last()
        common = xau_s.index.intersection(gc.index)
        corr = np.corrcoef(xau_s.reindex(common).pct_change().dropna(),
                           gc.reindex(common).pct_change().dropna().reindex(
                               xau_s.reindex(common).pct_change().dropna().index))[0, 1]
        print(f"  monthly-return corr (MT5 XAU vs yfinance GC=F) over {len(common)} months: {corr:.3f}")
        print("  (expect ~0.95+; confirms yfinance gold matches your broker gold)")
    except Exception as e:
        print("  cross-check skipped:", e)

    # align strategy returns on common window
    S = pd.DataFrame(strat).dropna()
    print(f"\n## (b) STABILITY — common window {S.index[0].date()}..{S.index[-1].date()} ({len(S)} months)\n")
    print(f"{'instr':10} {'full_mean%':>11} {'full_t':>7} {'H1_mean%':>9} {'H2_mean%':>9} {'sign_consistent':>16}")
    mid = len(S) // 2
    for tk in S.columns:
        s = S[tk]
        h1, h2 = s.iloc[:mid], s.iloc[mid:]
        consistent = "YES" if np.sign(h1.mean()) == np.sign(h2.mean()) else "no"
        print(f"{tk:10} {s.mean()*100:>11.3f} {tstat(s):>7.2f} {h1.mean()*100:>9.3f} "
              f"{h2.mean()*100:>9.3f} {consistent:>16}")

    # equal-asset-class-weight portfolio (here 1 instr per class, so equal weight)
    port = S.mean(axis=1)
    print(f"\n  equal-weight basket: mean {port.mean()*100:.3f}%/mo  t={tstat(port):.2f}  "
          f"Sharpe(ann) {port.mean()/port.std(ddof=1)*np.sqrt(12):.2f}")

    # (c) artifacts already flagged in data-quality (extreme days / stale). Lookahead: by construction (shift(1)).
    print("\n## (c) ARTIFACTS\n")
    print("  - Lookahead: position lagged 1 month by construction (pos_prev = (pos*lev).shift(1)).")
    print("  - Roll/spike artifacts: see '>10%d' column above (daily |logret|>10%).")
    print("  - Stale data: see 'stale' column (longest constant-price run).")

    # (d) independence preview
    print("\n## (d) INDEPENDENCE PREVIEW (on strategy returns)\n")
    C = S.corr()
    print("correlation matrix (strategy monthly returns):")
    print(C.round(2).to_string())
    eig = np.linalg.eigvalsh(C.values)
    eig = eig[eig > 0]
    enb = (eig.sum() ** 2) / (eig ** 2).sum()
    pc1_share = eig.max() / eig.sum()
    print(f"\n  N instruments         : {S.shape[1]}")
    print(f"  Effective # of bets   : {enb:.2f}   (target >= 0.4*N = {0.4*S.shape[1]:.1f})")
    print(f"  PC1 variance share    : {pc1_share:.2f}   (diversification gate: < 0.50)")
    maxoff = (C.values - np.eye(len(C))).max()
    print(f"  Max pairwise corr     : {maxoff:.2f}   (hard cap: < 0.70)")

    print("\n" + "=" * 72)
    print("SMOKE VERDICT: inspect above — proceed to full basket only if data is")
    print("clean, half-sample signs are mostly consistent, and ENB/PC1 look diversified.")
    print("=" * 72)


if __name__ == "__main__":
    main()
