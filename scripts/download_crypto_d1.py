"""Phase 10 step 2: download D1 OHLCV for BTC/ETH/SOL/BNB USDT from Binance public.

Output:
  data/raw_crypto/{SAFE_SYMBOL}/D1.parquet  (one per pair)
  data/raw_crypto/data_quality_report.md    (summary + gap analysis)

No API keys used. ccxt handles rate limiting via enableRateLimit=True.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import pandas as pd

PAIRS = {
    "BTC/USDT": {"start": "2017-08-17", "safe": "BTC_USDT"},
    "ETH/USDT": {"start": "2017-08-17", "safe": "ETH_USDT"},
    "BNB/USDT": {"start": "2017-11-06", "safe": "BNB_USDT"},
    "SOL/USDT": {"start": "2020-08-11", "safe": "SOL_USDT"},
}

OUT_ROOT = Path("data/raw_crypto")
OUT_ROOT.mkdir(parents=True, exist_ok=True)

TF = "1d"
LIMIT = 1000  # Binance max per call for D1
DAY_MS = 86_400_000


def to_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def fetch_all(ex: ccxt.Exchange, symbol: str, start_ms: int) -> list[list]:
    """Paginated fetch: keep pulling until we hit 'now' or get an empty page."""
    all_candles: list[list] = []
    since = start_ms
    now_ms = ex.milliseconds()
    page = 0
    while since < now_ms:
        page += 1
        batch = ex.fetch_ohlcv(symbol, timeframe=TF, since=since, limit=LIMIT)
        if not batch:
            break
        all_candles.extend(batch)
        last_ts = batch[-1][0]
        # Advance by one day to avoid refetching the last candle
        since = last_ts + DAY_MS
        print(f"    page {page}: +{len(batch)} candles, last={datetime.fromtimestamp(last_ts/1000, tz=timezone.utc).date()}")
        if len(batch) < LIMIT:
            # Caught up — Binance returned a partial page = we're at the tail
            break
    return all_candles


def to_frame(candles: list[list], symbol: str) -> pd.DataFrame:
    df = pd.DataFrame(candles, columns=["ts_ms", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True).dt.tz_localize(None)
    df["symbol"] = symbol
    df["timeframe"] = TF
    df = df[["symbol", "timeframe", "time", "open", "high", "low", "close", "volume"]]
    df = df.drop_duplicates(subset=["symbol", "timeframe", "time"]).sort_values("time").reset_index(drop=True)
    return df


def gap_analysis(df: pd.DataFrame) -> dict:
    times = df["time"].sort_values().reset_index(drop=True)
    diffs = times.diff().dropna()
    expected = pd.Timedelta(days=1)
    gaps = diffs[diffs > expected]
    gap_details = []
    for i, dur in gaps.items():
        prev = times.iloc[i - 1]
        curr = times.iloc[i]
        missing_days = int(dur.total_seconds() / 86400) - 1
        gap_details.append({
            "after": prev.strftime("%Y-%m-%d"),
            "next": curr.strftime("%Y-%m-%d"),
            "missing_days": missing_days,
        })
    return {
        "n_gaps": len(gaps),
        "max_gap_days": int(gaps.max().total_seconds() / 86400) if len(gaps) else 0,
        "total_missing_days": int(sum(g["missing_days"] for g in gap_details)),
        "details": gap_details,
    }


def main() -> None:
    ex = ccxt.binance({"enableRateLimit": True})
    ex.load_markets()
    print(f"binance markets loaded: {len(ex.markets)}\n")

    summary: dict[str, dict] = {}
    t_total = time.time()
    for sym, cfg in PAIRS.items():
        print(f"--- {sym} (since {cfg['start']}) ---")
        t0 = time.time()
        candles = fetch_all(ex, sym, to_ms(cfg["start"]))
        df = to_frame(candles, sym)

        out_dir = OUT_ROOT / cfg["safe"]
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "D1.parquet"
        df.to_parquet(out_path, index=False)

        gaps = gap_analysis(df)
        elapsed = time.time() - t0
        info = {
            "rows": len(df),
            "first": df["time"].iloc[0].strftime("%Y-%m-%d") if len(df) else None,
            "last": df["time"].iloc[-1].strftime("%Y-%m-%d") if len(df) else None,
            "n_gaps_gt_1d": gaps["n_gaps"],
            "max_gap_days": gaps["max_gap_days"],
            "total_missing_days": gaps["total_missing_days"],
            "gap_details": gaps["details"],
            "out_path": str(out_path).replace("\\", "/"),
            "size_bytes": out_path.stat().st_size,
            "fetch_seconds": round(elapsed, 2),
        }
        summary[sym] = info
        print(f"  {len(df)} rows | {info['first']} -> {info['last']} | {gaps['n_gaps']} gaps | {elapsed:.2f}s")
        print()

    # Write quality report
    lines = [
        "# Crypto D1 Data — Quality Report",
        f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
        f"*Source: Binance public (ccxt {ccxt.__version__})*",
        "",
        "## Summary",
        "",
        "| Symbol | Rows | First date | Last date | Gaps >1d | Max gap | Missing days | File size |",
        "|---|---:|---|---|---:|---:|---:|---:|",
    ]
    for sym, info in summary.items():
        lines.append(
            f"| `{sym}` | {info['rows']:,} | {info['first']} | {info['last']} | "
            f"{info['n_gaps_gt_1d']} | {info['max_gap_days']}d | "
            f"{info['total_missing_days']} | {info['size_bytes']/1024:.1f} KB |"
        )
    lines += ["", "## Gap Details", ""]
    any_gaps = False
    for sym, info in summary.items():
        if info["gap_details"]:
            any_gaps = True
            lines.append(f"### {sym}")
            lines.append("")
            lines.append("| After | Next | Missing days |")
            lines.append("|---|---|---:|")
            for g in info["gap_details"]:
                lines.append(f"| {g['after']} | {g['next']} | {g['missing_days']} |")
            lines.append("")
    if not any_gaps:
        lines.append("_No gaps >1 day detected in any pair._")
        lines.append("")

    lines += [
        "## Notes",
        "",
        "- All timestamps are UTC-naive (tz stripped after conversion to UTC), matching the FX parquet convention in `data/raw/`.",
        "- Columns: `symbol, timeframe, time, open, high, low, close, volume` (volume in base currency — e.g. BTC for BTC/USDT).",
        "- No forward-fill applied. Gaps (if any) are preserved as-is.",
        "- The latest row is the current partial day — its close will change until UTC midnight. Re-run to refresh the tail.",
        "",
    ]
    report = OUT_ROOT / "data_quality_report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"--- done in {time.time()-t_total:.1f}s total ---")
    print(f"Report: {report}")


if __name__ == "__main__":
    main()
