"""Residual P3-T3 slice: the provider-dispatching routes outside the
operation path join the exact-grant boundary.

/api/companion, /api/route, /api/forge, /api/forge/recheck, and
/v1/embeddings all dispatch to external providers, so per the completion
spec every one of them requires a short-lived one-use grant bound to the
authenticated actor, an exact journey and head, the canonical operation
digest, tool, arguments, scopes, refs, expiry, and nonce. A global
checkbox grants nothing.
"""
import pytest

from harness.gateway_operation import (
    GatewayOperationError,
    _derived_scopes,
    _destination,
    action_for_path,
    canonicalize_operation,
)


def test_provider_routes_join_the_grant_map():
    assert action_for_path("/api/companion") == "companion.ask"
    assert action_for_path("/api/route") == "route.send"
    assert action_for_path("/api/forge") == "forge.create"
    assert action_for_path("/api/forge/recheck") == "forge.recheck"
    assert action_for_path("/v1/embeddings") == "embeddings.create"


def _canonical(action, operation):
    return canonicalize_operation(action, operation)


def test_companion_ask_canonicalizes():
    op = _canonical("companion.ask", {
        "prompt": "what went wrong",
        "data_refs": [], "credential_refs": []})
    assert op.tool == "companion.ask"
    assert _destination("companion.ask", op.operation)["kind"] == "model"
    assert "network" in _derived_scopes("companion.ask", op.operation, False)


def test_companion_ask_rejects_missing_prompt():
    with pytest.raises(GatewayOperationError):
        _canonical("companion.ask", {
            "data_refs": [], "credential_refs": []})


def test_route_send_canonicalizes_with_endpoint_destination():
    op = _canonical("route.send", {
        "prompt": "hi", "endpoint": "codex", "model": "gpt",
        "data_refs": [], "credential_refs": []})
    dest = _destination("route.send", op.operation)
    assert dest == {"kind": "endpoint", "ref": "codex"}
    assert "network" in _derived_scopes("route.send", op.operation, False)


def test_route_send_requires_endpoint():
    with pytest.raises(GatewayOperationError):
        _canonical("route.send", {
            "prompt": "hi", "data_refs": [], "credential_refs": []})


def test_forge_create_canonicalizes_optional_sources():
    op = _canonical("forge.create", {
        "goal": "ship the gate",
        "context": "repo docs",
        "intent_source": "README",
        "data_refs": [], "credential_refs": []})
    assert op.operation["goal"] == "ship the gate"
    assert "network" in _derived_scopes("forge.create", op.operation, False)


def test_forge_recheck_is_bound_to_the_seal_id():
    op = _canonical("forge.recheck", {
        "prp_id": "prp_" + "a" * 32,
        "data_refs": [], "credential_refs": []})
    assert _destination("forge.recheck", op.operation)["ref"] == \
        "prp_" + "a" * 32
    with pytest.raises(GatewayOperationError):
        _canonical("forge.recheck", {
            "prp_id": "not-a-seal-ref",
            "data_refs": [], "credential_refs": []})


def test_embeddings_create_canonicalizes():
    op = _canonical("embeddings.create", {
        "input": ["hello"], "model": "embed",
        "data_refs": [], "credential_refs": []})
    assert "network" in _derived_scopes(
        "embeddings.create", op.operation, False)


def test_embeddings_rejects_a_bare_scalar_input():
    with pytest.raises(GatewayOperationError):
        _canonical("embeddings.create", {
            "input": 42, "data_refs": [], "credential_refs": []})
