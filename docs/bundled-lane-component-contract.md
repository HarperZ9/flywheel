# Installed lane component contract

The first extension adds fixed self-child admission for Writing and Local
Model. It does not remove any of the 15 lanes from the installation target.
Its status/doctor tools establish component admission only. Existing Writing
and agent HTTP operation workflows keep their own authority and execution.

## Shared with payload owners

Use the existing `flywheel.bundled-lane-component/v1` descriptor:

- `name`, `version`, `schema`.
- `source`: public `repo`, exact `commit`, relative `path`, `algorithm`,
  sorted `files` (`path`, `bytes`, `sha256`), `file_count`, aggregate `bytes`,
  and `manifest_sha256`.
- `entrypoint`: exact `argv: ["--bundled-lane-mcp", "<name>"]`, fixed `module`,
  fixed `callable`, and `health_tool`.
- `allowed_tools`: the reviewed tool set, not all tools a server may expose.
- `does_not_prove`: capability, workflow and runtime limitations.

Each admitted name also needs a compiled expectation with the descriptor's
SHA-256, source manifest SHA-256, source identity, version, entrypoint and tool
set. Runtime request arguments can choose only the compiled name. They cannot
provide a descriptor, source path, Python module or executable. Descriptors
live beneath the packaged `packaging/bundled-lanes` tree, not the user profile.
Missing or altered descriptors/modules refuse launch; no PATH fallback occurs.
Public-package collision refusals remain in effect outside bundled admission.

The v1 component descriptor is a source witness, not a signature or a hash of
the frozen interpreter. The installed release receipt binds the actual engine
and complete payload. Trust still starts with that installed executable.
Replacing the whole trusted executable is outside descriptor protection.
Python/Node sidecars need a separately reviewed runtime/artifact identity
extension before admission: do not put an arbitrary sidecar path into v1 argv.

## Core build integration

Core expectations are in `harness/bundled_lane_core_expectations.py`.
The two descriptors witness the unchanged MCP entrypoint source from the
recorded Flywheel commit, with LF-normalized source bytes. They do not claim
to enumerate every imported module. The source build gate
`harness.bundled_lane_core.check_core_descriptor(repo_root, name)` recomputes
the witness and requires equality with the saved descriptor and compiled pin.
Changing either MCP entrypoint requires an explicit source-pin refresh.

The packaging owner must run that gate for `writing` and `local-model`, copy
their JSON descriptors into `packaging/bundled-lanes`, and explicitly include
`harness.writing_mcp`, `harness.local_mcp` plus their normal import closure.
The existing gateway entry already dispatches fixed bundled children before
gateway startup. No independent service manager is introduced. A packaged
component must be checked again from an isolated installed process with no
developer Python, Node or source checkout accessible through PATH.

Relay's existing descriptor, source pin and `relay.status` admission remain
unchanged. Writing admits only `writing.status` and `writing.doctor`; Local
Model admits only `local-model.status` and `local-model.doctor` through this
initial component boundary. Provider tasks, file changes, memory mutation,
device actions and full CLI parity require their existing reviewed operation
boundaries and per-lane useful-workflow acceptance. A status receipt cannot
fulfill those requirements.

The child independently enforces this boundary around its existing module
server. It filters `tools/list`, removes argument properties from admitted
status/doctor schemas, rejects every nonempty argument object and refuses
unadmitted tools/resources before dispatch. This blocks Writing's normal
stdio `home` override in bundled mode. The ordinary unbundled servers remain
unchanged. Parent MCP filtering remains a second boundary, not the only one.
Startup/module failures return a fixed exit code without publishing raw errors.

Writing requires an explicit absolute `FLYWHEEL_HOME` from the trusted parent
environment. It is the only extra state variable passed into that child;
credential and Python import variables remain excluded. Missing or relative
state roots fail `bundled_state_root_missing`, with no user-profile fallback.
Writing's existing status service may initialize its owner/state scaffolding
and reads its configured workspace. It is not a stateless health ping. The
gateway launcher must pass its effective private state root, and isolated
acceptance must use a fresh synthetic state root. Other owners' state and
operation bodies must not be passed through a shared status projection.

Node and heavy Python payload owners should supply source pins, distribution
artifacts, dependency/runtime closure and exact tool/capability manifests for
review. Their components remain unavailable until this contract is explicitly
extended and installed. Merely installing packages into a developer runtime
does not install a lane into the frozen application.
