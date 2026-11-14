"""endpoints_reply.py -- one provider response, read into a backend return.

Each hosted backend sends a request and gets back one response object. These
readers turn that object into the dict a backend's `chat` returns: the text,
the model reference, the provider's token counts and the observation record.

They live apart from the request code so that two paths share them. `chat`
hands over the object the provider sent in one piece. The streamed path
(endpoints_stream) rebuilds the same object from the provider's stream events
and hands that over. One reader for both is what makes a streamed reply and a
plain reply record the same thing.
"""
from __future__ import annotations

from .endpoints_http import _parse_tool_call, _response_error
from .local_agent import BackendError
from .model_observation import attach as _observed
from .provider_fault_boundary import redacted_text
from .token_usage import field as _usage, from_anthropic, from_gemini, from_openai


def _empty_openai(backend, status, obj) -> BackendError:
    """A 200 with no content and no tool call.

    A reasoning model that spent its whole budget returns content null, which
    is refusal-shaped and is never an empty reply. finish_reason separates the
    two causes a person can act on: "length" means raise max_tokens, anything
    else means the turn came back empty.
    """
    reason = ""
    try:
        reason = obj["choices"][0].get("finish_reason") or ""
    except (KeyError, IndexError, TypeError, AttributeError):
        pass
    detail = f" (finish_reason={redacted_text(str(reason))})" if reason else ""
    if reason == "length":
        detail += "; the completion budget was spent before any " \
                  "content was emitted -- raise max_tokens"
    return BackendError(f"{backend.name} returned {status} with no message content{detail}")


def openai_reply(backend, status, obj, payload, seed) -> dict:
    """An OpenAI-compatible chat completion object."""
    try:
        message = obj["choices"][0]["message"]
        text = message["content"]
    except (KeyError, IndexError, TypeError):
        raise _response_error(backend.name, status, obj, kind=backend.name)
    out = {"model_ref": f"{backend.name}:{backend.model}", "seed": seed}
    calls = message.get("tool_calls") if isinstance(message, dict) else None
    if isinstance(calls, list) and calls:
        out["tool_calls"] = [_parse_tool_call(c) for c in calls]
    if not isinstance(text, str) or not text.strip():
        if not out.get("tool_calls"):
            raise _empty_openai(backend, status, obj)
        text = ""                  # a pure tool-call turn carries no prose
    out["text"] = text
    out.update(_usage(from_openai(obj)))
    return _observed(out, obj, dialect="openai", requested_model=backend.model,
                     keep_reasoning=backend.keep_reasoning, request=payload,
                     kind=backend.name)


def anthropic_reply(backend, status, obj, payload, seed) -> dict:
    """An Anthropic Messages response object."""
    try:
        text = "".join(b.get("text", "") for b in obj["content"] if b.get("type") == "text")
    except (KeyError, TypeError, AttributeError):
        raise _response_error(backend.name, status, obj, kind="anthropic")
    out = {"text": text, "model_ref": f"{backend.name}:{backend.model}", "seed": seed,
           **_usage(from_anthropic(obj))}
    return _observed(out, obj, dialect="anthropic", requested_model=backend.model,
                     keep_reasoning=backend.keep_reasoning, request=payload)


def gemini_reply(backend, status, obj, payload, seed) -> dict:
    """A Gemini GenerateContentResponse object.

    A part flagged thought:true is the model reasoning and is left out of the
    answer. Joining every part would put the chain of thought inside the text
    every caller stores as the reply.
    """
    try:
        parts = obj["candidates"][0]["content"]["parts"]
        text = "".join(q.get("text", "") for q in parts if q.get("thought") is not True)
    except (KeyError, IndexError, TypeError, AttributeError):
        raise _response_error(backend.name, status, obj, kind="gemini")
    out = {"text": text, "model_ref": f"{backend.name}:{backend.model}", "seed": seed,
           **_usage(from_gemini(obj))}
    return _observed(out, obj, dialect="gemini", requested_model=backend.model,
                     keep_reasoning=backend.keep_reasoning, request=payload)
