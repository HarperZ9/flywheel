# Privacy

Plexus runs on the user's computer. The publisher operates no backend for this package.
The connected client and its model can see tool arguments and results under that client's terms.
No model is included. Any model endpoint configured by the user belongs to that user.
Local access is granted to the running process by the operating system; a client permission dialog is not an OS sandbox.
Do not connect private stores or directories to an untrusted client. Stop the client process to disconnect.

## What this plugin runs and handles

**Hooks.** This plugin has no hooks.

**MCP server.** The plugin starts one local server named `plexus`. Claude Code runs it with this command:

`python3 -I -S -B ${CLAUDE_PLUGIN_ROOT}/server/serve.py`

`${CLAUDE_PLUGIN_ROOT}` is the folder where Claude Code installed the plugin. `-I` makes Python ignore `PYTHON*` environment variables and the user's site folder. `-S` skips the `site` module. `-B` stops Python from writing bytecode cache files. The command has no `${user_config.*}` values, because Plexus needs no settings. The server talks to Claude Code only through its standard input and output.

**Network.** Plexus opens no network connection. Its code imports no networking module and starts no other program.

**Files read.** Plexus reads the tool manifests built into its own code. When you or the model name a folder in a call, it also reads the `*.interop.json` files in that folder.

**Files written.** Plexus writes no file and no folder. Each answer is built in memory and returned to Claude Code. Nothing stays after the call returns.

**Environment variables and credentials.** Plexus's own code reads no environment variable and no credential. The shared launcher `server/serve.py` names `MNEME_STATE` and `RELAY_MCP_ROOT`, but only inside branches that run for the Mneme and Relay packages. The Plexus package never reaches them.

Python's standard library reads six variables while the server starts. The launcher parses its command line with `argparse`. That module reads `COLUMNS` and `LINES` to size help and error text for the terminal. It looks up message translations through `gettext`, which reads `LANGUAGE`, `LC_ALL`, `LC_MESSAGES` and `LANG`. These values only set text width and language. Plexus does not store them or send them anywhere. A trace of the packaged server through `initialize`, `tools/list` and every tool found no other read.

## What it reads, stores and sends

Plexus reads its built-in tool manifests and, when a call names one, a folder of
`*.interop.json` manifests. It stores nothing, opens no network connection and starts
no process.

## Retention and support

Plexus keeps no data after a call returns. Support and security reports:
https://github.com/HarperZ9/plexus/issues
