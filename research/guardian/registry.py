"""Append-only hypothesis registry — the multiple-testing counter.

Every hypothesis ever TESTED is recorded here, including failures. The count K feeds the
Deflated Sharpe gate so the bar rises with data-mining. Append-only by discipline: entries
are never edited or deleted (the file is git-committed as the tamper-evident record).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

DEFAULT_PATH = Path("data/hypothesis_registry.jsonl")


class HypothesisRegistry:
    def __init__(self, path: str | Path = DEFAULT_PATH):
        self.path = Path(path)

    # -- read --------------------------------------------------------------- #
    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    def count(self) -> int:
        """K = number of distinct hypotheses tested (the DSR trial count)."""
        return len({e["hypothesis_id"] for e in self.entries()})

    def has(self, hypothesis_id: str) -> bool:
        return any(e["hypothesis_id"] == hypothesis_id for e in self.entries())

    # -- write (append-only) ------------------------------------------------ #
    def append(self, hypothesis_id: str, *, title: str = "", verdict: str = "",
               prereg_commit: str = "", note: str = "", recorded: str = "") -> None:
        """Append one test record. `recorded` is an ISO date string passed by the caller
        (the engine never calls Date.now-style clocks — timestamps are supplied)."""
        entry = {
            "hypothesis_id": hypothesis_id, "title": title, "verdict": verdict,
            "prereg_commit": prereg_commit, "note": note, "recorded": recorded,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def seed(self, records: Iterable[dict]) -> int:
        """Append any records whose hypothesis_id is not already present. Returns #added."""
        existing = {e["hypothesis_id"] for e in self.entries()}
        added = 0
        for r in records:
            if r["hypothesis_id"] not in existing:
                self.append(**r)
                existing.add(r["hypothesis_id"])
                added += 1
        return added
