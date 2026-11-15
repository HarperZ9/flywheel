# Learn local client package

Learn plans study sessions, records your own practice answers and tells you what to review next. It stops at graded work and never answers an assessment for you.

## Try it

- Create a study session for linear algebra with three objectives.
- Record my practice answer for the eigenvalues objective as incorrect.
- Which objectives are due for review today?

## Details

The source ZIP includes the tool source and one scoped skill. It requires an
installed Node.js 20+; this advanced source package is not self-contained.
Extract it to a persistent folder. Claude Code can load that plugin folder;
Codex-compatible loaders use plugin.json and mcp.json. For a generic local MCP
client, replace the plugin-root token with the absolute extraction path and
select the absolute runtime executable in that client's settings. Keep arguments
as a JSON array. This package never changes client settings automatically.

Tutor plan and record tools write only inside the Learn state folder. A session stores your own practice attempts. No tool answers certified or graded assessments, and live course actuation stays on the operator-driven CLI.

The connected client supplies the model and pays any model-provider charges.
There is no publisher-hosted inference, relay or account requirement. Installing
a plugin does not authorize network calls, execution, publishing or production
deployment. Local MCP support differs between clients; ChatGPT cloud and Claude
web connections and marketplace acceptance are not established by this archive.

Build locally with Python 3.11+:

```sh
python scripts/build_client_plugin.py --mode dev --out ../client-artifacts
```

Development filenames include -dev. Their source receipt records the base commit
and every payload hash. They are not previously published bytes even when their
embedded version matches a release. Release mode requires a clean checkout,
an exact source tag and a version ending in .0; the ordinary tool release gates
still apply. Builders refuse to overwrite existing archives.

A Windows x64 package can also include the reviewed Node v24.21.0 runtime:

```sh
python scripts/build_client_plugin.py --mode dev --out ../native-client-artifacts --node-runtime /path/to/reviewed/node
```

The runtime folder must contain node.exe and LICENSE matching the pinned hashes.
The builder downloads nothing. This emits a ZIP and a Claude Desktop MCPB with
the same source and runtime bytes. No separate Node installation is needed for
those Windows x64 artifacts. RUNTIME.json identifies the upstream archive and
license hashes. Other platforms, installation in actual clients and marketplace
approval need separate validation. The runtime is not a model.
