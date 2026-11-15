# Local context and privacy

Canon reads the database and scope explicitly selected at launch. With the ingestion grant enabled, it stores supplied context in that database. Query and get return selected stored content to the connected client. The client's model provider and privacy policy determine how that client handles results.

Canon's client package supplies no telemetry, hosted storage, network listener or model compute. Context content is untrusted data. Secret scrubbing reduces accidental exposure but does not establish that content is safe to share. Review sensitive inputs and retrieved material before sending them to a provider.

Stored data persists until the owner removes it through a separate authorized workflow. This client does not expose purge. Backups, exported results and provider copies are outside its removal boundary. Scope IDs are selectors, not authentication. Filesystem permissions and the host account remain part of the security boundary.

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

## Retention and support

Canon keeps no copy of your data outside the database you selected. Content stays in
that database until you delete the file. This plugin has no purge tool; the separate
Canon command-line tool can purge records if you install it.
Canon sends nothing over a network and collects no usage statistics.

Support and security reports: https://github.com/HarperZ9/canon/issues
