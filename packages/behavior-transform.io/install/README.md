# Installing behavior-transform natively

behavior-transform is the IO-boundary safety layer: it blocks secrets, gates
`exec`/`fetch`/`read`/`search`, and requires a receipt at the model boundary.
The **host is flywheel** — flywheel distributes and manages this connector, and
every harness below loads the same stdlib-only MCP server (`tools/behavior_transform_mcp.py`).

The server needs only Python on `PATH`. No dependencies.

## Any MCP harness — ChatGPT, OpenCode, ZCode

All three consume a standard MCP stdio server. Point them at
[`install/mcp.json`](mcp.json), or add this block to the harness's MCP config:

```json
{
  "mcpServers": {
    "behavior-transform": {
      "command": "python",
      "args": ["tools/behavior_transform_mcp.py"]
    }
  }
}
```

- **ChatGPT** — add as a connector (Developer mode / MCP), stdio transport.
- **OpenCode** — add under `mcp` in the OpenCode config.
- **ZCode** — add under the harness MCP servers list.

The server exposes three tools: `behavior_transform.status` (which operations
require a receipt), `behavior_transform.doctor` (readiness: MATCH/DRIFT/
UNVERIFIABLE), and `behavior_transform.demo` (an offline boundary-receipt
demonstration).

## Claude Code — plugin (hooks + MCP)

Claude Code gets more than the MCP tools: the existing `hooks/` are Claude Code
hooks, so the plugin wires the safety membrane directly into the tool loop
(secret blocking, safe-exec/fetch/read/search redirects, pre-model gate).

Install the plugin from [`install/claude-code/`](claude-code/) — its
`.claude-plugin/plugin.json` declares both the MCP server and the bundled hooks.

## Verify after install

Call `behavior_transform.doctor` (or run `python tools/behavior_flagship.py
doctor --json`). A healthy install returns `status: MATCH`.
