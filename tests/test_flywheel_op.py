"""Contract for Flywheel OP: the connector layer that puts offensive, dual-use,
and security tools on the gateway-operations plane by riding the existing plugin
plane (plugin.register / plugin.probe / plugin.call), not a bespoke action.

These tests hold the OP invariants (proprietary license, containment for anything
that executes or reaches the network, scopes within the gateway set, a secret
boundary on arguments) AND prove the connection: every operation OP builds is
accepted by the real `canonicalize_operation`, so it is a genuine gateway
operation the existing, tested pipeline runs, not a shape nothing consumes.
"""
from __future__ import annotations

import pytest

from harness.flywheel_op import (
    ALLOWED_SCOPES,
    CALL_ACTION,
    CALL_GRANT_SCOPES,
    LICENSE_CLASS,
    OP_NAME_PREFIX,
    OP_REGISTRY,
    OPConnector,
    OPConnectorError,
    PROBE_ACTION,
    REGISTER_ACTION,
    build_op_call,
    build_op_probe,
    build_op_registration,
    canonical_op_call,
    connectors,
    get_connector,
)
from harness.gateway_operation import (
    GatewayOperationError, canonicalize_operation)


def test_allowed_scopes_match_the_gateway_scopes():
    # Drift guard: if the gateway changes its operation scope vocabulary, this
    # fails here rather than letting OP silently accept an unknown scope.
    from harness.gateway_operation import _SCOPES
    assert ALLOWED_SCOPES == frozenset(_SCOPES)


def test_op_rides_real_gateway_actions():
    # OP does not invent an action; it rides three wired, grant-gated ones.
    from harness.gateway_operation import _FIELDS
    assert {REGISTER_ACTION, PROBE_ACTION, CALL_ACTION} <= set(_FIELDS)


def test_registry_ids_are_unique_slugs_and_do_not_shadow_lanes():
    from harness.lanes import LANES
    ids = [c.connector_id for c in OP_REGISTRY.values()]
    assert len(ids) == len(set(ids))
    for c in OP_REGISTRY.values():
        assert c.connector_id and c.connector_id.replace("-", "").isalnum()
        assert c.plugin_name.startswith(OP_NAME_PREFIX)
        assert c.plugin_name not in LANES and c.plugin_name != "tools"


def test_every_connector_is_proprietary():
    assert all(c.license_class == LICENSE_CLASS for c in OP_REGISTRY.values())
    assert LICENSE_CLASS == "proprietary"


def test_every_connector_uses_known_scopes_within_the_call_grant():
    # A connector's declared scopes state least privilege; every OP invocation
    # actually runs under the plugin.call grant, so declared scopes must sit
    # inside what that grant covers (plus secrets, added only when credentials
    # are bound).
    for c in OP_REGISTRY.values():
        assert set(c.scopes) <= ALLOWED_SCOPES
        assert c.scopes, f"{c.connector_id} declares no scopes"
        assert set(c.scopes) <= (CALL_GRANT_SCOPES | {"secrets"})


def test_executing_or_networking_connectors_require_containment():
    for c in OP_REGISTRY.values():
        if {"exec", "network", "write"} & set(c.scopes):
            assert c.containment_required, f"{c.connector_id} escapes containment"


def test_available_connectors_name_a_command_and_cover_orca_and_array():
    available = {c.connector_id for c in connectors(available_only=True)}
    assert {"orca", "array"} <= available
    for c in connectors(available_only=True):
        assert c.mcp_command, f"{c.connector_id} is available but names no command"


def test_get_connector_known_and_unknown():
    assert get_connector("orca").tool == "assess"
    with pytest.raises(OPConnectorError):
        get_connector("does-not-exist")


def test_registration_is_a_valid_gateway_operation():
    op = build_op_registration(get_connector("array"))
    canonical = canonicalize_operation(REGISTER_ACTION, op)
    assert canonical.action == REGISTER_ACTION
    assert canonical.destination["kind"] == "plugin"
    assert canonical.destination["ref"] == "op-array"
    assert "plugin" in canonical.scopes and "write" in canonical.scopes


def test_probe_is_a_valid_gateway_operation():
    op = build_op_probe(get_connector("orca"))
    canonical = canonicalize_operation(PROBE_ACTION, op)
    assert canonical.action == PROBE_ACTION
    assert canonical.destination == {"kind": "plugin", "ref": "op-orca"}
    assert set(canonical.scopes) == {"exec", "network", "plugin"}


def test_call_is_a_valid_gateway_operation_with_plugin_grant():
    canonical = canonical_op_call(
        get_connector("array"), "plan_wave",
        {"goal": "authorized recon", "target": "fixture-a"})
    assert canonical.action == CALL_ACTION
    assert canonical.tool == "plan_wave"  # the MCP tool invoked on the connector
    assert canonical.destination == {"kind": "plugin", "ref": "op-array"}
    assert set(canonical.scopes) == set(CALL_GRANT_SCOPES)
    assert len(canonical.operation_sha256) == 64
    assert len(canonical.arguments_sha256) == 64


def test_call_digests_are_deterministic_and_argument_sensitive():
    c = get_connector("orca")
    a = canonical_op_call(c, "assess", {"workspace": "x"})
    b = canonical_op_call(c, "assess", {"workspace": "x"})
    d = canonical_op_call(c, "assess", {"workspace": "y"})
    assert a.operation_sha256 == b.operation_sha256
    assert a.arguments_sha256 == b.arguments_sha256
    assert a.arguments_sha256 != d.arguments_sha256


def test_call_rejects_raw_secrets_in_arguments():
    with pytest.raises(Exception):
        build_op_call(get_connector("array"), "plan_wave",
                      {"api_key": "sk-live-abc123"})


def test_call_rejects_non_dict_arguments():
    with pytest.raises(OPConnectorError):
        build_op_call(get_connector("orca"), "assess", ["not", "a", "dict"])


def test_unavailable_connectors_cannot_register_probe_or_call():
    # mcp_available is the gate, not command emptiness: isomorph/sofer carry a
    # known argv but are marked not-available, so they must be blocked exactly
    # like bounds/phantom (which carry no argv at all).
    unavailable = [c for c in OP_REGISTRY.values() if not c.mcp_available]
    assert {"isomorph", "sofer", "bounds", "phantom"} <= {c.connector_id for c in unavailable}
    for c in unavailable:
        for build in (build_op_registration, build_op_probe):
            with pytest.raises(OPConnectorError):
                build(c)
        with pytest.raises(OPConnectorError):
            build_op_call(c, c.tool, {})
        with pytest.raises(OPConnectorError):
            canonical_op_call(c, c.tool, {})


def test_connector_validation_rejects_bad_declarations():
    # unknown scope
    with pytest.raises(OPConnectorError):
        OPConnector("bad", "Bad", "t", ("x",), ("teleport",), True, True, "n/a")
    # non-proprietary license
    with pytest.raises(OPConnectorError):
        OPConnector("bad", "Bad", "t", ("x",), ("exec",), True, True, "n/a",
                    license_class="MIT")
    # exec without containment
    with pytest.raises(OPConnectorError):
        OPConnector("bad", "Bad", "t", ("x",), ("exec",), False, True, "n/a")
    # available but no command
    with pytest.raises(OPConnectorError):
        OPConnector("bad", "Bad", "t", (), ("exec",), True, True, "n/a")
