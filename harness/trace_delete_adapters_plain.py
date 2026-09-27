"""Deletion of plaintext and legacy stores (7.10, FW-07b).

Covered: store.db entities (v1 and v2 turn receipts; a forgotten row leaves a
`forget_entity` audit row), fold index notes and their term postings, legacy
agent runs, the trace bench rows derived from them, the sealed operation
results of a deleted gateway trace (S2), and the native CLI profile folders
a deleted trace names (S6; their contents were never classified, so the
whole folder goes and the report says so). Plaintext leaves its old bytes in
freed clusters, which the report names; the scan set of deleted text lets
verification search every file of these stores for what should be gone.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

_EID = re.compile(r"(tr2_[0-9a-f]{24}|[0-9a-f]{24})\Z")
_NOTE = re.compile(r"[0-9a-f]{64}\Z")
_RUN = re.compile(r"[0-9a-f]{16}\Z")
PROFILE_NOTE = ("native CLI profile folder contents were never classified; the whole "
                "folder was removed")


def valid(kind: str, value) -> bool:
    pattern = {"receipt_eids": _EID, "note_refs": _NOTE, "legacy_runs": _RUN}[kind]
    return type(value) is str and pattern.fullmatch(value) is not None


def _trace_records(state: Path, owner: str, entry: dict) -> list[dict]:
    from .gateway_agent_trace import AgentTrace
    from .trace_enc import is_encrypted
    from .trace_enc_write import ItemCipher
    raw = (state / entry["rel"] / "00000000.json").read_bytes()
    if is_encrypted(raw):
        raw = ItemCipher(state, owner, "S1", entry["item"]).open("00000000.json", raw)
    journey = json.loads(raw)["journey_ref"]
    return AgentTrace(state, owner, journey, entry["operation"]).read()


UNREAD_NOTE = ("{n} selected trace(s) could not be read (damaged, or the OS key is "
               "unavailable); each is still deleted, but profile folders named inside "
               "it were not found and stay")


def _readable_records(state: Path, owner: str, entry: dict, unread: list | None) -> list:
    """The trace's records, or [] when it cannot be read: a damaged trace or a
    lost OS key must never block its own deletion (the S1 entry comes from
    the folder and header alone)."""
    from .gateway_agent_trace import TraceError
    from .trace_enc import EncError
    try:
        return _trace_records(state, owner, entry)
    except (OSError, ValueError, KeyError, TypeError, TraceError, EncError):
        if unread is not None:
            unread.append(entry["item"])
        return []


def trace_closure(state: Path, owner: str, entry: dict, unread: list | None = None
                  ) -> list[dict]:
    """S6 profile folders named in the trace and S2 results of its operation.
    A trace that cannot be read adds its ref to `unread`."""
    out = []
    for record in _readable_records(state, owner, entry, unread):
        payload = record.get("payload") or {}
        name = payload.get("profile_dir") if payload.get("type") == "cli_profile" else None
        if isinstance(name, str) and name.startswith("native-cli-profile-") and "/" not in name:
            out.append({"store": "S6", "item": name, "action": "remove", "root": "state",
                        "rel": name})
    results = state / "gateway-operations" / "v1" / "owners" / owner / "results"
    for path in sorted(results.glob("*.json")) if results.is_dir() else []:
        try:
            if json.loads(path.read_bytes()).get("operation_ref") == entry["operation"]:
                out.append({"store": "S2", "item": path.stem, "action": "remove",
                            "root": "state", "rel": path.relative_to(state).as_posix()})
        except (OSError, ValueError, AttributeError):
            continue
    return out


def selection_entries(roots: dict, selection: dict, receipts: list) -> list[dict]:
    out = [{"store": "S7", "item": eid, "action": "forget"}
           for eid in sorted(set(selection.get("receipt_eids", [])) | set(receipts))]
    out += [{"store": "S9", "item": ref, "action": "fold_note"}
            for ref in selection.get("note_refs", [])]
    for run in selection.get("legacy_runs", []):
        out.append({"store": "S10", "item": run, "action": "remove", "root": "run",
                    "rel": f"agent_runs/{run}.json"})
        out.append({"store": "S11", "item": f"trace-{run}", "action": "bench_row"})
    return out


def _bench(roots) -> Path:
    return Path(roots["run"]) / "bench" / "trace-tasks.jsonl"


def _bench_rows(roots) -> list[str]:
    path = _bench(roots)
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] \
        if path.exists() else []


_SCHEMA = re.compile(r"flywheel\.[a-z0-9.\-]+/v[0-9]+\Z")
_HEX = re.compile(r"[0-9a-f]{32,}\Z")


def leaf_texts(text: str) -> list[str]:
    """The string values of a JSON document (else the text itself), without
    keys, structure, schema ids or bare hex digests: the scan looks for
    content, and shared boilerplate would read as residue everywhere."""
    try:
        stack, out = [json.loads(text)], []
    except ValueError:
        return [text]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, str) and not _SCHEMA.fullmatch(item) and not _HEX.fullmatch(item):
            out.append(item)
    return out


def item_texts(home: Path, roots: dict, entries: list[dict]) -> list[str]:
    """The content each plaintext item holds, for the scan set."""
    return [leaf for text in _raw_texts(home, roots, entries) for leaf in leaf_texts(text)
            if leaf]


def _raw_texts(home: Path, roots: dict, entries: list[dict]) -> list[str]:
    from .fold_index import FoldIndex
    from .store_tombstone import entity_texts
    texts = entity_texts(home, [e["item"] for e in entries if e["store"] == "S7"])
    fold = FoldIndex(Path(roots["run"]) / "fold_index.json")
    texts += [json.dumps(fold.spans.get(e["item"], [])) for e in entries if e["store"] == "S9"]
    rows = {json.loads(r).get("task_id"): r for r in _bench_rows(roots)}
    texts += [rows[e["item"]] for e in entries if e["store"] == "S11" and e["item"] in rows]
    for entry in (e for e in entries if e.get("action") == "remove"):
        target = Path(roots[entry["root"]]) / entry["rel"]
        files = [target] if target.is_file() else sorted(target.rglob("*")) if target.is_dir() else []
        texts += [p.read_bytes().decode("utf-8", "replace") for p in files if p.is_file()][:200]
    return [t for t in texts if t]


def live_texts(home: Path, roots: dict, entries: list[dict]) -> list[str]:
    from .fold_index import FoldIndex
    from .store_tombstone import live_texts as entity_live
    gone = {e["item"] for e in entries}
    fold = FoldIndex(Path(roots["run"]) / "fold_index.json")
    kept = entity_live(home, gone)
    kept += [json.dumps(v) for k, v in fold.spans.items() if k not in gone]
    kept += [r for r in _bench_rows(roots) if json.loads(r).get("task_id") not in gone]
    return kept


def scanned_files(home: Path, roots: dict) -> list[Path]:
    run = Path(roots["run"])
    files = [home / f"store.db{s}" for s in ("", "-wal", "-shm", "-journal")]
    files += [run / "fold_index.json", _bench(roots), run / "bench" / "trace-bench-prior.json"]
    for folder in (run / "agent_runs", home / "state" / "gateway-operations"):
        files += [p for p in folder.rglob("*") if p.is_file()] if folder.is_dir() else []
    return [p for p in files if p.exists()]


def legacy_snapshots(home: Path, entries: list[dict]) -> int:
    """Frozen pages cited by the v1 receipts being removed. They stay: other
    stores that cite snapshot hashes are not indexed yet (EN-C11)."""
    from .store import get_entity
    count = 0
    for entry in (e for e in entries if e["store"] == "S7"):
        entity = get_entity(entry["item"], home=home)
        data = entity["data"] if entity else {}
        count += len(data.get("sources_frozen", []) or []) if isinstance(data, dict) else 0
    return count
