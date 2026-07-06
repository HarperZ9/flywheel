"""failure_corpus.py — turn every rejection into a durable regression case.

The self-recursive discipline made literal for verification: when the oracle
REJECTS a candidate, that (candidate, task) pair is a known-bad worth keeping.
Banked as a content-addressed corpus, it (a) auto-grows the calibration set
(every real rejection becomes a should_pass=False case), and (b) is replayed on
any model/prompt/oracle version change to catch a WEAKENED verifier — an oracle
that now ACCEPTS a case it used to reject is a verifier regression, surfaced
immediately.

Composes with calibration.py (to_calibration_cases -> calibrate) and the
adversarial corpus: real failures feed the credibility gate instead of only
hand-crafted attacks.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path

from .cache import oracle_input_hash
from .calibration import CalibrationCase
from .oracle import Oracle
from .task import Task


def _chash(candidate: str) -> str:
    return hashlib.sha256(candidate.encode()).hexdigest()[:12]


@dataclass
class FailureCase:
    task_id: str
    candidate: str
    oracle_type: str
    oracle_input_hash: str
    candidate_hash: str = ""

    def __post_init__(self):
        if not self.candidate_hash:
            self.candidate_hash = _chash(self.candidate)


def load(store_path: str | Path) -> list[FailureCase]:
    """Load the corpus, deduped by candidate_hash (last write wins)."""
    p = Path(store_path)
    if not p.exists():
        return []
    by_hash: dict[str, FailureCase] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        c = FailureCase(**d)
        by_hash[c.candidate_hash] = c
    return list(by_hash.values())


def record(store_path: str | Path, case: FailureCase) -> bool:
    """Append a case unless its candidate_hash is already banked. Returns True if
    newly recorded."""
    p = Path(store_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if any(c.candidate_hash == case.candidate_hash for c in load(p)):
        return False
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(case), sort_keys=True) + "\n")
    return True


def record_if_rejected(store_path: str | Path, task: Task, candidate: str,
                       oracle: Oracle) -> bool:
    """Run the oracle; bank the candidate ONLY if it is rejected (a real
    known-bad). A passing candidate is not a failure and is never recorded."""
    if oracle.verify(candidate, task).passed:
        return False
    return record(store_path, FailureCase(
        task_id=task.task_id, candidate=candidate, oracle_type=oracle.oracle_type,
        oracle_input_hash=oracle_input_hash(task)))


def to_calibration_cases(failures: list[FailureCase]) -> list[CalibrationCase]:
    """Every banked failure is a known-bad calibration case (should_pass=False).
    This is how the corpus grows the credibility gate from real runs."""
    return [CalibrationCase(candidate=f.candidate, should_pass=False,
                            note=f"banked failure {f.candidate_hash}")
            for f in failures]


def replay(oracle: Oracle, task: Task, failures: list[FailureCase]) -> dict:
    """Re-run the banked known-bads for this task. Every one MUST still be
    rejected; any that now PASSES is a verifier regression (the oracle weakened)."""
    relevant = [f for f in failures if f.task_id == task.task_id]
    regressions = []
    for f in relevant:
        if oracle.verify(f.candidate, task).passed:
            regressions.append(f.candidate_hash)     # now accepts a known-bad
    return {"n": len(relevant),
            "still_rejected": len(relevant) - len(regressions),
            "regressions": regressions,
            "clean": len(regressions) == 0}
