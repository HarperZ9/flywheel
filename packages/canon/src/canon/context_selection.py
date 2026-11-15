"""What a purge selects: one event, an ordinal cut-off, or every event.

A selection resolves against a `ScopeView`, the events of one workspace and
project with their derived records and the answers paired with each of them.
With `keep_responses`, the bulk selectors (`before_ord` and `all`) leave out
every answer, meaning every event with `message_role: "assistant"`, whether
its prompt is selected, was purged earlier, was never captured or is not named
at all (D-165). An answer named by its own event id is purged as named.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .context_audit import StoreState

REASON_OWNER = "owner_request"
_ONE_SELECTOR = "choose exactly one of event_id, before_ord or all"
NOT_FOUND = "event_id is not a captured event in this workspace and project"


class ContextPurgeError(ValueError):
    """A purge selection, policy or confirmation that cannot be applied."""


class ContextPurgeNotFound(ContextPurgeError):
    """The selected event is not a captured event in this workspace and project."""


@dataclass(frozen=True)
class Target:
    event_id: str
    mode: str  # "event": the event and its closure; "derived": its derived records only
    reason_code: str


@dataclass(frozen=True)
class ScopeView:
    state: StoreState
    events: dict
    derived: dict
    answers: dict


@dataclass(frozen=True)
class Selection:
    description: dict
    keep_responses: bool
    resolve: Callable[[ScopeView], list[Target]] = field(compare=False, repr=False)


def select(*, event_id=None, before_ord=None, all_events=False, keep_responses=False) -> Selection:
    """Exactly one of an event record id, an ordinal cut-off, or every event."""
    if type(keep_responses) is not bool:
        raise ContextPurgeError("keep_responses must be true or false")
    if type(all_events) is not bool or [event_id is not None, before_ord is not None,
                                        all_events].count(True) != 1:
        raise ContextPurgeError(_ONE_SELECTOR)
    if event_id is not None:
        if not isinstance(event_id, str) or not event_id:
            raise ContextPurgeError(NOT_FOUND)
        return Selection({"event_id": event_id}, keep_responses,
                         lambda view: [Target(event_id, "event", REASON_OWNER)])
    if before_ord is not None:
        if type(before_ord) is not int or before_ord < 1:
            raise ContextPurgeError("before_ord must be a whole number of 1 or more")
        return Selection({"before_ord": before_ord}, keep_responses, lambda view: _bulk(
            view, [eid for eid, row in view.events.items() if row.ordinal < before_ord],
            keep_responses))
    return Selection({"all": True}, keep_responses,
                     lambda view: _bulk(view, list(view.events), keep_responses))


def _bulk(view: ScopeView, ids: list[str], keep_responses: bool) -> list[Target]:
    chosen = set(ids)
    if keep_responses:
        chosen = {eid for eid in chosen if not _is_answer(view, eid)}
    return [Target(eid, "event", REASON_OWNER) for eid in sorted(chosen)]


def _is_answer(view: ScopeView, event_id: str) -> bool:
    return view.events[event_id].record.data.get("message_role") == "assistant"


def scope_view(state: StoreState, workspace: str, project: str) -> ScopeView:
    """The events of one workspace and project, their derived records, and the
    assistant events that answer each of them."""
    events, derived, answers = {}, {}, {}
    for key, row in state.live.items():
        data = row.record.data
        parent = data.get("event_record_id")
        if (data.get("workspace_id"), data.get("project_id")) != (workspace, project) \
                or not isinstance(parent, str):
            continue
        if data.get("record_role") == "event" and parent == row.record.id:
            events[parent] = row
        else:
            derived.setdefault(parent, []).append(key)
    for event_id, row in events.items():
        data = row.record.data
        if data.get("message_role") == "assistant" and isinstance(data.get("responds_to"), str):
            answers.setdefault(data["responds_to"], []).append(event_id)
    return ScopeView(state, events, {k: sorted(v) for k, v in derived.items()},
                     {k: sorted(v) for k, v in answers.items()})


def was_purged(view: ScopeView, event_id: str) -> bool:
    """Whether the latest audit row for this event's record is a purge."""
    return "workspace/" + event_id in view.state.purged
