"""Guardian — methodology guardian for forex strategy research.

Deterministic gate engine that decides PASS/FAIL for a hypothesis submission against a
frozen, declared gate set. The verdict is computed, never argued — no LLM can convert
FAIL into PASS. See docs/research/guardian_gate_spec.md and guardian_roadmap.md.
"""
from research.guardian.engine import evaluate
from research.guardian.registry import HypothesisRegistry

__all__ = ["evaluate", "HypothesisRegistry"]
