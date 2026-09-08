"""Immutable private selected-source snapshots for approved gateway runs."""
from __future__ import annotations

from pathlib import Path
import hashlib
import os
import re

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .operation_grants import OWNER_REF_PATTERN, _secure_owner_only

PRIVATE_SCHEMA = "flywheel.source-context-private/v1"
PROJECTION_SCHEMA = "flywheel.source-context-projection/v1"
BINDING_SCHEMA = "flywheel.source-context-binding/v1"
WORKER_SCHEMA = "flywheel.source-context-worker-payload/v1"
SOURCE_REF_PREFIX = "data_source_context."
MAX_PRIVATE_BYTES = 1_000_000
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class SourceContextError(RuntimeError):
    """One fixed source-context failure, with no private text in its message."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "strict")).hexdigest()


def _safe_name(value: object, code: str = "INVALID_REQUEST") -> str:
    if type(value) is not str or _SAFE.fullmatch(value) is None:
        raise SourceContextError(code)
    return value


def _owner(value: object) -> str:
    if type(value) is not str or OWNER_REF_PATTERN.fullmatch(value) is None:
        raise SourceContextError("SOURCE_CONTEXT_PERMISSION_DENIED")
    return value


def _hex(value: object, code: str = "SOURCE_CONTEXT_SELECTION_FAILED") -> str:
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        raise SourceContextError(code)
    return value


def _json_file(path: Path, *, max_bytes: int = MAX_PRIVATE_BYTES) -> dict:
    try:
        return strict_load_json(path.read_bytes(), max_bytes=max_bytes, max_depth=24)
    except Exception:
        raise SourceContextError("SOURCE_CONTEXT_STORE_CORRUPT") from None


def _write_once(path: Path, value: dict) -> None:
    data = canonical_bytes(value)
    if len(data) > MAX_PRIVATE_BYTES:
        raise SourceContextError("SOURCE_CONTEXT_STORE_COMMIT_FAILED")
    path.parent.mkdir(parents=True, exist_ok=True)
    _secure_owner_only(path.parent, directory=True)
    if path.exists():
        if path.read_bytes() != data:
            raise SourceContextError("SOURCE_CONTEXT_REF_COLLISION")
        _secure_owner_only(path, directory=False)
        return
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, data); os.fsync(fd)
        finally:
            os.close(fd)
        _secure_owner_only(tmp, directory=False)
        try:
            os.link(tmp, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise SourceContextError("SOURCE_CONTEXT_REF_COLLISION")
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
        _secure_owner_only(path, directory=False)
    except SourceContextError:
        raise
    except OSError:
        raise SourceContextError("SOURCE_CONTEXT_DURABILITY_UNAVAILABLE") from None


def _row(row: dict) -> dict:
    span = row.get("range")
    text = row.get("text")
    if type(row) is not dict or type(span) is not dict or type(text) is not str:
        raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED")
    start, end = span.get("start"), span.get("end")
    if type(start) is not int or type(end) is not int or start < 0 or end < start:
        raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    full_hash = row.get("verified_sha256") or row.get("sha256")
    return {
        "row_ref": _safe_name(row.get("row_ref")),
        "kind": _safe_name(row.get("kind")),
        "id_sha256": _sha_text(str(row.get("id", ""))),
        "source_ref": str(row.get("ref", "")),
        "source_ref_sha256": _sha_text(str(row.get("ref", ""))),
        "method": _safe_name(row.get("method")),
        "normalized_full_text_sha256": _hex(full_hash),
        "range": {"start": start, "end": end},
        "text": normalized,
        "selected_text_utf8_bytes": len(normalized.encode("utf-8", "strict")),
        "selected_text_utf8_sha256": _sha_text(normalized),
        "full_text_chars": int(row.get("full_text_chars", 0)),
        "body_bytes_read": int(row.get("body_bytes_read", 0)),
        "omissions": list(row.get("omissions") or []),
    }


def _rows(payload: dict) -> list[dict]:
    rows = payload.get("selections")
    if type(rows) is not list or not rows:
        raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED")
    return [_row(row) for row in rows]


class SourceContextStore:
    """Publish and resolve owner-scoped immutable selected-source snapshots."""

    def __init__(self, state_root: Path, *, clock=None) -> None:
        self.root = Path(state_root) / "source-context" / "v1"
        self.clock = clock or (lambda: None)

    def publish_selection(self, *, owner_ref: str, state_root_identity: dict,
                          root_mode: str, profile: str, corpus_locator: str,
                          corpus_root_identity: dict, gather_payload: dict,
                          selected_at: str) -> dict:
        owner, profile = _owner(owner_ref), _safe_name(profile)
        if root_mode != "flywheel_corpus":
            raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
        if gather_payload.get("schema") != "gather.readable-context/v1":
            raise SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED")
        rows = _rows(gather_payload)
        private = {
            "schema": PRIVATE_SCHEMA, "owner_ref": owner,
            "state_root_identity": state_root_identity,
            "root_mode": root_mode, "profile": profile,
            "corpus_locator_sha256": _sha_text(corpus_locator),
            "corpus_root_identity": corpus_root_identity,
            "gather_schema": gather_payload["schema"],
            "corpus_digest": _hex(gather_payload.get("corpus_digest")),
            "selection_digest": _hex(gather_payload.get("selection_digest")),
            "rows": rows, "row_count": len(rows),
            "selected_text_utf8_bytes": sum(
                row["selected_text_utf8_bytes"] for row in rows),
            "omissions": list(gather_payload.get("omissions") or []),
            "does_not_prove": list(gather_payload.get("does_not_prove") or []),
            "source_framing_policy": "flywheel.untrusted-source-data/v1",
        }
        private_hash = canonical_sha256(private)
        ref = f"{SOURCE_REF_PREFIX}{private_hash[:32]}"
        projection = _projection(ref, private, private_hash)
        projection_hash = canonical_sha256(projection)
        binding = {
            "schema": BINDING_SCHEMA, "owner_ref": owner,
            "state_root_identity": state_root_identity,
            "root_mode": root_mode, "profile": profile,
            "source_context_ref": ref,
            "private_payload_sha256": private_hash,
            "projection_sha256": projection_hash,
            "corpus_digest": private["corpus_digest"],
            "selection_digest": private["selection_digest"],
        }
        self._publish(owner, ref, private_hash, projection_hash,
                      private, projection, binding)
        return {"schema": "flywheel.source-context-attach/v1",
                "source_context_ref": ref, "private_payload_sha256": private_hash,
                "projection_sha256": projection_hash, "projection": projection,
                "binding": binding, "selected_at": selected_at,
                "journey_basis": _journey_basis(ref, projection)}

    def _publish(self, owner: str, ref: str, private_hash: str,
                 projection_hash: str, private: dict, projection: dict,
                 binding: dict) -> None:
        base = self.root / "owners" / owner
        _write_once(base / "payloads" / f"{private_hash}.json", private)
        _write_once(base / "projections" / f"{projection_hash}.json", projection)
        _write_once(base / "bindings" / f"{private_hash}.json", binding)
        _write_once(base / "refs" / f"{ref.removeprefix(SOURCE_REF_PREFIX)}.json",
                    {"schema": "flywheel.source-context-ref/v1",
                     "source_context_ref": ref,
                     "private_payload_sha256": private_hash,
                     "projection_sha256": projection_hash})

    def read_private_for_test(self, owner_ref: str, ref: str) -> dict:
        private, _projection, _binding = self._resolve(_owner(owner_ref), ref)
        return private

    def resolve_worker_payload(self, owner_ref: str,
                               data_refs: tuple[str, ...] | list[str]) -> dict | None:
        contexts, owner = [], _owner(owner_ref)
        for ref in data_refs:
            if not (type(ref) is str and ref.startswith(SOURCE_REF_PREFIX)):
                continue
            private, projection, binding = self._resolve(owner, ref)
            contexts.append(_worker_context(private, projection, binding))
        if not contexts:
            return None
        payload = {"schema": WORKER_SCHEMA, "contexts": contexts,
                   "does_not_prove": sorted({item for ctx in contexts
                       for item in ctx.get("does_not_prove", [])})}
        return dict(payload, source_payload_sha256=canonical_sha256(payload))

    def _resolve(self, owner: str, ref: str) -> tuple[dict, dict, dict]:
        if type(ref) is not str or not ref.startswith(SOURCE_REF_PREFIX):
            raise SourceContextError("SOURCE_CONTEXT_REF_NOT_FOUND")
        suffix = ref.removeprefix(SOURCE_REF_PREFIX)
        if re.fullmatch(r"[0-9a-f]{32}\Z", suffix) is None:
            raise SourceContextError("SOURCE_CONTEXT_REF_NOT_FOUND")
        base = self.root / "owners" / owner
        ref_path = base / "refs" / f"{suffix}.json"
        if not ref_path.exists():
            raise SourceContextError(
                "SOURCE_CONTEXT_REF_NOT_FOUND" if base.exists()
                else "SOURCE_CONTEXT_PERMISSION_DENIED")
        record = _json_file(ref_path)
        private_hash = _hex(record.get("private_payload_sha256"),
                            "SOURCE_CONTEXT_STORE_CORRUPT")
        if record.get("source_context_ref") != ref or private_hash[:32] != suffix:
            raise SourceContextError("SOURCE_CONTEXT_REF_COLLISION")
        private = _json_file(base / "payloads" / f"{private_hash}.json")
        projection_hash = _hex(record.get("projection_sha256"),
                               "SOURCE_CONTEXT_STORE_CORRUPT")
        projection = _json_file(base / "projections" / f"{projection_hash}.json")
        binding = _json_file(base / "bindings" / f"{private_hash}.json")
        if (canonical_sha256(private) != private_hash
                or canonical_sha256(projection) != projection_hash
                or private.get("owner_ref") != owner
                or binding.get("owner_ref") != owner
                or binding.get("source_context_ref") != ref
                or binding.get("private_payload_sha256") != private_hash
                or binding.get("projection_sha256") != projection_hash):
            raise SourceContextError("SOURCE_CONTEXT_STORE_CORRUPT")
        return private, projection, binding


def _projection(ref: str, private: dict, private_hash: str) -> dict:
    rows = [{"row_ref": row["row_ref"],
             "range": row["range"],
             "selected_text_utf8_bytes": row["selected_text_utf8_bytes"],
             "selected_text_utf8_sha256_prefix":
                 row["selected_text_utf8_sha256"][:16],
             "normalized_full_text_sha256_prefix":
                 row["normalized_full_text_sha256"][:16],
             "omissions": row["omissions"]} for row in private["rows"]]
    return {"schema": PROJECTION_SCHEMA, "source_context_ref": ref,
            "private_payload_sha256": private_hash,
            "root_mode": private["root_mode"], "profile": private["profile"],
            "row_count": private["row_count"], "rows": rows,
            "selected_text_utf8_bytes": private["selected_text_utf8_bytes"],
            "omissions": private["omissions"],
            "does_not_prove": private["does_not_prove"]}


def _journey_basis(ref: str, projection: dict) -> dict:
    return {"source_context_ref": ref,
            "projection_sha256": canonical_sha256(projection),
            "row_count": projection["row_count"],
            "selected_text_utf8_bytes": projection["selected_text_utf8_bytes"],
            "omissions": projection["omissions"],
            "does_not_prove": projection["does_not_prove"]}


def _worker_context(private: dict, projection: dict, binding: dict) -> dict:
    rows = [{"row_ref": row["row_ref"], "range": row["range"],
             "text": row["text"],
             "selected_text_utf8_bytes": row["selected_text_utf8_bytes"],
             "selected_text_utf8_sha256": row["selected_text_utf8_sha256"],
             "normalized_full_text_sha256":
                 row["normalized_full_text_sha256"],
             "omissions": row["omissions"]} for row in private["rows"]]
    return {"source_context_ref": binding["source_context_ref"],
            "private_payload_sha256": binding["private_payload_sha256"],
            "projection_sha256": binding["projection_sha256"],
            "projection": projection, "rows": rows,
            "does_not_prove": private["does_not_prove"]}
