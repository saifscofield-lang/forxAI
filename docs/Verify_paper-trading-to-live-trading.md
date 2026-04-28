═══════════════════════════════════════════════════════════════════════════════
TASK: Verify paper-trading-to-live-trading fidelity
═══════════════════════════════════════════════════════════════════════════════

CONTEXT:
The system has run 137 v3 trades on a $100k MT5 demo account. Before any
Phase 8/9 transition to live trading is considered, we need to quantify HOW
CLOSELY the demo execution mirrors what live execution would look like.
This prompt does NOT change anything — it is a diagnostic-only audit that
produces a fidelity report.

The goal is to identify gaps where demo behavior would diverge from live,
quantify them where possible, and flag any silent assumptions that would
break under live conditions.

═══════════════════════════════════════════════════════════════════════════════
EXECUTE diagnostics in 7 sections. Produce a single markdown report at:
docs/research/live_fidelity_audit_2026_04_28.md

NO files modified outside of that report. NO database writes (read-only).
═══════════════════════════════════════════════════════════════════════════════

────────────────────────────────────────────────────────────────────────────────
SECTION 1 — Account configuration audit
────────────────────────────────────────────────────────────────────────────────

### 1.1 MT5 account info (live read)
Connect to MT5 and read:
  - Account number, broker name, server name
  - Account type (demo / live / contest)
  - Account leverage (e.g. 1:100, 1:500)
  - Account currency
  - Current balance, equity, free margin
  - Margin level
  - Trade mode allowed (full / closeonly / disabled)

Source: scripts/run_engine.py likely uses MetaTrader5 library — find the
init/login call and use account_info() function.

### 1.2 Compare to config assumptions
Open config/paper.yaml and config/base.yaml. List every assumption about
the account that the configs encode (e.g. leverage_assumed, balance_floor).
Compare to actual MT5 account_info() values. Flag any mismatch.

### 1.3 Symbol-level specs
For each of 7 trading symbols (EURUSD, GBPUSD, USDJPY, XAUUSD, AUDUSD,
USDCAD, USDCHF), call mt5.symbol_info() and capture:
  - contract_size
  - tick_size, tick_value
  - min_volume, max_volume, volume_step
  - margin_initial, margin_maintenance
  - swap_long, swap_short, swap_rollover3days
  - trade_mode (full / longonly / shortonly / disabled)
  - filling_mode (FOK / IOC / RETURN)
  - spread (current live spread, in points)

Save as a table.

────────────────────────────────────────────────────────────────────────────────
SECTION 2 — Lot sizing logic audit
────────────────────────────────────────────────────────────────────────────────

### 2.1 Find the lot calculation
Search for lot/volume calculation in risk/, engine/, execution/:
  grep -rn "calc.*lot\|position_size\|risk_per_trade\|lot_size" \
    risk/ engine/ execution/

Identify the function that computes lot size per trade.

### 2.2 Reproduce the math
Pick the most recent 5 closed v3 trades from trade_results (any symbol).
For each:
  - Read: account_balance at trade open, sl_distance_in_pips, executed_volume
  - Recompute: expected_volume using the formula in risk_per_trade config
  - Compare: actual vs expected

If they match within 0.01 lot tolerance, lot logic is internally consistent.
If they don't match, document the divergence.

### 2.3 Test edge cases (read-only simulation)
For each symbol, compute what lot size the system WOULD pick at:
  - balance = $100,000, risk = 1%, sl = 20 pips
  - balance = $50,000,  risk = 1%, sl = 20 pips
  - balance = $10,000,  risk = 1%, sl = 20 pips
  - balance = $2,000,   risk = 1%, sl = 20 pips  (Phase 9 starting capital)
  - balance = $100,000, risk = 1%, sl = 5 pips   (tight stop)

Flag any case where computed lot < min_volume or > max_volume.
Flag XAUUSD especially — its pip_value differs from FX pairs.

### 2.4 Lot rounding
Check: does the system round to volume_step (typically 0.01)? Or does it
truncate? Or does it just submit raw float?

────────────────────────────────────────────────────────────────────────────────
SECTION 3 — Slippage and execution fidelity
────────────────────────────────────────────────────────────────────────────────

### 3.1 Requested vs executed price
Query trade_results. For 137 v3 trades:
  - Is there a column for requested_price AND executed_price separately?
  - If yes: compute mean abs difference per symbol. This is observed slippage.
  - If no (only one price stored): the system is NOT capturing slippage —
    log this as a fidelity gap.

### 3.2 Order send result codes
Check if the engine logs MT5 OrderSend retcode for each trade. Common codes:
  - 10009 (TRADE_RETCODE_DONE) — clean fill
  - 10004 (TRADE_RETCODE_REQUOTE) — broker requoted
  - 10013 (TRADE_RETCODE_INVALID) — invalid request
  - 10018 (TRADE_RETCODE_MARKET_CLOSED)

Count distribution across 137 v3 trades. If 100% are 10009, the demo is
giving frictionless fills — live will not.

### 3.3 SL/TP placement
Are SL and TP submitted with the OrderSend (server-side), or set after fill
via OrderModify (client-side after order)?

  - Server-side SL/TP: protected even if engine crashes
  - Client-side: vulnerable to engine downtime gaps (relevant given the
    9.2h and 6.2h snapshot gaps from 04-16 and 04-21)

Find the OrderSend call and inspect the request dict — sl and tp keys
should be set BEFORE send.

────────────────────────────────────────────────────────────────────────────────
SECTION 4 — Spread and commission accounting
────────────────────────────────────────────────────────────────────────────────

### 4.1 Commission tracking
For 137 v3 trades, check if commission is captured per trade:
  - Column commission in trade_results? Sum across 137 trades.
  - Demo accounts often report commission = 0. Flag if so.

Estimate live commission impact:
  - XAUUSD typical: $5-7 per round-trip lot
  - For 77 XAUUSD trades at average lot 0.X: estimated commission =
    77 × avg_lot × $6 = $Y missing from demo PnL
  - Same for FX pairs at typical $3-4 per round-trip standard lot

Subtract estimated live commission from v3 +$18,441 PnL. Show "live-adjusted
v3 PnL" as a sanity check.

### 4.2 Spread sampling
Sample current live spread from MT5 over a 5-minute window per symbol:
  for each symbol, every 30 seconds for 5 minutes, capture symbol_info().spread
  → mean, median, max, min, p95

Compare to spread assumed in any backtests or filter calculations.

### 4.3 Spread regime
Repeat 4.2 sampling at three times of day:
  - Asian session (e.g. 02:00 UTC if you can)
  - London open (07:00-08:00 UTC)
  - OVERLAP (13:00-15:00 UTC)
  - Off-hours / late NY (22:00 UTC)

XAUUSD spread typically: 20-35 points OVERLAP, 50-80 points off-hours.
This is data — compare the system's behavior across these regimes.

(If running this prompt outside trading hours, document expected values
from broker spec sheet and flag for re-run during market.)

────────────────────────────────────────────────────────────────────────────────
SECTION 5 — Swap accounting
────────────────────────────────────────────────────────────────────────────────

### 5.1 Swap captured?
Query trade_results: is there a swap column? Sum across 137 trades.

For each XAUUSD SELL trade that was held > 24h, expected swap on a SELL
position = symbol_info().swap_short × volume × days_held.

Compute expected total swap over 137 trades vs captured. Flag delta.

### 5.2 Triple-swap days
Count how many of 137 trades were held over a Wednesday-to-Thursday
rollover (triple-swap day for most symbols). On those, swap should be 3x.

### 5.3 Live impact estimate
For Phase 9 ($2k account): swap charges are proportionally larger relative
to balance. Estimate worst-case swap drag for a typical trade duration.

────────────────────────────────────────────────────────────────────────────────
SECTION 6 — News and market-condition handling
────────────────────────────────────────────────────────────────────────────────

### 6.1 News filter audit
The system has a news/ directory and engine code references NEWS_FILTERED
status. Check:
  - What news source is consulted?
  - Is it real-time during execution?
  - What time window before/after a high-impact event blocks trades?
  - Has any v3 trade been NEWS_FILTERED? (Briefing said v3 NEWS_FILTERED = 0)
  - If 0 in v3, is the filter actually wired in, or has it been silently disabled?

### 6.2 Verify wiring
Find where news status is checked in the order pipeline. Confirm the check
returns NEWS_FILTERED on a known historical high-impact event timestamp
(e.g. last NFP release at 2026-04-04 12:30 UTC — was the system live then?).

If filter exists but never fired in 137 trades, this is a fidelity gap:
live conditions will include news events, and untested filters fail under
load.

────────────────────────────────────────────────────────────────────────────────
SECTION 7 — Demo-vs-live structural differences
────────────────────────────────────────────────────────────────────────────────

### 7.1 Broker A-book / B-book status
Check broker documentation or symbol_info() for hints:
  - If symbol shows trade_execution = REQUEST (broker quotes), B-book likely
  - If trade_execution = MARKET or INSTANT, possibly A-book

This is informational — many brokers don't disclose. But flag what's known.

### 7.2 Server-vs-local clock drift
Read mt5.symbol_info_tick(symbol).time (broker server time) and compare
to local datetime.utcnow(). Drift > 5s is a flag for review.

### 7.3 Required: list of ASSUMPTIONS the system makes
Walk the codebase and list every place where the engine assumes a value
without verifying it from MT5. Examples:
  - "spread is 30 points" hardcoded somewhere
  - "min_lot = 0.01" hardcoded
  - "leverage = 100" assumed without account_info() check
  - "USD account" assumed when computing PnL

Each hardcoded assumption is a future bug if the broker changes terms or
the account is migrated.

────────────────────────────────────────────────────────────────────────────────
DELIVERABLE — single markdown report
────────────────────────────────────────────────────────────────────────────────

Write to: docs/research/live_fidelity_audit_2026_04_28.md

Structure:

# Paper-to-Live Fidelity Audit — 2026-04-28

## Executive Summary
- Overall fidelity rating: HIGH / MEDIUM / LOW with 3-bullet justification
- Top 3 fidelity gaps that must close before Phase 9
- Live-adjusted v3 PnL estimate (after deducting estimated commission/spread
  not captured by demo)

## Section 1: Account configuration
[results from Section 1]

## Section 2: Lot sizing
[results from Section 2, with the 5-trade reproduction table]

## Section 3: Slippage & execution
[results from Section 3, with retcode distribution]

## Section 4: Spread & commission
[results from Section 4, with spread regime table]

## Section 5: Swap accounting
[results from Section 5]

## Section 6: News handling
[results from Section 6]

## Section 7: Structural differences
[results from Section 7, with hardcoded-assumptions list]

## Identified Fidelity Gaps (Action Items)
Each gap formatted as:
  - **GAP-FID-NN**: <title>
    Severity: <HIGH/MEDIUM/LOW>
    Impact: <what breaks in live>
    Recommended fix: <one sentence>
    Phase 9 blocker: yes/no

## Live-Trading Readiness Checklist
A checkbox list of conditions that must hold before the Sep 1 Phase 9 start:
  ☐ Server-side SL/TP confirmed
  ☐ Commission captured in trade PnL
  ☐ Slippage observed & bounded
  ☐ News filter functional & tested
  ☐ Swap captured
  ☐ All hardcoded assumptions removed or documented
  ☐ Lot sizing tested at $2k balance scale
  ☐ ... etc.

## Estimated cost of remaining demo time vs live
What does it cost in fidelity to spend Phase 8 on demo vs starting Phase 9
small (e.g. $500) earlier? Numbers, not opinions.

────────────────────────────────────────────────────────────────────────────────
RULES OF EXECUTION
────────────────────────────────────────────────────────────────────────────────

1. READ-ONLY. Do not modify any source file, config, or database.
2. Do not place test trades. All MT5 calls are info-only (account_info,
   symbol_info, symbol_info_tick).
3. If MT5 is not connected, document that and skip live samples — produce
   the static-analysis sections regardless.
4. If a section produces no data (e.g. no commission column exists),
   write "no data — fidelity gap" rather than fabricating numbers.
5. Final report must include explicit numbers wherever possible. "Slippage
   appears low" is not acceptable; "mean slippage = 0.0 points across 137
   trades, suggesting demo does not simulate slippage" is.
6. Do NOT add anything to action_items DB yet. The fidelity audit produces
   recommendations; the meeting decides which become tracked items.
7. Estimated total runtime: 30-45 minutes. Most of it is live MT5 sampling
   in Section 4 (5-minute windows × 4 time periods if covered).
8. If during Section 4 the market is closed (weekend), sample what data
   is available and flag "live spread sampling deferred to next market
   open" with clear instruction in the report.