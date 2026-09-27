<!--
Draft of the Flywheel 1.1.0 release notes, for the release owner to review before any tag.
Open before publishing:
- Lane classes come from the per-user installed-app check on the build machine
  (project-docs/lanes/evidence/installed-lanes-local-20260926.json, source commit
  5940abfc). That build predates the relay 0.4.0, gather 1.9.0, mneme 0.5.0 and
  canon 0.4.1 pins and the unlisted-tool change. Replace the table and the lane
  sentence with the receipt from the pre-tag windows-installed-acceptance.yml run on
  the 1.1.0 candidate commit (O-9), both install modes, before publishing.
- The README sentence "About fifteen composable lanes ship in the roster, ten of
  them bundled natively from source." stays until that receipt exists. The sentence
  this draft carries is the one the current receipt supports (O-5).
- Installer size is from a local build before the late pins, not the release workflow.
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
call sits under one reviewed policy, and tools that write outside the lane's folder,
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

Seventeen lanes ship in the roster. In the Windows app, 15 run their main action at
the class the app states: 8 with no setup (A), 4 after the setup step the card names
(B), 1 reads only by design (C), 1 runs with no setup and keeps actuation in its own
app (A/C), and 1 runs with no setup while its provider-backed path is untested
(A/B-untested). index is below that bar without Git, and telos is not in this build.

Measured by an installed-app check that installs the app per user, starts its engine
the way the app does under a throwaway profile, and calls each lane through the app's
own routes and approvals, once fresh and once after setup. Classes: **A** runs with no
setup; **B** runs after the setup step the card names; **C** reads only, by design, and
the main action runs in the tool's own app.

| Lane | Main action | Measured class | Note |
| :-- | :-- | :-- | :-- |
| gather | catalog a local document | A | feeds need the network |
| crucible | check a thesis against measurements | A | |
| chorus | digest a corpus into themes | A | |
| articulate | score and check prose | A | judge, fix and polish need a signed-in claude CLI and your approval at T2 |
| index | find symbols; map a repository | below bar | symbols run with no setup and map runs with Git; without Git, map returns an empty repository list instead of naming the Git step |
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

"At T2" means the tool runs only on a call you approve with the higher tier.

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
- **One tool policy.** Each lane's tools carry a tier. Reads and writes inside the
  lane's own folder run on an approved call; writes outside it, key spend, publishing,
  commands and device control need an approval at T2 for that one call. A tool the
  policy does not list needs T2 too. The engine computes the tier itself, whatever the
  caller sends. Plugins and agent runs cannot reach a T2 tool or an unlisted one, and
  agent runs also refuse state writes, open network egress and path arguments. The
  approval sheet shows the tier, the effect and the arguments in plain form.
- **Lanes start inside the installed engine.** local-model and writing run as modes of
  the bundled engine instead of a `python` found on your PATH. The native screens that
  call lane commands do the same.
- **New in the installer.** articulate 0.5.0, calibrate-pro 2.0.0 as a catalog slice
  (the panel catalog without numpy), learn 1.6.0, and Node.js v24.21.0 LTS to run it.
  forum 1.14.0 ships the data files it needs to start. `FLYWHEEL_NODE` or a node.exe you
  choose in the app still overrides the bundled Node; a chosen node.exe is checked by
  hash again at every launch.
- **Lane updates.** relay 0.4.0, gather 1.9.0, mneme 0.5.0 and canon 0.4.1, each
  frozen from its release tag. None adds a tool the app can call, and each tool keeps
  its tier. relay keeps its saved sessions in `lanes/relay/sessions` and starts with
  write, exec, shell child variables and agent CLI tiers all off. gather starts with
  no network, command or credential grant, since the app's gather tools read a local
  document or corpus. mneme's forget erases a memory with everything derived from it
  and returns a receipt. canon's context store can purge records from its own command
  line; the engine never starts canon's context server with purge applied.
- **relay starts from pip and source installs again.** With relay 0.3.0 or later, the
  engine's pip and source launch for relay exited at start. It now starts relay through its own
  command line. The Windows app was not affected.
- **Each lane keeps to its own folder.** Every lane process starts in `lanes/<lane>`
  under the Flywheel home and keeps its temporary files, caches and state there. The
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
  setup, check the lane or run again.
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

## Breaking changes

- A lane tool the policy does not list needs an approval at T2 on pip and source
  installs, as it already did in the Windows app.
- relay takes write and exec grants only from how it is started; tool arguments can
  only narrow them. From 0.4.0 its shell children see an allowlist of variables and
  its saved sessions default to a per-user folder. The app starts relay with write and
  exec off and its sessions in the lane folder.
- gather 1.9.0 needs launch grants for network sources, commands and credentials in
  `gather.run` and `gather.pilot`. Flywheel grants none, so such a run answers
  `GRANT_REQUIRED`. The feeds screen uses gather's command line and is unchanged.
- mneme 0.5.0 forget takes two calls: the first returns a plan and deletes nothing,
  the second carries the plan's hash and erases. Each call needs your approval at T2.
  A writable open migrates the lane's memory database to schema 5.
- canon 0.4.x raises the context store to identity version 2 on its first capture or
  purge; canon 0.3.0 and older refuse that store.
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

The installer grows by about 23.4 MB, mostly the bundled Node runtime: 79,771,311 bytes
for a local build of this release before the lane updates against 56,355,754 bytes for
the 1.0.4 candidate. The installed engine folder is about 135 MB, of which the Node lane
folder is about 94 MB.

## Limits

- index maps a repository's history only when Git for Windows is installed, and without
  Git its map reports no repositories instead of naming the Git step.
- telos is not in this build while its release contents are reviewed.
- Lanes still run as your user with no filesystem sandbox. The policy governs what a
  caller can ask a lane to do, not what a lane's own code can reach.
- forum real rooms, mneme extraction and articulate's judge, fix and polish need a
  provider key or a signed-in claude CLI and were not exercised.
- The limits listed for 1.0.4 on the verifier still hold.

## What the lane check does not prove

It ran on a build machine with only the Windows system folder on PATH, not on a
consumer Windows 11 machine, which remains untested; host libraries, the network and a
host model server were reachable. It used a stub model server, so it shows a model lane
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
