# ForexAI — Briefing for External Review

*Prepared 2026-04-28 for an outside second-opinion session (claude.ai or any other AI assistant). This is the minimal context an external reviewer needs to assess project health and advise on direction.*

---

## How to use this briefing

1. **Open claude.ai** in an incognito/private window (so the new session starts fresh, without your usual Claude context).
2. **Upload the 4 attached files** (listed at the bottom) OR paste this briefing + the most relevant 1-2 attached docs.
3. **Use the prompt template at the end** — it's calibrated to get useful skeptical review rather than generic praise.

---

## 1. What this project is (one paragraph)

Algorithmic forex trading system on a $100k MetaTrader 5 demo account. Single developer, ~37 days of paper trading data accumulated to date (2026-03-18 → 2026-04-28). The system has gone through three engine versions: v1 (OLD, pre-risk-controls, "lucky"), v2 (TRANSITION, construction zone, lost money), and v3 (STABLE, current, frozen at v2.4 since 2026-04-17). A v4 strategic pivot to crypto was attempted and formally rejected on 2026-04-22 (regime filter null-result). A go/no-go meeting is happening **today (2026-04-28)** to decide whether to proceed with v3.0 build-out (Phase 5 → 6/7) and a Jun 8 paper-trading start.

---

## 2. Current state (as of 2026-04-28 meeting day)

### Numbers

| metric | value |
|---|---:|
| Total trades all versions | 315 (314 closed) |
| v1 net PnL (132 trades, 13 days) | +$18,637 |
| v2 net PnL (46 trades, 10 days) | −$26,472 |
| v3 net PnL (137 trades, 18+ days) | **+$18,441** |
| Cumulative since 2026-03-18 | **+$10,607 from $100k start (+10.6%)** |

### Concentration risk
- **77 of 137 v3 trades (56%) are XAUUSD.** Every other symbol has ≤12 trades.
- **All 105 XAUUSD trades across all 3 versions are SELL.** Zero BUYs ever — structural model bias.
- **XAUUSD alone is +$21,110 in v3.** Without it, v3 is **−$2,669**.

### Identified failure modes
1. **OVERLAP session (13:00-17:00 UTC) is loss-concentrated for XAUUSD:** 24 trades, **−$18,701 net**. Other sessions on XAUUSD are strongly positive. Fisher exact p ≈ 0.006.
2. **`bollinger_bounce` strategy: 68% WR but losing money** (25 trades, −$3,006). R:R 0.12 — small wins, big losses. Profit factor 0.26.
3. **`ml_filtered_sma` strategy: same pathology** (22 trades, 68% WR, −$1,338).
4. **Two known recent silent bugs** (both fixed):
   - Schema-drift bug killed shadow-signal pipeline 2026-04-16 → 2026-04-22 (6 days lost)
   - Two further latent schema-drift candidates were closed in cleanup
5. **Config-vs-reality mismatch found this morning:** `config/base.yaml` defines a XAUUSD blacklist for ml_direct (the profitable strategy) but the engine actually loads `config/paper.yaml`, which has no blacklist. Pure luck — had it been mirrored, the +$21k profit would have been blocked.

### Phase plan
- Phase 5 (v3.0 Pre-Build): mostly complete. Today's meeting decides if 6 of 8 gate items GREEN is enough to advance.
- Phase 6 (TSMOM layer): planned for May 4
- Phase 7 (Meta-Labeler Rebuild): planned for May 4 - Jun 8
- Phase 8 (v3.0 Paper Trading, 6 weeks): planned for Jun 8 - Jul 20
- Phase 9 (Live trading $2k): Sep 1+ (skipping August low liquidity)
- Phase 10 (v4 research): **closed 2026-04-22, RED, pivoting to a different track**
- Phase 10.5: closed (regime-filter null result)

---

## 3. Recent decisions (last 7 days)

| date | decision | verdict |
|---|---|---|
| 2026-04-22 | v4 crypto momentum (Phase 10) — formal closure | RED, REJECTED |
| 2026-04-22 | Shadow-pipeline schema-drift bug fixed (1-line ORM Column declaration) | RESOLVED |
| 2026-04-22 | Latent drift cleanup on Trade + TradeResult ORM models | RESOLVED |
| 2026-04-24 | Comprehensive trade evolution analysis produced (281 trades) | DELIVERED |
| 2026-04-28 | Today's go/no-go meeting recommendations identified (R1-R7) | PENDING DECISION |

Full decision history: `docs/research/decision_log.md`.

---

## 4. The 04-28 meeting agenda (decisions on the table)

**Today's meeting must vote on:**

| # | Question | Recommended | Confidence |
|---|---|---|---|
| 1 | Phase 5 → 6/7 transition? May 4 vs May 10 | **YES, May 4** | HIGH (6/8 gates green) |
| 2 | Phase 8 paper-trading start: Jun 8 vs Jun 14 | Jun 8 (no slip) | MEDIUM |
| 3 | Block XAUUSD OVERLAP session (13-17 UTC) | **YES** | HIGH (n=24, p=0.006) |
| 4 | Retire/restructure `bollinger_bounce` | **YES** | HIGH (n=25, structural R:R) |
| 5 | Retire/restructure `ml_filtered_sma` | **YES** | HIGH (n=22, same pathology) |
| 6 | Resolve config blacklist mismatch (port to paper.yaml? remove from base.yaml? modified version?) | Modified (add OVERLAP block, remove XAUUSD ml_direct) | HIGH |
| 7 | Phase 7 model audit scope: include XAUUSD zero-BUY asymmetry investigation | YES | MEDIUM |
| 8 | Phase 9 hosting: local Windows vs VPS — defer to July? | Defer | LOW priority for today |

---

## 5. Where I want your advice

I'd appreciate a **skeptical outside review** focused on these questions specifically — please prioritize honesty over reassurance:

### A. Is the project actually progressing?

After 37 days, the account is +10.6%. Is this a sign of a working system, or could it be noise + one symbol's lucky run? If you'd never seen this project before, what would you conclude from the data?

### B. Is the XAUUSD concentration appropriate or alarming?

77 of 137 v3 trades in one symbol. The whole "v3 is profitable" story collapses if XAUUSD is removed. Should the meeting:
- Accept this and continue (because v3.0 paper trading is just data collection)?
- Mandate diversification before Phase 8?
- Stop and rebuild the strategy mix to reduce concentration?

### C. Are we self-deceiving on the OVERLAP filter?

The Fisher p-value is 0.006 on n=24, which sounds significant. But:
- It's still small-sample (24 OVERLAP trades vs 113 non-OVERLAP)
- The hypothesis was generated *after* looking at the same data we're testing on (data dredging risk)
- v1 OVERLAP was profitable, v2/v3 OVERLAP is bad — what changed?

How worried should I be about overfitting this filter? What would falsify it before Phase 8 starts?

### D. The "happy accident" on the blacklist

The XAUUSD ml_direct blacklist exists in `base.yaml` but the engine actually loads `paper.yaml` which has no blacklist. The unblocked strategy made +$21k. Two readings:
- "Process failure that worked out — fix the process"
- "The original blacklist was based on v2's bad regime; v3 invalidated it. The accidental absence is correct now."

Which reading is right? What's the institutional-quality way to handle a config-vs-policy gap like this?

### E. Phase 8 readiness

Phase 8 is 6 weeks of paper trading with ML-trained meta-labelers (Phase 7's deliverable). Given:
- `bollinger_bounce` and `ml_filtered_sma` both showing the "high WR, low PF" pathology
- Schema-drift bugs revealed in code that's been "frozen"
- One symbol carrying everything

Is the system ready to start Phase 8 on Jun 8, or is that aggressive?

### F. v4 closure — was rejecting v4 crypto right?

We rejected v4 cleanly on null-result. But there's a question whether the regime filter was the right rescue attempt at all. The OOS window was a low-vol downtrend; the filter was designed for high-vol chop. Did we test the wrong hypothesis?

---

## 6. Attached files (upload these to your second-opinion session)

The 4 most informative documents, in priority order:

1. **`docs/research/full_trade_evolution_report_2026-04-28.md`** (~25 pages) — the comprehensive analysis. Includes Wilson CIs, p-values, every claim sourced. **Most important attachment.**
2. **`docs/meetings/2026_04_28_v3_go_nogo.md`** (~3 pages) — the meeting agenda being decided today.
3. **`docs/research/decision_log.md`** (~2 pages) — running log of every formal decision since 2026-04-21.
4. **`docs/research/xauusd_sell_analysis.md`** (~5 pages) — the focused XAUUSD investigation that drives R1 (OVERLAP filter).

If the second-opinion AI can only take one attachment, prioritize the **full trade evolution report**.

Optional supporting files (only if questions get specific):
- `docs/research/shadow_signals_incident.md` — the schema-drift bug story
- `docs/research/regime_filter_results.md` — v4 closure null-result
- `docs/v4_framework.md` — strategic blueprint
- `artifacts/all_trades_enriched.csv` — raw data (262 KB)

---

## 7. Prompt template for the second-opinion session

Copy this into the new claude.ai session along with the uploaded files:

> I'm a solo developer running an algorithmic forex trading system on a paper-trading demo account. I'm having a go/no-go meeting today and want a skeptical outside review before I make decisions.
>
> The attached `BRIEFING_FOR_EXTERNAL_REVIEW.md` summarizes the state. The other attachments contain the underlying analysis.
>
> I want you to read this **as a skeptical reviewer**, not a cheerleader. Specifically:
>
> 1. Read §5 ("Where I want your advice") in the briefing — there are 6 specific questions (A-F).
> 2. For each, give me your honest answer. If you think I'm self-deceiving, say so.
> 3. Identify **at least 2 things you think I'm getting wrong or missing** that aren't already in the briefing.
> 4. Tell me what you'd do differently if you were leading this project.
>
> Don't soften your answers. I'd rather hear "your data is too small to support that conclusion" than a polite version. The decisions today will compound for months.
>
> Take your time. Quality over speed. If you need clarification on any data point, ask.

---

## 8. Things to watch for in the response

When you get the second opinion, calibrate trust by these signals:

**Good signs:**
- Specific objections with reasoning (e.g., "the n=24 OVERLAP sample's CI for the failure rate is [33%, 75%] — wide enough that you can't claim 54% is the truth")
- Disagreement with my recommendations, not just nuance
- Identifies risks I didn't flag (e.g., "what happens to the system if XAUUSD reverses and the SELL bias becomes a liability?")
- Says "I don't know" when the data doesn't support a claim

**Bad signs (means the second opinion isn't useful):**
- Generic praise without specifics
- Agreement with all my framings
- Lists of items I should "consider" without substance
- Refusal to take a position on anything

If the response is mostly bad-signs, push back hard with: *"You're being too agreeable. What's the strongest argument that v3 is not actually working?"*

---

*End of briefing. Upload this + the 4 priority attachments + paste the prompt template = useful second opinion in 5-10 min.*
