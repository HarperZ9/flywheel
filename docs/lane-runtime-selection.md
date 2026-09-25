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

A pip or npm lane MCP server starts with a minimal environment, not the
gateway's whole one. It receives three sets of variables and nothing else:

- The base allowlist in `harness/lane_env.py`: what a Python or Node process
  needs to start on Windows, macOS and Linux (`PATH`, system roots, temp and
  home directories, locale, CA bundle paths, `FLYWHEEL_HOME` and the workspace
  roots).
- The non-secret configuration names the lane declares in `env_vars` in
  `harness/lanes_registry.py`, such as `INDEX_CACHE_DIR` or `RELAY_RUN_ROOT`.
  A test fails if a declared name looks like a credential.
- Names the operator grants to that lane with `env_allow` in the registry:

```json
{
  "forum": {
    "env_allow": ["ANTHROPIC_API_KEY"]
  }
}
```

A provider key reaches a lane only through `env_allow`, one lane and one name at
a time. An `env_allow` entry that is not a plain variable name, or an
`env_allow` that is not a list, is dropped and reported as `env_allow_invalid`;
the lane still launches. Proxy variables (`HTTP_PROXY`, `HTTPS_PROXY`,
`NO_PROXY`) are not in the base set because a proxy URL can carry a user name
and password; grant them by name when a lane needs them. The bundled payload
path already used its own minimal environment and is unchanged. The in-repo
bundled lanes (`local-model`, `writing`) run Flywheel's own modules and still
inherit the gateway environment outside a frozen build.
