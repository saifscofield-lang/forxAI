# ForexAI — System Audit Report
*Generated: 2026-04-21*
*Auditor: Claude Code (data collection only — no evaluation)*

---

## 0. Important Nomenclature Note (Read First)

The audit prompt uses the labels `v1 / v2 / v3 / v4`. **The project itself does not use those labels.** The project uses fine-grained engine tags `v2.0, v2.1, v2.2, v2.3, v2.4` grouped into three canonical data-segments (`OLD`, `TRANSITION`, `STABLE`) plus a forward-looking `v3.0` plan and a `v4` strategic framework. The mapping applied here:

| Audit label | Project name     | Engine versions    | Period                   | Group      |
|-------------|------------------|--------------------|--------------------------|------------|
| **v1**      | OLD segment      | pre-v2.0, v2.0     | 2026-03-18 → 2026-03-30  | OLD        |
| **v2**      | TRANSITION       | v2.1, v2.2, v2.3   | 2026-03-31 → 2026-04-09  | TRANSITION |
| **v3**      | STABLE (current) | v2.4               | 2026-04-10 → ongoing     | STABLE     |
| **v4**      | Research only    | — (no code yet)    | 2026-04-17 → ongoing     | —          |

Source of mapping: `data/improvements.db::data_segmentation_log` — three rows explicitly defining the boundaries. Re-exported to `artifacts/version_definitions.csv`.

**There is no "v3.0 production" yet.** Phase 5 (`v3.0 Pre-Build`) is IN_PROGRESS, Phase 8 (`v3.0 Paper Trading`) has not started. The current running engine is `v2.4` (git tag `v2.4-frozen`). The name "v3" in this audit is a mapping from the STABLE segment, not from the planned v3.0 release.

**v4 has no executed trades.** The `tsmom_runs` and `meta_labeler_runs` tables contain prototype research runs on **existing forex data** — these were feasibility probes feeding into the v4 strategic plan, not v4 backtests on crypto. All eight Phase-10 (`v4 Research — Crypto Momentum`) steps are PENDING.

---

## 1. Project Map

### Folder tree (2 levels)

```
D:\forexAI\
├── backtest\                   # universal_backtester, fast_backtest, ml_backtest
├── config\                     # base.yaml (risk, instruments, timeframes)
├── dashboard\                  # Streamlit project tracker + phase pages
├── data\
│   ├── improvements.db         # SQLite — project tracker, research runs, segmentation
│   ├── trading.db              # SQLite — OHLCVBar, Trade, AccountSnapshot (live engine)
│   ├── backtest_results.db     # SQLite — backtest runs
│   ├── ml_training\            # 9 CSVs — trades, signal_logs, indicators, news
│   ├── raw\                    # Parquet — historical OHLCV per symbol/timeframe
│   ├── logs\, reports\, research\   # ancillary
├── docs\
│   ├── v4_framework.md         # 307-line strategic blueprint for v4
│   ├── project_evaluation_framework.md  # weighted-scoring methodology
│   ├── claude_code_audit_prompt.md      # this audit's instructions
│   ├── ForexAI_v3_Plan.docx, strategy_lab_final.jsx, platform_AR/EN.md
│   └── research\               # expectancy, feature_importance, meta_labeler, tsmom, keep_kill
├── engine\                     # TradingEngine (orchestrator)
├── execution\, risk\, strategies\, features\   # core pipeline
├── ingestion\, news\, ml\, models\
├── scripts\                    # 34 runnable scripts (backtests, research, tooling)
├── storage\                    # SQLAlchemy models
└── tests\                      # pytest
```

### File inventory (data artifacts audited)

| File                                       | Rows | Role                                                  |
|--------------------------------------------|-----:|-------------------------------------------------------|
| `data/improvements.db` (12 tables)         | —    | Canonical project state: version segments, phases, research results |
| `data/ml_training/trades.csv`              | 252  | Primary per-trade log (20 cols, has `engine_version`) |
| `data/ml_training/trade_results.csv`       | 246  | Enriched trades (118 cols incl. 82 ML features)       |
| `data/ml_training/signal_logs.csv`         | —    | Signal-level log (98 cols, pre-filter signals)        |
| `data/ml_training/account_snapshots.csv`   | 980  | Balance/equity snapshots (per minute-ish)             |
| `data/ml_training/indicator_snapshots.csv` | —    | Per-scan indicator values (106 cols)                  |
| `data/ml_training/market_contexts.csv`     | —    | Per-signal market context                             |
| `data/ml_training/scan_details.csv`        | —    | Per-scan details (crossover flags, rejections)        |
| `data/ml_training/news_events.csv`         | —    | Economic-calendar events                              |
| `docs/research/research.rar`               | —    | Archive — **not unpacked** (markdown summaries at `docs/research/*.md` already cover the content) |

### Time ranges covered

| Source                         | From                     | To                       |
|--------------------------------|--------------------------|--------------------------|
| `trades.csv` (open_time)       | 2026-03-18 01:47         | 2026-04-21 08:05         |
| `account_snapshots.csv` (time) | 2026-03-16 13:59         | 2026-04-21 05:05         |
| `tsmom_runs` (run_time)        | 2026-04-17 14:06         | 2026-04-17 14:06 (single batch) |
| `meta_labeler_runs` (run_time) | 2026-04-17 13:51         | 2026-04-17 13:51 (single batch) |

### How boundaries were inferred

1. `data_segmentation_log` (3 rows) is an explicit, human-authored boundary table with date_from/date_to, engine_versions, rationale. This is the canonical source.
2. Confirmed against git tag `v2.4-frozen` (commit `3b86730 Phase 5 step 8: ... v2.4 tagged`).
3. Trade records post-segmentation (data_group = NULL) were assigned to STABLE when `engine_version == '2.4'` AND `open_time >= 2026-04-10`, matching segmentation_log's "ongoing" definition.
4. `data_segmentation_log` is inconsistent on engine_version labeling for the OLD period (some rows show 2.0/2.1 pre-v2.0 era). The `data_group` column is authoritative; `engine_version` is informational.

---

## 2. Version Boundaries

| Version | Start date  | End date   | How boundary was determined                                                     |
|---------|-------------|------------|---------------------------------------------------------------------------------|
| v1      | 2026-03-18  | 2026-03-30 | `data_segmentation_log.id=1` (OLD) + trades.csv `data_group='OLD'` (132 rows)   |
| v2      | 2026-03-31  | 2026-04-09 | `data_segmentation_log.id=2` (TRANSITION) + trades.csv `data_group='TRANSITION'` (46 rows) |
| v3      | 2026-04-10  | ongoing    | `data_segmentation_log.id=3` (STABLE) + extension rule for post-04-14 trades with `engine_version=2.4` (74 rows total: 33 STABLE + 41 post-segmentation, of which 35 closed) |
| v4      | 2026-04-17  | ongoing    | Phase 10 start date (`project_phases.phase_number=10`); no live/paper trades exist, only prototype research runs logged on 2026-04-17 |

---

## 3. Per-Version Data

### 3.1 v1 — OLD segment

**Metadata**
- Data source: MT5 demo (paper trading), single continuous account (balance starts $100,000.00).
- Instruments: AUDUSD, EURUSD, GBPUSD, NZDUSD, USDCAD, USDCHF, USDJPY, XAUUSD (8 symbols).
- Timeframe: H1 primary (per `config/base.yaml`).
- Starting capital: **$100,000 USD** (real value from `account_snapshots.csv` at 2026-03-18 00:02).
- Position sizing: Fixed lot **2.0–10.0** (per segmentation_log narrative — not capped).

**Core change vs prior:** (baseline — no prior version)

**Aggregate metrics** (computed from 132 closed trades)

| Metric                     | Value        |
|----------------------------|-------------:|
| Total trades               | 132          |
| Winning trades             | 67           |
| Losing trades              | 65           |
| Win rate                   | 50.76%       |
| Net PnL                    | +$18,637.62  |
| Net PnL (% of start)       | +18.64%      |
| Avg win                    | +$656.82     |
| Avg loss                   | −$390.29     |
| Avg R:R                    | 1.683        |
| Profit factor              | 1.735        |
| Max drawdown               | −$6,224.64   |
| Max drawdown (% of start)  | −5.72%       |
| Longest losing streak      | 6            |
| Sharpe (daily, ann.)       | 7.87  ⚠ unreliable — only 13 trading days |
| Sortino (daily, ann.)      | 28.60 ⚠ unreliable — only 13 trading days |
| Exposure time              | 216.77% (multiple concurrent positions) |

**Trade log location:** `artifacts/v1_trades.csv`

**Gaps / assumptions:**
- Sharpe and Sortino computed over only 13 trading days — these are not meaningful annualized numbers, flagged as unreliable; reviewer should weight heavily against these.
- `engine_version` column in the CSV shows 2.0 (10 trades) + 2.1 (22 trades) + NaN (100 trades); assigned to v1 based on authoritative `data_group=OLD`.
- Per segmentation_log: "lot sizes 2-10, no ATR filter, no regime detector, no shadow tracker, no timezone fix, no strategy blacklist". Performance is **not representative** of current code.

---

### 3.2 v2 — TRANSITION segment

**Metadata**
- Data source: MT5 demo (paper trading), continuous account (starts $118,310.82 carrying v1 gains).
- Instruments: AUDUSD, EURUSD, GBPUSD, USDCAD, USDCHF, USDJPY, XAUUSD (7 symbols — NZDUSD dropped vs v1).
- Timeframe: H1 primary.
- Starting capital: **$118,310.82 USD** (from account_snapshots at 2026-03-31 03:52).
- Position sizing: Lot size cap changed from 2.0 → 1.0 mid-period.

**Core change vs prior:** 13 config changes in 10 days — ATR filter added (1.5× then 1.2×), regime detector built, scoring system added, circuit breaker added (log-only), shadow tracker added (Apr 2), session filter toggled, 8 strategies enabled, daily limits added then removed. Timezone bug still present (close times in local time). XAUUSD not yet ML-blacklisted.

**Aggregate metrics** (computed from 46 closed trades)

| Metric                     | Value         |
|----------------------------|--------------:|
| Total trades               | 46            |
| Winning trades             | 34            |
| Losing trades              | 12            |
| Win rate                   | 73.91%        |
| Net PnL                    | −$26,472.04   |
| Net PnL (% of start)       | −22.37%       |
| Avg win                    | +$269.33      |
| Avg loss                   | −$2,969.11    |
| Avg R:R                    | 0.091         |
| Profit factor              | 0.257         |
| Max drawdown               | −$27,241.67   |
| Max drawdown (% of start)  | −22.88%       |
| Longest losing streak      | 3             |
| Sharpe (daily, ann.)       | −10.28 ⚠ unreliable — only 9 trading days |
| Sortino (daily, ann.)      | −13.55 ⚠ unreliable — only 9 trading days |
| Exposure time              | 141.92%       |

**Trade log location:** `artifacts/v2_trades.csv`

**Gaps / assumptions:**
- v2's high win rate (73.9%) with catastrophic PnL (−22%) is the textbook "big losses on losers, tiny wins on winners" pattern (R:R = 0.091). This is also visible structurally: avg loss (−$2,969) is ~11× avg win (+$269).
- Per segmentation_log, this segment is explicitly marked **not valid for** ML training or strategy evaluation due to daily code changes.
- `engine_version` column shows 2.2 (5), 2.3 (8), 2.4 (33) — segmentation_log claims 2.1–2.4 but no 2.1 trades present in data (2.1 trades are tagged in v1/OLD).

---

### 3.3 v3 — STABLE segment (current production candidate)

**Metadata**
- Data source: MT5 demo (paper trading), continuous account (starts $92,165.58 carrying v2 losses).
- Instruments: AUDUSD, EURUSD, GBPUSD, USDCAD, USDCHF, USDJPY, XAUUSD (7 symbols).
- Timeframe: H1 primary, H4 secondary, M15 confirmation.
- Starting capital: **$92,165.58 USD** (from account_snapshots at 2026-04-10 00:05).
- Position sizing: Lot cap 1.0, all 8 strategies enabled.

**Core change vs prior:** v2.4 stable — timezone UTC fix, XAUUSD ML-blacklist, shadow tracker with lot+spread+UTC timestamps, session filter disabled in demo (for data collection), IMP-15 session filter disabled. First period with no daily code changes. All filters consistent.

**Aggregate metrics** (computed from 68 closed trades; 6 open positions excluded)

| Metric                     | Value         |
|----------------------------|--------------:|
| Total trades               | 68            |
| Winning trades             | 42            |
| Losing trades              | 26            |
| Win rate                   | 61.76%        |
| Net PnL                    | −$17,929.98   |
| Net PnL (% of start)       | −19.45%       |
| Avg win                    | +$508.10      |
| Avg loss                   | −$1,510.39    |
| Avg R:R                    | 0.336         |
| Profit factor              | 0.543         |
| Max drawdown               | −$26,765.66   |
| Max drawdown (% of start)  | −27.33%       |
| Longest losing streak      | 7             |
| Sharpe (daily, ann.)       | −5.44  ⚠ unreliable — only 11 trading days |
| Sortino (daily, ann.)      | −17.79 ⚠ unreliable — only 11 trading days |
| Exposure time              | 172.50%       |

**Trade log location:** `artifacts/v3_trades.csv` (74 rows total; 6 still-open excluded from metrics)

**Gaps / assumptions:**
- Sharpe/Sortino should be disregarded — 11-day window, highly concentrated in a few large losses.
- `system_state` table independently reports cumulative demo account stats at 2026-04-20: `total_trades=243, total_pnl=-28,796.80, balance=71,203.20, win_rate=58.02%`. These match the extracted figures within expected drift (trades after 2026-04-20 added).
- Avg loss (−$1,510) is still ~3× avg win (+$508) — the R:R problem persists from v2 but with smaller magnitude.
- This is the **only segment valid for ML training and evaluation** per segmentation_log.

---

### 3.4 v4 — Research phase (no executed trades)

**Metadata**
- Status: Phase 10 (`v4 Research — Crypto Momentum`) marked IN_PROGRESS since 2026-04-19.
- **All 8 Phase-10 steps are PENDING** (source: `phase_steps` where `phase_number=10`):
  1. `PENDING` — install ccxt + connect to Binance/Bybit
  2. `PENDING` — download D1+W1 history for BTC, ETH, SOL, BNB (2017-2026)
  3. `PENDING` — build TSMOM variant (12w lookback, 24w vol targeting, weekly rebalance)
  4. `PENDING` — Purged K-Fold validation on 2017-2024, held-out 2025-2026
  5. `PENDING` — compute Sharpe + Max DD + correlation with S&P500 + FX portfolio
  6. `PENDING` — compare with AQR benchmarks (crypto momentum Sharpe 0.5-0.8 / 0.8-1.5)
  7. `PENDING` — go/no-go decision (Sharpe ≥ 0.4 after costs)
  8. `PENDING` — document in `docs/research/crypto_momentum_prototype.md`

**Core change vs prior:** Strategic pivot from FX H1 to crypto D1/W1 momentum + multi-asset portfolio (see `docs/v4_framework.md`). Target Sharpe 0.8–1.0.

**Research data available** (these are FX-based feasibility probes — NOT v4 backtests on crypto)

`tsmom_runs` — 8 rows, all `run_time=2026-04-17 14:06:55`, D1 forex pairs 2012-02-29 → 2026-04-30:

| Scope                    | Ann. Return | Ann. Vol | Sharpe | Sortino | Max DD  | CAGR    | Verdict |
|--------------------------|------------:|---------:|-------:|--------:|--------:|--------:|---------|
| EURUSD                   | −0.10%      | 7.32%    | −0.01  | −0.02   | −26.0%  | −0.36%  | POOR    |
| GBPUSD                   | −0.56%      | 8.02%    | −0.07  | −0.13   | −22.7%  | −0.88%  | POOR    |
| USDJPY                   | +3.20%      | 9.02%    | +0.35  | +0.52   | −24.1%  | +2.83%  | MARGINAL|
| XAUUSD                   | +3.78%      | 10.90%   | +0.35  | +0.63   | −31.3%  | +3.25%  | MARGINAL|
| USDCHF                   | −2.07%      | 7.56%    | −0.27  | −0.45   | −41.0%  | −2.33%  | POOR    |
| AUDUSD                   | +0.50%      | 9.28%    | +0.05  | +0.09   | −22.1%  | +0.08%  | POOR    |
| USDCAD                   | −0.51%      | 7.31%    | −0.07  | −0.13   | −31.1%  | −0.77%  | POOR    |
| **portfolio_equal_weight** | **+0.61%**| **4.82%**| **+0.126**| **+0.198**| **−15.4%** | **+0.49%** | **POOR** |

`meta_labeler_runs` — 9 rows (GLOBAL + per-strategy + per-combo). Strongest result: RSI-reversal PER_STRATEGY, WR lift from 33.9% → 41.1% (+7.2pp), AUC 0.58, verdict STRONG. MACD-crossover meta-labeling verdict: MARGINAL. Several PER_COMBO rows show meta-labeler actively **hurting** performance (verdict NONE).

**v4 readiness section:** see §5 below.

**Trade log location:** `artifacts/v4_backtest_trades.csv` (17 rows: 8 tsmom + 9 meta_labeler research records; this is NOT a trade log — there are no v4 trades)

**Gaps / assumptions:**
- No executed trades at all. All v4 data is research output, not backtest trades.
- No crypto data, no ccxt, no BTC/ETH/SOL in the project.
- Verdicts in the tables are authored by the researcher, not computed ratings — I've reproduced them verbatim.

---

## 4. Cross-Version Comparison

| Metric                     | v1 (OLD)      | v2 (TRANSITION)| v3 (STABLE)   | v4 (research TSMOM portfolio) |
|----------------------------|--------------:|---------------:|--------------:|------------------------------:|
| Start date                 | 2026-03-18    | 2026-03-31     | 2026-04-10    | 2012-02-29 (backtest)         |
| End date                   | 2026-03-30    | 2026-04-09     | ongoing       | 2026-04-30 (backtest)         |
| Trading days (approx)      | 13            | 9              | 11            | 171 months                    |
| Total trades               | 132           | 46             | 68            | 0 (research only)             |
| Win rate                   | 50.76%        | 73.91%         | 61.76%        | 48.5% (monthly hit rate)      |
| Net PnL                    | +$18,637.62   | −$26,472.04    | −$17,929.98   | +$0 (no capital deployed)     |
| Net PnL (%)                | +18.64%       | −22.37%        | −19.45%       | +0.61% ann. return (backtest) |
| Avg R:R                    | 1.683         | 0.091          | 0.336         | n/a                           |
| Profit factor              | 1.735         | 0.257          | 0.543         | n/a                           |
| Max drawdown (%)           | −5.72%        | −22.88%        | −27.33%       | −15.45% (monthly)             |
| Sharpe                     | 7.87 ⚠        | −10.28 ⚠        | −5.44 ⚠        | +0.126 (monthly, ann.)        |
| Instruments                | 8 FX+XAU      | 7 FX+XAU       | 7 FX+XAU      | 7 FX+XAU (research; crypto planned) |
| Engine version(s)          | 2.0 + pre     | 2.1–2.4        | 2.4           | — (no code)                   |
| Core change                | —             | +13 configs in 10 days | timezone fix + XAU blacklist + filter consistency | pivot to crypto+multi-asset portfolio |

⚠ = Sharpe unreliable due to <15-trading-day window. Do not use these values in scoring without adjustment.

---

## 5. v4 Readiness Summary

### Ready (strategic planning)
- **Framework document:** `docs/v4_framework.md` (307 lines) — paradigm shifts, asset niches, infra plan, roadmap, honest expectations.
- **Evaluation methodology:** `docs/project_evaluation_framework.md` — weighted scoring (PnL 30 / R:R 20 / Sharpe 20 / WR 15 / DD 15).
- **FX feasibility probes:** TSMOM and meta-labeler prototypes on 7 forex pairs over 14 years of D1 data — produced enough evidence to justify the **pivot away** from pure-FX TSMOM (portfolio Sharpe 0.126).
- **Phases defined in tracker:** Phases 10–14 covering research → strategy expansion → infra → paper → live, spanning 2026 Q3 → 2027 Q4 per `v4_framework.md::Roadmap`.
- **Git tag:** `v2.4-frozen` locks the current production baseline so v4 can diverge cleanly.

### Blocking (technical)
- **No ccxt integration.** Grep for `ccxt|BTC|binance|bybit` in `.py/.yaml` returns matches only in dashboard phase descriptions (Arabic narrative) and audit/framework docs. Zero implementation code.
- **No crypto historical data.** No BTC/ETH/SOL/BNB files in `data/raw/`; only FX + XAU.
- **No crypto backtest window defined.** Step `2. download D1+W1 historical data for BTC, ETH, SOL, BNB (2017-2026)` is PENDING.
- **Out-of-sample split:** Planned (Step 4: "Purged K-Fold validation on 2017-2024, held-out test 2025-2026") but not implemented.
- **Transaction cost model:** Not present. Framework Section 4 specifies ≥0.1% per side; no code enforces this yet.
- **Buy-and-hold BTC benchmark:** Planned (Step 5 mentions S&P500 + FX portfolio correlation; buy-and-hold BTC comparison not in step list).
- **All 8 Phase-10 steps PENDING.** Concrete blocker: step 1 (install ccxt + connect).

### Dependencies blocked on Phase 5 (v3.0 Pre-Build)
- Phase 5 is IN_PROGRESS and concurrent with Phase 10. Completed Phase-5 steps relevant to v4: feature-importance shortlist (82→20), 1,144-signal dataset, strategy keep/kill decision (10 combos from 56), git tag `v2.4-frozen`.
- Pending Phase-5 steps that gate v3.0 go/no-go (set for 2026-04-28): reading *Advances in Financial Machine Learning* Ch. 3/4/7, confirming v2.4 demo stability, clean env setup for May 1-3.

---

## 6. Data Quality Notes

**Reviewer must know the following before trusting the v1/v2/v3 numbers:**

1. **Short trading windows make Sharpe meaningless.** v1 = 13 days, v2 = 9 days, v3 = 11 days. Annualizing a 9-day stdev produces values like −10 or +7 that are arithmetic artifacts, not signal. **Recommend: do not use Sharpe in the scoring for v1/v2/v3; substitute with profit factor or leave Sharpe weight empty.**

2. **Single continuous demo account, not three isolated pots.** The evaluation framework's Section 3 requests starting capital per version; the reality is $100k → $118k (v1 end) → $92k (v2 end) → $74k (current). I computed `% of start` using each version's starting balance. Absolute PnL is version-scoped (trades within the window only), but the capital base shrinks, so raw % comparisons have compounding baked in.

3. **Position sizing changed mid-v2.** Lot size cap was changed from 2.0 to 1.0 during TRANSITION. v1's high absolute PnL partly reflects larger positions, not better signals. Per segmentation_log: "Mixing this with current data would poison ML training."

4. **Exposure time >100% is normal here, not a bug.** Multiple concurrent positions across up to 8 symbols. The metric as reported sums individual trade durations.

5. **v2's 73.9% win rate is misleading.** Avg loss is 11× avg win — the rare losses wiped out the frequent small wins. R:R of 0.091 is the honest summary.

6. **`engine_version` labeling is inconsistent across CSVs.** `trades.csv` (252 rows) and `trade_results.csv` (246 rows) disagree on the engine_version for OLD-period rows. I used `data_group` (authoritative, authored by segmentation run on 2026-04-14) as the partition column and treated `engine_version` as informational.

7. **Post-segmentation trades (41 rows, open after 2026-04-14)** have `data_group=NaN` — I folded them into v3 on the rule `engine_version=2.4 AND open_time>=2026-04-10`, matching segmentation_log's "STABLE is ongoing" definition. Of those 41, only 35 are closed; 6 remain open and are excluded from metrics.

8. **6 open positions excluded from v3 metrics.** They hold unrealized P&L. Reviewer may want to check `account_snapshots.csv` for latest equity (last snapshot: balance=$74,235.60, equity=$77,853.88 at 2026-04-21 05:05 — so unrealized is +$3,618 MTM, not yet in the v3 realized-PnL figure).

9. **v4 "metrics" are research outputs, not executed trade results.** The TSMOM portfolio Sharpe of 0.126 is a backtest on 14 years of FX data — it is NOT v4 performance, it is the evidence that **justified** pivoting v4 away from FX-only TSMOM. Do not score v4 against v1/v2/v3 on the same ruler.

10. **`research.rar` was not unpacked.** Markdown summaries at `docs/research/*.md` (tsmom_prototype, meta_labeler_prototype, expectancy_report, feature_importance_report, strategy_keep_kill, primary_signals_*) provide the substantive content. The DB (`tsmom_runs`, `meta_labeler_runs`, `expectancy_analysis` — 62 rows) holds the raw numbers.

11. **Arabic text in the DB and docs** — Phase descriptions, improvement titles, and step descriptions contain Arabic (English summary is available in the English docs). Where I've quoted Arabic text in this report, the content is preserved verbatim.

12. **Trade count discrepancy:** `trades.csv` has 252 rows but `system_state` latest row reports `total_trades=243`. The 9-row difference is likely 6 open + 3 timing drift (snapshot taken 2026-04-20 19:45 vs CSV export 2026-04-21 08:05).

---

## 7. Files Produced

- `docs/audit_report.md` — this report
- `artifacts/version_definitions.csv` — raw export of `data_segmentation_log` (3 rows, 15 cols)
- `artifacts/v1_trades.csv` — 132 closed trades, OLD segment
- `artifacts/v2_trades.csv` — 46 closed trades, TRANSITION segment
- `artifacts/v3_trades.csv` — 74 rows (68 closed, 6 open), STABLE segment + post-segmentation
- `artifacts/v4_backtest_trades.csv` — 17 rows (8 tsmom + 9 meta_labeler research records; NOT per-trade data)
- `artifacts/metrics_summary.json` — all computed aggregate metrics in one JSON document
- `scripts/audit_extract.py` — the extraction script (re-runnable; paths relative to project root)

---

*Audit complete. 4 versions covered (v1/v2/v3 with trade data, v4 with research data only). Total closed trades extracted: 246 (v1: 132 + v2: 46 + v3: 68). Report path: `docs/audit_report.md`.*
