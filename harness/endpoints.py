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
import base64
import tempfile
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import shlex
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


def _env_prefix(provider_name: str) -> str:
    return provider_name.upper().replace("-", "_")


def _decode(data) -> str:
    if isinstance(data, bytes):
        return data.decode("utf-8", "replace")
    return str(data or "")


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
class OpenCodeBackend:
    """OpenCode desktop/server API.

    Verified against OpenCode Desktop 1.17.15 packaged API surface:
      POST /session
      POST /session/{id}/message

    The desktop app starts its own password-protected sidecar with a random
    password. This backend therefore only activates when the operator exposes a
    reachable OpenCode server/sidecar and provides its basic-auth credentials
    via env vars.
    """
    name: str
    base_url: str
    provider_id: str
    model: str
    username_env: str = "OPENCODE_USERNAME"
    password_env: str = "OPENCODE_PASSWORD"
    username_fallback_env: str = "OPENCODE_SERVER_USERNAME"
    password_fallback_env: str = "OPENCODE_SERVER_PASSWORD"
    directory_env: str = "OPENCODE_DIRECTORY"
    agent_env: str = "OPENCODE_AGENT"
    transport: "callable" = _http
    timeout: float = 300.0

    def health(self) -> bool:
        password = _k(self.password_env) or _k(self.password_fallback_env)
        return bool(self.base_url and self.provider_id and self.model and password)

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        username = _k(self.username_env) or _k(self.username_fallback_env) or "opencode"
        password = _k(self.password_env) or _k(self.password_fallback_env)
        if password:
            token = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {token}"
        return headers

    def _url(self, path: str) -> str:
        base = self.base_url.rstrip("/")
        params = {}
        directory = _k(self.directory_env) or os.getcwd()
        if directory:
            params["directory"] = directory
        qs = urllib.parse.urlencode(params)
        return f"{base}{path}?{qs}" if qs else f"{base}{path}"

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = json.dumps(payload or {}).encode() if payload is not None else None
        status, obj = _guard(
            self.transport,
            method,
            self._url(path),
            self._headers(),
            body,
            self.timeout,
            self.name,
        )
        if status >= 400:
            raise BackendError(f"{self.name} returned {status}: {obj.get('error', obj)}")
        return obj

    def _collect_text(self, obj) -> list[str]:
        found = []
        if isinstance(obj, dict):
            if obj.get("type") == "text" and isinstance(obj.get("text"), str):
                found.append(obj["text"])
            for value in obj.values():
                found.extend(self._collect_text(value))
        elif isinstance(obj, list):
            for value in obj:
                found.extend(self._collect_text(value))
        return found

    def _latest_assistant_text(self, session_id: str) -> str:
        obj = self._request("GET", f"/session/{urllib.parse.quote(session_id)}/message")
        messages = obj if isinstance(obj, list) else obj.get("messages", [])
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("info", {}).get("role") == "assistant":
                text = "\n".join(self._collect_text(message)).strip()
                if text:
                    return text
        return ""

    def chat(self, messages, *, system, max_tokens, temperature, seed) -> dict:
        del max_tokens, temperature
        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        session = self._request("POST", "/session", {})
        session_id = session.get("id") or session.get("sessionID") or session.get("info", {}).get("id")
        if not session_id:
            raise BackendError(f"{self.name} did not return a session id")

        payload = {
            "model": {"providerID": self.provider_id, "modelID": self.model},
            "parts": [{"type": "text", "text": prompt}],
        }
        if system:
            payload["system"] = system
        agent = _k(self.agent_env)
        if agent:
            payload["agent"] = agent

        obj = self._request("POST", f"/session/{urllib.parse.quote(session_id)}/message", payload)
        text = "\n".join(self._collect_text(obj)).strip()
        if not text:
            text = self._latest_assistant_text(session_id)
        if not text:
            raise BackendError(f"{self.name} returned no assistant text")
        return {"text": text, "model_ref": f"{self.name}:{self.provider_id}/{self.model}", "seed": seed}


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


def _one(pname: str, spec: dict, mode: str):
    up = _env_prefix(pname)
    model = os.environ.get(f"{up}_MODEL", spec.get("model", ""))
    if mode in ("plan", "max"):
        if spec.get("kind") == "opencode":
            model = os.environ.get(f"{up}_MODEL") or os.environ.get("OPENCODE_MODEL") or model
            port = os.environ.get(f"{up}_PORT") or os.environ.get("OPENCODE_PORT", "")
            base = (
                os.environ.get(f"{up}_BASE_URL")
                or os.environ.get("OPENCODE_BASE_URL", "")
                or (f"http://127.0.0.1:{port}" if port else "")
            )
            provider_id = (
                os.environ.get(f"{up}_PROVIDER_ID")
                or os.environ.get("OPENCODE_PROVIDER_ID")
                or "openai"
            )
            password_env = f"{up}_PASSWORD" if _k(f"{up}_PASSWORD") else "OPENCODE_PASSWORD"
            username_env = f"{up}_USERNAME" if _k(f"{up}_USERNAME") else "OPENCODE_USERNAME"
            password_fallback_env = (
                f"{up}_SERVER_PASSWORD"
                if _k(f"{up}_SERVER_PASSWORD")
                else "OPENCODE_SERVER_PASSWORD"
            )
            username_fallback_env = (
                f"{up}_SERVER_USERNAME"
                if _k(f"{up}_SERVER_USERNAME")
                else "OPENCODE_SERVER_USERNAME"
            )
            directory_env = f"{up}_DIRECTORY" if _k(f"{up}_DIRECTORY") else "OPENCODE_DIRECTORY"
            agent_env = f"{up}_AGENT" if _k(f"{up}_AGENT") else "OPENCODE_AGENT"
            if base:
                return OpenCodeBackend(
                    name=f"{pname}-{mode}",
                    base_url=base,
                    provider_id=provider_id,
                    model=model,
                    username_env=username_env,
                    password_env=password_env,
                    username_fallback_env=username_fallback_env,
                    password_fallback_env=password_fallback_env,
                    directory_env=directory_env,
                    agent_env=agent_env,
                )
            argv = _resolve_cli_command(spec, pname)
            return CliBackend(name=f"{pname}-{mode}", argv=argv, model=model) if argv else None
        if spec.get("kind") == "cli":
            argv = _resolve_cli_command(spec, pname)
            return CliBackend(name=f"{pname}-{mode}", argv=argv, model=model) if argv else None
        cli = _resolve_cli_command(spec, pname)
        return CliBackend(name=f"{pname}-{mode}", argv=cli, model=model) if cli else None
    if mode == "api":
        if spec.get("kind") not in _KINDS:
            return None
        return _api_backend(pname, spec, spec["base"], spec["key"])
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
