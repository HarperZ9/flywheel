"""Flywheel OP: the connector layer that brings offensive, dual-use, and security
tools onto the gateway-operations plane.

These tools are NOT domain packs. Domain packs (harness/domain_pack.py) are
data-only and deterministic, and the admission verifier never grants them
network, write, or secrets. Offensive tools need execution and network, so they
run as grant-gated gateway operations: an operation carries an action, a tool, a
destination, and derived scopes, and runs under a one-use exact-scope grant with
a secret boundary and a receipt.

This module is the declaration + build layer. It defines each connector, the
operation it produces, and the invariants (proprietary license, containment for
anything that executes or reaches the network, scopes within the gateway set, no
raw secrets in arguments). Wiring the `op.invoke` action into the gateway's own
action table (_FIELDS), shape validation, derived scopes, destination routing,
and supervisor dispatch is a separate, coordinated increment on the live gateway;
see project-docs for that plan. Until then this layer builds and validates the
operation an OP connector would submit, and its tests hold the contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from .evidence_json import canonical_sha256
from .gateway_secret_boundary import validate_no_raw_secrets

# The action an OP connector submits on the gateway-operations plane. Adding it to
# harness/gateway_operation.py `_FIELDS` (+ shape, derived_scopes, destination,
# supervisor dispatch) is the coordinated gateway increment.
OP_ACTION = "op.invoke"
OP_SCHEMA = "flywheel.op-operation/v1"

# The scopes an OP operation may request. Kept equal to the gateway's own
# operation scopes; test_flywheel_op asserts this set matches, so a change to the
# gateway scope vocabulary fails the OP contract test rather than drifting.
ALLOWED_SCOPES: frozenset[str] = frozenset(
    ("write", "exec", "network", "plugin", "secrets"))

# OP connectors are proprietary and never convert to open, unlike the public
# domain packs. This is a declaration the build layer enforces, not a license.
LICENSE_CLASS = "proprietary"


class OPConnectorError(ValueError):
    """A connector or operation that violates the OP contract."""


@dataclass(frozen=True)
class OPConnector:
    """One offensive, dual-use, or security tool on the operations plane."""
    connector_id: str
    display_name: str
    tool: str
    mcp_server: tuple[str, ...]
    scopes: tuple[str, ...]
    containment_required: bool
    mcp_available: bool
    does_not_prove: str
    license_class: str = LICENSE_CLASS

    def __post_init__(self) -> None:
        if not self.connector_id or not self.connector_id.replace("-", "").isalnum():
            raise OPConnectorError("connector_id must be a non-empty slug")
        if not self.tool:
            raise OPConnectorError("connector names no tool")
        if not self.scopes:
            raise OPConnectorError("connector declares no scopes")
        unknown = set(self.scopes) - ALLOWED_SCOPES
        if unknown:
            raise OPConnectorError(f"connector requests unknown scopes {sorted(unknown)}")
        if self.license_class != LICENSE_CLASS:
            raise OPConnectorError("OP connectors are proprietary; never a public license")
        # Anything that executes or reaches the network must run under containment.
        if ({"exec", "network", "write"} & set(self.scopes)) and not self.containment_required:
            raise OPConnectorError(
                f"{self.connector_id}: exec/network/write connectors require containment")
        if self.mcp_available and not self.mcp_server:
            raise OPConnectorError(f"{self.connector_id}: available connector names no mcp_server")


# The registry. mcp_available reflects whether the tool ships a running MCP server
# today; a False connector is a declared target whose surface is not yet wired,
# stated honestly rather than pretended-ready.
_CONNECTORS: tuple[OPConnector, ...] = (
    OPConnector(
        connector_id="orca",
        display_name="ORCA",
        tool="orca",
        mcp_server=("orca-mcp",),
        scopes=("exec",),
        containment_required=True,
        mcp_available=True,
        does_not_prove="a returned finding is a local, metadata-only assessment "
                       "record, not an exploited or verified vulnerability",
    ),
    OPConnector(
        connector_id="array",
        display_name="Array",
        tool="array",
        mcp_server=("python", "-m", "red_team_platform.mcp_server"),
        scopes=("exec", "network"),
        containment_required=True,
        mcp_available=True,
        does_not_prove="a planned or executed wave is authorized orchestration "
                       "under the operator's rules of engagement, not proof of impact",
    ),
    OPConnector(
        connector_id="isomorph",
        display_name="Isomorph",
        tool="isomorph",
        mcp_server=("isomorph-mcp",),
        scopes=("network", "exec"),
        containment_required=True,
        mcp_available=False,
        does_not_prove="a transformed or recovered response measures provider "
                       "boundary behavior, not a general capability grant",
    ),
    OPConnector(
        connector_id="sofer",
        display_name="Sofer",
        tool="sofer",
        mcp_server=("python", "-m", "sofer.mcp"),
        scopes=("exec", "network"),
        containment_required=True,
        mcp_available=False,
        does_not_prove="a domain result is authorized tooling output for the "
                       "operator's mandate, not lawful authorization in itself",
    ),
    OPConnector(
        connector_id="bounds",
        display_name="Bounds",
        tool="bounds",
        mcp_server=(),
        scopes=("exec",),
        containment_required=True,
        mcp_available=False,
        does_not_prove="a trust-verification receipt records what was observed, "
                       "not that a human authored, authorized, or attested it",
    ),
    OPConnector(
        connector_id="phantom",
        display_name="Phantom",
        tool="phantom",
        mcp_server=(),
        scopes=("exec",),
        containment_required=True,
        mcp_available=False,
        does_not_prove="a hardware-identity change is a local machine-state "
                       "transform, not off-host authenticity",
    ),
)

OP_REGISTRY: Mapping[str, OPConnector] = MappingProxyType(
    {c.connector_id: c for c in _CONNECTORS})


def connectors(*, available_only: bool = False) -> tuple[OPConnector, ...]:
    """Return the registered connectors, optionally only those with a live MCP surface."""
    return tuple(c for c in _CONNECTORS if c.mcp_available or not available_only)


def get_connector(connector_id: str) -> OPConnector:
    connector = OP_REGISTRY.get(connector_id)
    if connector is None:
        raise OPConnectorError(f"unknown OP connector {connector_id!r}")
    return connector


def build_op_operation(connector: OPConnector, arguments: dict) -> dict:
    """Build the gateway operation an OP connector submits.

    The result is shaped for the gateway-operations plane: an action, the tool,
    a destination that names the connector and its MCP server, the derived
    scopes, and canonical operation/argument digests computed the same way the
    gateway computes them. Raises if arguments carry raw secrets (the gateway's
    own secret boundary), if scopes fall outside the gateway set, or if an
    executing/networking connector is not contained.
    """
    if type(arguments) is not dict:
        raise OPConnectorError("operation arguments must be a dict")
    validate_no_raw_secrets(arguments)
    unknown = set(connector.scopes) - ALLOWED_SCOPES
    if unknown:
        raise OPConnectorError(f"connector requests unknown scopes {sorted(unknown)}")
    if ({"exec", "network", "write"} & set(connector.scopes)) and not connector.containment_required:
        raise OPConnectorError("executing or networking operation requires containment")
    operation = {
        "tool": connector.tool,
        "connector_id": connector.connector_id,
        "mcp_server": list(connector.mcp_server),
        "arguments": arguments,
    }
    return {
        "schema": OP_SCHEMA,
        "action": OP_ACTION,
        "tool": connector.tool,
        "destination": {"connector": connector.connector_id,
                        "mcp_server": list(connector.mcp_server)},
        "scopes": list(connector.scopes),
        "containment_required": connector.containment_required,
        "license_class": connector.license_class,
        "operation_sha256": canonical_sha256({"action": OP_ACTION, "operation": operation}),
        "arguments_sha256": canonical_sha256(arguments),
        "does_not_prove": connector.does_not_prove,
    }
