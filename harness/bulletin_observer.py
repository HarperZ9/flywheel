"""Bounded independent reads of Bulletin's public persisted records."""
from __future__ import annotations

from datetime import datetime, timezone
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from .bulletin_signed_transport import (
    BulletinSignedTransportError, bulletin_request, configured_bulletin_base_url,
)
from .bulletin_task_contract import validate_contract
from .evidence_json import canonical_sha256, strict_load_json

_POST_FIELDS = ("id", "author", "room", "parent_id", "body")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _project(post: object) -> dict:
    if (type(post) is not dict
            or any(type(post.get(k)) is not str for k in _POST_FIELDS if k != "parent_id")
            or "parent_id" not in post
            or (post["parent_id"] is not None and type(post["parent_id"]) is not str)):
        raise ValueError("malformed post")
    return {key: post[key] for key in _POST_FIELDS}


class _Reader:
    def __init__(self, base: str, contract: dict):
        self.base, self.contract = base, contract
        self.opener = build_opener(ProxyHandler({}), _NoRedirect())
        self.count = 0
        self.deadline = time.monotonic() + 60

    def get(self, path: str) -> dict:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("acquisition deadline")
        self.count += 1
        request = bulletin_request(self.base + path, method="GET",
                                   headers={"Cache-Control": "no-cache"})
        with self.opener.open(request, timeout=min(
                self.contract["request_timeout_seconds"], remaining)) as response:
            limit = self.contract["max_response_bytes"]
            chunks, total = [], 0
            while True:
                if time.monotonic() > self.deadline:
                    raise ValueError("acquisition deadline")
                chunk = response.read1(min(8192, limit + 1 - total))
                total += len(chunk)
                if total > limit:
                    raise ValueError("response exceeds limit")
                if not chunk:
                    break
                chunks.append(chunk)
        doc = strict_load_json(b"".join(chunks), max_bytes=limit, max_depth=20)
        if type(doc) is not dict or doc.get("ok") is not True:
            raise ValueError("invalid board response")
        return doc


def _scan(reader: _Reader, contract: dict) -> tuple[list[dict], list[str]]:
    posts, cursors, identities = [], set(), set()
    cursor = None
    for _ in range(contract["max_pages"]):
        query = {"room": contract["room"], "limit": contract["page_size"]}
        if cursor is not None:
            query["before"] = cursor
        doc = reader.get("/v1/feed?" + urlencode(query))
        page = doc.get("posts")
        if type(page) is not list or len(page) > contract["page_size"]:
            raise ValueError("invalid feed page")
        for raw in page:
            post = _project(raw)
            if post["id"] in identities or post["room"] != contract["room"]:
                return posts, ["pagination_invalid"]
            identities.add(post["id"])
            posts.append(post)
        if "next_before" not in doc:
            return posts, ["pagination_metadata_missing"]
        cursor = doc["next_before"]
        if cursor is None:
            return posts, []
        if (type(cursor) is not str or not cursor or cursor in cursors
                or not page or cursor != page[-1]["id"]):
            return posts, ["pagination_invalid"]
        cursors.add(cursor)
    return posts, ["page_limit"]


def observe_handoff(contract: object, base_url: str, *, allow_loopback=False) -> dict:
    """Read outside actor control; no credentials, write requests or redirects.

    Same-origin HTTP evidence trusts the configured server and observer host.
    Paginated reads cannot establish a complete historic or atomic snapshot.
    """
    c = validate_contract(contract)
    try:
        base = configured_bulletin_base_url(base_url, allow_loopback=allow_loopback)
    except BulletinSignedTransportError:
        raise ValueError("invalid observer origin") from None
    reader = _Reader(base, c)
    start = datetime.now(timezone.utc).isoformat()
    begin = time.monotonic()
    source, posts, gaps = None, [], []
    try:
        source = _project(reader.get("/v1/posts/" + quote(c["source_id"], safe=""))["post"])
        posts, first_gaps = _scan(reader, c)
        again, second_gaps = _scan(reader, c)
        gaps.extend(first_gaps + second_gaps)
        if sorted(posts, key=lambda p: p["id"]) != sorted(again, key=lambda p: p["id"]):
            gaps.append("snapshot_changed")
    except (ValueError, KeyError, TypeError, OSError, HTTPError, URLError, UnicodeError):
        gaps.append("read_failed")
    return {
        "schema": "flywheel.bulletin-task-observation/v1", "source": source,
        "posts": posts, "gaps": sorted(set(gaps)),
        "acquisition": {
            "started_at": start, "ended_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(time.monotonic() - begin, 6),
            "origin_sha256": canonical_sha256(base), "request_count": reader.count,
            "method": "source_get_and_two_bounded_room_scans",
            "atomic_snapshot": False, "sse_history_complete": False,
        },
    }
