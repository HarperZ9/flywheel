"""scaffold.py -- the organs fire on every message, or they are not organs.

A tool the model must remember to call is a tool that gets skipped.
This layer runs the reconcile's guarantees per turn, model-independent:

  pre-pass   every source the prompt names is frozen (snapshot, hash)
             before the model answers; failures are DEGRADED entries
             with reasons, never fabricated hashes, never a blocked turn
  post-pass  the turn chains a receipt (prompt hash, answer hash, frozen
             sources) into the audit ledger, and any citations the
             answer carries are re-sliced and verified

Wrappers compose it: the gateway routes call it inline; external
harnesses (hooks, agents) can reach the same guarantees through
/api/route's scaffold field. The scaffold never edits the answer and
never blocks on a dead source: perception failure is reported, not
hidden, and the answer ships with its honesty visible.
"""
from __future__ import annotations

import hashlib
import re

ENVELOPE_SCHEMA = "flywheel.scaffold-envelope/v1"
RECEIPT_SCHEMA = "flywheel.turn-receipt/v1"

_URL = re.compile(r"https?://[^\s)\]>\"']+")
_MAX_SOURCES = 5   # per-turn freeze budget: bounded, never unbounded fetch


def _default_snapshotter(url: str) -> dict:
    from pathlib import Path
    from .run_paths import run_root_default as run_root
    from .web_snapshot import snapshot_url
    doc = snapshot_url(url, Path(run_root()) / "snapshots")
    if "error" in doc:
        raise RuntimeError(doc["error"])
    return doc


def scaffold_turn(prompt: str, *, snapshotter=None) -> dict:
    """The pre-pass: freeze what the prompt names. Returns the envelope
    the answer path carries forward; degradation is named per source."""
    snapshotter = snapshotter or _default_snapshotter
    urls = list(dict.fromkeys(_URL.findall(prompt or "")))[:_MAX_SOURCES]
    frozen, degraded = [], []
    for u in urls:
        u = u.rstrip(".,;")
        try:
            doc = snapshotter(u)
            sha = str((doc or {}).get("sha256", ""))
            if len(sha) == 64:
                frozen.append({"url": u, "sha256": sha})
            else:
                degraded.append({"url": u,
                                 "reason": "snapshot returned no hash"})
        except Exception as e:
            degraded.append({"url": u,
                             "reason": f"{type(e).__name__}: {e}"})
    return {"schema": ENVELOPE_SCHEMA,
            "prompt_sha256": hashlib.sha256(
                (prompt or "").encode("utf-8")).hexdigest(),
            "sources_frozen": frozen, "degraded": degraded,
            "note": "sources named in the prompt are frozen before the "
                    "answer exists; a dead source is named, not faked"}


def scaffold_answer(answer: str, envelope: dict, *,
                    citations: "list | None" = None,
                    resolve=None) -> dict:
    """The post-pass: chain the turn receipt, verify citations if the
    answer carries them. Storage failure degrades to a named reason."""
    from .envelope import verify_citations
    doc = {"schema": RECEIPT_SCHEMA,
           "prompt_sha256": envelope.get("prompt_sha256", ""),
           "answer_sha256": hashlib.sha256(
               (answer or "").encode("utf-8")).hexdigest(),
           "sources_frozen": envelope.get("sources_frozen", []),
           "degraded": envelope.get("degraded", [])}
    if citations:
        doc["citations"] = verify_citations(
            citations, resolve if resolve else _store_resolver())
    try:
        from .store import put_entity
        stored = put_entity("turn-receipt", doc)
        doc["eid"] = stored.get("eid", "")
        doc["chain_hash"] = stored.get("chain_hash", "")
    except Exception as e:
        doc["eid"] = ""
        doc["chain_hash"] = ""
        doc["store_degraded"] = f"{type(e).__name__}: {e}"
    return doc


def _store_resolver():
    """Resolve a source hash to frozen bytes from the snapshot store."""
    from pathlib import Path
    from .run_paths import run_root_default as run_root
    snapdir = Path(run_root()) / "snapshots"

    def resolve(sha: str):
        for p in snapdir.glob("*") if snapdir.is_dir() else []:
            try:
                data = p.read_bytes()
            except OSError:
                continue
            if hashlib.sha256(data).hexdigest() == sha:
                return data
        return None
    return resolve
