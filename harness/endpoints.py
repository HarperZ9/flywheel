"""endpoints.py — the chat-agent's multi-endpoint ladder: reach every provider.

Extends the local agent from local-only to codex / claude / gemini / deepseek,
each in whatever access modes the operator has credentials for, and fails over
across them. Zero-dep (stdlib), and legitimate by construction: keys come from
the environment, subscriptions from the official CLI's own auth, gateways from a
configured base URL. Nothing is forged, harvested, or metered around; a missing
credential just means that endpoint is absent from the ladder.

Modes:
  plan/max : the official CLI (claude/codex) using the operator's subscription
  api      : the provider's public API + <PROVIDER>_API_KEY
  provider : a gateway via <PROVIDER>_PROVIDER_BASE_URL (+ _PROVIDER_KEY)
  cloud    : a cloud OpenAI-compatible endpoint via <PROVIDER>_CLOUD_BASE_URL (+ _CLOUD_KEY)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass

from .local_agent import BackendError


def _http(method, url, headers, body, timeout):
    """(method,url,headers,body,timeout)->(status,json). Injectable for tests."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, (json.loads(raw) if raw else {})
        except json.JSONDecodeError:
            return e.code, {"error": raw.decode("utf-8", "replace")[:300]}


def _k(env_name: str) -> str:
    return os.environ.get(env_name, "")


def _guard(transport, method, url, headers, body, timeout, name):
    try:
        return transport(method, url, headers, body, timeout)
    except (urllib.error.URLError, OSError, ConnectionError) as e:
        raise BackendError(f"{name} unreachable: {e}") from e


@dataclass
class OpenAICompatBackend:
    """OpenAI-compatible /chat/completions: OpenAI (codex api), DeepSeek, a
    provider gateway (OpenRouter), or a cloud gateway."""
    name: str
    base_url: str
    model: str
    key_env: str = ""
    transport: "callable" = _http
    timeout: float = 120.0

    def health(self) -> bool:
        return bool(_k(self.key_env)) if self.key_env else bool(self.base_url)

    def chat(self, messages, *, system, max_tokens, temperature, seed) -> dict:
        msgs = ([{"role": "system", "content": system}] if system else []) + list(messages)
        headers = {"Content-Type": "application/json"}
        if self.key_env and _k(self.key_env):
            headers["Authorization"] = f"Bearer {_k(self.key_env)}"
        body = json.dumps({"model": self.model, "messages": msgs,
                           "temperature": temperature, "max_tokens": max_tokens}).encode()
        status, obj = _guard(self.transport, "POST", f"{self.base_url}/chat/completions",
                             headers, body, self.timeout, self.name)
        try:
            text = obj["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise BackendError(f"{self.name} returned {status}: {obj.get('error', obj)}")
        return {"text": text, "model_ref": f"{self.name}:{self.model}", "seed": seed}


@dataclass
class AnthropicBackend:
    """Anthropic /v1/messages (claude api) — native shape."""
    name: str
    base_url: str
    model: str
    key_env: str = "ANTHROPIC_API_KEY"
    version: str = "2023-06-01"
    transport: "callable" = _http
    timeout: float = 120.0

    def health(self) -> bool:
        return bool(_k(self.key_env))

    def chat(self, messages, *, system, max_tokens, temperature, seed) -> dict:
        headers = {"Content-Type": "application/json", "x-api-key": _k(self.key_env),
                   "anthropic-version": self.version}
        payload = {"model": self.model, "max_tokens": max_tokens, "temperature": temperature,
                   "messages": [{"role": m["role"], "content": m["content"]} for m in messages]}
        if system:
            payload["system"] = system
        status, obj = _guard(self.transport, "POST", f"{self.base_url}/v1/messages",
                             headers, json.dumps(payload).encode(), self.timeout, self.name)
        try:
            text = "".join(b.get("text", "") for b in obj["content"] if b.get("type") == "text")
        except (KeyError, TypeError):
            raise BackendError(f"{self.name} returned {status}: {obj.get('error', obj)}")
        return {"text": text, "model_ref": f"{self.name}:{self.model}", "seed": seed}


@dataclass
class GeminiBackend:
    """Google Gemini :generateContent (api key in the query string, per the API)."""
    name: str
    base_url: str
    model: str
    key_env: str = "GEMINI_API_KEY"
    transport: "callable" = _http
    timeout: float = 120.0

    def health(self) -> bool:
        return bool(_k(self.key_env))

    def chat(self, messages, *, system, max_tokens, temperature, seed) -> dict:
        contents = [{"role": "model" if m["role"] == "assistant" else "user",
                     "parts": [{"text": m["content"]}]} for m in messages]
        payload = {"contents": contents,
                   "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        url = f"{self.base_url}/models/{self.model}:generateContent?key={_k(self.key_env)}"
        status, obj = _guard(self.transport, "POST", url, {"Content-Type": "application/json"},
                             json.dumps(payload).encode(), self.timeout, self.name)
        try:
            text = "".join(p.get("text", "") for p in obj["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            raise BackendError(f"{self.name} returned {status}: {obj.get('error', obj)}")
        return {"text": text, "model_ref": f"{self.name}:{self.model}", "seed": seed}


@dataclass
class CliBackend:
    """A subscription tier via the official CLI's OWN auth (claude max / codex
    plan). It invokes the operator's authenticated client; it never proxies or
    replays that client's tokens elsewhere."""
    name: str
    argv: list                       # {prompt} replaced with the flattened prompt
    runner: "callable" = None        # inject (cmd)->(rc,out,err) for tests
    timeout: float = 300.0

    def health(self) -> bool:
        return bool(self.argv) and shutil.which(self.argv[0]) is not None

    def chat(self, messages, *, system, max_tokens, temperature, seed) -> dict:
        prompt = (system + "\n\n" if system else "") + "\n".join(
            f"{m['role']}: {m['content']}" for m in messages)
        cmd = [prompt if a == "{prompt}" else a for a in self.argv]
        try:
            if self.runner is not None:
                rc, out, err = self.runner(cmd)
            else:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
                rc, out, err = p.returncode, p.stdout, p.stderr
        except (OSError, subprocess.SubprocessError) as e:
            raise BackendError(f"{self.name} cli failed: {e}") from e
        if rc != 0:
            raise BackendError(f"{self.name} cli exit {rc}: {(err or '').strip()[:200]}")
        return {"text": (out or "").strip(), "model_ref": f"{self.name}:cli", "seed": seed}


# provider -> how to reach it. base URLs are the public APIs; models are
# overridable via <PROVIDER>_MODEL. cli is the subscription tier if present.
PROVIDERS = {
    "codex":    {"kind": "openai", "base": "https://api.openai.com/v1",
                 "key": "OPENAI_API_KEY", "model": "gpt-4o",
                 "cli": ["codex", "exec", "{prompt}"]},
    "claude":   {"kind": "anthropic", "base": "https://api.anthropic.com",
                 "key": "ANTHROPIC_API_KEY", "model": "claude-sonnet-4-5",
                 "cli": ["claude", "-p", "{prompt}", "--output-format", "text"]},
    "gemini":   {"kind": "gemini", "base": "https://generativelanguage.googleapis.com/v1beta",
                 "key": "GEMINI_API_KEY", "model": "gemini-2.5-flash"},
    "deepseek": {"kind": "openai", "base": "https://api.deepseek.com/v1",
                 "key": "DEEPSEEK_API_KEY", "model": "deepseek-chat"},
}

_KINDS = {"openai": OpenAICompatBackend, "anthropic": AnthropicBackend, "gemini": GeminiBackend}


def _api_backend(pname: str, spec: dict, base: str, key_env: str):
    model = os.environ.get(f"{pname.upper()}_MODEL", spec["model"])
    return _KINDS[spec["kind"]](name=pname, base_url=base, model=model, key_env=key_env)


def build_endpoints(*, providers=None, modes=("plan", "api", "provider", "cloud"),
                    only_configured: bool = True) -> list:
    """The online ladder: for each provider and mode, a backend if its credential
    is present. `only_configured=False` includes every backend (health gates at
    call time). Order follows `modes` (subscriptions first by default)."""
    names = providers or list(PROVIDERS)
    ladder = []
    for mode in modes:
        for pname in names:
            spec = PROVIDERS.get(pname)
            if spec is None:
                continue
            b = _one(pname, spec, mode)
            if b is not None and (not only_configured or b.health()):
                ladder.append(b)
    return ladder


def _one(pname: str, spec: dict, mode: str):
    up = pname.upper()
    if mode in ("plan", "max"):
        cli = spec.get("cli")
        return CliBackend(name=f"{pname}-{mode}", argv=cli) if cli else None
    if mode == "api":
        return _api_backend(pname, spec, spec["base"], spec["key"])
    if mode == "provider":
        base = os.environ.get(f"{up}_PROVIDER_BASE_URL")
        if not base:
            return None
        key = f"{up}_PROVIDER_KEY" if _k(f"{up}_PROVIDER_KEY") else spec["key"]
        model = os.environ.get(f"{up}_MODEL", spec["model"])
        return OpenAICompatBackend(name=f"{pname}-provider", base_url=base, model=model, key_env=key)
    if mode == "cloud":
        base = os.environ.get(f"{up}_CLOUD_BASE_URL")
        if not base:
            return None
        model = os.environ.get(f"{up}_MODEL", spec["model"])
        return OpenAICompatBackend(name=f"{pname}-cloud", base_url=base, model=model,
                                   key_env=f"{up}_CLOUD_KEY")
    return None
