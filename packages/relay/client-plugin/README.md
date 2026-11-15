# Relay client package

Relay connects your assistant to a local coding agent that works in a project folder you choose. The agent uses a model server on your computer, such as Ollama, or one hosted model API you set up. File writes and command execution stay off until you allow them.

## Try it

- Check which local model tiers Relay can reach.
- Ask my local model to explain src/main.py.
- Start a background run that lists the TODO comments in this project, then show its result.

## Settings in Claude Code

Claude Code asks for these values when you enable the plugin. Change them later in `/plugin`, then restart the connection.

| Setting | Default | What it does |
| --- | --- | --- |
| Project folder | required | The folder Relay works in. Runs and file tools stay inside it. |
| Allow file changes | off | Lets approved runs change files inside the project folder. |
| Allow command execution | off | Lets runs start shell commands. Also turns on file changes. Commands can reach paths outside the project folder with your own permissions. |
| Hosted model provider | empty | Empty means local model servers only. Otherwise one of `codex` (the OpenAI API), `claude` (the Anthropic API), `gemini`, `deepseek` or `glm`. |
| Hosted model API key | empty | Stored by Claude Code as a sensitive value. Sent only to the hosted provider or the gateway URL. |
| OpenAI-compatible gateway URL | empty | Sends hosted calls to this URL instead of the provider's own API. |
| Hosted model name | empty | Empty uses Relay's default model for that provider. |

A tool call can ask for less than these settings allow, never more. A declared grant is not an operating-system sandbox. Hosted calls may incur charges from your provider.

## What this plugin runs and handles

**Hooks.** This plugin has no hooks.

**MCP server.** One stdio server named `relay`. Claude Code starts it with this command:

```
python3 -I -S -B ${CLAUDE_PLUGIN_ROOT}/server/serve.py --write=${user_config.write} --exec=${user_config.exec} --api-provider=${user_config.api_provider} --api-base-url=${user_config.api_base_url} --api-model=${user_config.api_model} --no-cli-tiers
```

`${CLAUDE_PLUGIN_ROOT}` is the folder Claude Code installed the plugin in. Each `${user_config.<key>}` is the plugin setting with that key: `project_folder`, `write`, `exec`, `api_provider`, `api_key`, `api_base_url` or `api_model`, described under Settings in Claude Code in README.md. `--write` and `--exec` receive `true` or `false`. Two settings travel in the server's environment instead of its arguments: the project folder as `RELAY_MCP_ROOT`, and the API key as `RELAY_API_KEY`. The key never appears in the command line. `--no-cli-tiers` leaves out Relay's agent-CLI tiers, so this plugin never starts the `claude` or `codex` programs and never uses a sign-in saved for them. `-I -S -B` makes Python ignore `PYTHON*` variables and site packages and write no bytecode files.

**Network.** Relay opens a connection only when a tool call needs a model, or to check one:

- Local model servers, on every chat, run and health check: `http://127.0.0.1:8765` (Relay's own model server: `/health`, `/generate`) and `http://127.0.0.1:11434` (Ollama: `/api/tags`, `/api/chat`). These addresses are fixed and stay on your computer. Relay sends the conversation: the system prompt, your prompt, project text the run read, and tool results.
- One hosted model API, only when you set a hosted provider and a call passes `online: true`. Relay tries the local servers first and uses the hosted API when they are down or the call names it. Relay sends the conversation, including project text the run read, and your own key from the sensitive Hosted model API key setting. Each provider goes to one host:
  - `codex`: `api.openai.com` (`/v1/chat/completions`), key in the `Authorization` header.
  - `claude`: `api.anthropic.com` (`/v1/messages`), key in the `x-api-key` header.
  - `gemini`: `generativelanguage.googleapis.com` (`/v1beta/models/<model>:generateContent`), key in the URL, as that API requires.
  - `deepseek`: `api.deepseek.com` (`/v1/chat/completions`), key in the `Authorization` header.
  - `glm`: `open.bigmodel.cn` (`/api/paas/v4/chat/completions`), key in the `Authorization` header.
  - With a gateway URL set, Relay sends to `<gateway URL>/chat/completions` instead, and the key goes only there.

  A health check for a hosted tier only tests that a key is set and sends nothing.
- Shell commands, only when command execution is allowed. The `run` tool, `test_cmd` and `check` start commands through your system shell in the project folder. A command can reach any network address and any path your account can.

Relay opens no listening port and sends no usage data. `relay.status` and `relay.doctor` contact no model.

**Files written.**

- Project files inside the project folder, only when file changes or command execution are allowed. They stay until you change them. Relay's file tools never write `.git`, agent settings such as `.claude` or `.mcp.json`, or Relay's own stores.
- Anything a shell command writes, only when command execution is allowed.
- Background run records stay in memory and are gone when the server stops. If `RELAY_RUN_ROOT` is set where Claude Code starts, Relay saves each record as a JSON file in that folder, and it stays until you delete it.

Relay writes nothing else. `local_agent_sessions` only reads sessions saved earlier by the `relay` command-line tool.

**Environment variables and credentials.** The server reads these variables. Claude Code passes them from the environment it was started in, unless the plugin sets them.

- Set by this plugin: `RELAY_MCP_ROOT` (project folder) and `RELAY_API_KEY` (API key). Relay removes `RELAY_API_KEY` from its environment after reading it.
- Cleared at startup, so values from your computer are never used: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `GLM_API_KEY`, and for each of `CODEX`, `CLAUDE`, `GEMINI`, `DEEPSEEK` and `GLM` the variables `<NAME>_PROVIDER_BASE_URL`, `<NAME>_PROVIDER_KEY`, `<NAME>_CLOUD_BASE_URL`, `<NAME>_CLOUD_KEY` and `<NAME>_MODEL`. Relay then sets only the ones your hosted settings need.
- `RELAY_RUN_ROOT`: folder for saved background run records. Unset means memory only.
- `RELAY_SESSION_DIR`: folder of saved sessions that `local_agent_sessions` reads. Unset means a `relay/sessions` folder under `LOCALAPPDATA` or `USERPROFILE` on Windows, `HOME` on macOS, or `XDG_DATA_HOME` or `HOME` on Linux.
- `RELAY_ENV_FILE`: the settings file of Relay's separate remote server. Relay reads only the name, so its file tools never read or write that file. It does not open the file.
- `RELAY_CHILD_ENV`: extra variable names to pass to shell commands.
- Passed on to shell commands, and not otherwise used: the system variables a program needs, such as `PATH`, `TEMP`, `HOME`, `USERPROFILE`, `APPDATA` and `LANG`, and toolchain variables such as `VIRTUAL_ENV`, `JAVA_HOME` and `CARGO_HOME`. API keys are not passed on unless `RELAY_CHILD_ENV` names them.

Relay uses one credential: the Hosted model API key setting. It reads no API key and no saved sign-in from your computer. A shell command, which runs only when command execution is allowed, runs as you and can use anything your account can.

## Data and network

| Question | Answer |
| --- | --- |
| What it reads | Files in the project folder that a run opens, the plugin settings, and the variables listed above |
| What it stores | File changes in the project folder when allowed. Run records in memory, or in `RELAY_RUN_ROOT` when you set it |
| Network calls | Local model servers at `127.0.0.1:8765` and `127.0.0.1:11434`. With a hosted provider and `online: true`, that provider's API or your gateway URL. With command execution, any address a shell command contacts |
| Telemetry | None |
| Retention | Run records last until the server stops unless `RELAY_RUN_ROOT` is set. Hosted providers keep what you send under their own policies |

Tool results go to the connected client, and that client's model provider handles them under its own privacy policy. See [PRIVACY.md](PRIVACY.md).

## Other clients

The source ZIP requires Python 3.11 or newer. Extract the entire archive, then point a local stdio MCP client at an absolute Python executable with arguments `-I -S -B /absolute/path/server/serve.py`. Set `RELAY_MCP_ROOT` to an absolute existing project directory in the client's server environment. The plugin folder and the source ZIP carry their own copy of the Relay modules the server loads under `server/src`, so the server never loads code from outside the folder it was installed in. If that copy is missing, the server prints one line asking you to reinstall the plugin and exits.

The Windows x64 native ZIP includes Python and needs no separate Python or Node installation. Extract everything and use the absolute `server/relay-local.exe` path. A client supporting binary MCPB extensions may open the matching MCPB, which offers the same settings as Claude Code. Both archives use identical executable bytes.

Grants come from explicit launch arguments: `--write=true|false` and `--exec=true|false`, or `--allow-write` and `--allow-exec`. Missing, malformed or unresolved values cannot enable a grant, and `RELAY_ALLOW_WRITE` and `RELAY_ALLOW_EXEC` in the environment are ignored. A hosted model needs `--api-provider=<name>` with the key in `RELAY_API_KEY`, plus optional `--api-base-url` and `--api-model`. These launches keep the agent-CLI tiers unless you add `--no-cli-tiers`: with command execution and `online: true`, Relay may then start the `claude` or `codex` CLI, which signs in with its own saved account.

Portable `plugin.json` and `mcp.json` and Codex's `.codex-plugin/plugin.json` use `${PLUGIN_ROOT}` and the `${RELAY_MCP_ROOT}` placeholder, which the client must resolve to an explicit path. Replace `python3` with an absolute trusted Python path if needed. No client configuration is modified automatically.

## Troubleshooting

An absent project folder, relative path, linked path component, unknown launch argument, unknown hosted provider, malformed gateway URL, or a gateway URL or model name without a provider stops startup. Correct the setting and restart the client. After a permission refusal, decide whether to change the launch grants. Check `SHA256SUMS` before extracting and keep the full package together. Unsigned Windows binaries can trigger platform warnings.
