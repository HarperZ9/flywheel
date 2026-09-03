"""cross_harness_usage.py -- verbatim inner-call usage capture and recompute.

The governed arm makes inner codex exec calls whose JSONL transcripts carry a
``usage`` block on ``turn.completed`` events. Three rules govern that block:

- VERBATIM: the provider's own field names are copied as-is. Nothing here
  computes a token count, renames a field, or fills a missing one.
- SUM-NEVER-FILL: the attempt aggregate sums per-call records only when every
  inner call produced a record and every record carries the same field names
  with nonnegative integer values. Anything less refuses the aggregate with a
  named reason; the per-call records are still retained.
- RECOMPUTABLE: the retained transcript is the authority. The checker
  recomputes the aggregate from the transcript and refuses the usage cell on
  any mismatch with what the receipt claims, over- or under-claiming alike.

Stdlib only. The checker never raises on disk data: malformed inputs return a
structured refusal, matching the verifier-never-raises house rule.
"""
from __future__ import annotations

from typing import Any

INNER_SOURCE = "codex_inner"

# The terminal event on which a peer reports the call's usage block. codex ends
# an inner call with turn.completed; the peer adapters record the block their
# provider puts on its result event as usage.observed. Both name the same
# thing, so the recompute reads both rather than being blind to one of them.
USAGE_EVENT_TYPES = ("turn.completed", "usage.observed")


def usage_from_events(events: list) -> "dict | None":
    """The verbatim usage block of one inner call's transcript, or None.

    Last ``turn.completed`` event carrying a dict ``usage`` wins, matching the
    served_model scan. No usage in the transcript yields None, never {}."""
    for event in reversed(events):
        if (isinstance(event, dict) and event.get("type") == "turn.completed"
                and isinstance(event.get("usage"), dict)):
            return dict(event["usage"])
    return None


def _summable(record: dict) -> bool:
    return (all(isinstance(key, str) for key in record)
            and all(type(value) is int and value >= 0 for value in record.values()))


def attempt_usage(per_call: list) -> dict:
    """Aggregate per-call usage records for one attempt, refusing over filling.

    ``per_call`` holds one entry per inner call, in call order; None marks a
    call whose transcript carried no usage block. All-None (or empty) gives {}
    so the receipt keeps its provider_usage_unavailable null reason. Otherwise
    the per-call records are retained verbatim and the ``aggregate`` is either
    a field-wise sum or None beside an ``aggregate_refused`` reason."""
    records = [record for record in per_call if record is not None]
    if not records:
        return {}
    out: dict[str, Any] = {
        "inner_calls": len(per_call),
        "per_call": [dict(record) if isinstance(record, dict) else record
                     for record in per_call]}
    if not all(isinstance(record, dict) for record in records):
        return {**out, "aggregate": None, "aggregate_refused":
                "USAGE_MALFORMED: a per-call usage record is not an object"}
    if len(records) < len(per_call):
        missing = len(per_call) - len(records)
        return {**out, "aggregate": None, "aggregate_refused":
                f"USAGE_ABSENT: {missing} of {len(per_call)} inner calls "
                "returned no usage block; summing the rest would understate "
                "the attempt"}
    if any(not _summable(record) for record in records):
        return {**out, "aggregate": None, "aggregate_refused":
                "USAGE_NON_SUMMABLE: a usage field is not a nonnegative "
                "integer"}
    keys = set(records[0])
    if any(set(record) != keys for record in records):
        return {**out, "aggregate": None, "aggregate_refused":
                "USAGE_KEY_MISMATCH: inner calls disagree on usage field "
                "names; summing would fill missing fields"}
    return {**out, "aggregate":
            {key: sum(record[key] for record in records) for key in sorted(keys)}}


def usage_records_from_trace(tool_trace: list, source: str = INNER_SOURCE) -> list:
    """Per-call usage records recovered from a retained attempt transcript.

    Inner events are tagged with a 1-based ``inner_call`` index at capture
    time. Each observed index yields one slot, ordered by index; the slot
    holds the call's last ``turn.completed`` usage dict, or None."""
    calls: dict[int, "dict | None"] = {}
    for event in tool_trace:
        if not isinstance(event, dict) or event.get("source") != source:
            continue
        index = event.get("inner_call")
        if type(index) is not int:
            continue
        calls.setdefault(index, None)
        if event.get("type") in USAGE_EVENT_TYPES and isinstance(event.get("usage"), dict):
            calls[index] = dict(event["usage"])
    return [calls[index] for index in sorted(calls)]


def inner_source(tool_trace: list) -> str:
    """The one event source that tagged inner calls in this transcript.

    Each harness names its own inner events: codex_inner for the governed arm,
    claude_code_inner for the Claude Code adapter. Reading the name off the
    transcript keeps the recompute honest for every adapter without any of them
    having to mislabel its events as another harness's.

    Exactly one tagged source is the only readable case. Zero and more than one
    both fall back to INNER_SOURCE, which recomputes a subset and so refuses a
    claim built from the whole; that is the fail-closed direction."""
    sources = {event.get("source") for event in tool_trace
               if isinstance(event, dict) and type(event.get("inner_call")) is int
               and isinstance(event.get("source"), str)}
    return sources.pop() if len(sources) == 1 else INNER_SOURCE


def recheck_inner_usage(tool_trace: Any, claimed: Any) -> dict:
    """Recompute the usage aggregate from the transcript; refuse on mismatch.

    ``claimed`` is the usage cell the attempt receipt carries. The transcript
    is the authority: equality passes, anything else returns a structured
    refusal carrying both sides. Never raises on malformed input."""
    if not isinstance(tool_trace, list):
        return {"verified": False, "usage_cell_refused":
                "USAGE_TRANSCRIPT_MALFORMED: transcript is not a list of events"}
    if not isinstance(claimed, dict):
        return {"verified": False, "usage_cell_refused":
                "USAGE_CLAIM_MALFORMED: the receipt's usage cell is not an object"}
    recomputed = attempt_usage(
        usage_records_from_trace(tool_trace, inner_source(tool_trace)))
    if recomputed == claimed:
        return {"verified": True, "recomputed": recomputed}
    return {"verified": False, "usage_cell_refused":
            "USAGE_RECOMPUTE_MISMATCH: the receipt's usage cell does not "
            "equal the transcript recompute",
            "claimed": claimed, "recomputed": recomputed}
