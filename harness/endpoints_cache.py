"""endpoints_cache.py -- provider prompt caching for a coding session.

A coding session sends the same long prefix on every model call: the tool
schemas, the system prompt, and the conversation so far. Providers can keep
that prefix and charge less to read it again. What each one needs from the
client differs:

  Anthropic  the request must mark what to keep. `marked` adds two marks: one
             on the system prompt, which holds the tools and the system text
             as one stable prefix, and one at the top level of the request,
             which the provider places on the last block and moves forward as
             the conversation grows.
  OpenAI     nothing. Caching is on by default for supported models.
  Gemini     nothing. Implicit caching is on by default for 2.5 and newer.

For all three, the token counts the provider reports for cache reads and
cache writes reach the session through endpoints_reply.cache_counts. Nothing
is estimated: a reply with no cache figure adds none.

The marks are added only while a session's toolbox is in force with caching
on, so the gateway and other callers send what they sent before. A host that
refuses `cache_control` is remembered and asked again without it.

Sources, read 2026-11-13:
  Anthropic  https://platform.claude.com/docs/en/build-with-claude/prompt-caching
  OpenAI     https://developers.openai.com/api/docs/guides/prompt-caching
  Gemini     https://aistudio.google.com/docs/caching
"""
from __future__ import annotations

import logging

from . import endpoints_tools as _tools

ENV = "FLYWHEEL_PROMPT_CACHE"            # "0" turns the marks off
MARK = {"type": "ephemeral"}             # the provider's default lifetime, five minutes
_NO_CACHE: set = set()                   # base URLs that refused cache_control
_LOG = logging.getLogger(__name__)


def on_from_env(environ) -> bool:
    return (environ.get(ENV) or "").strip() != "0"


def marked(dialect: str, backend, payload: dict) -> dict:
    """The request with cache marks, when this session and provider use them."""
    box = _tools.current()
    if dialect != "anthropic" or box is None or not getattr(box, "cache", False):
        return payload
    if backend.base_url in _NO_CACHE:
        return payload
    out = {**payload, "cache_control": dict(MARK)}
    system = payload.get("system")
    if isinstance(system, str) and system:
        out["system"] = [{"type": "text", "text": system, "cache_control": dict(MARK)}]
    return out


def refused(backend, status: int, obj, payload: dict) -> bool:
    """True when a host turned down the cache marks; it is remembered."""
    if status != 400 or "cache_control" not in payload:
        return False
    from .endpoints import _error_message
    from .provider_fault_boundary import redacted_text
    message = _error_message(obj).lower()
    if "cache_control" not in message:
        return False
    _NO_CACHE.add(backend.base_url)
    _LOG.warning("%s refused cache_control with status %s: %s; prompt caching is off "
                 "for this host", backend.name, status, redacted_text(message))
    return True
