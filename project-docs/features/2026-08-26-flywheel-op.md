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
nature, so they cannot be packs. Their home is the gateway-operations plane.

## Why it rides the plugin plane (and not a new action)

The operations plane already has a complete, tested path for invoking a named
tool on a named MCP server under a one-use grant: the plugin plane.

- `plugin.register` records an MCP stdio server by argv (`plugins.register_mcp`).
- `plugin.probe` spawns it and lists its real tools (`plugins.probe_plugin`).
- `plugin.call` invokes one tool with arguments. The wired path is
  `/api/plugins/call` -> `authorize_gateway_operation` (consumes the grant) ->
  `dispatch_builtin` -> `plugins.call_plugin` -> a real MCP `tools/call`, under a
  restricted child environment, the secret boundary, and a receipt. The gateway
  derives the scopes `write | exec | network | plugin` for the call.

An offensive tool IS an MCP stdio server (ORCA `orca-mcp`, Array
`python -m red_team_platform.mcp_server`). So OP rides `plugin.register` /
`plugin.probe` / `plugin.call` rather than adding a parallel `op.invoke` action
that would duplicate `plugin.call` and cut into the actively developed durable
`/api/agent` path. Nothing in the core gateway changes.

## What OP adds on top

`harness/flywheel_op.py` and `tests/test_flywheel_op.py`:

- `OPConnector`: one tool on the operations plane, with its MCP server argv, the
  scopes it actually uses (least privilege), whether it must run under
  containment, whether its MCP surface is live today (`mcp_available`), its
  proprietary license class, and a `does_not_prove` line.
- `OP_REGISTRY`: the six tools. ORCA (`orca-mcp`) and Array
  (`python -m red_team_platform.mcp_server`) have live MCP surfaces today;
  Isomorph, Sofer, Bounds, and Phantom are declared with `mcp_available=False`
  until their surface is wired, stated honestly rather than pretended-ready. A
  connector with no server argv cannot be registered, probed, or called.
- `build_op_registration` / `build_op_probe` / `build_op_call`: build the exact
  `plugin.register` / `plugin.probe` / `plugin.call` operations that mount and
  invoke a connector. Each is validated by the real `canonicalize_operation`, so
  an OP-emitted operation is a genuine gateway operation the existing pipeline
  runs, not a bespoke shape nothing consumes. Names are namespaced `op-<id>` so
  they never shadow a bundled lane or the builtin tool set.
- `canonical_op_call`: returns the real `CanonicalOperation` for an invocation,
  carrying the gateway's digests, destination (`kind: plugin`, `ref: op-<id>`),
  and derived scopes. This is the proof that OP is connected.

OP is what the generic plugin plane does not carry: a proprietary license class
that never converts to open (unlike the public data packs), a containment
requirement for anything that executes or reaches the network, and a
`does_not_prove` line per connector. The OP scope set is drift-guarded against
the gateway's own scope vocabulary by a test.

## Honest boundary

- The tool's own MCP server must exist and be importable for a live call; the
  four `mcp_available=False` connectors register and probe only once their server
  ships. OP does not fake a server.
- Every OP invocation runs under the plugin.call grant (`write | exec | network |
  plugin`), which is the plane's grant, a superset of a connector's declared
  least-privilege scopes. The declared scopes state intent; the enforced grant is
  the plane's.
- A desktop "Operations" destination that drives these registrations and calls
  from the UI is a separate front-end increment; it changes the desktop's
  asserted destination count and is left to land with that UI work.

## License

OP connectors are proprietary and never convert to open, unlike the public data
packs. `flywheel_op.py` enforces the license class on every connector and every
built operation.
