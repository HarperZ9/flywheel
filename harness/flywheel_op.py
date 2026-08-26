"""Flywheel OP: the connector layer that brings offensive, dual-use, and security
tools onto the gateway-operations plane.

These tools are NOT domain packs. Domain packs (harness/domain_pack.py) are
data-only and deterministic, and the admission verifier never grants them
network, write, or secrets. Offensive tools need execution and network, so they
run as grant-gated gateway operations.

The gateway already has a complete, tested plane for invoking a named tool on a
named MCP server under a one-use grant: the plugin plane. `plugin.register`
records an MCP stdio server by argv, `plugin.probe` lists its real tools, and
`plugin.call` invokes one tool with arguments through `authorize_gateway_operation`
-> `dispatch_builtin` -> `plugins.call_plugin` -> a real MCP `tools/call`, under a
restricted child environment, the secret boundary, and a receipt. An offensive
tool IS an MCP stdio server (ORCA `orca-mcp`, Array `python -m
red_team_platform.mcp_server`), so OP rides this plane rather than adding a
parallel gateway action that would duplicate `plugin.call`.

OP is therefore a curated, proprietary registry. It declares each connector and
builds the exact gateway operations that register, probe, and invoke it. Every
built operation is validated by the real `canonicalize_operation`, so an
OP-emitted operation is a genuine gateway operation the existing pipeline runs,
not a bespoke shape nothing consumes. OP adds what the generic plugin plane does
not carry: a proprietary license class that never converts to open, a
containment requirement for anything that executes or reaches the network, and a
`does_not_prove` line per connector.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

# The gateway actions OP rides. Each is a real, wired, grant-gated action.
REGISTER_ACTION = "plugin.register"
PROBE_ACTION = "plugin.probe"
CALL_ACTION = "plugin.call"

# OP plugin names are namespaced so they never shadow a bundled lane or the
# builtin tool set, which `plugins.register_mcp` reserves.
OP_NAME_PREFIX = "op-"

# The scopes an OP operation may request, kept equal to the gateway's own
# operation scopes. test_flywheel_op asserts this set matches, so a change to the
# gateway scope vocabulary fails the OP contract test rather than drifting.
ALLOWED_SCOPES: frozenset[str] = frozenset(
    ("write", "exec", "network", "plugin", "secrets"))

# OP connectors are proprietary and never convert to open, unlike the public
# domain packs. This is a declaration the build layer enforces, not a license.
LICENSE_CLASS = "proprietary"

# The scopes the gateway derives for a plugin.call, regardless of the tool. Every
# OP invocation runs under this grant; a connector's own `scopes` field states
# the capabilities the tool actually uses (least privilege), which must be a
# subset of what the plane grants.
CALL_GRANT_SCOPES: frozenset[str] = frozenset(("write", "exec", "network", "plugin"))


class OPConnectorError(ValueError):
    """A connector or operation that violates the OP contract."""


@dataclass(frozen=True)
class OPConnector:
    """One offensive, dual-use, or security tool on the operations plane.

    mcp_command is the argv for the connector's MCP server. It may name a known
    target whose server is not live yet; `mcp_available` is the gate that decides
    whether the connector can be registered, probed, or invoked. A connector with
    mcp_available=False is a declared target only, whether its command is empty
    (no server exists) or a known argv (server not shipped/vetted yet).
    """
    connector_id: str
    display_name: str
    tool: str
    mcp_command: tuple[str, ...]
    scopes: tuple[str, ...]
    containment_required: bool
    mcp_available: bool
    does_not_prove: str
    requires: tuple[str, ...] = ()
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
        if self.mcp_available and not self.mcp_command:
            raise OPConnectorError(f"{self.connector_id}: available connector names no mcp_command")

    @property
    def plugin_name(self) -> str:
        """The name this connector registers under on the plugin plane."""
        return OP_NAME_PREFIX + self.connector_id


# The registry. mcp_available reflects whether the tool ships a running MCP server
# today; a False connector is a declared target whose surface is not yet wired,
# stated honestly rather than pretended-ready.
_CONNECTORS: tuple[OPConnector, ...] = (
    OPConnector(
        connector_id="orca",
        display_name="ORCA",
        tool="assess",
        mcp_command=("orca-mcp",),
        scopes=("exec",),
        containment_required=True,
        mcp_available=True,
        does_not_prove="a returned finding is a local, metadata-only assessment "
                       "record, not an exploited or verified vulnerability",
    ),
    OPConnector(
        connector_id="array",
        display_name="Array",
        tool="plan_wave",
        mcp_command=("python", "-m", "red_team_platform.mcp_server"),
        scopes=("exec", "network"),
        containment_required=True,
        mcp_available=True,
        does_not_prove="a planned or executed wave is authorized orchestration "
                       "under the operator's rules of engagement, not proof of impact",
    ),
    OPConnector(
        connector_id="isomorph",
        display_name="Isomorph",
        tool="transform",
        mcp_command=("isomorph-mcp",),
        scopes=("network", "exec"),
        containment_required=True,
        mcp_available=False,
        does_not_prove="a transformed or recovered response measures provider "
                       "boundary behavior, not a general capability grant",
    ),
    OPConnector(
        connector_id="sofer",
        display_name="Sofer",
        tool="run",
        mcp_command=("python", "-m", "sofer.mcp"),
        scopes=("exec", "network"),
        containment_required=True,
        mcp_available=False,
        does_not_prove="a domain result is authorized tooling output for the "
                       "operator's mandate, not lawful authorization in itself",
    ),
    OPConnector(
        connector_id="bounds",
        display_name="Bounds",
        tool="verify",
        mcp_command=(),
        scopes=("exec",),
        containment_required=True,
        mcp_available=False,
        does_not_prove="a trust-verification receipt records what was observed, "
                       "not that a human authored, authorized, or attested it",
    ),
    OPConnector(
        connector_id="phantom",
        display_name="Phantom",
        tool="rotate",
        mcp_command=(),
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


def _require_server(connector: OPConnector) -> None:
    # mcp_available is the single gate. A connector marked unavailable is a
    # declared target only and must not reach the live grant-gated plugin plane,
    # even if it carries a known-but-not-yet-shipped command argv.
    if not connector.mcp_available:
        raise OPConnectorError(
            f"{connector.connector_id}: MCP surface not available yet, "
            "cannot register, probe, or invoke")
    if not connector.mcp_command:
        raise OPConnectorError(
            f"{connector.connector_id}: no MCP server, cannot register or invoke")
    if connector.license_class != LICENSE_CLASS:
        raise OPConnectorError("OP connectors are proprietary")
    if ({"exec", "network", "write"} & set(connector.scopes)) and not connector.containment_required:
        raise OPConnectorError("executing or networking connector requires containment")


def build_op_registration(connector: OPConnector) -> dict:
    """Build the `plugin.register` operation that mounts this connector.

    The result is a genuine gateway operation: `canonicalize_operation` accepts
    it and routes it to `plugins.register_mcp` under the plugin scope.
    """
    _require_server(connector)
    return {
        "name": connector.plugin_name,
        "command": list(connector.mcp_command),
        "detail": f"Flywheel OP connector ({connector.display_name}); "
                  f"proprietary. {connector.does_not_prove}",
        "requires": list(connector.requires),
        "data_refs": [],
        "credential_refs": [],
    }


def build_op_probe(connector: OPConnector) -> dict:
    """Build the `plugin.probe` operation that lists this connector's real tools."""
    _require_server(connector)
    return {
        "name": connector.plugin_name,
        "data_refs": [],
        "credential_refs": [],
    }


def build_op_call(connector: OPConnector, tool: str, arguments: dict,
                  *, credential_refs: tuple[str, ...] = ()) -> dict:
    """Build the `plugin.call` operation that invokes one tool on this connector.

    Raises if arguments carry raw secrets (the gateway's own secret boundary
    runs again in canonicalization; this fails early with a clear error).
    """
    _require_server(connector)
    if type(arguments) is not dict:
        raise OPConnectorError("operation arguments must be a dict")
    if not tool or type(tool) is not str:
        raise OPConnectorError("a tool name is required")
    from .gateway_secret_boundary import validate_no_raw_secrets
    validate_no_raw_secrets(arguments)
    return {
        "name": connector.plugin_name,
        "tool": tool,
        "arguments": dict(arguments),
        "data_refs": [],
        "credential_refs": list(credential_refs),
    }


def canonical_op_call(connector: OPConnector, tool: str, arguments: dict,
                      *, credential_refs: tuple[str, ...] = ()):
    """Return the real CanonicalOperation for an OP invocation.

    This is the proof that OP is connected: the built operation goes through the
    gateway's own `canonicalize_operation`, so it carries the gateway's digests,
    destination (kind "plugin", ref the connector's plugin name), and derived
    scopes. Raises GatewayOperationError on any shape the gateway refuses.
    """
    from .gateway_operation import canonicalize_operation
    return canonicalize_operation(
        CALL_ACTION, build_op_call(connector, tool, arguments,
                                   credential_refs=credential_refs))
