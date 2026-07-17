"""hard_lane.py — a curated hard-task lane with a re-checkable contamination gate.

A verified-inference lift only means something on tasks a model could NOT have
memorized. Each lane task is stamped with its public first-appearance date, its
source dataset, and its license; the freshness gate compares that date to a routed
model's training cutoff and returns FRESH / CONTAMINATED / UNKNOWN. This turns
contamination resistance into a falsifiable, re-checkable property: a stranger
confirms the dates offline and reproduces the verdict, no trust required.

This is the lane MECHANISM (schema + gate + loader + admission). Growing the lane
to ~100 tasks is ongoing curation from vetted, permissively-licensed sources
(Terminal-Bench 2.0, LiveCodeBench, SWE-bench-Live). Non-learned, zero-dep.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

VERDICT_FRESH = "FRESH"
VERDICT_CONTAMINATED = "CONTAMINATED"
VERDICT_UNKNOWN = "UNKNOWN"


@dataclass
class LaneTask:
    task_id: str = ""
    source: str = ""                  # e.g. "terminal-bench-2.0", "livecodebench", "swe-bench-live"
    license: str = ""
    public_date: str = ""             # ISO "YYYY-MM-DD" of first public appearance
    prompt: str = ""
    oracle_cmd: str = ""
    held_out_cmd: str = ""            # feeds the held-out oracle tier (accept_gate)
    difficulty: str = ""
    tags: list = field(default_factory=list)

    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps({
            "task_id": self.task_id, "source": self.source,
            "public_date": self.public_date, "oracle_cmd": self.oracle_cmd,
        }, sort_keys=True).encode()).hexdigest()[:16]


def _parse_date(s: str):
    parts = (s or "").split("-")
    if len(parts) < 3:
        return None
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def freshness(task_public_date: str, model_cutoff: str) -> str:
    """FRESH when the task went public STRICTLY AFTER the model's training cutoff
    (it could not have been memorized), CONTAMINATED when on/before it, UNKNOWN when
    either date is missing or malformed. Conservative: same-day counts as
    contaminated."""
    t, c = _parse_date(task_public_date), _parse_date(model_cutoff)
    if t is None or c is None:
        return VERDICT_UNKNOWN
    return VERDICT_FRESH if t > c else VERDICT_CONTAMINATED


def freshness_report(task: LaneTask, model_cutoff: str) -> dict:
    return {
        "schema": "flywheel.hard-lane-freshness/v1",
        "task_id": task.task_id, "source": task.source,
        "public_date": task.public_date, "model_cutoff": model_cutoff,
        "verdict": freshness(task.public_date, model_cutoff),
        "fingerprint": task.fingerprint(),
    }


def load_lane(path) -> list:
    """Load a lane from a JSONL manifest (one LaneTask per line)."""
    fields = set(LaneTask.__dataclass_fields__)
    tasks = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        tasks.append(LaneTask(**{k: v for k, v in d.items() if k in fields}))
    return tasks


def admit(tasks: list, model_cutoff: str, *, require_license: bool = True) -> dict:
    """Partition a lane into fresh / contaminated / unknown for one model, and flag
    any task missing a license so nothing enters the lane unvetted. The counts are
    re-derivable from the stamped dates, so a scored run's contamination profile is
    itself re-checkable."""
    buckets = {VERDICT_FRESH: [], VERDICT_CONTAMINATED: [], VERDICT_UNKNOWN: []}
    unlicensed = []
    for t in tasks:
        if require_license and not t.license:
            unlicensed.append(t.task_id)
        buckets[freshness(t.public_date, model_cutoff)].append(t.task_id)
    return {
        "schema": "flywheel.hard-lane-admission/v1",
        "model_cutoff": model_cutoff,
        "counts": {k: len(v) for k, v in buckets.items()},
        "fresh": buckets[VERDICT_FRESH],
        "contaminated": buckets[VERDICT_CONTAMINATED],
        "unknown": buckets[VERDICT_UNKNOWN],
        "unlicensed": unlicensed,
    }


def write_lane(tasks: list, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(asdict(t), sort_keys=True) for t in tasks),
                    encoding="utf-8")
    return path
