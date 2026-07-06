"""envelope.py — the proof receipt (HARNESS.md §proof-envelope).

Every accepted answer ships this. A third party re-runs `oracle_cmd` on the
candidate and must reproduce `oracle_output_hash` (and thus `verdict`). No
receipt -> no accept. M2 extends this into a per-stage carried chain; M1 ships
the terminal envelope only.
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class ProofEnvelope:
    task_id: str
    candidate: str
    oracle: str
    oracle_cmd: str
    oracle_output_hash: str
    verdict: str
    model_ref: str
    seed: int
    prompt_hash: str
    budget_spent: dict
    retrieved: list[dict] = field(default_factory=list)
    oracle_stdout_excerpt: str = ""
    harness_version: str = "m1"
    injected_context: dict | None = None
    admission: dict | None = None
    chain: list[dict] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    def content_hash(self) -> str:
        d = asdict(self)
        for k in ("oracle_output_hash", "verdict", "oracle_stdout_excerpt"):
            d.pop(k, None)
        return hashlib.sha256(
            json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]

    def write(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path


def load_envelope(path: str | Path) -> ProofEnvelope:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return ProofEnvelope(**d)


def verdict_from_oracle(passed: bool) -> str:
    return "PASS" if passed else "FAIL"
