"""Redact secret-shaped values from an event before the context store keeps it.

Every ingest passes through here, whoever sends it: the capture hook, the
`canon.context.ingest` MCP tool, or a library caller. The message text, the
text of each extraction and interpretation, and the `ref`, `locator` and
`caption` of each attachment and source are scrubbed; a `canon_event_ref`
source keeps its `ref`, which names a record. An event whose values had any
hits carries `coverage.redactions`, the count per rule and never a value.
Text the capture hook already scrubbed has no hits left, so its bytes, and a
redelivery of it, are unchanged. A secret with no recognisable shape passes
through.
"""
from __future__ import annotations

import copy

from .workspace.scrub import merge_hits, scrub

_TEXT_ROWS = ("extractions", "interpretations")
_REF_ROWS = ("attachments", "sources")
_REF_FIELDS = ("ref", "locator", "caption")
_EVENT_REF = "canon_event_ref"


def redact_payload(payload):
    """A copy of an ingest payload with its event's text redacted. Anything
    that is not the shape ingest accepts is returned unchanged, for the
    store's own validation to refuse."""
    event = payload.get("event") if isinstance(payload, dict) else None
    if not isinstance(event, dict):
        return payload
    event = copy.deepcopy(event)
    hits: dict[str, int] = {}
    if "message_text" in event:
        event["message_text"] = _clean(event["message_text"], hits)
    for group in _TEXT_ROWS:
        for row in _rows(event, group):
            if "text" in row:
                row["text"] = _clean(row["text"], hits)
    for group in _REF_ROWS:
        for row in _rows(event, group):
            for name in _REF_FIELDS:
                if name in row and not (name == "ref" and row.get("source_kind") == _EVENT_REF):
                    row[name] = _clean(row[name], hits)
    if hits:
        _record_hits(event, hits)
    return {**payload, "event": event}


def _clean(value, hits: dict[str, int]):
    if not isinstance(value, str):
        return value
    result = scrub(value)
    merge_hits(hits, result.hits)
    return result.text


def _rows(event: dict, group: str) -> list[dict]:
    rows = event.get(group)
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _record_hits(event: dict, hits: dict[str, int]) -> None:
    coverage = event.get("coverage")
    if coverage is None:
        coverage = event["coverage"] = {}
    if not isinstance(coverage, dict):
        return
    earlier = coverage.get("redactions")
    counted = dict(earlier) if isinstance(earlier, dict) else {}
    merge_hits(counted, hits)
    coverage["redactions"] = dict(sorted(counted.items()))
