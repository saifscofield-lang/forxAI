"""One-off data-quality audit. Reads every cached parquet, reports coverage,
gaps, columns, and whether tradable-cost info (spread) is present.
Not part of the engine — diagnostic only."""
import sys, os
sys.path.insert(0, ".")
import glob
import pandas as pd
import numpy as np

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)


def find_time_col(df):
    for c in ["time", "Date", "date", "timestamp", "Datetime", "index"]:
        if c in df.columns:
            return c
    return None


def audit_parquet(path):
    df = pd.read_parquet(path)
    cols = list(df.columns)
    tcol = find_time_col(df)
    if tcol is None and isinstance(df.index, pd.DatetimeIndex):
        df = df.reset_index()
        tcol = df.columns[0]
    info = {
        "rows": len(df),
        "cols": ",".join(cols)[:80],
        "has_spread": any("spread" in c.lower() for c in cols),
        "has_volume": any(c.lower() in ("volume", "tick_volume", "real_volume") for c in cols),
    }
    if tcol and len(df):
        t = pd.to_datetime(df[tcol])
        info["start"] = str(t.min())[:10]
        info["end"] = str(t.max())[:10]
        info["years"] = round((t.max() - t.min()).days / 365.25, 1)
        # gap detection: median bar spacing vs large gaps
        dt = t.sort_values().diff().dropna()
        if len(dt):
            med = dt.median()
            big = dt[dt > med * 5]
            info["med_spacing"] = str(med)
            info["n_big_gaps"] = int((dt > med * 10).sum())
            info["max_gap_days"] = round(dt.max().total_seconds() / 86400, 1)
    return info


def section(title):
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)


# ---- FX / gold (MT5) ----
section("FX + GOLD (MT5)  — raw/")
rows = []
for p in sorted(glob.glob("data/raw/*/*.parquet")):
    sym = os.path.basename(os.path.dirname(p))
    tf = os.path.basename(p).replace(".parquet", "")
    try:
        a = audit_parquet(p)
        a.update({"sym": sym, "tf": tf})
        rows.append(a)
    except Exception as e:
        rows.append({"sym": sym, "tf": tf, "rows": f"ERR {e}"})
fx = pd.DataFrame(rows)
# focus on H1 (primary) + D1
for tf in ["H1", "D1", "M15"]:
    sub = fx[fx.tf == tf]
    if len(sub):
        print(f"\n--- {tf} ---")
        print(sub[["sym", "rows", "start", "end", "years", "n_big_gaps", "max_gap_days", "has_spread", "has_volume"]].to_string(index=False))

# ---- trend (yfinance) ----
section("CROSS-ASSET TREND  — raw_trend/  (yfinance)")
rows = []
for p in sorted(glob.glob("data/raw_trend/*.parquet")):
    name = os.path.basename(p).replace(".parquet", "")
    try:
        a = audit_parquet(p)
        a["ticker"] = name
        rows.append(a)
    except Exception as e:
        rows.append({"ticker": name, "rows": f"ERR {e}"})
if rows:
    tr = pd.DataFrame(rows)
    print(tr[["ticker", "rows", "start", "end", "years", "n_big_gaps", "max_gap_days"]].to_string(index=False))

# ---- vol (yfinance) ----
section("VOLATILITY  — raw_vol/  (yfinance)")
rows = []
for p in sorted(glob.glob("data/raw_vol/*.parquet")):
    name = os.path.basename(p).replace(".parquet", "")
    try:
        a = audit_parquet(p)
        a["ticker"] = name
        rows.append(a)
    except Exception as e:
        rows.append({"ticker": name, "rows": f"ERR {e}"})
if rows:
    vol = pd.DataFrame(rows)
    print(vol[["ticker", "rows", "start", "end", "years", "n_big_gaps", "max_gap_days"]].to_string(index=False))

# ---- crypto ----
section("CRYPTO  — raw_crypto/  (Binance)")
rows = []
for p in sorted(glob.glob("data/raw_crypto/*/*.parquet")):
    sym = os.path.basename(os.path.dirname(p))
    try:
        a = audit_parquet(p)
        a["sym"] = sym
        rows.append(a)
    except Exception as e:
        rows.append({"sym": sym, "rows": f"ERR {e}"})
if rows:
    cr = pd.DataFrame(rows)
    print(cr[["sym", "rows", "start", "end", "years", "n_big_gaps", "max_gap_days"]].to_string(index=False))

print("\nDONE")
