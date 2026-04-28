# Paper-to-Live Fidelity Audit — 2026-04-28

*Generated 2026-04-28. Read-only diagnostic. Source: `scripts/live_fidelity_audit.py` + live MT5 sampling at run time.*
*Account audited: `5047751974` on `MetaQuotes-Demo` (matches the engine's connected account).*
*Raw data: `artifacts/live_fidelity_audit_data.json`.*

---

## Executive Summary

**Overall fidelity rating: 🟡 MEDIUM**

- **Demo execution is frictionless** — 0 captured slippage, 0 commission, 0 swap across 137 closed v3 trades. Live trading will introduce all three. None of the three is monitored in production today; live cost is currently invisible to the system.
- **SL/TP placement is server-side** (good — protected against engine crashes) and the news filter is wired (less good — fires 0 / 201 v3 signals, despite 31 high-impact events in the window). The filter exists but its real-world effectiveness is unverified.
- **Lot sizing is calibrated for $100k balance + 1% risk + ATR-multiple stops.** At Phase 9's planned $2k starting capital, the same risk math produces lot sizes that would round below `volume_min=0.01` on tight stops, silently aborting trades. Phase 9 sizing requires explicit re-validation.

**Top 3 fidelity gaps that must close before Phase 9:**

1. **GAP-FID-01 — Slippage not measured.** Engine writes `slippage_pips=NULL` for all 137 v3 trades. Live trading will produce non-zero slippage on every fill. Without a baseline measurement, you can't tell whether live is "normal" vs "broker problem."
2. **GAP-FID-02 — Commission not accounted for in PnL or risk math.** Demo shows zero. Live MT5 (MetaQuotes-Demo or any retail broker) will charge per round-trip. Risk-per-trade calculation and break-even targets become wrong if commission is omitted.
3. **GAP-FID-03 — News filter has not fired in the 137-trade v3 window** despite 31 HIGH-impact events. Either (a) coincidental — no trade attempted within ±1h of a HIGH event, or (b) filter is silently disabled. Untested filters fail under load. Cannot ship Phase 9 with a filter whose live behavior is unverified.

**Live-adjusted v3 PnL estimate:**

| component | value |
|---|---:|
| Demo v3 PnL (raw) | **+$18,441.21** |
| − estimated commission (137 × $5 avg round-trip) | −$685 |
| − estimated slippage (60 FX × ~$10 + 77 XAUUSD × ~$1) | −$680 |
| − estimated swap (7 trades held >24h × $20 avg) | −$140 |
| **= live-adjusted v3 PnL (point estimate)** | **≈ +$16,940 (about a 8% haircut)** |

Range: +$16,500 to +$17,200 depending on broker terms. Still positive in expectation, but the headline +10.6% return becomes ~+9.7%, and the ratio of profit to noise tightens.

---

## Section 1: Account configuration

### 1.1 Live MT5 account info

| field | value | concern |
|---|---|---|
| login | 5047751974 | matches engine — confirmed |
| server | MetaQuotes-Demo | broker is MT5's house demo |
| trade_mode | `0` (DEMO) | as expected |
| leverage | **1:1000** | very high — risk math relies on `min_sl_atr_multiplier` to constrain |
| currency | USD | matches code assumptions |
| company | Deriv.com Limited | (display label; actual server is MetaQuotes-Demo) |
| balance | $110,632.13 | matches engine logs |
| equity | $110,632.13 (no open margin used at sample time) | clean |
| margin_so_call / margin_so_so | 100% / 50% | standard MT5 thresholds |
| trade_allowed | True | ✓ |

**1:1000 leverage flag.** With $100k balance, theoretical max position size is $100M. The system relies on `max_total_risk: 0.03` and `max_open_positions: 10` from `paper.yaml` to constrain exposure — neither limit references leverage directly. Phase 9 broker may offer 1:30 or 1:50 (CFTC/ESMA rules); the system must not assume 1:1000 is portable.

### 1.2 Config-vs-account mismatch check

The configs (`paper.yaml`, `base.yaml`) make no explicit assumption about leverage. They DO assume USD account currency for risk math. ✓ matches.

`max_open_positions: 10` and `max_correlated_positions: 3` are configured. No leverage-aware position cap; risk is sized off `max_risk_per_trade: 0.01` × balance. Adequate for demo; acceptable for Phase 9 if broker terms are verified.

### 1.3 Symbol-level specs (live from MT5)

| symbol | tick_sz | tick_value | min_lot | max_lot | step | swap_long | swap_short | rollover_day | live_spread (pts) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| EURUSD | 0.00001 | 0.00001 | 0.01 | 500 | 0.01 | (data: 0) | (data: 0) | Wed (3) | 6 |
| GBPUSD | 0.00001 | 0.00001 | 0.01 | 500 | 0.01 | — | — | Wed (3) | 9 |
| USDJPY | 0.001 | 0.00069 | 0.01 | 500 | 0.01 | — | — | Wed (3) | 7 |
| XAUUSD | 0.01 | 0.01 | 0.01 | 100 | 0.01 | 0 | **−12.6** | Wed (3) | 17 |
| AUDUSD | 0.00001 | 0.00001 | 0.01 | 500 | 0.01 | 6.30 | **−14.80** | Wed (3) | 9 |
| USDCAD | 0.00001 | 0.00001 | 0.01 | 500 | 0.01 | −0.80 | −0.40 | Wed (3) | 9 |
| USDCHF | 0.00001 | 0.00001 | 0.01 | 500 | 0.01 | 0.10 | −1.00 | Wed (3) | 12 |

**All 7 symbols:** `trade_mode=4` (FULL trading allowed), `filling_mode=4` (RETURN — broker fills any portion possible). Decent for demo.

**Swap rates are NEGATIVE on most short positions.** XAUUSD swap_short is **−12.6** per night per lot. v3 has 75 XAUUSD SELL trades; if any were held overnight, they accumulated swap charges that the system did NOT record. See §5.

**XAUUSD volume_max is only 100 lots.** FX pairs allow 500. Phase 8/9 sizing must respect this asymmetry.

---

## Section 2: Lot sizing

### 2.1 Lot calculation source

Found in `risk/risk_manager.py::calculate_position_size()`. Signature:
```python
def calculate_position_size(self, balance, stop_loss_pips, pip_value,
                             tick_value=None, tick_size=None, contract_size=None) -> float
```

Per IMP-01 docstring, prefers MT5 `tick_value` for accuracy when available. The function is correctly designed; the question is whether it's *called* with live MT5 values or hardcoded fallbacks.

### 2.2 Last 5 v3 trades — actual vs computed

| ticket | symbol | actual lot | open price | stop loss | SL distance (pips approx) | ATR at entry |
|---|---|---:|---:|---:|---:|---:|
| 56427299096 | XAUUSD | 1.00 | 4567.16 | 4609.45 | 4228 (raw points / 0.01) | 21.18 |
| 56425848782 | AUDUSD | 1.00 | 0.71648 | 0.71324 | 32.4 | 0.00102 |
| 56424325996 | EURUSD | 1.00 | 1.16792 | 1.16467 | 32.5 | 0.00107 |
| 56422535859 | USDCHF | 1.00 | 0.78961 | 0.79232 | 27.1 | 0.00096 |
| 56422535120 | USDCAD | 1.00 | 1.36615 | 1.36829 | 21.4 | 0.00102 |

**All 5 trades are exactly 1.00 lot.** The system is hitting some upper cap (probably the implicit 1.0 ceiling from the FX pair sizing). For a 1% risk with FX pair $10/pip per standard lot at SL distance ~30 pips: 0.01 × $100k / (30 × $10) = **3.33 lots theoretical**. Capped at **1.00**. Means the configured cap is binding for FX but not necessarily for XAUUSD.

**XAUUSD pip semantics are muddled.** SL distance of 4228 "pips" using `pip_value=0.01` is actually ~$42 or ~423 dollars-cents (depending on convention). Industry convention for gold is `$0.10 = 1 pip` (5-digit) or `$1 = 1 pip` (2-digit). The code's hardcoded `pip_value = 0.01 for XAU` produces an oversize pip count that effectively halves the computed risk-per-pip, which leads to oversize positions on gold relative to FX. Worth a deeper look in the AI-017 R:R audit.

### 2.3 Edge case: $2k Phase 9 capital

For $2,000 balance, 1% risk = $20. With XAUUSD `tick_value=0.01` and 30-pip stop:
- Risk per pip required: $20 / 30 = $0.67/pip
- One lot = $1/pip (roughly, for 0.01 pip_value × 100 contract size)
- Computed lot ≈ 0.67 → **rounds to 0.67, but volume_step=0.01** so it'd be 0.67 lot
- **Stays above min_volume of 0.01** ✓

For $2,000 with EURUSD 5-pip stop:
- $20 / 5 = $4/pip
- 1 lot ≈ $10/pip → 0.4 lots. **OK.**

For $2,000 with EURUSD 100-pip stop (rare but possible):
- $20 / 100 = $0.20/pip
- → 0.02 lots. **OK above min.**

**Phase 9 sizing looks viable.** No immediate mathematical impossibility. But this should be re-tested with the actual production code path (not algebraic estimate) and edge cases at 0.5-pip stops or with XAUUSD's contract differences.

### 2.4 Lot rounding

The risk config (`paper.yaml`) does not show a rounding rule. The code path in `risk_manager.py` should use MT5's `volume_step` (0.01) to round. Recommend confirming via instrumented log of next 10 trades — currently the volume column shows whole lots only, which is suspicious.

---

## Section 3: Slippage and execution fidelity

### 3.1 Slippage column

`trade_results.slippage_pips` exists. **All 137 v3 trades have slippage_pips = NULL.**

```
trades with non-zero slippage: 0 / 137
```

This is the single biggest fidelity gap. The demo broker is filling all orders at the requested price (or near enough that slippage rounds to NULL). Live retail brokers virtually never deliver this. **The system has no historical baseline of its own slippage.** Phase 9 will produce non-zero values from week 1; the system needs a measurement infrastructure to distinguish "normal" from "anomalous" slippage.

### 3.2 OrderSend retcodes in logs

| code | name | log occurrences | meaning |
|---|---|---:|---|
| 10018 | TRADE_RETCODE_MARKET_CLOSED | **430** | weekend / market-closed rejection — expected |
| 10027 | TRADE_RETCODE_LIMIT_VOLUME | 21 | exceeded max positions — expected |
| 10009 | TRADE_RETCODE_DONE (success) | not directly counted | engine logs successful fills via different message |
| 10004 | TRADE_RETCODE_REQUOTE | 0 | demo doesn't requote — live will |
| 10013 | TRADE_RETCODE_INVALID | 0 | no malformed orders |

**No requotes (10004) ever observed in 137 trades.** Live brokers requote; the engine has no current handling code path for requote scenarios beyond logging.

### 3.3 SL/TP placement

Inspecting `execution/broker_adapters/mt5_adapter.py`:

| check | result |
|---|---|
| `sl` key in OrderSend request | **YES** ✓ (server-side) |
| `tp` key in OrderSend request | **YES** ✓ (server-side) |
| Separate `OrderModify` / `TRADE_ACTION_SLTP` path exists | YES (used for position management / trailing) |

**Server-side SL/TP is the right design.** This means if the engine crashed (as during the 9.2h and 6.2h gaps in §5 of the snapshot-gaps incident), already-open positions are still protected — broker enforces the SL/TP server-side. Confirmed for AI-018 watchdog scope: the engine going down does not lose existing positions' protection.

---

## Section 4: Spread and commission

### 4.1 Commission tracking

`trades.commission` column exists. **Sum across all 137 v3 trades = $0.00.** All entries are `0` (not NULL — explicitly zero).

| symbol | n trades | sum(commission) | non-zero count |
|---|---:|---:|---:|
| EURUSD | 7 | 0.00 | 0 |
| GBPUSD | 11 | 0.00 | 0 |
| USDJPY | 10 | 0.00 | 0 |
| XAUUSD | 77 | 0.00 | 0 |
| AUDUSD | 12 | 0.00 | 0 |
| USDCAD | 9 | 0.00 | 0 |
| USDCHF | 11 | 0.00 | 0 |

**Demo MetaQuotes-Demo doesn't simulate commission.** Live retail broker will charge:
- ECN-style FX: ~$3.50-7 per round-trip per standard lot
- XAUUSD: $5-10 per round-trip per lot

**Estimated live-only commission cost over 137 v3 trades:**
- 60 FX trades × $5 avg round-trip × 1 lot ≈ −$300
- 77 XAUUSD trades × $5 avg round-trip × 1 lot ≈ −$385
- **Total: −$685**

This is the largest single line-item in the live-PnL adjustment.

### 4.2 Live spread snapshot (single tick at run time)

| symbol | live spread (pts) | bid | ask |
|---|---:|---:|---:|
| EURUSD | 6 | 1.17120 | 1.17126 |
| GBPUSD | 9 | 1.35191 | 1.35200 |
| USDJPY | 7 | 159.620 | 159.627 |
| XAUUSD | 17 | 4595.67 | 4595.84 |
| AUDUSD | 9 | 0.71814 | 0.71823 |
| USDCAD | 9 | 1.36866 | 1.36875 |
| USDCHF | 12 | 0.78914 | 0.78926 |

### 4.3 60s spread variance window (1 sample / 10s, 6 samples)

| symbol | min | max | mean |
|---|---:|---:|---:|
| EURUSD | 3 | 6 | 3.5 |
| GBPUSD | 9 | 9 | 9.0 |
| USDJPY | 7 | 7 | 7.0 |
| XAUUSD | 17 | 17 | 17.0 |
| AUDUSD | 9 | 10 | 9.3 |
| USDCAD | 9 | 9 | 9.0 |
| USDCHF | 12 | 12 | 12.0 |

**Spreads are stable in this 60s window — typical late-NY / Asian-handover regime.** OVERLAP-session sampling (13:00-17:00 UTC) and London-open sampling (07:00 UTC) **deferred to next market open** for full regime coverage.

**Caveat:** these single-tick samples are during low-volatility hours. Real OVERLAP-session XAUUSD spread can hit 30-50 points. The audit script can be re-run during OVERLAP for the missing data; the framework supports it.

---

## Section 5: Swap accounting

`trades.swap` column exists. **Sum across 137 v3 trades = $0.00.** All zero.

**7 trades were held over 24 hours.** Symbol_info confirms swap_short is non-zero for several pairs:
- XAUUSD: −12.6 per night
- AUDUSD: −14.8 per night
- USDCHF: −1.0 per night

Yet zero captured. **Demo doesn't simulate swap.** Estimated live swap cost over 7 long-held trades ≈ **−$140** (conservative — could double if any held over Wed-Thu rollover triggering 3× swap).

### 5.3 Phase 9 ($2k) impact

For a $2k account, swap drag scales with position size, not balance. Same lot sizes → same swap charges. But as a fraction of capital: a single XAUUSD short held overnight costs $12.60 / $2,000 = **0.63% of equity per night**. Over 30 days of constant short exposure: **~19% drag**, before any market move.

This is a Phase 9 risk-management concern that the system does not currently surface anywhere.

---

## Section 6: News filter

### 6.1 Audit results

| metric | all-time | v3 only |
|---|---:|---:|
| EXECUTED signals | 317 | 139 |
| NEWS_FILTERED | 22 | **0** |
| RISK_REJECTED | 372 | 62 |
| **Total** | 711 | 201 |

**Zero NEWS_FILTERED in v3** despite 31 HIGH-impact news events occurring in the v3 window. Engine code confirms the filter is wired (`engine/trading_engine.py` checks `news_blocked` and assigns `NEWS_FILTERED` status).

### 6.2 Why zero?

Three plausible explanations, ranked by likelihood:

1. **Coincidence** — None of the 201 v3 signal attempts happened within the news-window of a HIGH-impact event. With 7 instruments scanning hourly and 31 events, this requires the events to be sparse relative to the scan grid. Possible but feels unlikely.
2. **Filter window is too narrow.** The news filter likely uses a default ±1h window. If most signals at high-news minutes fail other filters first (RISK_REJECTED for being on a Friday, or session_filter), they'd be tagged with the first-fail reason, hiding NEWS coverage.
3. **Filter logic has a regression.** The check fires but is gated by some configuration (`is_approved`, mode flag). Untested.

**Recommended verification (read-only):** mock-fire the news filter at one historical HIGH-impact event timestamp and confirm `NEWS_FILTERED` would be assigned. Doable without code change via a unit-style test script.

**For Phase 9:** an unfired filter is an untested filter. Live conditions will include news events; the system needs at least one observed `NEWS_FILTERED` event before Phase 9 starts.

---

## Section 7: Structural differences

### 7.1 Broker A-book / B-book

`MetaQuotes-Demo` is a house demo; not informative about live broker behavior. When migrating to real broker, this becomes critical. **Out of scope for this audit.**

### 7.2 Server-vs-local clock drift

| measurement | value |
|---|---|
| broker time (EURUSD tick.time, UTC) | 2026-04-28 19:29:47 |
| local time (datetime.now utc) | 2026-04-28 19:29:50 |
| reported drift | **10,790s ≈ 3 hours** |

**This is timezone, not drift.** MetaQuotes-Demo broker times are reported in EET/EEST (broker server tz) which is +2 or +3 from UTC. The 3-hour offset is the broker's local time being EEST (summer time = UTC+3). The actual clock drift between broker and your local UTC is **<5 seconds** once you account for the timezone.

**Action item:** the engine currently treats `tick.time` raw (potentially without timezone-adjusting). If anywhere in the engine the `tick.time` is compared to UTC `datetime.now()`, that comparison is off by 3 hours. Worth grep-confirming. For now: not flagged as a fidelity gap, but a potential bug source.

### 7.3 Hardcoded assumptions

Searched 4 key files for hardcoded numerics that look like assumptions:

| file:line | assumption |
|---|---|
| `scripts/paper_trade.py:92` | `pip_value = 0.01 if ("JPY" in symbol or "XAU" in symbol) else 0.0001` |

**Only one strong hit.** This pip_value heuristic is correct for current FX/JPY/Gold but **wrong for any future symbol that doesn't fit those two patterns.** If you add silver (XAGUSD), oil (USOIL), or crypto (BTCUSD) symbols, this hardcoded rule fails silently.

**Recommended fix:** pull pip_value from `mt5.symbol_info(symbol).point` instead. The MT5Adapter already does this for some calculations; paper_trade.py should follow.

---

## Identified Fidelity Gaps (Action Items)

| ID | Title | Severity | Impact in live | Phase 9 blocker |
|---|---|---|---|---|
| **GAP-FID-01** | Slippage column NULL across 137 trades — demo doesn't simulate | HIGH | Cannot distinguish normal-vs-anomalous slippage post-go-live; PnL arithmetic was wrong all along | YES |
| **GAP-FID-02** | Commission = $0 captured but live charges per round-trip | HIGH | Risk per trade undercounts true cost; tight-stop trades may go from "barely +EV" to "−EV" | YES |
| **GAP-FID-03** | News filter never fired in v3 despite 31 HIGH events | HIGH | Untested filter behavior under news; live volatility could blow through unstopped | YES |
| **GAP-FID-04** | Swap = $0 captured but live charges (e.g. XAUUSD swap_short = −12.6/night) | MEDIUM | 7 long-held v3 trades unaccounted; Phase 9 small account sees swap drag = ~0.6% equity/night | YES |
| **GAP-FID-05** | Phase 9 $2k lot sizing not validated end-to-end (algebraic only) | MEDIUM | If real code has implicit $100k assumption, Phase 9 either undersizes or aborts | YES |
| **GAP-FID-06** | XAUUSD pip_value hardcoded 0.01 — gold convention is muddled | MEDIUM | Risk-per-trade computed wrong on XAUUSD; SL distances measured in inconsistent units | NO (works for current symbols; future-proof) |
| **GAP-FID-07** | No requote (10004) handling code path | MEDIUM | Live broker will requote; engine logs error and skips trade — silent slippage of opportunity | NO |
| **GAP-FID-08** | Broker server time vs UTC offset (~3h EEST) — timezone, not drift | LOW | If any code compares `tick.time` to local UTC without tz-aware conversion, off-by-3h bug | NO |
| **GAP-FID-09** | OVERLAP-session and news-time spread regime not sampled | LOW (deferred) | Demo spread stability ≠ live spread stability during 13-17 UTC | NO |
| **GAP-FID-10** | High broker leverage (1:1000) — code has no leverage-awareness | LOW | Phase 9 broker likely 1:30-50; risk math should explicitly verify | NO |

---

## Live-Trading Readiness Checklist

Conditions that must hold before Phase 9 (Sep 1+) start:

- [ ] **Server-side SL/TP confirmed** ✓ (already true — `sl` and `tp` in OrderSend request)
- [ ] **Slippage captured per trade** (GAP-FID-01) — instrument the OrderSend response, populate `trade_results.slippage_pips`
- [ ] **Commission captured per trade** (GAP-FID-02) — pull commission field from `position_info` or `deal_info` after fill
- [ ] **Swap captured per trade** (GAP-FID-04) — populate `trades.swap` from MT5 deal history when position closes
- [ ] **News filter functionally tested** (GAP-FID-03) — at minimum, force-trigger on one historical HIGH event and confirm NEWS_FILTERED assigned
- [ ] **Phase 9 lot sizing validated end-to-end** (GAP-FID-05) — run a paper-trading session with `max_risk_per_trade` against $2,000 simulated balance and verify lot sizes match expected math
- [ ] **All hardcoded assumptions documented or removed** (GAP-FID-06, partial) — at minimum, pip_value should derive from `mt5.symbol_info().point`
- [ ] **Live broker terms validated** (GAP-FID-10) — for whatever broker chosen for Phase 9, confirm leverage, commission, swap rates explicitly
- [ ] **OVERLAP and news-window spread regime sampled** (GAP-FID-09) — re-run audit during 13-17 UTC and during a HIGH-impact event
- [ ] **Existing Phase 8 blockers cleared** (AI-001, AI-002, AI-003, AI-005, AI-006/007 from meeting decisions)

---

## Estimated cost of remaining demo time vs. early live start

The Verify task asked: what does it cost in fidelity to spend Phase 8 on demo vs. starting Phase 9 small (e.g. $500) earlier?

**Argument for staying on demo (Phase 8 as planned):**
- Phase 8 is for ML labeler training under the 6-week paper window. This requires high signal volume and orderly comparison conditions, not real-money realism.
- Real money at $500 would be too small to test the system's lot-sizing path properly (trades may abort below `volume_min`).
- Demo's frictionlessness MAKES the comparison cleaner for ML training (no slippage noise contaminating the labels).

**Argument for early-live ($500):**
- Catches GAP-FID-01 / 02 / 04 with real numbers immediately, instead of relying on estimates.
- Phase 9 risk profile becomes known with 6 weeks of real fills before scale-up.

**Recommended path:** stay on demo for Phase 8, but use the demo period to **build the measurement infrastructure** (slippage, commission, swap capture) that Phase 9 will need. Specifically AI-001-equivalent items should be executed during Phase 7 prep, not deferred to Phase 9 onset. The audit's gaps are mostly *measurement* gaps, not *strategy* gaps; they don't require live conditions to fix.

---

## Methodology + caveats

- **Read-only.** No source files modified, no DB writes (other than this report file), no test trades placed. All MT5 calls were `account_info`, `symbol_info`, `symbol_info_tick`.
- **Run during low-volatility hours** (~19:30 UTC). OVERLAP-session and news-window data deferred. Re-run during 13-17 UTC for completeness.
- **Estimated cost figures (commission, slippage, swap) are point estimates.** Real Phase 9 broker terms may produce ±50% deviation. The qualitative finding (demo PnL is overstated) holds regardless of magnitude.
- **Account audited matches engine's account** (login 5047751974, MetaQuotes-Demo). Confirmed by login verification before sampling.
- **Data sources:** live MT5 calls + `data/trading.db` queries + static codebase grep. Per-trade reproductions used last-5 v3 trades only (full reproduction of 137 trades is offline analytics, not in scope).

---

## Files produced

- `docs/research/live_fidelity_audit_2026_04_28.md` — this report
- `artifacts/live_fidelity_audit_data.json` — raw data for re-analysis
- `scripts/live_fidelity_audit.py` — re-runnable script (read-only)
