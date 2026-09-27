"""Apply and verify the plaintext part of a deletion plan (7.10, FW-07b).

store.db rows go through the checked scrub in one transaction; a busy
database (an open reader keeps the WAL) stops the step with DB_BUSY and the
journal resumes it on the next run. Fold index notes and bench rows are
rewritten without the deleted items, atomically. Files and folders are
removed by handle inside their pinned root. Verification requires every item
absent and, when the scan set is readable, no window of deleted text in any
file of these stores, subtracting text that kept rows still hold.
"""
from __future__ import annotations

import json
from pathlib import Path

from .private_artifact_remove import remove
from .trace_delete_adapters_plain import _bench, live_texts, scanned_files


class ScrubPending(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _atomic(path: Path, text: str) -> None:
    from . import trace_durable
    trace_durable.write_durable(path, text.encode("utf-8"))


def _fold(roots: dict, refs: set) -> None:
    from .fold_index import FoldIndex
    index = FoldIndex(Path(roots["run"]) / "fold_index.json")
    if not refs & set(index.spans):
        return
    for ref in refs:
        index.spans.pop(ref, None)
        index._content.pop(ref, None)
    for term in list(index.postings):
        index.postings[term] -= refs
        if not index.postings[term]:
            del index.postings[term]
    _atomic(index.path, json.dumps(index._snapshot(), sort_keys=True))


def _bench_rows(roots: dict, tasks: set) -> None:
    path = _bench(roots)
    if path.exists():
        rows = [r for r in path.read_text(encoding="utf-8").splitlines() if r.strip()]
        _atomic(path, "\n".join(r for r in rows if json.loads(r).get("task_id") not in tasks))
    prior = path.with_name("trace-bench-prior.json")
    if prior.exists() and any(t in prior.read_text(encoding="utf-8") for t in tasks):
        prior.unlink()


def scrub_store(home: Path, entries: list[dict], reason: str) -> dict:
    from .store_tombstone import forget_entities
    eids = [e["item"] for e in entries if e["store"] == "S7"]
    if not eids:
        return {"state": "SCRUBBED", "legacy_fingerprint": 0}
    result = forget_entities(home, eids, reason)
    if result["state"] != "SCRUBBED":
        raise ScrubPending(result["reason"])
    return result


def remove_plain(roots: dict, entries: list[dict]) -> None:
    from .private_artifact_fs import root_identity
    _fold(roots, {e["item"] for e in entries if e["store"] == "S9"})
    _bench_rows(roots, {e["item"] for e in entries if e["store"] == "S11"})
    for entry in (e for e in entries if e.get("action") == "remove"):
        root = Path(roots[entry["root"]])
        remove(root, entry["rel"], expected=root_identity(root))


def verify_plain(home: Path, roots: dict, entries: list[dict], scan_set) -> dict:
    from .fold_index import FoldIndex
    from .store import get_entity
    from .trace_residual_scan import Needles, scan_paths
    present = [e for e in entries if e["store"] == "S7" and get_entity(e["item"], home=home)]
    spans = FoldIndex(Path(roots["run"]) / "fold_index.json").spans
    present += [e for e in entries if e["store"] == "S9" and e["item"] in spans]
    present += [e for e in entries if e.get("action") == "remove"
                and (Path(roots[e["root"]]) / e["rel"]).exists()]
    checks = ["items_absent"]
    hits = 0
    if scan_set is not None:
        needles = Needles.build(scan_set, live=live_texts(home, roots, entries))
        hits = scan_paths(scanned_files(home, roots), needles)["total"]
        checks.append("residual_scan")
    reason = "RESIDUE_FOUND" if present or hits else None
    return {"ok": reason is None, "reason": reason, "checks": checks,
            "residual": {"plaintext": hits}}
