"""chain.py — M2 spanning receipt chain (HARNESS-ROADMAP.md §0, the spine).

The envelope becomes a chain of witnessed transitions, not a terminal blob.
Each stage (boot, propose, policy, verify, accept) emits a StageReceipt
hash-linked to the prior. `no-receipt -> no-accept` becomes the binary-collapse
guard at EVERY link, not only the terminal one.

Tamper-evidence: each receipt's content is hashed (excluding its prev_hash
pointer). Receipt i+1.prev_hash must equal receipt_hash(i). Corrupting any
receipt's content breaks the link at i+1. The chain head (last receipt's hash)
is bound into the envelope so terminal-receipt tampering is also caught.

Falsifier: corrupt any stage -> validate_chain -> DRIFT/UNVERIFIABLE, never MATCH.
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Iterable


@dataclass
class StageReceipt:
    stage: str
    inputs_hash: str
    outputs_hash: str
    verdict: str
    prev_hash: str = ""
    evidence_ref: str | None = None
    payload: dict = field(default_factory=dict)

    def receipt_hash(self) -> str:
        d = asdict(self)
        d.pop("prev_hash", None)
        return hashlib.sha256(
            json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["receipt_hash"] = self.receipt_hash()
        return d


@dataclass
class ChainValidation:
    verdict: str  # MATCH | DRIFT | UNVERIFIABLE
    broken_at: int | None
    head_hash: str | None
    reason: str


def validate_chain(stages: Iterable[StageReceipt | dict]) -> ChainValidation:
    stages = list(stages)
    if not stages:
        return ChainValidation("UNVERIFIABLE", None, None, "empty chain")
    prev = ""
    for i, s in enumerate(stages):
        sd = s if isinstance(s, dict) else asdict(s)
        rh = StageReceipt(
            stage=sd["stage"], inputs_hash=sd["inputs_hash"],
            outputs_hash=sd["outputs_hash"], verdict=sd["verdict"],
            prev_hash=sd.get("prev_hash", ""), evidence_ref=sd.get("evidence_ref"),
            payload=sd.get("payload", {})).receipt_hash()
        if sd.get("prev_hash", "") != prev:
            return ChainValidation(
                "UNVERIFIABLE", i, rh,
                f"broken link at stage {i} ({sd['stage']}): prev_hash mismatch")
        prev = rh
    return ChainValidation("MATCH", None, prev, "all links verified")


def append_stage(chain: list[StageReceipt], stage: str, inputs_hash: str,
                  outputs_hash: str, verdict: str, *,
                  evidence_ref: str | None = None,
                  payload: dict | None = None) -> StageReceipt:
    prev = chain[-1].receipt_hash() if chain else ""
    r = StageReceipt(stage=stage, inputs_hash=inputs_hash,
                     outputs_hash=outputs_hash, verdict=verdict,
                     prev_hash=prev, evidence_ref=evidence_ref,
                     payload=payload or {})
    chain.append(r)
    return r


def chain_to_dicts(chain: list[StageReceipt]) -> list[dict]:
    return [s.to_dict() for s in chain]


def chain_from_dicts(dicts: list[dict]) -> list[StageReceipt]:
    return [StageReceipt(
        stage=d["stage"], inputs_hash=d["inputs_hash"],
        outputs_hash=d["outputs_hash"], verdict=d["verdict"],
        prev_hash=d.get("prev_hash", ""), evidence_ref=d.get("evidence_ref"),
        payload=d.get("payload", {})) for d in dicts]
