"""Selected artifact to Bulletin media publication bridge."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re

from .bulletin_readback import post_matches
from .bulletin_signed_transport import (
    configured_bulletin_base_url,
)
from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .evidence_public import TransportError
from .gateway_operation import (
    CREDENTIAL_REF_PATTERN,
    REQUEST_SCHEMA as GATEWAY_SCHEMA,
    thaw_operation,
)
from .operation_grants import GRANT_REF_PATTERN
from .private_artifact_fs import ArtifactIdentity, open_artifact_root

REQUEST_SCHEMA = "flywheel.outcome-bulletin-media-request/v1"
SELECTION_SCHEMA = "flywheel.outcome-bulletin-media-selection/v1"
PREVIEW_SCHEMA = "flywheel.outcome-bulletin-media-preview/v1"
PRIVATE_PACKET_SCHEMA = "flywheel.outcome-bulletin-media-private-packet/v1"
REVIEW_SCHEMA = "flywheel.bulletin-media-review/v1"
PUBLICATION_SCHEMA = "flywheel.outcome-bulletin-publication/v1"
TOOL = "board_publish_media_post"
MAX_MEDIA_BYTES = 10 * 1024 * 1024
INLINE_PREVIEW_MAX_BYTES = 1_048_576
_ROOM = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_ARTIFACT = re.compile(r"artifact_[A-Za-z0-9._:-]{1,96}\Z")
_PACKET_REF = re.compile(r"data_bulletin_media_packet_[0-9a-f]{16}\Z")
_MEDIA_REF = re.compile(r"data_bulletin_media_preview_[0-9a-f]{16}\Z")


class OutcomeBulletinMediaError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


from .outcome_bulletin_media_core import (  # noqa: E402
    _attach_refs,
    _credential_ref,
    _fail,
    _media_selection,
    _one_text,
    _preview,
    _read_requested_media,
    _render_post,
    _room,
    _root_json,
    _strict_dict,
)
from .outcome_bulletin_media_runtime import (  # noqa: E402
    _grant_problem,
    _load_json,
    _media_metadata_matches,
    _packet_dir,
    _preview_from_authorized,
    _private_text,
    _publication,
    _read_packet,
    _read_row_bytes,
    _same_media,
    _validate_preview,
    _write_packet,
)
from .outcome_bulletin_media_publish import publish_authorized_media_preview


def build_media_preview(
        request: dict, *, state_root: Path | None = None,
        owner_ref: str | None = None, allow_loopback: bool = False) -> dict:
    """Build and optionally persist a private packet for selected media bytes."""
    req = _strict_dict(request)
    if req.get("schema") != REQUEST_SCHEMA or set(req) != {
            "schema", "mode", "post", "media", "artifact_root", "destination"}:
        _fail()
    base = configured_bulletin_base_url(
        _private_text(req["destination"].get("base_url"), 300),
        allow_loopback=allow_loopback)
    post_body = _render_post(req["mode"], req["post"])
    private, public_rows = _read_requested_media(req)
    post = {"room": _room(req["post"].get("room", "findings")),
            "body": post_body,
            "attachments": [{"media_id": row["expected_media_id"],
                             "alt": row["alt"]} for row in public_rows]}
    packet_core = {"root": req["artifact_root"], "destination": {"base_url": base},
                   "post": post, "private_media": private,
                   "public_media": public_rows}
    packet_sha = canonical_sha256(packet_core)
    packet_ref = f"data_bulletin_media_packet_{packet_sha[:16]}"
    public_rows, private = _attach_refs(public_rows, private, packet_sha)
    preview = _preview(req["mode"], base, post, public_rows, packet_ref,
                       packet_sha)
    if state_root is not None:
        _write_packet(Path(state_root), packet_ref, {
            "schema": PRIVATE_PACKET_SCHEMA, "packet_ref": packet_ref,
            "packet_sha256": packet_sha, **packet_core,
            "private_media": private, "public_media": public_rows},
            owner_ref=owner_ref)
    return preview


def build_media_preview_from_run_selection(
        request: dict, *, state_root: Path, run_root: Path,
        owner_ref: str | None = None, allow_loopback: bool = False) -> dict:
    """Resolve selected artifact IDs from the configured run store."""
    from .outcome_bulletin_media_selection import resolve_selected_media
    req = _strict_dict(request)
    if req.get("schema") != SELECTION_SCHEMA:
        _fail()
    artifact_root = Path(run_root) / "artifacts"
    return build_media_preview({
        "schema": REQUEST_SCHEMA, "mode": "artifact_share",
        "post": req["post"],
        "media": resolve_selected_media(req, run_root=Path(run_root)),
        "artifact_root": {"path": str(artifact_root),
                          "identity": _root_json(artifact_root)},
        "destination": req["destination"]}, state_root=state_root,
        owner_ref=owner_ref, allow_loopback=allow_loopback)


def build_gateway_media_grant_request(
        preview: dict, *, journey_ref: str, expected_event_head: str,
        client_request_id: str, timeout: int = 20,
        credential_ref: str | None = None) -> dict:
    preview = _validate_preview(preview)
    refs = [] if credential_ref is None else [_credential_ref(credential_ref)]
    return {"schema": GATEWAY_SCHEMA, "journey_ref": journey_ref,
            "expected_event_head": expected_event_head,
            "client_request_id": client_request_id,
            "operation": {"name": "bulletin", "tool": TOOL, "args": preview,
                          "governance_tier": "T2", "timeout": timeout,
                          "data_refs": preview["data_refs"],
                          "credential_refs": refs}}


def build_gateway_media_publish_envelope(
        preview: dict, *, journey_ref: str, expected_event_head: str,
        client_request_id: str, grant_ref: str, timeout: int = 20,
        credential_ref: str | None = None) -> dict:
    if type(grant_ref) is not str or GRANT_REF_PATTERN.fullmatch(grant_ref) is None:
        _fail()
    req = build_gateway_media_grant_request(
        preview, journey_ref=journey_ref, expected_event_head=expected_event_head,
        client_request_id=client_request_id, timeout=timeout,
        credential_ref=credential_ref)
    return {"schema": GATEWAY_SCHEMA, "journey_ref": journey_ref,
            "expected_event_head": expected_event_head,
            "client_request_id": client_request_id, "grant_ref": grant_ref,
            **req["operation"]}


def validate_media_authorized_operation(
        authorized, *, state_root: Path, require_config: bool = False,
        owner_ref: str | None = None) -> dict:
    preview = _preview_from_authorized(authorized)
    if tuple(getattr(authorized, "data_refs", ())) != tuple(preview["data_refs"]):
        _fail()
    _read_packet(Path(state_root), preview, with_bytes=False,
                 owner_ref=owner_ref or getattr(authorized, "owner_ref", None))
    if require_config:
        configured = configured_bulletin_base_url(
            None, allow_loopback=os.environ.get(
                "FLYWHEEL_BULLETIN_ALLOW_LOOPBACK") == "1")
        if configured != preview["destination"]["base_url"]:
            _fail()
    return preview


def proposal_review(operation) -> dict | None:
    op = thaw_operation(getattr(operation, "operation", {}))
    if (getattr(operation, "action", None) != "lane.call"
            or op.get("name") != "bulletin" or op.get("tool") != TOOL):
        return None
    preview = _validate_preview(op.get("args"))
    review = dict(preview["review"])
    review["preview_sha256"] = preview["preview_sha256"]
    review["preview_media"] = preview["preview_media"]
    review["attachments"] = [
        {**media, "media_id": media["expected_media_id"]}
        for media in preview["media"]]
    return review


def preview_media_bytes(
        state_root: Path, preview_ref: str,
        owner_ref: str | None = None) -> tuple[bytes, dict]:
    if type(preview_ref) is not str or _MEDIA_REF.fullmatch(preview_ref) is None:
        _fail()
    root = _packet_dir(Path(state_root), owner_ref=owner_ref)
    marker = _load_json(root / f"{preview_ref}.json")
    packet = _load_json(root / f"{marker['packet_ref']}.json")
    row = next((item for item in packet["private_media"]
                if item.get("preview_ref") == preview_ref), None)
    if row is None:
        _fail()
    raw = _read_row_bytes(packet, row, MAX_MEDIA_BYTES)
    if hashlib.sha256(raw).hexdigest() != row["sha256"]:
        _fail()
    return raw, {"content-type": row["media_type"], "x-content-type-options": "nosniff",
                 "content-length": str(len(raw))}
