<!--
Draft of the Flywheel 1.1.0 release notes, for the release owner to review before any tag.
Open before publishing:
- Lane classes, the lane sentence and the method paragraph cite CI run 36302181098
  (project-docs/lanes/evidence/installed-lanes-ci-36302181098.json, source ba371e6b).
  Replace that summary, run id and commit with the windows-installed-acceptance.yml
  run on the release commit (O-9); tests/test_release_drafts.py reads the summary.
- The README lane sentence carries the same count (O-5).
- Installer size is from that CI build; re-measure it from the release workflow build.
- The 1.0.4 known-issues page (RELEASE-NOTES-1.0.4-known-issues.md) publishes on its
  own; the section below points to it.
Remove this comment before publishing.
-->

# Flywheel 1.1.0

The Windows app now runs each lane's main action from the lane's card, and the card
tells you the truth about it: whether the action is ready, what setup it still needs,
and when it was last checked. articulate, calibrate-pro and learn join the installer,
learn with a bundled Node runtime, so it runs with nothing else installed. forum,
local-model and writing now start inside the installed app. Every lane tool the app can
call sits under one policy, listed tool by tool in
`docs/features/lane-tool-policy.md`, and tools that write outside the lane's folder,
spend a key, publish or act on your machine run only on a call you approve.

## Why this is 1.1.0

A lane tool the policy does not list now needs an approval at T2 in every install:
the Windows app, a pip install and a source checkout. Before, a pip or source install
ran such a tool at the lane's default tier, T1 on most lanes, so a lane upgrade that
added a tool opened it with no review. If you call lane tools from a pip or source
install, a tool the policy does not name now answers with a governance denial until
you approve that call at T2. The Windows app already refused these tools and still
does, even at T2. This changes what existing pip and source setups do, so the release
takes the minor number.

## Try it

Install the Windows app, open Tools and pick a lane card. Each card shows its state,
lists the lane's tools with a form for each, and runs the one you choose after you
approve the call. A card that needs setup names the step: Git for Windows for index's
repository history, a model server for local-model and relay, a project folder for
local-model, a blocks folder for canon, a recorded draft for writing.

For the engine alone: `python -m pip install -U flywheel-verify`, then
`flywheel lanes --probe`.

## What each lane does in the app

Seventeen lanes ship in the roster. In the Windows app's installed-app check, 15 of 17
lanes reach the class the check expects for them: 8 run their main action with no setup
(A), 4 after the setup step the card names (B), 1 reads only by design (C), 1 runs with
no setup and keeps actuation in its own app (A/C), and 1 runs with no setup while its
provider-backed path is untested (A/B-untested). index is below that bar without Git,
and telos is not in this build.

Measured by an installed-app check (CI run 36302181098, commit ba371e6b) that installs
the release installer per user and then for all users on a GitHub-hosted Windows Server
runner, starts the engine the way the app does under a throwaway profile, and calls each
lane through the app's own routes and approvals, once fresh and once after setup. The
check fails when a lane leaves its expected class. Classes: **A** runs with no setup;
**B** runs after the setup step the card names; **C** reads only, by design, and the
main action runs in the tool's own app.

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

The check confirms the class each lane is expected to reach: writing is expected at B
because diagnose needs a recorded draft, and accountable-surface's actuation limit
comes from the tool policy, not from a check. "At T2" means the tool runs only on a
call you approve with the higher tier.

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
  approval at T2 for that one call. A tool the
  policy does not list needs T2 too. The engine computes the tier itself, whatever the
  caller sends. Plugins and agent runs cannot reach a T2 tool or an unlisted one, and
  agent runs also refuse state writes, open network egress and path arguments. The
  approval sheet shows the tier, the effect, whether the lane's granted keys reach
  the call and the arguments in plain form. A tool the policy does not list reads
  "not reviewed: effect unknown".
- **Lanes start inside the installed engine.** local-model and writing run as modes of
  the bundled engine instead of a `python` found on your PATH. The native screens that
  call lane commands do the same.
- **New in the installer.** articulate 0.5.0, calibrate-pro 2.0.0 as a catalog slice
  (the panel catalog without numpy), learn 1.6.0, and Node.js v24.21.0 LTS to run it.
  forum 1.14.0 ships the data files it needs to start. `FLYWHEEL_NODE` or a node.exe you
  choose in the app still overrides the bundled Node; a chosen node.exe is checked by
  hash again at every launch.
- **Lane updates.** relay 0.4.0, gather 1.9.0, mneme 0.5.1 and canon 0.4.2, each
  frozen from its release tag. None adds a tool the app can call, and each tool keeps
  its tier. In the Windows app, a pip install and a source checkout, relay keeps its
  saved sessions in `lanes/relay/sessions` and starts with write, exec, shell child
  variables and agent CLI tiers all off, and gather starts with no network, command or
  credential grant, since the app's gather tools read a local document or corpus.
  mneme's forget erases a memory with the rows derived from it and returns a receipt
  that names any residue it finds. canon's context store redacts every ingest and can
  purge records from its own command line; the engine starts canon's context server
  with purge disabled, so it can only plan one.
- **relay starts from pip and source installs again.** With relay 0.3.0 or later, the
  engine's pip and source launch for relay exited at start. It now starts relay through its own
  command line. The Windows app was not affected.
- **Each lane keeps to its own folder.** In the Windows app, a pip install and a
  source checkout, every lane process starts in `lanes/<lane>` under the Flywheel home
  and keeps its temporary files, caches and state there. On a pip or source install,
  local-model and writing run as modes of the engine, so they start in the engine's
  folder and keep only their temporary and app-data files in `lanes/<lane>`. The
  installed-app check found no change to the install folder.
- **Keys reach a lane only when you grant them.** A key saved in the app can be bound to
  one approved T2 call of a lane whose `env_allow` names it. The lane card names the key
  and says whether it is present, never its value, and the engine removes the value from
  the lane's reply.
- **Long runs survive between calls.** relay background runs and index router jobs keep
  one lane process alive between the start, status and result calls. It ends after ten
  idle minutes (up to an hour while a run it started is still active) or when the
  engine stops.
- **Error codes you can act on.** A failed lane call returns one of six fixed codes with
  a short reason slug, and the card offers one action for each: list tools again, show
  setup, check the lane or run again. A call refused at its tier says so and offers no
  action.
- **License texts ship with the engine.** The engine folder now carries the Python
  license (with OpenSSL's), the texts for code compiled into Python, and each lane's
  license. The installer's third-party notice lists every one.

## Security fixes in the lanes

- relay 0.4.0 fixes GHSA-phjr-6qrc-39mw (a session listing could read ledger files
  outside the session store) and GHSA-xxcc-grhg-v9g7 (agent CLI tiers could run a
  planted binary or project hooks, and shell children inherited provider keys). The
  engine also refuses a session id that is not a plain name before relay sees it.
- gather 1.9.0 fixes GHSA-pxvv-rg3f-4v5w (tool arguments could run commands and send
  environment secrets to a chosen host) and GHSA-r4f3-9xrf-72m5 (external tools started
  by bare name from the working folder).
- mneme 0.5.1 fixes GHSA-j2pw-g7f4-9ppp (forget could keep erased text in its reason,
  erase another user's turn, and let the receipt confirm a guess of the erased text).
- canon 0.4.2 fixes GHSA-48rq-xjfx-6j4f (the shared context store kept secrets from an
  MCP ingest, returned the start of a secret in query excerpts, and put transcript
  paths into the next prompt). The same advisory covers canon 0.2.0, which 1.0.4
  shipped; the 1.0.4 known-issues page says what to do there.
- On a pip or npm install, a lane older than its pinned release no longer starts, so
  these fixes cannot be skipped by an older package. `flywheel install` and the
  install route ask for the pinned version.

## Security changes in the engine

- A path argument that names a Windows device path (`\\?\`, `\??\`) or a network
  share is refused before the lane starts, and so is such a value inside gather.run's
  inline config. A folder is compared by identity, so no spelling of the Flywheel home
  or the run root reaches a lane's read. The Node and local-model folder settings refuse
  network paths and mapped network drives too.
- A T2 call keeps the keys granted to its lane only when its tool spends a model call.
  A key you bind to the call still joins it. Plugins and the forum and relay screens run
  without granted keys, and those screens refuse a tool above T1.
- `learn_tutor_plan` is refused for a session that already has a file, so a T1 plan
  cannot reset what an approved `learn_tutor_record` wrote. An id may not be a Windows
  device name such as `CON` or `NUL`.
- The engine refuses context capture and preflight through a flywheel-canon older than
  its pin.
- Installing a lane through the engine's install route now takes an approval.

## Breaking changes

- A lane tool the policy does not list needs an approval at T2 on pip and source
  installs, as it already did in the Windows app.
- On pip and source installs, a call that carries T1 can now run the tools the policy
  lists at T1 on relay, local-model and accountable-surface, including
  `local_agent_run` and `perceive`. 1.0.4 required T2 for every tool on those lanes.
  Their write, exec and actuation paths stay at T2 or off.
- A pip or npm lane older than its pin reports `installed_version_below_pin` and does
  not start. Run `flywheel install` for that lane to get the pinned version.
- A source checkout now starts each lane in `lanes/<lane>` with the same forced grants
  as a pip install. An `env_allow` of `GATHER_ALLOW_NETWORK` or `RELAY_ALLOW_EXEC` no
  longer reaches the lane there either.
- A T2 call to a tool that does not spend a model call, such as `mneme.forget` or
  `gather.run`, no longer receives keys granted with `env_allow`. Bind the key to the
  call instead.
- `/api/forum/run-room` answers `CAPABILITY_NOT_ADMITTED` on pip and source installs,
  since `forum.run.room` is T2. The Windows app already refused it.
- `POST /api/lanes/install` needs a `lane.install` approval; a bearer token alone
  installs nothing.
- relay takes write and exec grants only from how it is started; tool arguments can
  only narrow them. From 0.4.0 its shell children see an allowlist of variables and
  its saved sessions default to a per-user folder. The app starts relay with write and
  exec off and its sessions in the lane folder.
- gather 1.9.0 needs launch grants for network sources, commands and credentials in
  `gather.run` and `gather.pilot`. Flywheel grants none, so such a run answers
  `GRANT_REQUIRED`. The feeds screen uses gather's command line and is unchanged.
- mneme 0.5.x forget takes two calls: the first returns a plan and deletes nothing,
  the second carries the plan's hash and erases. Each call needs your approval at T2.
  A writable open migrates the lane's memory database to schema 5. The 0.5.1 receipt
  drops `plan_sha256` and adds finding codes.
- canon 0.4.2 raises the context store to identity version 2 on its first capture or
  purge; canon 0.3.0 and older refuse that store. An event stored raw before 0.4.2 and
  sent again with a secret-shaped value is refused as a collision.
- writing's `diagnose` now needs an approval at T2, because it works on the shared
  draft store outside the lane's folder.
- Plugins and agent runs refuse a lane tool the policy does not list.

## Corrections to the 1.0.4 notes

The 1.0.4 notes described the Windows app's lanes more strongly than the installed app
delivered: one lane ran its main action, nine answered only status and doctor, forum,
local-model and writing did not start, and a key granted with `env_allow` did not reach
a bundled lane. The engine from pip was not affected. The 1.0.4 known-issues page lists
each statement, what we measured and what to do on 1.0.4. This release is the fix.

## Installer size

The installer is about 23.7 MB larger, mostly the bundled Node runtime: 80,081,007 bytes
in CI run 36302181098 against 56,355,754 bytes for the published 1.0.4 installer.

## Limits

- index maps a repository's history only when Git for Windows is installed. Without
  Git, map lists the repository with its branch and head as unknown and a
  FileNotFoundError, instead of naming the Git step.
- telos is not in this build while its release contents are reviewed.
- The Windows app bundles index 2.13.0 plus one later commit (a bounded context-envelope
  output), which no index release contains; a pip install gets PyPI 2.13.0.
- Lanes still run as your user with no filesystem sandbox. The policy governs what a
  caller can ask a lane to do, not what a lane's own code can reach.
- forum real rooms, mneme extraction and articulate's judge, fix and polish need a
  provider key or a signed-in claude CLI and were not exercised.
- The limits listed for 1.0.4 on the verifier still hold.

## What the lane check does not prove

It ran on a GitHub-hosted Windows Server runner with only the Windows system folder on
PATH and an administrator account, not on a consumer Windows 11 machine, which remains
untested; the network was reachable and no host model server ran. It used a stub model server, so it shows a model lane
reached a model and the engine's guards held, not answer quality. It used no provider
key, posted nothing and actuated nothing. Each main tool has one fixture assertion. The
desktop screens were not driven; the check calls the routes the app calls.

## Upgrade

- Engine: `python -m pip install -U flywheel-verify`
- Desktop app: the Windows installer attached below. Verify it against the checksums
  attached to the release.
- If you granted keys to lanes with `env_allow` in `lanes.json`, they now reach the
  bundled lanes too, on a call you approve at T2.
- If a script calls a lane tool the policy does not list on a pip or source install,
  send that call with an approval at T2, or ask for the tool to be reviewed into the
  policy.
