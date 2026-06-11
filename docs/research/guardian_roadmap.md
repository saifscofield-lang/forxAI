# Guardian — Methodology Guardian & Autonomous Research Framework — ROADMAP

**Status:** ACTIVE build (started 2026-06-11). Owner-approved.
**Source discussion:** memory `project-strategy-lab-idea` + the 2026-06-11 design debate.

This document is the durable record of *what we are building, why, and in what order*.
Every step is recorded here. Update this file as steps complete — do not let the plan
live only in chat.

---

## 1. The thing we are building

A **methodology guardian**: the component that decides, for any proposed trading
strategy/hypothesis, whether it has survived a rigorous falsification process — and
nothing an LLM says can soften that decision.

It is the foundation for everything later (strategy generators, regime systems, ML/RL
agents, autonomous research workflows). Build order: **Guardian first**, then a Workflow
clipped on top of it.

## 2. The one principle that drives the whole design

> **LLM agents at the edges (generative + interpretive). Deterministic code in the core
> (data, backtest, gates, holdout). The integrity of the system lives in the
> deterministic core — and nothing an agent says can corrupt the verdict.**

Corollary rules (these are law, not preferences):

1. **The verdict is computed, not argued.** PASS/FAIL comes from deterministic code
   comparing numbers to frozen thresholds. No LLM can convert FAIL→PASS.
2. **The separation that matters is `hypothesis ⊥ data`** (pre-registration + a locked
   holdout), *not* agent-role-vs-agent-role. More agents ≠ more statistical independence.
3. **Critics are diverse lenses with VETO power, never advocates seeking consensus.**
   Any one critic can fail a candidate; none can pass it. (No "Bull agent".)
4. **Multiple-testing is throttled at the front:** a human gate to *approve spending a
   test*, an append-only hypothesis registry, and a Deflated Sharpe penalty that rises
   with the test count. High per-hypothesis cost is a feature.
5. **Past failures raise the bar, never cast the vote** — qualitatively (novelty bar) and
   mathematically (DSR counter). They never directly reject a new idea.
6. **The backtest harness, data loader, cost model, and universe/windows are frozen
   infrastructure** no generative agent can touch. The Builder writes only the signal
   function that plugs into the frozen harness.

## 3. Architecture (target)

```
  LLM (generative/interpretive)        DETERMINISTIC CORE = the integrity
  ─────────────────────────────        ──────────────────────────────────
  Research advisor   ─┐
  Hypothesis advisor  ├─► pre-reg doc ─► [HUMAN GATE 1: worth a test?] ─► registry (append-only, git)
  (must state the     │                         │
   source of edge)    │                         ▼
  Builder (signal    ─┘             FROZEN backtest harness (code, seeded)
   function ONLY)                              │
                                               ▼
                              FROZEN gate engine (cost · WF · regime ·
                              DSR-with-counter · corr · Monte Carlo) → PASS/FAIL
                                               │
  Critic panel  ◄──────────────────────────────┤  each owns ONE failure mode,
  (veto-only; FLAG/explain;                    │  VETO power, never PASS power
   any veto = FAIL; can flag                    ▼
   gate defects → human, never relax)  [HUMAN GATE 2: cross to holdout?] ─► holdout (opened once)
                                               ▼
                                       [HUMAN GATE 3: capital?]
```

### Why this differs from the first 7-agent proposal
- `Backtest` and `Guardian PASS/FAIL` are **deterministic code, not LLM agents** — they
  must be reproducible bit-for-bit.
- The `Risk Committee` is reframed from *consensus among Bull/Bear/Risk/Statistician*
  into a **veto-only panel of distinct failure-mode lenses** (no advocate).
- A **second human gate is added at the front** (approve the pre-registration) — this,
  not the end gate, is what controls multiple-testing.

## 4. The critic panel (veto-only lenses)

Each owns one way to die; any single veto = FAIL; none can approve.

| Critic | Failure mode it owns | Primary evidence |
|---|---|---|
| Statistician | Multiple testing / luck | DSR w/ cumulative counter, #trades, #folds |
| Regime | Single-regime artifact (Carry lesson) | per-regime returns, attribution |
| Cost/Microstructure | Dies after frictions (Rescue lesson) | PF_net @1x and @1.5x, fill realism |
| Robustness | Fragile to perturbation | walk-forward spread, Monte Carlo, param sensitivity |

## 5. Lessons encoded (these ARE the gates)

- **Single-regime artifact** (Phase 11 Carry, C5): an edge present in only one macro
  regime is not an edge. Gate: *all regimes must be net-positive*.
- **Cost-survivability** (Rescue Phase 5): clean PF means nothing; PF_net after
  spread+slippage in ATR units is the test. Gate: *net-of-cost (and @1.5x) must be > 0*.
- **Multiple-testing / overfitting** (the lab's core risk): Deflated Sharpe Ratio whose
  bar rises with the number of tests in the registry.
- **OOS drift** (Phase 10 crypto): an OOS window that is significantly worse than train
  fails even if both are positive. Gate: *no significant drift + OOS Sharpe floor*.
- **Diversification validity, and the D5 gate-defect** (Phase 12 Trend): genuine
  independence is ENB / PC1 on *strategy* returns. Max-pairwise-corr is a
  universe-construction diagnostic, **not** a result gate — it fails any liquid universe
  with within-class duplicates. Encoded as a FLAG, never an auto-relaxation.

## 6. Gate-defect discipline (the Phase 12b rule, made law)

A critic may **flag** that a frozen gate looks mis-specified (e.g. D5 fails while ENB/PC1
strongly pass). That flag:
- **does NOT change the current verdict** — the frozen gate stands, the candidate stays
  FAIL on the data it was tested on;
- produces a separate artifact routed to a **human**, who may authorize a *new,
  separately pre-registered re-test* with a corrected gate.

Never relax a gate in place. Never let the analysis rewrite the exam it just failed.

## 7. Build steps (live checklist)

- [x] **S0** — Roadmap recorded (this file).
- [x] **S1** — Frozen gate spec: `docs/research/guardian_gate_spec.md` (metrics schema,
      gates G1–G8, thresholds, DSR formula + proxy, defect-detector rules).
- [x] **S2** — Deterministic engine: `research/guardian/` (`gates.py`, `engine.py`,
      `registry.py`). Pure functions; verdict computed, never argued.
- [x] **S3** — Golden cases + validation: Carry & Trend encoded in
      `research/guardian/cases.py`; `scripts/validate_guardian.py` asserts the engine
      reproduces `FAIL[C1,C3,C4,C5]` and `FAIL[D5]` **plus** the D5 gate-defect flag.
- [x] **S4** — Critic agent: `.claude/agents/methodology-guardian.md` (thin LLM critic,
      flag/explain only, never PASS).
- [x] **S5** — Seeded `data/hypothesis_registry.jsonl` (10 past hypotheses, K=10); ran
      validation — **both golden cases reproduced ✅**. (Not yet git-committed.)
- [~] **S6 (in progress)** — Workflow on top. **Stage 1 built + the deterministic bridge:**
      - `research/guardian/canonical.py` — canonical G1–G8 template + `assess()` (reads
        registry K, runs the engine). The verdict bridge — no LLM in the verdict path.
      - `scripts/guardian_assess.py` — CLI the verdict stage calls (input JSON → verdict
        report). Validated on a synthetic clean candidate (PASS, K=11).
      - `.claude/workflows/research-lab-prereg.workflow.js` — **Stage 1** autonomous
        workflow: novelty-check vs the failure registry → author a frozen pre-reg →
        **HALT at HUMAN GATE 1**. Never backtests, never reads holdout, never touches
        capital. (Invocable via `Workflow{name:'research-lab-prereg', args:'<idea>'}` —
        running it requires the owner's explicit opt-in.)
      - [ ] **Stage 2 (verdict)** — to build when a frozen pre-reg exists: Builder writes
        ONLY the signal fn into the frozen harness → deterministic backtest on
        Discovery/train → `guardian_assess.py` → veto panel (4 lenses) → **HALT at HUMAN
        GATE 2** (cross to holdout?). Design below.

### S6 Stage 2 — verdict workflow (design, not yet built)
Runs only AFTER a human freezes + commits a pre-reg (HUMAN GATE 1 passed). Steps:
1. **Builder** writes the strategy's signal function only, plugged into the frozen backtest
   harness (it may not touch the data loader, cost model, gates, or universe).
2. **Deterministic backtest** on Discovery/train data → raw metrics JSON.
3. **`guardian_assess.py`** → PASS/FAIL verdict + flags (the computed truth).
4. **Veto panel** — 4 critic agents (Statistician, Regime, Cost, Robustness), each owns one
   failure mode, each can VETO, none can approve. Any veto = FAIL.
5. **HALT at HUMAN GATE 2** — a PASS + clean panel produces a recommendation to cross to the
   locked holdout; the human decides. A gate-defect flag routes to a NEW pre-reg, never
   relaxes the verdict.

### S0–S5 result (2026-06-11)
`validate_guardian.py` green. Carry FAIL`[C1,C3,C4,C5]` + DEF-2 single-regime flag (DSR
0.152). Trend FAIL`[D5]` + DEF-1 gate-defect flag, verdict unchanged (DSR 0.961 — above the
0.95 bar at K=10, mechanically corroborating that Trend dies only on the mis-specified
max-corr gate). Foundation is trustworthy; S6 may be built on it.

## 8. Hard autonomy boundary

The autonomous loop is permitted **only** in the research/backtest sandbox on
Discovery/train data. It **must stop** at producing a ready pre-registration document and
a PASS/FAIL report. It never reads the holdout and never touches capital. Crossing to
holdout or capital requires an explicit human go/no-go.

## 9. Acceptance test for the Guardian (definition of "trustworthy")

Feed it the two cases whose answers we already know:
1. **Carry** → must return FAIL on `{C1, C3, C4, C5}` (regime artifact caught by C5).
2. **Trend** → must return FAIL on `{D5}` **and** raise a "D5 likely mis-specified"
   flag (because ENB 12.27 / PC1 0.17 pass strongly) **without** changing the FAIL.

If it reproduces both — faithful verdict + correct flag — the foundation is trustworthy
and S6 (the Workflow) may be built on it.

## 10. Related

memory: `project-strategy-lab-idea`, `project-phase11-carry-state`,
`project-phase12-trend-state`, `project-rescue-phase2to5-findings`,
`project-xauusd-validation-plan`.
Pre-regs this generalizes: `phase11_carry_prereg.md`, `phase12_trend_premium_prereg.md`.
