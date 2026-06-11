"""Deterministic Guardian verdict CLI — the bridge the research Workflow's verdict stage calls.

Reads a JSON file describing a hypothesis (meta + raw backtest metrics), attaches the
canonical gate set, runs the Guardian engine against the registry's multiple-testing count
K, and prints + writes a verdict report. No LLM in the verdict path.

Input JSON shape:
  {
    "meta": {"hypothesis_id": "...", "title": "...", "economic_rationale": "...",
             "prereg_commit": "..."},
    "metrics": { ... per docs/research/guardian_gate_spec.md §1 ... }
  }

Run:  venv/Scripts/python.exe scripts/guardian_assess.py path/to/submission.json
Exit 0 = PASS, 2 = FAIL, 1 = bad input.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from research.guardian.canonical import assess, build_submission


def main(argv):
    if len(argv) < 2:
        print("usage: guardian_assess.py <submission.json> [--out report.md]")
        return 1
    src = Path(argv[1])
    if not src.exists():
        print(f"input not found: {src}")
        return 1

    payload = json.loads(src.read_text(encoding="utf-8"))
    meta = payload.get("meta", {})
    metrics = payload.get("metrics", {})
    sub = build_submission(meta, metrics)
    v = assess(sub)

    lines = []
    def out(s=""):
        print(s); lines.append(s)

    out(f"# Guardian verdict — {v['hypothesis_id']}")
    out(f"\n**VERDICT: {v['verdict']}**  (declared canonical gates G1-G8)\n")
    out(f"- passed: {v['passed']}")
    out(f"- failed: {v['failed']}")
    d = v["dsr"]
    out(f"- DSR: {d['value']:.3f} (SR={d['sr']:.3f} SR0={d['sr0']:.3f} K={d['K']})")
    out("\n## Gate detail")
    for gid, det in v["details"].items():
        mark = "PASS" if gid in v["passed"] else "FAIL"
        out(f"- **{gid}** [{mark}] — {det}")
    if v["flags"]:
        out("\n## Flags (advisory — do NOT change the verdict)")
        for f in v["flags"]:
            out(f"- [{f['severity']}] **{f['code']}** — {f['message']}")
    out("\n---")
    out("HUMAN GATE: a PASS here authorizes nothing automatically. Crossing to the locked")
    out("holdout or to capital is a separate human go/no-go. A gate-defect flag NEVER")
    out("relaxes this verdict — it routes to a separately pre-registered re-test.")

    # optional report file
    if "--out" in argv:
        outp = Path(argv[argv.index("--out") + 1])
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n(written to {outp})")

    return 0 if v["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
