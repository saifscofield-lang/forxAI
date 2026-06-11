export const meta = {
  name: 'research-lab-prereg',
  description: 'Stage 1 of the autonomous research lab: novelty-check a hypothesis against the failure registry, then author a frozen pre-registration. HALTS at HUMAN GATE 1 — never backtests, never reads holdout, never touches capital.',
  whenToUse: 'When evaluating whether a NEW strategy hypothesis is worth spending a pre-registered test on. Pass the hypothesis idea as args.',
  phases: [
    { title: 'Novelty', detail: 'research advisor checks the idea vs the dead-idea registry + lessons' },
    { title: 'Pre-register', detail: 'hypothesis advisor authors a frozen pre-reg with canonical gates' },
  ],
}

// args = the hypothesis idea. Accept a bare string or {idea, hypothesis_id}.
const idea = (typeof args === 'string' ? args : (args && args.idea)) || ''
const hypId = (args && args.hypothesis_id) || ''
if (!idea) {
  log('No hypothesis idea provided in args. Pass a string or {idea, hypothesis_id}.')
}

const NOVELTY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['states_source_of_edge', 'novel', 'resembles', 'must_differ', 'registry_K', 'recommendation', 'reasoning'],
  properties: {
    states_source_of_edge: { type: 'boolean', description: 'Does the idea explain WHY an edge should exist (a causal mechanism), not just a pattern?' },
    novel: { type: 'boolean', description: 'Is this materially different from hypotheses already FAILED in the registry?' },
    resembles: { type: 'array', items: { type: 'string' }, description: 'hypothesis_ids in the registry this idea resembles' },
    must_differ: { type: 'array', items: { type: 'string' }, description: 'Concrete things that must differ from the resembled dead idea for this to be worth a test' },
    registry_K: { type: 'integer', description: 'Current number of distinct hypotheses in data/hypothesis_registry.jsonl' },
    recommendation: { type: 'string', enum: ['worth_a_test', 'reject_pre_implementation', 'needs_sharper_hypothesis'] },
    reasoning: { type: 'string', description: 'Falsification-minded justification, base-rate aware. Do NOT advocate; report evidence.' },
  },
}

phase('Novelty')
const novelty = await agent(
  `You are the RESEARCH ADVISOR of a forex strategy lab whose discipline is FALSIFICATION, not validation.
A hypothesis idea has been proposed:

"""${idea}"""

Your job is to decide whether this is even worth spending a pre-registered test on. Do this:
1. Read data/hypothesis_registry.jsonl — every hypothesis EVER tested (all FAILED so far). Count the distinct hypothesis_ids (that is registry_K).
2. Skim the lessons in docs/research/guardian_gate_spec.md (§3, §5) and the memory of past failures (Rescue = no price-only TA edge; Carry = single-regime artifact; Trend = died only on a mis-specified max-corr gate).
3. Judge the idea on TWO axes:
   - Does it state a SOURCE OF EDGE (a causal/economic mechanism), or is it just a pattern? If it cannot explain WHY the edge exists, recommend 'reject_pre_implementation'.
   - Is it materially novel vs the dead ideas? If it resembles a failed one, it is NOT auto-rejected — instead raise the bar: list exactly what must DIFFER for a re-test to be worth it.
Rules: be base-rate aware (almost everything fails). NEVER advocate for the idea or recommend a research direction; report evidence and let the gates judge later. History raises the bar, it does not cast the vote.
Return the structured verdict.`,
  { label: 'research-advisor', phase: 'Novelty', schema: NOVELTY_SCHEMA, agentType: 'Explore' }
)

if (novelty && novelty.recommendation === 'reject_pre_implementation') {
  log(`Research advisor REJECTS pre-implementation: ${novelty.reasoning}`)
  return {
    stage: 'novelty',
    halted_reason: 'rejected_pre_implementation',
    novelty,
    human_gate_1: 'No pre-registration authored — the idea does not state a source of edge. Sharpen the mechanism or drop it.',
  }
}

phase('Pre-register')
const prereg = await agent(
  `You are the HYPOTHESIS ADVISOR of a forex strategy lab. The research advisor judged the idea worth a test (or in need of a sharper hypothesis). Author a FROZEN pre-registration document in Markdown for:

"""${idea}"""

Research-advisor findings (incorporate them):
${JSON.stringify(novelty, null, 2)}

The pre-reg MUST contain, ex-ante (before any data is seen):
1. **Hypothesis & source of edge** — one falsifiable sentence + the causal/economic mechanism.
2. **Universe & windows** — exact instruments, date range, train/OOS split, and a LOCKED HOLDOUT that this process will never read. Chosen by tradability/availability, NEVER by results.
3. **Rule** — the exact, canonical strategy logic. No tuning, no free parameters chosen post-hoc.
4. **Cost model** — per-trade spread+slippage in ATR units (the Rescue lesson).
5. **Frozen gates** — adopt the canonical set G1-G8 from docs/research/guardian_gate_spec.md §3 with concrete thresholds for THIS universe. Do NOT include max-pairwise-corr as a hard gate (Phase 12 D5 defect); it is a diagnostic flag only. State that the Guardian engine (research/guardian/) computes PASS/FAIL — no human or LLM relaxes a gate.
6. **Decision rule** — ALL gates must pass; any fail = FAIL; no post-hoc gate relaxation (a mis-specified gate routes to a NEW separately pre-registered re-test).
7. **Multiple-testing disclosure** — note that this is trial K+1 against the registry; the Deflated Sharpe bar (G3) rises accordingly.

Read docs/research/phase12_trend_premium_prereg.md and phase11_carry_prereg.md as format references. Output ONLY the pre-registration Markdown — it must be ready for a human to freeze and git-commit. Do not run any backtest. Do not read any holdout file.`,
  { label: 'hypothesis-advisor', phase: 'Pre-register', agentType: 'Explore' }
)

const slug = (hypId || idea).toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 40).replace(/^_+|_+$/g, '')

return {
  stage: 'prereg_ready',
  novelty,
  prereg_markdown: prereg,
  suggested_path: `docs/research/prereg_${slug || 'hypothesis'}.md`,
  human_gate_1: [
    'HUMAN GATE 1 — worth a test?',
    'Review the pre-registration above. If you approve:',
    '  1. Save it to the suggested_path and git-commit it (this FREEZES the gates).',
    '  2. Append this hypothesis to data/hypothesis_registry.jsonl (increments K).',
    '  3. Only THEN run the backtest + scripts/guardian_assess.py for the verdict.',
    'This workflow stops here by design — it never backtests, reads the holdout, or touches capital.',
  ].join('\n'),
}
