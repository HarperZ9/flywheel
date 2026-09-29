"""Explicit live-usage endpoint resolution.

The live sampler observes a selected local runtime; it does not discover one by
enumerating provider defaults. A registry default URL is allowed only after the
caller names the endpoint explicitly.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from typing import Any

_ENDPOINT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,159}\Z")
_SUPPORTED = frozenset(("vllm", "llamacpp"))


@dataclass(frozen=True)
class EndpointTelemetry:
    endpoint: str
    model: str
    base_url: str
    source: str


def _first(values: dict[str, list[str]], key: str) -> str:
    raw = values.get(key, [""])
    value = raw[0] if raw else ""
    return str(value or "").strip()


def _query(qs: Any) -> dict[str, list[str]]:
    if isinstance(qs, dict):
        out: dict[str, list[str]] = {}
        for key, value in qs.items():
            if isinstance(value, list):
                out[str(key)] = [str(v) for v in value[:1]]
            else:
                out[str(key)] = [str(value)]
        return out
    raw = str(qs or "")
    if len(raw) > 1024:
        return {}
    try:
        return urllib.parse.parse_qs(raw, keep_blank_values=False,
                                     max_num_fields=8)
    except ValueError:
        return {}


def _safe_endpoint(endpoint: str) -> str:
    return endpoint if _ENDPOINT.fullmatch(endpoint) else "unsupported"


def _safe_model(model: str, fallback: str = "") -> str:
    return model if _MODEL.fullmatch(model) else fallback


def _context_value(context: Any, key: str) -> str:
    if not isinstance(context, dict):
        return ""
    return str(context.get(key, "") or "").strip()


def resolve_usage_live_endpoints(qs: Any, context: Any = None) -> list[EndpointTelemetry]:
    query = _query(qs)
    endpoint = _first(query, "endpoint") or _context_value(context, "endpoint")
    if not endpoint:
        return []
    endpoint = _safe_endpoint(endpoint)
    model = _first(query, "model") or _context_value(context, "model")
    base_url = _first(query, "base_url") or _context_value(context, "base_url")
    if endpoint not in _SUPPORTED:
        return [EndpointTelemetry(endpoint, _safe_model(model), base_url,
                                  "query.unsupported_endpoint")]
    if base_url:
        return [EndpointTelemetry(endpoint, _safe_model(model), base_url,
                                  "query.explicit_base_url")]
    try:
        from . import providers
        spec = providers.REGISTRY.get(endpoint)
        if spec is None:
            return [EndpointTelemetry(endpoint, _safe_model(model), "",
                                      "query.endpoint_default_missing")]
        return [EndpointTelemetry(
            endpoint, _safe_model(model, spec.default_model), spec.base_url,
            "query.endpoint_default_url")]
    except Exception:
        return [EndpointTelemetry(endpoint, _safe_model(model), "",
                                  "query.endpoint_default_unavailable")]
