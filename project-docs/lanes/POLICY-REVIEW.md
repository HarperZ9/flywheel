# Lane tool policy review

Status: draft for operator review before merge (decision O-4). Branch `feat/lanes-operational`.

This review covers every tool of all 17 lanes: 233 tools. The engine admits 172 of them at T1 on
an ordinary lane call. 45 tools need a granted T2 call. 16 tools are out of this build with a
reason slug. The 1.0.x rows admitted two tools per bundled lane (relay one), and nothing checked a
tier unless the caller sent one.

The table of record is `harness/lane_tool_policy.py` with its three data files
(`lane_tool_policy_evidence.py`, `lane_tool_policy_agents.py`, `lane_tool_policy_node.py`). The
per-lane tables at the end of this file are rendered from it by
`python scripts/render_lane_policy_review.py --write`, and `tests/test_lane_tool_policy.py` fails
when they differ.

## The rule the draft applies

Each tool carries an `effect`. The T2 rule: a tool whose effect writes outside the lane's own
folder (`outside_write`), spends a model call or provider key (`spend`), publishes under an
identity (`publish`), acts on the device (`actuate`) or decides a human approval (`approve`) is T2.
`validate_policy` refuses a table that breaks the rule. The other effects are `read`,
`network_read`, `state_write` (only the lane's own folder) and `model_call` (the model server the
person set up; a provider key reaches it only through a per-call grant).

Section 1a of the plan is the starting draft. Where section 1a puts a tool at T2 and its effect
alone allows T1, the draft keeps T2 and the table says "rule alone: T1". Where a T1 tool in
section 1a takes one argument that would write elsewhere or widen a grant, the engine forces or
drops that argument (`forced_args`) and the tool stays T1.

## Decisions for the operator

1. **Listed tiers beat the lane floor.** relay, local-model and accountable-surface carry a T2
   floor in `lane_caller.LANE_MIN_TIERS`. The draft lets the table open their listed read and run
   tools at T1 (23 tools, listed in `tests/test_lane_caller.py::REVIEWED_BELOW_FLOOR`). The floor
   still applies to a tool the table does not list. Approve, or keep the floor over the table.
2. **A call without a tier runs at T1.** 1.0.x skipped the tier check when no tier was sent. The
   engine now computes the tier on every call. This also changes pip and source installs for the
   45 listed T2 tools, which were callable there with no tier. Unlisted tools keep the floor
   (O-12 default). Approve, or limit the change to the frozen build.
3. **Stricter than the rule.** 19 tools sit at T2 only because section 1a put them there (the
   "rule alone: T1" rows). The largest group is 9 writing tools: 8 records that prepare a
   proposal and change nothing until a commit, and the commit, which changes the manuscript inside
   the writing workspace. That leaves `writing.diagnose` (main) dependent on T2 tools to create
   its project. Others: `gather.federation`, `index.invalidate`, `forum.prose.humanize`
   (fixed rules, no model), `forum.run.room` (a snapshot read), `mneme.to_crucible` and
   `mneme.replay_crucible` (read-only), `mneme.forget` (irreversible delete inside the lane
   database), `canon.render` (returns text, writes no file), `accountable-surface.propose` (the
   gate check; never acts), `learn_tutor_record`. Lower any of them to T1, or keep.
4. **Argument guards.** The engine forces `allow_write=false` and `allow_exec=false` on relay and
   local-model `local_agent_run`, drops `resume_state` from `index.map`, drops `out` from
   `crucible.report`, and forces `apply=false` on `crucible.registry` (prune stays a dry run). No
   route can pass those arguments. Approve, or move a tool to T2 with its full arguments.
5. **Agent runs.** An agent run may select a lane tool only when it is T1, in the build and has no
   argument guard, because the agent runtime passes the model's arguments through. That keeps
   `index.map` and both `local_agent_run` tools out of agent runs. Approve, or add a guard hook to
   the agent runtime (`gateway_agent_mcp_runtime.py`, outside this package).
6. **Tools section 1a did not name.** relay `local_agent_chat` (T1, model call), local-model
   `flywheel.context.health`, `flywheel.context.preflight`, `receipt.verify_inclusion` (T1 reads)
   and `flywheel.context.capture` (T2: writes the Canon context store), index `index_router` (T1:
   returns the map, writes nothing), forum's older names `route`, `status`, `verify`,
   `ledger_get` (T1) and `submit` (T2), bulletin `board_reports`, `board_bounties`,
   `board_bounty` (T1 reads; 1.0.x left them unlisted, so they needed T2), `board_ack_receipt`
   (T2: moves the inbox cursor on the board).
7. **Corrections to section 1a from the source.** bulletin `board_post` is a read in
   `src/tools/read.ts` (it fetches one post), so the draft keeps it T1; the board's writes are the
   14 tools in `write.ts`. forum `plan` runs the configured executor: the echo executor by default,
   one model call once FORUM_RUN_REAL and a key are set. The draft keeps it T1 main with effect
   `model_call`, the same footing as relay `local_agent_run`.
8. **Tool listing approval.** `/api/lanes/<lane>/tools` (WP8) keeps the `plugin.probe` approval
   unless you decide otherwise.
9. **mneme `remember` at T1** (plan note): it writes only the lane's own database. A granted key
   makes extraction a model call. Approve or move to T2.

## Changes from the 1.0.x status-and-doctor boundary

1. Frozen admission. Each payload row's `allowed_tools` was `<lane>.status` and `<lane>.doctor`;
   relay's compiled expectation was `relay.status` alone. Every row now admits the table's T1
   tools that are in the build (for example gather 5 of 8, index 16 of 22, relay 7 of 10). All 12
   rows were regenerated from their pinned revisions through the WP1 generator; only
   `allowed_tools`, `does_not_prove`, `packaging_boundary` and the descriptor digests changed.
   The relay descriptor (`packaging/bundled-lanes/relay.json`) and its compiled digest in
   `harness/bundled_lane_expectations.py` changed with it.
2. `packaging_boundary` changes from `..._status_doctor_tools_only` to `..._policy_t1_tools_only`,
   and each row carries a new does-not-prove line: T2 tools reach a lane through the engine only on
   a granted T2 call, and the lane module itself still serves them.
3. The frozen local-model and writing launches carried no `allowed_tools`; they now carry the T1
   list, so `flywheel.context.capture` and the T2 writing records are out of a plain call.
4. The tier check runs on every lane call (decision 2). A granted T2 call widens a restricted
   launch by its one tool for that call only; a tool out of the build is never widened.
5. Plugins (`plugin.call`) refuse a lane tool that needs more than T1, before anything spawns, and
   say `required_tier` and `route: lane.call`. 1.0.x checked `allowed_tools` alone, so a pip or
   source install reached every lane tool through Plugins.
6. Agent runs refuse T2, out-of-build and guarded lane tools (decision 5).
7. Argument guards apply on the lane call and Plugins routes in every install mode (decision 4).
8. A tool the build leaves out now answers `NOT_IN_BUILD` with a reason slug on the engine side;
   1.0.x answered `CAPABILITY_NOT_ADMITTED`. The HTTP boundary still masks it as `EXTERNAL_ACTION_FAILED`
   until WP8 adds the code to `public_boundary`.
9. `list_available_lanes` carries `tool_tiers` for all 17 lanes; 1.0.x carried them for bulletin alone.
10. bulletin tools the table lists take their listed tier; an unlisted bulletin tool still takes T2.

## Measured on this branch

- `tests/test_lane_tool_policy.py`: the table lists exactly the tools each lane serves (payload
  rows, Node pins, the engine's `local_mcp` and `writing_mcp`, bulletin 0.5.0 read from tag
  v0.5.0); every rule-covered tool is T2; the section 1a T2 list, main tools and out-of-build
  lists hold; the rendered tables match this file.
- `tests/test_lane_tier_enforcement.py`: each route above, through the real gate with a fake
  client.
- A local freeze of the release spec (`build/wp7-dist`), then a granted `lane.call` through the
  frozen engine's HTTP route (`build/wp7-frozen-tier-probe.txt`): `gather.run` with no tier gave
  403 with the governance gate; `canon.render` with a granted T2 gave 200 (the launch widened for
  that call) and 403 without it; relay `local_agent_run` asked for write and exec and ran with
  `allow_write` and `allow_exec` false in relay's own request binding; `index.map` with a
  `resume_state` path answered and wrote no file there; the relay roster launch lists the 7 T1
  tools.
- The WP0 lane smoke on that freeze: 10 lanes now reach their main tool through the admitted
  launch (accountable-surface, articulate, calibrate-pro, chorus, crucible, forum, gather, index,
  mneme, plexus), and their rows rise to `main`. relay also reached `main` here only because this
  machine runs Ollama at 127.0.0.1:11434; its row stays `health`, the expected result without a
  model server (inferred, not measured on a machine without one).

## Limits and open items

- Timeouts in the table are draft values, unmeasured. `/api/lane/...` still defaults to 20 s when
  the caller sends none; WP8 owns that route.
- index writes its caches under `%LOCALAPPDATA%\index_graph`, outside the lane folder. The draft
  classes the index tools as reads; pointing `INDEX_CACHE_DIR`, `INDEX_MCP_CACHE_DIR` and
  `INDEX_GRAPH_REPO_CACHE_DIR` at the lane folder belongs in the bundled environment (WP3 files).
- bulletin is an http lane; its launch carries no `allowed_tools`, so the tier gate is its only
  tool filter in this branch.
- relay stays pinned at 0.2.5 here. 0.3.0 (grants from the launch only) is published; moving the
  pin, the submodule and the relay row is not done in this package.
- articulate stays pinned at 0.4.0; judge, fix and polish stay out until the 0.5.0 pin and a
  resolved `claude` path land (O-14).
- `GET /api/forum/run-room` calls `forum.run.room`, which stays T2, so the frozen build refuses it,
  as 1.0.x did.
- `mneme.forget` leaves raw turn text (known finding 4).

## Node lane evidence (learn 1.6.0, telos 0.4.1)

Measured in WP4 on the pinned archives: telos `project-telos-mcp-0.4.1.tgz` (release v0.4.1, tag
commit `3cb786d0`) and learn `@harperz9/learn@1.6.0`, both pinned in
`packaging/node-lane-payloads.json`, run on the bundled Node v24.21.0 with a System32 PATH and an
empty home.

- telos: every MCP tool ignores its arguments and runs one fixed package script with fixed flags,
  so a tool's reach is its script. All 41 tools answered from the packed archive; no file appeared
  in the lane folder. `telos.native.control` is the Chrome DevTools and UI Automation driver (mail,
  post and listing actions sit behind other arguments), so the draft leaves it out rather than
  admit it at T2; over MCP today it only prints its capability catalog. `telos.room` and
  `telos.workflow` run `python` against sibling source checkouts an installed app does not have.
  The plan's acceptance row "a Chrome tool without Chrome returns `LANE_SETUP_REQUIRED`" has no
  tool to test in 0.4.1 and needs rewording in WP11.
- learn: `learn_tutor_plan` and `learn_tutor_record` write one session file under
  `<home>/lanes/learn/tutor/`. The crucible, gather and telos interop commands are CLI only in
  1.6.0, so no MCP tool is out of the build for that reason. `learn_dry_run` and
  `learn_tutor_prooflesson` read a path the caller names, the same exposure as other lanes' path
  inputs.
- Every tool of both lanes needs the `node` setup item; the bundled Node meets it.

## Per-lane tables

"Engine sets" lists the forced arguments. "Needs" lists setup item ids from
`lane_tool_policy.SETUP_ITEMS`.

<!-- policy-tables:start (scripts/render_lane_policy_review.py) -->

### gather 1.8.2

Admitted at launch: 5 of 8 tools. T2 per granted call: 3. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `gather.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `gather.doctor` | T1 |  | read |  |  | Readiness report; network-free. |
| `gather.docs` | T1 | main | read |  |  | Reads a local file or folder and returns catalog rows and digests; writes nothing. |
| `gather.arxiv` | T1 |  | network_read |  |  | Fetches arXiv metadata and returns rows; writes nothing. |
| `gather.federation` | T2 (rule alone: T1) |  | read |  |  | Validates or plans a registry in memory. Section 1a puts it at T2. |
| `gather.run` | T2 |  | outside_write |  |  | Runs a multi-source config over the network and writes the corpus store the config names. |
| `gather.context` | T1 | main | read |  |  | Reads a corpus and returns bounded excerpts or a selection; writes nothing. |
| `gather.pilot` | T2 |  | outside_write |  |  | Runs, refreshes or bundles a pilot into the output folders the caller names. |

### crucible 1.2.0

Admitted at launch: 10 of 13 tools. T2 per granted call: 3. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `crucible.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `crucible.doctor` | T1 |  | read |  |  | Readiness report; network-free. |
| `crucible.assess` | T1 | main | read |  |  | Assesses a thesis against measurements in memory and returns verdicts. |
| `crucible.recheck` | T1 |  | read |  |  | Reads a registry and replays a pack the caller names; writes nothing. |
| `crucible.run` | T2 |  | outside_write |  |  | Writes the registry, report, packet and bundle paths the caller names. |
| `crucible.measurement_gate` | T1 |  | read |  |  | Checks a packet against criteria. |
| `crucible.review` | T1 |  | read |  |  | Validates a review bundle. |
| `crucible.report` | T1 |  | read |  | drops `out` | Renders a report and returns it. The engine drops `out`, which would write a file. |
| `crucible.batch` | T2 |  | outside_write |  |  | Assesses a manifest into the registry the caller names. |
| `crucible.registry` | T1 |  | read |  | `apply=false` | Lists, verifies or searches a registry. The engine forces `apply` false, so prune stays a dry run. |
| `crucible.drift` | T1 |  | read |  |  | Compares the two latest assessments in a registry. |
| `crucible.refine` | T2 |  | outside_write |  |  | Runs the refine loop into the registry the caller names. |
| `crucible.verdicts` | T1 |  | read |  |  | Lists or re-checks assessments in a registry. |

### chorus 0.3.1

Admitted at launch: 6 of 6 tools. T2 per granted call: 0. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `chorus.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `chorus.doctor` | T1 |  | read |  |  | Readiness report; network-free. |
| `chorus.run` | T1 | main | read |  |  | Digests a corpus in memory and returns themes with a receipt. |
| `chorus.corpora` | T1 |  | read |  |  | Lists gather corpora under a folder. |
| `chorus.digests` | T1 |  | read |  |  | Lists digests a daemon stored. |
| `chorus.decision` | T1 |  | read |  |  | Compares two source packs and returns a review gate. |

### articulate 0.4.0

Admitted at launch: 4 of 7 tools. T2 per granted call: 0. Not in this build: 3.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `check` | T1 | main | read |  |  | Local detector; no network. |
| `score` | T1 | main | read |  |  | Local score; no network. |
| `judge` | T2, not in build: `claude_cli_not_resolvable` |  | spend | claude_cli |  | Runs the claude CLI, a model call. Out of this build until the articulate 0.5.0 pin and a resolved claude path land (O-14). |
| `fix` | T2, not in build: `claude_cli_not_resolvable` |  | spend | claude_cli |  | Runs the claude CLI, a model call. Out of this build until the articulate 0.5.0 pin and a resolved claude path land (O-14). |
| `polish` | T2, not in build: `claude_cli_not_resolvable` |  | spend | claude_cli |  | Runs the claude CLI, a model call. Out of this build until the articulate 0.5.0 pin and a resolved claude path land (O-14). |
| `articulate.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `articulate.doctor` | T1 |  | read |  |  | Readiness report; network-free. |

### index 2.13.0

Admitted at launch: 16 of 22 tools. T2 per granted call: 1. Not in this build: 5.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `index.map` | T1 | main | read | git | drops `resume_state` | Maps a repository. Needs Git for branch and history. The engine drops `resume_state`, which would write a file. |
| `index.context` | T1 |  | read |  |  | Builds a dependency context pack. |
| `index.context.envelope` | T1 |  | read |  |  | Builds a budgeted context envelope. |
| `index.select` | T1 |  | read |  |  | Selects paths with rejection receipts. |
| `index.invalidate` | T2 (rule alone: T1) |  | read |  |  | Mints or checks a tree pin and returns it. Section 1a puts it at T2. |
| `index.wiki` | T1 |  | read |  |  | Builds or verifies a wiki pack and returns it. |
| `index.symbol-graph` | T1 |  | read |  |  | Builds a symbol graph for one repo. |
| `index.symbol-definition` | T1 | main | read |  |  | Finds a symbol's definition from the AST. |
| `index.symbol-references` | T1 | main | read |  |  | Finds a symbol's resolved callers. |
| `index.symbol-implementations` | T1 |  | read |  |  | Finds subclasses and overrides. |
| `index.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `index.doctor` | T1 |  | read |  |  | Readiness report; network-free. |
| `index_graph` | T1 |  | read |  |  | Builds a repo dependency graph. |
| `index_focus` | T1 |  | read |  |  | Returns one repo's dependency neighborhood. |
| `index_verify` | T1 |  | read |  |  | Grounds a structural claim with file:line evidence. |
| `index_router` | T1 |  | read |  |  | Builds a workspace map and returns it; writes nothing. |
| `index_internals` | T1 |  | read |  |  | Builds one repo's module graph. |
| `index.router.job.start` | T1, not in build: `per_call_child_ends_job` |  | state_write |  |  | A background router job dies with the per-call lane child. Out of this build until long-lived lane sessions land (WP10). |
| `index.router.job.status` | T1, not in build: `per_call_child_ends_job` |  | read |  |  | A background router job dies with the per-call lane child. Out of this build until long-lived lane sessions land (WP10). |
| `index.router.job.result` | T1, not in build: `per_call_child_ends_job` |  | read |  |  | A background router job dies with the per-call lane child. Out of this build until long-lived lane sessions land (WP10). |
| `index.router.job.cancel` | T1, not in build: `per_call_child_ends_job` |  | state_write |  |  | A background router job dies with the per-call lane child. Out of this build until long-lived lane sessions land (WP10). |
| `index.router.job.resume` | T1, not in build: `per_call_child_ends_job` |  | state_write |  |  | A background router job dies with the per-call lane child. Out of this build until long-lived lane sessions land (WP10). |

### forum 1.14.0

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
| `forum.prose.humanize` | T2 (rule alone: T1) |  | read |  |  | Rewrites prose by fixed rules, no model. Section 1a puts it at T2. |
| `forum.prose.contract` | T1 |  | read |  |  | Returns the deterministic communication contract. |
| `forum.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `forum.doctor` | T1 |  | read |  |  | Readiness report; network-free. |
| `forum.ledger.summary` | T1 |  | read |  |  | Summarizes the ledger. |
| `forum.ledger.capsule` | T1 |  | read |  |  | Compacts the ledger into a capsule and returns it. |
| `forum.run.room` | T2 (rule alone: T1) |  | read |  |  | Projects the latest run into a snapshot. Section 1a puts it at T2. |
| `forum.runtime.inspect` | T1 |  | read |  |  | Reports the executor policy without running a model. |
| `forum.context.preflight` | T1 |  | read |  |  | Estimates context pressure before a submit. |
| `gate_list` | T1 |  | read |  |  | Lists paused approval gates. |
| `gate_approve` | T2 |  | approve |  |  | Resolves a paused human-approval gate. An agent must not approve its own wave. |
| `gate_edit` | T2 |  | approve |  |  | Resolves a paused human-approval gate. An agent must not approve its own wave. |
| `gate_reject` | T2 |  | approve |  |  | Resolves a paused human-approval gate. An agent must not approve its own wave. |

### learn 1.6.0

Admitted at launch: 14 of 15 tools. T2 per granted call: 1. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `learn_doctor` | T1 |  | read | node |  | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_status` | T1 |  | read | node |  | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_verify` | T1 |  | read | node |  | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_receipt` | T1 |  | read | node |  | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_dry_run` | T1 | main | read | node |  | Checks a workflow step by step without running it; reads the file the caller names. |
| `learn_tutor_plan` | T1 | main | state_write | node |  | Writes one session file under <home>/lanes/learn/tutor/, the lane's own folder. |
| `learn_tutor_record` | T2 (rule alone: T1) |  | state_write | node |  | Writes one session file under <home>/lanes/learn/tutor/, the lane's own folder. Section 1a puts it at T2. |
| `learn_tutor_mastery` | T1 |  | read | node |  | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_visualize_dry_run` | T1 |  | read | node |  | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_tutor_due` | T1 |  | read | node |  | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_tutor_studyplan` | T1 |  | read | node |  | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_tutor_misconceptions` | T1 |  | read | node |  | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_tutor_reverify` | T1 |  | read | node |  | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_tutor_derive_schedule` | T1 |  | read | node |  | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |
| `learn_tutor_prooflesson` | T1 |  | read | node |  | Reads a saved run or session in the lane folder, or a file the caller names, and returns JSON. |

### telos 0.4.1

Admitted at launch: 38 of 41 tools. T2 per granted call: 0. Not in this build: 3.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `telos.status` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.doctor` | T1 | main | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.room` | T1, not in build: `needs_source_checkouts` |  | read | node |  | Runs python against sibling source checkouts an installed app does not have. |
| `telos.workflow` | T1, not in build: `needs_source_checkouts` |  | read | node |  | Runs python and node by name against sibling source checkouts and writes temp files. |
| `telos.catalog` | T1 | main | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.server.manifest` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.mcp.freshness` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.ci.doctor` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.ci.triage` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.presentation.doctor` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.accessibility.doctor` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.performance.doctor` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.compatibility.doctor` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.operator.doctor` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.admission.telemetry` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.context.envelope` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.context.pack` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.action.receipt` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.loop.ledger` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.objective.monitor` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.model.foundry` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.learning.forge` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.learning.labs` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.research.seed` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.research.thermodynamic` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.rendering.research` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.rendering.capabilities` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.measurement.layers` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.creative.engine` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.creative.kernels` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.revival.registry` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.second_level.queue` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.workstation.substrate` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.display.calibration` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.native.control` | T2, not in build: `actuation_outside_app` |  | actuate | node |  | The Chrome DevTools and UI Automation driver; mail, post and listing actions sit behind other arguments. Left out rather than admitted at T2. |
| `telos.browser.evidence` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.showcase.scout` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.proof` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.proof.research` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.proof.visual` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |
| `telos.proof.build` | T1 |  | read | node |  | Runs one fixed package script that reads files inside the package and prints JSON; the MCP mapping passes no arguments. |

### local-model 0.1.0

Admitted at launch: 8 of 9 tools. T2 per granted call: 1. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `local_agent_health` | T1 |  | network_read |  |  | Pings the local model tiers. |
| `local_agent_chat` | T1 | main | model_call | model_server |  | One completion from the first healthy tier. |
| `local_agent_run` | T1 | main | model_call | model_server, project_folder | `allow_write=false`, `allow_exec=false` | Runs an agent task inside the picked project folder. Write and exec come from the launch and default off; the engine forces both off in the call. |
| `local-model.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `local-model.doctor` | T1 |  | read |  |  | Readiness report; network-free. |
| `flywheel.context.health` | T1 |  | read |  |  | Reports the Canon context bridge status. Not named in section 1a. |
| `flywheel.context.capture` | T2 |  | outside_write |  |  | Writes captured context into the Canon context store, outside the lane folder. |
| `flywheel.context.preflight` | T1 |  | read |  |  | Searches the Canon context store. Not named in section 1a. |
| `receipt.verify_inclusion` | T1 |  | read |  |  | Checks a receipt digest against the Merkle log. Not named in section 1a. |

### writing 0.1.0

Admitted at launch: 4 of 14 tools. T2 per granted call: 9. Not in this build: 1.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `writing.status` | T1 |  | read |  |  | Lists the owner's writing projects. |
| `writing.doctor` | T1 |  | read |  |  | Reports writing workflow readiness. |
| `writing.project_init` | T2 (rule alone: T1) |  | state_write |  |  | Prepares a proposal in the writing workspace under the Flywheel home; nothing changes until a commit. Section 1a puts the records at T2. |
| `writing.section_record` | T2 (rule alone: T1) |  | state_write |  |  | Prepares a proposal in the writing workspace under the Flywheel home; nothing changes until a commit. Section 1a puts the records at T2. |
| `writing.revision_record` | T2 (rule alone: T1) |  | state_write |  |  | Prepares a proposal in the writing workspace under the Flywheel home; nothing changes until a commit. Section 1a puts the records at T2. |
| `writing.diagnose` | T1 | main | state_write |  |  | Prepares a reader-flow diagnostic proposal for a revision. |
| `writing.card_record` | T2 (rule alone: T1) |  | state_write |  |  | Prepares a proposal in the writing workspace under the Flywheel home; nothing changes until a commit. Section 1a puts the records at T2. |
| `writing.candidate_record` | T2 (rule alone: T1) |  | state_write |  |  | Prepares a proposal in the writing workspace under the Flywheel home; nothing changes until a commit. Section 1a puts the records at T2. |
| `writing.decision_record` | T2 (rule alone: T1) |  | state_write |  |  | Prepares a proposal in the writing workspace under the Flywheel home; nothing changes until a commit. Section 1a puts the records at T2. |
| `writing.review_prepare` | T2 (rule alone: T1) |  | state_write |  |  | Prepares a proposal in the writing workspace under the Flywheel home; nothing changes until a commit. Section 1a puts the records at T2. |
| `writing.export_prepare` | T2 (rule alone: T1) |  | state_write |  |  | Prepares a proposal in the writing workspace under the Flywheel home; nothing changes until a commit. Section 1a puts the records at T2. |
| `writing.proposal_get` | T1 |  | read |  |  | Reads one proposal preview. |
| `writing.proposal_approve` | T2, not in build: `approval_cli_only` |  | approve |  |  | Unavailable over MCP by design; approval runs from the CLI. |
| `writing.proposal_commit` | T2 (rule alone: T1) |  | state_write |  |  | Commits a proposal that an approval outside MCP granted; changes the manuscript in the writing workspace. Section 1a puts the records at T2. |

### relay 0.2.5

Admitted at launch: 7 of 10 tools. T2 per granted call: 0. Not in this build: 3.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `local_agent_health` | T1 |  | network_read |  |  | Pings the local model tiers. |
| `local_agent_chat` | T1 |  | model_call | model_server |  | One completion from the first healthy tier. Not named in section 1a. |
| `local_agent_run` | T1 | main | model_call | model_server | `allow_write=false`, `allow_exec=false` | Runs an agent task on the model server the person set up. The engine forces write and exec off, so the run reads and proposes only. |
| `local_agent_start` | T2 (rule alone: T1), not in build: `per_call_child_ends_run` |  | model_call |  | `allow_write=false`, `allow_exec=false` | A background run dies with the per-call lane child. Out of this build until long-lived lane sessions land (WP10) and relay start is allowed (O-3). |
| `local_agent_status` | T1, not in build: `per_call_child_ends_run` |  | read |  |  | A background run dies with the per-call lane child. Out of this build until long-lived lane sessions land (WP10) and relay start is allowed (O-3). |
| `local_agent_result` | T1, not in build: `per_call_child_ends_run` |  | read |  |  | A background run dies with the per-call lane child. Out of this build until long-lived lane sessions land (WP10) and relay start is allowed (O-3). |
| `local_agent_runs` | T1 |  | read |  |  | Lists recorded runs. |
| `local_agent_sessions` | T1 |  | read |  |  | Lists saved sessions and re-verifies each. |
| `relay.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `relay.doctor` | T1 |  | read |  |  | Readiness report; network-free. |

### plexus 0.2.2

Admitted at launch: 6 of 6 tools. T2 per granted call: 0. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `plexus_discover` | T1 |  | read |  |  | Reads interop manifests and returns the mesh. |
| `plexus_wiring` | T1 |  | read |  |  | Returns the capability wiring map. |
| `plexus_plan` | T1 | main | read |  |  | Returns the pipeline that feeds a target organ. |
| `plexus_route` | T1 | main | read |  |  | Returns the shortest capability path. |
| `plexus.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `plexus.doctor` | T1 |  | read |  |  | Readiness report; network-free. |

### mneme 0.4.2

Admitted at launch: 8 of 11 tools. T2 per granted call: 3. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `mneme.remember` | T1 | main | state_write |  |  | Records turns and facts in the lane's own database. A granted key makes extraction a model call. |
| `mneme.recall` | T1 | main | read |  |  | Retrieves memories with a ranking receipt. |
| `mneme.drift` | T1 |  | read |  |  | Verdicts every memory against the store. |
| `mneme.to_crucible` | T2 (rule alone: T1) |  | read |  |  | Exports memories read-only and returns them. Section 1a puts it at T2. |
| `mneme.replay_crucible` | T2 (rule alone: T1) |  | read |  |  | Replays a template on a read-only snapshot. Section 1a puts it at T2. |
| `mneme.provenance` | T1 |  | read |  |  | Shows one memory's provenance receipt. |
| `mneme.origin_recheck` | T1 |  | read |  |  | Re-reads a source file under an allowed root. |
| `mneme.forget` | T2 (rule alone: T1) |  | state_write |  |  | Deletes a memory in the lane's database and cannot be undone; raw turn text stays (known finding 4). Section 1a puts it at T2. |
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
| `calibrate-pro.list-targets` | T1, not in build: `numpy_not_in_build` |  | read |  |  | Needs numpy, which the catalog slice leaves out (O-2). |
| `calibrate-pro.list-panels` | T1 | main | read |  |  | Lists the characterized panel catalog. |
| `calibrate-pro.panel-info` | T1 | main | read |  |  | Returns one panel's stored characterization. |

### canon 0.2.0

Admitted at launch: 5 of 6 tools. T2 per granted call: 1. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `canon.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `canon.doctor` | T1 |  | read |  |  | Readiness report; network-free. |
| `canon.blocks` | T1 |  | read |  |  | Lists the authored blocks. |
| `canon.render` | T2 (rule alone: T1) |  | read |  |  | Returns the rendered region text and writes no file (canon's own words). Section 1a puts it at T2. |
| `canon.validate` | T1 | main | read | canon_blocks |  | Validates one record or the block folder. |
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

Admitted at launch: 6 of 8 tools. T2 per granted call: 2. Not in this build: 0.

| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |
|---|---|---|---|---|---|---|
| `accountable-surface.perceive` | T1 | main | network_read |  |  | Witnesses a folder, file or web page with its provenance digest. No gate, no act. |
| `accountable-surface.propose` | T2 (rule alone: T1) |  | state_write |  |  | Runs the pre-execution gate against the operator's grants and journals the decision; never acts. Section 1a puts it at T2. |
| `accountable-surface.actuate` | T2 |  | actuate | actuation_grant |  | The full act loop for a wired verb. |
| `accountable-surface.device_ls` | T1 |  | read |  |  | The shipped read-only verb: lists a folder, with a receipt in the temp folder. |
| `accountable-surface.journal` | T1 |  | read |  |  | Returns this session's journal. |
| `accountable-surface.receipt` | T1 |  | read |  |  | Re-derives the receipt store. |
| `accountable-surface.status` | T1 |  | read |  |  | Identity and liveness; network-free. |
| `accountable-surface.doctor` | T1 |  | read |  |  | Readiness report; network-free. |

<!-- policy-tables:end -->
