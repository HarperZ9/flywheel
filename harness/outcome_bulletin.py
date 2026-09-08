"""Public-safe projection from an owner-selected outcome to Bulletin."""
from __future__ import annotations

import re
from typing import Callable

from .bulletin_readback import post_matches
from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .evidence_public import TransportError, public_result
from .gateway_operation import (
    CREDENTIAL_REF_PATTERN, REQUEST_SCHEMA, canonicalize_operation,
)
from .operation_grants import GRANT_REF_PATTERN
REQUEST_INPUT_SCHEMA = "flywheel.outcome-bulletin-request/v1"
PREVIEW_SCHEMA = "flywheel.outcome-bulletin-preview/v1"
PUBLICATION_SCHEMA = "flywheel.outcome-bulletin-publication/v1"

_ALLOWED_FIELDS = frozenset((
    "schema", "title", "status", "room", "checked", "positive_controls",
    "held_blockers", "next_actions", "does_not_prove", "links",
    "attachments",
))
_TEXT_LISTS = ("checked", "positive_controls", "held_blockers",
               "next_actions", "does_not_prove")
_PRIVATE_FIELDS = frozenset((
    "owner_ref", "journey_ref", "expected_event_head", "event_head_sha256",
    "grant_ref", "proposal_ref", "operation_ref", "source_path",
    "local_path", "scratch_path", "raw_transcript", "transcript",
    "private_notes",
))
_PRIVATE_HANDLE = re.compile(r"\b(?:owner|jrn|gnt|prp|op|cred)_[0-9a-f]{32}\b")
_ROOM = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_PUBLIC_PREFIXES = (
    "https://github.com/HarperZ9/",
    "https://pypi.org/project/",
    "https://bulletin.zaindharper.workers.dev/",
    "https://harperz9.github.io/",
)

class OutcomeBulletinError(RuntimeError):
    """One fixed non-echoing refusal for unsafe public projection input."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _fail() -> None:
    raise OutcomeBulletinError(
        "UNSAFE_PUBLIC_OUTCOME",
        "outcome contains fields or content that cannot be projected publicly",
    )


def _check_no_private(value: object) -> None:
    if type(value) is dict:
        if any(key in _PRIVATE_FIELDS for key in value):
            _fail()
        for key, item in value.items():
            _check_no_private(key)
            _check_no_private(item)
    elif type(value) is list:
        for item in value:
            _check_no_private(item)
    elif type(value) is str and _PRIVATE_HANDLE.search(value):
        _fail()


def _text(value: object) -> str:
    if type(value) is not str or not value.strip():
        _fail()
    if len(value.encode("utf-8", "surrogateescape")) > 800:
        _fail()
    return value.strip()


def _text_list(value: object) -> list[str]:
    if type(value) is not list or not value or len(value) > 12:
        _fail()
    return [_text(item) for item in value]


def _links(value: object) -> list[dict[str, str]]:
    if type(value) is not list or not value or len(value) > 8:
        _fail()
    rows = []
    seen = set()
    for item in value:
        if type(item) is not dict or set(item) != {"label", "url"}:
            _fail()
        label, url = _text(item["label"]), _text(item["url"])
        if not url.startswith(_PUBLIC_PREFIXES) or url in seen:
            _fail()
        seen.add(url)
        rows.append({"label": label, "url": url})
    return rows


def _attachments(value: object) -> list[dict[str, str]]:
    if value is None:
        return []
    if type(value) is not list or len(value) > 2:
        _fail()
    rows = []
    for item in value:
        if type(item) is not dict or set(item) != {"media_id", "alt"}:
            _fail()
        media, alt = _text(item["media_id"]), _text(item["alt"])
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,96}", media):
            _fail()
        rows.append({"media_id": media, "alt": alt})
    return rows


def _normalize(outcome: dict) -> dict:
    if type(outcome) is not dict or set(outcome) - _ALLOWED_FIELDS:
        _fail()
    if outcome.get("schema") != REQUEST_INPUT_SCHEMA:
        _fail()
    _check_no_private(outcome)
    room = _text(outcome.get("room", "findings"))
    if _ROOM.fullmatch(room) is None:
        _fail()
    normalized = {
        "title": _text(outcome.get("title")),
        "status": _text(outcome.get("status")),
        "room": room,
        "links": _links(outcome.get("links")),
        "attachments": _attachments(outcome.get("attachments")),
    }
    for name in _TEXT_LISTS:
        if name in outcome:
            normalized[name] = _text_list(outcome[name])
    if "does_not_prove" not in normalized:
        _fail()
    try:
        public_result("outcome-bulletin-input", normalized)
    except TransportError:
        _fail()
    return normalized


def _section(title: str, rows: list[str]) -> list[str]:
    if not rows:
        return []
    return ["", f"{title}:"] + [f"- {row}" for row in rows]


def _render(outcome: dict) -> str:
    lines = [outcome["title"], "", f"Status: {outcome['status']}"]
    lines += _section("Checked", outcome.get("checked", []))
    lines += _section("Positive controls", outcome.get("positive_controls", []))
    lines += _section("Held blockers", outcome.get("held_blockers", []))
    lines += _section("Next actions", outcome.get("next_actions", []))
    lines += _section("Does not prove", outcome["does_not_prove"])
    lines += ["", "Links:"]
    lines += [f"- {row['label']}: {row['url']}" for row in outcome["links"]]
    return "\n".join(lines)


def build_preview(outcome: dict) -> dict:
    """Render a deterministic public Bulletin post preview from public input."""
    normalized = _normalize(outcome)
    body = _render(normalized)
    post = {"room": normalized["room"], "body": body}
    if normalized["attachments"]:
        post["attachments"] = normalized["attachments"]
    preview = {
        "schema": PREVIEW_SCHEMA,
        "target": {
            "lane": "bulletin",
            "tool": "board_write_post",
            "governance_tier": "T2",
        },
        "post": post,
        "body_bytes": len(body.encode("utf-8", "surrogateescape")),
        "body_sha256": canonical_sha256(body),
        "post_payload_sha256": canonical_sha256(post),
        "privacy": {
            "private_journey_fields": "excluded",
            "public_guard": "harness.evidence_public.public_result",
            "url_allowlist": list(_PUBLIC_PREFIXES),
        },
    }
    return strict_load_json(canonical_bytes(preview), max_bytes=1_048_576, max_depth=32)


def build_gateway_grant_request(
        preview: dict, *, journey_ref: str, expected_event_head: str,
        client_request_id: str, timeout: int = 20,
        credential_ref: str | None = None) -> dict:
    """Prepare the exact existing gateway `lane.call` operation for approval."""
    if type(preview) is not dict or preview.get("schema") != PREVIEW_SCHEMA:
        _fail()
    if (credential_ref is not None
            and CREDENTIAL_REF_PATTERN.fullmatch(credential_ref) is None):
        _fail()
    operation = {
        "name": "bulletin",
        "tool": "board_write_post",
        "args": preview["post"],
        "governance_tier": "T2",
        "timeout": timeout,
        "data_refs": [],
        "credential_refs": [] if credential_ref is None else [credential_ref],
    }
    canonical = canonicalize_operation("lane.call", operation)
    request = {
        "schema": REQUEST_SCHEMA,
        "journey_ref": journey_ref,
        "expected_event_head": expected_event_head,
        "client_request_id": client_request_id,
        "operation": operation,
    }
    if not canonical.operation_sha256 or not canonical.arguments_sha256:
        _fail()
    return request


def build_gateway_publish_envelope(
        preview: dict, *, journey_ref: str, expected_event_head: str,
        client_request_id: str, grant_ref: str, timeout: int = 20,
        credential_ref: str | None = None) -> dict:
    """Build the final gateway authorization envelope after grant approval."""
    if type(grant_ref) is not str or GRANT_REF_PATTERN.fullmatch(grant_ref) is None:
        _fail()
    request = build_gateway_grant_request(
        preview,
        journey_ref=journey_ref,
        expected_event_head=expected_event_head,
        client_request_id=client_request_id,
        timeout=timeout,
        credential_ref=credential_ref,
    )
    return {
        "schema": REQUEST_SCHEMA,
        "journey_ref": request["journey_ref"],
        "expected_event_head": request["expected_event_head"],
        "client_request_id": request["client_request_id"],
        "grant_ref": grant_ref,
        **request["operation"],
    }


def _safe_publication(status: str, preview: dict, **extra) -> dict:
    body = {
        "schema": PUBLICATION_SCHEMA,
        "status": status,
        "post_payload_sha256": preview.get("post_payload_sha256", ""),
        **extra,
    }
    return public_result("outcome-bulletin-publication", body)


def _post_id(value: object) -> str | None:
    post = value.get("post") if type(value) is dict else None
    post_id = post.get("id") if type(post) is dict else None
    return post_id if type(post_id) is str and post_id.strip() else None


def publish_preview(
        preview: dict, *, grant_ref: str,
        publisher: Callable[..., dict] | None = None,
        readback: Callable[[str], dict] | None = None,
        timeout: int = 20) -> dict:
    """Publish through the existing Bulletin lane caller and verify readback.
    Tests pass fake callbacks. Live callers must pass a signed Bulletin
    publisher after a matching gateway grant has been reviewed and approved.
    """
    if type(preview) is not dict or preview.get("schema") != PREVIEW_SCHEMA:
        _fail()
    if type(grant_ref) is not str or GRANT_REF_PATTERN.fullmatch(grant_ref) is None:
        _fail()
    if publisher is None:
        return _safe_publication(
            "publish_unavailable", preview,
            does_not_prove=["a signed Bulletin write was attempted"],
        )
    result = publisher(
        "bulletin", "board_write_post", preview["post"], timeout=timeout,
        governance_tier="T2")
    post_id = _post_id(result)
    if not post_id or type(result) is not dict or result.get("ok") is not True:
        return _safe_publication(
            "publish_failed", preview,
            error="Bulletin write did not return an accepted post id",
        )
    if readback is None:
        return _safe_publication(
            "posted_readback_unchecked", preview, post_id=post_id,
            does_not_prove=["public board readback matched the requested post"],
        )
    seen = readback(post_id)
    post = seen.get("post") if type(seen) is dict else None
    if post_matches(post, preview["post"]):
        return _safe_publication("posted_readback_match", preview, post_id=post_id)
    return _safe_publication(
        "posted_readback_drift", preview, post_id=post_id,
        does_not_prove=["public board readback matched the requested post"],
    )
