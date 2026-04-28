# External Review — 1-Pager for 04-28 Meeting

*Read time: 3 minutes. Synthesis source: `docs/research/external_review_2026_04_28.md`.*

---

## Executive summary

- **Reframing:** v3 is not "narrowly profitable v3" — it is **"structurally broken model funded by an incidental window of bias × falling gold"**. The +10.6% PnL is single-symbol, single-direction, single-regime. Strip XAUUSD: v3 is **−$2,669** across 60 trades on 6 symbols.
- **Risk added:** Q3 institutional gold consensus is **bullish** (JPM $5,000, GS $5,400-6,000, DB $6,000). Phase 8 (Jun 8 - Jul 20) coincides with the **projected reversal**. A zero-BUY system in a rising market = **guaranteed drawdown**.
- **Vote that should change:** **Vote 6 (blacklist resolution).** Briefing recommended option (C) "modified — add OVERLAP block". Reviewer recommends **option (D) — block ml_direct/XAUUSD in BOTH configs until zero-BUY is resolved**. Document (D) as institutionally correct even if business pressure selects (C).

---

## Vote changes recommended

Only the four CHANGED votes shown. **Votes 1, 4, 5, 8: agreed with briefing.**

| # | Question | Reviewer's recommended | Why changed |
|---|---|---|---|
| 2 | Phase 8 paper-trading start | **DEFERRED, gate review June 1** | Five blocking conditions present simultaneously: zero-BUY unresolved, two strategies retiring during not before Phase 7, four schema-drift instances, 6-day shadow gap, projected Q3 gold reversal coincides with the 6-week window. |
| 3 | Block XAUUSD OVERLAP session | **Shadow-mode 14d first, then decide** | Hypothesis is post-hoc (generated and tested on same data). Likely confounded with ATR. p=0.006 does not carry nominal power. Validate on n≥20 *new* OVERLAP trades before installing. |
| 6 | Resolve config blacklist mismatch | **Option (D) — block ml_direct/XAUUSD in BOTH configs** | Both framings the briefing offered are post-hoc rationalizations of an unlogged silent config drift. Forward risk in BOTH regimes (rising and falling) requires blocking until zero-BUY is fixed. Document (D) even if business pressure selects (C). |
| 7 | Phase 7 includes XAUUSD zero-BUY investigation | **ELEVATE TO BLOCKING for Phase 8** | Zero-BUY on highest-volume symbol entering projected reversal regime is a Phase 8 gate, not a Phase 7 deliverable. |

---

## The single first action

**Open the meeting with R3 (vote 6) reframed as option (D).** State the +$21k as "data we are choosing to set aside" rather than "data validating our position". This anchors the meeting on institutional discipline before any other vote, and forces the same rigor onto votes 2, 3, and 7. Without this anchor, the +$21k creates downstream pressure to keep the broken model running.

---

## Three decisions that can wait

These can DEFER without cost — do not let them consume meeting time:

1. **Vote 8 — Phase 9 hosting (local Windows vs VPS).** Operational decision, not blocking for v3 evaluation. Defer to July.
2. **Specific Phase 7 task ordering (TSMOM vs Meta-Labeler timing).** Both are May 4 - Jun 8. Sequencing is the project lead's call, not a meeting-level decision.
3. **`ml_filtered_sma` retirement mechanics (config-flag vs strategy-class removal).** Vote 5 approves the retirement; the implementation detail can be decided in implementation, not in the meeting.

---

## Risks added (full detail in synthesis §5)

| ID | Title | Severity | Likelihood |
|---|---|---|---|
| R-EXT-001 | Gold regime reversal during Phase 8 | CRITICAL | HIGH |
| R-EXT-002 | ML training threshold bakes biases (manual trigger — verified) | MEDIUM | HIGH |
| R-EXT-003 | Schema-drift class not resolved without migrations | HIGH | MEDIUM |
| R-EXT-004 | Config-load-once + manual restart = stale-config window | MEDIUM | MEDIUM |

All four also persisted in `improvements.db::risks_register`. 16 action items in `improvements.db::action_items` (5 BLOCKING for Phase 8).

---

*Bottom line: the meeting's real question is not the schedule. It is whether the team confronts the framing or celebrates the +10.6% as accomplishment.*
