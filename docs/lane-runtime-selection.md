# Lane Runtime Selection

Flywheel lane launch selection is controlled by the local lane registry at
`FLYWHEEL_HOME/lanes.json`. The legacy `profile` field is install provenance
only. It does not select the runtime used for MCP calls.

Add `runtime_profile` to select a runtime explicitly:

```json
{
  "index": {
    "runtime_profile": "package",
    "runtime_version": "2.12.0",
    "runtime_python": "<absolute path to the pinned Python runtime>"
  }
}
```

`runtime_profile` accepts:

- `auto`: preserve the legacy behavior. A source checkout wins when present,
  otherwise Flywheel uses the installed package command.
- `source`: require the declared source checkout. Missing source fails with
  `source_runtime_missing`.
- `package`: require the installed package runtime. Missing or mismatched package
  runtime fails with a named runtime error instead of falling back to source.

For Python package lanes, `runtime_python` may point at an operator-selected
Python executable. Flywheel launches that runtime with `-I -m <lane module>` and
does not add a source checkout `cwd` or `PYTHONPATH`. `runtime_version` is the
accepted package pin for that selected runtime; it may differ from the historical
version declared in `harness/lanes_registry.py`.

`flywheel lanes` and `/api/lanes` report selected profile/runtime, declared and
runtime-expected versions, observed package version, source/package availability,
sanitized launch shape, and mismatch codes. Public version fields only contain
validated package-version strings. Malformed declared, expected, installed, or
source versions are reported as `null` with a named mismatch code. With
`probe=False`, capability is reported as unprobed and no lane MCP server is
spawned. With `probe=True`, Flywheel probes the selected runtime and records only
bounded capability metadata: tool count and a digest of sorted tool names.

Status details use stable codes for malformed runtime config and probe failures.
They do not echo raw runtime registry values, child process exceptions, health
tool response text, local executable paths, or environment values.

## Lane environment

Lane code runs with a minimal environment, not the gateway's whole one. This
covers the MCP server launch of every pip and npm lane and every other child
process that runs lane code: the index, chorus, gather, crucible and telos CLIs
and kernels the gateway calls, index router jobs, the canon context child, the
package version probe, and `pip install` or `npm install -g` of a lane (whose
build backend and install scripts are lane-supplied code). Each gets three sets
of variables and nothing else:

- The base allowlist in `harness/lane_env.py`: what a Python or Node process
  needs to start on Windows, macOS and Linux (`PATH`, system roots, temp and
  home directories, locale, CA bundle paths, the Python import path
  `PYTHONPATH`, `PYTHONHOME` and `PYTHONUSERBASE`, `FLYWHEEL_HOME` and the
  workspace roots).
- The non-secret configuration names the lane declares in `env_vars` in
  `harness/lanes_registry.py`, such as `INDEX_CACHE_DIR`, `CANON_BLOCKS_DIR` or
  `RELAY_RUN_ROOT`. A test fails if a declared name looks like a credential.
- Names the operator grants to that lane with `env_allow` in the registry:

```json
{
  "forum": {
    "env_allow": ["ANTHROPIC_API_KEY"]
  }
}
```

A provider key reaches a lane's environment only through `env_allow`, one lane
and one name at a time. An `env_allow` entry that is not a plain variable name,
or an `env_allow` that is not a list, is dropped and reported as
`env_allow_invalid`; the lane still launches. `flywheel install` merges its
fields into an existing registry row, so a re-install keeps `env_allow` and
`runtime_profile`. Proxy variables (`HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`)
and package index settings (`PIP_INDEX_URL`, `PIP_EXTRA_INDEX_URL`,
`NPM_CONFIG_REGISTRY`) are not in the base set because each can carry a user
name and password; grant them by name to the lanes that need them. The bundled
payload path already used its own minimal environment and is unchanged. The
in-repo bundled lanes (`local-model`, `writing`) run Flywheel's own modules and
still inherit the gateway environment outside a frozen build.

These lanes read a credential for some of their features. Without a grant, that
feature runs as if the variable were unset.

| Lane | Credential names it reads | Feature | `env_allow` to add |
| --- | --- | --- | --- |
| forum | `ANTHROPIC_API_KEY` | the Anthropic API executor (`--api`, real model rooms) | `["ANTHROPIC_API_KEY"]` |
| accountable-surface | `ANTHROPIC_API_KEY` | model calls from the world server | `["ANTHROPIC_API_KEY"]` |
| relay | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GLM_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `<PROVIDER>_PROVIDER_KEY`, `<PROVIDER>_CLOUD_KEY` | the online tier (`online=true`) | the names for the providers you use |
| mneme | `OPENAI_API_KEY` (the default `api_key_env`) | model-assisted extraction (`llm_extract`) | `["OPENAI_API_KEY"]` |
| gather | `GATHER_API_TOKEN` and the credential names a pilot manifest declares | `gather api` and credentialed pilot sources | the names the manifest declares |

On the admitted `agent.run` MCP path the gateway rebuilds a lane launch from its
strict plugin set (seven names on Windows, five on POSIX) plus the launch's own
`PYTHONPATH`. `env_allow` grants never reach that path, and never reach a stored
discovery receipt.

Stated limits. This boundary covers environment variables only. A lane still
runs unsandboxed as the same operating-system user as the gateway, so it can
read any file that user can read, including `~/.flywheel/gateway.token`, the
receipt signing key under `~/.flywheel/keys` and other credential files in the
home directory. The integrity label on the token and the key stops the
low-integrity command sandbox on Windows, and not a lane, which runs at medium
integrity. A lane can also write `~/.flywheel/lanes.json` and grant itself an
`env_allow` name that takes effect on its next launch. Closing those needs a
filesystem boundary for lanes, which Flywheel does not have yet.

## Installing a lane

`flywheel install [--lanes all|NAME[,NAME...]] [--profile package|source]` parses
its arguments strictly: `-h` and `--help` print the usage and exit 0, and any
other argument it does not know, a flag without its value, a flag given twice, an
unknown profile or an empty lane list prints the error and the usage and exits 2
before anything installs. The gateway's `POST /api/lanes/install` calls the same
`install_lane`.

A pip lane installs with `<python> -m pip install`, where `<python>` is the
interpreter running Flywheel, or the lane's `runtime_python` for a package install
when the registry row pins one. A frozen build has no interpreter of its own, so a
pip install there needs that pin and otherwise answers
`pip_interpreter_unavailable`. An npm lane resolves `npm` through the shared
program lookup below (`npm.cmd` on Windows) and answers `npm_unavailable` when no
safe npm exists. The package manager runs in a new empty folder with the lane
environment (`harness/lane_install.py`).

## Program lookup

Every program the engine starts by a bare name (git, lean, node, npm, a lane
console script, an endpoint CLI, an MCP, LSP, DAP or ACP server, a hook or gate
command) resolves through `harness/safe_program.py`, which wraps the vendored
safe_spawn helper (`harness/_vendor/safe_spawn.py`, pinned by `VENDORED.sha256`).
The lookup walks only absolute PATH entries, skips any entry that reaches the
current folder or the folder the child will run in (directly, below it, or through
a link or junction), refuses a name holding a colon such as `C:tool`, and on
Windows prefers a `.exe` anywhere on PATH over a batch shim. A batch-file target
whose arguments hold a cmd.exe metacharacter is refused before it starts. A shell
the engine starts, including the oracle's, gets `safe_program.shell_env()`: PATH
keeps what the lookup keeps, and on Windows `NoDefaultCurrentDirectoryInExePath=1`
stops cmd.exe searching its own folder first. Windows system tools come from the
System32 folder (`safe_program.system_tool`). On Windows the lookup reads the
parent's PATH, as CreateProcess does; on POSIX it reads the PATH handed to the
child, as subprocess does.
