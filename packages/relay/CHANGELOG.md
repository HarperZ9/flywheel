# Changelog

## 0.7.0, 2026-10-03

- Opt-in local-first cascade: `relay.cascade.Cascade` asks a local classifier a yes-or-no question first and calls your model endpoint only when the classifier abstains. Each answer goes to the session ledger with who answered it. The bundled "is this test failure flaky?" classifier missed both bars set before the run. On 81 held-out failure tails it decided 23% of questions, under the 50% bar, at 0.89 accuracy, under the 0.95 bar. The default threshold, 1.0, therefore sends nearly every question to the endpoint. A shuffled-label control reached 0.79. A substring defect found after the first run is fixed, and both runs are recorded. Details, the bar and the limits: `docs/CASCADE.md`.
- The Claude plugin folder now carries the server code at `client-plugin/server/src/relay/`, limited to the modules the plugin launch can import. `python scripts/build_client_package.py --sync-vendored` rewrites that copy from `src/`, and a test fails when it drifts. The remote server's modules, which name its OAuth secrets, are no longer shipped in the folder or the source ZIP.
- The Claude manifest passes `--no-cli-tiers`, so the plugin never builds a claude or codex CLI backend and uses one credential, the API key setting. It adds the plugin directory listing fields and a 1024 px icon, and takes the project folder, the write and exec grants and an optional hosted model from `userConfig`. The client adapter clears hosted-model keys, gateway URLs and model names from its starting environment and sets only the provider the launch names.
- Every MCP tool carries a title, `readOnlyHint` and `destructiveHint`. README and PRIVACY list the launch command, every network destination, every file written and every environment variable the server reads.
- Release checksum files are written with LF line endings on every OS, and the release workflow refuses a checksum file that contains a CR byte.
- The native release gate sends its loopback fixture through the hosted-model launch settings a user fills in. The first 0.7.0 tag failed this gate before anything was published: the launcher now clears ambient gateway URLs, and the gate still set the fixture gateway in the environment, so the granted write found no backend. The same gate now runs through `python serve.py` in ordinary CI on every platform, so a launcher change that breaks it fails before a release.

Source version metadata is not release availability proof; release availability is established only by the accepted Git tag, uploaded GitHub Release assets, and matching hash readback. Do not publish or recommend the bare PyPI name `relay-agent`; it belongs to another project.

## 0.6.0, 2026-10-01

- Adds default-off file-change and command-execution switches to MCPB setup. Strict boolean launch arguments retain the existing grants; native fixture workflows check both enabled permissions and refusals without a real model.
- Fixes a Windows restart-read race: completed background runs no longer replace their durable record again after publishing the terminal state. Failed final persistence reports an error and preserves the request binding when that error record can be written.
- Adds portable, Claude and Codex client manifests, a scoped skill, privacy guidance and troubleshooting.
- Adds deterministic source plugin ZIPs and self-contained Windows x64 ZIP/MCPB candidates with runtime licenses, checksums and dependency provenance. Source ZIPs still require Python.
- Requires an explicit absolute RELAY_MCP_ROOT binding. Ambient environment variables cannot grant write or execution access. Explicit --allow-write and --allow-exec launch flags preserve the existing permission model; exec implies write and is not an OS sandbox. Synthetic tests cover an approved bounded file write and denied execution. Native model-driven runs remain unverified and require a user-owned endpoint.
- Adds clean, tag-bound release packaging for .0 versions. Linked inputs, untracked release payloads, state files and credential file types are refused. The release workflow attaches checked client packages alongside the product release.
- Real Windows stdio checks cover identity, source/version parity, discovery and permission refusals without a model account. Installed-client compatibility, clean-OS compatibility, signing and marketplace admission remain open gates. No publisher backend, model, network listener or service is installed.

Source version metadata is not release availability proof; release availability is established only by the accepted Git tag, uploaded GitHub Release assets, and matching hash readback. Do not publish or recommend the bare PyPI name `relay-agent`; it belongs to another project.

## 0.5.0, 2026-09-27

A program planted in a project folder no longer runs through a `PATH` entry that
reaches that folder. 0.4.0 started its children through `safe_spawn` 1.0.0,
which skipped only relative `PATH` entries. This release vendors `safe_spawn`
1.0.1 and hands it the folder each child works in.

This was prepared as a 0.4.1 patch. It takes the minor number instead because
it changes what existing setups do, the rule 0.3.0 set for a pre-1.0 break: a
`run`, `test_cmd` or `check` command, or a git hook or filter during
`--auto-commit`, no longer finds a program through a project folder on `PATH`,
such as `.venv/bin` or `node_modules/.bin`, unless that folder holds the
interpreter relay runs on. A pin such as `~=0.4.0` excludes this release;
widen it to take the fix. The MCP tool names, the `relay.mcp-run-request/v2`
binding and the shapes of `relay.status` and `relay.doctor` are unchanged.

Source version metadata is not release availability proof; release availability
is established only by the accepted Git tag, uploaded GitHub Release assets, and
matching hash readback. Do not publish or recommend the bare PyPI name
`relay-agent`; that public namespace belongs to an unrelated project and is not
the HarperZ9 Relay distribution.

### Security

- An absolute `PATH` entry could reach a folder a child works in: the server's
  folder, the root of a `run`, `test_cmd` or `check`, the project a bisect
  check copies, or the repository `--auto-commit` commits to. The entry could
  name the folder or a folder below it, spell it another way, or lead there
  through a junction or symlink. On Windows a quoted entry such as
  `"C:\proj"\bin` reached it too, because cmd.exe drops the quotes. A program
  planted there ran in place of the installed `claude`, `codex` or `git`,
  including the `--version` check that `relay.doctor` starts under exec, and a
  shell child found it by bare name. Affected: every release through 0.4.0.
  0.4.0 closed the direct search of the server's folder and left these routes
  open.
- `git` itself ran with that `PATH`, so a program git starts by bare name ran
  from the repository: a clean filter the repository selects in
  `.gitattributes`, or `gpg` when commits are signed. Affected: every release
  through 0.4.0.
- On Windows a drive-relative name such as `C:claude` named a file in the
  current folder of drive C:. relay's own tiers use fixed names, so this needed
  a caller that builds a `CliBackend` with such a name. It is now refused with
  `BAD_PATH`.

### Changed

- The vendored `safe_spawn` is 1.0.1 (`src/relay/_vendor/safe_spawn.py`,
  SHA-256 recorded in `VENDORED.sha256`). It drops every `PATH` entry that
  reaches the server's folder or the folder named for the child, from the
  lookup and from the child's `PATH`. Folders are compared by name and by file
  identity after links are resolved.
- `run`, `test_cmd` and `check` hand their root to the helper. A bisect check
  runs in a fresh copy of the project, so it hands the helper the project it
  copied.
- `--auto-commit` resolves `git` with the repository as the named folder, and
  starts it with a `PATH` guarded the same way. git keeps the rest of its
  environment (`HOME`, `GNUPGHOME`, `SSH_AUTH_SOCK`, its `GIT_` variables). One
  lookup serves every git call of a commit.
- A command in `run`, `test_cmd` or `check` that found a program through a
  folder inside the root or the server's folder, such as a project's
  `.venv/bin` or `node_modules/.bin`, now needs that program's path
  (`.venv/bin/pytest`). So does a git hook or filter that found a program that
  way during `--auto-commit`. The folder that holds the interpreter relay runs
  on stays on `PATH`, so starting relay from the project's virtual environment
  keeps that environment's tools (`.venv/bin`, or `.venv\Scripts` on Windows).
  Tools in other folders inside the project, such as a Windows conda
  environment's `Scripts` and `Library\bin`, need their path. On Windows the
  Windows, System32 and SysWOW64 folders also stay.
- A child's `PATH` names each kept folder as its real folder, with links
  resolved, so a link repointed after the check cannot change what starts. On
  merged-/usr Linux, `/bin` reaches a child as `/usr/bin`.
- On Windows, `PATH` is read the way cmd.exe reads it, quotes included. An entry
  whose folder name holds `;` is left out, since Windows programs disagree on
  how to read it.
- On POSIX, a `PATH` that the filter leaves empty reaches the child as
  `/bin:/usr/bin`, because an empty `PATH` means the current folder there.

### Limits

- When the server's folder or a run's root is a filesystem root, or holds the
  home folder, only an entry naming that folder itself leaves. The tool folders
  below home, such as `~/.local/bin`, stay.
- The check reads the filesystem before the start. Swapping the program file,
  or a folder inside a kept folder, between the two still wins. That needs write
  access to a folder `PATH` already trusts.
- On a filesystem without file indices, such as some network shares, every
  `PATH` entry on the working folder's device leaves. A CLI there needs
  `RELAY_CLAUDE_CLI` or `RELAY_CODEX_CLI`, and a shell tool there needs its
  path.
- Each start reads every `PATH` entry, a step that took under 1 ms on 0.4.0.
  On Windows, with 58 entries, one read took about 11 ms. Under WSL with the
  Windows `PATH` appended (67 entries, 58 of them under `/mnt`) it took 0.5 to
  1.3 s, and under 1 ms with the `/mnt` entries removed. Every shell child and
  every CLI tier start pays at least one read. An `--auto-commit` reads `PATH`
  once for all its git calls, about 1.3 s there against 12 ms on 0.4.0.
- The new tests ran on Windows 11 and on Linux (Ubuntu 24.04 under WSL2).
  macOS was not run.

## 0.4.0, 2026-09-26

The session store stays inside itself, and every program relay starts gets an
environment allowlist and, for the `claude` and `codex` tiers, a proven isolation
profile. This was scoped as a 0.3.1 patch. It takes the minor number instead
because it changes what existing setups do, the rule 0.3.0 set for a pre-1.0
break:

- `run`, `test_cmd` and `check` no longer inherit the server's whole
  environment. A command that reads a variable outside the allowlist, such as a
  test suite that needs `DATABASE_URL` or a provider key, sees it unset until
  `RELAY_CHILD_ENV` names it.
- On Windows a shell no longer finds a program in the root by bare name. Call it
  as `.\tool`.
- The `claude` tier runs with `--tools ""` and the `codex` tier with a read-only
  sandbox, both in a new empty folder. A setup that used either tier as a
  sub-agent acting on the project gets a model reply only.
- With `RELAY_SESSION_DIR` unset, `local_agent_sessions` reads a per-user folder
  instead of the folder the server started in.
- `local_agent_sessions` refuses a `session_id` that is not a bare name.
- MCP file tools refuse writes into agent and editor configuration folders.

The MCP tool names, the `relay.mcp-run-request/v2` binding and the shape of
`relay.status` are unchanged. `relay.doctor` and the session listing gain
fields.

Source version metadata is not release availability proof; release availability
is established only by the accepted Git tag, uploaded GitHub Release assets, and
matching hash readback. Do not publish or recommend the bare PyPI name
`relay-agent`; that public namespace belongs to an unrelated project and is not
the HarperZ9 Relay distribution.

### Security

- `local_agent_sessions` joined the caller's `session_id` onto the session
  store with no check. `"../outside/private"` or an absolute path returned the
  transcript of any ledger file the server's user could read, with no grant.
  Affected: 0.2.0 through 0.3.0. Fixed: a `session_id` is a bare name, and a file
  whose real path leaves the store is neither opened nor listed.
- The `claude` and `codex` CLI tiers started the CLI by bare name from the
  server's folder, with every variable and no isolation flags. A `claude.exe`
  planted in that folder ran instead of the installed one, and a
  `.claude/settings.json` there could run its hooks. Reaching a tier needed the
  exec grant. Affected: every release through 0.3.0. Fixed below.
- `run`, `test_cmd`, `check` and bisect checks inherited every provider key, so a
  model with exec could print them into the ledger it returns. Affected: every
  release through 0.3.0.

### Changed

- The CLI tiers start through a vendored copy of `safe_spawn` 1.0.0
  (`src/relay/_vendor/safe_spawn.py`, SHA-256 recorded in `VENDORED.sha256`): an
  absolute executable, a new empty working folder, an environment allowlist, the
  prompt on stdin, and the isolation profile the probes proved. For `claude`
  2.1.251 that is `--setting-sources user --strict-mcp-config --tools ""`. For
  `codex` 0.144.6 it is `exec --ignore-user-config --ignore-rules --ephemeral
  --skip-git-repo-check --sandbox read-only --disable hooks --disable plugins
  --disable memories --disable apps -c project_doc_max_bytes=0
  -c skills.include_instructions=false`. `RELAY_CLAUDE_CLI` and
  `RELAY_CODEX_CLI` override the executable and must be absolute paths. The
  `codex` tier now runs on a stock Windows npm install, where 0.3.0 could not
  find `codex.cmd`. The tiers still need exec.
- A CLI tier whose isolation profile is not proven is refused with
  `EXEC_NOT_GRANTED` unless the launch also names it in `RELAY_ALLOW_EXEC_CLI`.
  No such tier ships today.
- `relay.doctor` adds `cli_tiers`, one row per CLI tier: `PASS` only when the
  CLI resolves, exec is granted, the profile is proven and `--version` reports
  the tested version, and `WARN` with a setup code (`CLI_NOT_FOUND`,
  `EXEC_NOT_GRANTED`, `CLI_PROFILE_UNPROVEN`, `CLI_VERSION_UNTESTED`,
  `CLI_VERSION_UNKNOWN`) otherwise. It starts `--version` only under exec and
  never reports the resolved path.
- Shell children get the platform base, a fixed set of toolchain variables
  (`VIRTUAL_ENV`, `JAVA_HOME`, `CARGO_HOME` and similar) and the names in
  `RELAY_CHILD_ENV`. `PATH` keeps absolute entries only, and on Windows
  `NoDefaultCurrentDirectoryInExePath=1` stops cmd.exe searching the root.
- `RELAY_CHILD_ENV`, `RELAY_ALLOW_EXEC_CLI`, `RELAY_CLAUDE_CLI` and
  `RELAY_CODEX_CLI` are launch-only. The remote entrypoint never takes them from
  its env file and names any it finds there.
- The session store defaults to a per-user folder: `%LOCALAPPDATA%\relay\sessions`
  on Windows, `~/Library/Application Support/relay/sessions` on macOS, and
  `$XDG_DATA_HOME/relay/sessions` or `~/.local/share/relay/sessions` elsewhere.
  MCP runs cannot write it.
- The session listing skips a file that will not load, a dangling link or a
  name that is not a valid id, and counts them in `skipped`. A missing session
  carries `"code": "NOT_FOUND"` beside its error text.
- The `local_agent_sessions` description and `session_id` schema say the id is
  a bare name.
- The stdio `relay.doctor` reads an env file only when `RELAY_ENV_FILE` names
  one. The remote entrypoint still reads `.env` from its folder.
- MCP file tools refuse writes into `.claude`, `.codex`, `.cursor`, `.vscode`,
  `.gemini`, `.agents`, `.opencode` and `.mcp.json`.
- `--auto-commit` resolves `git` to an absolute path, so a `git.exe` in the
  working folder never runs.

### Limits

- The profiles are proven for the tested CLI versions only, by one probe run per
  scenario on Windows. The Linux half of the probes has not run.
- `codex` has no flag that removes its shell tool. Under the profile it can still
  run read-only commands in its empty folder. Whether the CLI tiers become
  model-only backends that no longer need exec is an open decision.
- The shell is still not path-confined, and write is still a route to code
  execution outside the refused folders.

## 0.3.0, 2026-09-26

Write, exec and the working root for the MCP servers move from tool arguments to
launch configuration. This changes what existing MCP calls and setups do, so it
is a minor release rather than a patch. Relay is pre-1.0, where a breaking change
takes the minor number. The breaks:

- A client that sends `allow_write: true` or `allow_exec: true` to a server
  started without that grant now runs with it off.
- A run's `root` must resolve inside the server's launch root. A call that names
  any other directory is refused with `ROOT_NOT_GRANTED`.
- `check` and the online `codex` and `claude` CLI tiers need exec.
- The remote entrypoint no longer reads `RELAY_ALLOW_WRITE`, `RELAY_ALLOW_EXEC`,
  `RELAY_ALLOW_REMOTE_EXEC` or `RELAY_MCP_ROOT` from its `.env` file. In 0.2.5 a
  `RELAY_ALLOW_REMOTE_EXEC` line there was honored; set it in the environment
  that starts the server instead.
- `RELAY_ALLOW_REMOTE_EXEC` accepts `on` and `off`, and an unrecognized value
  now stops the remote server instead of reading as off.

An omitted `allow_write` or `allow_exec` still means off, as in 0.2.5.

Source version metadata is not release availability proof; release availability
is established only by the accepted Git tag, uploaded GitHub Release assets, and
matching hash readback. Do not publish or recommend the bare PyPI name
`relay-agent`; that public namespace belongs to an unrelated project and is not
the HarperZ9 Relay distribution.

### Changed

- `relay --mcp` and `python -m relay.local_mcp` take write and exec from their
  launch: `--allow-write` and `--allow-exec`, or `RELAY_ALLOW_WRITE` and
  `RELAY_ALLOW_EXEC`. Both are off by default. The launch root comes from
  `--root` or `RELAY_MCP_ROOT` and defaults to the working directory. An
  unrecognized value or a root that is not a directory stops the server at
  launch, including a direct call to `serve()`, which now returns 2 with a
  message instead of raising.
- A run gets what it asks for and the launch granted, both. `allow_write: true`
  and `allow_exec: true` ask; an omitted argument asks for nothing. Asking for
  exec also asks for write, and `allow_write: false` turns exec off.
- A run's `root` resolves under the launch root, and links are followed before
  the check, so neither `..` nor a link steps outside it.
- An MCP run's file tools never read the server's env file (`RELAY_ENV_FILE`,
  default `.env`), and never write it, the run store (`RELAY_RUN_ROOT`), the
  session store (`RELAY_SESSION_DIR`) or anything under a `.git` directory. On
  Windows they refuse a name ending in a dot or a space, or naming a stream,
  since it opens another spelling of a file.
- `check` runs a shell outside the tool gate, so an MCP run that sets it needs
  exec and is refused with `EXEC_NOT_GRANTED` otherwise. Before this release a
  caller could reach a shell through `check` with exec off.
- The online `codex` and `claude` CLI tiers start an agent with its own shell.
  Without exec, `local_agent_chat`, `local_agent_health` and auto routing leave
  them out, and naming one is refused with `EXEC_NOT_GRANTED`.
- On the remote surface, exec needs both `RELAY_ALLOW_EXEC` and
  `RELAY_ALLOW_REMOTE_EXEC`, and write needs `RELAY_ALLOW_WRITE` on its own:
  `RELAY_ALLOW_EXEC` alone grants the phone nothing. The server configures only
  what the surface allows, so its banner and `relay.status` report what runs
  get, and it still refuses exec per request as a second layer.
- The remote entrypoint reads the grant variables from its process environment
  only, because a run allowed to write could otherwise edit `.env` and give
  itself exec on the next restart. It names any such line it finds at startup,
  and the remote readout lists them as `env_file_ignored`.
- `.env` values may carry an inline comment after whitespace (`KEY=value  # note`).
  Before this release the comment became part of the value, so the shipped
  `.env.example` failed to start as documented.
- The request binding is `relay.mcp-run-request/v2`. It adds
  `granted_allow_write`, `granted_allow_exec`, `granted_root`,
  `requested_root`, `grant_shortfall`, `remote_exec_refused` and `protected`,
  and reports `requested_allow_write` and `requested_allow_exec` as `null`
  when omitted.
- `relay.status` and `relay.doctor` report the launch grants and root. The
  remote readout reports the grants the surface would configure as
  `start_grants`, and adds `remote_exec_in_effect` next to
  `remote_exec_allowed`.

### Limits

- The shell is not path-confined: with exec granted, `run`, `test_cmd` and
  `check` start in root and can reach any path the server's user can.
- Write is a route to code execution. A file written under the root runs the
  next time something executes it there, such as a build script, a test, or a
  shell profile when the root is a home directory. Launch the server over a
  workspace its callers may edit.
- Background runs keep the gate and root they started with. Changing the grants
  needs a server restart.

## 0.2.5, 2026-09-22

Relay now publishes to PyPI as `flywheel-relay`. The install command changes, so
this is a release rather than a metadata edit.

Source version metadata is not release availability proof; release availability
is established only by the accepted Git tag, uploaded GitHub Release assets, and
matching hash readback. Do not publish or recommend the bare PyPI name
`relay-agent`; that public namespace belongs to an unrelated project and is not
the HarperZ9 Relay distribution.

### Changed

- The distribution name is `flywheel-relay`. `pip install flywheel-relay` is the
  documented path, and releases carry PEP 740 attestations recording which
  workflow built the bytes. The import name, the module layout and the `relay`
  console script are unchanged.
- The hash-verified GitHub route is kept and still supported, for anyone who
  would rather check the bytes than trust an index. See
  `docs/GITHUB-ONLY-INSTALL.md`, updated for the new asset names.
- `tools/check_release_metadata.py` compares whitespace-normalized text, so a
  phrase split across a wrapped line no longer fails a guard that no change in
  wording had broken.

### Note

0.2.4 was never released. A stray `v0.2.4` tag points at a commit that is not on
main and whose own `pyproject.toml` reads 0.1.0, so this release skips that
number rather than reusing it.

## 0.2.3, 2026-09-17

Status: GitHub-only patch release. Source version metadata is not release
availability proof; release availability is established only by the accepted Git
tag, uploaded GitHub Release assets, and matching hash readback. Do not publish
or recommend the bare PyPI name `relay-agent`; that public namespace is not the
HarperZ9 Relay distribution.

### Added

- Architect mode can run an attributed planning pass before a plain single-run
  agent execution, then pass that proposal to the implementer as context.
- `--architect` refuses watch, MCP, probe, view, verify, bisect, health,
  best-of, and other modes until those paths have explicit planner semantics.

### Distribution boundary

- Source version metadata, changelog text, and built local artifacts are not
  release availability proof. The release is established by the accepted Git tag,
  uploaded GitHub Release assets, and matching hash readback.
- Install from a pinned HarperZ9 GitHub commit or from a hash-verified GitHub
  Release wheel. Missing checksum entries or hash mismatches stop before
  `pip install`.

## 0.2.2, 2026-09-13

Status: GitHub-only patch release. Do not publish or recommend the bare PyPI
name `relay-agent`; that public namespace is not the HarperZ9 Relay
distribution.

### Fixed

- Background MCP/agent runs with `RELAY_RUN_ROOT` now durably checkpoint
  witnessed partial ledgers while they are still running, so a server restart can
  reload observed progress as an `interrupted` partial run instead of losing it.
- Final result persistence and running checkpoint writes are serialized so a
  final `done` record is not replaced by an older running checkpoint.

### Limits

- A partial checkpoint is observed progress only. It is not a completed result,
  rollback guarantee, or acceptance verdict; `local_agent_result` returns `done`
  only after the final result record persists.

## 0.2.1, 2026-09-10

Status: GitHub-only patch release. Do not publish or recommend the bare PyPI name
`relay-agent`; that public namespace is not the HarperZ9 Relay distribution.

### Fixed

- MCP stdio now returns JSON-RPC parse/invalid-request/invalid-params errors
  for malformed input, invalid request ids, and non-object `tools/call` params
  without echoing rejected input or stopping the server.

## 0.2.0, 2026-09-08

Status: GitHub-only release with hash-verified GitHub Release artifacts
uploaded by the release owner.

### Added

- `local_agent_run` and `local_agent_start` accept the existing CLI route and
  acceptance dials: `backend`, `model`, `max_tokens`, `check`, `test_cmd`, and
  `compact_budget`.
- Blocking and background MCP runs return a `relay.mcp-run-request/v1` binding
  with admitted backend/model/root/effective gate choices, request gate intent,
  and hashes of goal/check/test command text.
- Background run status/result/list preserve the request binding across process
  restarts when `RELAY_RUN_ROOT` is configured.
- MCP results report the last witnessed assistant route with receipt id,
  `model_ref`, and ledger sequence when available.

### Fixed

- `DONE` background results are not exposed before the final done/result/finished
  record is durable.
- MCP scalar validation for run/start authority fields rejects string integers,
  floats, booleans in integer fields, non-string route fields, and negative
  limits.
- `local_agent_runs.limit` now rejects coercive or negative values.

### Distribution boundary

- This candidate is GitHub-only. Do not publish or recommend the bare PyPI name
  `relay-agent`; that public namespace is not the HarperZ9 Relay distribution.
- Install from a pinned HarperZ9 GitHub commit or from a hash-verified GitHub
  Release wheel after the release owner publishes one.
