"""In-memory fakes mirroring the external engine surfaces the adapters wrap.

These stand in for mneme's Store and flywheel's store module in F1 tests. Each
mirrors the exact surface read directly from source this session, so a test
against the fake exercises the same contract the real engine will:

  FakeMnemeStore    memories table shape and semantics from
                    mneme/src/mneme/{schema.py, store.py}: source_ids stored as
                    JSON text, a content-hash collision guard on re-put, a
                    monotonic created_ord, and supersede() setting valid_until +
                    superseded_by.
  FakeFlywheelStore entities keyed by eid (INSERT OR REPLACE), get_entity/
                    query_all_entities returning the shapes in
                    flywheel/harness/store.py.

Rows are plain dicts, which support the ["col"] access the adapters use exactly
as sqlite3.Row does.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _sha(*parts: Any) -> str:
    return hashlib.sha256(
        json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


class FakeMnemeStore:
    LAYERS = ("L0", "L1", "L2", "L3")

    def __init__(self) -> None:
        self._rows: dict[str, dict] = {}
        self._ord = 0

    def _next_ord(self) -> int:
        self._ord += 1
        return self._ord

    def add_memory(self, memory_id, layer, text, source_ids, extractor,
                   criterion, session=None, user=""):
        if layer not in self.LAYERS:
            raise ValueError(f"layer must be one of {self.LAYERS}, got {layer!r}")
        if isinstance(source_ids, (str, bytes)):
            raise ValueError("source_ids must be an iterable of source-id strings")
        sids = list(source_ids)
        sha = _sha(text, sids, criterion)
        prior = self._rows.get(memory_id)
        if prior is not None:
            if prior["user"] != user:
                raise ValueError(
                    f"memory id {memory_id!r} already owned by user "
                    f"{prior['user']!r}; refusing cross-tenant overwrite")
            if prior["content_sha256"] != sha:
                raise ValueError(
                    f"memory id {memory_id!r} exists with different content")
        self._rows[memory_id] = {
            "id": memory_id, "layer": layer, "session": session, "user": user,
            "text": text, "source_ids": json.dumps(sids), "extractor": extractor,
            "criterion": criterion, "content_sha256": sha,
            "created_ord": self._next_ord(), "valid_until": None,
            "superseded_by": None, "source_hashes": "{}"}
        return {"memory_id": memory_id, "sha256": sha}

    def memory(self, memory_id):
        return self._rows.get(memory_id)

    def memories(self, layer=None, session=None, user=None, *, as_of=None,
                 include_superseded=False):
        rows = sorted(self._rows.values(), key=lambda r: r["created_ord"])
        out = []
        for r in rows:
            if layer and r["layer"] != layer:
                continue
            if session and r["session"] != session:
                continue
            if user is not None and r["user"] != user:
                continue
            if not include_superseded and r["valid_until"] is not None:
                continue
            out.append(r)
        return out

    def supersede(self, old_id, new_id, reason=""):
        row = self._rows.get(old_id)
        if row is None or row["valid_until"] is not None:
            return None
        row["valid_until"] = self._next_ord()
        row["superseded_by"] = new_id
        return {"op": "supersede", "old": old_id, "new": new_id}


class FakeFlywheelStore:
    def __init__(self) -> None:
        self._ent: dict[str, dict] = {}
        self._ord = 0

    def put_entity(self, kind, data, *, project="", eid=None):
        kind = (kind or "").strip()
        if not kind:
            return {"error": "provide a non-empty 'kind'"}
        sha = _sha({"kind": kind, "project": project, "data": data})
        eid = (eid or sha[:24]).strip()
        self._ord += 1
        # flywheel json-serializes data; mimic the round-trip so the store
        # never aliases the caller's dict.
        blob = json.loads(json.dumps(data, default=str))
        self._ent[eid] = {"eid": eid, "kind": kind, "project": project,
                          "data": blob, "sha256": sha, "created": self._ord}
        return {"eid": eid, "kind": kind, "sha256": sha, "chain_hash": ""}

    def get_entity(self, eid):
        e = self._ent.get(eid)
        if e is None:
            return None
        return {**e, "data": json.loads(json.dumps(e["data"]))}

    def query_entities(self, *, kind=None, project=None, limit=200, offset=0):
        rows = sorted(self._ent.values(), key=lambda e: e["created"],
                      reverse=True)
        rows = [e for e in rows
                if (kind is None or e["kind"] == kind)
                and (project is None or e["project"] == project)]
        page = rows[offset:offset + limit]
        return [{"eid": e["eid"], "kind": e["kind"], "project": e["project"],
                 "sha256": e["sha256"], "created": e["created"]} for e in page]

    def query_all_entities(self, *, kind=None, project=None, chunk=500):
        return self.query_entities(kind=kind, project=project, limit=10 ** 9)


# --- M4.1 transport handle fake ---------------------------------------------
from canon.schema import SCHEMA  # noqa: E402


class FakeRelayHandle:
    """Wire-side mock. Each knob wires to one refusal branch a real relay could
    trip. Not a Transport; a low-level handle a Transport wraps."""

    def __init__(self, *, unreachable=False, corrupt_on_fetch=False,
                 wrong_pin_on_fetch=None, oversize_on_fetch=False,
                 auth_refused=False, rate_limited_every=None,
                 spoof_wrong_key=False, duplicate_push_tampered=False):
        self.unreachable = unreachable
        self.corrupt_on_fetch = corrupt_on_fetch
        self.wrong_pin_on_fetch = wrong_pin_on_fetch
        self.oversize_on_fetch = oversize_on_fetch
        self.auth_refused = auth_refused
        self.rate_limited_every = rate_limited_every
        self.spoof_wrong_key = spoof_wrong_key
        self.duplicate_push_tampered = duplicate_push_tampered
        self._store: dict[str, tuple[str, str]] = {}
        self._push_count = 0

    def put(self, key: str, envelope: str, idem: str) -> str:
        if self.unreachable:
            raise ConnectionError("unreachable")
        if self.auth_refused:
            raise PermissionError("401 auth refused")
        self._push_count += 1
        if (self.rate_limited_every
                and self._push_count % self.rate_limited_every == 0):
            err = RuntimeError("429 rate limited")
            err.retry_after = 0.5  # type: ignore[attr-defined]
            raise err
        prior = self._store.get(key)
        if (prior is not None and prior[1] == idem
                and self.duplicate_push_tampered):
            raise ValueError(
                f"duplicate push with idem={idem!r}, tampered payload")
        self._store[key] = (envelope, idem)
        return idem

    def get(self, key: str) -> str | None:
        if self.unreachable:
            raise ConnectionError("unreachable")
        row = self._store.get(key)
        if row is None:
            return None
        payload = row[0]
        if self.corrupt_on_fetch:
            return "{not valid json"
        if self.wrong_pin_on_fetch is not None:
            return payload.replace(SCHEMA, self.wrong_pin_on_fetch)
        if self.oversize_on_fetch:
            return payload[:-1] + ',"pad":"' + ("X" * 4096) + '"}'
        if self.spoof_wrong_key:
            tail = key.split("/", 1)[-1]
            # The inner record json is JSON-escaped inside the envelope, so we
            # match the escaped form of "id": "<tail>".
            token = f'\\"id\\": \\"{tail}\\"'
            return payload.replace(token, f'\\"id\\": \\"{tail}-forged\\"')
        return payload

    def list_keys(self, scope: str) -> list[str]:
        if self.unreachable:
            raise ConnectionError("unreachable")
        return sorted(k for k in self._store if k.startswith(scope + "/"))
