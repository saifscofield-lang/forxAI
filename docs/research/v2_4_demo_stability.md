# v2.4 Demo Stability Report

*Generated: 2026-04-22 14:54 UTC*
*Scope: STABLE segment, 2026-04-10 → latest*
*Purpose: Input for 2026-04-28 v3.0 Go/No-Go meeting*

## Verdict

🔴 **RED** — Critical issues present. v3.0 paper trading cannot start until resolved.

### Flags

- **[CRITICAL]** Account-snapshot weekday gap 9.2h on Thu 2026-04-16 21:05 → Fri 06:16 UTC
- **[CRITICAL]** Account-snapshot weekday gap 6.2h on Tue 2026-04-21 07:05 → Tue 13:15 UTC
- **[CRITICAL]** Shadow-signals pipeline silent for 141 hours (last record 2026-04-16 18:05 UTC). This is the training data source for v3.0 — feed must be restored before Phase 8 (v3.0 paper).
- **[WARN]** Scan-loop weekday gap 9.2h on Thu 2026-04-16 21:05 → 06:16 UTC (2 weekday scan gap(s) >=3h total)

## Headline Numbers

| Item | Value |
|---|---|
| Scope | 2026-04-10 → 2026-04-22 14:05 UTC |
| Account snapshots | 197 rows across 11 days |
| Last snapshot | 2026-04-22 14:05 UTC |
| Weekday gaps in snapshots (>1h, non-weekend) | 2 |
| Trades (total / closed / open) | 89 / 88 / 1 |
| Win rate (closed) | 67.0% |
| Net PnL (closed) | $-615.16 |
| Signals logged | 130 |
| Shadow-signal pipeline | 236 total rows, last at 2026-04-16 18:05 UTC |
| Shadow (STABLE-tagged) | 109 rows |
| Circuit-breaker fires | 0 |
| Scan logs | 197 rows |
| Weekday gaps in scan loop (>30m, non-weekend) | 2 |

## Snapshot Gaps (all non-weekend gaps >1h)

| Previous | Current | Gap (h) |
|---|---|---:|
| Thu 2026-04-16 21:05 | Fri 2026-04-17 06:16 | 9.19 |
| Tue 2026-04-21 07:05 | Tue 2026-04-21 13:15 | 6.16 |

## Daily Cadence

| Date | Snapshots | Scans | Signals | Trades Opened |
|---|---:|---:|---:|---:|
| 2026-04-10 | 23 | 23 | 14 | 11 |
| 2026-04-12 | 2 | 2 | 0 | 0 |
| 2026-04-13 | 24 | 24 | 23 | 15 |
| 2026-04-14 | 25 | 25 | 19 | 10 |
| 2026-04-15 | 24 | 24 | 14 | 9 |
| 2026-04-16 | 23 | 23 | 6 | 5 |
| 2026-04-17 | 16 | 16 | 10 | 8 |
| 2026-04-19 | 2 | 2 | 0 | 0 |
| 2026-04-20 | 24 | 24 | 13 | 10 |
| 2026-04-21 | 19 | 19 | 26 | 17 |
| 2026-04-22 | 15 | 15 | 5 | 4 |

## Engine Version Purity (should be 100% v2.4)

| engine_version | count |
|---|---:|
| `2.4` | 89 |

## Exit-Reason Mix (closed trades)

| exit_reason | count |
|---|---:|
| `SL_HIT` | 77 |
| `TP_HIT` | 11 |

## Signal Status Mix

| status | count |
|---|---:|
| `EXECUTED` | 89 |
| `RISK_REJECTED` | 41 |

## Methodology Notes

- FX-weekend gaps (Fri ≥20:00 UTC → Sun ≤22:00 UTC) are considered expected and excluded from flags.
- Shadow-signals check treats >24h silence since last record as CRITICAL because shadow_signals is the training data source for v3.0 ML work (Phase 7-8).
- Snapshot & scan cadence observed to be ~hourly. Weekday gaps >=3h flagged WARN, >=6h flagged CRITICAL.
- All times UTC.

*Source: `data/trading.db` (account_snapshots, trades, trade_results, signal_logs, scan_logs, circuit_breaker_logs, shadow_signals).*