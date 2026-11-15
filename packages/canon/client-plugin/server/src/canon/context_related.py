"""Explicit one-hop source-reference sidecars for context query results."""
from __future__ import annotations

from .workspace.scrub import scrub


def related_events(records, hits, workspace, project, limit):
    events = _scoped_events(records, workspace, project)
    anchors = _anchor_event_ids(hits, events)
    relations = []
    seen = set()
    for anchor in anchors:
        _outgoing_relations(events, anchor, relations, seen, workspace, project)
        _incoming_relations(events, anchor, relations, seen, workspace, project)
    relations.sort(key=_relation_sort_key)
    return relations[:limit], {
        "related_event_expansion": "explicit_source_refs",
        "related_event_traversal": "one_hop_non_recursive",
        "related_event_scope": "same_workspace_project_only",
        "related_event_currentness": "not_inferred",
        "related_event_truth": "not_inferred",
        "related_anchor_events_considered": len(anchors),
        "related_events_considered": len(relations),
        "related_events_returned": min(limit, len(relations)),
        "related_events_omitted": max(0, len(relations) - limit),
        "related_limit": limit,
    }


def _scoped_events(records, workspace, project):
    events = {}
    for rec in records:
        data = rec.data
        event_id = data.get("event_record_id")
        if data.get("record_role") != "event" or event_id != rec.id:
            continue
        if (data.get("workspace_id"), data.get("project_id")) != (workspace, project):
            continue
        events[event_id] = rec
    return events


def _anchor_event_ids(hits, events):
    anchors = []
    seen = set()
    for row in hits:
        event_id = row.get("citation", {}).get("event_record_id")
        if event_id in events and event_id not in seen:
            anchors.append(event_id)
            seen.add(event_id)
    return anchors


def _outgoing_relations(events, anchor, relations, seen, workspace, project):
    for source in _canon_event_refs(events[anchor]):
        target = _ref_target(source)
        if target in events and target != anchor:
            _append_relation(relations, seen, events[target], anchor,
                             "outgoing_source_ref", source, workspace, project)


def _incoming_relations(events, anchor, relations, seen, workspace, project):
    for event_id, rec in events.items():
        if event_id == anchor:
            continue
        for source in _canon_event_refs(rec):
            if _ref_target(source) == anchor:
                _append_relation(relations, seen, rec, anchor,
                                 "incoming_source_ref", source, workspace, project)


def _append_relation(relations, seen, rec, anchor, direction, source, workspace, project):
    event_id = rec.data["event_record_id"]
    key = (anchor, direction, event_id)
    if key in seen:
        return
    seen.add(key)
    relations.append(_related_hit(rec, anchor, direction, source, workspace, project))


def _related_hit(rec, anchor, direction, source, workspace, project):
    return {"event_record_id": rec.data["event_record_id"],
            "workspace_id": workspace, "project_id": project,
            "anchor_event_record_id": anchor, "direction": direction,
            "source": _source_summary(source), "claim_state": rec.data.get("claim_state"),
            "citation": {"record_key": "workspace/" + rec.id,
                         "source_hash": rec.provenance.source_hash,
                         "source_app": rec.provenance.harness,
                         "native_id": rec.provenance.native_id,
                         "session_id": rec.provenance.session_id}}


def cited_event_ids(rec) -> set[str]:
    """The event record ids this record cites through canon_event_ref sources."""
    return {_ref_target(source) for source in _canon_event_refs(rec)}


def mark_purged_citations(hits, records, purged_ids) -> None:
    """Name, on each hit, the purged events that the hit's event cites. The
    citing record keeps its own text; only the cited event is gone."""
    if not purged_ids:
        return
    by_id = {rec.id: rec for rec in records}
    for hit in hits:
        cited = purged_citations(by_id.get(hit.get("record_id")), by_id, purged_ids)
        if cited:
            hit["cited_events_purged"] = cited


def purged_citations(rec, by_id, purged_ids) -> list[str]:
    if rec is None:
        return []
    event = by_id.get(rec.data.get("event_record_id"), rec)
    return sorted(cited_event_ids(event) & set(purged_ids))


def _canon_event_refs(rec):
    return [source for source in rec.data.get("sources", [])
            if isinstance(source, dict) and source.get("source_kind") == "canon_event_ref"
            and isinstance(_ref_target(source), str)]


def _ref_target(source):
    return source.get("ref") or source.get("locator")


def _source_summary(source):
    """The source a relation followed, scrubbed like any text a query returns."""
    return {key: scrub(str(source[key])).text[:4096] for key in (
        "source_id", "source_kind", "ref", "locator", "extraction_status", "source_status")
            if key in source}


def _relation_sort_key(row):
    source = row["source"]
    return (row["anchor_event_record_id"], row["direction"],
            source.get("source_id", ""), row["event_record_id"])

