# Lane tool policy review

Status: draft for operator review before merge (decision O-4). This file starts with the two Node
lanes, which ship for the first time on this branch (O-1 b bundles Node; O-8 ships telos from its
v0.4.1 GitHub release). The policy content for the other lanes joins this file with WP7.

The table of record is `harness/lane_tool_policy.py`; the Node lane draft lives in
`harness/lane_tool_policy_node.py`. A launch admits a lane's T1 tools that are in the build. A T2 tool
needs a granted operation per call. A `not_in_build` tool is never admitted.

## What was measured

- Archives: telos `project-telos-mcp-0.4.1.tgz`, sha256 `9797ea6b...a56264`, from release `v0.4.1`
  (tag commit `3cb786d0`, not a draft or prerelease), and learn `@harperz9/learn@1.6.0` from npm,
  integrity `sha512-n1IPaGKo...`. Both are pinned in `packaging/node-lane-payloads.json`.
- Runtime: Node v24.21.0 (LTS Krypton, released 2026-09-07), the newest LTS line in the nodejs.org
  release index on 2026-09-26. The v26 line was newer but not LTS.
- Tool lists come from `tools/list` of the packed archives: learn 15 tools, telos 41 tools.
- Every telos tool was called once from the packed archive with Node v24.21.0, a System32-only PATH
  and an empty home folder. All 41 returned a result without an error flag. `telos.room` and
  `telos.workflow` returned status `UNVERIFIABLE`, since they need sibling source checkouts. No file
  appeared in the lane folder.
- Through the Flywheel launch (`harness/node_lanes.py`, frozen layout) with the bundled Node:
  `telos.catalog` returned the catalog (42,209 characters), `telos.doctor` returned `MATCH`,
  `learn_doctor` returned `MATCH`, `learn_dry_run` returned `halted-assess` on a two-step test
  workflow, and `learn_tutor_plan` wrote one session file under `<home>/lanes/learn/tutor/`. A call
  to `telos.native.control` was refused with `CAPABILITY_NOT_ADMITTED`.

## telos 0.4.1 (41 tools)

Every telos MCP tool ignores its arguments. `demo/telos-mcp.mjs` maps each tool name to one script of
the package and fixed flags, and runs it with the same Node. A tool's reach is therefore its script
with those flags, and the draft classifies each tool by reading that script.

| Tier | Tools | Why |
|---|---|---|
| T1, main | `telos.catalog`, `telos.doctor` | the lane's main action in the plan (read the catalog and the doctor) |
| T1 | `telos.status`, `server.manifest`, `mcp.freshness`, `ci.doctor`, `ci.triage`, the five `*.doctor` tools for presentation, accessibility, performance, compatibility and operator, `admission.telemetry`, `context.envelope`, `context.pack`, `action.receipt`, `loop.ledger`, `objective.monitor`, `model.foundry`, `learning.forge`, `learning.labs`, `research.seed`, `research.thermodynamic`, `rendering.research`, `rendering.capabilities`, `measurement.layers`, `creative.engine`, `creative.kernels`, `revival.registry`, `second_level.queue`, `workstation.substrate`, `display.calibration`, `browser.evidence`, `showcase.scout`, `proof`, `proof.research`, `proof.visual`, `proof.build` | each script reads files inside the package and prints JSON; `showcase` and `proof` write files only with `--out`, which the MCP mapping never passes; `operator.doctor` runs `status.mjs` with the same Node |
| not in build: `actuation_outside_app` | `telos.native.control` | the script is the Chrome DevTools and Windows UI Automation driver; behind other arguments it holds screenshot writes, mail send, social post and store listing actions |
| not in build: `needs_source_checkouts` | `telos.room`, `telos.workflow` | they run `python` from PATH against sibling source checkouts, and `workflow` also writes temp files and runs `node` by name; an installed app has neither checkout |
| T2 | none | no remaining tool writes outside the lane folder, spends a key, publishes or actuates |

Operator questions:

1. `telos.native.control` over MCP only prints its capability catalog today, since the mapping passes
   no arguments. The draft still leaves it out of the build, because its script is the actuation
   driver and a later telos release could pass arguments through. Admitting it at T2 is the other
   option O-8 allows.
2. The plan's acceptance row for telos names "a Chrome tool without Chrome returns
   `LANE_SETUP_REQUIRED`". The 0.4.1 MCP surface has no such tool: every tool runs from package
   fixtures, and the only Chrome or UI Automation path is `native.control`, which the draft leaves out.
   The row needs rewording in WP11.
3. `telos.workstation.substrate` describes itself as intake for local workstation repositories. From
   the packed archive it returns a fixture register (7,745 characters) and reads nothing outside the
   package. The draft keeps it at T1.

## learn 1.6.0 (15 tools)

| Tier | Tools | Why |
|---|---|---|
| T1, main | `learn_dry_run`, `learn_tutor_plan` | the main action in the plan: plan and check a study step |
| T1 | `learn_doctor`, `learn_status`, `learn_verify`, `learn_receipt`, `learn_tutor_mastery`, `learn_visualize_dry_run`, `learn_tutor_due`, `learn_tutor_studyplan`, `learn_tutor_misconceptions`, `learn_tutor_reverify`, `learn_tutor_derive_schedule`, `learn_tutor_prooflesson` | read a saved run or session in the lane folder, or a file the caller names, and return JSON |
| T2 | `learn_tutor_record` | kept from the plan draft; see question 1 |
| not in build | none | see question 2 |

Operator questions:

1. `learn_tutor_plan` and `learn_tutor_record` both write one session file under
   `<home>/lanes/learn/tutor/`. The v1 rule puts writes inside the lane's own folder at T1 (the same
   reason mneme `remember` moved to T1). By that rule `learn_tutor_record` is T1. The draft keeps the
   plan's T2 until the operator decides.
2. The plan asked for learn's crucible- and gather-backed tools to be marked not in build, because
   `LEARN_CRUCIBLE_CMD` splits on spaces. In 1.6.0 those interop calls exist only in the CLI
   (`src/cli.mjs`); none of the 15 MCP tools reaches them, and `learn_doctor` calls the telos render
   check with an empty command, so it spawns nothing. No MCP tool needed the mark.
3. `learn_dry_run` and `learn_tutor_prooflesson` read a file path the caller supplies. That is a read
   anywhere the engine user can read, the same exposure as other lanes' path inputs.

## Setup item

Every tool of both lanes needs the `node` setup item. The bundled Node meets it on a fresh install.
`FLYWHEEL_NODE=none` makes it unmet, which is how the acceptance run tests the no-Node state; a Node
the operator names that is older than 20 is reported, never replaced.
