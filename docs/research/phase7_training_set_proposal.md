# Phase 7 — Meta-Labeler Training-Set Composition Proposal

**Date:** 2026-05-01
**Author:** automated proposal (Claude Code), per `docs/p.md` Phase 3 instructions
**Status:** **proposal only — no decision in this document.** Three options (α, β, γ) for the May 4 kickoff meeting to choose from.
**Prior context:** Phase 7 (`May 4 → Jun 8`) trains a meta-labeler on existing strategy signals. The composition of that training set determines what the labeler learns.

---

## Why this matters

The meta-labeler trains on closed trades labelled by outcome (`profitable=1/0`, with optional features that may include `exit_reason`, R-units, etc.). What it learns about "what to take" vs. "what to avoid" depends on which trades are in the training corpus.

The dominant cell in v3 trade history is `ml_direct/XAUUSD/SELL` at **92 of 174 v3 trades (53%)**. If left uncorrected, the meta-labeler trains predominantly on the structural-defect strategy that meeting Vote 6D ordered blocked. Conversely, excluding it leaves a thin training set (~71 trades) over a narrow strategy palette.

Two new constraints from this session:

1. **AI-017b SL_HIT mislabel contamination**: 26% of v3 SL_HIT trades are mislabelled (close near entry, not near SL). On `ml_direct` specifically: **38 of 76 SL_HIT trades (50%)**. Other strategies: **0% mislabel** (clean). Any option that uses `exit_reason` as a feature is contaminated proportional to ml_direct's share. Options that use only `pnl_sign`/`profitable` (label-only) route around the bug.
2. **MACD/RSI signal scarcity**: Phase 7 plan steps 6–7 train the meta-labeler on **MACD signals** (May 18–24) and **RSI signals** (May 25–31). v3 has **0 MACD trades** and **3 RSI trades**. MACD/RSI training MUST come from a backfill source (v1/v2 raw signals or signal_logs replay) regardless of which option below is chosen for the v3-base meta-labeler. Treat this as a separate orthogonal problem; the three options below cover only the v3-derived training corpus.

---

## v3 trade inventory (engine_version=2.4, n=174)

### By dominant cells

| Strategy × Symbol × Direction | n | wins | WR | comment |
|---|---:|---:|---:|---|
| **ml_direct / XAUUSD / SELL** | **92** | 67 | 72.8% | 50% AI-017b mislabel; the dominant cell |
| bollinger_bounce / GBPUSD / SELL | 6 | 2 | 33.3% | retired strategy (Vote 4) |
| bollinger_bounce / USDCAD / BUY | 5 | 4 | 80.0% | retired symbol + retired strategy |
| ml_filtered_sma / EURUSD / BUY | 4 | 2 | 50.0% | retired strategy (Vote 5), file kept |
| ml_filtered_sma / USDJPY / BUY | 4 | 3 | 75.0% | retired strategy |
| 37 other cells | n ≤ 3 each | — | — | mostly statistical noise alone |

Top 5 cells: **111 trades, 64% of corpus.** Bottom 37 cells: 63 trades, 36% — many at n=1.

### By strategy (with AI-017b exposure)

| Strategy | n | SL_HIT | Mislabels | % |
|---|---:|---:|---:|---:|
| ml_direct | 97 | 76 | 38 | **50.0%** |
| ml_filtered_sma | 31 | 30 | 0 | 0.0% |
| bollinger_bounce | 29 | 27 | 0 | 0.0% |
| asia_breakout | 6 | 6 | 0 | 0.0% |
| stop_hunt_reversal | 5 | 5 | 0 | 0.0% |
| rsi_reversal | 3 | 3 | 1 | 33.3% |
| sma_crossover | 2 | 2 | 0 | 0.0% |

**Total v3: 39/149 SL_HIT mislabelled (26%)**. Concentration is in `ml_direct`.

---

## Option α — All v3 trades, equal weighting

### Composition

- **Size:** 174 trades
- **Distribution:** as inventoried above. ml_direct/XAUUSD/SELL = 53% of corpus; 37 thin cells make up the long tail.
- **Inclusion of currently-retired strategies?** Yes (bollinger_bounce, ml_filtered_sma, asia_breakout, stop_hunt_reversal). Their tails contribute the "what NOT to take" signal.

### Predicted bias direction

- **Strategy bias:** ml_direct dominates → meta-labeler learns "good entry = ml_direct-shaped feature vector". Generalisation to ml_filtered_sma / bollinger_bounce / sma_crossover signals is questionable.
- **Symbol bias:** XAUUSD over-represented (~55% of dataset, since 92 trades are ml_direct/XAUUSD/SELL plus a handful from other strategies). EURUSD, GBPUSD, AUDUSD, USDJPY, USDCHF each get ~5–10% representation; the rest is split.
- **Direction bias:** SELL dominant on XAUUSD (the ml_direct zero-BUY structural defect). Meta-labeler may learn that "BUY signals on XAUUSD ≈ wins" without realising the BUY count is tiny.
- **Outcome class bias:** WR 72.4% across the corpus → label imbalance favouring positives. Standard mitigation (class weights or threshold tuning) applies.

### Validation method

- Walk-forward by `close_time` (no random shuffles; respect time order).
- **Purged K-fold CV** (Phase 7 plan step 2): 5 folds, gap = max trade duration (~1 day on XAUUSD ml_direct from inventory), to prevent label leakage from open-close overlap.
- **Concentration check** (Phase 7 plan step 10): no symbol-month should produce > 25% of the model's PnL on the validation slice. With 53% concentration in one cell, this check is likely to fail without explicit re-weighting at training time.
- **Phase 7 ship gate** (`phase7_ship_gate_definition.md`): R-PF ≥ 1.3 AND $-PF ≥ 1.0 on the held-out validation window.

### Interaction with AI-017b — **CONTAMINATED**

- **If `exit_reason` is used as a feature**: 50% of ml_direct's SL_HIT labels are wrong. ml_direct represents 56% of the corpus's SL_HIT trades. The "avoid SL_HIT" feature direction the labeler tries to learn is approximately measuring "avoid break-even break-even-stop / trailing-stop closes that happen to be tagged SL_HIT" — counter-productive. Net effect: the labeler learns a noisy version of "avoid trailing stops on ml_direct" instead of "avoid actual stop-outs". Meta-labeler precision drops; recall drops; model becomes unreliable.
- **If only `pnl_sign` / `profitable` is used as label, no `exit_reason` feature**: route around AI-017b. Profitable=True/False is computed from `pnl > 0` which is unaffected by the comment-substring bug. **This is the only safe path for Option α.**
- **Concrete recommendation if α is chosen**: explicitly forbid `exit_reason`, `slippage_pips`, and any derived "SL_HIT proximity" features in the training feature set until AI-017b ships. Document the constraint in the training script header.

### Risk summary

- HIGH: domination by ml_direct/XAUUSD/SELL biases the model toward a strategy that meeting Vote 6D ordered blocked.
- HIGH: concentration check will likely fail without re-weighting.
- MED: AI-017b contamination — manageable if `exit_reason` is excluded from features; serious otherwise.
- LOW: dataset size (174) is adequate for a meta-labeler if features are kept compact.

---

## Option β — Stratified sampling per (symbol × direction), cap N per cell

### Composition

- **Size:** depends on cap. Two illustrative caps:

| Cap (N) | Total trades retained | ml_direct/XAUUSD/SELL retained | Trades dropped |
|---|---:|---:|---:|
| 20 | 102 | 20 (of 92) | 72 |
| 15 | 97 | 15 (of 92) | 77 |
| 10 | 92 | 10 (of 92) | 82 |

- All non-dominant cells (n ≤ 6) pass through unchanged at any reasonable cap.
- Sampling method within capped cell: choices are (1) random uniform, (2) most-recent first, (3) stratified by outcome (preserve win/loss ratio), (4) stratified by exit_reason. The kickoff would need to choose; (3) preserves outcome distribution and is the safest default.

### Predicted bias direction

- **Strategy bias:** dramatically reduced. With cap=20, ml_direct drops from 53% → 20% of corpus.
- **Symbol bias:** still XAUUSD-heavy in absolute count, but no longer dominated by one cell.
- **Direction bias:** still SELL-skewed on XAUUSD because of the dominance there, but reduced.
- **Outcome class bias:** WR depends on the sampling method. Method (1) random uniform: WR drifts to ml_direct's 72.8% on the retained 20, mixed with non-ml_direct cells' average WR ~70% → corpus WR stays around 71%. Method (3) stratified preserves the original 72.4%.

### Validation method

- Same as α (walk-forward, purged K-fold, concentration check, ship gate).
- **Add:** sensitivity test — run training at 3 cap values (15, 20, 25) and inspect ship-gate stability. If the verdict flips on cap value, the model is over-fitting the dominant cell and the result isn't robust.
- **Concentration check** is now likely to PASS at cap 20 (no cell > 20% of corpus → no symbol-month likely > 25% of PnL).

### Interaction with AI-017b — **STILL CONTAMINATED, partially attenuated**

- Random sampling within ml_direct preserves the **50% mislabel rate** in the retained 20 — half of those will still be break-even-tagged-as-SL_HIT.
- Other cells (29 trades on bollinger_bounce, 31 on ml_filtered_sma, etc.) are at 0% mislabel — they enter the corpus clean.
- **Net mislabel rate at cap=20**: (20 × 0.50) + (82 × 0.0 within the 0%-cells' SL_HIT subset) ≈ 10 mislabels in a 102-trade corpus, or **~10%** of total. Down from 26% in Option α but still non-trivial.
- **Mitigations**: (1) sample within ml_direct stratified to exclude `pnl ≈ +$2 break-even cohort` (a heuristic filter for the AI-017b-affected rows); (2) same `exit_reason`-feature-exclusion as Option α.

### Risk summary

- MED: cap value is a tunable knob the kickoff would need to fix; sensitivity tests help.
- MED: AI-017b contamination reduced from 26% → ~10% but not zero. `exit_reason` feature exclusion still mandatory.
- LOW: dataset size (~100) is on the small side for a meta-labeler with many features; feature-count budget will be tight.
- LOW: throws away 70+ trades of ml_direct signal that, *if AI-017b were fixed*, would have been usable.

---

## Option γ — Excluded ml_direct entirely; train on retired strategies' tails

### Composition

- **Size:** 174 − 97 (ml_direct) − 2 (sma_crossover, n=2 — drop for n<5 floor) − 3 (rsi_reversal, n=3 — drop for n<5 floor) = **72 trades**.
- **Strategies retained (all currently retired or commented-out):**
  - ml_filtered_sma: 31 (retired Vote 5, 2026-04-28)
  - bollinger_bounce: 29 (retired Vote 4, 2026-04-28)
  - asia_breakout: 6 (archived 2026-04-30)
  - stop_hunt_reversal: 5 (archived 2026-04-30)
  - macd_crossover: 0 — does not appear in v3 (will need v1/v2 backfill regardless of option)

### Predicted bias direction

- **Strategy bias:** training corpus consists entirely of strategies the meeting decided to RETIRE. The meta-labeler learns the "what NOT to take" pattern by definition.
- **Symbol bias:** much flatter. ml_filtered_sma's 31 trades are split 7-symbol-wide; bollinger_bounce's 29 split 5-symbol-wide. No single cell exceeds ~6 trades.
- **Direction bias:** balanced — the retired strategies have both BUY and SELL representation (unlike ml_direct's near-zero-BUY pattern).
- **Outcome class bias:** WR varies — bollinger_bounce v3 was 69%, ml_filtered_sma v3 was 68%, but both with PF < 0.3 (the pathology that retired them). So class balance is similar to α/β but **trade outcomes are unrepresentative of profitable trading**.

### Validation method

- Walk-forward + purged K-fold as in α/β.
- **Distinct treatment**: since the corpus is "what NOT to take" by construction, the labeler's binary output should be reframed: **predict whether a signal of the retired-pattern shape is profitable or not**. The labeler isn't learning to identify good trades; it's learning to identify which signals from retired strategies would have been salvageable. This is closer to a "rescue meta-labeler" than a "validation meta-labeler".
- **Compare against α/β baselines**: train all three labelers and inspect whether γ's labeler offers any uplift on the held-out non-retired (ml_direct + future) signals it never saw in training. If γ generalises, that's evidence the labeler learned a transferable pattern. If not, γ is academic.

### Interaction with AI-017b — **CLEAN (routes around the bug)**

- **0% AI-017b mislabel exposure** in this corpus (ml_direct excluded; rsi_reversal's 1 mislabel is below the n<5 cutoff so the strategy is dropped).
- `exit_reason` features can be used safely.
- **The cleanest option from a data-quality perspective.**

### Risk summary

- HIGH: dataset is small (72) for a multi-feature meta-labeler. F1 confidence intervals will be wide.
- HIGH: corpus is structurally biased toward losing strategies. The labeler learns avoidance rather than selection. May not generalise to ml_direct or future strategies.
- HIGH: kickoff plan step 11 ship gate (F1 ≥ 0.55 + PF ≥ 1.3 on 6mo OOS) is hard to meet on a 72-trade corpus — Phase 7 may go fundamentally over budget if γ is chosen.
- LOW (paradoxically): AI-017b is a non-issue here.

---

## Comparison summary

| Dimension | α (all v3) | β (cap N=20) | γ (retired only) |
|---|---|---|---|
| Training set size | 174 | ~102 | 72 |
| Mislabel exposure | 26% | ~10% | **0%** |
| `exit_reason` feature usable? | Only if AI-017b ships first | Only if AI-017b ships first | **Yes** |
| Concentration risk (top cell %) | 53% | 20% | <10% |
| Generalises to live strategies? | Likely (ml_direct over-fit risk) | Likely (more balanced) | Unclear (corpus is retired-strategy-only) |
| Phase 7 ship gate likely to pass? | Possible if reweighted | Probable | Hard at n=72 |
| Data quality / cleanness | Lowest | Mid | **Highest** |

## Decision-needed inputs (kickoff)

1. **Pick one of α / β / γ** for the v3-derived corpus. The MACD/RSI scarcity (0 + 3 trades) requires a separate backfill plan regardless.
2. **If β**: choose cap N (suggested: 20) and within-cell sampling method (suggested: stratified-by-outcome).
3. **AI-017b sequencing decision**: ship the AI-017b fix BEFORE Phase 7 Step 6 (May 18) so α/β can use `exit_reason` cleanly, or skip the feature category entirely for the v3-derived labeler.
4. **MACD/RSI backfill source**: v1/v2 trades (with regime caveats), `signal_logs` replay, or shift Phase 7 step ordering to start with strategies that have data.

## Files this session

- This document (new — `docs/research/phase7_training_set_proposal.md`).
- `data/improvements.db`: AI-004b phase update (9→8), AI-020 added (USDCAD removal), AI-017 cross-link.
- `docs/research/decision_log.md`: USDCAD drop entry appended.
- No edits to `optimized_params.yaml`, `paper.yaml`, `base.yaml` (engine restart still pending; Rule 2 + Rule 6).

## Cross-references

- `docs/research/ai017_rr_audit.md` (yesterday)
- `docs/research/ai017_supplemental_findings_2026_05_01.md` (today)
- `docs/research/phase7_ship_gate_definition.md`
- `docs/research/phase7_blocker_2_audusd_usdcad_rr_analysis.md`
- AI-017, AI-017b, AI-019, AI-004b, AI-020 in `data/improvements.db::action_items`
