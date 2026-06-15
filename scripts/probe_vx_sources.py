"""Probe alternative FREE, scraping-friendly sources for a continuous VX
(VIX futures) series in a single file. Diagnostic ONLY — coverage check, no
strategy return. Tries Stooq continuous-futures CSV endpoints."""
import sys
import io

sys.path.insert(0, ".")
import urllib.request
import urllib.error
import pandas as pd

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"}

# Stooq continuous-futures CSV: s=<symbol>, i=d (daily). Try common VIX-futures symbols.
STOOQ = "https://stooq.com/q/d/l/?s={}&i=d"
SYMBOLS = ["vx.f", "vx_f", "^vx", "vi.f", "vxc.f"]


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", errors="replace")
        return raw, None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, f"ERR {type(e).__name__}: {e}"


print("Probing Stooq continuous-futures CSV for VIX futures (VX)\n")
found = False
for sym in SYMBOLS:
    url = STOOQ.format(sym)
    raw, err = fetch(url)
    if err:
        print(f"  {sym:8s} -> {err}")
        continue
    head = raw[:60].replace("\n", " ")
    if raw.strip().lower().startswith("date") or "Date,Open" in raw[:30]:
        try:
            df = pd.read_csv(io.StringIO(raw))
            t = pd.to_datetime(df["Date"], errors="coerce").dropna()
            print(f"  {sym:8s} -> OK rows={len(df)}  span={str(t.min())[:10]}..{str(t.max())[:10]}  cols={list(df.columns)}")
            if len(df) > 100:
                found = True
                print(f"            head:\n{df.head(2).to_string()}")
                print(f"            tail:\n{df.tail(2).to_string()}")
        except Exception as e:
            print(f"  {sym:8s} -> parse ERR {e}; raw head: {head}")
    else:
        # Stooq returns "No data" as plain text for unknown symbols
        print(f"  {sym:8s} -> no data / unexpected: {head}")

print("\nVERDICT:", "FOUND a usable continuous VX series" if found else "Stooq has no clean VX continuous — try other source")
