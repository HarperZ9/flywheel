"""Tests and planted-failure controls for harness/rowan_provider_router.py."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from harness.rowan_provider_router import (
    SCHEMA,
    EndpointProfile,
    RoutePolicy,
    RouteRequest,
    classify_avtr_route,
    plan_rowan_route,
    verify_route_receipt,
)


def _sample_endpoints() -> list[EndpointProfile]:
    return [
        EndpointProfile(
            endpoint_id="rtx4090-jfc3p-oracle",
            endpoint_class="local",
            backend="gguf",
            model_ref="jfc3p-7b-oracle-v1",
            base_url="http://127.0.0.1:8080",
            is_oracle_model=True,
            max_context=32_768,
        ),
        EndpointProfile(
            endpoint_id="rtx4090-ollama-qwen",
            endpoint_class="local",
            backend="ollama",
            model_ref="qwen2.5-coder:14b",
            base_url="http://localhost:11434",
            is_oracle_model=False,
            max_context=32_768,
        ),
        EndpointProfile(
            endpoint_id="claude-oauth-sub",
            endpoint_class="subscription",
            backend="oauth_signin",
            model_ref="claude-sonnet-4",
            credential_ref="cred_" + "a" * 32,
            max_context=200_000,
        ),
        EndpointProfile(
            endpoint_id="openai-api-primary",
            endpoint_class="api",
            backend="openai_compat",
            model_ref="gpt-5-codex",
            base_url="https://api.openai.com/v1",
            credential_ref="cred_" + "b" * 32,
            max_context=128_000,
        ),
    ]


def test_avtr_4r_routing_and_token_savings() -> None:
    workloads = [
        (0.10, 0.15, 0.05),
        (0.80, 0.20, 0.10),
        (0.20, 0.75, 0.15),
        (0.85, 0.80, 0.65),
    ]
    routed = [classify_avtr_route(*w) for w in workloads]
    assert [r["route"] for r in routed] == [
        "<direct>", "<imagine>", "<think>", "<imagine_then_think>",
    ]
    assert routed[3]["rlvb_wait_triggered"] is True
    assert routed[0]["rlvb_wait_triggered"] is False
    saved = 1.0 - sum(r["est_tokens"] for r in routed) / float(
        sum(r["always_think_tokens"] for r in routed)
    )
    assert round(saved, 4) == 0.4673


def test_local_oracle_selected_first_and_receipt_verifies() -> None:
    req = RouteRequest(
        task_id="wave20a-oracle-check",
        visual_complexity=0.1,
        text_depth=0.7,
        require_oracle=True,
        metadata={"lane": "flywheel"},
    )
    receipt = plan_rowan_route(req, _sample_endpoints())
    assert receipt["schema"] == SCHEMA
    assert receipt["verdict"] == "MATCH"
    assert receipt["route_status"] == "planned"
    assert receipt["selected"]["endpoint_id"] == "rtx4090-jfc3p-oracle"
    assert receipt["selected"]["endpoint_class"] == "local"
    assert receipt["avtr"]["route"] == "<think>"
    assert verify_route_receipt(receipt) is True


def test_fallback_ladder_local_to_subscription_to_api() -> None:
    endpoints = [
        EndpointProfile(
            endpoint_id="local-down",
            endpoint_class="local",
            backend="vllm",
            model_ref="qwen2.5-7b",
            base_url="http://127.0.0.1:8000",
            healthy=False,
        ),
        EndpointProfile(
            endpoint_id="sub-small-ctx",
            endpoint_class="subscription",
            backend="acp",
            model_ref="codex-sub",
            max_context=16_000,
        ),
        EndpointProfile(
            endpoint_id="api-healthy",
            endpoint_class="api",
            backend="anthropic",
            model_ref="claude-opus-4",
            credential_ref="cred_" + "c" * 32,
            max_context=200_000,
        ),
    ]
    policy = RoutePolicy(min_context=64_000)
    receipt = plan_rowan_route(RouteRequest(task_id="fallback-ladder"), endpoints, policy)
    assert receipt["verdict"] == "MATCH"
    assert receipt["selected"]["endpoint_id"] == "api-healthy"
    assert receipt["skipped_endpoints"] == [
        {"endpoint_id": "local-down", "reason": "endpoint_unhealthy"},
        {"endpoint_id": "sub-small-ctx", "reason": "context_below_minimum"},
    ]
    assert verify_route_receipt(receipt) is True


def test_planted_failure_offline_mode_refuses_remote_endpoints() -> None:
    remote_only = [ep for ep in _sample_endpoints() if ep.endpoint_class != "local"]
    policy = RoutePolicy(offline_only=True)
    receipt = plan_rowan_route(RouteRequest(task_id="offline-strict"), remote_only, policy)
    assert receipt["verdict"] == "UNVERIFIABLE"
    assert receipt["route_status"] == "refused"
    assert receipt["selected"] is None
    assert len(receipt["skipped_endpoints"]) == 2
    assert all(s["reason"] == "refused_remote_offline_only" for s in receipt["skipped_endpoints"])
    assert verify_route_receipt(receipt) is True


def test_planted_failure_invalid_endpoint_class_and_backend() -> None:
    bad_class = EndpointProfile("bad-1", "cloud_magic", "ollama", "qwen")
    with pytest.raises(ValueError, match="unsupported endpoint_class"):
        plan_rowan_route(RouteRequest(task_id="t1"), [bad_class])

    bad_backend = EndpointProfile("bad-2", "api", "ollama", "qwen")
    with pytest.raises(ValueError, match="invalid for class"):
        plan_rowan_route(RouteRequest(task_id="t2"), [bad_backend])

    non_loopback_local = EndpointProfile(
        "bad-3", "local", "ollama", "qwen", base_url="https://remote.example.com/v1",
    )
    with pytest.raises(ValueError, match="loopback host only"):
        plan_rowan_route(RouteRequest(task_id="t3"), [non_loopback_local])


def test_planted_failure_leaked_secret_rejected_without_echo() -> None:
    fake_sk = "sk-live-secret1234567890abcdef1234567890"
    bad_cred = EndpointProfile(
        "leak-1", "api", "openai_compat", "gpt-5", credential_ref=fake_sk,
    )
    with pytest.raises(ValueError) as exc_info:
        plan_rowan_route(RouteRequest(task_id="leak-cred"), [bad_cred])
    assert fake_sk not in str(exc_info.value)

    bad_url = EndpointProfile(
        "leak-2", "api", "openai_compat", "gpt-5",
        base_url="https://api.example.com/v1?api_key=topsecretvalue123",
    )
    with pytest.raises(ValueError) as exc_url:
        plan_rowan_route(RouteRequest(task_id="leak-url"), [bad_url])
    assert "topsecretvalue123" not in str(exc_url.value)

    req_leak = RouteRequest(
        task_id="leak-meta", metadata={"note": "Authorization: Bearer supersecret999"},
    )
    with pytest.raises(ValueError) as exc_meta:
        plan_rowan_route(req_leak, _sample_endpoints())
    assert "supersecret999" not in str(exc_meta.value)


def test_planted_failure_tampered_receipt_fails_verification() -> None:
    receipt = plan_rowan_route(RouteRequest(task_id="tamper-test"), _sample_endpoints())
    assert verify_route_receipt(receipt) is True
    tampered = dict(receipt)
    tampered["selected"] = dict(receipt["selected"], endpoint_id="evil-endpoint")
    assert verify_route_receipt(tampered) is False


def test_router_module_size_and_function_loc_budget() -> None:
    src_path = Path(__file__).resolve().parent.parent / "harness" / "rowan_provider_router.py"
    lines = src_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 280, f"rowan_provider_router.py is {len(lines)} lines (limit 280)"
    tree = ast.parse("\n".join(lines))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_lines = (node.end_lineno or node.lineno) - node.lineno + 1
            assert fn_lines <= 50, f"{node.name} is {fn_lines} lines (limit 50)"
