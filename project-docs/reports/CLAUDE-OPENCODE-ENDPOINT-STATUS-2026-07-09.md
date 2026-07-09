# Claude Code and OpenCode endpoint status - 2026-07-09

## Scope

This report records the verified state of the Claude Code and OpenCode harness endpoints for the Codex/Flywheel local-model benchmark program.

Required target model row remains `gpt-5.3-codex-spark`. GPT-5.5 Extra High is allowed for orchestration or extra comparison rows, but it does not replace Spark baseline evidence.

## Endpoint adapter changes

File changed:

- `C:/dev/local-model/harness/endpoints.py`
- `C:/dev/local-model/scripts/run_endpoint_auth_status.py`

Changes:

- Claude Code plan mode now uses deterministic noninteractive flags:
  - `--model {model}`
  - `--effort xhigh`
  - `--permission-mode dontAsk`
  - `--no-session-persistence`
  - `--output-format text`
- Windows CLI resolution now maps:
  - `codex` to `codex.cmd`
  - `claude` to `claude.exe`
- CLI failure reporting now preserves stdout when stderr is empty. This matters because Claude Code emitted the account failure on stdout.
- Claude/Codex account visibility now has a non-secret status receipt command:
  - Claude subscription account: official `claude` CLI / `CLAUDE_CLI`
  - Claude API: `ANTHROPIC_API_KEY`
  - Codex subscription account: official `codex` CLI / `CODEX_CLI`
  - Codex/OpenAI API: `OPENAI_API_KEY`
  - The status command reports only presence, resolved CLI path, backend ladder rows, and next action; it never prints key or token values.
- OpenCode now has a first-class API backend guarded by explicit env configuration:
  - `OPENCODE_BASE_URL`
  - `OPENCODE_PORT`, optional alternative to `OPENCODE_BASE_URL`; resolves to `http://127.0.0.1:<port>`
  - `OPENCODE_USERNAME`, optional; defaults to `opencode`
  - `OPENCODE_PASSWORD`
  - `OPENCODE_SERVER_USERNAME`, accepted packaged-sidecar alias
  - `OPENCODE_SERVER_PASSWORD`, accepted packaged-sidecar alias
  - `OPENCODE_PROVIDER_ID`, optional; defaults to `openai`
  - `OPENCODE_MODEL`, optional; defaults to `gpt-5.3-codex-spark`
  - `OPENCODE_DIRECTORY`, optional; defaults to current working directory
  - `OPENCODE_AGENT`, optional

## Verified OpenCode Desktop API surface

OpenCode Desktop local package:

- Path: `C:/Users/Zain/AppData/Local/Programs/@opencode-aidesktop/OpenCode.exe`
- Version observed from startup logs: `1.17.15`
- Package main entry: `./out/main/index.js`
- Sidecar entry: `out/main/sidecar.js`

Verified sidecar contract from packaged code:

- Desktop starts a local sidecar on `127.0.0.1`.
- Desktop honors `OPENCODE_PORT`.
- Desktop generates a random sidecar password at runtime.
- Sidecar auth uses HTTP Basic auth with username `opencode` by default.
- Server auth env names are `OPENCODE_SERVER_USERNAME` and `OPENCODE_SERVER_PASSWORD`.

Verified API routes from packaged server chunk:

- `POST /session`
- `GET /session`
- `GET /session/status`
- `POST /session/{id}/message`
- `POST /session/{id}/prompt_async`
- `GET /session/{id}/message`
- `GET /provider`
- `GET /config/providers`

Verified prompt payload shape:

```json
{
  "model": {
    "providerID": "openai",
    "modelID": "gpt-5.3-codex-spark"
  },
  "system": "optional system prompt",
  "agent": "optional agent id",
  "parts": [
    {
      "type": "text",
      "text": "prompt text"
    }
  ]
}
```

## Claude/Codex account lane receipt

Command:

```powershell
python scripts/run_endpoint_auth_status.py --out C:/tmp/harness_endpoint_auth_status_20260709.json --markdown-out C:/tmp/harness_endpoint_auth_status_20260709.md
```

Lane contract:

| Lane | Provider | Harness mode | Activation prerequisite |
|---|---|---|---|
| `claude_subscription` | `claude` | `plan` | Official Claude CLI is installed and authenticated in the operator terminal. |
| `claude_api` | `claude` | `api` | `ANTHROPIC_API_KEY` is set in the local secret environment. |
| `codex_subscription` | `codex` | `plan` | Official Codex CLI is installed and authenticated in the operator terminal. |
| `codex_api` | `codex` | `api` | `OPENAI_API_KEY` is set in the local secret environment. |

Security boundary:

- The harness does not collect provider passwords.
- The harness does not read provider token stores.
- The receipt reports whether env vars are set, not their values.
- Subscription sign-in stays inside each official CLI's own auth flow.
- API keys stay in the local secret environment and are consumed only by the endpoint backend selected for that provider.

## Benchmark evidence

Command:

```powershell
python scripts/run_source_mined_backend_matrix.py --providers claude,opencode --allow-online --modes plan --endpoint-model gpt-5.3-codex-spark --max-cases 1 --backend-timeout-seconds 60 --out-root C:/tmp/source_mined_backend_matrix_claude_opencode_spark_n1_v3
```

Artifact:

- `C:/tmp/source_mined_backend_matrix_claude_opencode_spark_n1_v3/20260709_005827/source_mined_backend_matrix.json`
- `C:/tmp/source_mined_backend_matrix_claude_opencode_spark_n1_v3/20260709_005827/source_mined_backend_matrix.md`

Result summary:

| Provider | Requested model | Live | Operational | Skipped | Pass rate | Response rate | Receipt completeness | Mean latency ms | Outcome |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| claude | `gpt-5.3-codex-spark` | true | false | false | 0.0 | 0.0 | 1.0 | 2489 | `claude-plan cli exit 1: Credit balance is too low` |
| opencode | `gpt-5.3-codex-spark` | false | false | true | 0.0 | 0.0 | 0.0 | 0.0 | `no configured endpoint backend for provider=opencode modes=plan` |

Direct probes:

- `C:/Users/Zain/.local/bin/claude.exe -p ... --model sonnet ...` returned `Credit balance is too low`.
- `C:/Users/Zain/.local/bin/claude.exe -p ... --model gpt-5.3-codex-spark ...` returned `Credit balance is too low`.
- `OpenCode.exe --help` and `OpenCode.exe -h` started the Electron app and did not expose a noninteractive CLI help surface.
- Follow-up environment probe after the desktop path was supplied found `OPENCODE_BASE_URL`, `OPENCODE_PORT`, `OPENCODE_PASSWORD`, `OPENCODE_SERVER_PASSWORD`, and `OPEN_CODE_CLI` unset.
- Follow-up process probe found no running `OpenCode` process.

## Follow-up harness patch

The OpenCode adapter now accepts the packaged sidecar env names directly:

- `OPENCODE_SERVER_USERNAME`
- `OPENCODE_SERVER_PASSWORD`

It also derives `OPENCODE_BASE_URL` from `OPENCODE_PORT` when a desktop sidecar is launched with a known port. This closes the harness-side mismatch between the packaged OpenCode server contract and the earlier adapter contract. A running sidecar plus its runtime password is still required before a live benchmark row can be produced.

## Experimental conclusion

Claude Code is wired as a reproducible noninteractive harness endpoint, but the current account path is not operational because the CLI returns `Credit balance is too low`.

OpenCode Desktop is not a terminal CLI endpoint in its installed form. It is now wired as an API-backed endpoint when an OpenCode sidecar/server URL and Basic auth credentials are provided. Without `OPENCODE_BASE_URL` and `OPENCODE_PASSWORD`, the benchmark matrix correctly marks the provider skipped rather than fabricating a result.

## Next native solution

To benchmark OpenCode against local models or Spark, use one of these endpoint forms:

1. Start or expose an OpenCode server/sidecar with known credentials, then run:

```powershell
$env:OPENCODE_BASE_URL='http://127.0.0.1:<port>'
$env:OPENCODE_USERNAME='opencode'
$env:OPENCODE_PASSWORD='<sidecar-password>'
$env:OPENCODE_PROVIDER_ID='openai'
$env:OPENCODE_MODEL='gpt-5.3-codex-spark'
python scripts/run_source_mined_backend_matrix.py --providers opencode --allow-online --modes plan --endpoint-model gpt-5.3-codex-spark --max-cases 1 --backend-timeout-seconds 120 --out-root C:/tmp/source_mined_backend_matrix_opencode_spark_n1
```

Equivalent packaged-sidecar alias form:

```powershell
$env:OPENCODE_PORT='<port>'
$env:OPENCODE_SERVER_USERNAME='opencode'
$env:OPENCODE_SERVER_PASSWORD='<sidecar-password>'
$env:OPENCODE_PROVIDER_ID='openai'
$env:OPENCODE_MODEL='gpt-5.3-codex-spark'
python scripts/run_source_mined_backend_matrix.py --providers opencode --allow-online --modes plan --endpoint-model gpt-5.3-codex-spark --max-cases 1 --backend-timeout-seconds 120 --out-root C:/tmp/source_mined_backend_matrix_opencode_spark_n1
```

2. Configure OpenCode with an OpenAI-compatible local provider pointing at the local `/v1` endpoint, then set `OPENCODE_PROVIDER_ID` and `OPENCODE_MODEL` to that configured provider/model pair.

3. If an official OpenCode CLI is installed separately later, set `OPEN_CODE_CLI` to its noninteractive command. The adapter will fall back to CLI mode when no `OPENCODE_BASE_URL` is present.
