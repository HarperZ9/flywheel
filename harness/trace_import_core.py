"""Import core: plan, bounds, reading, storage and idempotence (7.6, I9).

A plan lists every candidate source with its state: `new`, `grown` (the same
source with more bytes after what was stored; imported as a new version with
a `supersedes` edge), `already`, `LIVE_WRITER` (modified in the last minute,
retried later), `PREVIOUSLY_DELETED` or `PREVIOUSLY_DELETED_SESSION`. It also
names every file it will not import and why, refused reparse points, the
bytes needed against free space (INSUFFICIENT_SPACE when source bytes plus
512 MiB exceed it), and the client's sweep risk. Running a plan reads each
source by handle, proves it unchanged, and stores it; nothing else is
touched and nothing is half imported.
"""
from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
import shutil
import time

from .trace_import_exclusion import (ExclusionUnavailable, PrefixProbe, check,
                                     custody_key, entries, keyed_path, session_ref,
                                     source_ref)
from .trace_import_items import ImportStore

__all__ = ["ImportStore", "build_plan", "run_import"]

LINE_BOUND = 64 * 1024 * 1024
DEPTH_BOUND = 200
FILES_PER_DIRECTORY = 10_000
MARGIN = 512 * 1024 * 1024
LIVE_WINDOW_S = 60
CODEX_KINDS = ("rollout", "archived_rollout", "compressed_rollout")
JSONL_KINDS = ("transcript", "subagent", "variant", *CODEX_KINDS)
PARSER_VERSION = "flywheel.import-lines/1"


def _prefix_mac(key: bytes, path: Path, n: int) -> str:
    from .trace_import_read import read_prefix
    probe = PrefixProbe(key, [n])
    read_prefix(path, n, probe.feed)
    return probe.digest(n)


def _state(key, listed, stored, client, source, now, live_window_s) -> dict:
    path, size = source["path"], source["size"]
    ref = source_ref(key, client, path, source.get("session_id"))
    from .trace_import_read import read_prefix
    probe = PrefixProbe(key, [e.get("n", 0) for e in listed if e.get("n", 0) <= size])
    read_prefix(path, max(probe.states or [0]), probe.feed)
    excluded, new_bytes = check(key, listed, ref, size, probe,
                                path_ref=keyed_path(key, client, path),
                                session=session_ref(key, client, source.get("session_id")))
    if excluded:
        return {"state": excluded, "new_bytes": new_bytes}
    if source.get("forced_state"):
        return {"state": source["forced_state"]}
    if now - source["mtime"] < live_window_s:
        return {"state": "LIVE_WRITER"}
    for row in reversed(stored):
        if row["source_ref"] == ref and row["bytes"] <= size and \
                _prefix_mac(key, path, row["bytes"]) == row["content_ref"]:
            return {"state": "already"} if row["bytes"] == size else {
                "state": "grown", "supersedes": row["item_ref"]}
    return {"state": "new"}


def _safe_state(*args) -> dict:
    from .trace_import_read import SourceRefused
    try:
        return _state(*args)
    except SourceRefused as refused:
        return {"state": refused.code}
    except OSError:
        return {"state": "UNREADABLE"}


def build_plan(home, owner_ref: str, client: str, sources, *, refused=(), not_imported=(),
               sweep=None, now=None, free_space=None, live_window_s=LIVE_WINDOW_S,
               root=None) -> dict:
    now = now or time.time()
    plan = {"schema": "flywheel.import-plan/v1", "client": client, "owner_ref": owner_ref,
            "state": "OK", "items": [], "refused": list(refused),
            "not_imported": list(not_imported), "sweep": sweep,
            "root": str(root) if root is not None else None}
    try:
        key = custody_key(home, owner_ref)
        listed, stored = entries(home, owner_ref), ImportStore(home, owner_ref).index()
    except ExclusionUnavailable:
        return {**plan, "state": "CUSTODY_KEY_UNAVAILABLE"}
    for source in sources:
        rel = {k: v for k, v in source.items() if k != "path"}
        rel["path"] = str(source["path"])
        plan["items"].append({**rel, **_safe_state(key, listed, stored, client, source, now,
                                                   live_window_s)})
    need = sum(i["size"] for i in plan["items"] if i["state"] in ("new", "grown"))
    free = (free_space or (lambda p: shutil.disk_usage(p).free))(Path(home))
    plan.update(need=need, free=free)
    if need and need + MARGIN > free:
        plan["state"] = "INSUFFICIENT_SPACE"
    return plan


class _Sink:
    """Where one source's bytes go while it streams: the staged item, the
    keyed digests, and the line analyzer (through zstd for compressed)."""

    def __init__(self, key, listed, item, staged) -> None:
        from .trace_import_lines import LineAnalyzer
        from .trace_zstd import Stream
        self.staged = staged
        self.probe = PrefixProbe(key, [e.get("n", 0) for e in listed])
        self.whole = hmac.new(key, b"prefix\x00", hashlib.sha256)  # prefix_ref of all bytes
        self.lines = (LineAnalyzer(LINE_BOUND, DEPTH_BOUND, turn_ids=item["kind"] in CODEX_KINDS)
                      if item["kind"] in JSONL_KINDS else None)
        feed = self.lines.feed if self.lines else (lambda piece: None)
        self.stream = Stream(feed) if item["kind"] == "compressed_rollout" else None
        self.feed = self.stream.feed if self.stream else feed

    def take(self, chunk: bytes) -> None:
        self.probe.feed(chunk)
        self.whole.update(chunk)
        self.staged.write(chunk)
        self.feed(chunk)


def _manifest(item, read, ref, sink) -> dict:
    from .trace_redact_rules import CATALOG_VERSION
    stats = sink.lines.finish() if sink.lines else {}
    return {"schema": "flywheel.import-manifest/v1", "client": item["client"],
            "rel": item["rel"], "kind": item["kind"], "session_id": item.get("session_id"),
            "source_ref": ref, "bytes": read["bytes"], "sha256": read["sha256"],
            "identity_before": [str(v) for v in read["before"]],
            "identity_after": [str(v) for v in read["after"]],
            "second_hash": read["second_hash"], "catalog_version": CATALOG_VERSION,
            "parser_version": PARSER_VERSION, "supersedes": item.get("supersedes"),
            "decompressed_bytes": sink.stream.produced if sink.stream else None, **stats}


def _import_one(store, key, listed, item, on_read) -> tuple[str | None, int]:
    from .trace_import_read import SourceRefused, read_source
    from .trace_zstd import InputBound
    path, staged = Path(item["path"]), store.stage(item["client"])
    try:
        sink = _Sink(key, listed, item, staged)
        read = read_source(path, sink.take, on_read=on_read, root=item.get("root"))
        ref = source_ref(key, item["client"], path, item.get("session_id"))
        excluded, _ = check(key, listed, ref, read["bytes"], sink.probe,
                            path_ref=keyed_path(key, item["client"], path),
                            session=session_ref(key, item["client"], item.get("session_id")))
        if excluded:
            staged.discard()
            return excluded, 0
    except (SourceRefused, InputBound) as refused:
        staged.discard()
        return refused.code, 0
    row = {"kind": item["kind"], "bytes": read["bytes"], "source_ref": ref,
           "content_ref": sink.whole.hexdigest(),
           "keyed_path": keyed_path(key, item["client"], path)}
    staged.finalize(_manifest(item, read, ref, sink), sink.lines.index if sink.lines else [],
                    row)
    return None, read["bytes"]


def run_import(home, plan: dict, *, on_read=None) -> dict:
    result = {"state": plan["state"], "imported": 0, "bytes": 0, "skipped": {},
              "refused": {}}
    if plan["state"] != "OK":
        return result
    owner = plan["owner_ref"]
    try:
        key = custody_key(home, owner)
    except ExclusionUnavailable:
        return {**result, "state": "CUSTODY_KEY_UNAVAILABLE"}
    listed, store = entries(home, owner), ImportStore(home, owner)
    for item in plan["items"]:
        if item["state"] not in ("new", "grown"):
            result["skipped"][item["state"]] = result["skipped"].get(item["state"], 0) + 1
            continue
        code, size = _import_one(store, key, listed, {**item, "client": plan["client"],
                                                      "root": plan.get("root")}, on_read)
        if code:
            bucket = "skipped" if code.startswith("PREVIOUSLY") else "refused"
            result[bucket][code] = result[bucket].get(code, 0) + 1
            continue
        result["imported"] += 1
        result["bytes"] += size
    _ledger(home, owner, plan["client"], result)
    return result


def _ledger(home, owner: str, client: str, result: dict) -> None:
    from .trace_custody_ledger import CustodyLedger
    CustodyLedger(home, owner).append("import", {
        "client": client, "items": result["imported"], "bytes": result["bytes"],
        "skipped": sum(result["skipped"].values()), "refused": sum(result["refused"].values())})
