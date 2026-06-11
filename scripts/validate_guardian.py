"""Acceptance test for the Guardian engine.

Feeds the two historical hypotheses whose verdicts we already know (Carry, Trend) and
asserts the engine reproduces them faithfully:

  Carry  -> FAIL {C1, C3, C4, C5}            + DEF-2 single-regime flag
  Trend  -> FAIL {D5}                         + DEF-1 gate-defect flag (D5 mis-specified)

The Trend case is the important one: the engine must reproduce the FROZEN FAIL (no
retroactive relaxation of the mis-specified max-corr sub-gate) AND raise the gate-defect
flag — proving "faithful verdict + correct flag, verdict unchanged".

Run:  venv/Scripts/python.exe scripts/validate_guardian.py
Exit code 0 = all golden cases reproduced. Non-zero = a mismatch (engine is NOT trusted).
"""
import sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from research.guardian.cases import GOLDEN_CASES
from research.guardian.engine import evaluate
from research.guardian.registry import HypothesisRegistry


def run():
    reg = HypothesisRegistry()
    k = max(reg.count(), len(GOLDEN_CASES))  # registry-driven DSR trial count
    print(f"Hypothesis registry K = {k} (DSR trial count)\n")

    all_ok = True
    for case in GOLDEN_CASES:
        v = evaluate(case, k=k)
        got_failed = set(v["failed"])
        got_flags = {f["code"] for f in v["flags"]}
        exp_failed = case["expected_failed"]
        exp_flags = case.get("expected_flags", set())

        verdict_ok = v["verdict"] == case["expected_verdict"]
        failed_ok = got_failed == exp_failed
        flags_ok = exp_flags.issubset(got_flags)
        ok = verdict_ok and failed_ok and flags_ok
        all_ok &= ok

        mark = "PASS" if ok else "**FAIL**"
        print(f"[{mark}] {case['hypothesis_id']} — {case['title']}")
        print(f"   verdict : {v['verdict']}  (expected {case['expected_verdict']})"
              f"{'' if verdict_ok else '   <-- MISMATCH'}")
        print(f"   failed  : {sorted(got_failed)}  (expected {sorted(exp_failed)})"
              f"{'' if failed_ok else '   <-- MISMATCH'}")
        print(f"   passed  : {sorted(v['passed'])}")
        d = v["dsr"]
        print(f"   DSR     : {d['value']:.3f}  (SR={d['sr']:.3f} SR0={d['sr0']:.3f} K={d['K']}, advisory)")
        print(f"   flags   : {sorted(got_flags) or '—'}"
              f"{'' if flags_ok else f'   <-- expected superset of {sorted(exp_flags)}'}")
        for f in v["flags"]:
            print(f"       · [{f['severity']}] {f['code']}: {f['message']}")
        for gid in v["failed"]:
            print(f"       gate {gid}: {v['details'][gid]}")
        print()

    print("=" * 70)
    if all_ok:
        print("ALL GOLDEN CASES REPRODUCED — Guardian engine is trustworthy. ✅")
        return 0
    print("MISMATCH — Guardian engine is NOT trusted. Fix before building on it. ❌")
    return 1


if __name__ == "__main__":
    raise SystemExit(run())
