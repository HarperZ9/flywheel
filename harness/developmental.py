"""developmental.py — the environment's verified experience becomes growth.

The operator's thesis (Sapolsky's frame: environment shapes the agent as it shapes
an organism): a harness is a developmental environment. The honest "complete the
loop" is not consciousness — it is that the environment's OWN verified outcomes
become the nutrition the model grows on. Every oracle-accepted answer is a datum of
"this worked, provably"; curated, those data are a self-generated training corpus
that raises the next generation's baseline.

C2-clean by construction: the ORACLE is the selection pressure, never a learned
reward. Only PASS envelopes that STILL re-witness MATCH become training examples —
so a tampered or stale accept is excluded, and the model never trains on its own
unverified guesses. This is the developmental flywheel: verified experience ->
curated corpus -> growth -> better proposals -> more verified experience.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict


@dataclass
class TrainingExample:
    task_id: str
    prompt: str
    completion: str          # the verified candidate
    oracle: str
    source_receipt: str      # the proof envelope's content hash — full provenance


def _chash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def curate(items, rewitness) -> list[TrainingExample]:
    """Turn (envelope, prompt) pairs into a training corpus. `rewitness` maps an
    envelope to its fresh verdict (typically witness.witness_envelope(...).verdict).
    Only PASS envelopes that re-witness MATCH are admitted — the oracle curates,
    not a learned filter. Deduped by (task, completion)."""
    out: list[TrainingExample] = []
    seen: set[str] = set()
    for env, prompt in items:
        if getattr(env, "verdict", None) != "PASS":
            continue
        if rewitness(env) != "MATCH":          # tampered / stale -> not nutrition
            continue
        completion = getattr(env, "candidate", "")
        key = _chash(str(getattr(env, "task_id", "")) + "|" + completion)
        if key in seen:
            continue
        seen.add(key)
        receipt = env.content_hash() if hasattr(env, "content_hash") else _chash(completion)
        out.append(TrainingExample(
            task_id=str(getattr(env, "task_id", "")), prompt=prompt,
            completion=completion, oracle=str(getattr(env, "oracle", "")),
            source_receipt=receipt))
    return out


def to_jsonl(examples: list[TrainingExample]) -> str:
    """SFT-ready JSONL: one {prompt, completion, meta} per line, every line
    traceable to its proof envelope via source_receipt."""
    lines = []
    for ex in examples:
        lines.append(json.dumps({
            "prompt": ex.prompt, "completion": ex.completion,
            "meta": {"task_id": ex.task_id, "oracle": ex.oracle,
                     "source_receipt": ex.source_receipt}}, sort_keys=True))
    return "\n".join(lines)


def corpus_stats(examples: list[TrainingExample]) -> dict:
    return {"n_examples": len(examples),
            "n_tasks": len({e.task_id for e in examples}),
            "oracles": sorted({e.oracle for e in examples}),
            "all_receipted": all(e.source_receipt for e in examples)}
