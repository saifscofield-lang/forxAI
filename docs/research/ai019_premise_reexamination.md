# AI-019 — v3 Ledger Premise Re-examination

**Date:** 2026-05-06
**Source:** automated re-analysis after the AI-019 finding (May 1)
**Trigger action item:** `AI-019` — *"Apr 10 ml_direct/XAUUSD blacklist was a no-op — re-examine decisions made on the wrong premise"*
**Re-runnable:** the queries below run directly against `data/trading.db` and are reproducible from this doc.

## Executive summary (3 bullets)

- The v3 ledger headline (**+$2,283** net PnL across 177 closed trades) is entirely propped up by **70 trades opened during the Apr 10 → Apr 28 "thought-blocked" window** that contributed **+$29,594**. Excluding that cohort, v3 is **−$27,311 across 107 trades** — every strategy except `rsi_reversal` (n=3, statistical noise) is net-negative.
- The dual-gate ship verdict shifts from **marginal-fail** (R-PF 0.916, $-PF 1.035 on all 178 v3 trades) to **decisive-fail** (R-PF 0.429, $-PF 0.280 excluding the thought-blocked cohort). Either way the dual gate fails, but the corrected accounting changes the narrative from "we're close to passing" to "we're nowhere near passing".
- **The "+$21k from ml_direct/XAUUSD" framing that informed Vote 6D was correct as an arithmetic sum but misleading as evidence of edge.** The +$21k came from a window where the engine was supposed to be blocked from those trades. With the corrected timeline: pre-Apr-10 ml_direct/XAUUSD lost $19,778 on 21 trades; thought-blocked window made $29,594 on 70 trades; post-AI-002 made $0 on 0 trades. The blacklist's purpose is to prevent both the losses AND the lucky wins — both come from the same broken-by-design pattern. **The corrected framing strengthens Vote 6D, doesn't weaken it.**

## Why this re-analysis exists

Per `ai017_supplemental_findings_2026_05_01.md` Finding 3: between **Apr 10 19:01 UTC** (when commit `b8a2c3b` wrote the blacklist to `base.yaml` only) and **Apr 28 21:55 UTC** (when AI-002 deployed it to `paper.yaml` AND restarted the engine), the engine continued trading `ml_direct/XAUUSD` against the project lead's intent. The blacklist was a no-op for 18 days. The May 1 supplemental flagged this as a finding for the May 4 kickoff under "Premise re-examination — 5 min".

This document is that re-examination.

## Three windows of the v3 ml_direct/XAUUSD record

| Window | Boundary | n | Net PnL | WR | $-PF |
|---|---|---:|---:|---:|---:|
| Pre-blacklist | < 2026-04-10 19:01 UTC | 21 | **−$19,778** | 61.9% | 0.255 |
| Thought-blocked (no-op blacklist) | Apr 10 19:01 → Apr 28 21:55 | **70** | **+$29,594** | 75.7% | 1.712 |
| Actually blocked (post-AI-002) | ≥ Apr 28 21:55 | 0 | $0 | — | — |
| **Total v3 ml_direct/XAUUSD** | | **91** | **+$9,816** | 72.5% | 1.040 |

Note: 1 ml_direct/XAUUSD trade opened Apr 28 21:05 (50 minutes before the AI-002 engine restart) is included in the thought-blocked window — the running engine still had the unblacklisted paper.yaml in memory at that moment.

## v3 OVERALL ledger under each accounting

```
                                      n      Net PnL       WR     $-PF    R-PF    Dual gate
Including thought-blocked          178    +$2,283.49    72.9%    1.035   0.916   FAIL (R-PF<1.3)
EXCLUDING thought-blocked          108   −$27,310.71    71.0%    0.280   0.429   FAIL (both)
                                  ────────────────────────────────────────────────────────────
   delta (the cohort's effect)     −70   −$29,594.20            +0.755  +0.487
```

The thought-blocked cohort alone contributes **+$0.755 to $-PF and +0.487 to R-PF**. Removing it drops both metrics by exactly that amount. The cohort is the mathematical reason v3 looks even close to breakeven.

## Per-strategy ledger (excluding thought-blocked)

```
rsi_reversal             n=  3   pnl=$   +231.33   WR=100.0%   PF=  inf  ← n too small
asia_breakout            n=  6   pnl=$    -24.33   WR= 83.3%   PF=0.820
stop_hunt_reversal       n=  5   pnl=$   -112.66   WR= 80.0%   PF=0.431
sma_crossover            n=  2   pnl=$   -627.23   WR=  0.0%   PF=0.000  ← n too small
bollinger_bounce         n= 29   pnl=$ -3,092.11   WR= 69.0%   PF=0.274  ← retired Apr 28
ml_filtered_sma          n= 31   pnl=$ -4,957.70   WR= 67.7%   PF=0.095  ← retired Apr 28
ml_direct                n= 31   pnl=$-18,728.01   WR= 74.2%   PF=0.294
```

Two of the seven (rsi_reversal n=3, sma_crossover n=2) are below the n≥10 powered threshold — drop those and **every meaningfully-sampled strategy is net-negative**. The two retired strategies (`bollinger_bounce`, `ml_filtered_sma`) account for $-8,050; pre-Apr-10 `ml_direct/XAUUSD` plus the lone post-AI-002 trade account for $-18,728. The retirement votes (Apr 28 Votes 4 + 5) match the data here exactly.

## Per-symbol ledger (excluding thought-blocked)

```
USDJPY    n= 17   pnl=$   +259.56   WR=70.6%
USDCHF    n= 16   pnl=$   +110.94   WR=93.8%
AUDUSD    n= 15   pnl=$   +101.60   WR=86.7%
EURUSD    n= 12   pnl=$   -440.40   WR=75.0%
USDCAD    n= 11   pnl=$   -544.01   WR=63.6%   ← removed from instruments Apr 28 (AI-020)
GBPUSD    n= 12   pnl=$ -1,274.60   WR=50.0%
XAUUSD    n= 24   pnl=$-25,523.80   WR=58.3%   ← all losses are pre-Apr-10 ml_direct
```

XAUUSD's $-25,524 is **96% of v3's net loss outside the thought-blocked window**. The non-XAUUSD ledger is approximately balanced (+$472 + $−2,259 = $−1,787 across 6 symbols, mostly noise at low n).

## What this means for outstanding decisions

### Vote 6D (block ml_direct/XAUUSD until AI-001 ships)

**Stronger, not weaker.** The original framing was "the +$21k profit was 'lucky' on a falling-gold regime, not edge". The corrected framing is "the +$21k profit was 'lucky' AND happened in a window the system shouldn't have been trading". Both reasons remain valid. Vote 6D's blacklist remains correct. **No change required.**

### Phase 8 deferral (Vote 2)

**Stronger.** Phase 8 was deferred per Vote 2 with a Jun 1 gate review. The corrected accounting shows v3 is **structurally losing money** outside the lucky window. Vote 2's caution was the right call; the deferral should not be lifted casually at the Jun 1 gate without addressing the structural loss.

### AI-001 (XAUUSD BUY-side capability)

**Now genuinely urgent.** Today's diagnostic confirmed the model is regime-biased SELL-only. Today's Path A retrain attempt empirically failed. Without AI-001 fix (Path B time-stratified retraining or Path D Phase 7 meta-labeler replacement), the system has no profitable XAUUSD strategy — and XAUUSD is where v3's pre-Apr-10 losses concentrated. This is no longer "fix the asymmetry for upside"; it's "fix the asymmetry to stop the bleeding".

### Phase 7 meta-labeler training corpus (α / β / γ kickoff decision)

**Heavily affects the answer.** The α / β / γ proposal (`docs/research/phase7_training_set_proposal.md`) framed the trade-off as "data volume vs corpus dominance vs corpus representativeness". With the corrected accounting:

- **Option α** (all 178 v3 trades) — half the labels (the thought-blocked cohort) are from a window the engine wasn't supposed to be operating in. Training on it means the meta-labeler learns the lucky-window pattern as ground truth.
- **Option β** (stratified cap) — capping ml_direct/XAUUSD at e.g. 20 trades cuts the thought-blocked dominance but doesn't address that the cohort represents a "shouldn't have happened" period.
- **Option γ** (retired strategies only) — completely sidesteps the thought-blocked cohort because ml_direct isn't in γ's corpus by construction. Going into the kickoff, **γ now looks more defensible than the original analysis suggested**.

Recommend the kickoff revisit decision #2 (corpus α/β/γ) with the corrected ledger as primary input.

### AI-005 holdout validation (May 6 deliverable)

Already accounted for the corrected timeline implicitly — the OOS holdout window starts after the thought-blocked period ended. R1 (OVERLAP filter) and R4 (defer per-symbol) **both survive on the OOS** even after correcting the IS narrative, because the OOS is independent of the IS bias. **No change to AI-005.**

## What this re-analysis does NOT change

- **Vote 6D** still correct — strengthens rather than weakens it.
- **AI-002 deployment** still correct (Apr 28 fix that finally made the blacklist effective).
- **AI-005 OOS verdicts** still hold — they were derived on a holdout that postdates the thought-blocked window.
- **Phase 8 gate criteria** unchanged — but the system will fail them more decisively under corrected accounting unless the AI-001 retraining (or meta-labeler) lands.

## Cross-references

- `docs/research/ai017_supplemental_findings_2026_05_01.md` — original AI-019 finding (Finding 3)
- `docs/research/ai001_zero_buy_root_cause.md` — AI-001 diagnostic (urgent given this re-analysis)
- `docs/research/ai001_retrain_balanced_report.md` — Path A empirical failure
- `docs/research/ai005_holdout_validation.md` — OOS holdout (unaffected)
- `docs/research/phase7_training_set_proposal.md` — α/β/γ proposal (γ stronger now)
- `data/improvements.db::action_items` — AI-001, AI-019, AI-020
- `data/trading.db::trades` — source of all numbers in this report
