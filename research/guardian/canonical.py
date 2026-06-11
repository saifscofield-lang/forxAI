"""Canonical gate template + the deterministic Guardian bridge.

`build_submission(meta, metrics)` attaches the lessons-corrected canonical gate set
(G1-G8) to a metrics dict, and `assess(submission)` reads the multiple-testing count K from
the hypothesis registry and runs the engine. This is the deterministic bridge the research
Workflow's verdict stage calls — no LLM in the verdict path.

The canonical set is the template for NEW pre-regs. Note G8 deliberately OMITS the
max-pairwise-corr sub-gate (the Phase 12 D5 defect) — that diagnostic lives in the engine's
defect detector, not as a result gate. See docs/research/guardian_gate_spec.md §3.
"""
from __future__ import annotations

import math

from research.guardian.engine import evaluate
from research.guardian.registry import HypothesisRegistry


def build_canonical_gates(metrics: dict) -> list[dict]:
    """Construct G1-G8 for a submission. Dynamic thresholds (G6, G8) are computed from the
    submission's own breadth/diversification so the spec's relative rules hold."""
    n_total = (metrics.get("breadth") or {}).get("n_total", 0) or 0
    n_inst = (metrics.get("diversification") or {}).get("n_instruments", 0) or 0
    breadth_th = 0.5 * n_total                 # >= half the universe positive
    enb_th = 0.4 * n_inst                      # ENB >= 40% of instrument count

    return [
        {"id": "G1", "kind": "threshold", "desc": "economic rationale stated",
         "path": "economic_rationale_present", "op": "==", "th": True},
        {"id": "G2", "kind": "all_of", "desc": "significance: mean>0 & t>=2.0",
         "subs": [{"path": "mean_period", "op": ">", "th": 0.0},
                  {"path": "t_stat", "op": ">=", "th": 2.0}]},
        {"id": "G3", "kind": "dsr", "desc": "Deflated Sharpe vs registry K", "alpha": 0.95},
        {"id": "G4", "kind": "all_of", "desc": "OOS + no drift",
         "subs": [{"path": "oos.mean", "op": ">", "th": 0.0},
                  {"path": "oos.sharpe", "op": ">=", "th": 0.30},
                  {"path": "oos.drift_p", "op": ">", "th": 0.05}]},
        {"id": "G5", "kind": "all_positive", "desc": "all regimes net-positive",
         "path": "regimes"},
        {"id": "G6", "kind": "threshold", "desc": ">= half the universe positive",
         "path": "breadth.n_positive", "op": ">=", "th": breadth_th},
        {"id": "G7", "kind": "all_of", "desc": "cost-survivable @1.5x and PF_net>1",
         "subs": [{"path": "cost.net_mean_1_5x", "op": ">", "th": 0.0},
                  {"path": "cost.pf_net", "op": ">", "th": 1.0}]},
        {"id": "G8", "kind": "all_of", "desc": "diversification (ENB/PC1; max-corr is a FLAG)",
         "subs": [{"path": "diversification.enb", "op": ">=", "th": enb_th},
                  {"path": "diversification.pc1", "op": "<", "th": 0.50}]},
    ]


def build_submission(meta: dict, metrics: dict) -> dict:
    """Wrap raw backtest metrics into a Guardian submission with canonical gates.

    `meta` carries hypothesis_id, title, economic_rationale, prereg_commit.
    """
    metrics = dict(metrics)  # don't mutate caller's dict
    rationale = (meta.get("economic_rationale") or "").strip()
    metrics["economic_rationale_present"] = bool(rationale)
    return {
        "hypothesis_id": meta.get("hypothesis_id", ""),
        "title": meta.get("title", ""),
        "economic_rationale": rationale,
        "prereg_commit": meta.get("prereg_commit", ""),
        "declared_gates": build_canonical_gates(metrics),
        "metrics": metrics,
    }


def assess(submission: dict, registry: HypothesisRegistry | None = None) -> dict:
    """Run the deterministic verdict. K = #distinct hypotheses in the registry (>= this one)."""
    registry = registry or HypothesisRegistry()
    k = max(registry.count(), 1)
    if not registry.has(submission.get("hypothesis_id", "")):
        k += 1  # this hypothesis is a new trial not yet recorded
    return evaluate(submission, k=k)
