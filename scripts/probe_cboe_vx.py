"""Probe v2: retry CBOE VX CDN with FULL browser headers (the 403 is likely
bot-detection on missing Referer/Accept). Diagnostic ONLY — no series build,
no strategy return. Just: does the download work, and what does the CSV look like."""
import sys
import io

sys.path.insert(0, ".")
import urllib.request
import urllib.error

import pandas as pd

BASE = "https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_{}.csv"

# Full browser-like header set to defeat naive bot blocking.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/csv,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.cboe.com/us/futures/market_statistics/historical_data/",
    "Origin": "https://www.cboe.com",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "Connection": "keep-alive",
}

PROBE_DATES = ["2024-01-17", "2018-02-14", "2010-05-19", "2004-05-19"]


def try_fetch(date):
    url = BASE.format(date)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", errors="replace")
        if not raw.strip() or "<html" in raw[:300].lower():
            return f"EMPTY/HTML ({len(raw)} bytes)", None
        df = pd.read_csv(io.StringIO(raw))
        return f"OK rows={len(df)} cols=[{','.join(df.columns)[:70]}]", df
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}", None
    except Exception as e:
        return f"ERR {type(e).__name__}: {e}", None


print("Probe v2 — full browser headers\n")
ok = False
for d in PROBE_DATES:
    status, df = try_fetch(d)
    print(f"  {d} -> {status}")
    if df is not None and not ok:
        ok = True
        dcol = next((c for c in df.columns if "date" in c.lower() or "trade" in c.lower()), None)
        if dcol:
            t = pd.to_datetime(df[dcol], errors="coerce").dropna()
            print(f"        span: {str(t.min())[:10]} .. {str(t.max())[:10]}")
        print(f"        head:\n{df.head(2).to_string()}")

print("\nVERDICT:", "AUTOMATED DOWNLOAD WORKS" if ok else "STILL BLOCKED — manual browser download needed")
