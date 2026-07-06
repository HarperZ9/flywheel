"""cache.py — M5 receipt cache (content-addressed verified-results store).

The compounding asset (MEMORY-SUBSTRATE cost->~0). Key binds everything that
determines the verdict: task, prompt, model, seed, oracle cmd, AND the oracle's
input content (the test files). A hit returns the stored envelope at ~0 cost —
the model generation (expensive) and the oracle run are both skipped, because
the tuple is deterministic. Any drift in any component -> different key -> miss.
Never serves a stale verdict: if the tests change, oracle_input_hash changes,
the key misses, and the oracle re-runs.

The falsifier: same query twice -> second is a HIT (proposer not called); any
key component drift -> MISS; changed test content -> MISS (no stale serve).
"""
from __future__ import annotations
import hashlib
from pathlib import Path

from .envelope import ProofEnvelope, load_envelope
from .task import Task

_SKIP_DIRS = {"__pycache__", ".pytest_cache", "_oracle_junit.xml"}


def oracle_input_hash(task: Task) -> str:
    h = hashlib.sha256()
    wd = Path(task.workdir)
    cand_name = Path(task.candidate_path).name
    if wd.is_dir():
        for p in sorted(wd.rglob("*")):
            if not p.is_file():
                continue
            if p.name == cand_name or p.name in _SKIP_DIRS:
                continue
            if any(part in _SKIP_DIRS for part in p.parts):
                continue
            rel = p.relative_to(wd).as_posix()
            h.update(rel.encode())
            h.update(hashlib.sha256(p.read_bytes()).hexdigest().encode())
    return h.hexdigest()[:16]


def cache_key(task: Task, prompt_hash: str, model_ref: str, seed: int,
              oracle_cmd: str) -> str:
    parts = [task.task_id, prompt_hash, model_ref, str(seed), oracle_cmd,
             oracle_input_hash(task)]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


class ReceiptCache:
    def __init__(self, store_dir: str | Path):
        self.store = Path(store_dir)
        self.store.mkdir(parents=True, exist_ok=True)

    def lookup(self, key: str) -> ProofEnvelope | None:
        p = self.store / f"{key}.json"
        return load_envelope(p) if p.exists() else None

    def insert(self, envelope: ProofEnvelope, key: str) -> Path:
        return envelope.write(self.store / f"{key}.json")

    def size(self) -> int:
        return len(list(self.store.glob("*.json")))
