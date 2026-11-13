"""model_gates.py -- what had to be asked for before a figure could come back.

model_usage reports a quantity as ABSENT when the provider did not send it.
That is honest and it is also where the entropy is, because absent has two very
different causes and the response alone cannot separate them:

- the call asked for the figure and the provider did not send it, which is a
  provider fact worth escalating, or
- the call never asked, and the provider behaved exactly as documented.

Several providers put the figure behind a flag that defaults to off. A streamed
OpenAI call without ``stream_options.include_usage`` reports null usage on every
chunk, so a receipt built from it says zero tokens for a call that spent
thousands. Nothing in that response is wrong. The request was.

This module reads the REQUEST beside the response and says which gates were
open, so a reading of an absent figure can name its cause instead of implying
one. A gate reported ``unknown`` is not reported open.

Two kinds of gate, and the difference matters because only one of them is
visible from a request body:

- REQUEST_GATES live in the JSON that was sent. Checkable here, exactly.
- SERVER_GATES are launch flags on a self-hosted server. A vLLM started without
  ``--reasoning-parser`` never separates the chain of thought from the answer
  no matter what the request asks for, and the response carries no trace of the
  omission. These are UNKNOWN unless a caller hands over the serving process
  argv, which is the only place the fact exists.

``unlocks`` names either a usage meaning as model_dialects spells it, or
``reasoning_text``, which is the text model_reasoning captures. They are
separate: Gemini returns thoughtsTokenCount whether or not includeThoughts was
set, so the count and the text are behind different gates.

A gate belongs to a response schema. Whether it GOVERNS belongs to the service,
and the two do not always agree, so KIND_WAIVES exists to say where they part.

Standard library only. This module never reads a clock and never makes a call.
"""
from __future__ import annotations

from typing import Any

from .model_dialects import GEMINI, OLLAMA, OPENAI, OPENAI_RESPONSES

REASONING_TEXT = "reasoning_text"
_USAGE_MEANINGS = ("input", "output", "total", "cache_read", "cache_write",
                   "reasoning")

# state values, spelled once so a reader can compare rather than match strings
OPEN = "open"
SHUT = "shut"
UNKNOWN = "unknown"
NOT_APPLICABLE = "not_applicable"

REQUEST_GATES = {
    OPENAI: (
        {"gate": "stream_usage",
         "unlocks": _USAGE_MEANINGS,
         "path": ("stream_options", "include_usage"),
         "opens_on": True,
         "absent_state": SHUT,
         "applies_when": ("stream",),
         "note": "A streamed chat completion carries usage null on every chunk "
                 "unless this is set. The final chunk then arrives with an "
                 "empty choices array and the usage block, and a reader that "
                 "stops at the last content chunk still misses it."},
    ),
    OPENAI_RESPONSES: (
        {"gate": "stream_usage",
         "unlocks": _USAGE_MEANINGS,
         "path": ("stream_options", "include_usage"),
         "opens_on": True,
         "absent_state": SHUT,
         "applies_when": ("stream",),
         "note": "Same default as the chat endpoint."},
        {"gate": "encrypted_reasoning",
         "unlocks": (),
         "path": ("include",),
         "opens_on": "reasoning.encrypted_content",
         "absent_state": SHUT,
         "applies_when": (),
         "note": "Returns the reasoning in a form only the vendor can open. It "
                 "unlocks no readable text, so it is listed to explain an "
                 "encrypted block rather than to promise one."},
    ),
    GEMINI: (
        {"gate": "include_thoughts",
         "unlocks": (REASONING_TEXT,),
         "path": ("generationConfig", "thinkingConfig", "includeThoughts"),
         "opens_on": True,
         "absent_state": SHUT,
         "applies_when": (),
         "note": "Gates the thought PARTS only. thoughtsTokenCount comes back "
                 "either way, so a call can report reasoning tokens spent and "
                 "no reasoning text, and both readings are correct."},
    ),
    OLLAMA: (
        {"gate": "think",
         "unlocks": (REASONING_TEXT,),
         "path": ("think",),
         "opens_on": True,
         "absent_state": UNKNOWN,
         "applies_when": (),
         "note": "Three-state. true asks for thinking, false suppresses it, "
                 "and omitting the key leaves the model's own default in "
                 "charge. Omitted is therefore not the same claim as false, "
                 "and this reader will not turn one into the other."},
    ),
}

# Keyed by backend kind rather than dialect, because a vLLM and a llama-server
# both speak the OpenAI schema and are gated differently at launch.
SERVER_GATES = {
    "vllm": (
        {"gate": "reasoning_parser", "unlocks": (REASONING_TEXT,),
         "flag": "--reasoning-parser", "off_values": (),
         "note": "Without it the chain of thought stays inside message.content "
                 "and no reasoning field is ever emitted. The answer text then "
                 "silently contains the reasoning."},
    ),
    "llamacpp": (
        {"gate": "reasoning_format", "unlocks": (REASONING_TEXT,),
         "flag": "--reasoning-format", "off_values": ("none",),
         "note": "The value none leaves the chain inside content. Passing the "
                 "flag is not enough on its own."},
    ),
}

# Same gate, same schema, different service. OpenRouter speaks the OpenAI
# schema and meters usage unconditionally: its usage-accounting page states
# that accounting is automatic, that "No additional parameters are required",
# and that stream_options.include_usage is "deprecated and has no effect". So
# on that kind the streaming gate governs nothing, and calling it shut would
# blame the request for an absence only the provider could have caused. That is
# this module's own error pointed the other way, and it is worse than saying
# nothing, because it hands an operator a cause that closes the question.
#
# A caller who supplies no kind gets the dialect default and is told which
# kinds would have waived the gate, so the caveat travels with the reading
# rather than being dropped.
KIND_WAIVES = {
    "openrouter": ("stream_usage",),
}

_WAIVABLE = {name for names in KIND_WAIVES.values() for name in names}


def _dig(obj: Any, path: tuple) -> Any:
    """Walk a path, returning None the moment the walk leaves dicts."""
    cursor = obj
    for key in path:
        if not isinstance(cursor, dict) or key not in cursor:
            return None
        cursor = cursor[key]
    return cursor


def _request_state(request: Any, gate: dict) -> str:
    """One request gate's state.

    A request this module was not given reads UNKNOWN throughout, never
    NOT_APPLICABLE, because not seeing the body is not the same as seeing a
    body that did not stream.
    """
    if not isinstance(request, dict):
        return UNKNOWN
    applies = gate["applies_when"]
    if applies and not _dig(request, applies):
        return NOT_APPLICABLE
    value = _dig(request, gate["path"])
    if value is None:
        return gate["absent_state"]
    wanted = gate["opens_on"]
    if isinstance(value, list):
        return OPEN if wanted in value else SHUT
    if isinstance(wanted, bool):
        # 1 == True in Python, and a gate is not opened by an integer.
        return OPEN if value is wanted else SHUT
    return OPEN if value == wanted else SHUT


def _server_state(argv: Any, gate: dict) -> str:
    """A launch flag's state, or unknown when no argv was supplied.

    Absent argv is UNKNOWN and never SHUT. Not being told how a server was
    started is not evidence that it was started wrong.
    """
    if not isinstance(argv, (list, tuple)) or not argv:
        return UNKNOWN
    tokens = [str(a) for a in argv]
    flag = gate["flag"]
    for index, token in enumerate(tokens):
        if token == flag:
            following = tokens[index + 1] if index + 1 < len(tokens) else ""
            if not following or following.startswith("-"):
                return SHUT      # the flag takes a value and did not get one
            return SHUT if following in gate["off_values"] else OPEN
        if token.startswith(flag + "="):
            return SHUT if token.split("=", 1)[1] in gate["off_values"] else OPEN
    return SHUT


def check(request: Any, *, dialect: str, kind: str = "",
          server_argv: Any = None) -> dict:
    """Every gate that governs what this call could report, with its state.

    ``request`` is the JSON body that was sent. ``kind`` is the backend kind as
    endpoints.py spells it, and supplying it is what lets a gate that does not
    govern this service report so. ``server_argv`` is the command line of a
    self-hosted server when the caller has it, and omitting it leaves those
    gates unknown rather than assuming either answer.
    """
    gates = []
    waived = KIND_WAIVES.get(kind, ())
    for gate in REQUEST_GATES.get(dialect, ()):
        name = gate["gate"]
        entry = {"gate": name, "where": "request",
                 "state": (NOT_APPLICABLE if name in waived
                           else _request_state(request, gate)),
                 "path": ".".join(gate["path"]),
                 "unlocks": list(gate["unlocks"]),
                 "note": gate["note"]}
        if name in waived:
            entry["waived_by_kind"] = kind
        elif not kind and name in _WAIVABLE:
            entry["waived_on_kinds"] = sorted(
                k for k, names in KIND_WAIVES.items() if name in names)
        gates.append(entry)
    for gate in SERVER_GATES.get(kind, ()):
        gates.append({"gate": gate["gate"], "where": "server",
                      "state": _server_state(server_argv, gate),
                      "path": gate["flag"],
                      "unlocks": list(gate["unlocks"]),
                      "note": gate["note"]})
    return {"dialect": dialect, "kind": kind or None, "gates": gates,
            "all_open": all(g["state"] in (OPEN, NOT_APPLICABLE)
                            for g in gates)}


def why_absent(reading: Any, meaning: str) -> dict:
    """Whether a gate explains this quantity being missing from the response.

    ``explained`` True means the call did not ask for the figure, so its absence
    says nothing about the provider. ``explained`` False with every governing
    gate open means the provider was asked and did not answer, which is the case
    worth escalating. A gate in the unknown state explains nothing, and is
    reported so the reader can go and find out.
    """
    out = {"meaning": meaning, "explained": False, "by": [], "unknown": []}
    gates = reading.get("gates") if isinstance(reading, dict) else None
    for gate in gates or ():
        if meaning not in gate.get("unlocks", ()):
            continue
        if gate["state"] == SHUT:
            out["explained"] = True
            out["by"].append(gate["gate"])
        elif gate["state"] == UNKNOWN:
            out["unknown"].append(gate["gate"])
    return out


__all__ = ["KIND_WAIVES", "NOT_APPLICABLE", "OPEN", "REASONING_TEXT",
           "REQUEST_GATES",
           "SERVER_GATES", "SHUT", "UNKNOWN", "check", "why_absent"]
