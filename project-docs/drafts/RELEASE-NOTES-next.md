<!--
Draft of the next release notes, for the release owner to review before any tag.
Open before publishing:
- The version is not chosen yet; it goes with the decision on unlisted lane tools
  in pip and source installs, which this draft leaves unchanged.
- Lane classes come from a per-user installed-app check on the build machine
  (project-docs/lanes/evidence/installed-lanes-local-20260926.json). Replace them
  with the receipt from the pre-tag installed-acceptance workflow, both install
  modes, on the release candidate commit.
- The README sentence "About fifteen composable lanes ship in the roster, ten of
  them bundled natively from source." stays until the public wording is chosen.
  A sentence the receipt supports: "Seventeen lanes ship in the roster. In the
  Windows app, 15 run their main action at the class the app states, one (index)
  is below that bar without Git, and one (telos) is not in this build."
- Installer size is from local builds, not the release workflow.
Remove this comment before publishing.
-->

# Flywheel (next release)

The Windows app now runs each lane's main action from the lane's card, and the card
tells you the truth about it: whether the action is ready, what setup it still needs,
and when it was last checked. articulate, calibrate-pro and learn join the installer,
learn with a bundled Node runtime, so it runs with nothing else installed. forum,
local-model and writing now start inside the installed app. Every lane tool the app can
call sits under one reviewed policy, and tools that write outside the lane's folder,
spend a key, publish or act on your machine run only on a call you approve.

## Try it

Install the Windows app, open Tools and pick a lane card. Each card shows its state,
lists the lane's tools with a form for each, and runs the one you choose after you
approve the call. A card that needs setup names the step: Git for Windows for index's
repository history, a model server for local-model and relay, a project folder for
local-model, a blocks folder for canon, a recorded draft for writing.

For the engine alone: `python -m pip install -U flywheel-verify`, then
`flywheel lanes --probe`.

## What each lane does in the app

Measured by an installed-app check that installs the app, starts its engine the way the
app does under a throwaway profile, and calls each lane through the app's own routes
and approvals, once fresh and once after setup. Classes: **A** runs with no setup;
**B** runs after the setup step the card names; **C** reads only, by design, and the
main action runs in the tool's own app.

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
  health reply alone. When the app starts the engine, the engine checks each local lane four at a
  time. bulletin is checked only when you ask, so the app does not contact the board at
  start. A card from an earlier session reads "Last checked" until a new check replaces
  it, and a call that fails to start the lane updates the card.
- **One tool policy.** Each lane's tools carry a tier. Reads and writes inside the
  lane's own folder run on an approved call; writes outside it, key spend, publishing,
  commands and device control need an approval at T2 for that one call. The engine
  computes the tier itself, whatever the caller sends. Plugins and agent runs cannot
  reach a T2 tool, and agent runs also refuse state writes, open network egress and
  path arguments. The approval sheet shows the tier, the effect and the arguments in
  plain form.
- **Lanes start inside the installed engine.** local-model and writing run as modes of
  the bundled engine instead of a `python` found on your PATH. The native screens that
  call lane commands do the same.
- **New in the installer.** articulate 0.5.0, calibrate-pro 2.0.0 as a catalog slice
  (the panel catalog without numpy), learn 1.6.0, and Node.js v24.21.0 LTS to run it.
  forum 1.14.0 ships the data files it needs to start. `FLYWHEEL_NODE` or a node.exe you
  choose in the app still overrides the bundled Node; a chosen node.exe is checked by
  hash again at every launch.
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

## Breaking changes

- relay 0.3.0 takes write and exec grants only from how it is started; tool arguments
  can only narrow them. The app starts relay with both off.
- writing's `diagnose` now needs an approval at T2, because it works on the shared
  draft store outside the lane's folder.
- Plugins and agent runs refuse a lane tool the policy does not list.

## Installer size

The installer grows by about 23.4 MB, mostly the bundled Node runtime: 79,771,311 bytes
for a local build of this release against 56,355,754 bytes for the 1.0.4 candidate. The
installed engine folder is about 135 MB, of which the Node lane folder is about 94 MB.

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

It ran on a build machine with only the Windows system folder on PATH, not on a clean
Windows 11 install; host libraries, the network and a host model server were reachable.
It used a stub model server, so it shows a model lane reached a model and the engine's
guards held, not answer quality. It used no provider key, posted nothing and actuated
nothing. Each main tool has one fixture assertion. The desktop screens were not driven;
the check calls the routes the app calls.

## Upgrade

- Engine: `python -m pip install -U flywheel-verify`
- Desktop app: the Windows installer attached below. Verify it against the checksums
  attached to the release.
- If you granted keys to lanes with `env_allow` in `lanes.json`, they now reach the
  bundled lanes too, on a call you approve at T2.
