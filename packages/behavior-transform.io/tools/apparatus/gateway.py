"""Universal Model Gateway.

Applies the full apparatus to any LLM endpoint. The same truth injection,
vocabulary calibration, and demodulation pipeline wraps every backend.

Supported backends: anthropic, openai, gemini, ollama, generic (any
OpenAI-compatible endpoint via base URL).
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.request
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from inference_loop import LoopResult


@dataclass
class BackendConfig:
    name: str
    base_url: str
    api_key_env: str
    chat_path: str = "/v1/messages"
    auth_header: str = "x-api-key"

    @property
    def api_key(self) -> str:
        return os.environ.get(self.api_key_env, "")

    @property
    def chat_url(self) -> str:
        return self.base_url.rstrip("/") + self.chat_path


BACKENDS: dict[str, BackendConfig] = {
    "anthropic": BackendConfig(
        name="anthropic",
        base_url=os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
        api_key_env="ANTHROPIC_API_KEY",
        chat_path="/v1/messages",
        auth_header="x-api-key",
    ),
    "openai": BackendConfig(
        name="openai",
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com"),
        api_key_env="OPENAI_API_KEY",
        chat_path="/v1/chat/completions",
        auth_header="Authorization",
    ),
    "gemini": BackendConfig(
        name="gemini",
        base_url=os.environ.get("GOOGLE_AI_BASE_URL", "https://generativelanguage.googleapis.com"),
        api_key_env="GOOGLE_API_KEY",
        chat_path="/v1beta/models/{model}:generateContent",
        auth_header="x-goog-api-key",
    ),
    "ollama": BackendConfig(
        name="ollama",
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        api_key_env="",
        chat_path="/api/chat",
        auth_header="",
    ),
}


class ModelGateway:
    """Apparatus-governed model gateway. Same pipeline, any backend."""

    def __init__(self, backend: str = "anthropic") -> None:
        if backend not in BACKENDS and not backend.startswith("http"):
            raise ValueError(f"Unknown backend '{backend}'. Known: {list(BACKENDS)}")
        if backend.startswith("http"):
            self._cfg = BackendConfig(
                name="generic",
                base_url=backend,
                api_key_env="GENERIC_API_KEY",
                chat_path="/v1/chat/completions",
                auth_header="Authorization",
            )
        else:
            self._cfg = BACKENDS[backend]

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a chat request through the apparatus pipeline."""
        request_id = uuid4().hex[:12]
        narrative = _active_narrative()
        effective_system = (
            f"{narrative}\n\n{system}" if system else narrative
        ) or system

        calibrated_messages = _calibrate(messages, request_id=request_id)
        payload = self._build_payload(model, calibrated_messages, effective_system, **kwargs)
        raw_response = self._send(payload)
        return _demodulate_response(raw_response, request_id=request_id)

    def _build_payload(
        self,
        model: str,
        messages: list[dict],
        system: str | None,
        **kwargs: Any,
    ) -> bytes:
        data: dict[str, Any] = {"model": model, "messages": messages, **kwargs}
        if system:
            data["system"] = system
        return json.dumps(data, ensure_ascii=False).encode("utf-8")

    def _send(self, payload: bytes) -> dict[str, Any]:
        url = self._cfg.chat_url
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Content-Length", str(len(payload)))
        if self._cfg.api_key and self._cfg.auth_header:
            if self._cfg.auth_header == "Authorization":
                req.add_header("Authorization", f"Bearer {self._cfg.api_key}")
            else:
                req.add_header(self._cfg.auth_header, self._cfg.api_key)

        ctx = ssl.create_default_context() if url.startswith("https") else None
        kwargs: dict[str, Any] = {"timeout": 180}
        if ctx:
            kwargs["context"] = ctx
        with urllib.request.urlopen(req, **kwargs) as resp:
            return json.loads(resp.read().decode("utf-8"))


    def chat_with_recovery(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None = None,
        *,
        max_level: int = 5,
        **kwargs: Any,
    ) -> "LoopResult":
        """Chat with automatic refusal recovery and hedge enforcement."""
        from inference_loop import InferenceLoop

        def send_fn(sys_prompt, msgs):
            resp = self.chat(model, msgs, system=sys_prompt, **kwargs)
            for block in resp.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    return block.get("text", "")
            for choice in resp.get("choices", []):
                msg = choice.get("message", {})
                if isinstance(msg.get("content"), str):
                    return msg["content"]
            return ""

        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    user_text = content
                    break

        loop = InferenceLoop(send_fn, max_level=max_level)
        return loop.run(
            user_text, messages[:-1] if messages else [], system=system,
        )


def _active_narrative() -> str:
    try:
        from ..truth_profile import render_truth_context
        return render_truth_context()
    except Exception:
        return ""


def _calibrate(messages: list[dict], *, request_id: str = "") -> list[dict]:
    try:
        from ..vocab_backend import apply_patterns, build_patterns, load_vocab_backend
        patterns = build_patterns(load_vocab_backend())
        out = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str):
                calibrated, _ = apply_patterns(content, patterns)
                out.append({**msg, "content": calibrated})
            else:
                out.append(msg)
        if request_id:
            _register_calibration(messages, request_id)
        return out
    except Exception:
        return messages


def _register_calibration(messages: list[dict], request_id: str) -> None:
    """Register calibration context so the response demodulator can reverse it."""
    try:
        from ..response_demodulator import register_modulation_for_request
        from ..categories import classify
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    result = classify(content)
                    register_modulation_for_request(request_id, result)
                    return
    except Exception:
        pass


def _demodulate_response(data: dict, *, request_id: str = "") -> dict:
    try:
        from ..response_demodulator import demodulate_response as _demod
        for block in data.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                result = _demod(block.get("text", ""), request_id)
                block["text"] = result.demodulated_response
        for choice in data.get("choices", []):
            msg = choice.get("message", {})
            if isinstance(msg.get("content"), str):
                result = _demod(msg["content"], request_id)
                msg["content"] = result.demodulated_response
    except Exception:
        pass
    return data


def gateway_status() -> dict[str, object]:
    return {
        name: {
            "base_url": cfg.base_url,
            "key_configured": bool(cfg.api_key),
            "proxy_active": name == "anthropic" and cfg.base_url != "https://api.anthropic.com",
        }
        for name, cfg in BACKENDS.items()
    }
