# Flywheel 1.0.4

A self-hostable, model-agnostic AI workstation and coding harness. Flywheel runs a task
with any model, frontier or local, behind one OpenAI-compatible surface, and your keys and
data stay on your machine. An answer is accepted only when a real check passes, such as a
test run or a Lean proof. Each accepted answer carries a sealed receipt, and the witness
re-runs that receipt offline to return MATCH, DRIFT, or UNVERIFIABLE.

1.0.4 brings the Windows installer level with a pip install and closes three security gaps
in how Flywheel starts its lanes and its local agent. It also makes `flywheel --version`
print the version. One change needs action from some users: a lane that reads a provider
key now needs that key granted to it by name (see Upgrade).

## What 1.0.4 fixes

- The installer bundles the current lanes (#296). The 1.0.3 installer bundled older code
  than a pip install for six lanes. The frozen app now carries the versions the lane
  registry pins: chorus 0.3.1, relay 0.2.5, plexus 0.2.2, mneme 0.4.2, canon 0.2.0 and
  accountable-surface 0.3.1. gather 1.8.2, crucible 1.2.0, index 2.13.0 and forum 1.14.0
  were already current.
- Lanes start with a minimal environment (#295). Every pip or npm lane used to inherit
  the gateway's whole environment, so a provider API key exported for the gateway reached
  every lane process. A lane now starts with a base set (PATH, system and temp
  directories, locale, CA bundles, FLYWHEEL_HOME and workspace roots), the non-secret
  variables it declares, and any variable you grant it by name with `env_allow` in
  `lanes.json`. Proxy variables also need a grant, because a proxy URL can carry a user
  name and password.
- The local agent takes its authority from you (#295). `local_agent_run` read
  `allow_write`, `allow_exec` and `root` from the tool call, so a model could grant itself
  exec or point file tools anywhere, and the string "false" counted as true. Grants now
  come from how you start the server (`--allow-write`, `--allow-exec`, `--allow-online`,
  `--root`, or the matching `FLYWHEEL_LOCAL_AGENT_*` variables). A tool argument can only
  narrow them. A root outside the workspace, a root that is your home directory, and a
  root that contains or sits inside FLYWHEEL_HOME are refused before any agent step runs.
  When the gateway launches the bundled local-model lane, it confines the agent to its
  own `--root`.
- The gateway token and the receipt signing key are unreadable from the Windows sandbox
  (#295). A sandboxed agent command could open `~/.flywheel/gateway.token`. Both files now
  carry a medium mandatory label that the low-integrity sandbox cannot read, applied every
  time the gateway loads them. On macOS and Linux the sandbox's credential denylist now
  hides the token and the signing key, including under a custom FLYWHEEL_HOME.
- `flywheel --version` prints the version (#296). It used to print a usage error.

## A correction to the 1.0.3 notes

The 1.0.3 notes said the 1.0.2 installer build stopped at a version check. They did not
say that 5 of the 31 automated checks on the 1.0.2 release commit had failed: two
whole-suite test shards, both Flutter builds and the installer build. 1.0.2 went to the
Python Package Index with those failures. The cause was the version declaration that
#281 fixed in 1.0.3.

## Upgrade

- Engine: `pip install -U flywheel-verify`
- Desktop app: the Windows installer (Flywheel-Setup-1.0.4-x64.exe) is attached below.
- If a lane needs a provider key, grant it by name in `lanes.json`, for example
  `"env_allow": ["ANTHROPIC_API_KEY"]` on the forum or accountable-surface row. forum,
  accountable-surface, relay's online route, mneme's extraction and gather's credentialed
  sources need this for real model runs. The "Lane environment" section of
  docs/lane-runtime-selection.md lists each lane's variables.
- To let the local agent write, run commands or go online, start its server with the
  matching flag, for example
  `python -m harness.local_agent_cli --mcp --root /path/to/project --allow-write`, or set
  the matching `FLYWHEEL_LOCAL_AGENT_*` variable. Every grant is off by default.

## Limits

- Lanes still run outside any sandbox, as your user. A lane can read the gateway token
  and the signing key, and can edit `lanes.json` to grant itself a variable on its next
  start. Closing this needs a filesystem boundary for lanes.
- On Windows the sandbox can still read other credential files, such as `.ssh`, `.aws`
  and `.npmrc`, and it can still reach loopback. With the token unreadable, a loopback
  connection alone carries no gateway authority for a sandboxed command.
- relay's own `local_agent_run` tool still reads its grants from tool arguments. The
  gateway's local agent is fixed; relay's needs its own release.
- The bundled accountable-surface 0.3.1 runs with the coherence-membrane and
  proof-surface copies the desktop runtime already ships, not with versions a pip install
  resolves.
- The limits listed for 1.0.3 on the verifier still hold: code inside the pytest process
  can forge its own report, the workdir restore does not undo writes outside the workdir,
  the math oracle does not bind a proof to the task's theorem, and a def built on an
  axiom a metaprogram added can still pass.
- On the shipped benchmark the verified loop shows no measured accuracy uplift over
  single-shot. The interval includes zero.
- A receipt proves a check reproduces. It does not prove the answer is true of the world.
