"""Validation and custody helpers for Bulletin media publication."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import uuid4

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .evidence_public import TransportError, public_metadata, public_result
from .gateway_operation import CREDENTIAL_REF_PATTERN, _relative_path, thaw_operation
from .journey_lock import fsync_directory
from .outcome_bulletin import _PUBLIC_PREFIXES, _check_no_private
from .private_artifact_fs import ArtifactIdentity, open_artifact_root, root_identity

REQUEST_SCHEMA = "flywheel.outcome-bulletin-media-request/v1"
PREVIEW_SCHEMA = "flywheel.outcome-bulletin-media-preview/v1"
PRIVATE_PACKET_SCHEMA = "flywheel.outcome-bulletin-media-private-packet/v1"
REVIEW_SCHEMA = "flywheel.bulletin-media-review/v1"
PUBLICATION_SCHEMA = "flywheel.outcome-bulletin-publication/v1"
TOOL = "board_publish_media_post"
MAX_MEDIA_BYTES = 10 * 1024 * 1024
INLINE_PREVIEW_MAX_BYTES = 1_048_576
_ROOM = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_URL = re.compile(r"https://[^\s)>\"']+")
_ARTIFACT = re.compile(r"artifact_[A-Za-z0-9._:-]{1,96}\Z")
_PACKET_REF = re.compile(r"data_bulletin_media_packet_[0-9a-f]{16}\Z")
_MEDIA_REF = re.compile(r"data_bulletin_media_preview_[0-9a-f]{16}\Z")


def _fail() -> None:
    raise TransportError("INVALID_BULLETIN_MEDIA", "Bulletin media request is invalid", 422)


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _strict_dict(value: object) -> dict:
    try:
        if not isinstance(value, dict):
            value = thaw_operation(value)
        return strict_load_json(canonical_bytes(value), max_depth=32)
    except Exception as exc:
        raise TransportError("INVALID_BULLETIN_MEDIA",
                             "Bulletin media request is invalid", 422) from exc


def _one_text(value: object, limit: int = 800) -> str:
    if type(value) is not str or not value.strip() or len(value.encode()) > limit:
        _fail()
    text = value.strip()
    try:
        _check_no_private(text)
        public_metadata(_guard_public_urls(text))
    except Exception as exc:
        raise TransportError("INVALID_BULLETIN_MEDIA",
                             "Bulletin media request is invalid", 422) from exc
    return text


def _room(value: object) -> str:
    room = _one_text(value, 64)
    if _ROOM.fullmatch(room) is None:
        _fail()
    return room


def _credential_ref(value: str) -> str:
    if type(value) is not str or CREDENTIAL_REF_PATTERN.fullmatch(value) is None:
        _fail()
    return value


def _guard_public_urls(text: str) -> str:
    def replace(match) -> str:
        value = match.group(0)
        url = value.rstrip(".,;:")
        suffix = value[len(url):]
        if any(url.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
            return "PUBLIC_URL" + suffix
        _fail()
    return _URL.sub(replace, text)


def _public_links(value: object) -> list[dict[str, str]]:
    if value is None:
        return []
    if type(value) is not list or len(value) > 8:
        _fail()
    rows, seen = [], set()
    for item in value:
        if type(item) is not dict or set(item) != {"label", "url"}:
            _fail()
        label, url = _one_text(item["label"], 120), _one_text(item["url"], 300)
        if not any(url.startswith(prefix) for prefix in _PUBLIC_PREFIXES) or url in seen:
            _fail()
        seen.add(url)
        rows.append({"label": label, "url": url})
    return rows


def _render_post(mode: object, post: object) -> str:
    if mode != "artifact_share" or type(post) is not dict:
        _fail()
    allowed = {"room", "title", "description", "source_attribution",
               "limits", "links"}
    if set(post) - allowed:
        _fail()
    title = _one_text(post.get("title"), 160)
    description = _one_text(post.get("description"), 4000)
    lines = [title, "", description]
    if post.get("source_attribution") is not None:
        lines += ["", f"Source: {_one_text(post['source_attribution'], 500)}"]
    limits = _text_list(post.get("limits"), required=True)
    lines += ["", "Limits:"] + [f"- {row}" for row in limits]
    links = _public_links(post.get("links"))
    if links:
        lines += ["", "Links:"] + [f"- {row['label']}: {row['url']}" for row in links]
    return "\n".join(lines)


def _text_list(value: object, *, required: bool) -> list[str]:
    if value is None and not required:
        return []
    if type(value) is not list or (required and not value) or len(value) > 12:
        _fail()
    return [_one_text(item, 800) for item in value]


def _media_selection(value: object) -> list[dict[str, str]]:
    if type(value) is not list or not 1 <= len(value) <= 3:
        _fail()
    out, seen = [], set()
    for item in value:
        if type(item) is not dict or set(item) - {"artifact_id", "label",
                                                  "relative_path", "alt"}:
            _fail()
        artifact = _one_text(item.get("artifact_id"), 120)
        if _ARTIFACT.fullmatch(artifact) is None or artifact in seen:
            _fail()
        seen.add(artifact)
        out.append({"artifact_id": artifact,
                    "label": _one_text(item.get("label", artifact), 120),
                    "relative_path": item.get("relative_path", ""),
                    "alt": _one_text(item.get("alt"), 800)})
    return out


def _root_json(root: Path) -> dict:
    return root_identity(root).to_json_dict()


def _read_requested_media(req: dict) -> tuple[list[dict], list[dict]]:
    root = req["artifact_root"]
    if type(root) is not dict or set(root) != {"path", "identity"}:
        _fail()
    path = Path(_private_text(root["path"], 2048))
    identity = ArtifactIdentity.from_json_dict(root["identity"])
    private, public = [], []
    with open_artifact_root(path, expected=identity, writable=False) as fs:
        for item in _media_selection(req["media"]):
            rel = item["relative_path"]
            if type(rel) is not str or not _relative_path(rel):
                _fail()
            raw = fs.read_bytes(rel, max_bytes=MAX_MEDIA_BYTES)
            media_type, kind = _sniff(raw)
            sha = hashlib.sha256(raw).hexdigest()
            media = _b64u(hashlib.sha256(raw).digest())
            private.append({**item, "sha256": sha, "bytes": len(raw),
                            "expected_media_id": media,
                            "media_type": media_type, "kind": kind})
            public.append({k: private[-1][k] for k in (
                "artifact_id", "label", "alt", "sha256", "bytes",
                "expected_media_id", "media_type", "kind")})
    return private, public


def _private_text(value: object, limit: int) -> str:
    if type(value) is not str or not value.strip() or len(value.encode()) > limit:
        _fail()
    return value.strip()


def _sniff(raw: bytes) -> tuple[str, str]:
    if not raw:
        _fail()
    low = raw[:128].lstrip().lower()
    if low.startswith((b"<svg", b"<?xml", b"<!doctype html", b"<html", b"<script")):
        _fail()
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "image"
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg", "image"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif", "image"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "image/webp", "image"
    if len(raw) >= 12 and raw[4:8] == b"ftyp" and raw[8:12] in (b"avif", b"avis"):
        return "image/avif", "image"
    if raw.startswith(b"ID3") or (len(raw) > 1 and raw[0] == 0xFF and raw[1] & 0xE0 == 0xE0):
        return "audio/mpeg", "audio"
    if raw.startswith(b"OggS"):
        return "audio/ogg", "audio"
    if raw.startswith(b"fLaC"):
        return "audio/flac", "audio"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WAVE":
        return "audio/wav", "audio"
    if len(raw) >= 12 and raw[4:8] == b"ftyp":
        return "video/mp4", "video"
    if raw.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm", "video"
    _fail()


def _attach_refs(public_rows: list[dict], private_rows: list[dict],
                 packet_sha: str) -> tuple[list[dict], list[dict]]:
    pub, pri = [], []
    for row, private in zip(public_rows, private_rows):
        ref = "data_bulletin_media_preview_" + canonical_sha256({
            "packet": packet_sha, "media": row["expected_media_id"]})[:16]
        pub.append({**row, "preview_ref": ref})
        pri.append({**private, "preview_ref": ref})
    return pub, pri


def _preview(mode: str, base: str, post: dict, media: list[dict],
             packet_ref: str, packet_sha: str) -> dict:
    media_sha = canonical_sha256(media)
    review = {"schema": REVIEW_SCHEMA, "mode": mode,
              "destination": {"base_url": base},
              "effect": "upload these public bytes, then publish this post once",
              "post": {"room": post["room"], "body": post["body"]},
              "body_sha256": canonical_sha256(post["body"]),
              "post_payload_sha256": canonical_sha256(post),
              "media_list_sha256": media_sha,
              "packet_sha256": packet_sha,
              "does_not_prove": [
                  "semantic truth of the post body",
                  "license, authorship, malware safety, or hidden-data absence"]}
    preview = {"schema": PREVIEW_SCHEMA, "mode": mode,
               "preview_ref": packet_ref, "packet_ref": packet_ref,
               "destination": {"base_url": base,
                               "base_url_sha256": canonical_sha256(base)},
               "target": {"lane": "bulletin", "tool": TOOL,
                          "governance_tier": "T2"},
               "post": post, "media": media, "review": review,
               "preview_media": [{
                   "preview_ref": row["preview_ref"], "kind": row["kind"],
                   "media_type": row["media_type"], "bytes": row["bytes"],
                   "media_id": row["expected_media_id"]} for row in media],
               "data_refs": [packet_ref] + [row["preview_ref"] for row in media],
               "privacy": {"public_guard": "harness.evidence_public.public_result",
                           "artifact_bytes": "private until approved upload",
                           "credential_values": "never included"}}
    preview["preview_sha256"] = canonical_sha256(preview)
    return _preview_result(preview)


def _preview_result(preview: dict) -> dict:
    checked = strict_load_json(canonical_bytes(preview), max_depth=32)
    post = dict(checked["post"])
    post["body"] = _guard_public_urls(post["body"])
    checked["post"] = post
    checked["review"] = {**checked["review"], "post": {
        **checked["review"]["post"], "body": post["body"]}}
    base = preview["destination"]["base_url"]
    parsed = urlsplit(base)
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return strict_load_json(canonical_bytes(preview), max_depth=32)
    public_result("outcome-bulletin-media-preview", checked)
    return strict_load_json(canonical_bytes(preview), max_depth=32)


def _read_row_bytes(packet: dict, row: dict, max_bytes: int) -> bytes:
    root = packet.get("root")
    if type(root) is not dict or set(root) != {"path", "identity"}:
        _fail()
    identity = ArtifactIdentity.from_json_dict(root["identity"])
    with open_artifact_root(Path(root["path"]), expected=identity,
                            writable=False) as fs:
        return fs.read_bytes(row["relative_path"], max_bytes=max_bytes)


def _same_media(value: object, row: dict) -> bool:
    return (type(value) is dict and value.get("id") == row["expected_media_id"]
            and value.get("type") == row["media_type"]
            and value.get("kind") == row["kind"]
            and value.get("bytes") == row["bytes"])


PACKET_REF_PATTERN = _PACKET_REF
MEDIA_REF_PATTERN = _MEDIA_REF
