# Frozen Gateway MCP Entry Addendum

Date: 2026-09-15

This addendum extends `SPEC-receipt-mcp-parity-20260915.md` to the frozen
Flywheel gateway executable. The receipt MCP parity work is accepted only when
the compiled gateway can serve the same native MCP tool surface as the source
entry point.

## Requirement

`packaging/gateway_entry.py` must support an explicit frozen `--mcp` mode that
delegates to `harness.local_agent_cli --mcp` with the same `--root` and
`--run-root` startup arguments. This is a startup mode of the executable, not a
new gateway HTTP route and not a new authority layer.

The mode is bounded:

- `flywheel-gateway --mcp` starts the existing local MCP stdio server.
- `flywheel-gateway --mcp --root <repo> --run-root <run-root>` uses the same
  configured repository root and run root as the source MCP entry point.
- Tool calls still accept only the tool's declared arguments. Receipt proof
  calls do not receive path/root arguments.
- Ambiguous combinations with bundled Relay child mode, gateway server mode, or
  other local-agent modes are rejected instead of being forwarded silently.
- Normal gateway startup and the exact bundled Relay child mode stay unchanged.

## Freeze Requirement

The PyInstaller spec must statically include the real Flywheel MCP modules from
this repository, including `harness.local_mcp` and `harness.receipt_operations`.
The spec must fail if `harness.local_mcp` resolves outside the repository's
`harness/` package before analysis. This keeps the frozen executable from
shipping a gateway that can answer HTTP receipt proof requests but cannot start
the native MCP receipt surface.

## Does Not Prove

This mode proves only that the frozen executable carries and can start the same
bounded MCP receipt-proof surface. It does not prove receipt semantic
correctness, evidence completeness, release readiness, installed acceptance, or
third-party use.
