# Post-Freeze Backlog

**Opened:** 2026-05-09 (start of STABLE_v2 freeze window)
**Earliest action:** ~2026-06-20 (after Phase 8 gate review)

> Anything you find yourself wanting to fix during the freeze goes here,
> not into a commit. The whole point of the freeze is to NOT touch the
> trading logic until the gate review answers "is the current system
> good?". Adding to the backlog is the discipline that makes 6 weeks of
> watching tolerable.

## Hard rule

If a thought starts with "I should fix..." or "I noticed we could
improve...", it belongs here. The only exceptions are the four
emergency categories defined in `code_freeze_policy.md` — wrong-direction
trade, runaway lot size, engine-can't-start crash, ledger corruption.

## Pending items (added during STABLE_v2 freeze)

### Phase 7 follow-ups (after Jun 8 path-selection vote)
- **Decide MACD-strategy fate.** Phase 7 Path B walk-forward exposed
  no symbol stable for MACD. Options: drop the strategy, raise the
  TP multiplier from 3.5 to widen R:R, or accept it as a no-edge
  strategy and remove from rotation.
- **Decide RSI-strategy fate.** Same story; EURUSD-only single-corpus
  result didn't survive walk-forward. Same options.
- **Re-scope Step 8** if the Jun 8 vote chose Phase 8 corpus widening
  (M15/H4 timeframes or new generators).

### Engine bugs / cleanups (verified read-only during freeze)
- **AI-001 — XAUUSD BUY-side capability.** Was Path-D dependent on
  Phase 7 (now exhausted). Needs a different solution path —
  retraining the ml_direct model on a balanced corpus, or accepting
  XAUUSD is SELL-only.
- **AI-021 — Persist SL modifications to DB.** Currently, when the
  position monitor moves SL to breakeven (e.g. 21:40 yesterday on
  USDJPY #56582564696), the modification updates MT5 but doesn't
  write a row to a local audit table. Adds a `trade_sl_modifications`
  table or extends `trade_results`.
- **AI-022 — Shadow-write silence post-restart.** Confirmed bounded
  bug 2026-05-09; needs Sunday-evening market-open scans to verify
  whether it persists. If yes: instrument `shadow_tracker.log_signal`
  with explicit success logger.

### Observability / instrumentation enhancements
- **AI-009 — RFC for ml_direct/XAUUSD keep-or-block.** Pure docs;
  could be done DURING the freeze (no code change). Filed here in
  case the user prefers to do it after the gate so the decision
  can use STABLE_v2 evidence.
- **AI-011 — Decide ML training set composition explicitly.** Same:
  pure docs.
- **AI-012 — Gold regime monitor (5/20 SMA crossover).** Small new
  monitoring script; can be done during the freeze if read-only
  (no engine integration). Filed here to be safe.

### GAP-FID gaps requiring live broker
- **GAP-FID-05 — 2k lot sizing not end-to-end validated.** Needs
  the live broker switch. Plan: run after Phase 9.1 (Sep 1) on
  the actual live account before scaling capital.
- **GAP-FID-07 — REQUOTE handling.** No path for `TRADE_RETCODE_REQUOTE`
  (10004). The demo doesn't requote; live broker will. Add handling
  before Phase 9.
- **GAP-FID-08 — Broker server time is EEST (+3 UTC), not UTC.** Adjust
  timestamp handling where it matters (news_filter, possibly TSMOM
  timing). Investigate whether the current EEST→UTC normalisation
  in MT5Adapter is sufficient.
- **GAP-FID-09 — OVERLAP-session and news-window spread regime not
  sampled.** Need a separate spread-by-session study. Would feed
  Phase 9 risk model.
- **GAP-FID-10 — Demo leverage 1:1000 vs Phase 9 broker likely 1:30-50.**
  Document the assumption + add a config-validated leverage assertion
  at engine startup.

### v4 / Phase 11+ research (long-horizon)
- **Phase 11 strategy expansion.** 4-5 uncorrelated strategies:
  crypto momentum (Phase 10 outcome), commodity TSMOM (Phase 6
  TSMOM was FX-only), VIX regime, etc.
- **Phase 12 infrastructure migration.** MT5 → IBKR (multi-asset)
  + ccxt (crypto) + TimescaleDB + Grafana. Big lift; only after
  v3 has live track record.

## How to use this file

- During the freeze: append items here. Don't act on them.
- At the gate review: look at the list, prioritise based on what
  STABLE_v2 evidence revealed, and start a Phase 8.5 / Phase 9
  prep window with the top 3-5 items.
- Items can also be deleted if STABLE_v2 evidence shows they're
  irrelevant (e.g., AI-001 might disappear if XAUUSD trades
  perform fine SELL-only).

## What is NOT in this backlog

- Anything that's currently OPEN as an action_item — those have their
  own home in the tracker. This file is the post-freeze sequencing
  layer, not a duplicate of the tracker.
- Documentation that's already DONE.
- Dashboard widgets / non-trading code (those can be done DURING the
  freeze; no need to defer).

## Cross-references

- `docs/research/code_freeze_policy.md` — the freeze rules
- `docs/research/phase8_success_criteria.md` — the gate-review criteria
- `data/improvements.db` `action_items` — full project backlog
