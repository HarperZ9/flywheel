"""Shared vocabulary for hosted peer sessions.

A peer session is another agent harness (Claude Code, Codex) whose local
transcript Flywheel observes read-only. Every record here carries the file
provenance the observer used and a does_not_prove statement. A field the
source did not emit stays null; the observer never fills it in.

Two bounding rules apply to every label that leaves a transcript. A closed
set (a message role, a stop reason, a top-level record type) is checked
against an allowlist and anything else becomes "other". An open set (an
event sub-type, a tool name, a model label) is checked for identifier shape
and the number of distinct keys is capped. A crafted transcript therefore
cannot push free text, or an unbounded key set, into an observer record.
"""
from __future__ import annotations

from collections import Counter
import re

SESSION_SCHEMA = "flywheel.hosted-peer-session/v1"
REGISTRY_SCHEMA = "flywheel.hosted-peer-session-registry/v1"
MAILBOX_SCHEMA = "flywheel.peer-mailbox-message/v1"
OBSERVER_VERSION = "1"
HARNESS_CLAUDE = "claude_code"
HARNESS_CODEX = "codex"
HARNESSES = (HARNESS_CLAUDE, HARNESS_CODEX)
ACTIVITY_STATES = ("recent", "quiet", "stale", "unknown")
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/+-]{0,63}\Z")
MAX_DISTINCT_KEYS = 64
DOES_NOT_PROVE = ("Observation of a local transcript window proves the file's bytes at read time. "
                  "It does not prove the session is alive, that reported models or versions ran, "
                  "that any task succeeded, or that the file was written by the harness it names.")
FAILURE_DOES_NOT_PROVE = ("A recorded observation failure proves the observer could not read the "
                          "named path at that moment. It does not prove the file is absent, that "
                          "no session exists, or that the condition is permanent.")
CONTENT_POLICY = "content_minimized_hashes_and_counts_only"
SOURCE_AUTHENTICITY = "unavailable"
PUBLICATION_STATE = "not_approved_for_publication"


def activity_state(age: float | None, *, recent_within: float = 600.0,
                   quiet_within: float = 21_600.0) -> str:
    """Classify file freshness. Freshness is not liveness."""
    if age is None or age < 0:
        return "unknown"
    if age <= recent_within:
        return "recent"
    if age <= quiet_within:
        return "quiet"
    return "stale"


def bucket(value: object, allowed: tuple, *, other: str = "other") -> str:
    """Map a closed-set label onto its allowlist. Unlisted text never passes through."""
    if type(value) is not str:
        return "unknown"
    return value if value in allowed else other


def label(value: object, *, other: str = "other") -> str | None:
    """Keep an open-set label only when it has identifier shape, else `other`."""
    if type(value) is not str:
        return None
    return value if LABEL.match(value) else other


def bounded_counts(counter: Counter, *, other: str = "other",
                   limit: int = MAX_DISTINCT_KEYS) -> dict:
    """Sorted counts holding at most `limit` keys; the rest are summed under `other`."""
    if len(counter) <= limit:
        return dict(sorted(counter.items()))
    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    keep = dict(ranked[:limit - 1])
    keep[other] = keep.get(other, 0) + sum(count for _name, count in ranked[limit - 1:])
    return dict(sorted(keep.items()))


def base_record(harness: str, *, observed_at: str) -> dict:
    if harness not in HARNESSES:
        raise ValueError("unknown harness")
    return {"schema": SESSION_SCHEMA, "observer_version": OBSERVER_VERSION,
            "harness": harness, "observed_at": observed_at,
            "content_policy": CONTENT_POLICY, "source_authenticity": SOURCE_AUTHENTICITY,
            "publication_state": PUBLICATION_STATE, "does_not_prove": DOES_NOT_PROVE,
            "external_calls": 0}


def consistent(values: list) -> dict:
    """Report one value only when every emitted sample agrees.

    `samples` counts the samples the source actually emitted, so a field
    absent from most records cannot look well attested. One sample agrees
    with nothing, so it is reported as "single_sample", not "consistent".
    """
    samples = [v for v in values if v is not None]
    distinct = []
    for value in samples:
        if value not in distinct:
            distinct.append(value)
    if not distinct:
        return {"value": None, "basis": "not_emitted", "samples": 0}
    if len(distinct) == 1:
        basis = "consistent" if len(samples) > 1 else "single_sample"
        return {"value": distinct[0], "basis": basis, "samples": len(samples)}
    return {"value": None, "basis": "conflict", "samples": len(samples),
            "distinct": len(distinct)}


AGREED = ("consistent", "single_sample")

__all__ = ["ACTIVITY_STATES", "AGREED", "CONTENT_POLICY", "DOES_NOT_PROVE",
           "FAILURE_DOES_NOT_PROVE", "HARNESSES", "HARNESS_CLAUDE", "HARNESS_CODEX",
           "MAILBOX_SCHEMA", "MAX_DISTINCT_KEYS", "OBSERVER_VERSION", "PUBLICATION_STATE",
           "REGISTRY_SCHEMA", "SESSION_SCHEMA", "SOURCE_AUTHENTICITY", "activity_state",
           "base_record", "bounded_counts", "bucket", "consistent", "label"]
