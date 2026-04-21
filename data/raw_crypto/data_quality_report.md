# Crypto D1 Data — Quality Report
*Generated: 2026-04-21 17:07 UTC*
*Source: Binance public (ccxt 4.5.50)*

## Summary

| Symbol | Rows | First date | Last date | Gaps >1d | Max gap | Missing days | File size |
|---|---:|---|---|---:|---:|---:|---:|
| `BTC/USDT` | 3,170 | 2017-08-17 | 2026-04-21 | 0 | 0d | 0 | 146.0 KB |
| `ETH/USDT` | 3,170 | 2017-08-17 | 2026-04-21 | 0 | 0d | 0 | 139.2 KB |
| `BNB/USDT` | 3,089 | 2017-11-06 | 2026-04-21 | 0 | 0d | 0 | 132.4 KB |
| `SOL/USDT` | 2,080 | 2020-08-11 | 2026-04-21 | 0 | 0d | 0 | 91.7 KB |

## Gap Details

_No gaps >1 day detected in any pair._

## Notes

- All timestamps are UTC-naive (tz stripped after conversion to UTC), matching the FX parquet convention in `data/raw/`.
- Columns: `symbol, timeframe, time, open, high, low, close, volume` (volume in base currency — e.g. BTC for BTC/USDT).
- No forward-fill applied. Gaps (if any) are preserved as-is.
- The latest row is the current partial day — its close will change until UTC midnight. Re-run to refresh the tail.
