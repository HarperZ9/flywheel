"""Signed upload and post dispatcher for reviewed Bulletin media previews."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from .bulletin_media_http import read_public_bytes
from .bulletin_readback import post_matches
from .bulletin_signed_transport import (
    BulletinSignedTransportError,
    _SignedClient,
    _key_from_bindings,
    _post_id,
    _read_json,
    _resolve_key,
    configured_bulletin_base_url,
)
from .evidence_public import TransportError
from .gateway_operation import thaw_operation
from .outcome_bulletin_media_runtime import (
    _grant_problem,
    _media_metadata_matches,
    _publication,
    _read_packet,
    _same_media,
)
def publish_authorized_media_preview(
        authorized, preview: dict, *, state_root: Path,
        keychain_get: Callable[[str], str | None] | None = None,
        credential_bindings: object | None = None, timeout: int | None = None,
        allow_loopback: bool = False, now=None, nonce_bytes=None) -> dict:
    problem = _grant_problem(authorized, preview)
    if problem:
        return _publication(problem, preview, does_not_prove=["media upload ran"])
    try:
        base = configured_bulletin_base_url(
            preview["destination"]["base_url"], allow_loopback=allow_loopback)
        packet = _read_packet(Path(state_root), preview, with_bytes=True,
                              owner_ref=getattr(authorized, "owner_ref", None))
        key = _key_from_bindings(credential_bindings) if credential_bindings else (
            _resolve_key(authorized, state_root, keychain_get))
    except (BulletinSignedTransportError, TransportError):
        return _publication("publish_unavailable", preview,
                            does_not_prove=["media upload ran"])
    span = float(timeout if timeout is not None else thaw_operation(
        getattr(authorized, "operation", {})).get("timeout", 20))
    deadline = time.monotonic() + max(0.001, span)
    try:
        client = _SignedClient(base, key, timeout=_time_left(deadline),
                               now=now, nonce_bytes=nonce_bytes)
    except BulletinSignedTransportError:
        return _publication("publish_unavailable", preview,
                            does_not_prove=["media upload ran"])
    uploaded = []
    for row, raw in zip(preview["media"], packet["bytes"]):
        status = _upload_one(client, base, row, raw, deadline)
        if status.get("status") != "uploaded":
            return _publication(status["status"], preview, uploaded_media=uploaded,
                                media_id=row["expected_media_id"],
                                does_not_prove=status["does_not_prove"])
        uploaded.append(status["media"])
    try:
        client.timeout = _time_left(deadline)
        posted = client.post_json("/v1/posts", preview["post"])
    except BulletinSignedTransportError as exc:
        state = "media_uploaded_post_unverified" if exc.code == "WRITE_RESPONSE_LOST" else "media_uploaded_post_failed"
        return _publication(state, preview, uploaded_media=uploaded,
                            does_not_prove=["Bulletin accepted or rejected the post"])
    post_id = _post_id(posted)
    if not post_id or posted.get("ok") is not True:
        return _publication("media_uploaded_post_failed", preview,
                            uploaded_media=uploaded)
    try:
        seen = _read_json(f"{base}/v1/posts/{quote(post_id, safe='')}",
                          _time_left(deadline))
    except BulletinSignedTransportError:
        return _publication("posted_readback_unavailable", preview,
                            post_id=post_id, uploaded_media=uploaded)
    post = seen.get("post") if type(seen) is dict else None
    if post_matches(post, preview["post"]) and _media_metadata_matches(post, preview):
        return _publication("posted_readback_match", preview, post_id=post_id,
                            uploaded_media=uploaded)
    return _publication("posted_readback_drift", preview, post_id=post_id,
                        uploaded_media=uploaded,
                        does_not_prove=["public board readback matched media"])


def _upload_one(client, base: str, row: dict, raw: bytes, deadline: float) -> dict:
    try:
        client.timeout = _time_left(deadline)
        uploaded = client.post_bytes("/v1/media", raw)
    except BulletinSignedTransportError as exc:
        return {"status": "media_upload_unverified" if exc.code == "WRITE_RESPONSE_LOST" else "media_upload_failed",
                "does_not_prove": ["Bulletin accepted or rejected the upload"]}
    media = uploaded.get("media") if type(uploaded) is dict else None
    if not _same_media(media, row):
        return {"status": "media_upload_drift",
                "does_not_prove": ["Bulletin returned the reviewed media id"]}
    if not _public_media_bytes_match(base, row, raw, deadline):
        return {"status": "media_upload_drift",
                "does_not_prove": ["public media bytes matched upload"]}
    return {"status": "uploaded", "media": {
        "media_id": row["expected_media_id"], "sha256": row["sha256"],
        "bytes": row["bytes"], "media_type": row["media_type"],
        "kind": row["kind"]}}


def _public_media_bytes_match(base: str, row: dict, raw: bytes, deadline: float) -> bool:
    try:
        url = f"{base}/v1/media/{quote(row['expected_media_id'], safe='')}"
        code, body, headers = read_public_bytes(
            url, _time_left(deadline), max_bytes=len(raw))
        if (code != 200 or body != raw
                or headers.get("content-type", "").split(";")[0] != row["media_type"]):
            return False
        expected_len = headers.get("content-length")
        if expected_len is not None and expected_len != str(len(raw)):
            return False
        if row["kind"] in {"audio", "video"}:
            code, body, headers = read_public_bytes(
                url, _time_left(deadline), headers={"range": "bytes=0-0"},
                max_bytes=1)
            return (code == 206 and body == raw[:1]
                    and headers.get("content-range") == f"bytes 0-0/{len(raw)}")
        return True
    except BulletinSignedTransportError:
        return False


def _time_left(deadline: float) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise BulletinSignedTransportError("DEADLINE_EXCEEDED")
    return left
