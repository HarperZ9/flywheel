"""The discourse unit and the adapters that produce it from a gathered corpus.

A DiscourseItem is one comment/post/reply, normalized from any source. Engagement
(likes/upvotes) is read from the source when present; when a source genuinely has
no engagement signal, engagement is 0 and meta records the absence, so a missing
signal is never rendered as a real zero-weight vote.
"""
from __future__ import annotations

from dataclasses import dataclass

# Which gather Item kinds are discourse (as opposed to the media they respond to).
# "feed-entry" is the kind gather's feed adapter actually emits; "feed_item" is
# kept as an alias so either producer naming normalizes.
_DISCOURSE_KINDS = {"comment": "video", "feed-entry": "feed", "feed_item": "feed",
                    "post": "reddit", "reply": "reddit"}


@dataclass(frozen=True)
class DiscourseItem:
    id: str
    source: str
    responds_to: str
    parent: str | None
    author: str
    text: str
    engagement: int
    ts: float | None
    meta: dict


def _engagement(meta: dict) -> tuple[int, bool]:
    """Return (engagement, present). Absent -> (0, False); never a fabricated weight."""
    raw = meta.get("like_count", meta.get("score"))
    if raw is None:
        return 0, False
    try:
        return int(raw), True
    except (TypeError, ValueError):
        return 0, False


def normalize(rows: list[dict]) -> list[DiscourseItem]:
    """Map gather-style catalog rows into DiscourseItems. Non-discourse kinds are skipped."""
    items: list[DiscourseItem] = []
    for row in rows:
        source = _DISCOURSE_KINDS.get(row.get("kind", ""))
        if source is None:
            continue
        meta = dict(row.get("meta") or {})
        engagement, present = _engagement(meta)
        meta["engagement_present"] = present
        ts = meta.get("ts")
        items.append(DiscourseItem(
            id=str(row.get("id", "")),
            source=source,
            responds_to=str(row.get("ref", "")),
            parent=meta.get("parent"),
            author=str(meta.get("author", "")),
            text=str(row.get("text", "")),
            engagement=engagement,
            ts=float(ts) if isinstance(ts, (int, float)) else None,
            meta=meta,
        ))
    return items
