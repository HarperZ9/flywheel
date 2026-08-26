"""Contract for Flywheel OP: the connector layer that puts offensive, dual-use,
and security tools on the gateway-operations plane (not the data-only pack plane).

These tests hold the OP invariants: proprietary license, containment for anything
that executes or reaches the network, scopes within the gateway set, canonical
digests, and a secret boundary on arguments. Live gateway dispatch of the
`op.invoke` action is a separate coordinated increment; this file pins the shape
the connectors produce so that increment has a fixed target.
"""
from __future__ import annotations

import pytest

from harness.flywheel_op import (
    ALLOWED_SCOPES,
    LICENSE_CLASS,
    OP_ACTION,
    OP_REGISTRY,
    OPConnector,
    OPConnectorError,
    build_op_operation,
    connectors,
    get_connector,
)


def test_allowed_scopes_match_the_gateway_scopes():
    # Drift guard: if the gateway changes its operation scope vocabulary, this
    # fails here rather than letting OP silently accept an unknown scope.
    from harness.gateway_operation import _SCOPES
    assert ALLOWED_SCOPES == frozenset(_SCOPES)


def test_registry_ids_are_unique_and_slugs():
    ids = [c.connector_id for c in OP_REGISTRY.values()]
    assert len(ids) == len(set(ids))
    assert all(cid and cid.replace("-", "").isalnum() for cid in ids)


def test_every_connector_is_proprietary():
    assert all(c.license_class == LICENSE_CLASS for c in OP_REGISTRY.values())
    assert LICENSE_CLASS == "proprietary"


def test_every_connector_uses_known_scopes():
    for c in OP_REGISTRY.values():
        assert set(c.scopes) <= ALLOWED_SCOPES
        assert c.scopes, f"{c.connector_id} declares no scopes"


def test_executing_or_networking_connectors_require_containment():
    for c in OP_REGISTRY.values():
        if {"exec", "network", "write"} & set(c.scopes):
            assert c.containment_required, f"{c.connector_id} escapes containment"


def test_available_connectors_name_a_server_and_cover_orca_and_array():
    available = {c.connector_id for c in connectors(available_only=True)}
    assert {"orca", "array"} <= available
    for c in connectors(available_only=True):
        assert c.mcp_server, f"{c.connector_id} is available but names no server"


def test_get_connector_known_and_unknown():
    assert get_connector("orca").tool == "orca"
    with pytest.raises(OPConnectorError):
        get_connector("does-not-exist")


def test_build_operation_shape_and_digests():
    op = build_op_operation(get_connector("array"), {"goal": "authorized recon", "target": "fixture-a"})
    assert op["action"] == OP_ACTION
    assert op["tool"] == "array"
    assert op["destination"]["connector"] == "array"
    assert set(op["scopes"]) == {"exec", "network"}
    assert op["license_class"] == "proprietary"
    assert op["containment_required"] is True
    for key in ("operation_sha256", "arguments_sha256"):
        assert len(op[key]) == 64 and all(ch in "0123456789abcdef" for ch in op[key])


def test_build_operation_is_deterministic_and_argument_sensitive():
    c = get_connector("orca")
    a = build_op_operation(c, {"workspace": "x"})
    b = build_op_operation(c, {"workspace": "x"})
    d = build_op_operation(c, {"workspace": "y"})
    assert a["operation_sha256"] == b["operation_sha256"]
    assert a["arguments_sha256"] == b["arguments_sha256"]
    assert a["arguments_sha256"] != d["arguments_sha256"]


def test_build_operation_rejects_raw_secrets():
    with pytest.raises(Exception):
        build_op_operation(get_connector("array"), {"api_key": "sk-live-abc123"})


def test_build_operation_rejects_non_dict_arguments():
    with pytest.raises(OPConnectorError):
        build_op_operation(get_connector("orca"), ["not", "a", "dict"])


def test_connector_validation_rejects_bad_declarations():
    with pytest.raises(OPConnectorError):
        OPConnector("bad", "Bad", "bad", ("x",), ("teleport",), True, True, "n/a")
    with pytest.raises(OPConnectorError):
        OPConnector("bad", "Bad", "bad", ("x",), ("exec",), True, True, "n/a", license_class="MIT")
    with pytest.raises(OPConnectorError):
        OPConnector("bad", "Bad", "bad", ("x",), ("exec",), False, True, "n/a")
