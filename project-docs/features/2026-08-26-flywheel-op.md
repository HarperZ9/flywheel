# Flywheel OP: offensive, dual-use, and security tools on the operations plane

## What it is

Flywheel OP connects the offensive, dual-use, and security tools (ORCA, Array,
Isomorph, Sofer, Bounds, Phantom) into Flywheel as grant-gated gateway
operations. It is the surface that lets an operator run those tools through the
gateway, under one-use exact-scope grants, with a secret boundary and receipts.

## Why not domain packs

Domain packs (`harness/domain_pack.py`) are the data-only substrate: the
admission verifier never grants a pack network, write, or secrets, and only
deterministic oracles pass. The offensive tools need execution and network by
nature, so they cannot be packs. Their home is the gateway-operations plane,
where `harness/gateway_operation.py` already models grant-gated operations with
the scopes `write | exec | network | plugin | secrets`, one-use grants
(`operation_grants.py`), a secret boundary, and receipts.

## What shipped now (the connector layer)

`harness/flywheel_op.py` and `tests/test_flywheel_op.py`:

- `OPConnector`: one tool on the operations plane, with its MCP server, the
  scopes it requests, whether it must run under containment, whether its MCP
  surface is live today (`mcp_available`), its proprietary license class, and a
  `does_not_prove` line.
- `OP_REGISTRY`: the six tools. ORCA (`orca-mcp`) and Array
  (`python -m red_team_platform.mcp_server`) have live MCP surfaces today;
  Isomorph, Sofer, Bounds, and Phantom are declared with `mcp_available=False`
  until their surface is wired, stated honestly rather than pretended-ready.
- `build_op_operation`: builds the gateway operation a connector submits, with
  canonical operation and argument digests computed the same way the gateway
  computes them, and it enforces the invariants: proprietary license, containment
  for anything that executes or reaches the network, scopes within the gateway
  set, and no raw secrets in arguments (the gateway's own secret boundary).

The OP scope set is drift-guarded against the gateway's own scope vocabulary by a
test, so a change there fails the OP contract rather than drifting silently.

## The next increment (a coordinated gateway change)

Running an OP operation end to end needs one new gateway action, `op.invoke`,
wired into the live gateway:

- `_FIELDS` in `harness/gateway_operation.py` (the action's required and optional
  fields).
- `gateway_operation_shape.validate_operation_shape` and `derived_scopes` for the
  action.
- Destination routing for the action.
- Supervisor dispatch (`gateway_operation_process.supervise_operation` /
  `_run_agent`) to launch the connector's MCP server under the grant and capture
  a receipt.

This touches the core gateway, which is under active development. It is left as a
coordinated increment so it lands with, not across, that work. The connector
layer above is the fixed target it builds toward, and its tests hold the shape.

## License

OP connectors are proprietary and never convert to open, unlike the public data
packs. `build_op_operation` enforces the license class on every operation.
