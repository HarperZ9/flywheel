"""Production bridge for authorized outcome Bulletin lane writes."""
from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
import re

from .bulletin_signed_transport import publish_authorized_preview
from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .evidence_public import TransportError, error_response, public_result
from .outcome_bulletin import PREVIEW_SCHEMA, OutcomeBulletinError, _check_no_private

_ROOM = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_URL = re.compile(r"https://[^\s)>\"']+")
_PUBLIC_PREFIXES = (
    "https://github.com/HarperZ9/",
    "https://pypi.org/project/",
    "https://bulletin.zaindharper.workers.dev/",
    "https://harperz9.github.io/",
)


def dispatch_outcome_bulletin_gateway(authorized):
    """Return a gateway response for the exact Bulletin outcome lane, else None."""
    if _targets_bulletin_lane(authorized):
        denied = _bulletin_access_denial(authorized)
        if denied is not None:
            return denied, 403
    if _targets_media_bulletin(authorized):
        from .outcome_bulletin_media import publish_authorized_media_preview
        from .gateway_operation import thaw_operation
        op = thaw_operation(getattr(authorized, "operation", {}))
        plan = getattr(authorized, "execution_plan", None)
        media_state = getattr(plan, "verified_plan", {}) or {}
        result = publish_authorized_media_preview(
            authorized, op["args"], state_root=Path(
                media_state.get("bulletin_media_state_root", ".")),
            credential_bindings=authorized.credential_bindings,
            allow_loopback=os.environ.get("FLYWHEEL_BULLETIN_ALLOW_LOOPBACK") == "1")
        return result, 200
    if not _targets_outcome_bulletin(authorized):
        return None
    try:
        preview = preview_from_authorized_operation(authorized)
    except TransportError as exc:
        return error_response(exc)
    result = publish_authorized_preview(
        authorized, preview, state_root=Path("."),
        credential_bindings=authorized.credential_bindings,
        allow_loopback=os.environ.get("FLYWHEEL_BULLETIN_ALLOW_LOOPBACK") == "1")
    return result, 200


def _targets_bulletin_lane(authorized) -> bool:
    op = dict(getattr(authorized, "operation", {}))
    return (
        getattr(authorized, "action", None) == "lane.call"
        and op.get("name") == "bulletin")


def _bulletin_access_denial(authorized) -> dict | None:
    from .bulletin_access import authorized_bulletin_access_denial
    return authorized_bulletin_access_denial(authorized)


def preview_from_authorized_operation(authorized) -> dict:
    op = dict(getattr(authorized, "operation", {}))
    post = _post(op.get("args"))
    body = post["body"]
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
    return strict_load_json(canonical_bytes(preview), max_bytes=1_048_576,
                            max_depth=32)


def _targets_outcome_bulletin(authorized) -> bool:
    op = dict(getattr(authorized, "operation", {}))
    return (
        getattr(authorized, "action", None) == "lane.call"
        and op.get("name") == "bulletin"
        and op.get("tool") == "board_write_post")


def _targets_media_bulletin(authorized) -> bool:
    op = dict(getattr(authorized, "operation", {}))
    return (
        getattr(authorized, "action", None) == "lane.call"
        and op.get("name") == "bulletin"
        and op.get("tool") == "board_publish_media_post")


def _post(value: object) -> dict:
    if not isinstance(value, Mapping):
        raise TransportError(
            "INVALID_REQUEST", "authorized Bulletin post is invalid", 422)
    value = dict(value)
    if not {"room", "body"} <= set(value):
        raise TransportError(
            "INVALID_REQUEST", "authorized Bulletin post is invalid", 422)
    if set(value) - {"room", "body", "attachments"}:
        raise TransportError(
            "INVALID_REQUEST", "authorized Bulletin post is invalid", 422)
    room, body = value["room"], value["body"]
    if type(room) is not str or _ROOM.fullmatch(room) is None:
        raise TransportError(
            "INVALID_REQUEST", "authorized Bulletin post is invalid", 422)
    if type(body) is not str or not body.strip() or len(body.encode()) > 65_536:
        raise TransportError(
            "INVALID_REQUEST", "authorized Bulletin post is invalid", 422)
    guarded_body = _guard_urls(body)
    post = {"room": room, "body": body}
    attachments = _attachments(value.get("attachments"))
    if attachments:
        post["attachments"] = attachments
    try:
        _check_no_private(post)
        public_result("outcome-bulletin-authorized-post",
                      {"room": room, "body": guarded_body,
                       "attachments": [{**row, "alt": _guard_urls(row["alt"])}
                                       for row in attachments]})
    except (TransportError, OutcomeBulletinError) as exc:
        raise TransportError(
            "UNSAFE_PUBLIC_OUTCOME",
            "authorized Bulletin post is not public-safe", 422) from exc
    return post


def _attachments(value: object) -> list[dict[str, str]]:
    if value is None:
        return []
    if type(value) not in (list, tuple) or len(value) > 2:
        raise TransportError("INVALID_REQUEST",
                             "authorized Bulletin post is invalid", 422)
    rows = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"media_id", "alt"}:
            raise TransportError(
                "INVALID_REQUEST", "authorized Bulletin post is invalid", 422)
        media, alt = item["media_id"], item["alt"]
        if (type(media) is not str or type(alt) is not str
                or not re.fullmatch(r"[A-Za-z0-9_-]{32,96}", media)
                or not alt.strip() or len(alt.encode()) > 800):
            raise TransportError(
                "INVALID_REQUEST", "authorized Bulletin post is invalid", 422)
        rows.append({"media_id": media, "alt": alt.strip()})
    return rows


def _guard_urls(body: str) -> str:
    def replace(match) -> str:
        value = match.group(0)
        url = value.rstrip(".,;:")
        suffix = value[len(url):]
        if any(url.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
            return "PUBLIC_URL" + suffix
        raise TransportError(
            "UNSAFE_PUBLIC_OUTCOME",
            "authorized Bulletin post is not public-safe", 422)
    return _URL.sub(replace, body)
