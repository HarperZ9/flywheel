"""Safe Codex consumer-account normalization.

This layer keeps ChatGPT consumer login, OpenAI API-key routing, and model
catalog discovery as separate facts. It never treats a CLI binary or a provider
catalog row as authenticated inference access.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from .codex_app_server_client import CodexAppServerClient

_OPENAI_KEY_ENV = "OPENAI_API_KEY"
_PLAN_TYPES = {
    "free", "go", "plus", "pro", "prolite", "team",
    "self_serve_business_usage_based", "business",
    "enterprise_cbp_usage_based", "enterprise", "edu", "unknown",
}
_REASONING_EFFORTS = {
    "none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra",
}
_INPUT_MODALITIES = {"text", "image"}
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:sk|sess|pat|rk|pk)-[A-Za-z0-9][A-Za-z0-9._-]{3,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."
               r"[A-Za-z0-9_-]{10,}\b"),
)


def _default_key_source(env_name: str) -> str:
    try:
        from .keychain import credential_source
        return credential_source(env_name)
    except Exception:
        return "absent"


def _public_string(value: Any, *, limit: int = 240) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = "".join(" " if (ch.isspace() or ord(ch) < 32 or ord(ch) == 127)
                      else ch for ch in value)
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub("[redacted]", cleaned)
    return cleaned[:limit]


def _secret_shaped(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SECRET_PATTERNS)


def _route_identity(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return ""
    if _secret_shaped(value):
        return ""
    return value


def _safe_plan(value: Any) -> str:
    return value if isinstance(value, str) and value in _PLAN_TYPES else "unknown"


def _safe_reasoning(value: Any, *, default: str = "") -> str:
    label = _public_string(value, limit=80)
    return label if label in _REASONING_EFFORTS else default


def _key_state(source: str, account: dict | None, *, env_name: str) -> dict:
    if account and account.get("type") == "apiKey":
        return {"state": "present", "source": "codex-app-server:apiKey",
                "env": env_name}
    if source in {"env", "keychain"}:
        return {"state": "present", "source": f"{source}:{env_name}",
                "env": env_name}
    if source == "present":
        return {"state": "present", "source": f"present:{env_name}",
                "env": env_name}
    return {"state": "absent", "source": f"absent:{env_name}",
            "env": env_name}


def _consumer_state(account: dict | None, *, requires_openai_auth: bool) -> dict:
    if not account:
        state = "not_authenticated" if requires_openai_auth else "unknown"
        return {"state": state, "type": None, "plan_type": "unknown",
                "email_present": False}
    kind = account.get("type")
    if kind == "chatgpt":
        return {"state": "authenticated", "type": "chatgpt",
                "plan_type": _safe_plan(account.get("planType")),
                "email_present": bool(account.get("email"))}
    if kind == "apiKey":
        return {"state": "not_consumer_route", "type": "apiKey",
                "plan_type": "unknown", "email_present": False}
    return {"state": "not_consumer_route", "type": _public_string(kind),
            "plan_type": "unknown", "email_present": False}


def read_account_state(
        client: CodexAppServerClient, *, refresh_token: bool = False,
        key_source: Callable[[str], str] | None = None,
        api_key_env: str = _OPENAI_KEY_ENV) -> dict:
    key_source = key_source or _default_key_source
    try:
        response = client.get_account(refresh_token=refresh_token)
    except Exception as exc:
        return {
            "provider": "openai",
            "transport": "codex-app-server",
            "consumer": {"state": "unknown", "type": None,
                         "plan_type": "unknown", "email_present": False},
            "api_key": {"state": "unknown", "source": f"unknown:{api_key_env}",
                        "env": api_key_env},
            "requires_openai_auth": None,
            "effective_auth_source": "unknown",
            "usable_for_codex": False,
            "reason": f"account read unavailable: {type(exc).__name__}",
        }
    response = response if isinstance(response, dict) else {}
    account = response.get("account")
    account = account if isinstance(account, dict) else None
    requires = bool(response.get("requiresOpenaiAuth"))
    api_key = _key_state(key_source(api_key_env), account, env_name=api_key_env)
    consumer = _consumer_state(account, requires_openai_auth=requires)
    if api_key["state"] == "present":
        effective = "api-key"
    elif consumer["state"] == "authenticated":
        effective = "consumer-chatgpt"
    else:
        effective = "none"
    return {
        "provider": "openai",
        "transport": "codex-app-server",
        "consumer": consumer,
        "api_key": api_key,
        "requires_openai_auth": requires,
        "effective_auth_source": effective,
        "usable_for_codex": effective in {"api-key", "consumer-chatgpt"},
        "reason": "" if effective != "none" else "Codex account not authenticated",
    }


def start_managed_login(client: CodexAppServerClient, *, mode: str) -> dict:
    if mode in {"browser", "chatgpt"}:
        response = client.start_chatgpt_login()
        if response.get("type") != "chatgpt":
            raise ValueError("managed browser login returned the wrong type")
        return {"state": "login_started", "mode": "browser",
                "login_id": _public_string(response.get("loginId")),
                "auth_url": _public_string(response.get("authUrl"), limit=2048)}
    if mode in {"device", "device_code", "chatgptDeviceCode"}:
        response = client.start_device_code_login()
        if response.get("type") != "chatgptDeviceCode":
            raise ValueError("managed device-code login returned the wrong type")
        return {"state": "login_started", "mode": "device_code",
                "login_id": _public_string(response.get("loginId")),
                "verification_url": _public_string(
                    response.get("verificationUrl"), limit=2048),
                "user_code": _public_string(response.get("userCode"), limit=80)}
    raise ValueError("managed Codex login supports browser or device_code only")


def cancel_managed_login(client: CodexAppServerClient, login_id: str) -> dict:
    response = client.cancel_login(login_id)
    status = response.get("status") if isinstance(response, dict) else None
    return {"state": _public_string(status) or "unknown"}


def logout_account(client: CodexAppServerClient) -> dict:
    client.logout()
    return {"state": "logout_requested"}


def _model_row(row: dict) -> dict | None:
    model_id = _route_identity(row.get("id"))
    model_route = _route_identity(row.get("model"))
    if not model_id or not model_route:
        return None
    efforts = []
    for item in row.get("supportedReasoningEfforts") or []:
        if isinstance(item, dict):
            effort = _safe_reasoning(item.get("reasoningEffort"))
            if effort:
                efforts.append(effort)
    tiers = []
    for item in row.get("serviceTiers") or []:
        if isinstance(item, dict):
            tiers.append({"id": _public_string(item.get("id"), limit=80),
                          "name": _public_string(item.get("name"), limit=80)})
    return {
        "id": model_id,
        "model": model_route,
        "display_name": _public_string(row.get("displayName"), limit=180),
        "description": _public_string(row.get("description"), limit=500),
        "hidden": bool(row.get("hidden")),
        "is_default": bool(row.get("isDefault")),
        "default_reasoning_effort": _safe_reasoning(
            row.get("defaultReasoningEffort"), default="unknown"),
        "supported_reasoning_efforts": efforts,
        "input_modalities": [x for x in (
            _public_string(item, limit=40)
            for item in row.get("inputModalities") or [])
            if x in _INPUT_MODALITIES],
        "supports_personality": bool(row.get("supportsPersonality")),
        "service_tiers": tiers,
    }


def discover_models(
        client: CodexAppServerClient, *, include_hidden: bool = False,
        page_limit: int = 100, max_pages: int = 10) -> dict:
    models = []
    omitted = 0
    cursor = None
    try:
        for _ in range(max_pages):
            response = client.list_models(
                cursor=cursor, limit=page_limit, include_hidden=include_hidden)
            data = response.get("data") if isinstance(response, dict) else []
            for row in data:
                if not isinstance(row, dict):
                    omitted += 1
                    continue
                model_row = _model_row(row)
                if model_row is None:
                    omitted += 1
                    continue
                models.append(model_row)
            cursor = response.get("nextCursor") if isinstance(response, dict) else None
            if not cursor:
                break
    except Exception as exc:
        return {"provider": "codex", "transport": "codex-app-server",
                "models": [], "omitted_model_rows": omitted,
                "listing_partial": False,
                "reason": f"listing unavailable: {type(exc).__name__}"}
    partial = bool(cursor)
    reason = f"provider catalog truncated after {max_pages} pages" if partial else ""
    return {"provider": "codex", "transport": "codex-app-server",
            "models": models, "omitted_model_rows": omitted,
            "listing_partial": partial, "reason": reason}


def read_model_provider_capabilities(client: CodexAppServerClient) -> dict:
    try:
        response = client.read_model_provider_capabilities()
    except Exception as exc:
        return {"namespace_tools": False, "image_generation": False,
                "web_search": False,
                "reason": f"capability read unavailable: {type(exc).__name__}"}
    response = response if isinstance(response, dict) else {}
    return {"namespace_tools": bool(response.get("namespaceTools")),
            "image_generation": bool(response.get("imageGeneration")),
            "web_search": bool(response.get("webSearch")),
            "reason": ""}


def read_capability_snapshot(
        client: CodexAppServerClient, *,
        key_source: Callable[[str], str] | None = None) -> dict:
    return {
        "account": read_account_state(client, key_source=key_source),
        "capabilities": read_model_provider_capabilities(client),
        "models": discover_models(client),
    }
