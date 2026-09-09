"""Immutable private selected-source snapshots for approved gateway runs."""
from __future__ import annotations

from pathlib import Path
import re

from .evidence_json import canonical_sha256
from .operation_grants import OWNER_REF_PATTERN
from .source_context_error import SourceContextError
from .source_context_payload import (
    BINDING_SCHEMA, PRIVATE_SCHEMA, PROJECTION_SCHEMA, SOURCE_REF_PREFIX,
    WORKER_SCHEMA, _hex, _safe_name, _sha_text, journey_basis_for,
    projection_for, validated_gather_payload, worker_context_for,
)
from .source_context_store_io import MAX_PRIVATE_BYTES, _json_file, _write_once
from .source_context_identity import current_identity


def _owner(value: object) -> str:
    if type(value) is not str or OWNER_REF_PATTERN.fullmatch(value) is None:
        raise SourceContextError("SOURCE_CONTEXT_PERMISSION_DENIED")
    return value


class SourceContextStore:
    """Publish and resolve owner-scoped immutable selected-source snapshots."""

    def __init__(self, state_root: Path, *, clock=None,
                 expected_state_root_identity: dict | None = None) -> None:
        self.state_root = Path(state_root)
        self.root = self.state_root / "source-context" / "v1"
        self.clock = clock or (lambda: None)
        self.expected_state_root_identity = expected_state_root_identity

    def state_root_identity(self) -> dict:
        if self.expected_state_root_identity is not None:
            return dict(self.expected_state_root_identity)
        return current_identity(self.state_root)

    def publish_selection(self, *, owner_ref: str, state_root_identity: dict,
                          root_mode: str, profile: str, corpus_locator: str,
                          corpus_root_identity: dict, gather_payload: dict,
                          selected_at: str) -> dict:
        owner, profile = _owner(owner_ref), _safe_name(profile)
        actual_state = self.state_root_identity()
        if state_root_identity != actual_state:
            raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
        if root_mode != "flywheel_corpus":
            raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
        rows, caps = validated_gather_payload(gather_payload)
        private = {"schema": PRIVATE_SCHEMA, "owner_ref": owner,
            "state_root_identity": actual_state, "root_mode": root_mode,
            "profile": profile, "corpus_locator_sha256": _sha_text(corpus_locator),
            "corpus_root_identity": corpus_root_identity,
            "gather_schema": gather_payload["schema"], "caps": caps,
            "corpus_digest": _hex(gather_payload.get("corpus_digest")),
            "selection_digest": _hex(gather_payload.get("selection_digest")),
            "rows": rows, "row_count": len(rows),
            "total_text_chars": gather_payload.get("total_text_chars"),
            "selected_text_utf8_bytes": sum(r["selected_text_utf8_bytes"] for r in rows),
            "omissions": list(gather_payload.get("omissions") or []),
            "does_not_prove": list(gather_payload.get("does_not_prove") or []),
            "source_framing_policy": "flywheel.untrusted-source-data/v1"}
        private_hash = canonical_sha256(private)
        ref = f"{SOURCE_REF_PREFIX}{private_hash[:32]}"
        projection = projection_for(ref, private, private_hash)
        projection_hash = canonical_sha256(projection)
        binding = _binding(owner, ref, actual_state, private, private_hash, projection_hash)
        self._publish(owner, ref, actual_state, private_hash, projection_hash,
                      private, projection, binding)
        return {"schema": "flywheel.source-context-attach/v1",
            "source_context_ref": ref, "private_payload_sha256": private_hash,
            "projection_sha256": projection_hash, "projection": projection,
            "binding": binding, "selected_at": selected_at,
            "journey_basis": journey_basis_for(ref, projection)}

    def _publish(self, owner: str, ref: str, actual_state: dict,
                 private_hash: str, projection_hash: str, private: dict,
                 projection: dict, binding: dict) -> None:
        base = self.root / "owners" / owner
        _write_once(base / "payloads" / f"{private_hash}.json", private,
            state_root=self.state_root, expected_root_identity=actual_state)
        _write_once(base / "projections" / f"{projection_hash}.json",
            projection, state_root=self.state_root,
            expected_root_identity=actual_state)
        _write_once(base / "bindings" / f"{private_hash}.json", binding,
            state_root=self.state_root, expected_root_identity=actual_state)
        _write_once(base / "refs" / f"{ref.removeprefix(SOURCE_REF_PREFIX)}.json",
            {"schema": "flywheel.source-context-ref/v1", "source_context_ref": ref,
             "private_payload_sha256": private_hash,
             "projection_sha256": projection_hash}, state_root=self.state_root,
            expected_root_identity=actual_state)

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
            contexts.append(worker_context_for(private, projection, binding))
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
        base, actual = self.root / "owners" / owner, self.state_root_identity()
        ref_path = base / "refs" / f"{suffix}.json"
        if not ref_path.exists():
            raise SourceContextError("SOURCE_CONTEXT_REF_NOT_FOUND" if base.exists()
                else "SOURCE_CONTEXT_PERMISSION_DENIED")
        record = _json_file(ref_path, state_root=self.state_root,
            expected_root_identity=actual)
        private_hash = _hex(record.get("private_payload_sha256"), "SOURCE_CONTEXT_STORE_CORRUPT")
        projection_hash = _hex(record.get("projection_sha256"), "SOURCE_CONTEXT_STORE_CORRUPT")
        if (record.get("schema") != "flywheel.source-context-ref/v1"
                or record.get("source_context_ref") != ref or private_hash[:32] != suffix):
            raise SourceContextError("SOURCE_CONTEXT_REF_COLLISION")
        private = _json_file(base / "payloads" / f"{private_hash}.json",
            state_root=self.state_root, expected_root_identity=actual)
        projection = _json_file(base / "projections" / f"{projection_hash}.json",
            state_root=self.state_root, expected_root_identity=actual)
        binding = _json_file(base / "bindings" / f"{private_hash}.json",
            state_root=self.state_root, expected_root_identity=actual)
        self._validate_resolved(owner, ref, actual, private_hash,
            projection_hash, private, projection, binding)
        return private, projection, binding

    def _validate_resolved(self, owner: str, ref: str, actual: dict,
                           private_hash: str, projection_hash: str,
                           private: dict, projection: dict, binding: dict) -> None:
        if private.get("schema") != PRIVATE_SCHEMA or projection.get("schema") != PROJECTION_SCHEMA:
            raise SourceContextError("SOURCE_CONTEXT_STORE_CORRUPT")
        if canonical_sha256(private) != private_hash or canonical_sha256(projection) != projection_hash:
            raise SourceContextError("SOURCE_CONTEXT_STORE_CORRUPT")
        expected_projection = projection_for(ref, private, private_hash)
        expected_binding = _binding(owner, ref, actual, private, private_hash, projection_hash)
        if (projection != expected_projection or binding != expected_binding
                or private.get("owner_ref") != owner
                or private.get("state_root_identity") != actual):
            raise SourceContextError("SOURCE_CONTEXT_STORE_CORRUPT")


def _binding(owner: str, ref: str, state_identity: dict, private: dict,
             private_hash: str, projection_hash: str) -> dict:
    return {"schema": BINDING_SCHEMA, "owner_ref": owner,
        "state_root_identity": state_identity, "root_mode": private.get("root_mode"),
        "profile": private.get("profile"), "source_context_ref": ref,
        "private_payload_sha256": private_hash, "projection_sha256": projection_hash,
        "corpus_locator_sha256": private.get("corpus_locator_sha256"),
        "corpus_root_identity": private.get("corpus_root_identity"),
        "corpus_digest": private.get("corpus_digest"),
        "selection_digest": private.get("selection_digest")}
