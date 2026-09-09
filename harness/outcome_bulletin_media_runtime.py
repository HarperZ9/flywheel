"""Stored packet and grant checks for Bulletin media publication."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import uuid4

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .evidence_public import public_result
from .gateway_operation import thaw_operation
from .journey_lock import fsync_directory
from .operation_grants import _validate_owner_ref
from .outcome_bulletin_media_core import (
    MAX_MEDIA_BYTES,
    PACKET_REF_PATTERN,
    MEDIA_REF_PATTERN,
    PREVIEW_SCHEMA,
    PRIVATE_PACKET_SCHEMA,
    PUBLICATION_SCHEMA,
    TOOL,
    _fail,
    _private_text,
    _read_row_bytes as _read_bytes_for_row,
    _same_media as _same_media_value,
    _strict_dict,
)


def _packet_dir(state_root: Path, owner_ref: str | None = None) -> Path:
    root = Path(state_root) / "bulletin-media-previews"
    if owner_ref is None:
        return root
    _validate_owner_ref(owner_ref)
    return root / owner_ref


def _load_json(path: Path) -> dict:
    try:
        value = strict_load_json(path.read_bytes(), max_bytes=1_048_576,
                                 max_depth=32)
    except Exception as exc:
        _fail()
    if type(value) is not dict:
        _fail()
    return value


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with tmp.open("xb") as stream:
            stream.write(canonical_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        fsync_directory(path.parent)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _write_packet(
        state_root: Path, packet_ref: str, packet: dict,
        owner_ref: str | None = None) -> None:
    if PACKET_REF_PATTERN.fullmatch(packet_ref) is None:
        _fail()
    root = _packet_dir(state_root, owner_ref=owner_ref)
    _atomic_json(root / f"{packet_ref}.json", packet)
    for row in packet["private_media"]:
        ref = row["preview_ref"]
        if MEDIA_REF_PATTERN.fullmatch(ref) is None:
            _fail()
        _atomic_json(root / f"{ref}.json", {
            "schema": "flywheel.outcome-bulletin-media-ref/v1",
            "preview_ref": ref, "packet_ref": packet_ref,
            "packet_sha256": packet["packet_sha256"],
            "sha256": row["sha256"]})


def _validate_preview(value: object) -> dict:
    preview = _strict_dict(value)
    if preview.get("schema") != PREVIEW_SCHEMA:
        _fail()
    expected = canonical_sha256({
        key: item for key, item in preview.items() if key != "preview_sha256"})
    if preview.get("preview_sha256") != expected:
        _fail()
    if preview.get("packet_ref") != preview.get("preview_ref"):
        _fail()
    refs = preview.get("data_refs")
    if (type(refs) is not list or not refs
            or refs[0] != preview["packet_ref"]
            or PACKET_REF_PATTERN.fullmatch(refs[0]) is None):
        _fail()
    media_refs = [row.get("preview_ref") for row in preview.get("media", [])]
    if refs[1:] != media_refs or any(
            type(ref) is not str or MEDIA_REF_PATTERN.fullmatch(ref) is None
            for ref in media_refs):
        _fail()
    return preview


def _preview_from_authorized(authorized) -> dict:
    op = thaw_operation(getattr(authorized, "operation", {}))
    if (getattr(authorized, "action", None) != "lane.call"
            or getattr(authorized, "tool", None) != TOOL
            or dict(getattr(authorized, "destination", {})) != {
                "kind": "lane", "ref": "bulletin"}
            or op.get("name") != "bulletin" or op.get("tool") != TOOL):
        _fail()
    return _validate_preview(op.get("args"))


def _read_packet(
        state_root: Path, preview: dict, *, with_bytes: bool,
        owner_ref: str | None = None) -> dict:
    preview = _validate_preview(preview)
    packet = _load_json(
        _packet_dir(state_root, owner_ref=owner_ref) / f"{preview['packet_ref']}.json")
    if (packet.get("schema") != PRIVATE_PACKET_SCHEMA
            or packet.get("packet_ref") != preview["packet_ref"]
            or packet.get("packet_sha256") != preview["review"]["packet_sha256"]
            or packet.get("destination") != {"base_url": preview["destination"]["base_url"]}
            or packet.get("post") != preview["post"]
            or packet.get("public_media") != preview["media"]):
        _fail()
    raw_rows = []
    for private, public in zip(packet["private_media"], preview["media"]):
        raw = _read_row_bytes(packet, private, MAX_MEDIA_BYTES)
        if _same_public(private, public, raw) is False:
            _fail()
        raw_rows.append(raw)
    if len(raw_rows) != len(preview["media"]):
        _fail()
    return {**packet, "bytes": raw_rows} if with_bytes else packet


def _read_row_bytes(packet: dict, row: dict, max_bytes: int) -> bytes:
    return _read_bytes_for_row(packet, row, max_bytes)


def _same_public(private: dict, public: dict, raw: bytes) -> bool:
    return (all(private.get(k) == public.get(k) for k in (
        "artifact_id", "label", "alt", "sha256", "bytes",
        "expected_media_id", "media_type", "kind", "preview_ref"))
        and len(raw) == public["bytes"]
        and hashlib.sha256(raw).hexdigest() == public["sha256"])


def _grant_problem(authorized, preview: dict) -> str | None:
    try:
        preview = _validate_preview(preview)
        op = thaw_operation(getattr(authorized, "operation", {}))
        if _preview_from_authorized(authorized) != preview:
            return "grant_binding_mismatch"
        if tuple(op.get("data_refs", ())) != tuple(preview["data_refs"]):
            return "grant_binding_mismatch"
        refs = getattr(authorized, "credential_refs", ())
        if len(refs) != 1:
            return "publish_unavailable"
        if tuple(op.get("credential_refs", ())) != tuple(refs):
            return "grant_binding_mismatch"
        return None
    except Exception:
        return "grant_binding_mismatch"


def _publication(status: str, preview: dict, **extra) -> dict:
    body = {"schema": PUBLICATION_SCHEMA, "status": status,
            "post_payload_sha256": preview.get("review", {}).get(
                "post_payload_sha256", ""),
            **extra}
    return public_result("outcome-bulletin-publication", body)


def _same_media(value: object, row: dict) -> bool:
    if type(value) is not dict:
        return False
    return _same_media_value(value, row)


def _media_metadata_matches(post: object, preview: dict) -> bool:
    if type(post) is not dict or type(post.get("attachments")) is not list:
        return False
    for returned, row in zip(post["attachments"], preview["media"]):
        if (returned.get("media_id") != row["expected_media_id"]
                or returned.get("alt") != row["alt"]
                or returned.get("kind") != row["kind"]
                or returned.get("bytes") != row["bytes"]):
            return False
        media_type = returned.get("type", returned.get("media_type"))
        if media_type != row["media_type"]:
            return False
        url = returned.get("url")
        parsed = urlsplit(url) if type(url) is str else None
        expected_path = f"/v1/media/{quote(row['expected_media_id'], safe='')}"
        if (parsed is None or parsed.scheme or parsed.netloc
                or parsed.path != expected_path or parsed.query or parsed.fragment):
            return False
    return len(post["attachments"]) == len(preview["media"])
