"""model_observation.py -- one model call, as observed at the boundary.

model_usage reads what a provider reported about a call. model_reasoning reads
what the model thought while answering it. This composes both into the single
record a backend attaches to its return, and it owns the one decision neither
of those modules can make alone: whether the reasoning TEXT travels.

It does not, by default. Fifteen call sites take a backend return, and at least
one of them writes the whole dict to a durable store
(bulletin_model_worker.py:136 seals it into worker-result.json). Attaching
reasoning text by default would put unrehearsed model output into artifacts
that never carried it before, at every one of those sites at once. So the
default is the redacted record, and a caller that wants the text asks for it by
passing keep_reasoning=True, the same way the wire witness only keeps bytes when
the operator passes --keep-bytes.

The dialect is a property of the response shape, not of the vendor. A local
llama-server speaking the OpenAI schema is the openai dialect even though no
OpenAI service was involved, and reading it any other way would find no usage
block at all.

Three things happen to provider text on its way into the record. Every string
in the usage block and the served model name is scrubbed for key shapes, since
the record is what lands in a receipt. Reasoning text a caller keeps is
scrubbed the same way, and its digest and character count still describe the
text the provider sent. And when a backend hands over the request it sent,
model_gates reads it beside the response, so an absent figure names its cause.

``keep_reasoning`` has one switch outside code: FLYWHEEL_KEEP_REASONING=1 in
the environment turns it on for every hosted backend built after that. Unset,
or any other value, leaves the default: the text does not travel.
"""
from __future__ import annotations

import os
from typing import Any

from . import model_gates, model_reasoning, model_redaction
from .model_dialects import dialect_for
from .model_usage import capture as _usage

KEEP_REASONING_ENV = "FLYWHEEL_KEEP_REASONING"


def keep_reasoning_default() -> bool:
    """Whether the operator asked, in the environment, for reasoning text."""
    return os.environ.get(KEEP_REASONING_ENV, "").strip() == "1"


def _note(record: dict, kinds: list) -> None:
    for kind in kinds:
        if kind not in record.setdefault("redacted_kinds", []):
            record["redacted_kinds"].append(kind)


def _scrubbed_usage(usage: dict) -> dict:
    """The usage record with a key-shaped string taken out of provider text.

    ``redacted_kinds`` appears only when something was replaced, so a clean
    record is byte-for-byte what model_usage produced."""
    block = model_redaction.scrub_value(usage.get("reported"), items=256)
    if block["kinds"]:
        usage["reported"] = block["value"]
        _note(usage, block["kinds"])
    served = usage.get("served_model")
    if isinstance(served, str):
        reading = model_redaction.scrub(served, limit=256)
        if reading["redacted"] or reading["truncated"]:
            usage["served_model"] = reading["text"]
            _note(usage, reading["kinds"])
    return usage


def _scrubbed_reasoning(record: dict) -> dict:
    """Kept reasoning text with key shapes replaced and nothing cut.

    ``sha256`` and ``chars`` stay as model_reasoning measured them, on the
    provider's text, so model_reasoning.matches answers for that text and not
    for the scrubbed copy. ``text_redacted_kinds`` says when the two differ."""
    text = record.get("text")
    if not isinstance(text, str):
        return record
    reading = model_redaction.scrub(text, limit=len(text))
    if reading["redacted"]:
        record = {**record, "text": reading["text"],
                  "text_redacted_kinds": reading["kinds"]}
    return record


def _gates(request: Any, usage: dict, reasoning: dict, *, dialect: str,
           kind: str) -> dict:
    """Which request gates were open, and whether one explains an absence."""
    reading = model_gates.check(request, dialect=dialect, kind=kind)
    absent = {}
    if usage.get("provenance") == "absent":
        absent["usage"] = model_gates.why_absent(reading, "total")
    if not reasoning.get("present"):
        absent[model_gates.REASONING_TEXT] = model_gates.why_absent(
            reading, model_gates.REASONING_TEXT)
    reading["absent"] = absent
    return reading


def observe(response: Any, *, dialect: "str | None", requested_model: str = "",
            keep_reasoning: bool = False, request: Any = None,
            kind: str = "") -> dict:
    """What can be said about one answered call, without its answer text.

    Returns a record with ``usage`` and ``reasoning`` always present, so a
    caller never has to branch on whether observation happened. An unmapped
    dialect still yields both, each marked as unread rather than as empty.
    ``gates`` is added when the caller hands over the request body it sent.
    """
    if not dialect:
        return {"usage": {"dialect": None, "provenance": "absent",
                          "refused": "USAGE_DIALECT_UNMAPPED: the backend kind "
                                     "has no mapped response schema"},
                "reasoning": model_reasoning.redacted(
                    model_reasoning.capture(None, dialect=""))}
    usage = _scrubbed_usage(
        _usage(response, dialect=dialect, requested_model=requested_model))
    reasoning = model_reasoning.capture(response, dialect=dialect)
    reasoning = (_scrubbed_reasoning(reasoning) if keep_reasoning
                 else model_reasoning.redacted(reasoning))
    record = {"usage": usage, "reasoning": reasoning}
    if request is not None:
        record["gates"] = _gates(request, usage, reasoning, dialect=dialect,
                                 kind=kind)
    return record


def attach(out: dict, response: Any, *, dialect: "str | None",
           requested_model: str = "", keep_reasoning: bool = False,
           request: Any = None, kind: str = "") -> dict:
    """Put the observation on a backend return and hand the return back.

    Written as a one-line call so a backend's chat() gains a line rather than a
    paragraph, and so every backend attaches the same keys in the same shape.
    """
    out.update(observe(response, dialect=dialect,
                       requested_model=requested_model,
                       keep_reasoning=keep_reasoning, request=request,
                       kind=kind))
    return out


__all__ = ["KEEP_REASONING_ENV", "attach", "dialect_for",
           "keep_reasoning_default", "observe"]
