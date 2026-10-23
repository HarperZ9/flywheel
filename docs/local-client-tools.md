# Use bundled Articulate tools from a local client

Flywheel's native **Plugins** view offers a configuration preview for the
bundled Articulate text tools. It is available even when the gateway is offline.
Flywheel remains the full native application; this connection lets another
local client use its bundled text tools with the model that client already uses.
This connection adds no model or publisher compute service. The calling client and
model retain their own data handling and costs.

1. Open **Plugins** in the installed Flywheel app and select **Connect a local client**.
2. Confirm that the preview found the bundled engine. A missing bundle disables
   copying; install or repair Flywheel with its engine, then reopen Plugins.
3. Select **Codex (TOML)** or **MCP JSON** and review the entry.
4. Choose **Copy configuration**, then add the entry using the target client's
   documented configuration procedure. Merge it beside your other entries under
   a server name of its own.
5. Run that client's connection diagnostics and check the exposed tool list
   before sending text. The diagnostics confirm the connection works.

The command is the absolute bundled executable resolved by the native app,
with arguments `--bundled-lane-mcp articulate --local-only`, and that bundled
executable is the only command it runs. The profile exposes operations on
supplied text: local review and the calling-model edit-plan/edit-submit
protocol. File tools, command execution and network backends stay off this
profile. The accepted Articulate 0.6.0 source checks ordered protected spans and
lexical modal, scope and negation features, which catch a rewrite that drops a
"must" or a "not"; meaning and facts still need a reader. Local protocol state
and edit receipts are separate from filesystem tool grants.
The preview holds the command and its arguments alone: credentials, provider
URLs, gateway pairing tokens and approval grants stay out of it. Its one side
effect is a clipboard write when you choose Copy configuration; other clients'
files, processes, listeners and tunnels stay as they were.

## Configuration formats and acceptance boundary

The exported shapes were checked on 2026-09-30 against the official
[Codex MCP configuration reference](https://developers.openai.com/codex/mcp)
(`mcp_servers.<name>` with `command` and `args`) and the MCP project's
[local-server guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers)
(`mcpServers` JSON with `command` and `args`). Each client documents its own
configuration format, so check yours against these two shapes.

The preview targets local clients; a remote connector, such as one for the
ChatGPT website, is a separate design. Source and widget checks cover
formatting, restricted arguments, absence handling and copying through a fake
clipboard. Frozen binary startup, restricted-tool behavior and installed-client
acceptance are separate release gates, which is why the native preview shows
**Connection not tested** when it finds a bundled engine.

To check this UI from a Flutter development environment, run from `desktop/`:

```text
flutter test test/client_connection_preview_test.dart test/client_connection_panel_test.dart
flutter analyze
```
