"""endpoint_opencode.py -- the OpenCode desktop/server backend.

Extracted from endpoints.py to keep that file under its ceiling. Verified
against OpenCode Desktop 1.17.15 packaged API surface:
  POST /session
  POST /session/{id}/message

The desktop app starts its own password-protected sidecar with a random
password. This backend therefore only activates when the operator exposes a
reachable OpenCode server/sidecar and provides its basic-auth credentials
via env vars.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.parse
from dataclasses import dataclass

from .endpoints_http import _guard, _k, _http
from .local_agent import BackendError


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


