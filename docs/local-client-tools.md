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
   documented configuration procedure. Preserve other entries; do not replace
   an existing configuration wholesale or add a duplicate server name.
5. Use that client's connection diagnostics and inspect the exposed tool list
   before sending text. Finding an executable and copying a configuration do
   not establish a working connection.

The command is the absolute bundled executable resolved by the native app,
with arguments `--bundled-lane-mcp articulate --local-only`. It never falls back
to Python, Node or a command on PATH. The profile exposes operations on supplied
text, including local review and the calling-model edit-plan/edit-submit
protocol. It does not expose file tools, command execution or network backends.
The accepted Articulate 0.6.0 source checks ordered protected spans and lexical
modal, scope and negation features. These checks do not prove semantic
equivalence or factual correctness. Local protocol state and edit receipts are
distinct from filesystem tool grants.
The preview contains no credentials, provider URLs, gateway pairing tokens or
automatic approval grants. It does not read or modify another client's files,
start a process, open a listener or establish a tunnel. Clipboard access happens
only when the user chooses Copy configuration.

## Configuration formats and acceptance boundary

The exported shapes were checked on 2026-09-30 against the official
[Codex MCP configuration reference](https://developers.openai.com/codex/mcp)
(`mcp_servers.<name>` with `command` and `args`) and the MCP project's
[local-server guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers)
(`mcpServers` JSON with `command` and `args`). JSON support depends on the
target local client's configuration format; this is not a universal MCP
configuration standard.

This preview does not claim compatibility with the ChatGPT website or provide
a remote connector. Source and widget checks cover formatting, restricted
arguments, absence handling and copying through a fake clipboard. Actual frozen
binary startup, restricted-tool behavior and installed-client acceptance are
separate release gates. The native preview always says **Connection not tested**
when it finds a bundled engine.

To check this UI from a Flutter development environment, run from `desktop/`:

```text
flutter test test/client_connection_preview_test.dart test/client_connection_panel_test.dart
flutter analyze
```
