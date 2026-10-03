"""Per-provider capture adapters. capture(provider, request, response) is the one entry.

Each adapter reads only fields its provider documents, plus a field map that
names the source and confidence for every path it reads.
"""
from __future__ import annotations

from . import anthropic, deepseek, gemini, mistral, ollama, openai
from ._common import Capture

ADAPTERS = {
    "anthropic": anthropic.capture,
    "openai": openai.capture,
    "xai": openai.capture_xai,
    "google": gemini.capture,
    "deepseek": deepseek.capture,
    "mistral": mistral.capture,
    "ollama": ollama.capture,
}
CLOSED = ("anthropic", "openai", "xai", "google")
OPEN_WEIGHT_LOCAL = ("ollama",)


def capture(provider: str, request: dict, response: dict, *, run_id: str,
            turn_index: int = 0) -> Capture:
    if provider not in ADAPTERS:
        raise ValueError(f"no capture adapter for provider {provider!r}; known: {sorted(ADAPTERS)}")
    if not isinstance(response, dict):
        raise ValueError("capture: response must be the decoded JSON object the caller received")
    return ADAPTERS[provider](request or {}, response, run_id=run_id, turn_index=turn_index)


__all__ = ["ADAPTERS", "CLOSED", "OPEN_WEIGHT_LOCAL", "Capture", "capture"]
