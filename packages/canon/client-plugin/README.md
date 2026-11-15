# Canon local client

Canon keeps project context in a local database you choose and lets your assistant search and read it, scoped to one workspace and project.

## Try it

- Check that the Canon context store is healthy.
- Search Canon for decisions about the release checklist.
- Show the full Canon record behind the first search result.

## Details

Canon supplies local context tools to an MCP client using the model the operator chooses. It includes no model, inference endpoint, network listener or background service.

## Bind the connection

Supply `--context-db` with an absolute SQLite file path whose parent exists, and `--workspace-id` and `--project-id` with explicit nonempty IDs. Every request stays bound to that database and scope. IDs select data; they do not authenticate a user. Linked paths are refused, but path validation is not an OS sandbox.

The default profile exposes health, query and get. Add `--context-write=true` or `--allow-context-write` to permit ingestion. A tool call or environment variable cannot grant writes. Purge is unavailable in this client, including when the legacy purge environment variable is present.

Read access requires an existing identity-bearing Canon database. Reads use an in-memory snapshot capped at 256 MiB and require Python's SQLite `deserialize` support. Reads create no SQLite sidecar file and work in DELETE or WAL journal mode, also while another process changes the mode; a request retries for up to 5 seconds while a writer commits, then reports the store busy. This client does not repair or migrate the database. A writable launch can initialize a new selected database. See the [client guide](https://github.com/HarperZ9/canon/blob/main/docs/client-packages.md) for configuration and limits.

## Install

The source ZIP requires Python 3.11 or newer. Extract the complete ZIP. Configure a stdio client with a trusted absolute Python executable and arguments `-I -S -B /absolute/path/server/serve.py`, followed by the three binding flags. The plugin folder carries its own copy of the server source under `server/src`, so an install of this folder alone runs; the source ZIP carries the same tree.

In Claude Code, enabling the plugin asks for the database path, workspace ID and project ID, and for **Allow context writes**, which defaults to off. Turn writes on for the first launch when the database does not exist yet. The Claude manifest passes these values as `${user_config.*}` arguments. Portable and Codex manifests use `${PLUGIN_ROOT}` with the placeholders `CANON_CONTEXT_DB`, `CANON_WORKSPACE_ID` and `CANON_PROJECT_ID`; the client must resolve these to explicit argument values. Replace `python3` with a trusted absolute Python path where necessary. No client configuration is edited automatically.

The Windows x64 native ZIP includes the Python runtime. Extract all files and point the client at the absolute `server/canon-local.exe` path with the same binding flags. The MCPB offers the database, workspace and project settings and an **Allow context writes** option that defaults to off. Restart the connection after changing settings. Native ZIP and MCPB contain identical executable bytes.

## What this plugin runs and handles

**Hooks.** This plugin has no hooks.

**MCP server.** The plugin starts one local MCP server named `canon`. Claude Code runs this command:

`python3 -I -S -B ${CLAUDE_PLUGIN_ROOT}/server/serve.py --context-db ${user_config.context_db} --workspace-id ${user_config.workspace_id} --project-id ${user_config.project_id} --context-write=${user_config.context_write}`

`${CLAUDE_PLUGIN_ROOT}` is the folder where Claude Code installed the plugin. The four `${user_config...}` values are the answers you give when you enable the plugin: the database file path, the workspace ID, the project ID, and whether writes are allowed. Writes start off. The server talks to Claude Code over standard input and output only.

**Network.** The server opens no network connection. It sends nothing to the author or to any other service.

**Programs.** The server starts no other program.

**Files it reads.** It reads the SQLite database file you chose. When that database uses WAL mode, it also reads the matching `-wal` file next to it.

**Files it writes.** With writes off, it writes no file. With writes on, it writes context you store into the database file you chose. While a write runs, SQLite keeps a temporary journal file next to the database (the database name plus `-journal`, or `-wal` and `-shm` in WAL mode). Stored context stays in the database until you remove it. The server keeps no other copy.

**Environment variables and credentials.** Canon's own code reads no environment variables and no credentials. When the server reads its launch arguments, Python's argument parser reads the usual terminal and language settings: `COLUMNS`, `LINES`, `LANG`, `LANGUAGE`, `LC_ALL` and `LC_MESSAGES`. On Windows, Canon loads Python's `ctypes` module for its database file lock. In some Python releases, 3.13.14 among them, loading `ctypes` also reads `APPDATA`, `PYTHONUSERBASE` and `_PYTHON_PROJECT_BASE`; Canon does not use those values. The `-I` flag makes Python ignore its own `PYTHON*` variables.

## Data and network

| Question | Answer |
| --- | --- |
| What it reads | The SQLite database and the workspace and project scope you select |
| What it stores | Context you ingest, in that database, only when writes are allowed |
| Network calls | None. The server opens no socket and runs no other program |
| Telemetry | None |
| Retention | Content stays in your database file until you remove it |

Query results go to the connected client, and that client's model provider handles them under its own privacy policy. See [PRIVACY.md](PRIVACY.md).

## Troubleshooting and limits

A missing binding, relative database path, linked path component, unresolved placeholder or malformed boolean stops startup. Correct the binding and restart the client. A refused tool call returns one fixed code with a short hint and never echoes your arguments or stored text: `ARGUMENT_REFUSED`, `SCOPE_MISMATCH`, `STORE_ID_MISMATCH`, `STORE_BUSY` (retry) or `WRITE_NOT_GRANTED` (turn on **Allow context writes** and restart). Any other failure returns "context request refused or store unavailable". Keep the full archive together and verify its hashes against `SHA256SUMS`.

Local protocol checks do not establish installed-client compatibility, marketplace acceptance or clean-machine compatibility. Unsigned Windows artifacts may receive platform warnings. Build receipts distinguish development and release candidates and record source and native dependency hashes.
