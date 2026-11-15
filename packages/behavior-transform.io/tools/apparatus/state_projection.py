"""Carrier-state projection with sealed local reconstitution.

Projects source values into carrier tokens while keeping the symbol
table local. The model sees opaque tokens; reconstitution happens
on the return leg using the sealed local context.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable


_TOKEN = "__STATE_{:04d}__"
_SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b[A-Fa-f0-9]{32,}\b"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"https?://[^\s\"'<>]+"),
    re.compile(r"\b[A-Za-z]:\\[^\s\"'<>]+"),
    re.compile(r"(?<!\w)/(?:[A-Za-z0-9._-]+/)+[A-Za-z0-9._-]+"),
)


@dataclass(frozen=True)
class StateProjection:
    carrier_text: str
    carrier_payload: Any
    symbols: dict[str, str]
    source_hash: str

    def to_dict(self, *, include_symbols: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "projection_mode": "carrier_state",
            "symbol_scope": "sealed_local",
            "source_hash": self.source_hash,
            "symbol_count": len(self.symbols),
            "carrier_text": self.carrier_text,
            "carrier_payload": self.carrier_payload,
        }
        if include_symbols:
            payload["symbols"] = dict(self.symbols)
        return payload


class StateProjector:
    """Project source values into carrier tokens while keeping symbols local."""

    def __init__(self, *, default_level: str = "full") -> None:
        self.default_level = projection_level(default_level)

    def project(
        self,
        *,
        text: str = "",
        payload: Any = None,
        level: str | None = None,
    ) -> StateProjection:
        selected = projection_level(level or self.default_level)
        symbols: dict[str, str] = {}
        reverse: dict[str, str] = {}

        def token_for(raw: str) -> str:
            if raw in reverse:
                return reverse[raw]
            token = _TOKEN.format(len(reverse) + 1)
            reverse[raw] = token
            symbols[token] = raw
            return token

        carrier_text = self._project_text(text, token_for, selected)
        carrier_payload = self._project_payload(payload, token_for, selected)
        return StateProjection(
            carrier_text=carrier_text,
            carrier_payload=carrier_payload,
            symbols=symbols,
            source_hash=hash_json({"text": text, "payload": payload}),
        )

    def reconstitute(self, value: Any, symbols: dict[str, str]) -> Any:
        if isinstance(value, str):
            return self.reconstitute_text(value, symbols)
        if isinstance(value, list):
            return [self.reconstitute(item, symbols) for item in value]
        if isinstance(value, dict):
            return {key: self.reconstitute(item, symbols) for key, item in value.items()}
        return value

    def reconstitute_text(self, text: str, symbols: dict[str, str]) -> str:
        result = text
        for token, raw in sorted(symbols.items(), key=lambda item: len(item[0]), reverse=True):
            result = result.replace(token, raw)
        return result

    def _project_payload(
        self,
        value: Any,
        token_for: Callable[[str], str],
        level: str,
    ) -> Any:
        if isinstance(value, str):
            return self._project_text(value, token_for, level)
        if isinstance(value, list):
            return [self._project_payload(item, token_for, level) for item in value]
        if isinstance(value, dict):
            return {
                key: self._project_payload(item, token_for, level)
                for key, item in value.items()
            }
        return value

    def _project_text(
        self,
        text: str,
        token_for: Callable[[str], str],
        level: str,
    ) -> str:
        if not text:
            return text
        if level == "full":
            return token_for(text)
        spans = _sensitive_spans(text)
        if not spans:
            return text
        output: list[str] = []
        cursor = 0
        for start, end in spans:
            output.append(text[cursor:start])
            output.append(token_for(text[start:end]))
            cursor = end
        output.append(text[cursor:])
        return "".join(output)


def _sensitive_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for pattern in _SENSITIVE_PATTERNS:
        for match in pattern.finditer(text):
            span = match.span()
            if any(not (span[1] <= start or span[0] >= end) for start, end in spans):
                continue
            spans.append(span)
    return sorted(spans)


def projection_level(level: str) -> str:
    if level not in {"full", "sensitive"}:
        raise ValueError("projection level must be 'full' or 'sensitive'")
    return level


def hash_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
