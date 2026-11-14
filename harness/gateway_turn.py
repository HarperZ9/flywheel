"""gateway_turn.py -- one neutral model turn behind every gateway interface.

The gateway answers more than one wire format: Anthropic Messages and OpenAI
Responses. Each interface parses its request into a `Turn`, picks an
upstream with `resolve_upstream`, sends the turn (gateway_turn_call) and
renders the `Reply` in its own format. What every interface shares lives in
this module: the turn and reply shapes, the upstream choice, the tool-result
check, the text form the ledger hashes, the ledger entries and the receipt.

A neutral message is {"role", "text", "calls", "results"}:
  role     "user" or "assistant"
  text     the turn's prose
  calls    [{"id", "name", "arguments"}], tool calls an assistant turn made
  results  [{"id", "ok", "output"}], tool results a user turn carries

Neutral usage is {"input", "output", "cache_read", "cache_write"}. "input" is
the input the provider did not serve from cache, which is Anthropic's meaning
of input_tokens. A count the provider did not send is None, never an estimate.

Ledger. A served call appends `endpoint_call` with the meta keys the
OpenAI-chat path writes (endpoint, model_ref, seed, prompt_sha, response_sha)
plus `interface`, `usage_reported` and the caller: `key` is `owner` for the
gateway token, or a virtual key's name with `key_fp`, `charged_tokens` and,
when the charge is the word estimate, `estimated`. A call that fails after
the upstream was contacted appends `endpoint_call_failed` with the caller. A
request refused before any upstream call appends nothing, except a virtual
key's budget or allow-list refusal, which appends `endpoint_call_refused`
(gateway_key_gate).
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field

_LOG = logging.getLogger(__name__)
_APPEND = threading.Lock()            # Claude Code sends requests in parallel

UPSTREAM_ENV = "FLYWHEEL_GATEWAY_UPSTREAM"
TIMEOUT = 600.0
# name -> (dialect, base URL, default model). Tests point these at a loopback stub.
NATIVE = {
    "anthropic": ("anthropic", "https://api.anthropic.com", "claude-sonnet-5"),
    "gemini": ("gemini", "https://generativelanguage.googleapis.com/v1beta", "gemini-2.5-flash"),
}
# Endpoints that take one flattened prompt and so cannot carry a structured turn.
NO_STRUCTURED = ("claude-cli", "codex-cli", "opencode", "serve")


class TurnRefused(Exception):
    """A request refused before any upstream call. kind: "invalid" or "not_found"."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


class UpstreamFailed(Exception):
    """The upstream was contacted and the call did not produce a reply."""

    def __init__(self, message: str, *, status: int = 502, reason: str = "upstream_error",
                 body=None, headers: "dict | None" = None):
        super().__init__(message)
        self.status, self.reason = status, reason
        self.body, self.headers = body, headers or {}


@dataclass
class Turn:
    interface: str                      # "anthropic-messages", "openai-responses"
    model: str                          # the model name the client sent
    system: str = ""
    messages: list = field(default_factory=list)
    tools: list = field(default_factory=list)   # [{"name", "description", "parameters"}]
    tool_choice: "dict | None" = None   # {"mode": auto|any|none|tool, "name", "parallel"}
    max_tokens: int = 1024
    temperature: "float | None" = None
    top_p: "float | None" = None
    stop: list = field(default_factory=list)
    stream: bool = False
    uncarried: list = field(default_factory=list)   # content only the same dialect carries
    caller: object = None               # gateway_key_gate.Caller; None is the owner
    _form: "tuple | None" = field(default=None, repr=False)

    def text_form(self) -> tuple:
        """(system, prompt): the conversation as the OpenAI-chat path flattens it."""
        if self._form is None:
            self._form = _text_form(self)
        return self._form


@dataclass
class Reply:
    text: str
    calls: list                         # [{"id", "name", "arguments"}]
    stop_reason: str                    # "end", "length", "tool" or "refusal"
    usage: dict                         # neutral usage; None where not reported
    model_ref: str                      # "endpoint:model", as the chat path records it
    served_model: str = ""              # the model the provider says it served
    raw: object = None                  # the upstream response object

    @property
    def usage_reported(self) -> bool:
        return self.usage.get("input") is not None and self.usage.get("output") is not None


@dataclass
class Response:
    """What an interface hands the HTTP layer: a JSON body or an event stream."""
    status: int
    body: "dict | None" = None
    chunks: object = None               # an iterator of bytes, for an event stream
    headers: dict = field(default_factory=dict)
    fault: object = None                # text -> the interface's stream error event


@dataclass
class Upstream:
    name: str                           # the gateway endpoint name, e.g. "ollama"
    dialect: str                        # "openai", "anthropic" or "gemini"
    backend: object                     # a harness.endpoints backend


def _known(name: str) -> bool:
    from . import providers
    return name in providers.REGISTRY or name in NATIVE or name in NO_STRUCTURED


def make_backend(name: str, model: str) -> tuple:
    """(dialect, backend) for a gateway endpoint name."""
    from . import endpoints, providers
    if name in NATIVE:
        dialect, base, default = NATIVE[name]
        made = endpoints.AnthropicBackend if dialect == "anthropic" else endpoints.GeminiBackend
        return dialect, made(name=name, base_url=base, model=model or default, timeout=TIMEOUT)
    from .endpoint_registry import _registry_base_url
    spec = providers.REGISTRY[name]
    base, model = _registry_base_url(name, spec), model or spec.default_model
    if not base or not model:
        raise TurnRefused("invalid", f"endpoint {name!r} has no base URL or model configured")
    return "openai", endpoints.OpenAICompatBackend(
        name=name, base_url=base, model=model, key_env=spec.api_key_env, timeout=TIMEOUT)


def resolve_upstream(model: str, environ=None) -> Upstream:
    """The upstream for a client's `model`, or TurnRefused.

    A gateway endpoint name (`anthropic`, `openai:gpt-4o`, `ollama:qwen2.5:1.5b`)
    is used as it is. Any other name goes to the endpoint FLYWHEEL_GATEWAY_UPSTREAM
    names: `provider` keeps the client's model name, `provider:model` replaces it.
    """
    from .provider_fault_boundary import redacted_text
    environ = os.environ if environ is None else environ
    wanted = (model or "").strip()
    name, _, sub = wanted.partition(":")
    if not _known(name):
        target = (environ.get(UPSTREAM_ENV) or "").strip()
        if not target:
            raise TurnRefused("not_found", (
                f"model {redacted_text(wanted, limit=80)!r} is not a gateway endpoint. Name "
                f"one from GET /v1/models, or set {UPSTREAM_ENV} to `provider` or "
                "`provider:model` to send other model names to that endpoint."))
        name, _, forced = target.partition(":")
        sub = forced or wanted
        if not _known(name):
            raise TurnRefused("not_found", f"{UPSTREAM_ENV} names an endpoint the gateway "
                              "does not have; see GET /v1/models")
    if name in NO_STRUCTURED:
        raise TurnRefused("invalid", f"endpoint {name!r} takes one flattened prompt and "
                          "cannot carry tools or structured turns; name an API endpoint")
    dialect, backend = make_backend(name, sub)
    if not backend.health():
        raise TurnRefused("invalid", f"endpoint {name!r} has no credential present; set "
                          "its API key in the environment (presence only, never read here)")
    return Upstream(name, dialect, backend)


def check_results(messages: list) -> None:
    """Refuse a tool result the conversation never asked for."""
    for index, message in enumerate(messages):
        before = messages[index - 1] if index else {}
        asked = ({call["id"] for call in before.get("calls") or []}
                 if before.get("role") == "assistant" else set())
        for result in message.get("results") or []:
            if result["id"] not in asked:
                raise TurnRefused("invalid", (
                    f"messages.{index}: tool_result names a tool_use_id that the assistant "
                    "turn before it did not produce; nothing was sent upstream"))


def _text_form(turn: Turn) -> tuple:
    from .endpoints_tools import canonical
    from .gateway_openai_route import flatten_messages
    rows = [{"role": "system", "content": turn.system}] if turn.system else []
    for message in turn.messages:
        for result in message.get("results") or []:
            rows.append({"role": "tool", "content": result["output"]})
        if message["role"] == "assistant":
            rows.append({"role": "assistant",
                         "content": canonical(message["text"], message.get("calls") or [])})
        elif message["text"] or not message.get("results"):
            rows.append({"role": "user", "content": message["text"]})
    return flatten_messages(rows)


def prompt_sha(turn: Turn) -> str:
    from .proposer import prompt_hash
    return prompt_hash(turn.text_form()[1])


def reply_text(reply: Reply) -> str:
    """The reply as the ledger and the receipt hash it: prose, then TOOL lines."""
    from .endpoints_tools import canonical
    return canonical(reply.text, reply.calls)


def record(ledger, upstream: Upstream, turn: Turn, reply: Reply) -> None:
    """Append the `endpoint_call` entry. A reply with no ledger is not served."""
    from .proposer import prompt_hash
    if ledger is None:
        raise RuntimeError("the gateway ledger is unavailable; the reply was not served")
    from .gateway_key_gate import Bill
    sha, bill = prompt_hash(reply_text(reply)), Bill(turn, reply)
    meta = {"endpoint": upstream.name, "interface": turn.interface,
            "model_ref": reply.model_ref, "seed": 0,
            "prompt_sha": prompt_sha(turn), "response_sha": sha,
            "usage_reported": reply.usage_reported, **bill.meta}
    bill.settle()                       # a call that cannot be charged is not served
    with _APPEND:
        ledger.append("endpoint_call", sha, meta)


def record_failed(ledger, upstream: Upstream, turn: Turn, reason: str, detail="") -> None:
    """Append `endpoint_call_failed` and log why, with secrets scrubbed."""
    from .provider_fault_boundary import redacted_text
    _LOG.warning("gateway %s call to %s failed (%s): %s", turn.interface, upstream.name,
                 reason, redacted_text(str(detail)))
    if ledger is not None:
        from .gateway_key_gate import OWNER
        meta = {"endpoint": upstream.name, "interface": turn.interface,
                "prompt_sha": prompt_sha(turn), "reason": reason,
                **(turn.caller or OWNER).meta}
        with _APPEND:
            ledger.append("endpoint_call_failed", reason, meta)


def receipt(turn: Turn, reply: Reply) -> dict:
    """The receipt the OpenAI-chat path mints, over this turn and reply."""
    from .messages_api import make_receipt
    system, prompt = turn.text_form()
    request = {"prompt": prompt, "system": system, "max_new_tokens": turn.max_tokens,
               "temperature": turn.temperature, "seed": 0}
    gen = {"text": reply_text(reply), "seed": 0, "prompt_hash": prompt_sha(turn),
           "served_model": reply.served_model}
    return make_receipt(request, gen, reply.model_ref)
