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
import json
import re
from pathlib import Path

from .envelope import ProofEnvelope, load_envelope
from .task import Task

_SKIP_DIRS = {"__pycache__", ".pytest_cache", "_oracle_junit.xml"}

# F2 fix: volatile prompt decorations that change every turn (attribution
# headers, request/session/trace ids, timestamps, co-author trailers) and never
# affect the oracle's verdict. Stripped ONLY at the cache-key site — the envelope
# keeps the real prompt_hash for provenance. Conservative: whole-line drops +
# a bracketed-id inline scrub; the semantic body is untouched, so two prompts
# that differ only in a volatile header collapse to one key (fixes the 0%
# agent-cache-hit) while a real body change still misses.
# Whole-line drops: lines that are ENTIRELY a volatile decoration (never carry
# task content). NOT the "[req-id: x] real content" case — that is handled by the
# inline scrub so the content survives.
_VOLATILE_WHOLE = re.compile(
    r"^\s*(?:co-authored-by:.*"
    r"|x-(?:request|trace|session)-id\s*[:=].*"
    r"|\d{4}-\d{2}-\d{2}t\d{2}:\d{2}[:0-9.]*z?\s*)$",
    re.IGNORECASE)
# Inline scrub: a bracketed id token anywhere (incl. a leading prefix). Removes
# just the token; surrounding task content is kept.
_VOLATILE_INLINE = re.compile(
    r"\[\s*(?:req|request|session|trace|turn|conversation)[\s_-]?id\s*[:=]\s*[^\]]*\]",
    re.IGNORECASE)


def canonical_prompt(prompt: str) -> str:
    """Strip volatile decorations so semantically-identical prompts hash the
    same. Used only for the cache KEY, never for the provenance prompt_hash.
    Conservative: drops pure-decoration lines and bracketed id tokens; every line
    with real content survives (a body change still changes the key)."""
    out = []
    for ln in prompt.splitlines():
        if _VOLATILE_WHOLE.match(ln):
            continue
        ln = _VOLATILE_INLINE.sub("", ln).strip()
        if ln:
            out.append(ln)
    return "\n".join(out)


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


def knowledge_hash(task: Task) -> str:
    """Content-hash of the retrieved knowledge a task was grounded on (its
    `retrieved` receipts). Empty when the task cites nothing — so a task with no
    grounding keys exactly as before (backward compatible). #4 provenance-keyed
    flywheel: binding this into the cache key means a cited source's DRIFT gives a
    different key -> a miss -> re-verification, instead of serving a result
    grounded on stale knowledge."""
    ret = getattr(task, "retrieved", None) or []
    if not ret:
        return ""
    payload = sorted((str(r.source), str(r.receipt)) for r in ret)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def cache_key(task: Task, prompt_hash: str, model_ref: str, seed: int,
              oracle_cmd: str, knowledge: str = "") -> str:
    parts = [task.task_id, prompt_hash, model_ref, str(seed), oracle_cmd,
             oracle_input_hash(task)]
    if knowledge:                         # only bound when the task cites knowledge
        parts.append(knowledge)
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
