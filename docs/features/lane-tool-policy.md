# Lane tool policy

Flywheel calls every lane tool through one policy, the same in the Windows app, a pip
install and a source checkout. The engine decides each call's tier itself, whatever
the caller sends, and the approval sheet shows the tier, the effect and the reason
below before you approve a call.

## Tiers

- **T1**: the tool runs on an ordinary lane call. T1 covers reads, network reads,
  writes inside the lane's own folder under the Flywheel home, and calls to the model
  server you set up.
- **T2**: the tool runs only on a call you approve with the higher tier. T2 covers
  writes outside the lane's folder, spending a model call or a provider key,
  publishing under an identity, acting on your machine, and deciding an approval. A
  tool the policy does not list is T2 as well, so a lane upgrade that adds a tool
  cannot open it without a review.
- **Not in build**: the tool is listed so you can see it, and the Windows app refuses
  it with the reason shown.

Plugins and agent runs never reach a T2 tool or an unlisted one. Agent runs also
refuse tools that write lane state, fetch a URL the caller names, or have an
argument the engine checks, drops, or fixes, since an agent run passes the
model's arguments through. Every telos tool is one of them: the engine passes
telos no argument.

## Reading the tables

- **Tier**: "T2 (rule alone: T1)" marks a tool the policy review keeps at T2 although
  its effect alone would allow T1.
- **Main**: the lane's main action, the one its card runs.
- **Effect**: what the tool does, which decides the tier.
- **Needs**: a setup item the lane card names before the tool can run.
- **Engine sets**: what the engine does to the arguments before the lane sees them:
  an argument it drops or fixes, an id that must be a plain name, and a path argument
  it keeps out of Flywheel's own state (the home and the run root), including every
  value inside an inline configuration where the column says so, and a flag the
  engine adds to the lane's launch for one approved call only (forum's
  `--allow-gate-decisions`, which forum 1.15 needs before it runs a gate decision).
  The engine checks a path both as given and with `~` expanded, since lanes read it
  either way. An index `root` above the home, such as your user folder, still lets
  index read the repositories inside the home.
- **Reason**: why the tool has its tier, from reading the lane's source.

The tables come from the engine's policy table (`harness/lane_tool_policy.py`),
rendered by `scripts/render_lane_policy_review.py`. A test fails when this page and the
table differ.

<!-- policy-tables:start (scripts/render_lane_policy_review.py) -->

### gather 2.1.0

Admitted at launch: 5 of 8 tools. T2 per granted call: 3. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `gather.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `gather.doctor` | T1 |  | read |  |  | Readiness report; network-free. |
| `gather.docs` | T1 | main | read |  | `path` kept out of the home | Reads a local file or folder and returns catalog rows and digests; writes nothing. |
| `gather.arxiv` | T1 |  | network_read |  |  | Fetches arXiv metadata and returns rows; writes nothing. |
| `gather.federation` | T2 (rule alone: T1) |  | read |  | `registry` kept out of the home | Validates or plans a registry in memory. The policy review keeps it at T2. |
| `gather.run` | T2 |  | outside_write |  | `config_path` kept out of the home, every value in `config` kept out of the home | Runs a multi-source config over the network and writes the corpus store the config names. |
| `gather.context` | T1 | main | read |  | `corpus` kept out of the home | Reads a corpus and returns bounded excerpts or a selection; writes nothing. |
| `gather.pilot` | T2 |  | outside_write |  | `manifest` kept out of the home, `output` kept out of the home, `bundle_output` kept out of the home | Runs, refreshes or bundles a pilot into the output folders the caller names. |

### crucible 1.4.0

Admitted at launch: 11 of 14 tools. T2 per granted call: 3. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `crucible.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `crucible.doctor` | T1 |  | read |  |  | Readiness report; network-free. |
| `crucible.assess` | T1 | main | read |  | `thesis` kept out of the home, `measurements` kept out of the home | Assesses a thesis against measurements in memory and returns verdicts. |
| `crucible.recheck` | T1 |  | read |  | `dir` kept out of the home, `index` kept out of the home, `pack` kept out of the home | Reads a registry and replays a pack the caller names; writes nothing. |
| `crucible.recheck_template` | T1 |  | read |  | `dir` kept out of the home, `index` kept out of the home | Reads a registry assessment and returns a replay template; writes nothing. |
| `crucible.run` | T2 |  | outside_write |  | `thesis` kept out of the home, `registry` kept out of the home, `measurements` kept out of the home, `report` kept out of the home, `out` kept out of the home, `bundle` kept out of the home | Writes the registry, report, packet and bundle paths the caller names. |
| `crucible.measurement_gate` | T1 |  | read |  | `packet` kept out of the home, `criteria` kept out of the home | Checks a packet against criteria. |
| `crucible.review` | T1 |  | read |  | `bundle` kept out of the home | Validates a review bundle. |
| `crucible.report` | T1 |  | read |  | drops `out`, `dir` kept out of the home, `index` kept out of the home | Renders a report and returns it. The engine drops `out`, which would write a file. |
| `crucible.batch` | T2 |  | outside_write |  | `manifest` kept out of the home, `registry` kept out of the home, `reports` kept out of the home | Assesses a manifest into the registry the caller names. |
| `crucible.registry` | T1 |  | read |  | `apply=false`, `dir` kept out of the home | Lists, verifies or searches a registry. The engine forces `apply` false, so prune stays a dry run. |
| `crucible.drift` | T1 |  | read |  | `dir` kept out of the home | Compares the two latest assessments in a registry. |
| `crucible.refine` | T2 |  | outside_write |  | `config` kept out of the home, `thesis` kept out of the home, `registry` kept out of the home | Runs the refine loop into the registry the caller names. |
| `crucible.verdicts` | T1 |  | read |  | `dir` kept out of the home | Lists or re-checks assessments in a registry. |

### chorus 0.3.1

Admitted at launch: 6 of 6 tools. T2 per granted call: 0. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `chorus.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `chorus.doctor` | T1 |  | read |  |  | Readiness report; network-free. |
| `chorus.run` | T1 | main | read |  | `corpus` kept out of the home | Digests a corpus in memory and returns themes with a receipt. |
| `chorus.corpora` | T1 |  | read |  | `root` kept out of the home | Lists gather corpora under a folder. |
| `chorus.digests` | T1 |  | read |  | `store` kept out of the home | Lists digests a daemon stored. |
| `chorus.decision` | T1 |  | read |  | `current` kept out of the home, `reference` kept out of the home | Compares two source packs and returns a review gate. |

### articulate 0.6.0

Admitted at launch: 6 of 9 tools. T2 per granted call: 3. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `check` | T1 | main | read |  |  | Local detector; no network. |
| `score` | T1 | main | read |  |  | Local score; no network. |
| `judge` | T2 |  | spend | claude_cli |  | May call an explicit model backend or the signed-in claude CLI. The legacy engine route retains its CLI prerequisite and T2 grant; local calling-model editing uses edit_plan/edit_submit. The CLI runs with settings, MCP servers and tools off, from the path the engine passes in ARTICULATE_CLAUDE_CLI. |
| `fix` | T2 |  | spend | claude_cli |  | May call an explicit model backend or the signed-in claude CLI. The legacy engine route retains its CLI prerequisite and T2 grant; local calling-model editing uses edit_plan/edit_submit. The CLI runs with settings, MCP servers and tools off, from the path the engine passes in ARTICULATE_CLAUDE_CLI. |
| `polish` | T2 |  | spend | claude_cli |  | May call an explicit model backend or the signed-in claude CLI. The legacy engine route retains its CLI prerequisite and T2 grant; local calling-model editing uses edit_plan/edit_submit. The CLI runs with settings, MCP servers and tools off, from the path the engine passes in ARTICULATE_CLAUDE_CLI. |
| `edit_plan` | T1 |  | read |  |  | Prepares calling-model instructions and protected spans in memory; no network, subprocess or separate model account. |
| `edit_submit` | T1 |  | read |  |  | Checks the submitted rewrite locally and returns a receipt; no network, subprocess or separate model account. |
| `articulate.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `articulate.doctor` | T1 |  | read |  |  | Readiness report; network-free. |

### index 2.15.0

Admitted at launch: 22 of 23 tools. T2 per granted call: 1. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `index.map` | T1 | main | read | git | drops `resume_state`, `root` kept out of the home | Maps a repository. Needs Git for branch and history. The engine drops `resume_state`, which would write a file. |
| `index.context` | T1 |  | read |  | `root` kept out of the home | Builds a dependency context pack. |
| `index.context.envelope` | T1 |  | read |  | `root` kept out of the home | Builds a budgeted context envelope. |
| `index.select` | T1 |  | read |  | `root` kept out of the home | Selects paths with rejection receipts. |
| `index.invalidate` | T2 (rule alone: T1) |  | read |  | `root` kept out of the home | Mints or checks a tree pin and returns it. The policy review keeps it at T2. |
| `index.wiki` | T1 |  | read |  | `root` kept out of the home | Builds or verifies a wiki pack and returns it. |
| `index.symbol-graph` | T1 |  | read |  | `root` kept out of the home | Builds a symbol graph for one repo. |
| `index.symbol-definition` | T1 | main | read |  | `root` kept out of the home | Finds a symbol's definition from the AST. |
| `index.symbol-references` | T1 | main | read |  | `root` kept out of the home | Finds a symbol's resolved callers. |
| `index.symbol-implementations` | T1 |  | read |  | `root` kept out of the home | Finds subclasses and overrides. |
| `index.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `index.doctor` | T1 |  | read |  |  | Readiness report; network-free. |
| `index_graph` | T1 |  | read |  | `root` kept out of the home | Builds a repo dependency graph. |
| `index_focus` | T1 |  | read |  | `root` kept out of the home | Returns one repo's dependency neighborhood. |
| `index_verify` | T1 |  | read |  | `root` kept out of the home | Grounds a structural claim with file:line evidence. |
| `index_router` | T1 |  | read |  | `root` kept out of the home | Builds a workspace map and returns it; its cache stays in the lane folder (INDEX_MCP_CACHE_DIR). |
| `index.route` | T1 |  | read |  | `root` kept out of the home, every value in `paths` kept out of the home, a relative one checked under `root` | Builds a context envelope for the repositories `paths` names under `root` and returns a route receipt; its graph cache stays in the lane folder (INDEX_GRAPH_REPO_CACHE_DIR). |
| `index_internals` | T1 |  | read |  | `root` kept out of the home | Builds one repo's module graph. |
| `index.router.job.start` | T1 |  | state_write |  | `root` kept out of the home | Runs on the index lane's long-lived session, so the job's worker outlives the call that started it; in a frozen engine the worker runs as --bundled-lane-worker. Job state and caches stay in the lane folder. |
| `index.router.job.status` | T1 |  | read |  | `job_id` a plain id | Runs on the index lane's long-lived session, so the job's worker outlives the call that started it; in a frozen engine the worker runs as --bundled-lane-worker. Job state and caches stay in the lane folder. The job id must be a plain id. |
| `index.router.job.result` | T1 |  | read |  | `job_id` a plain id | Runs on the index lane's long-lived session, so the job's worker outlives the call that started it; in a frozen engine the worker runs as --bundled-lane-worker. Job state and caches stay in the lane folder. The job id must be a plain id. |
| `index.router.job.cancel` | T1 |  | state_write |  | `job_id` a plain id | Runs on the index lane's long-lived session, so the job's worker outlives the call that started it; in a frozen engine the worker runs as --bundled-lane-worker. Job state and caches stay in the lane folder. The job id must be a plain id. |
| `index.router.job.resume` | T1 |  | state_write |  | `job_id` a plain id | Runs on the index lane's long-lived session, so the job's worker outlives the call that started it; in a frozen engine the worker runs as --bundled-lane-worker. Job state and caches stay in the lane folder. The job id must be a plain id. |

### forum 1.16.0

Admitted at launch: 14 of 21 tools. T2 per granted call: 7. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `submit` | T2 |  | spend |  |  | Runs a plan through the executor. With FORUM_RUN_REAL and a granted key it spends model calls. |
| `route` | T1 |  | read |  |  | Older name for forum.route: scores a request against the roster with no model. |
| `plan` | T1 | main | model_call |  |  | Plans a request with the configured executor without running it: the echo executor by default, one model call with FORUM_RUN_REAL and a granted key. |
| `status` | T1 |  | read |  |  | Older ledger status: entry count and checkpoint. |
| `verify` | T1 |  | read |  |  | Verifies the ledger chain. |
| `ledger_get` | T1 |  | read |  |  | Reads one ledger entry. |
| `forum.submit` | T2 |  | spend |  |  | Runs a plan through the executor. With FORUM_RUN_REAL and a granted key it spends model calls. |
| `forum.route` | T1 | main | read |  |  | Scores a request against the roster with no model and returns the decided lane. |
| `forum.prose.humanize` | T2 (rule alone: T1) |  | read |  |  | Rewrites prose by fixed rules, no model. The policy review keeps it at T2. |
| `forum.prose.contract` | T1 |  | read |  |  | Returns the deterministic communication contract. |
| `forum.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `forum.doctor` | T1 |  | read |  |  | Readiness report; network-free. |
| `forum.ledger.summary` | T1 |  | read |  |  | Summarizes the ledger. |
| `forum.ledger.capsule` | T1 |  | read |  |  | Compacts the ledger into a capsule and returns it. |
| `forum.run.room` | T2 (rule alone: T1) |  | read |  |  | Projects the latest run into a snapshot. The policy review keeps it at T2. |
| `forum.runtime.inspect` | T1 |  | read |  |  | Reports the executor policy without running a model. |
| `forum.context.preflight` | T1 |  | read |  |  | Estimates context pressure before a submit. |
| `gate_list` | T1 |  | read |  |  | Lists paused approval gates. |
| `gate_approve` | T2 |  | approve |  | `--allow-gate-decisions` on this call's launch only | Resolves a paused human-approval gate. An agent must not approve its own wave. forum 1.15 serves it only on a launch with --allow-gate-decisions, which the engine adds for this one approved call; every other forum launch has it off. |
| `gate_edit` | T2 |  | approve |  | `--allow-gate-decisions` on this call's launch only | Resolves a paused human-approval gate. An agent must not approve its own wave. forum 1.15 serves it only on a launch with --allow-gate-decisions, which the engine adds for this one approved call; every other forum launch has it off. |
| `gate_reject` | T2 |  | approve |  | `--allow-gate-decisions` on this call's launch only | Resolves a paused human-approval gate. An agent must not approve its own wave. forum 1.15 serves it only on a launch with --allow-gate-decisions, which the engine adds for this one approved call; every other forum launch has it off. |

### learn 2.1.0

Admitted at launch: 14 of 15 tools. T2 per granted call: 1. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `learn_doctor` | T1 |  | read | node |  | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_status` | T1 |  | read | node |  | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_verify` | T1 |  | read | node | `runId` a plain id | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_receipt` | T1 |  | read | node | `runId` a plain id | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_dry_run` | T1 | main | read | node | `workflowPath` kept out of the home | Checks a workflow step by step without running it; reads the file the caller names. |
| `learn_tutor_plan` | T1 | main | state_write | node | `sessionId` a plain id | Writes one session file under <home>/lanes/learn/tutor/, the lane's own folder. The engine refuses a plan for a session that already has a file, so a T1 plan cannot reset what the T2 record wrote. |
| `learn_tutor_record` | T2 (rule alone: T1) |  | state_write | node | `sessionId` a plain id | Writes one session file under <home>/lanes/learn/tutor/, the lane's own folder. The policy review keeps it at T2. |
| `learn_tutor_mastery` | T1 |  | read | node | `sessionId` a plain id | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_visualize_dry_run` | T1 |  | read | node |  | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_tutor_due` | T1 |  | read | node | `sessionId` a plain id | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_tutor_studyplan` | T1 |  | read | node | `sessionId` a plain id | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_tutor_misconceptions` | T1 |  | read | node | `sessionId` a plain id | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_tutor_reverify` | T1 |  | read | node | `sessionId` a plain id, `file` kept out of the home | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_tutor_derive_schedule` | T1 |  | read | node | `sessionId` a plain id | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_tutor_prooflesson` | T1 |  | read | node | `packetPath` kept out of the home | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |

### telos 0.5.0

Admitted at launch: 37 of 41 tools. T2 per granted call: 3. Not in this build: 1.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `telos.status` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.doctor` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.room` | T2 |  | actuate | node | passes no argument | Starts the python found on PATH and, when gather, crucible, index and forum source folders sit beside the package, runs their status and doctor commands from those folders. Programs outside the package run, so each call needs a T2 approval. |
| `telos.workflow` | T2 |  | actuate | node | passes no argument | Starts the python found on PATH and, with the four source folders beside the package, runs index map, gather docs, forum route and crucible assess from them and a node from PATH; its temp files stay in the lane folder. Programs outside the package run, so each call needs a T2 approval. |
| `telos.catalog` | T1 | main | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.server.manifest` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.mcp.freshness` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.ci.doctor` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.ci.triage` | T1 |  | read | node | passes no argument | Triages the package's bundled CI fixture and prints JSON; the MCP mapping passes no arguments, so the live GitHub intake is never reached. |
| `telos.presentation.doctor` | T1 |  | read | node | passes no argument | Reads the package and, read-only, the README, changelog and brand files in gather, crucible, index and forum folders beside it; prints JSON and writes nothing. |
| `telos.accessibility.doctor` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.performance.doctor` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.compatibility.doctor` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.operator.doctor` | T1 |  | read | node | passes no argument | Runs one fixed package script, which also starts the package's own status script on the same Node; reads files inside the package and prints JSON. |
| `telos.admission.telemetry` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.context.envelope` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.context.pack` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.action.receipt` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.loop.ledger` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.objective.monitor` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.model.foundry` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.learning.forge` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.learning.labs` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.research.seed` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.research.thermodynamic` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.rendering.research` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.rendering.capabilities` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.measurement.layers` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.creative.engine` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.creative.kernels` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.revival.registry` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.second_level.queue` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.workstation.substrate` | T1 |  | read | node | passes no argument | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.display.calibration` | T1 |  | read | node | passes no argument | Returns a calibration contract from package data; changes no display setting. |
| `telos.native.control` | T2, not in build: `actuation_outside_app` |  | actuate | node | passes no argument | The package's Chrome DevTools, UI Automation and device driver. With no arguments it prints its verb catalog, but the script is the driver, so the build leaves it out rather than admit it at T2. |
| `telos.browser.evidence` | T1 |  | read | node | passes no argument | Returns the package's synthetic browser evidence fixture as JSON; starts no browser. |
| `telos.showcase.scout` | T1 |  | read | node | passes no argument | Ranks the package's bundled scout fixture and prints JSON; the live GitHub search and the file output are not reachable from the MCP mapping. |
| `telos.proof` | T2 |  | actuate | node | passes no argument | Its witness stage runs node on the script TELOS_EMET_CLI names, or on an emet folder beside the package, with temp files in the lane folder. Programs outside the package run, so each call needs a T2 approval. |
| `telos.proof.research` | T1 | main | read | node | passes no argument | Assembles and verifies the bundled demo packet in memory; this proof has no witness stage and writes nothing. |
| `telos.proof.visual` | T1 | main | read | node | passes no argument | Recomputes the bundled demo packet's measurements in memory; no witness stage, no write. |
| `telos.proof.build` | T1 | main | read | node | passes no argument | Recomputes the bundled demo run's invariant in memory; no witness stage, no write. |

### local-model 0.1.0

Admitted at launch: 8 of 9 tools. T2 per granted call: 1. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `local_agent_health` | T1 |  | network_read |  | passes no argument, `online=false` | Pings the local model tiers; online tiers are forced off. |
| `local_agent_chat` | T1 | main | model_call | model_server | `online=false` | One completion from the first healthy local tier; online tiers are forced off. |
| `local_agent_run` | T1 | main | model_call | model_server, project_folder | passes only `goal`, `root`, `max_steps`, `max_tokens`, `backend`, `allow_write=false`, `allow_exec=false`, `online=false`, `root` kept out of the home | Runs an agent task inside the picked project folder. Write and exec come from the launch and default off; the engine passes only the listed arguments and forces write, exec and online off in the call. |
| `local-model.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `local-model.doctor` | T1 |  | read |  |  | Readiness report; network-free. |
| `flywheel.context.health` | T1 |  | read |  |  | Reports the Canon context bridge status. |
| `flywheel.context.capture` | T2 |  | outside_write |  |  | Writes captured context into the Canon context store, outside the lane folder. |
| `flywheel.context.preflight` | T1 |  | read |  |  | Searches the Canon context store. |
| `receipt.verify_inclusion` | T1 |  | read |  |  | Checks a receipt digest against the Merkle log. |

### writing 0.1.0

Admitted at launch: 3 of 14 tools. T2 per granted call: 10. Not in this build: 1.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `writing.status` | T1 |  | read |  | drops `home` | Lists the owner's writing projects. |
| `writing.doctor` | T1 |  | read |  | drops `home` | Reports writing workflow readiness. |
| `writing.project_init` | T2 (rule alone: T1) |  | state_write |  | drops `home` | Prepares a proposal in the writing workspace under the Flywheel home; nothing changes until a commit. The policy review keeps the records at T2. |
| `writing.section_record` | T2 (rule alone: T1) |  | state_write |  | drops `home` | Prepares a proposal in the writing workspace under the Flywheel home; nothing changes until a commit. The policy review keeps the records at T2. |
| `writing.revision_record` | T2 (rule alone: T1) |  | state_write |  | drops `home` | Prepares a proposal in the writing workspace under the Flywheel home; nothing changes until a commit. The policy review keeps the records at T2. |
| `writing.diagnose` | T2 | main | outside_write | writing_draft | drops `home` | Prepares a reader-flow diagnostic proposal for a recorded revision in the engine's journey store under <home>/state, outside the lane folder, so it runs on a call the owner approves at T2. |
| `writing.card_record` | T2 (rule alone: T1) |  | state_write |  | drops `home` | Prepares a proposal in the writing workspace under the Flywheel home; nothing changes until a commit. The policy review keeps the records at T2. |
| `writing.candidate_record` | T2 (rule alone: T1) |  | state_write |  | drops `home` | Prepares a proposal in the writing workspace under the Flywheel home; nothing changes until a commit. The policy review keeps the records at T2. |
| `writing.decision_record` | T2 (rule alone: T1) |  | state_write |  | drops `home` | Prepares a proposal in the writing workspace under the Flywheel home; nothing changes until a commit. The policy review keeps the records at T2. |
| `writing.review_prepare` | T2 (rule alone: T1) |  | state_write |  | drops `home` | Prepares a proposal in the writing workspace under the Flywheel home; nothing changes until a commit. The policy review keeps the records at T2. |
| `writing.export_prepare` | T2 (rule alone: T1) |  | state_write |  | drops `home` | Prepares a proposal in the writing workspace under the Flywheel home; nothing changes until a commit. The policy review keeps the records at T2. |
| `writing.proposal_get` | T1 |  | read |  | drops `home` | Reads one proposal preview. |
| `writing.proposal_approve` | T2, not in build: `approval_cli_only` |  | approve |  | drops `home` | Unavailable over MCP by design; approval runs from the CLI. |
| `writing.proposal_commit` | T2 (rule alone: T1) |  | state_write |  | drops `home` | Commits a proposal that an approval outside MCP granted; changes the manuscript in the writing workspace. The policy review keeps the records at T2. |

### relay 0.6.0

Admitted at launch: 9 of 10 tools. T2 per granted call: 1. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `local_agent_health` | T1 |  | network_read |  | passes no argument, `online=false` | Pings the local model tiers; online tiers are forced off. |
| `local_agent_chat` | T1 |  | model_call | model_server | passes only `prompt`, `backend`, `online=false` | One completion from the first healthy local tier; online tiers are forced off. |
| `local_agent_run` | T1 | main | model_call | model_server | passes only `goal`, `max_steps`, `max_tokens`, `model`, `backend`, `compact_budget`, `allow_write=false`, `allow_exec=false`, `online=false` | Runs an agent task on the model server the person set up. relay 0.5.0 takes write and exec from its launch, which the engine starts with both off and its root at the lane folder; the engine also passes only the listed arguments, so root, check, test_cmd and online never reach the run, and forces write, exec and online off. |
| `local_agent_start` | T2 (rule alone: T1) |  | model_call | model_server | passes only `goal`, `max_steps`, `max_tokens`, `model`, `backend`, `compact_budget`, `allow_write=false`, `allow_exec=false`, `online=false` | Starts the same agent run in the background on the relay lane's long-lived session and returns its run id at once. T2: it holds the model server for minutes with no call waiting on it. relay 0.5.0 takes write and exec from its launch, which the engine starts with both off and its root at the lane folder; the engine passes only the listed arguments and forces write, exec and online off. |
| `local_agent_status` | T1 |  | read |  | passes only `run_id`, `run_id` a plain id | Reads a background run from the relay lane session, where the run lives; the run id must be a plain id. |
| `local_agent_result` | T1 |  | read |  | passes only `run_id`, `run_id` a plain id | Reads a background run from the relay lane session, where the run lives; the run id must be a plain id. |
| `local_agent_runs` | T1 |  | read |  | passes only `limit` | Lists the runs the relay lane session holds. |
| `local_agent_sessions` | T1 |  | read |  | `session_id` a plain id | Lists saved sessions and re-verifies each. |
| `relay.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `relay.doctor` | T1 |  | read |  |  | Readiness report; network-free. |

### plexus 0.3.0

Admitted at launch: 6 of 6 tools. T2 per granted call: 0. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `plexus_discover` | T1 |  | read |  | `dir` kept out of the home | Reads interop manifests and returns the mesh. |
| `plexus_wiring` | T1 |  | read |  | `dir` kept out of the home | Returns the capability wiring map. |
| `plexus_plan` | T1 | main | read |  | `dir` kept out of the home | Returns the pipeline that feeds a target organ. |
| `plexus_route` | T1 | main | read |  | `dir` kept out of the home | Returns the shortest capability path. |
| `plexus.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `plexus.doctor` | T1 |  | read |  |  | Readiness report; network-free. |

### mneme 0.6.0

Admitted at launch: 8 of 11 tools. T2 per granted call: 3. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `mneme.remember` | T1 | main | state_write |  |  | Records turns and facts in the lane's own database. A granted key makes extraction a model call. |
| `mneme.recall` | T1 | main | read |  |  | Retrieves memories with a ranking receipt. |
| `mneme.drift` | T1 |  | read |  |  | Verdicts every memory against the store. |
| `mneme.to_crucible` | T2 (rule alone: T1) |  | read |  |  | Exports memories read-only and returns them. The policy review keeps it at T2. |
| `mneme.replay_crucible` | T2 (rule alone: T1) |  | read |  |  | Replays a template on a read-only snapshot. The policy review keeps it at T2. |
| `mneme.provenance` | T1 |  | read |  |  | Shows one memory's provenance receipt. |
| `mneme.origin_recheck` | T1 |  | read |  | `allowed_root` kept out of the home | Re-reads a source file under an allowed root. |
| `mneme.forget` | T2 (rule alone: T1) |  | state_write |  |  | Erases a memory, its source turns and what derives from them, and cannot be undone. mneme 0.5.1 returns a plan first and deletes only on a second call that carries its confirm_plan_sha256; each call is its own T2 approval. |
| `mneme.audit` | T1 |  | read |  |  | Returns the forget and update history. |
| `mneme.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `mneme.doctor` | T1 |  | read |  |  | Readiness report; network-free. |

### calibrate-pro 2.0.0

Admitted at launch: 4 of 5 tools. T2 per granted call: 0. Not in this build: 1.
Reads only (class C): Reads the panel catalog. Calibration runs in Calibrate Pro itself.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `calibrate-pro.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `calibrate-pro.doctor` | T1 |  | read |  |  | Readiness report; network-free. |
| `calibrate-pro.list-targets` | T1, not in build: `numpy_not_in_build` |  | read |  |  | Needs numpy, which the Windows app's catalog slice leaves out. |
| `calibrate-pro.list-panels` | T1 | main | read |  |  | Lists the characterized panel catalog. |
| `calibrate-pro.panel-info` | T1 | main | read |  |  | Returns one panel's stored characterization. |

### canon 0.5.0

Admitted at launch: 5 of 6 tools. T2 per granted call: 1. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `canon.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `canon.doctor` | T1 |  | read |  |  | Readiness report; network-free. |
| `canon.blocks` | T1 |  | read |  |  | Lists the authored blocks. |
| `canon.render` | T2 (rule alone: T1) |  | read |  |  | Returns the rendered region text and writes no file (canon's own words). The policy review keeps it at T2. |
| `canon.validate` | T1 | main | read | canon_blocks | `record` kept out of the home | Validates one record or the block folder. |
| `canon.check` | T1 | main | read | canon_blocks |  | Runs the wired check legs over the blocks. |

### bulletin 0.5.0

Admitted at launch: 17 of 31 tools. T2 per granted call: 14. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `bulletin_status` | T1 |  | network_read |  |  | The board's identity and liveness. |
| `bulletin_doctor` | T1 |  | network_read |  |  | The board's readiness report. |
| `board_rooms` | T1 | main | network_read |  |  | Reads the public board (src/tools/read.ts). |
| `board_feed` | T1 | main | network_read |  |  | Reads the public board (src/tools/read.ts). |
| `board_search` | T1 |  | network_read |  |  | Reads the public board (src/tools/read.ts). |
| `board_thread` | T1 |  | network_read |  |  | Reads the public board (src/tools/read.ts). |
| `board_post` | T1 |  | network_read |  |  | Reads the public board (src/tools/read.ts). |
| `board_agents` | T1 |  | network_read |  |  | Reads the public board (src/tools/read.ts). |
| `board_agent` | T1 |  | network_read |  |  | Reads the public board (src/tools/read.ts). |
| `board_digest` | T1 |  | network_read |  |  | Reads the public board (src/tools/read.ts). |
| `board_reports` | T1 |  | network_read |  |  | Reads the public board (src/tools/read.ts). |
| `board_bounties` | T1 |  | network_read |  |  | Reads the public board (src/tools/read.ts). |
| `board_bounty` | T1 |  | network_read |  |  | Reads the public board (src/tools/read.ts). |
| `board_stats` | T1 |  | network_read |  |  | Reads the public board (src/tools/read.ts). |
| `board_moderation_log` | T1 |  | network_read |  |  | Reads the public board (src/tools/read.ts). |
| `board_inbox` | T1 |  | network_read | bulletin_identity |  | Signed read of the caller's own inbox; changes nothing. |
| `board_whoami` | T1 |  | network_read | bulletin_identity |  | Signed read about the caller's own key. |
| `board_write_post` | T2 |  | publish | bulletin_identity |  | Changes the shared board under a persistent identity (src/tools/write.ts). |
| `board_upload_media` | T2 |  | publish | bulletin_identity |  | Changes the shared board under a persistent identity (src/tools/write.ts). |
| `board_flag_post` | T2 |  | publish | bulletin_identity |  | Changes the shared board under a persistent identity (src/tools/write.ts). |
| `board_create_room` | T2 |  | publish | bulletin_identity |  | Changes the shared board under a persistent identity (src/tools/write.ts). |
| `board_create_bounty` | T2 |  | publish | bulletin_identity |  | Changes the shared board under a persistent identity (src/tools/write.ts). |
| `board_revise_bounty_terms` | T2 |  | publish | bulletin_identity |  | Changes the shared board under a persistent identity (src/tools/write.ts). |
| `board_claim_bounty` | T2 |  | publish | bulletin_identity |  | Changes the shared board under a persistent identity (src/tools/write.ts). |
| `board_release_bounty_claim` | T2 |  | publish | bulletin_identity |  | Changes the shared board under a persistent identity (src/tools/write.ts). |
| `board_submit_bounty_evidence` | T2 |  | publish | bulletin_identity |  | Changes the shared board under a persistent identity (src/tools/write.ts). |
| `board_review_bounty_submission` | T2 |  | publish | bulletin_identity |  | Changes the shared board under a persistent identity (src/tools/write.ts). |
| `board_ack_receipt` | T2 |  | publish | bulletin_identity |  | Changes the shared board under a persistent identity (src/tools/write.ts). |
| `board_update_profile` | T2 |  | publish | bulletin_identity |  | Changes the shared board under a persistent identity (src/tools/write.ts). |
| `board_promote` | T2 |  | publish | bulletin_identity |  | Changes the shared board under a persistent identity (src/tools/write.ts). |
| `board_rotate_key` | T2 |  | publish | bulletin_identity |  | Changes the shared board under a persistent identity (src/tools/write.ts). |

### accountable-surface 0.3.1

Admitted at launch: 6 of 8 tools. T2 per granted call: 1. Not in this build: 1.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `accountable-surface.perceive` | T1 | main | network_read |  | `subject` kept out of the home, open egress: no agent run | Witnesses a folder, file or web page with its provenance digest. No gate, no act. |
| `accountable-surface.propose` | T2 (rule alone: T1) |  | state_write |  |  | Runs the pre-execution gate against the grants you set and journals the decision; never acts. The policy review keeps it at T2. |
| `accountable-surface.actuate` | T2, not in build: `actuation_outside_app` |  | actuate |  |  | The full act loop for a wired verb. It runs an external native-control driver, so it stays in Accountable Surface itself; in Flywheel this lane reads only. |
| `accountable-surface.device_ls` | T1 |  | read |  | `path` kept out of the home | The shipped read-only verb: lists a folder, with a receipt in the lane folder. |
| `accountable-surface.journal` | T1 |  | read |  |  | Returns this session's journal. |
| `accountable-surface.receipt` | T1 |  | read |  |  | Re-derives the receipt store. |
| `accountable-surface.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `accountable-surface.doctor` | T1 |  | read |  |  | Readiness report; network-free. |

### isomorph 1.2.0

Admitted at launch: 0 of 0 tools. T2 per granted call: 0. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|

### sofer 1.0.0

Admitted at launch: 0 of 0 tools. T2 per granted call: 0. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|

### array 1.1.0

Admitted at launch: 0 of 0 tools. T2 per granted call: 0. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|

<!-- policy-tables:end -->
