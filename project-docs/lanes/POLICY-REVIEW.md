# Lane tool policy review

Status: decided under O-4 (the agent decided under operator delegation, 2026-09-26). The decision
of record is `POLICY-DECISION.md` in the lanes mission folder; this file renders the table it
adopted. Branch `feat/lanes-operational`.

This review covers every tool of all 17 lanes: 234 tools. The engine admits 141 of them at T1 on
an ordinary lane call. 49 tools need a granted T2 call. 44 tools are out of this build with a
reason slug. The decision counted 133, 45 and 55 before the articulate 0.5.0 pin moved judge,
fix and polish from out of the build to T2. Long-lived lane sessions (WP10) then brought the
five index router-job tools and relay's run status and result in at T1, and relay
`local_agent_start` in at T2. The crucible 1.3.0 pin added `crucible.recheck_template` at T1.
The drop from the first draft (172, 45, 16) is telos
(all 38 of its in-build tools held out under the O-8 hold), `writing.diagnose` (T1 to T2) and
`accountable-surface.actuate` (T2 to out of the build). The 1.0.x rows admitted two tools per
bundled lane (relay one), and nothing checked a tier unless the caller sent one.

The table of record is `harness/lane_tool_policy.py` with its three data files
(`lane_tool_policy_evidence.py`, `lane_tool_policy_agents.py`, `lane_tool_policy_node.py`) and the
argument facts in `lane_tool_policy_args.py`. The per-lane tables at the end of this file are
rendered from it by `python scripts/render_lane_policy_review.py --write`, and
`tests/test_lane_tool_policy.py` fails when they differ.

## The rule the table applies

Each tool carries an `effect`. The T2 rule: a tool whose effect writes outside the lane's own
folder (`outside_write`), spends a model call or provider key (`spend`), publishes under an
identity (`publish`), acts on the device (`actuate`) or decides a human approval (`approve`) is T2.
`validate_policy` refuses a table that breaks the rule. The other effects are `read`,
`network_read`, `state_write` (only the lane's own folder) and `model_call` (the model server the
person set up).

Every lane call already needs an exact, one-use grant the owner approves, so a T1 call is approved
one at a time too. The tier decides which routes can carry the call: `lane.call` carries T2 for
one tool and one call; Plugins carry no tier and refuse anything above T1; an agent run never
reaches T2, since the model picks each inner call and its arguments.

## What the decision changed (C-1 to C-17)

- **Argument guards** (C-1 to C-4, C-14). `allowed_args` is an allowlist: relay `local_agent_run`
  passes only `goal`, `max_steps`, `max_tokens`, `model`, `backend` and `compact_budget`, so
  `root`, `check`, `test_cmd` and `online` never reach a run. Write, exec and online are forced off
  on both agent lanes. learn's `sessionId` and `runId` must be plain ids. A path argument that
  resolves inside the Flywheel home outside the lane folder is refused before a child spawns.
- **writing** (C-5). No writing tool receives a `home`. `writing.diagnose` is T2 main: it writes
  into the engine's journey store, and it needs a recorded draft (`writing_draft`).
- **Held and out** (C-6, C-7). Actuation stays in Accountable Surface. Every telos tool is out
  while the O-8 hold stands.
- **Keys** (C-8). A call that would hand a lane child a provider key is T2; below T2 the key-shaped
  names granted through `env_allow` are stripped from the child.
- **Where a child writes** (C-9, C-10). Every spawned lane child gets TEMP, TMP and the app-data
  folders inside its lane folder; index and accountable-surface keep caches, receipts and journal
  there. Git joins only index's PATH, and only from FLYWHEEL_GIT, a Git for Windows `cmd` folder
  or Program Files.
- **Unlisted tools** (O-12, after the decision). A tool the table does not list is T2 on every
  lane and in every install mode. On a pip or source install it runs only on a `lane.call` the
  owner approved at T2. The frozen build admits listed tools only, so there it is refused even at
  T2. Before this, a pip or source install ran it at the lane floor, T1 on most lanes.
- **Routes** (C-11, C-12, C-15). Plugins and agent runs refuse a tool the table does not list.
  Agent runs also refuse state writes, open egress and path arguments. The node path and the
  local-model project folder are granted actions (`settings.node_path`, `lane.root`), and the
  lane check route is private.
- **The approval sheet** (C-13). A `lane.call` proposal carries a `lane_policy` block: the tier
  needed and requested, the effect, the arguments forced or dropped, and the arguments in plain
  form. The desktop sheet that renders it lands in WP9b.
- **Lane sessions** (WP10, after the decision). A relay background run and an index router job
  live in one long-lived child per lane, so start, status and result sent as separate calls reach
  the same child. `local_agent_start` is T2: it runs only on a call a granted T2 operation carries,
  on a relay launched with write and exec off (relay 0.3.0 and later take both only from their
  launch). The
  run and job ids must be plain ids. Plugins and agent runs cannot reach a session tool, and no
  provider key joins a session child, since it outlives the call. A session ends after 10 idle
  minutes unless its work is still running (then at most one hour after the last call), when its
  child exits, and when the engine stops.
- **Late pins** (PINS_2026-09-26_LATE, after the decision). relay 0.4.0, gather 1.9.0, mneme
  0.5.0 and canon 0.4.1 add no lane tool; each tool keeps its row. The launches adapt: relay keeps
  its session store in `<lane>/sessions` and starts with no `RELAY_CHILD_ENV` names and no
  unproven CLI tier allowed; relay's `session_id` must be a plain id. gather starts with its four
  launch grants (`GATHER_ALLOW_NETWORK`, `GATHER_ALLOW_EXEC`, `GATHER_AUTH_ENV_ALLOW`,
  `GATHER_CHILD_ENV`) empty, since its app tools read a local document or corpus; a T2
  `gather.run` that names a network source, a command or a credential answers `GRANT_REQUIRED`.
  `mneme.forget` stays T2 as a two-step erase. canon's context purge lives on the context
  server, which the engine calls only for health, ingest and query and never starts with
  `CANON_CONTEXT_MCP_PURGE`.
- **Final pins and the finish review** (2026-09-26). mneme 0.5.1 (GHSA-j2pw-g7f4-9ppp) and canon
  0.4.2 (GHSA-48rq-xjfx-6j4f) replace 0.5.0 and 0.4.1 and add no lane tool. A pip or npm lane
  below its pin no longer launches under the default profile (`installed_version_below_pin`),
  install asks for the pinned version, and the context bridge refuses ingest and query through a
  canon below its pin. The home path guard refuses Windows device, NT-object and UNC spellings
  and compares folders by identity; the local-model folder setting follows the same rule. A
  source checkout starts in its lane folder like a pip launch, so the forced grants and scoped
  folders apply in every install mode. A T2 call keeps granted keys only for a listed tool that
  spends a model call; Plugins and the forum and relay GET proxies strip them, and the proxies
  refuse a tool above T1 (`forum.run.room`). `learn_tutor_plan` is refused for a session that
  already has a file. Ids refuse Windows device names, key-shaped names cover `*_AUTH`,
  `*_BEARER`, `*_COOKIE`, `*_DSN` and `*_PASSPHRASE`, and `POST /api/lanes/install` takes a
  `lane.install` grant.
- **Pins 2026-09-27** (O-4, O-12). gather 1.9.1 (GHSA-j6j7-39vh-qrp4,
  GHSA-r38f-cr69-jpp8), relay 0.5.0 (GHSA-82fg-qprm-q5r7) and forum 1.15.1
  (GHSA-36gv-h885-fmjf, GHSA-h6qh-49hv-4xcg) add no lane tool; each tool keeps its row.
  forum 1.15 serves `gate_approve`, `gate_edit` and `gate_reject` only on a launch with
  `--allow-gate-decisions`. Each of the three names that flag as its `launch_grant`,
  and the engine adds it only to the launch of one granted T2 call of that tool: the
  argv of a pip or source launch, the `allow_gate_decisions` keyword of `serve_stdio`
  in the frozen child mode, which refuses any other trailing token. The owner's T2
  approval decides a gate (O-4); an unlisted alias (`forum.gate.approve`) stays T2 with
  no grant (O-12), and no listing, probe, proxy, plugin or agent run carries it. The
  forum card lists the 18 tools of an ordinary launch. forum starts with
  `FORUM_CHILD_ENV` and `FORUM_ALLOW_EXEC_CLI` empty. gather's own `NON_LOCAL_PATH` and a
  lane's `GRANT_REQUIRED` answer as fixed refusals (`argument_refused`,
  `lane_grant_required`). All three vendor safe_spawn 1.0.1; a PATH differential under
  the engine's lane environments, system folder only and a full developer PATH, found
  no program lost.
- **crucible 1.3.0, 2026-09-27** (O-4, O-12). crucible 1.2.0 is inside
  GHSA-49qx-cj4f-wfqv: a measurement file could widen the tolerance that decides MATCH,
  and status and doctor answered MATCH without measuring anything. 1.3.0 fixes both and
  adds one tool, `crucible.recheck_template`, which reads a registry assessment and
  returns a `crucible.replay-template/1` object (`src/crucible/mcp_tools.py`,
  `recheck_cmd.replay_template_payload`). It writes nothing, so it is `read` at T1, with
  `dir` and `index` kept out of the home as on `crucible.report`; `crucible.recheck`
  takes a `template` flag with the same effect. Through the engine's pip-mode launch
  from each tag's source, the lane smoke fixture passes at both tags, the advisory's
  widened-tolerance case reads MATCH at 1.2.0 and UNVERIFIABLE at 1.3.0, no write leaves
  the lane folder, and a `dir` inside the Flywheel home answers `argument_refused`.
- **Measured containment** (C-16). The frozen lane smoke snapshots its throwaway home around each
  lane's fixture and fails a lane that writes outside its folder.

## Limits and open items

- The engine applies these rules at the MCP boundary only. Lanes still run unsandboxed as the same
  OS user; the table governs what a caller can ask a lane to do, not what a compromised lane can
  do.
- `USERPROFILE` stays the user's profile (the claude CLI reads its login there). Writes under it
  outside the smoke's throwaway home are unmeasured.
- `path_args` is a name-based list read from the pinned schemas. A path inside a nested object or a
  free-text field escapes it, and the containment probe measures writes, not reads.
- Timeouts in the table are draft values, unmeasured. The engine applies them on every call and
  clamps a caller's value to 1 .. `timeout_s`.
- bulletin is an http lane; its launch carries no `allowed_tools`, so the tier gate is its only
  tool filter.
- O-13 (class C for calibrate-pro and actuation) is recorded as the default in DECISIONS.json.
- `mneme.forget` erases source turns and derived rows from mneme 0.5.0 on, and 0.5.1 closes the
  gaps GHSA-j2pw-g7f4-9ppp names (known finding 4 closed
  in the lane); its receipt names the residue it cannot reach, such as exports and freed disk
  blocks.

## Node lane evidence (learn 1.6.0; telos 0.4.1 held)

Measured in WP4 on the pinned archives, run on the bundled Node v24.21.0 with a System32 PATH and
an empty home. telos is now held out of every freeze (O-8); its notes describe the held archive.

- telos: every MCP tool ignores its arguments and runs one fixed package script with fixed flags.
  `telos.native.control` is the Chrome DevTools and UI Automation driver and stays out in any
  release. A contained telos release gets a new tool-by-tool review before any tool returns.
- learn: `learn_tutor_plan` and `learn_tutor_record` write one session file under
  `<home>/lanes/learn/tutor/`, joining the caller's `sessionId` into the path, which is why the id
  guard exists. `learn_dry_run`, `learn_tutor_reverify` and `learn_tutor_prooflesson` read a path
  the caller names.
- Every learn tool needs the `node` setup item; the bundled Node meets it.

## Per-lane tables

"Engine sets" lists the argument guards: the allowlist, forced or dropped arguments, id and path
checks, and open egress. "Needs" lists setup item ids from `lane_tool_policy.SETUP_ITEMS`.

<!-- policy-tables:start (scripts/render_lane_policy_review.py) -->

### gather 1.9.1

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

### crucible 1.3.0

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

### articulate 0.5.0

Admitted at launch: 4 of 7 tools. T2 per granted call: 3. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `check` | T1 | main | read |  |  | Local detector; no network. |
| `score` | T1 | main | read |  |  | Local score; no network. |
| `judge` | T2 |  | spend | claude_cli |  | Runs the signed-in claude CLI, a model call on the person's account. articulate 0.5.0 runs it in a fresh empty folder with settings, MCP servers and tools off, from the path the engine passes in ARTICULATE_CLAUDE_CLI. |
| `fix` | T2 |  | spend | claude_cli |  | Runs the signed-in claude CLI, a model call on the person's account. articulate 0.5.0 runs it in a fresh empty folder with settings, MCP servers and tools off, from the path the engine passes in ARTICULATE_CLAUDE_CLI. |
| `polish` | T2 |  | spend | claude_cli |  | Runs the signed-in claude CLI, a model call on the person's account. articulate 0.5.0 runs it in a fresh empty folder with settings, MCP servers and tools off, from the path the engine passes in ARTICULATE_CLAUDE_CLI. |
| `articulate.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `articulate.doctor` | T1 |  | read |  |  | Readiness report; network-free. |

### index 2.13.0

Admitted at launch: 21 of 22 tools. T2 per granted call: 1. Not in this build: 0.

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
| `index_internals` | T1 |  | read |  | `root` kept out of the home | Builds one repo's module graph. |
| `index.router.job.start` | T1 |  | state_write |  | `root` kept out of the home | Runs on the index lane's long-lived session, so the job's worker outlives the call that started it; in a frozen engine the worker runs as --bundled-lane-worker. Job state and caches stay in the lane folder. |
| `index.router.job.status` | T1 |  | read |  | `job_id` a plain id | Runs on the index lane's long-lived session, so the job's worker outlives the call that started it; in a frozen engine the worker runs as --bundled-lane-worker. Job state and caches stay in the lane folder. The job id must be a plain id. |
| `index.router.job.result` | T1 |  | read |  | `job_id` a plain id | Runs on the index lane's long-lived session, so the job's worker outlives the call that started it; in a frozen engine the worker runs as --bundled-lane-worker. Job state and caches stay in the lane folder. The job id must be a plain id. |
| `index.router.job.cancel` | T1 |  | state_write |  | `job_id` a plain id | Runs on the index lane's long-lived session, so the job's worker outlives the call that started it; in a frozen engine the worker runs as --bundled-lane-worker. Job state and caches stay in the lane folder. The job id must be a plain id. |
| `index.router.job.resume` | T1 |  | state_write |  | `job_id` a plain id | Runs on the index lane's long-lived session, so the job's worker outlives the call that started it; in a frozen engine the worker runs as --bundled-lane-worker. Job state and caches stay in the lane folder. The job id must be a plain id. |

### forum 1.15.1

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

### learn 1.6.0

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

### telos 0.4.1

Admitted at launch: 0 of 41 tools. T2 per granted call: 0. Not in this build: 41.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `telos.status` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.doctor` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.room` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.workflow` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.catalog` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.server.manifest` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.mcp.freshness` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.ci.doctor` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.ci.triage` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.presentation.doctor` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.accessibility.doctor` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.performance.doctor` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.compatibility.doctor` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.operator.doctor` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.admission.telemetry` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.context.envelope` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.context.pack` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.action.receipt` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.loop.ledger` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.objective.monitor` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.model.foundry` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.learning.forge` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.learning.labs` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.research.seed` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.research.thermodynamic` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.rendering.research` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.rendering.capabilities` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.measurement.layers` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.creative.engine` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.creative.kernels` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.revival.registry` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.second_level.queue` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.workstation.substrate` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.display.calibration` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.native.control` | T2, not in build: `actuation_outside_app` |  | actuate | node |  | The Chrome DevTools and UI Automation driver; mail, post and listing actions sit behind other arguments. Left out rather than admitted at T2. |
| `telos.browser.evidence` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.showcase.scout` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.proof` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.proof.research` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.proof.visual` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |
| `telos.proof.build` | T1, not in build: `release_on_hold` |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. Held out of this build while its release contents are reviewed. |

### local-model 0.1.0

Admitted at launch: 8 of 9 tools. T2 per granted call: 1. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `local_agent_health` | T1 |  | network_read |  | passes only no argument, `online=false` | Pings the local model tiers; online tiers are forced off. |
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

### relay 0.5.0

Admitted at launch: 9 of 10 tools. T2 per granted call: 1. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `local_agent_health` | T1 |  | network_read |  | passes only no argument, `online=false` | Pings the local model tiers; online tiers are forced off. |
| `local_agent_chat` | T1 |  | model_call | model_server | passes only `prompt`, `backend`, `online=false` | One completion from the first healthy local tier; online tiers are forced off. |
| `local_agent_run` | T1 | main | model_call | model_server | passes only `goal`, `max_steps`, `max_tokens`, `model`, `backend`, `compact_budget`, `allow_write=false`, `allow_exec=false`, `online=false` | Runs an agent task on the model server the person set up. relay 0.5.0 takes write and exec from its launch, which the engine starts with both off and its root at the lane folder; the engine also passes only the listed arguments, so root, check, test_cmd and online never reach the run, and forces write, exec and online off. |
| `local_agent_start` | T2 (rule alone: T1) |  | model_call | model_server | passes only `goal`, `max_steps`, `max_tokens`, `model`, `backend`, `compact_budget`, `allow_write=false`, `allow_exec=false`, `online=false` | Starts the same agent run in the background on the relay lane's long-lived session and returns its run id at once. T2: it holds the model server for minutes with no call waiting on it. relay 0.5.0 takes write and exec from its launch, which the engine starts with both off and its root at the lane folder; the engine passes only the listed arguments and forces write, exec and online off. |
| `local_agent_status` | T1 |  | read |  | passes only `run_id`, `run_id` a plain id | Reads a background run from the relay lane session, where the run lives; the run id must be a plain id. |
| `local_agent_result` | T1 |  | read |  | passes only `run_id`, `run_id` a plain id | Reads a background run from the relay lane session, where the run lives; the run id must be a plain id. |
| `local_agent_runs` | T1 |  | read |  | passes only `limit` | Lists the runs the relay lane session holds. |
| `local_agent_sessions` | T1 |  | read |  | `session_id` a plain id | Lists saved sessions and re-verifies each. |
| `relay.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `relay.doctor` | T1 |  | read |  |  | Readiness report; network-free. |

### plexus 0.2.2

Admitted at launch: 6 of 6 tools. T2 per granted call: 0. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `plexus_discover` | T1 |  | read |  | `dir` kept out of the home | Reads interop manifests and returns the mesh. |
| `plexus_wiring` | T1 |  | read |  | `dir` kept out of the home | Returns the capability wiring map. |
| `plexus_plan` | T1 | main | read |  | `dir` kept out of the home | Returns the pipeline that feeds a target organ. |
| `plexus_route` | T1 | main | read |  | `dir` kept out of the home | Returns the shortest capability path. |
| `plexus.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `plexus.doctor` | T1 |  | read |  |  | Readiness report; network-free. |

### mneme 0.5.1

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

### canon 0.4.2

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

<!-- policy-tables:end -->
