"""Codex consumer model catalog to picker roster.

The Codex app-server catalog has two identifiers per row: a catalog id and the
actual model route to pass back to Codex. The picker must emit the route while
preserving the catalog id as provenance. It must not invent an endpoint default
when the catalog is absent, ambiguous, hidden, or duplicated.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .codex_app_server_client import CodexAppServerClient
from .codex_consumer_account import discover_models


def codex_consumer_roster(
        endpoint: str, configured_default: str, *, timeout: float = 3.0,
        client_factory: Callable[..., Any] | None = None) -> dict:
    client = None
    try:
        factory = client_factory or CodexAppServerClient.connect
        client = factory(timeout=timeout)
        discovered = discover_models(client, include_hidden=False)
    except Exception as exc:
        return _empty(endpoint, configured_default,
                      f"listing unavailable: {type(exc).__name__}")
    finally:
        if client is not None:
            close = getattr(client, "close", None)
            if close is not None:
                try:
                    close()
                except Exception:
                    pass
    return _normalize(endpoint, configured_default, discovered)


def _empty(endpoint: str, configured_default: str, reason: str) -> dict:
    return {
        "endpoint": endpoint,
        "provider": "codex",
        "transport": "codex-app-server",
        "models": [],
        "reason": reason,
        "provider_listed_models": [],
        "provider_listed_model_routes": [],
        "default_model_source": "none",
        "default_provider_listed": False,
        "actual_provider_default": None,
        "configured_default_model": configured_default,
        "configured_default_selectable": False,
        "endpoint_default_selectable": False,
        "availability": "unavailable",
        "availability_note": _AVAILABILITY_NOTE,
        "omitted_model_rows": 0,
        "allow_manual": True,
        "listing_authoritative": False,
        "listing_partial": False,
    }


def _normalize(endpoint: str, configured_default: str, discovered: dict) -> dict:
    base = _empty(endpoint, configured_default,
                  _public_text(discovered.get("reason")))
    rows, omitted = _visible_unique_rows(discovered)
    base["omitted_model_rows"] = int(base["omitted_model_rows"]) + omitted
    base["listing_partial"] = discovered.get("listing_partial") is True
    base["provider_listed_models"] = [row["catalog_id"] for row in rows]
    base["provider_listed_model_routes"] = [row["model"] for row in rows]
    base["models"] = rows
    if rows:
        base["availability"] = "provider_catalog_only"
    defaults = [row for row in rows if row.pop("_provider_default", False)]
    warnings = []
    if base["reason"]:
        warnings.append(base["reason"])
    if len(defaults) == 1:
        default = defaults[0]
        default["default"] = "true"
        default["is_default"] = True
        base["default_model_source"] = "provider_catalog"
        base["default_provider_listed"] = True
        base["actual_provider_default"] = {
            "catalog_id": default["catalog_id"],
            "model": default["model"],
        }
    elif len(defaults) > 1:
        warnings.append("provider catalog returned ambiguous default models")
    elif rows:
        warnings.append("provider catalog did not report a default model")
    elif not base["reason"]:
        warnings.append("provider catalog returned no visible models")
    base["reason"] = "; ".join(warnings)
    return base


def _visible_unique_rows(discovered: dict) -> "tuple[list[dict], int]":
    rows = []
    omitted = _safe_int(discovered.get("omitted_model_rows"))
    seen_catalog_ids = set()
    seen_routes = set()
    raw_rows = discovered.get("models") if isinstance(discovered, dict) else []
    for raw in raw_rows if isinstance(raw_rows, list) else []:
        if not isinstance(raw, dict):
            omitted += 1
            continue
        catalog_id = _token(raw.get("id"))
        route = _token(raw.get("model"))
        if not catalog_id or not route or raw.get("hidden") is True:
            omitted += 1
            continue
        if catalog_id in seen_catalog_ids or route in seen_routes:
            omitted += 1
            continue
        seen_catalog_ids.add(catalog_id)
        seen_routes.add(route)
        rows.append(_picker_row(raw, catalog_id, route))
    return rows, omitted


def _picker_row(raw: dict, catalog_id: str, route: str) -> dict:
    return {
        "id": route,
        "model": route,
        "catalog_id": catalog_id,
        "display_name": _public_text(raw.get("display_name")) or catalog_id,
        "description": _public_text(raw.get("description")),
        "default": "false",
        "is_default": False,
        "default_reasoning_effort": _token(raw.get("default_reasoning_effort")),
        "supported_reasoning_efforts": _token_list(
            raw.get("supported_reasoning_efforts")),
        "input_modalities": _token_list(raw.get("input_modalities")),
        "supports_personality": raw.get("supports_personality") is True,
        "service_tiers": [
            tier for tier in raw.get("service_tiers", [])
            if isinstance(tier, dict)
        ],
        "_provider_default": raw.get("is_default") is True,
    }


def _token(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return ""
    return value[:240]


def _public_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = "".join(
        " " if (ch.isspace() or ord(ch) < 32 or ord(ch) == 127) else ch
        for ch in value)
    return " ".join(cleaned.split())[:240]


def _token_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _token(item))]


def _safe_int(value: Any) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


_AVAILABILITY_NOTE = (
    "provider catalog presence is not inference availability or strict tool "
    "capability proof"
)
