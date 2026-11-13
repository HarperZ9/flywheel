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
"""
from __future__ import annotations

from typing import Any

from . import model_reasoning
from .model_dialects import dialect_for
from .model_usage import capture as _usage


def observe(response: Any, *, dialect: "str | None", requested_model: str = "",
            keep_reasoning: bool = False) -> dict:
    """What can be said about one answered call, without its answer text.

    Returns a record with ``usage`` and ``reasoning`` always present, so a
    caller never has to branch on whether observation happened. An unmapped
    dialect still yields both, each marked as unread rather than as empty.
    """
    if not dialect:
        return {"usage": {"dialect": None, "provenance": "absent",
                          "refused": "USAGE_DIALECT_UNMAPPED: the backend kind "
                                     "has no mapped response schema"},
                "reasoning": model_reasoning.redacted(
                    model_reasoning.capture(None, dialect=""))}
    usage = _usage(response, dialect=dialect, requested_model=requested_model)
    reasoning = model_reasoning.capture(response, dialect=dialect)
    if not keep_reasoning:
        reasoning = model_reasoning.redacted(reasoning)
    return {"usage": usage, "reasoning": reasoning}


def attach(out: dict, response: Any, *, dialect: "str | None",
           requested_model: str = "", keep_reasoning: bool = False) -> dict:
    """Put the observation on a backend return and hand the return back.

    Written as a one-line call so a backend's chat() gains a line rather than a
    paragraph, and so every backend attaches the same keys in the same shape.
    """
    out.update(observe(response, dialect=dialect,
                       requested_model=requested_model,
                       keep_reasoning=keep_reasoning))
    return out


__all__ = ["attach", "dialect_for", "observe"]
