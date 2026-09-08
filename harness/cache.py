"""cache.py — M5 receipt cache (content-addressed verified-results store).

The compounding asset (MEMORY-SUBSTRATE cost shrink). A hit supplies a stored
candidate so model generation can be skipped; the current run still executes
the oracle and every acceptance gate. The key binds task, prompt, model, seed,
oracle command, retrieved knowledge, oracle input content, and an allowlisted
oracle-context fingerprint. Any bound drift -> miss.

The falsifier: same query twice -> second is a HIT (proposer not called); any
key component drift -> MISS; changed test content -> MISS (no stale serve).
"""
from __future__ import annotations
import hashlib
import json
import re
import sys
from pathlib import Path

from .envelope import ProofEnvelope, load_envelope
from .task import Task

_SKIP_DIRS = {"__pycache__", ".pytest_cache", "_oracle_junit.xml"}

# Prompt text is task text unless a caller explicitly marks decoration metadata
# as trusted. The default cache key hashes the exact prompt so ID-shaped issue
# names, timestamps, attribution lines, indentation, and blank lines cannot be
# erased by lexical inference. The optional stripping mode is only for future
# callers that have already separated trusted transport metadata from author
# content; no current loop path opts into it.
_VOLATILE_WHOLE = re.compile(
    r"^\s*(?:co-authored-by:.*"
    r"|\d{4}-\d{2}-\d{2}t\d{2}:\d{2}[:0-9.]*z?\s*)$",
    re.IGNORECASE)
_VOLATILE_HEADER = re.compile(
    r"^\s*x-(?:request|trace|session)-id\s*[:=]\s*(.*?)\s*$",
    re.IGNORECASE)
# Inline scrub: a bracketed id token anywhere (incl. a leading prefix). Removes
# just the token; surrounding task content is kept.
_VOLATILE_INLINE = re.compile(
    r"\[\s*(?:req|request|session|trace|turn|conversation)[\s_-]?id\s*[:=]\s*([^\]]*)\]",
    re.IGNORECASE)
_OPAQUE_ID = re.compile(r"(?=.{6,128}\Z)(?=.*\d)[A-Za-z0-9._:/-]+\Z")


def _opaque_id(value: str) -> bool:
    return bool(_OPAQUE_ID.match(value.strip()))


def _drop_inline_id(match: re.Match) -> str:
    return "" if _opaque_id(match.group(1)) else match.group(0)


def canonical_prompt(prompt: str, *, strip_trusted_metadata: bool = False) -> str:
    """Return the cache-key prompt.

    The default is exact prompt text. Lexically ID-shaped content may be the
    user's task, so cache key callers must not erase it unless another trusted
    channel has already classified the decoration as transport metadata.
    """
    if not strip_trusted_metadata:
        return prompt
    out = []
    for ln in prompt.splitlines():
        if _VOLATILE_WHOLE.match(ln):
            continue
        header = _VOLATILE_HEADER.match(ln)
        if header and _opaque_id(header.group(1)):
            continue
        ln = _VOLATILE_INLINE.sub(_drop_inline_id, ln).strip()
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
    payload = []
    for r in ret:
        payload.append({
            "source": str(r.source),
            "receipt": str(r.receipt),
            "digest": str(getattr(r, "digest", "")),
            "text_sha256": hashlib.sha256(
                str(getattr(r, "text", "")).encode()).hexdigest(),
        })
    payload.sort(key=lambda item: (
        item["source"], item["receipt"], item["digest"], item["text_sha256"]))
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def _lockfile_hashes(workdir: Path) -> list[tuple[str, str]]:
    names = (
        "requirements.txt", "pyproject.toml", "poetry.lock", "uv.lock",
        "Pipfile.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    )
    out = []
    for name in names:
        p = workdir / name
        if p.is_file():
            out.append((name, hashlib.sha256(p.read_bytes()).hexdigest()))
    return out


def oracle_context_hash(task: Task, oracle_type: str = "") -> str:
    """Hash the allowlisted oracle context inputs bound by this cache.

    The raw environment is not returned or written to receipts. Only the digest
    reaches cache keys and chain payloads, so cacheability narrows when the
    allowlisted environment, interpreter, or local lockfiles drift. This is not
    a complete fingerprint of every external resource an oracle could observe.
    """
    from .oracle import run_env
    payload = {
        "schema": "flywheel.oracle-context/v1",
        "oracle": oracle_type,
        "cmd": task.oracle_cmd,
        "env": sorted(run_env().items()),
        "python": {"executable": sys.executable, "version": sys.version},
        "platform": sys.platform,
        "lockfiles": _lockfile_hashes(Path(task.workdir)),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def cache_key(task: Task, prompt_hash: str, model_ref: str, seed: int,
              oracle_cmd: str, knowledge: str = "",
              oracle_context: str = "") -> str:
    parts = [task.task_id, prompt_hash, model_ref, str(seed), oracle_cmd,
             oracle_input_hash(task)]
    if knowledge:                         # only bound when the task cites knowledge
        parts.append(f"knowledge:{knowledge}")
    if oracle_context:
        parts.append(f"oracle_context:{oracle_context}")
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
