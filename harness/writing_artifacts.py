"""Private owner-scoped artifact custody for Writing Workspace."""
from __future__ import annotations
import os
from pathlib import Path
from .evidence_json import canonical_bytes, strict_load_json
from .evidence_public import TransportError
from .writing_types import (
    MAX_ARTIFACT_JSON_BYTES, MAX_AUTHOR_TEXT_BYTES,
    MAX_BRIEF_JSON_BYTES, MAX_MANUSCRIPT_TEXT_BYTES, MAX_SOURCE_PACKET_BYTES,
    WRITING_DOES_NOT_PROVE, WritingTypeError,
    admit_text, canonical_digest, require_ref, require_sha, sha256_bytes,
    validate_artifact,
)
class WritingArtifactError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
def _contained(root: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath((
            os.path.normcase(str(root)),
            os.path.normcase(str(candidate)),
        )) == os.path.normcase(str(root))
    except ValueError:
        return False
def _is_reparse(path: Path) -> bool:
    try:
        attrs = getattr(path.lstat(), "st_file_attributes", 0)
        return path.is_symlink() or bool(attrs & 0x400)
    except OSError:
        return False
class WritingArtifactStore:
    """Write-once artifact store under ``state/artifacts``."""
    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)
        self.root = self.state_root / "artifacts"
        if self.state_root.exists():
            self._reject_reparse_chain(self.state_root, self.state_root)
        if self.root.exists():
            self._reject_reparse_chain(self.state_root, self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._root_abs = self.root.absolute()
        self._reject_reparse_chain(self.root, self.root)
    def write_json(self, owner_ref: str, project_ref: str, kind: str, name: str,
                   value: dict) -> dict:
        owner_ref, project_ref = self._owner_project(owner_ref, project_ref)
        artifact = validate_artifact(value, kind)
        if artifact["project_ref"] != project_ref:
            raise WritingArtifactError("PROJECT_MISMATCH")
        raw, digest = canonical_digest(artifact)
        return self._write(owner_ref, project_ref, kind, name, ".json", raw,
                           digest, _cap(kind))
    def write_text(self, owner_ref: str, project_ref: str, kind: str, name: str,
                   raw: str | bytes, *, max_bytes: int = MAX_AUTHOR_TEXT_BYTES) -> dict:
        owner_ref, project_ref = self._owner_project(owner_ref, project_ref)
        _ = self._safe_name(kind); _ = self._safe_name(name)
        text, data, receipt = admit_text(raw, max_bytes=max_bytes)
        digest = sha256_bytes(data)
        record = self._write(owner_ref, project_ref, kind, name, ".txt", data,
                             digest, max_bytes)
        return {**record, "text": text, "text_admission": receipt}
    def write_manifest(self, owner_ref: str, project_ref: str, kind: str,
                       name: str, value: dict) -> dict:
        owner_ref, project_ref = self._owner_project(owner_ref, project_ref)
        raw = canonical_bytes(value)
        digest = sha256_bytes(raw)
        return self._write(owner_ref, project_ref, kind, name, ".json", raw,
                           digest, MAX_ARTIFACT_JSON_BYTES)
    def read_json(self, artifact_ref: str, expected_sha256: str | None = None,
                  *, expected_kind: str | None = None,
                  max_bytes: int = MAX_ARTIFACT_JSON_BYTES,
                  expected_owner_ref: str | None = None,
                  expected_project_ref: str | None = None) -> dict:
        path = self.path_for_ref(
            artifact_ref, max_bytes=max_bytes, expected_kind=expected_kind,
            expected_owner_ref=expected_owner_ref,
            expected_project_ref=expected_project_ref)
        raw = path.read_bytes()
        if len(raw) > max_bytes:
            raise WritingArtifactError("ARTIFACT_TOO_LARGE")
        self._match(raw, expected_sha256)
        try:
            value = strict_load_json(raw, max_bytes=max_bytes, max_depth=32)
            return validate_artifact(value, expected_kind)
        except (TypeError, ValueError, UnicodeError, RecursionError, WritingTypeError) as exc:
            raise WritingArtifactError("ARTIFACT_INVALID") from exc
    def read_text(self, artifact_ref: str, expected_sha256: str | None = None,
                  *, max_bytes: int = MAX_AUTHOR_TEXT_BYTES,
                  expected_owner_ref: str | None = None,
                  expected_project_ref: str | None = None) -> str:
        path = self.path_for_ref(
            artifact_ref, max_bytes=max_bytes,
            expected_owner_ref=expected_owner_ref,
            expected_project_ref=expected_project_ref)
        raw = path.read_bytes()
        if len(raw) > max_bytes:
            raise WritingArtifactError("ARTIFACT_TOO_LARGE")
        self._match(raw, expected_sha256)
        try:
            return raw.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise WritingArtifactError("TEXT_INVALID") from exc
    def path_for_ref(self, artifact_ref: str, *, max_bytes: int | None = None,
                     expected_owner_ref: str | None = None,
                     expected_project_ref: str | None = None,
                     expected_kind: str | None = None) -> Path:
        if type(artifact_ref) is not str or "\\" in artifact_ref:
            raise WritingArtifactError("ARTIFACT_REF_INVALID")
        parts = artifact_ref.split("/")
        if any(part in {"", ".", ".."} or ":" in part for part in parts):
            raise WritingArtifactError("ARTIFACT_REF_INVALID")
        self._match_scope(parts, expected_owner_ref, expected_project_ref,
                          expected_kind)
        candidate = self._root_abs.joinpath(*parts)
        if not _contained(self._root_abs, candidate.absolute()):
            raise WritingArtifactError("ARTIFACT_REF_INVALID")
        self._reject_reparse_chain(self.root, candidate.parent)
        if candidate.exists() and _is_reparse(candidate):
            raise WritingArtifactError("ARTIFACT_AUTHORITY")
        if not candidate.exists() or not candidate.is_file():
            raise WritingArtifactError("ARTIFACT_MISSING")
        if max_bytes is not None and candidate.stat().st_size > max_bytes:
            raise WritingArtifactError("ARTIFACT_TOO_LARGE")
        return candidate
    def exists(self, owner_ref: str, project_ref: str, kind: str, name: str,
               suffix: str) -> bool:
        rel = self._ref(owner_ref, project_ref, kind, name, suffix)
        try:
            self.path_for_ref(rel)
            return True
        except WritingArtifactError as exc:
            if exc.code == "ARTIFACT_MISSING":
                return False
            raise
    def _write(self, owner_ref: str, project_ref: str, kind: str, name: str,
               suffix: str, raw: bytes, digest: str, max_bytes: int) -> dict:
        if len(raw) > max_bytes:
            raise WritingArtifactError("ARTIFACT_TOO_LARGE")
        rel = self._ref(owner_ref, project_ref, kind, name, suffix)
        path = self._root_abs.joinpath(*rel.split("/"))
        if not _contained(self._root_abs, path.absolute()):
            raise WritingArtifactError("ARTIFACT_REF_INVALID")
        self._reject_reparse_chain(self.root, path.parent)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._reject_reparse_chain(self.root, path)
        if path.exists():
            if _is_reparse(path) or not path.is_file():
                raise WritingArtifactError("ARTIFACT_AUTHORITY")
            if path.stat().st_size > len(raw) + 1_024:
                raise WritingArtifactError("ARTIFACT_EXISTS")
            if path.read_bytes() == raw:
                return self._record(rel, raw, digest)
            raise WritingArtifactError("ARTIFACT_EXISTS")
        try:
            with path.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as exc:
            raise WritingArtifactError("ARTIFACT_EXISTS") from exc
        return self._record(rel, raw, digest)
    def _ref(self, owner_ref: str, project_ref: str, kind: str, name: str,
             suffix: str) -> str:
        owner_ref, project_ref = self._owner_project(owner_ref, project_ref)
        return "/".join((
            "writing", "v1", "owners", owner_ref, "projects", project_ref,
            self._safe_name(kind), f"{self._safe_name(name)}{suffix}",
        ))
    def _owner_project(self, owner_ref: str, project_ref: str) -> tuple[str, str]:
        try:
            return (require_ref(owner_ref, "owner_ref", "owner_"),
                    require_ref(project_ref, "project_ref", "wpr_"))
        except WritingTypeError as exc:
            raise WritingArtifactError(str(exc)) from exc
    @staticmethod
    def _safe_name(value: str) -> str:
        try:
            return require_ref(value, "artifact_name")
        except WritingTypeError as exc:
            raise WritingArtifactError("ARTIFACT_REF_INVALID") from exc
    def _reject_reparse_chain(self, start: Path, path: Path) -> None:
        start_abs, path_abs = start.absolute(), path.absolute()
        if not _contained(start_abs, path_abs):
            raise WritingArtifactError("ARTIFACT_REF_INVALID")
        current = start_abs
        for part in ("", *path_abs.relative_to(start_abs).parts):
            current = current if not part else current / part
            if current.exists() and _is_reparse(current):
                raise WritingArtifactError("ARTIFACT_AUTHORITY")
    @staticmethod
    def _match_scope(parts: list[str], owner: str | None, project: str | None,
                     kind: str | None) -> None:
        if owner is None and project is None and kind is None:
            return
        if (len(parts) < 8 or tuple(parts[:3]) != ("writing", "v1", "owners")
                or parts[4] != "projects"):
            raise WritingArtifactError("ARTIFACT_REF_INVALID")
        if ((owner is not None and parts[3] != owner)
                or (project is not None and parts[5] != project)
                or (kind is not None and parts[6] != kind)):
            raise WritingArtifactError("ARTIFACT_AUTHORITY")
    @staticmethod
    def _match(raw: bytes, expected_sha256: str | None) -> None:
        if expected_sha256 is None:
            return
        try:
            require_sha(expected_sha256, "expected_sha256")
        except WritingTypeError as exc:
            raise WritingArtifactError("ARTIFACT_SHA_INVALID") from exc
        if sha256_bytes(raw) != expected_sha256:
            raise WritingArtifactError("ARTIFACT_DRIFT")
    @staticmethod
    def _record(ref: str, raw: bytes, digest: str) -> dict:
        return {
            "artifact_ref": ref,
            "artifact_sha256": digest,
            "artifact_bytes": raw,
        }
def record_fact_for_artifact(store: WritingArtifactStore, command: dict, *,
                             owner_ref: str | None = None,
                             project_ref: str | None = None) -> dict:
    artifact_ref = command["artifact_ref"]
    artifact_sha256 = command["artifact_sha256"]
    kind = command["kind"]
    artifact = store.read_json(
        artifact_ref, artifact_sha256, expected_kind=kind,
        expected_owner_ref=owner_ref, expected_project_ref=project_ref)
    opaque = command.get("opaque_ref") or artifact.get(f"{kind}_ref") or artifact_ref
    if type(opaque) is not str:
        raise TransportError("INVALID_TRANSITION", "writing artifact is invalid", 422)
    return {
        "facts": [{
            "fact_id": f"writing:{kind}:{opaque}",
            "statement": f"Writing {kind} artifact recorded",
            "receipt_refs": [artifact_ref],
            "artifact_sha256": artifact_sha256,
            "receipt_state": "MATCH",
            "does_not_prove": WRITING_DOES_NOT_PROVE,
        }]
    }
def plan_writing_artifact_append(service, req: dict, command: dict) -> tuple[str, dict]:
    from .journey_store import JourneyStoreError
    projection = service.resume(req["journey_ref"])
    if projection["event_head_sha256"] != req["expected_event_head"]:
        raise JourneyStoreError("HEAD_CONFLICT")
    store = WritingArtifactStore(service.store.state_root)
    owner_ref = service.owner_ref
    events = service._events(req["journey_ref"])
    project_ref = events[0]["payload"].get("intake", {}).get("project_ref")
    try:
        artifact = store.read_json(
            command["artifact_ref"], command["artifact_sha256"],
            expected_kind=command["kind"], expected_owner_ref=owner_ref,
            expected_project_ref=project_ref)
    except WritingArtifactError as exc:
        raise TransportError("INVALID_TRANSITION", "writing artifact is invalid", 422) from exc
    if artifact.get("project_ref") != project_ref:
        raise TransportError(
            "INVALID_TRANSITION", "writing artifact project mismatch", 422)
    payload = record_fact_for_artifact(
        store, command, owner_ref=owner_ref, project_ref=project_ref)
    from .writing_projection import WritingProjectionError, validate_writing_append
    try:
        validate_writing_append(
            service, store, req, "record_fact",
            {"occurred_at": "1970-01-01T00:00:00Z", "payload": payload})
    except WritingProjectionError as exc:
        raise TransportError(exc.code, "writing artifact is invalid", 422) from exc
    return "record_fact", payload
def artifact_plan_body(value: dict) -> bytes:
    return canonical_bytes(validate_artifact(value))
def _cap(kind: str) -> int:
    if kind == "brief":
        return MAX_BRIEF_JSON_BYTES
    if kind == "source_packet":
        return MAX_SOURCE_PACKET_BYTES
    return MAX_MANUSCRIPT_TEXT_BYTES if kind == "export" else MAX_ARTIFACT_JSON_BYTES
