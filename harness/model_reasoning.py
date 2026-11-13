"""model_reasoning.py -- the model's own reasoning, captured and gated.

A reasoning model spends most of its output tokens on text the caller never
sees. When a turn goes wrong, that text is the evidence, and until now every
hosted backend dropped it on the floor: AnthropicBackend joined only the blocks
of type "text", and the OpenAI-compatible backend read only message.content.
A thinking block that arrived was discarded without being counted.

This module captures it and puts a gate around it in the same movement, because
reasoning is the most sensitive thing a model call produces. It is unrehearsed,
it quotes the prompt back, and it routinely contains material the final answer
was careful to leave out. So the record carries a publication state, and the
default form that crosses a route or lands in an artifact is the REDACTED one:
a digest, a character count and a block count, with no text.

Two block kinds are deliberately not treated alike. An Anthropic
``redacted_thinking`` block carries an encrypted blob under ``data`` which no
reader here can decrypt, including the model. Digesting it as reasoning text
would put a number on something that is not text at all, so it is counted and
never read. Its presence is reported under its own key.

Nothing here decides retention. A caller that wants the text keeps the full
record; a caller serving a browser calls ``redacted`` first. Making that an
explicit call rather than a default keeps the leak an act rather than an
oversight.

Standard library only. This module never reads a clock and never makes a call.
"""
from __future__ import annotations

import hashlib
from typing import Any

from .model_dialects import ANTHROPIC, GEMINI, OLLAMA, OPENAI, OPENAI_RESPONSES
from .model_dialects import OPENAI_REASONING_KEYS as _OPENAI_KEYS

# The same spelling peer_session_types.PUBLICATION_STATE and norvane_capture
# use. Reasoning is operator material until an operator says otherwise, and no
# code path here can change this value.
PUBLICATION_STATE = "not_approved_for_publication"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _from_openai(response: dict) -> tuple:
    """Reasoning from choices[0].message, under whichever key carries it."""
    try:
        message = response["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return [], None, 0
    if not isinstance(message, dict):
        return [], None, 0
    for key in _OPENAI_KEYS:
        value = message.get(key)
        if isinstance(value, str) and value:
            return [value], key, 0
    return [], None, 0


def _from_responses(response: dict) -> tuple:
    """Reasoning items in the Responses output array.

    A different shape from the chat endpoint on the same vendor. What arrives
    is a SUMMARY of the reasoning rather than the reasoning itself, so a caller
    holding this holds less than an Anthropic thinking block gives, and the
    source key says which of the two it got. ``encrypted_content`` carries the
    real chain in a form only the vendor can open, so it is counted the way a
    redacted_thinking block is counted and is never digested as text.
    """
    items = response.get("output")
    if not isinstance(items, list):
        return [], None, 0
    texts, encrypted = [], 0
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "reasoning":
            continue
        if isinstance(item.get("encrypted_content"), str) and item["encrypted_content"]:
            encrypted += 1
        for part in item.get("summary") or ():
            if not isinstance(part, dict) or part.get("type") != "summary_text":
                continue
            value = part.get("text")
            if isinstance(value, str) and value:
                texts.append(value)
    return texts, ("summary_text" if texts else None), encrypted


def _from_anthropic(response: dict) -> tuple:
    """Thinking blocks in the content array, with encrypted blocks counted.

    The signature that travels with a thinking block is not part of the
    reasoning, so it is not read here. Counting the redacted blocks separately
    is what keeps "no reasoning was returned" distinguishable from "reasoning
    was returned in a form nothing here can read"."""
    blocks = response.get("content")
    if not isinstance(blocks, list):
        return [], None, 0
    texts, encrypted = [], 0
    for block in blocks:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "thinking":
            value = block.get("thinking")
            if isinstance(value, str) and value:
                texts.append(value)
        elif kind == "redacted_thinking":
            encrypted += 1
    return texts, ("thinking" if texts else None), encrypted


def _from_gemini(response: dict) -> tuple:
    """Parts flagged thought: true on the first candidate.

    A part with no thought flag is the answer, not the reasoning. The flag is
    checked with ``is True`` because a truthy value of another type would be a
    shape this function does not understand, and reading it as a thought would
    put the answer in the reasoning field."""
    try:
        parts = response["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return [], None, 0
    if not isinstance(parts, list):
        return [], None, 0
    texts = [p.get("text") for p in parts
             if isinstance(p, dict) and p.get("thought") is True
             and isinstance(p.get("text"), str) and p.get("text")]
    return texts, ("thought" if texts else None), 0


def _from_ollama(response: dict) -> tuple:
    """The thinking field ollama returns, from either of its two endpoints.

    /api/chat puts it beside content on the message. /api/generate has no
    message and puts it at the top level. Both are read because model_ollama
    calls both, and reading only the chat shape would report no reasoning for
    every generate call rather than reporting the reasoning that arrived."""
    message = response.get("message")
    if isinstance(message, dict):
        value = message.get("thinking")
        if isinstance(value, str) and value:
            return [value], "message.thinking", 0
    value = response.get("thinking")
    if isinstance(value, str) and value:
        return [value], "thinking", 0
    return [], None, 0


_READERS = {
    OPENAI: _from_openai,
    OPENAI_RESPONSES: _from_responses,
    ANTHROPIC: _from_anthropic,
    GEMINI: _from_gemini,
    OLLAMA: _from_ollama,
}


def capture(response: Any, *, dialect: str) -> dict:
    """One call's reasoning, with its text, or a record saying there was none.

    ``present`` is the field to branch on. A dialect this module cannot read
    reports present False with ``dialect_unmapped`` set, which is not the same
    claim as the provider having returned nothing.
    """
    record = {
        "dialect": dialect,
        "present": False,
        "blocks": 0,
        "chars": 0,
        "sha256": None,
        "source_key": None,
        "encrypted_blocks": 0,
        "dialect_unmapped": dialect not in _READERS,
        "publication_state": PUBLICATION_STATE,
    }
    reader = _READERS.get(dialect)
    if reader is None or not isinstance(response, dict):
        return record
    texts, source_key, encrypted = reader(response)
    record["encrypted_blocks"] = encrypted
    if not texts:
        return record
    joined = "\n".join(texts)
    record.update({
        "present": True,
        "blocks": len(texts),
        "chars": len(joined),
        "sha256": _sha256(joined),
        "source_key": source_key,
        "text": joined,
    })
    return record


def redacted(record: Any) -> dict:
    """The same record with the reasoning text removed.

    The digest and the counts stay, so a surface can show that reasoning was
    returned and how much of it, and a later holder of the text can prove the
    text is the one this record was taken from. Calling this twice is safe.
    """
    if not isinstance(record, dict):
        return {"present": False, "publication_state": PUBLICATION_STATE}
    out = {k: v for k, v in record.items() if k != "text"}
    out["redacted"] = True
    return out


def matches(record: Any, text: Any) -> "bool | None":
    """Whether some text is the reasoning this record was taken from.

    None when the record carries no digest to compare against, because an
    absent digest makes the question unanswerable rather than answered no.
    """
    if not isinstance(record, dict) or not isinstance(text, str):
        return None
    digest = record.get("sha256")
    if not isinstance(digest, str) or not digest:
        return None
    return _sha256(text) == digest


__all__ = ["PUBLICATION_STATE", "capture", "matches", "redacted"]
