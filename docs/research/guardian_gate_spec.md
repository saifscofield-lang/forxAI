# Guardian — Frozen Gate Specification (v1)

**Frozen:** 2026-06-11. Changes require a version bump (v2, …) and a note in
`guardian_roadmap.md`. This is the law the engine in `research/guardian/` enforces.

The Guardian evaluates a **submission** (computed metrics for one hypothesis) against a
**declared frozen gate set** and returns a deterministic verdict. It additionally runs a
**defect detector** that may raise FLAGS — flags never change the verdict.

---

## 1. Submission schema

A submission is a plain dict (JSON-serializable):

```python
{
  "hypothesis_id":      str,    # e.g. "phase11_carry"  (key into the registry)
  "title":              str,
  "economic_rationale": str,    # WHY the edge should exist; must explain the source
  "prereg_commit":      str,    # git commit of the frozen pre-reg (or "" if pre-implementation)
  "declared_gates":     [GateSpec, ...],   # the gates frozen for THIS hypothesis
  "metrics": {
    # --- core return stats (per-period = the rebalance period, usually monthly) ---
    "mean_period":   float,     # mean per-period net return (fraction, e.g. 0.0022)
    "t_stat":        float,     # t-stat of mean_period vs 0
    "sharpe_ann":    float,     # annualized Sharpe of net returns
    "n_obs":         int,       # number of return periods (months) — DSR sample size
    "mpy":           int,       # periods per year (12 monthly, 252 daily) default 12
    "skew":          float,     # return skew (default 0.0)
    "kurtosis":      float,     # return kurtosis, normal=3 (default 3.0)

    # --- out-of-sample ---
    "oos": {"mean": float, "sharpe": float, "drift_p": float},
                                # drift_p = one-sided p that OOS < train (high = no drift)

    # --- regime robustness (the Carry C5 lesson) ---
    "regimes": {str: float, ...},   # regime_name -> mean per-period return; ALL must be >0

    # --- breadth ---
    "breadth": {"n_positive": int, "n_total": int},

    # --- cost-survivability (the Rescue lesson) ---
    "cost": {"net_mean_1x": float, "net_mean_1_5x": float, "pf_net": float},

    # --- diversification validity (the Phase 12 / D5 lesson) ---
    "diversification": {"enb": float, "pc1": float,
                        "max_corr": float, "n_instruments": int},

    # --- benchmark ---
    "beats_passive": bool
  }
}
```

Missing optional fields fall back to documented defaults. A gate whose required metric is
absent evaluates to **FAIL** with reason `"metric missing"` (never silently skipped).

## 2. GateSpec — how a frozen gate is expressed

Each declared gate is a small declarative record the engine knows how to evaluate:

```python
{"id": "C5", "kind": "all_positive", "path": "regimes",
 "desc": "all macro regimes net-positive"}

{"id": "C1", "kind": "all_of", "desc": "mean>0 and t>=2.0",
 "subs": [{"path": "mean_period", "op": ">",  "th": 0.0},
          {"path": "t_stat",      "op": ">=", "th": 2.0}]}

{"id": "D5", "kind": "all_of", "desc": "ENB/PC1/max-corr",
 "subs": [{"path": "diversification.enb",      "op": ">=", "th": 10.4},
          {"path": "diversification.pc1",      "op": "<",  "th": 0.50},
          {"path": "diversification.max_corr", "op": "<",  "th": 0.70}]}
```

Supported `kind`:
- `all_of` — every sub-condition holds (logical AND).
- `any_of` — at least one sub-condition holds.
- `all_positive` — every value in the dict at `path` is `> 0` (regime/breadth use).
- `n_positive` — `>= th` values in the dict at `path` are `> 0`.
- `threshold` — single `{path, op, th}`.
- `dsr` — the Deflated Sharpe gate (see §4); params `{alpha}` default 0.95.

`op` ∈ `>`, `>=`, `<`, `<=`, `==`. `path` is dotted (`diversification.enb`).

This keeps gates **data-driven**: a new pre-reg lists its own GateSpecs; the engine
evaluates exactly those, with no code change and no hidden relaxation.

## 3. Canonical recommended gate set (template for NEW hypotheses)

New pre-regs SHOULD start from this lessons-corrected default (they may add/strengthen,
never weaken without justification recorded in the pre-reg):

| id | name | rule | lesson |
|----|------|------|--------|
| G1 | Economic rationale | `economic_rationale` non-empty & states a source of edge | kills data-mined junk pre-build |
| G2 | Significance | `mean_period > 0` and `t_stat >= 2.0` | basic signal |
| G3 | Deflated Sharpe | `DSR(alpha=0.95)` passes at registry's K | **multiple testing** |
| G4 | OOS | `oos.mean > 0` and `oos.sharpe >= 0.30` and `oos.drift_p > 0.05` | OOS drift (Phase 10) |
| G5 | Regime | all `regimes` > 0 | **single-regime artifact (Carry)** |
| G6 | Breadth | `breadth.n_positive / n_total >= 0.5` | not one-instrument luck |
| G7 | Cost | `cost.net_mean_1_5x > 0` (and `pf_net > 1.0`) | **cost-survivability (Rescue)** |
| G8 | Diversification | `enb >= 0.4*n_instruments` and `pc1 < 0.50` | genuine independence |

**Note the deliberate omission:** the canonical G8 does **not** include `max_corr < 0.70`
as a hard sub-gate. Per the Phase 12 lesson, max-pairwise-corr is a universe-construction
diagnostic, not a result gate. It lives in the **defect detector** (§5), not in G8.

> The historical Phase 12 submission still *declares* the original D5 (with max_corr),
> because that is what was frozen at the time — the engine reproduces its FAIL faithfully.
> The canonical set is only the template for *future* pre-regs.

## 4. Deflated Sharpe Ratio (the multiple-testing gate)

Per López de Prado (2014), "The Deflated Sharpe Ratio".

Per-period Sharpe: `SR = sharpe_ann / sqrt(mpy)`.

Expected maximum Sharpe under `K` independent trials (the registry's test count):

```
γ  = 0.5772156649            # Euler–Mascheroni
z1 = Φ⁻¹(1 − 1/K)
z2 = Φ⁻¹(1 − 1/(K·e))
SR0 = sqrt(V) · [ (1−γ)·z1 + γ·z2 ]
```

where `V` = variance of the trial Sharpe estimates. We rarely have all trial SRs, so we
use the standard estimator-variance **proxy**:

```
V ≈ (1 − γ3·SR + (γ4−1)/4 · SR²) / (n_obs − 1)
```

(`γ3` = skew, `γ4` = kurtosis of returns). This is the same denominator family used in the
DSR statistic and is documented here as an explicit approximation; it is configurable.

Deflated Sharpe statistic (probability the true SR > SR0):

```
DSR = Φ( (SR − SR0) · sqrt(n_obs − 1) / sqrt(1 − γ3·SR + (γ4−1)/4 · SR²) )
```

Gate passes iff `DSR >= alpha` (default `alpha = 0.95`).

`K` (number of trials) is read from the **hypothesis registry** (§6 of roadmap; file
`data/hypothesis_registry.jsonl`). Every test ever run — including failures — increments
`K`. This is what makes the bar rise with data-mining. `K >= 1` always (a lone test still
deflates slightly via SR0 at K=1, which is ~0).

## 5. Defect detector (flags only — NEVER change the verdict)

Runs after the verdict on every submission. Each rule emits a FLAG with severity and a
human-routed recommendation. A flag is advisory: it may justify a *future, separately
pre-registered* re-test, but the current verdict stands.

**DEF-1 — max-corr / ENB contradiction (the D5 defect).**
If a declared gate failed *solely or partly* on a `max_corr`-style sub-condition, AND
`enb >= 0.4*n_instruments` AND `pc1 < 0.50`, emit:
> `FLAG[gate-defect]: max-pairwise-corr sub-gate likely mis-specified — companion ENB/PC1
> indicate genuine independence. Verdict UNCHANGED. Route to human for a corrected re-test
> (do NOT relax in place).`

**DEF-2 — single-regime artifact.**
If the regime gate failed because exactly one regime is strongly positive and the rest
non-positive, emit an explanatory flag naming the carrying regime (e.g. Carry = USDJPY
hiking era). Verdict unchanged. (Diagnostic, reinforces the FAIL.)

**DEF-3 — cost cliff.**
If clean stats pass but `cost.net_mean_1x <= 0` or `pf_net <= 1.0`, emit a flag: edge is a
pre-cost illusion. Verdict unchanged (G7 already fails it).

**DEF-4 — thin sample for DSR.**
If `n_obs < 36`, emit a flag that the DSR estimate is low-power; treat a DSR pass on a
short sample with suspicion.

## 6. Verdict object (engine output)

```python
{
  "hypothesis_id": str,
  "verdict": "PASS" | "FAIL",
  "passed":  [gate_id, ...],
  "failed":  [gate_id, ...],
  "details": {gate_id: "human-readable detail string"},
  "dsr": {"value": float, "K": int, "sr0": float, "passed": bool},
  "flags": [{"code": str, "severity": str, "message": str}, ...],
}
```

`verdict == "PASS"` iff **every** declared gate passed. Flags are reported alongside but
are independent of the verdict.

## 7. What the engine guarantees

1. **Determinism** — same submission + same registry K → same verdict, byte-for-byte.
2. **No relaxation** — the engine evaluates declared gates as frozen; it cannot drop or
   soften a gate. A mis-specified gate produces a FLAG, never a PASS.
3. **No LLM in the verdict path** — pure arithmetic. The critic agent consumes this output
   and may explain/flag, but has no write access to the verdict.
