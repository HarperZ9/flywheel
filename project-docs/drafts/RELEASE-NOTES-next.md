<!-- Draft 1.1.0 notes, reviewed before any tag. The lane classes, lane sentence, README
count, method paragraph and installer size cite CI run 36302181098, which predates the
gather 1.9.1, relay 0.5.0, forum 1.15.1, crucible 1.3.0 and index 2.14.0 pins: replace them
from the release commit's windows-installed-acceptance.yml run. The 1.0.4 known-issues page
publishes on its own. Trace manual checks X4, X6, X7, X8 and X18 were not run. -->

# Flywheel 1.1.0

The Windows app now runs each lane's main action from the lane's card, and the card
tells you the truth about it: whether the action is ready, what setup it still needs,
and when it was last checked. articulate, calibrate-pro and learn join the installer,
learn with a bundled Node runtime, so it runs with nothing else installed. forum,
local-model and writing now start inside the installed app. Every lane tool the app can
call sits under one policy, listed tool by tool in `docs/features/lane-tool-policy.md`,
and tools that write outside the lane's folder, spend a key, publish or act on your
machine run only on a call you approve. The engine also takes custody of your agent
traces (`docs/TRACE-OWNERSHIP.md`): `flywheel traces` lists every store that holds them,
encrypts gateway traces, captured turns and imports at rest where an OS key store is
available, and exports or deletes what Flywheel holds.

## Why this is 1.1.0

A lane tool the policy does not list now needs an approval at T2 in every install: the
Windows app, a pip install and a source checkout. Before, a pip or source install ran
such a tool at the lane's default tier, T1 on most lanes, so a lane upgrade that added a
tool opened it with no review. Now such a call answers with a governance denial until
you approve it at T2. The Windows app refused these tools before and still does, even at
T2. Existing pip and source setups change, so the release takes the minor number.

## Try it

Install the Windows app, open Tools and pick a lane card. Each card shows its state and
runs the tool you choose after you approve the call; a card that needs setup names the
step. For the engine alone: `python -m pip install -U flywheel-verify`, then
`flywheel lanes --probe`.

## What each lane does in the app

In the Windows app's installed-app check, 15 of 17 lanes reach the class the check
expects for them: 8 run their main action with no setup (A), 4 after the setup step the
card names (B), 1 reads only by design (C), 1 runs with no setup and keeps actuation in
its own app (A/C), and 1 runs with no setup while its provider-backed path is untested
(A/B-untested). index is below that bar without Git, and telos is not in this build.

Measured by an installed-app check (CI run 36302181098, commit ba371e6b) that installs
the release installer per user and then for all users on a GitHub-hosted Windows Server
runner, starts the engine the way the app does under a throwaway profile, and calls each
lane through the app's own routes and approvals, once fresh and once after setup. The
check fails when a lane leaves its expected class. For a class C lane, the main action
runs in the tool's own app.

| Lane | Main action | Class the check confirmed | Note |
| :-- | :-- | :-- | :-- |
| gather | catalog a local document | A | feeds need the network |
| crucible | check a thesis against measurements | A | |
| chorus | digest a corpus into themes | A | |
| articulate | score and check prose | A | judge, fix and polish need a signed-in claude CLI and your approval at T2 |
| index | find symbols; map a repository | below bar | symbols run with no setup and map runs with Git; without Git, map lists the repository with its branch and head as unknown and a FileNotFoundError, instead of naming the Git step |
| forum | route a question to a plan | A/B-untested | real rooms need a provider key and are untested |
| learn | plan and check a study step | A | Node ships with the app |
| telos | read the workstation catalog | not in this build | its release contents are under review |
| local-model | run a local agent task in a project | B | needs a project folder and a model server |
| writing | diagnose a draft | B | needs a recorded draft; diagnose runs at T2 |
| relay | run one agent task through a local model | B | needs a model server |
| plexus | plan a route between lanes | A | |
| mneme | remember and recall a fact | A | key-backed extraction is untested |
| calibrate-pro | look up a display panel profile | C | calibration runs in Calibrate Pro |
| canon | validate context blocks | B | needs blocks in the lane's folder |
| bulletin | read board rooms and the feed | A | needs the network; posting is untested |
| accountable-surface | perceive a folder with provenance | A/C | actuation runs in Accountable Surface |

The check confirms the class each lane is expected to reach; accountable-surface's
actuation limit comes from the tool policy, not from a check. "At T2" means the tool
runs only on a call you approve with the higher tier.

## What changed

- **Lane cards run the main action.** The Tools view lists each lane's tools from the
  lane itself, builds a form from each tool's input schema, and shows the result with
  the raw reply folded underneath. Tools that are not in this build appear disabled
  with the reason.
- **True lane states.** A card reads ready, limited, needs setup, reads only, cannot
  start, unreachable, not checked or not in build, from a real check, never from a
  health reply alone. When the app starts the engine, the engine checks each local lane
  four at a time. bulletin is checked only when you ask, so the app does not contact the
  board at start. A card from an earlier session reads "Last checked" until a new check
  replaces it, and a call that fails to start the lane updates the card.
- **One tool policy.** Each lane's tools carry a tier. Reads, network reads, writes
  inside the lane's own folder and calls to your local model server run on an approved
  call; writes outside it, key spend, publishing, commands and device control need an
  approval at T2 for that one call. A tool the policy does not list needs T2 too. The
  engine computes the tier itself, whatever the caller sends. Plugins and agent runs
  cannot reach a T2 tool or an unlisted one, and agent runs also refuse state writes,
  open network egress and path arguments. The approval sheet shows the tier, the effect,
  whether the lane's granted keys reach the call and the arguments in plain form. A tool
  the policy does not list reads "not reviewed: effect unknown".
- **New in the installer.** articulate 0.5.0, calibrate-pro 2.0.0 as a catalog slice
  (the panel catalog without numpy), learn 1.6.0, and Node.js v24.21.0 LTS to run it.
  forum 1.15.1 ships the data files it needs to start. `FLYWHEEL_NODE` or a node.exe you
  choose in the app still overrides the bundled Node; a chosen node.exe is checked by
  hash again at every launch. The installer is about 23.7 MB larger, mostly the Node
  runtime: 80,081,007 bytes in CI run 36302181098 against 56,355,754 bytes for 1.0.4.
- **License texts ship with the engine.** The engine folder now carries the Python
  license (with OpenSSL's), the texts for code compiled into Python, and each lane's
  license. The installer's third-party notice lists every one.
- **Lane updates.** relay 0.5.0, gather 1.9.1, forum 1.15.1, crucible 1.3.0, index
  2.14.0, mneme 0.5.1 and canon 0.4.2, each frozen from its release tag. Each tool keeps
  its tier. Two releases add a T1 read with its path arguments kept out of the home:
  crucible 1.3.0 `crucible.recheck_template`, which returns a replay template, and index
  2.14.0 `index.route`, which builds a context envelope for the repositories you name
  under a root. The Windows app and a pip install now get the same index release. In the
  Windows app, a pip install and a source checkout, relay keeps its saved sessions in
  `lanes/relay/sessions` and starts with write, exec, shell child variables and agent
  CLI tiers all off, gather starts with no network, command or credential grant and
  forum with its command variables empty. mneme's forget erases a memory with the rows
  derived from it and returns a receipt that names any residue it finds. canon's context
  store redacts every ingest and can purge records from its own command line; the engine
  starts canon's context server with purge disabled, so it can only plan one.
- **Gate decisions stay with your approval.** forum 1.15 runs `gate_approve`, `gate_edit`
  and `gate_reject` only when started with `--allow-gate-decisions`. The engine adds it
  only to the launch of one call you approve at T2 for one of them, so your approval
  decides each gate. The forum card lists what an ordinary launch lists, which leaves
  the three out. The app has no control for them in this release; a lane call to the
  engine at T2 runs them.
- **relay starts from pip and source installs again.** With relay 0.3.0 or later, the
  engine's pip and source launch for relay exited at start. It now starts relay through its own
  command line. The Windows app was not affected.
- **Lanes start inside the installed engine and keep to their own folders.** In the
  Windows app, local-model and writing run as modes of the bundled engine instead of a
  `python` found on your PATH, and so do the native screens that call lane commands. In
  the app, a pip install and a source checkout, every lane process starts in
  `lanes/<lane>` under the Flywheel home and keeps its temporary files, caches and state
  there. On a pip or source install, local-model and writing run as modes of the engine,
  so they start in the engine's folder and keep only their temporary and app-data files
  in `lanes/<lane>`. The installed-app check found no change to the install folder.
- **Keys reach a lane only when you grant them.** A key saved in the app can be bound to
  one approved T2 call of a lane whose `env_allow` names it. The lane card names the key
  and says whether it is present, never its value, and the engine removes the value from
  the lane's reply.
- **Long runs survive between calls.** relay background runs and index router jobs keep
  one lane process alive from their start call to their result. It ends after ten idle
  minutes (up to an hour while a run it started is active) or when the engine stops.
- **Error codes you can act on.** A failed lane call returns one of six fixed codes with
  a short reason slug, and the card offers one action for each: list tools again, show
  setup, check the lane or run again. A call refused at its tier says so and offers no
  action. A lane that refuses a network or device path reads `argument_refused`, and a
  lane whose launch lacks the grant a call needs reads `lane_grant_required`.

## Your traces

These commands come with the engine from pip; the Windows app has no traces screen yet.

- `flywheel traces status` lists every store that holds data derived from your traces:
  where it is, how it is protected and kept, and whether it can be exported and deleted.
- Gateway traces, captured turns, frozen pages, imported transcripts and bench tasks are
  encrypted at rest where an OS key store is available, each under its own key: DPAPI on
  Windows; on macOS, and on Linux with `secret-tool`, AES-256-GCM with the `encryption`
  extra, a path with no automated test yet. Otherwise status says plaintext.
- `flywheel traces delete` plans its closure, destroys keys before files, leaves a
  tombstone and names the copies it cannot reach: the model provider's, the client's own
  transcript, backups and earlier exports. `export` writes a verifiable copy (never to a
  network share), `import` copies Claude Code and Codex transcripts into custody, and
  retention deletes only under a rule you adopt; the default keeps everything.
- The capture hooks send salted commitments by default, over a channel signed per request
  and bound to the engine's loopback address, never the raw gateway token. A turn's text
  is kept only after you turn content capture on. Lane processes run with capture off.
- Custody events land in a hash-chained, metadata-only ledger and the Windows event log.
  The desktop app keeps a conversation it cannot read, names it and asks before deletes.

## Security fixes in the lanes

- relay 0.5.0 fixes GHSA-82fg-qprm-q5r7 (a PATH entry reaching a child's folder could
  start a planted program, git's children included) and, from 0.4.0, GHSA-phjr-6qrc-39mw
  (a session listing could read ledger files outside the store) and GHSA-xxcc-grhg-v9g7
  (CLI tiers could run a planted binary or project hooks, and shell children got
  provider keys). The engine also refuses a session id that is not a plain name.
- gather 1.9.1 fixes GHSA-j6j7-39vh-qrp4 (a path argument over MCP could make Windows
  sign in to a share a model named) and GHSA-r38f-cr69-jpp8 (a PATH entry reaching the
  working folder could start a planted program) and, from 1.9.0, GHSA-pxvv-rg3f-4v5w
  (tool arguments could run commands and send secrets to a chosen host) and
  GHSA-r4f3-9xrf-72m5 (tools started by bare name from the working folder).
- forum 1.15.1 fixes GHSA-36gv-h885-fmjf (approvals not tied to a raised gate, executors
  given the working folder and the whole environment, an open local daemon) and
  GHSA-h6qh-49hv-4xcg (1.15.0's folder guard missed an alias, a repointed link and a
  quoted PATH entry). Every advisory above except GHSA-h6qh-49hv-4xcg also covers the
  gather 1.8.2, relay 0.2.5 or forum 1.14.0 that 1.0.4 pins. The 1.0.4 known-issues
  page says where they run.
- crucible 1.3.0 fixes GHSA-49qx-cj4f-wfqv (a measurement file could widen the tolerance
  that decides MATCH, and status and doctor answered MATCH without measuring anything).
  It also covers crucible 1.2.0, which 1.0.4 pins (see the 1.0.4 known-issues page).
- mneme 0.5.1 fixes GHSA-j2pw-g7f4-9ppp (forget could keep erased text in its reason,
  erase another user's turn, and let the receipt confirm a guess of the erased text).
- canon 0.4.2 fixes GHSA-48rq-xjfx-6j4f (the shared context store kept secrets from an
  MCP ingest, returned the start of a secret in query excerpts, and put transcript
  paths into the next prompt). The same advisory covers canon 0.2.0, which 1.0.4
  shipped; the 1.0.4 known-issues page says what to do there.

## Security changes in the engine

- A path argument that names a Windows device path (`\\?\`, `\??\`), a reserved device
  name such as `CON.md` or a network share is refused before the lane starts, and so is a
  device path or share inside gather.run's inline config. A folder is compared by
  identity, so no spelling of the Flywheel home or the run root reaches a lane's read.
  The Node and local-model folder settings refuse network paths and mapped network
  drives too.
- A T2 call keeps the keys granted to its lane only when its tool spends a model call.
  A key you bind to the call still joins it. Plugins and the forum and relay screens run
  without granted keys, and those screens refuse a tool above T1.
- `learn_tutor_plan` is refused for a session that already has a file, so a T1 plan
  cannot reset what an approved `learn_tutor_record` wrote. An id may not be a Windows
  device name such as `CON` or `NUL`.
- Context capture and preflight refuse a flywheel-canon older than its pin.

## Breaking changes

- A lane tool the policy does not list needs an approval at T2 on pip and source
  installs, as it already did in the Windows app; plugins and agent runs refuse it.
- On pip and source installs, a call that carries T1 can now run the tools the policy
  lists at T1 on relay, local-model and accountable-surface, including
  `local_agent_run` and `perceive`. 1.0.4 required T2 for every tool on those lanes.
  Their write, exec and actuation paths stay at T2 or off.
- A pip or npm lane older than its pin reports `installed_version_below_pin` and does
  not start, so an older package cannot skip the lane security fixes above. Run
  `flywheel install` for that lane; it and the install route ask for the pinned version.
- A source checkout now starts each lane in `lanes/<lane>` with the same forced grants
  as a pip install. An `env_allow` of `GATHER_ALLOW_NETWORK` or `RELAY_ALLOW_EXEC` no
  longer reaches the lane there either.
- A T2 call to a tool that spends no model call, such as `mneme.forget` or `gather.run`,
  no longer receives keys granted with `env_allow`. Bind the key to the call instead.
- `/api/forum/run-room` answers `CAPABILITY_NOT_ADMITTED` on pip and source installs,
  since `forum.run.room` is T2. The Windows app already refused it.
- `POST /api/lanes/install` needs a `lane.install` approval; a bearer token alone
  installs nothing.
- relay takes write and exec grants only from how it is started; tool arguments can only
  narrow them. From 0.4.0 its shell children see an allowlist of variables and its saved
  sessions default to a per-user folder, which Flywheel sets to the lane folder.
- gather 1.9.0 and later need launch grants for network sources, commands and
  credentials in `gather.run` and `gather.pilot`. Flywheel grants none, so such a run
  answers `lane_grant_required`. gather 1.9.1 also refuses a network or device path,
  including a reserved name such as `con.md`. The feeds screen uses gather's command
  line and is unchanged.
- forum's `gate_approve`, `gate_edit` and `gate_reject` run only on a call you approve at
  T2, which starts forum with its decision grant for that call.
- crucible 1.3.0's status and doctor answer `OK` (1.2.0: `MATCH`). Replay packs need their
  assessment binding, and a measurement off its claim's sealed tolerance is UNVERIFIABLE.
- mneme 0.5.x forget takes two calls: the first returns a plan and deletes nothing,
  the second carries the plan's hash and erases. Each call needs your approval at T2.
  A writable open migrates the lane's memory database to schema 5. The 0.5.1 receipt
  drops `plan_sha256` and adds finding codes.
- canon 0.4.2 raises the context store to identity version 2 on its first capture or
  purge; canon 0.3.0 and older refuse that store. An event stored raw before 0.4.2 and
  sent again with a secret-shaped value is refused as a collision.
- writing's `diagnose` now needs an approval at T2, because it works on the shared
  draft store outside the lane's folder.
- The capture hook mount is now `"<python>" -P -E -m harness.capture_hooks`, and
  `flywheel traces doctor` fails the old line. With `-E`, a mount that found Flywheel
  through `PYTHONPATH` stops working; install Flywheel for that Python instead.

## Corrections to the 1.0.3 and 1.0.4 notes

The 1.0.4 notes described the Windows app's lanes more strongly than the installed app
delivered: one lane ran its main action, nine answered only status and doctor, forum,
local-model and writing did not start, and a key granted with `env_allow` did not reach
a bundled lane. The engine from pip was not affected. The 1.0.4 known-issues page lists
each statement, what we measured and what to do on 1.0.4. This release is the fix.
The 1.0.3 and 1.0.4 notes also overstated where your data goes. Your keys are stored
only on your machine and sent only to their own provider, and Flywheel's records stay
on your machine; the content of each request goes to the hosted provider you route it to.

## Limits

- index maps a repository's history only with Git for Windows; see its row in the table.
- telos is not in this build while its release contents are reviewed.
- Lanes still run as your user with no filesystem sandbox. The policy governs what a
  caller can ask a lane to do, not what a lane's own code can reach.
- forum real rooms, mneme extraction and articulate's judge, fix and polish need a
  provider key or a signed-in claude CLI and were not exercised.
- The limits listed for 1.0.4 on the verifier still hold.
- Custody presence defaults to `none`: any process running as you, a lane's own code
  included, can read the gateway token and confirm a custody operation. `flywheel traces
  delete` does not reach lane stores, such as mneme's.
- Desktop chat history stays plaintext. Windows Hello presence and Codex capture were not
  exercised on real hardware or a real Codex install.
- The lane check ran on a GitHub-hosted Windows Server runner with only the Windows
  system folder on PATH, an administrator account, the network reachable and no host
  model server; a consumer Windows 11 machine and offline use remain untested. Its stub
  model server shows a model lane reached a model and the engine's guards held, not
  answer quality. It used no provider key, posted nothing and actuated nothing, and ran
  one fixture assertion per main tool through the app's routes, without driving screens.

## Upgrade

- Engine: `python -m pip install -U flywheel-verify`
- Desktop app: the Windows installer attached below. Verify it with the release checksums.
- If you granted keys to lanes with `env_allow` in `lanes.json`, they now reach the
  bundled lanes too, on a call you approve at T2.
- If a script calls a lane tool the policy does not list on a pip or source install,
  approve that call at T2, or ask for the tool to be reviewed into the policy.
- If you mounted the capture hooks, paste the lines from `flywheel traces hooks
  print-mount` again. `flywheel traces encrypt --legacy` encrypts older traces.
