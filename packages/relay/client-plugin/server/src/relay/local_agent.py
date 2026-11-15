"""local_agent.py — the standalone LOCAL agent: the offline / exhaustion tier.

When the subscription or a hosted API is out of usage, this keeps you working
entirely on models running on THIS machine — the trained 14B/32B behind
serve.py, or an Ollama model — with automatic failover between them. It proxies
no hosted account and harvests no session token; it speaks only to local model
servers over localhost.

Design:
  - Backends implement a tiny protocol (name / health / chat). Two ship:
    ServeBackend (serve.py's /generate, the trained 14B/32B) and OllamaBackend
    (Ollama's native /api/chat). Both are health-probed; the router picks the
    first live backend in preference order and fails over on a chat error.
  - Every turn is wrapped through messages_api, so the fallback tier still emits
    a re-checkable per-turn receipt (request ⊕ prompt ⊕ model ⊕ response).
  - Zero runtime deps (stdlib urllib). Transport is injectable, so the router,
    failover, and receipt logic are falsifiable without a GPU or a live server.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

from .messages_api import translate_response

# A transport is (method, url, body_bytes_or_none, timeout) -> (status, parsed_json).
# The default hits the network; tests inject a fake to stay hermetic.
Transport = Callable[[str, str, Optional[bytes], float], "tuple[int, dict]"]

SERVE_URL = "http://127.0.0.1:8765"
OLLAMA_URL = "http://127.0.0.1:11434"


def _http(method: str, url: str, body: Optional[bytes], timeout: float) -> "tuple[int, dict]":
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, (json.loads(raw) if raw else {})
        except json.JSONDecodeError:
            return e.code, {"error": raw.decode("utf-8", "replace")[:200]}


class BackendError(RuntimeError):
    """A backend failed to produce a completion (down, HTTP error, malformed)."""


class Backend(Protocol):
    name: str

    def health(self) -> bool: ...

    def chat(self, messages: list[dict], *, system: str, max_tokens: int,
             temperature: float, seed: int) -> dict: ...


def _flatten(messages: list[dict]) -> str:
    """Conversation -> single prompt (serve.py takes one prompt + system)."""
    return "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}"
                     for m in messages)


@dataclass
class ServeBackend:
    """The trained 14B/32B served by harness/serve.py over /generate."""

    base_url: str = SERVE_URL
    name: str = "serve"
    transport: Transport = _http
    timeout: float = 300.0

    def health(self) -> bool:
        try:
            status, obj = self.transport("GET", f"{self.base_url}/health", None, 5.0)
        except (urllib.error.URLError, OSError, ConnectionError):
            return False
        return status == 200 and bool(obj.get("ok"))

    def chat(self, messages, *, system, max_tokens, temperature, seed) -> dict:
        body = json.dumps({
            "prompt": _flatten(messages), "system": system,
            "max_new_tokens": max_tokens, "temperature": temperature, "seed": seed,
        }).encode()
        try:
            status, obj = self.transport("POST", f"{self.base_url}/generate", body, self.timeout)
        except (urllib.error.URLError, OSError, ConnectionError) as e:
            raise BackendError(f"serve unreachable: {e}") from e
        if status != 200 or "text" not in obj:
            raise BackendError(f"serve returned {status}: {obj.get('error', obj)}")
        gen = {"text": obj["text"], "model_ref": obj.get("model_ref", "serve"),
               "seed": obj.get("seed", seed)}
        if obj.get("prompt_hash"):        # only when served; else make_receipt hashes the prompt
            gen["prompt_hash"] = obj["prompt_hash"]
        return gen


@dataclass
class OllamaBackend:
    """A local Ollama model (qwen2.5 today, any pulled model). Native /api/chat.

    model="" auto-selects the largest pulled model at health time, so the 14B/32B
    become the backend automatically once pulled into Ollama — no code change."""

    base_url: str = OLLAMA_URL
    model: str = ""
    name: str = "ollama"
    transport: Transport = _http
    timeout: float = 300.0
    stream_transport: "Callable" = None      # inject (body_bytes)->iter[dict] for tests
    _resolved: str = field(default="", repr=False)

    def health(self) -> bool:
        try:
            status, obj = self.transport("GET", f"{self.base_url}/api/tags", None, 5.0)
        except (urllib.error.URLError, OSError, ConnectionError):
            return False
        if status != 200:
            return False
        tags = [m.get("name", "") for m in obj.get("models", []) if m.get("name")]
        if not tags:
            return False
        self._resolved = self.model or _prefer_largest(tags)
        return bool(self._resolved)

    def chat(self, messages, *, system, max_tokens, temperature, seed) -> dict:
        model = self._resolved or self.model
        if not model:
            raise BackendError("no ollama model resolved (call health() or pass model=)")
        msgs = ([{"role": "system", "content": system}] if system else []) + messages
        body = json.dumps({
            "model": model, "messages": msgs, "stream": False,
            "options": {"temperature": temperature, "seed": seed,
                        "num_predict": max_tokens},
        }).encode()
        try:
            status, obj = self.transport("POST", f"{self.base_url}/api/chat", body, self.timeout)
        except (urllib.error.URLError, OSError, ConnectionError) as e:
            raise BackendError(f"ollama unreachable: {e}") from e
        text = (obj.get("message") or {}).get("content")
        if status != 200 or text is None:
            raise BackendError(f"ollama returned {status}: {obj.get('error', obj)}")
        gen = {"text": text, "model_ref": f"ollama:{model}", "seed": seed}
        if obj.get("done_reason"):        # "length" -> truncation, surfaced by the receipt
            gen["stop_reason"] = obj["done_reason"]
        return gen

    def _body(self, messages, system, max_tokens, temperature, seed, stream):
        model = self._resolved or self.model
        msgs = ([{"role": "system", "content": system}] if system else []) + messages
        return model, json.dumps({
            "model": model, "messages": msgs, "stream": stream,
            "options": {"temperature": temperature, "seed": seed, "num_predict": max_tokens},
        }).encode()

    def chat_stream(self, messages, *, system, max_tokens, temperature, seed):
        """Yield text chunks as the model produces them (Ollama NDJSON stream).

        A mid-stream error object, or a stream that ends without the done:true
        terminator, is a FAILURE — it raises BackendError rather than being
        silently dropped and the partial text receipted as a finished turn."""
        model = self._resolved or self.model
        if not model:
            raise BackendError("no ollama model resolved (call health() first)")
        _, body = self._body(messages, system, max_tokens, temperature, seed, True)
        done = False
        for chunk in self._iter_stream(body):
            if chunk.get("error"):
                raise BackendError(f"ollama stream error: {chunk['error']}")
            piece = (chunk.get("message") or {}).get("content")
            if piece:
                yield piece
            if chunk.get("done"):
                done = True
                if chunk.get("done_reason") == "length":
                    raise BackendError("ollama stream truncated (num_predict/length)")
        if not done:
            raise BackendError("ollama stream ended without done:true (truncated)")

    def _iter_stream(self, body):
        if self.stream_transport is not None:
            yield from self.stream_transport(body)
            return
        req = urllib.request.Request(f"{self.base_url}/api/chat", data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            for line in r:
                line = line.strip()
                if line:
                    yield json.loads(line)


def _prefer_largest(tags: list[str]) -> str:
    """Pick the biggest model by the NNb tag (32b > 14b > 7b), else the first.
    Keeps the strongest local model as the default backend."""
    def size(name: str) -> float:
        import re
        m = re.search(r"(\d+(?:\.\d+)?)b", name.lower())
        return float(m.group(1)) if m else 0.0
    return sorted(tags, key=size, reverse=True)[0]


def available_backends(*, serve_url: str = SERVE_URL, ollama_url: str = OLLAMA_URL,
                        model: str = "", transport: Transport = _http) -> list[Backend]:
    """The local backends in preference order (trained model first, Ollama next)."""
    return [ServeBackend(base_url=serve_url, transport=transport),
            OllamaBackend(base_url=ollama_url, model=model, transport=transport)]


def select_backend(backends: list[Backend], prefer: str = "auto") -> Optional[Backend]:
    """First healthy backend. prefer names one to force (still health-gated)."""
    ordered = backends
    if prefer != "auto":
        ordered = [b for b in backends if b.name == prefer]
    for b in ordered:
        if b.health():
            return b
    return None


@dataclass
class LocalAgent:
    """A multi-turn local agent with automatic backend failover + per-turn receipts."""

    backends: list[Backend] = field(default_factory=available_backends)
    system: str = ("You are a local coding assistant running offline. Be concise "
                   "and correct. If unsure, say so.")
    prefer: str = "auto"
    max_tokens: int = 512
    temperature: float = 0.0
    seed: int = 0
    history: list[dict] = field(default_factory=list)

    def live_backend(self) -> Optional[Backend]:
        return select_backend(self.backends, self.prefer)

    def _healthy(self) -> list:
        return [b for b in self.backends
                if (self.prefer == "auto" or b.name == self.prefer) and b.health()]

    def _finalize(self, gen: dict, backend_name: str,
                  failover: "list | None" = None) -> dict:
        """Build the receipt for a completion, record the assistant turn, return
        the Anthropic-shaped response. Shared by send() and stream()."""
        req_params = {"prompt": _flatten(self.history), "system": self.system,
                      "max_new_tokens": self.max_tokens, "temperature": self.temperature,
                      "seed": self.seed, "requested_model": gen["model_ref"]}
        resp = translate_response(gen, req_params, gen["model_ref"])
        self.history.append({"role": "assistant", "content": gen["text"]})
        resp["backend"] = backend_name
        if failover:                     # backends that failed before this one won:
            resp["failover"] = failover  # record it so the win does not erase the failure
        return resp

    def send(self, user_text: str) -> dict:
        """One turn. Tries healthy backends in order; the first that returns a
        completion wins. Raises BackendError only if every backend fails."""
        self.history.append({"role": "user", "content": user_text})
        healthy = self._healthy()
        if not healthy:
            raise BackendError("no local backend is healthy (start serve.py or ollama)")
        errors = []
        for b in healthy:
            try:
                gen = b.chat(self.history, system=self.system, max_tokens=self.max_tokens,
                             temperature=self.temperature, seed=self.seed)
            except BackendError as e:
                errors.append(f"{b.name}: {e}")
                continue
            return self._finalize(gen, b.name, failover=errors)
        raise BackendError("all healthy backends failed: " + "; ".join(errors))

    def stream(self, user_text: str, on_chunk) -> dict:
        """One turn, streaming text chunks to `on_chunk` as they arrive. Uses the
        first healthy backend that supports streaming; falls back to send() (whole
        answer as one chunk) if none does. Same receipt as send()."""
        self.history.append({"role": "user", "content": user_text})
        for b in self._healthy():
            stream_fn = getattr(b, "chat_stream", None)
            if stream_fn is None:
                continue
            full = ""
            for piece in stream_fn(self.history, system=self.system, max_tokens=self.max_tokens,
                                   temperature=self.temperature, seed=self.seed):
                full += piece
                on_chunk(piece)
            ref = f"{b.name}:{getattr(b, '_resolved', '') or getattr(b, 'model', '')}".rstrip(":")
            return self._finalize({"text": full, "model_ref": ref, "seed": self.seed}, b.name)
        # no streaming backend: fall back to a normal turn, emit once
        self.history.pop()                       # send() re-appends the user turn
        resp = self.send(user_text)
        on_chunk(resp["content"][0]["text"] if resp.get("content") else "")
        return resp


def health_report(backends: Optional[list[Backend]] = None) -> dict:
    """Which local tiers are live right now — the 'can I keep working offline?' check."""
    bs = backends if backends is not None else available_backends()
    tiers = []
    for b in bs:
        live = b.health()
        argv = getattr(b, "argv", None)
        ref = (getattr(b, "_resolved", "") or getattr(b, "model", "")
               or getattr(b, "base_url", "") or (argv[0] if argv else ""))
        tiers.append({"backend": b.name, "healthy": live, "detail": ref})
    return {"any_live": any(t["healthy"] for t in tiers), "tiers": tiers}
