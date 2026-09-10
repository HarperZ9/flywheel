"""Compare public post content with an approved Bulletin payload."""
from __future__ import annotations


def post_matches(seen: object, expected: dict) -> bool:
    """Match content, reply destination and media references, not playback."""
    if (type(seen) is not dict or seen.get("room") != expected.get("room")
            or seen.get("body") != expected.get("body")
            or seen.get("parent_id") != expected.get("parent_id")):
        return False
    returned = seen.get("attachments", [])
    if type(returned) is not list or any(type(row) is not dict for row in returned):
        return False
    identities = [{"media_id": row.get("media_id"), "alt": row.get("alt")}
                  for row in returned]
    return identities == expected.get("attachments", [])
