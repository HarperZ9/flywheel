"""endpoints_tools_fallback.py -- when a host says a model cannot take tool schemas.

Native function calling falls back to the text protocol for a model whose
host refuses tool schemas (endpoints_tools.refused). In the text protocol a
`TOOL name {json}` line in a reply is a call, so the fallback also switches
off the rule that only tool-call objects run. It must therefore start only on
an error that says tools or function calling are unsupported for the model,
and never on another 400 that happens to mention tools or functions (a
context-length error counts the tokens "in the functions").

`unsupported(obj)` decides. It reads the error's message, and for the OpenAI
error shape its `code` and `param`.

What the wording rests on, read 2026-11-14:

  https://platform.claude.com/docs/en/api/errors
      The error shape, and two documented forms: "'<model>' does not support
      tool types: <type>." and "... is not supported for this model". The
      page documents no error for a model that cannot take custom tools.
  https://developers.openai.com/api/docs/guides/error-codes
      `error.type`, `error.code` and `error.param`. The page documents no
      error for a model without tool support.
  https://aistudio.google.com/docs/troubleshooting
      (ai.google.dev/gemini-api/docs/troubleshooting redirects there.) No
      error text for a model without function calling.

So no first-party page gives the exact sentence. The phrases below come from
those two documented forms and from error texts quoted in public issue
reports, which a web search listed on the same day and which were not opened
or checked against a live host: Ollama "<model> does not support tools"
(github.com/EricleungDK/Alfredo/issues/254), Gemini "Function calling is not
enabled for <model>" (github.com/BerriAI/litellm/issues/10313,
github.com/vercel/ai/issues/10775), OpenRouter "No endpoints found that
support tool use" (github.com/mastra-ai/mastra/issues/2839). A host that
words its refusal another way is not recognized: the request fails with the
host's error, and `FLYWHEEL_NATIVE_TOOLS=0` selects the text protocol by hand.
"""
from __future__ import annotations

import re

KIND = "native_tools_fallback"           # ledger kind of the notice
_SAYS = re.compile(
    r"does(?: not|n't) support (?:tools?|tool (?:use|calling|calls|types)|function calling"
    r"|functions?)(?!\w)"
    r"|(?:\btools?|\btool (?:use|calling|calls)|\bfunction calling|\bfunctions?(?: parameter)?"
    r"|['\"`]tools['\"`]) (?:is|are) not (?:supported|enabled|available)"
    r"|no endpoints found that support tool use"
    r"|['\"`]auto['\"`] tool choice requires"
    r"|unsupported parameter: ['\"`]?(?:tools|functions)['\"`]?(?!\w)")
# An error about something narrower or something else, whatever else it says: a size or
# rate limit, one way of choosing or combining tools, or tools together with another input.
_OTHER = re.compile(r"context[ _-]?(?:length|window)|maximum context|too many tokens"
                    r"|too long|too large|rate limit|quota|tool_choice|parallel"
                    r"|stream|with (?:images?|vision|audio|files?)")
_OTHER_CODES = ("context_length_exceeded", "string_above_max_length", "rate_limit_exceeded",
                "insufficient_quota")
_PARAMS = ("tools", "functions")


def unsupported(obj) -> bool:
    """True when a provider's error says the model cannot take tools or function calls."""
    from .endpoints import _error_message
    error = obj.get("error") if isinstance(obj, dict) else None
    error = error if isinstance(error, dict) else {}
    message = _error_message(obj).lower()
    code = str(error.get("code") or "").lower()
    if code in _OTHER_CODES or _OTHER.search(message):
        return False
    if _SAYS.search(message):
        return True
    return (str(error.get("param") or "").lower() in _PARAMS
            and code in ("unsupported_parameter", "unsupported_value"))


def notice(backend, status: int) -> str:
    """The one line a session shows and records when a model moves to the text protocol."""
    return (f"{backend.name} ({backend.model}) answered {status}: it does not take tool "
            "schemas. This model now uses the text protocol until the program ends, so "
            "`TOOL name {json}` lines in its replies are calls. Set FLYWHEEL_NATIVE_TOOLS=0 "
            "to choose the text protocol yourself.")


def moved_notice(backend) -> str:
    """The line for a session whose model was moved by another session of the program.

    The list of moved models is shared by the process, so this session's
    replies are read by the text protocol too. It shows and records this line
    once, at its first request for the model after the move."""
    return (f"{backend.name} ({backend.model}) does not take tool schemas: its host said so "
            "to another session of this program. This model uses the text protocol until "
            "the program ends, so `TOOL name {json}` lines in its replies are calls. Set "
            "FLYWHEEL_NATIVE_TOOLS=0 to choose the text protocol yourself.")
