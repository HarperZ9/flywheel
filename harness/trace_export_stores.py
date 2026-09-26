"""What each exported store contributes to an export (7.5).

Gateway traces (S1) are written as the exact canonical records the trace
route returns, so their chains re-derive; they are never redacted. Captured
turns (CT), capture snapshots (S8b) and imported transcript lines (IM) pass
through the export's redactor. An imported item that is not a JSON-lines
transcript cannot be redacted line by line; a redacted export omits it and
says so, and `--no-redact` exports its exact bytes.
"""
from __future__ import annotations

import json
from pathlib import Path

from .evidence_json import canonical_bytes

JSONL_KINDS = ("transcript", "subagent", "variant", "rollout", "archived_rollout",
               "compressed_rollout")


def _trace_folders(state: Path, owner: str):
    from .trace_delete_adapters_enc import _first_record_ref
    base = state / "gateway-agent-traces" / "v1" / "owners" / owner
    for folder in sorted(base.iterdir()) if base.is_dir() else []:
        ref = _first_record_ref(folder) if (folder / "00000000.json").is_file() else None
        if ref:
            yield folder, ref


def gateway_traces(home: Path, owner: str) -> list[tuple[str, list[dict]]]:
    """(trace ref, verified records) for every gateway trace of the owner."""
    from .trace_delete_adapters_plain import _trace_records
    state = home / "state"
    return [(ref, _trace_records(state, owner, {"rel": folder.relative_to(state).as_posix(),
                                               "item": ref, "operation": folder.name}))
            for folder, ref in _trace_folders(state, owner)]


def gateway_trace_records(home) -> list[dict]:
    """Inventory export adapter for S1: every owner's verified records."""
    home = Path(home)
    base = home / "state" / "gateway-agent-traces" / "v1" / "owners"
    owners = sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
    return [record for owner in owners for _, records in gateway_traces(home, owner)
            for record in records]


class Collector:
    """Writes store files into the staging folder and keeps the header."""

    def __init__(self, folder: Path, redactor) -> None:
        self.folder, self.redactor = folder, redactor
        self.files: list[dict] = []
        self.traces, self.lineage, self.omissions, self.unredacted = [], [], [], []

    def write(self, rel: str, data: bytes, store: str | None, item_ref: str | None) -> None:
        from .trace_export_manifest import file_entry
        path = self.folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.files.append(file_entry(rel, data, store, item_ref))

    def lines(self, rel: str, docs, store: str, item_ref: str | None) -> None:
        text = "".join(self.redactor.line(canonical_bytes(d).decode("utf-8")) + "\n"
                       for d in docs)
        self.write(rel, text.encode("utf-8"), store, item_ref)

    def gateway(self, home: Path, owner: str) -> None:
        from .trace_redact import scan
        for ref, records in gateway_traces(home, owner):
            raw = [canonical_bytes(r) for r in records]
            self.write(f"stores/S1/{ref}.jsonl", b"".join(r + b"\n" for r in raw), "S1", ref)
            self.traces.append({"store": "S1", "item_ref": ref, "path": f"stores/S1/{ref}.jsonl",
                                "records": len(records),
                                "head": records[-1]["record_sha256"] if records else None})
            counts: dict[str, int] = {}
            for line in raw:
                for hit in scan(line.decode("utf-8"), personal=True):
                    counts[hit.rule_id] = counts.get(hit.rule_id, 0) + 1
            if counts:
                self.unredacted.append({"item_ref": ref, "counts": counts})

    def turns(self, home: Path, owner: str) -> list[dict]:
        from .trace_turn_store import TurnStore
        store = TurnStore(home, owner)
        docs = [store.read_turn(t["turn_ref"]) for t in store.turns()]
        for doc in docs:
            self.lines(f"stores/CT/{doc['turn_ref']}.jsonl", [doc], "CT", doc["turn_ref"])
        return docs

    def snapshots(self, home: Path, owner: str, turns: list[dict]) -> None:
        from .trace_capture_freeze import export_records
        base = home / "state" / "capture-snapshots" / "v1" / "owners" / owner
        mine = {p.stem for p in base.glob("snap_*.enc")} if base.is_dir() else set()
        done = set()
        for doc in export_records(home):
            if doc["snap_ref"] in mine:
                self.lines(f"stores/S8b/{doc['snap_ref']}.jsonl", [doc], "S8b", doc["snap_ref"])
                done.add(doc["snap_ref"])
        for turn in turns:
            for source in (turn.get("freeze") or {}).get("sources", []):
                if source["snap_ref"] in done:
                    self.lineage.append([turn["turn_ref"], source["snap_ref"]])

    def _import_item(self, store, ref: str, manifest: dict) -> None:
        data = store.read_bytes(ref)
        if manifest["kind"] not in JSONL_KINDS:
            if self.redactor.active:
                self.omissions.append({"store": "IM", "item_ref": ref, "reason":
                                       "not a JSON-lines transcript, so it cannot be redacted; "
                                       "exported only with --no-redact"})
                return
            self.write(f"stores/IM/{ref}.bin", data, "IM", ref)
            return
        if self.redactor.active:
            text = "".join(self.redactor.line(line.decode("utf-8", "replace")) + "\n"
                           for line in data.splitlines())
            data = text.encode("utf-8")
        self.write(f"stores/IM/{ref}.jsonl", data, "IM", ref)

    def imports(self, home: Path, owner: str) -> None:
        from .trace_import_items import ImportStore
        store = ImportStore(home, owner)
        index = []
        for ref in store.item_refs():
            manifest = store.manifest(ref)
            self._import_item(store, ref, manifest)
            index.append({k: manifest.get(k) for k in ("item_ref", "client", "kind", "rel",
                                                       "session_id", "bytes", "supersedes")})
        exported = {f["item_ref"] for f in self.files}
        self.lineage += [[row["item_ref"], row["supersedes"]] for row in index
                         if row["supersedes"] in exported and row["item_ref"] in exported]
        if index:
            self.lines("stores/IM/index.jsonl", index, "IM", None)

    def tombstones(self, home: Path, owner: str) -> None:
        from .trace_tombstones import TombstoneLedger
        entries = TombstoneLedger(home / "state", owner).entries()
        self.write("tombstones.jsonl", b"".join(canonical_bytes(e) + b"\n" for e in entries),
                   "TD", None)


def dump(doc: dict) -> bytes:
    return json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False).encode("utf-8")
