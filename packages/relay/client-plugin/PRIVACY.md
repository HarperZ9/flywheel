# Privacy

Relay runs on your computer. The publisher operates no backend for this package and receives nothing from it.
The connected client and its model see tool arguments and results under that client's terms.
No model is included. The local model servers and any hosted model API you configure belong to you or your provider.
A grant in the plugin settings is not an operating-system sandbox. Do not connect private folders to an untrusted client. Stop the client to disconnect.

## Summary

Relay reads files in the project folder you choose. File changes and command execution stay off unless you turn them on.
Chat and agent runs send your prompt and the project text a run reads to the model servers on your computer at
`127.0.0.1:8765` and `127.0.0.1:11434`. When you set a hosted provider and a call asks for online tiers, they also go to
that provider's API or the gateway URL you set, with the API key from the plugin settings. Relay reads no API key from
your computer's environment. Relay collects no usage statistics.

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

## Retention and support

Run records stay in memory until the server stops, unless `RELAY_RUN_ROOT` names a folder, where they stay until you
delete them. File changes stay in your project until you change them. Your hosted model provider's privacy policy covers
what you send to it. Support and security reports: https://github.com/HarperZ9/relay/issues
