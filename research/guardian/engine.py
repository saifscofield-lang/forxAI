"""Guardian verdict engine.

evaluate(submission, k) -> verdict dict. Deterministic: same submission + same K -> same
verdict, byte-for-byte. Evaluates the submission's OWN declared frozen gates (no relaxation,
no LLM). Then runs the defect detector, which may raise FLAGS that never change the verdict.

See docs/research/guardian_gate_spec.md §6-§7.
"""
from __future__ import annotations

from research.guardian.gates import deflated_sharpe, evaluate_gate, get_path, _MISSING


def evaluate(submission: dict, k: int = 1) -> dict:
    metrics = submission.get("metrics", {})
    declared = submission.get("declared_gates", [])

    passed, failed, details = [], [], {}
    dsr_info = None

    for spec in declared:
        gid = spec["id"]
        ok, detail, extra = evaluate_gate(metrics, spec, k)
        details[gid] = detail
        if spec["kind"] == "dsr" and extra is not None:
            dsr_info = {**extra, "passed": ok}
        (passed if ok else failed).append(gid)

    # DSR info even if no DSR gate was declared (diagnostic for the critic).
    if dsr_info is None:
        d = deflated_sharpe(metrics, k)
        dsr_info = {**d, "passed": None}  # None = not a declared gate, advisory only

    verdict = "PASS" if not failed else "FAIL"
    flags = _detect_defects(submission, failed, details, metrics)

    return {
        "hypothesis_id": submission.get("hypothesis_id", ""),
        "verdict": verdict,
        "passed": passed,
        "failed": failed,
        "details": details,
        "dsr": dsr_info,
        "flags": flags,
    }


# --------------------------------------------------------------------------- #
# Defect detector (FLAGS ONLY — never change the verdict). Spec §5.
# --------------------------------------------------------------------------- #
def _detect_defects(submission, failed, details, metrics) -> list[dict]:
    flags: list[dict] = []
    declared = {g["id"]: g for g in submission.get("declared_gates", [])}

    # DEF-1 — max-corr / ENB contradiction (the Phase 12 D5 gate-defect).
    for gid in failed:
        spec = declared.get(gid, {})
        subs = spec.get("subs", [])
        has_maxcorr = any("max_corr" in s.get("path", "") for s in subs)
        if not has_maxcorr:
            continue
        enb = get_path(metrics, "diversification.enb")
        pc1 = get_path(metrics, "diversification.pc1")
        n_inst = get_path(metrics, "diversification.n_instruments")
        if _MISSING in (enb, pc1, n_inst):
            continue
        # did the OTHER sub-conditions (enb, pc1) actually pass? then max_corr is the culprit
        enb_ok = enb >= 0.4 * n_inst
        pc1_ok = pc1 < 0.50
        if enb_ok and pc1_ok:
            flags.append({
                "code": "DEF-1-gate-defect",
                "severity": "high",
                "message": (
                    f"Gate {gid} failed but companion metrics indicate genuine "
                    f"independence (ENB={enb:.2f}>=0.4*{int(n_inst)}={0.4*n_inst:.1f}, "
                    f"PC1={pc1:.2f}<0.50). The max-pairwise-corr sub-gate is likely "
                    f"MIS-SPECIFIED (a universe-construction diagnostic encoded as a "
                    f"result gate). VERDICT UNCHANGED — route to human for a separately "
                    f"pre-registered re-test with a corrected gate. Do NOT relax in place."
                ),
            })

    # DEF-2 — single-regime artifact.
    if any(_is_regime_gate(declared.get(g, {})) for g in failed):
        regimes = metrics.get("regimes", {})
        if regimes:
            pos = {k: v for k, v in regimes.items() if v > 0}
            nonpos = {k: v for k, v in regimes.items() if v <= 0}
            if len(pos) == 1 and nonpos:
                carrier = next(iter(pos))
                flags.append({
                    "code": "DEF-2-single-regime",
                    "severity": "info",
                    "message": (
                        f"Edge concentrated in a single regime ('{carrier}'={pos[carrier]:+.4f}); "
                        f"other regimes non-positive ({_fmt_regimes(nonpos)}). "
                        f"Classic single-regime artifact — reinforces the FAIL."
                    ),
                })

    # DEF-3 — cost cliff (clean stats but dies after frictions).
    cost = metrics.get("cost", {})
    net1x = cost.get("net_mean_1x")
    pf = cost.get("pf_net")
    if (net1x is not None and net1x <= 0) or (pf is not None and pf <= 1.0):
        flags.append({
            "code": "DEF-3-cost-cliff",
            "severity": "info",
            "message": (
                f"Edge does not survive costs (net_mean_1x={net1x}, pf_net={pf}). "
                f"Pre-cost performance is an illusion."
            ),
        })

    # DEF-4 — thin sample for DSR.
    n_obs = metrics.get("n_obs", 0) or 0
    if 0 < n_obs < 36:
        flags.append({
            "code": "DEF-4-thin-sample",
            "severity": "info",
            "message": (f"n_obs={n_obs} (<36): DSR estimate is low-power; treat any DSR "
                        f"pass on this short a sample with suspicion."),
        })

    return flags


def _is_regime_gate(spec: dict) -> bool:
    return spec.get("kind") == "all_positive" and spec.get("path") == "regimes"


def _fmt_regimes(d: dict) -> str:
    return ", ".join(f"{k}:{v:+.4f}" for k, v in d.items())
