"""Multi-endpoint chat ladder with injectable transports and credentials."""
from __future__ import annotations

import json
import os
import base64
import tempfile
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import shlex
from dataclasses import dataclass, field

from .local_agent import BackendError
from .endpoints_http import _http, _guard, _k
from .endpoint_opencode import OpenCodeBackend  # noqa: F401 (re-exported)


def _credential(env_name: str, direct: str | None) -> str:
    return _k(env_name) if direct is None else direct


def _env_prefix(provider_name: str) -> str:
    return provider_name.upper().replace("-", "_")


def _decode(data) -> str:
    if isinstance(data, bytes):
        return data.decode("utf-8", "replace")
    return str(data or "")


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
    api_key: str | None = field(default=None, repr=False)
    tools: list | None = None
    tool_choice: "str | dict | None" = None

    def health(self) -> bool:
        return bool(_credential(self.key_env, self.api_key)) \
            if self.key_env else bool(self.base_url)

    def chat(self, messages, *, system, max_tokens, temperature, seed) -> dict:
        msgs = ([{"role": "system", "content": system}] if system else []) + list(messages)
        headers = {"Content-Type": "application/json"}
        key = _credential(self.key_env, self.api_key)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload = {"model": self.model, "messages": msgs,
                   "temperature": temperature, "max_tokens": max_tokens}
        if self.tools:
            payload["tools"] = self.tools
            if self.tool_choice is not None:
                payload["tool_choice"] = self.tool_choice
        status, obj = _guard(self.transport, "POST",
                             f"{self.base_url}/chat/completions",
                             headers, json.dumps(payload).encode(),
                             self.timeout, self.name)
        try:
            message = obj["choices"][0]["message"]
            text = message["content"]
        except (KeyError, IndexError, TypeError):
            raise BackendError(f"{self.name} returned {status}: {obj.get('error', obj)}")
        out = {"model_ref": f"{self.name}:{self.model}", "seed": seed}
        calls = message.get("tool_calls") if isinstance(message, dict) else None
        if isinstance(calls, list) and calls:
            out["tool_calls"] = [_parse_tool_call(c) for c in calls]
        if not isinstance(text, str) or not text.strip():
            if out.get("tool_calls"):
                text = ""          # a pure tool-call turn carries no prose
            else:
                # A 200 with content: null (a reasoning model that spent
                # its whole budget) is refusal-shaped, not an empty reply.
                raise BackendError(
                    f"{self.name} returned {status} with no message content")
        out["text"] = text
        return out


def _parse_tool_call(call: dict) -> dict:
    """One native tool call, parsed strictly: malformed JSON arguments are
    reported, never silently executed with guessed arguments."""
    fn = call.get("function") if isinstance(call, dict) else None
    name = fn.get("name", "") if isinstance(fn, dict) else ""
    raw = fn.get("arguments", "{}") if isinstance(fn, dict) else "{}"
    parsed: dict = {}
    error = ""
    if isinstance(raw, dict):
        parsed = raw
    else:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                parsed = loaded
            else:
                error = "arguments are not a JSON object"
        except (json.JSONDecodeError, TypeError):
            error = "arguments are not parseable JSON"
    out = {"id": call.get("id", ""), "name": name, "arguments": parsed}
    if error:
        out["arguments_error"] = error
    return out


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
    api_key: str | None = field(default=None, repr=False)

    def health(self) -> bool:
        return bool(_credential(self.key_env, self.api_key))

    def chat(self, messages, *, system, max_tokens, temperature, seed) -> dict:
        headers = {"Content-Type": "application/json",
                   "x-api-key": _credential(self.key_env, self.api_key),
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
    """Google Gemini :generateContent. The API key travels in the x-goog-api-key
    HEADER, never the URL query string -- a query-string key leaks into access
    logs, proxy logs, and browser history; the header does not. (Gemini accepts
    both; the header is the non-leaking form.)"""
    name: str
    base_url: str
    model: str
    key_env: str = "GEMINI_API_KEY"
    transport: "callable" = _http
    timeout: float = 120.0
    api_key: str | None = field(default=None, repr=False)

    def health(self) -> bool:
        return bool(_credential(self.key_env, self.api_key))

    def chat(self, messages, *, system, max_tokens, temperature, seed) -> dict:
        contents = [{"role": "model" if m["role"] == "assistant" else "user",
                     "parts": [{"text": m["content"]}]} for m in messages]
        payload = {"contents": contents,
                   "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        url = f"{self.base_url}/models/{self.model}:generateContent"
        headers = {"Content-Type": "application/json",
                   "x-goog-api-key": _credential(self.key_env, self.api_key)}
        status, obj = _guard(self.transport, "POST", url, headers,
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
    model: str = ""
    runner: "callable" = None        # inject (cmd)->(rc,out,err) for tests
    timeout: float = 300.0

    def health(self) -> bool:
        return bool(self.argv) and shutil.which(self.argv[0]) is not None

    def chat(self, messages, *, system, max_tokens, temperature, seed) -> dict:
        prompt = (system + "\n\n" if system else "") + "\n".join(
            f"{m['role']}: {m['content']}" for m in messages)
        output_path = ""
        if any(a == "{output}" for a in self.argv):
            fd, output_path = tempfile.mkstemp(prefix=f"{self.name}-", suffix=".txt")
            os.close(fd)
        replacements = {
            "{prompt}": prompt,
            "{model}": self.model,
            "{max_tokens}": str(max_tokens),
            "{temperature}": str(temperature),
            "{output}": output_path,
        }
        cmd = [replacements.get(a, a) for a in self.argv]
        try:
            if self.runner is not None:
                rc, out, err = self.runner(cmd)
            else:
                p = subprocess.run(cmd, capture_output=True, timeout=self.timeout)
                rc, out, err = p.returncode, p.stdout, p.stderr
        except (OSError, subprocess.SubprocessError) as e:
            raise BackendError(f"{self.name} cli failed: {e}") from e
        if rc != 0:
            detail = _decode(err).strip() or _decode(out).strip()
            raise BackendError(
                f"{self.name} cli exit {rc}: {detail[:200]}")
        text = ""
        if output_path and os.path.exists(output_path):
            try:
                text = open(output_path, "r", encoding="utf-8", errors="replace").read().strip()
            finally:
                try:
                    os.unlink(output_path)
                except OSError:
                    pass
        if not text:
            text = _decode(out).strip()
        return {"text": text, "model_ref": f"{self.name}:{self.model or 'cli'}", "seed": seed}


def _resolve_cli_command(spec: dict, pname: str):
    """Resolve provider CLI command from list-like spec or env-var placeholder."""
    env_cli = os.environ.get(f"{_env_prefix(pname)}_CLI", "")
    if env_cli:
        return shlex.split(env_cli)
    cli = spec.get("cli")
    if isinstance(cli, str):
        if cli.endswith("_CLI"):
            cli = os.environ.get(cli, "")
        if not cli:
            return None
        return shlex.split(cli)
    if not cli:
        return None
    if isinstance(cli, (list, tuple)):
        if cli[0] == "codex":
            return ["codex.cmd", *cli[1:]]
        if pname == "codex" and cli[0].lower() == "codex.cmd":
            return list(cli)
        if os.name == "nt" and cli[0] == "claude":
            return ["claude.exe", *cli[1:]]
        if pname == "claude" and os.name == "nt" and cli[0].lower() == "claude.exe":
            return list(cli)
        return list(cli)
    return None


# provider -> how to reach it. base URLs are the public APIs; models are
# overridable via <PROVIDER>_MODEL. cli is the subscription tier if present.
PROVIDERS = {
    "codex":    {"kind": "openai", "base": "https://api.openai.com/v1",
                 "key": "OPENAI_API_KEY", "model": "gpt-5.3-codex-spark",
                 "cli": [
                     "codex", "exec",
                     "--model", "{model}",
                     "--sandbox", "read-only",
                     "--skip-git-repo-check",
                     "--ephemeral",
                     "--output-last-message", "{output}",
                     "{prompt}",
                 ]},
    "claude":   {"kind": "anthropic", "base": "https://api.anthropic.com",
                 "key": "ANTHROPIC_API_KEY", "model": "claude-sonnet-4-5",
                 "cli": [
                     "claude", "-p", "{prompt}",
                     "--model", "{model}",
                     "--effort", "xhigh",
                     "--permission-mode", "dontAsk",
                     "--no-session-persistence",
                     "--output-format", "text",
                 ]},
    "opencode": {"kind": "opencode", "base": "", "key": "", "model": "gpt-5.3-codex-spark",
                 "cli": "OPEN_CODE_CLI"},
    "open-code": {"kind": "opencode", "base": "", "key": "", "model": "gpt-5.3-codex-spark",
                  "cli": "OPEN_CODE_CLI"},
    "glm":      {"kind": "openai", "base": "https://open.bigmodel.cn/api/paas/v4",
                 "key": "GLM_API_KEY", "model": "glm-4.6"},
    "gemini":   {"kind": "gemini", "base": "https://generativelanguage.googleapis.com/v1beta",
                 "key": "GEMINI_API_KEY", "model": "gemini-2.5-flash"},
    "deepseek": {"kind": "openai", "base": "https://api.deepseek.com/v1",
                 "key": "DEEPSEEK_API_KEY", "model": "deepseek-chat"},
    # ox-alpha: OpenRouter's stealth reasoning model (slug stealth/ox-alpha,
    # OpenAI-compatible, 1M context, tool calling). Dormant until
    # OX_ALPHA_API_KEY is set, so an unconfigured slot can never dispatch.
    "ox-alpha": {"kind": "openai", "base": "https://openrouter.ai/api/v1",
                 "key": "OX_ALPHA_API_KEY", "model": "stealth/ox-alpha"},
}

_KINDS = {"openai": OpenAICompatBackend, "anthropic": AnthropicBackend, "gemini": GeminiBackend}


def _api_backend(pname: str, spec: dict, base: str, key_env: str):
    model = os.environ.get(f"{_env_prefix(pname)}_MODEL", spec["model"])
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


def _opencode_plan(pname: str, spec: dict, mode: str, up: str, model: str):
    model = os.environ.get(f"{up}_MODEL") or os.environ.get("OPENCODE_MODEL") or model
    port = os.environ.get(f"{up}_PORT") or os.environ.get("OPENCODE_PORT", "")
    base = (os.environ.get(f"{up}_BASE_URL")
            or os.environ.get("OPENCODE_BASE_URL", "")
            or (f"http://127.0.0.1:{port}" if port else ""))
    provider_id = (os.environ.get(f"{up}_PROVIDER_ID")
                   or os.environ.get("OPENCODE_PROVIDER_ID") or "openai")

    def alias(suffix, fallback):
        name = f"{up}_{suffix}"
        return name if _k(name) else fallback

    if base:
        return OpenCodeBackend(
            name=f"{pname}-{mode}", base_url=base, provider_id=provider_id,
            model=model, username_env=alias("USERNAME", "OPENCODE_USERNAME"),
            password_env=alias("PASSWORD", "OPENCODE_PASSWORD"),
            username_fallback_env=alias(
                "SERVER_USERNAME", "OPENCODE_SERVER_USERNAME"),
            password_fallback_env=alias(
                "SERVER_PASSWORD", "OPENCODE_SERVER_PASSWORD"),
            directory_env=alias("DIRECTORY", "OPENCODE_DIRECTORY"),
            agent_env=alias("AGENT", "OPENCODE_AGENT"))
    argv = _resolve_cli_command(spec, pname)
    return CliBackend(name=f"{pname}-{mode}", argv=argv, model=model) if argv else None


def _one(pname: str, spec: dict, mode: str):
    up = _env_prefix(pname)
    model = os.environ.get(f"{up}_MODEL", spec.get("model", ""))
    if mode in ("plan", "max"):
        if spec.get("kind") == "opencode":
            return _opencode_plan(pname, spec, mode, up, model)
        if spec.get("kind") == "cli":
            argv = _resolve_cli_command(spec, pname)
            return CliBackend(name=f"{pname}-{mode}", argv=argv, model=model) if argv else None
        cli = _resolve_cli_command(spec, pname)
        return CliBackend(name=f"{pname}-{mode}", argv=cli, model=model) if cli else None
    if mode == "api":
        if spec.get("kind") not in _KINDS:
            return None
        base = os.environ.get(f"{up}_BASE_URL", spec.get("base", ""))
        if not base:
            return None          # env-routed slot with no host: dormant
        return _api_backend(pname, spec, base, spec["key"])
    if mode == "provider":
        if spec.get("kind") != "openai":
            return None
        base = os.environ.get(f"{up}_PROVIDER_BASE_URL")
        if not base:
            return None
        key = f"{up}_PROVIDER_KEY" if _k(f"{up}_PROVIDER_KEY") else spec["key"]
        model = os.environ.get(f"{up}_MODEL", spec["model"])
        return OpenAICompatBackend(name=f"{pname}-provider", base_url=base, model=model, key_env=key)
    if mode == "cloud":
        if spec.get("kind") != "openai":
            return None
        base = os.environ.get(f"{up}_CLOUD_BASE_URL")
        if not base:
            return None
        model = os.environ.get(f"{up}_MODEL", spec["model"])
        return OpenAICompatBackend(name=f"{pname}-cloud", base_url=base, model=model,
                                   key_env=f"{up}_CLOUD_KEY")
    return None
