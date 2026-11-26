"""Unified fail-closed provider router and AVTR-4R execution planner for Rowan.

Unifies three endpoint classes behind one deterministic, receipted surface:
1. local: ollama, llama.cpp, vllm, or local GGUF runtimes (e.g. jfc3p-7b-oracle-v1)
2. subscription: OAuth/session-backed host adapters (oauth_signin, acp, codex_cli, claude_code)
3. api: key-backed API endpoints (openai_compat, anthropic, gemini)

Pure standard library (plus verifier-pure harness helpers). Never executes
provider calls, never reads live token stores, and never echoes raw secrets.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Sequence
from urllib.parse import urlsplit

from .evidence_json import canonical_bytes
from .gateway_secret_boundary import validate_no_raw_secrets

SCHEMA = "flywheel.rowan-route-receipt/v1"
ENDPOINT_CLASSES = frozenset(("local", "subscription", "api"))
CLASS_BACKENDS: dict[str, frozenset[str]] = {
    "local": frozenset(("ollama", "llama.cpp", "vllm", "gguf")),
    "subscription": frozenset(("oauth_signin", "acp", "codex_cli", "claude_code")),
    "api": frozenset(("openai_compat", "anthropic", "gemini")),
}
AVTR_ROUTE_TOKENS: dict[str, int] = {
    "<direct>": 48,
    "<imagine>": 160,
    "<think>": 380,
    "<imagine_then_think>": 520,
}
ALWAYS_THINK_TOKENS = 520
_CRED_REF_RE = re.compile(r"^cred_[0-9a-f]{32}$")
_LOOPBACK_HOSTS = frozenset(("localhost", "127.0.0.1", "::1", ""))


@dataclass(frozen=True)
class EndpointProfile:
    endpoint_id: str
    endpoint_class: str
    backend: str
    model_ref: str
    base_url: str = ""
    credential_ref: str = ""
    healthy: bool = True
    supports_tools: bool = True
    max_context: int = 32_768
    is_oracle_model: bool = False


@dataclass(frozen=True)
class RoutePolicy:
    fallback_order: tuple[str, ...] = ("local", "subscription", "api")
    offline_only: bool = False
    require_tools: bool = False
    min_context: int = 0
    prefer_local_oracle: bool = True


@dataclass(frozen=True)
class RouteRequest:
    task_id: str
    visual_complexity: float = 0.0
    text_depth: float = 0.0
    belief_ambiguity: float = 0.0
    require_oracle: bool = False
    metadata: dict[str, str] | None = None


def _check_unit_float(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    fval = float(value)
    if not (0.0 <= fval <= 1.0):
        raise ValueError(f"{name} must be within [0.0, 1.0]")
    return round(fval, 6)


def classify_avtr_route(
    visual_complexity: float,
    text_depth: float,
    belief_ambiguity: float = 0.0,
) -> dict[str, Any]:
    """Deterministic AVTR-4R 4-route budget controller with RLVB escalation."""
    vis = _check_unit_float("visual_complexity", visual_complexity)
    txt = _check_unit_float("text_depth", text_depth)
    amb = _check_unit_float("belief_ambiguity", belief_ambiguity)
    if vis >= 0.55 and (txt >= 0.55 or amb >= 0.45):
        tag = "<imagine_then_think>"
    elif vis >= 0.55:
        tag = "<imagine>"
    elif txt >= 0.55 or amb >= 0.45:
        tag = "<think>"
    else:
        tag = "<direct>"
    est = AVTR_ROUTE_TOKENS[tag]
    return {
        "route": tag,
        "est_tokens": est,
        "always_think_tokens": ALWAYS_THINK_TOKENS,
        "token_savings_frac": round(1.0 - (est / float(ALWAYS_THINK_TOKENS)), 4),
        "rlvb_wait_triggered": amb >= 0.45,
    }


def _check_no_secrets(payload: object) -> None:
    try:
        validate_no_raw_secrets(payload)
    except Exception:
        raise ValueError("RAW_SECRET_REJECTED") from None


def _validate_local_url(base_url: str) -> None:
    if not base_url:
        return
    parsed = urlsplit(base_url)
    if parsed.scheme == "file":
        return
    if parsed.scheme not in ("http", "https"):
        raise ValueError("local endpoint base_url must use http, https, or file scheme")
    if (parsed.hostname or "").lower() not in _LOOPBACK_HOSTS:
        raise ValueError("local endpoint base_url must target loopback host only")


def validate_endpoint_profile(profile: EndpointProfile) -> None:
    """Fail-closed validation of one endpoint profile without echoing secrets."""
    if not profile.endpoint_id.strip() or not profile.model_ref.strip():
        raise ValueError("endpoint_id and model_ref must be non-empty")
    if profile.endpoint_class not in ENDPOINT_CLASSES:
        raise ValueError(f"unsupported endpoint_class: {profile.endpoint_class}")
    allowed = CLASS_BACKENDS[profile.endpoint_class]
    if profile.backend not in allowed:
        raise ValueError(f"backend {profile.backend!r} invalid for class {profile.endpoint_class!r}")
    if profile.max_context < 0:
        raise ValueError("max_context must be non-negative")
    if profile.credential_ref and not _CRED_REF_RE.match(profile.credential_ref):
        raise ValueError("credential_ref must be an opaque cred_<32hex> handle")
    secret_check = {
        "endpoint_id": profile.endpoint_id,
        "backend": profile.backend,
        "model_ref": profile.model_ref,
        "base_url": profile.base_url,
    }
    if profile.credential_ref:
        secret_check["credential_ref"] = profile.credential_ref
    _check_no_secrets(secret_check)
    if profile.endpoint_class == "local":
        _validate_local_url(profile.base_url)


def _validate_policy(policy: RoutePolicy) -> None:
    if not policy.fallback_order:
        raise ValueError("fallback_order must not be empty")
    for cls in policy.fallback_order:
        if cls not in ENDPOINT_CLASSES:
            raise ValueError(f"invalid fallback_order class: {cls}")
    if policy.min_context < 0:
        raise ValueError("min_context must be non-negative")


def _select_from_tier(
    candidates: list[EndpointProfile],
    request: RouteRequest,
    policy: RoutePolicy,
    skipped: list[dict[str, str]],
) -> EndpointProfile | None:
    eligible: list[EndpointProfile] = []
    for ep in candidates:
        if policy.offline_only and ep.endpoint_class != "local":
            skipped.append({"endpoint_id": ep.endpoint_id, "reason": "refused_remote_offline_only"})
            continue
        if not ep.healthy:
            skipped.append({"endpoint_id": ep.endpoint_id, "reason": "endpoint_unhealthy"})
            continue
        if policy.require_tools and not ep.supports_tools:
            skipped.append({"endpoint_id": ep.endpoint_id, "reason": "missing_tool_support"})
            continue
        if ep.max_context < policy.min_context:
            skipped.append({"endpoint_id": ep.endpoint_id, "reason": "context_below_minimum"})
            continue
        eligible.append(ep)
    if not eligible:
        return None
    if request.require_oracle and policy.prefer_local_oracle:
        eligible.sort(key=lambda ep: (not ep.is_oracle_model, ep.endpoint_id))
    return eligible[0]


def _seal_receipt(body: dict[str, Any]) -> dict[str, Any]:
    digest = hashlib.sha256(canonical_bytes(body)).hexdigest()
    sealed = dict(body)
    sealed["receipt_sha256"] = f"sha256:{digest}"
    return sealed


def _build_route_body(
    request: RouteRequest,
    policy: RoutePolicy,
    avtr: dict[str, Any],
    chosen: EndpointProfile | None,
    skipped: list[dict[str, str]],
    meta: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "task_id": request.task_id,
        "verdict": "MATCH" if chosen is not None else "UNVERIFIABLE",
        "route_status": "planned" if chosen is not None else "refused",
        "offline_only": policy.offline_only,
        "fallback_order": list(policy.fallback_order),
        "avtr": avtr,
        "selected": {
            "endpoint_id": chosen.endpoint_id,
            "endpoint_class": chosen.endpoint_class,
            "backend": chosen.backend,
            "model_ref": chosen.model_ref,
            "is_oracle_model": chosen.is_oracle_model,
        } if chosen is not None else None,
        "skipped_endpoints": skipped,
        "metadata": meta,
        "non_execution": {
            "provider_execution": False,
            "credential_store_read": False,
            "raw_secrets_present": False,
        },
    }


def plan_rowan_route(
    request: RouteRequest,
    endpoints: Sequence[EndpointProfile],
    policy: RoutePolicy | None = None,
) -> dict[str, Any]:
    """Plan one deterministic Rowan provider route and seal a SHA-256 receipt."""
    active_policy = policy or RoutePolicy()
    if not request.task_id.strip():
        raise ValueError("task_id must be non-empty")
    _validate_policy(active_policy)
    meta = dict(request.metadata) if request.metadata else {}
    _check_no_secrets({"task_id": request.task_id, "metadata": meta})
    seen_ids: set[str] = set()
    for ep in endpoints:
        validate_endpoint_profile(ep)
        if ep.endpoint_id in seen_ids:
            raise ValueError(f"duplicate endpoint_id: {ep.endpoint_id}")
        seen_ids.add(ep.endpoint_id)

    avtr = classify_avtr_route(
        request.visual_complexity, request.text_depth, request.belief_ambiguity,
    )
    skipped: list[dict[str, str]] = []
    chosen: EndpointProfile | None = None
    for tier in active_policy.fallback_order:
        tier_eps = [ep for ep in endpoints if ep.endpoint_class == tier]
        chosen = _select_from_tier(tier_eps, request, active_policy, skipped)
        if chosen is not None:
            break
    return _seal_receipt(_build_route_body(request, active_policy, avtr, chosen, skipped, meta))


def verify_route_receipt(receipt: dict[str, Any]) -> bool:
    """Offline stdlib verifier for a flywheel.rowan-route-receipt/v1 record."""
    if not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA:
        return False
    digest = receipt.get("receipt_sha256")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        return False
    try:
        _check_no_secrets(receipt)
    except ValueError:
        return False
    guard = receipt.get("non_execution")
    if not isinstance(guard, dict) or guard.get("provider_execution") is not False:
        return False
    body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    expected = "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()
    return digest == expected
