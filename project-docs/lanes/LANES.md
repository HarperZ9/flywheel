# Lanes in the Windows app

A lane is a companion tool that Flywheel runs as its own process: gather, crucible,
index and the rest. This page lists, for each of the 17 lanes in the roster, the main
action a person installs it for, the class an installed-app check measured, and the
setup the app's lane card states. It describes the build after 1.0.4; for 1.0.4 itself
see the known-issues correction.

## Classes

- **A**: the main action returns a real result on a fresh install, with no setup.
- **B**: the main action runs after a setup step the lane card names. The check
  performed that step and ran the main action again.
- **C**: the app reads only, by design. The main action runs in the tool's own app.
- **A/B-untested** and **A/C**: the main action is class A, and a second action is
  class B but untested (it needs a provider key) or class C.
- **below bar**: the check found a gap. The row says which.
- **not in this build**: the lane is listed but does not ship.

"Approve at T2" means the tool runs only on a call you approve with the higher tier on
the approval sheet. Plugins and agent runs cannot reach a T2 tool.

## Per lane

| Lane | Main action | Measured class | Setup the card states | Outside the class or untested |
| :-- | :-- | :-- | :-- | :-- |
| gather | catalog a local document | A | none; feeds and arXiv need the network | feeds were not run; run, pilot and federation need approval at T2 |
| crucible | check a thesis against measurements | A | none | run, batch and refine need approval at T2 |
| chorus | digest a corpus into themes | A | none | none |
| articulate | score and check prose | A | none for score and check; judge, fix and polish need the claude CLI, signed in with claude login | judge, fix and polish need approval at T2 and were not run |
| index | find symbols; map a repository | below bar | Git for Windows, to read branch and history | symbols run with no setup, and map passes once Git is found; without Git, map returns an empty repository list instead of naming the Git step |
| forum | route a question to a plan | A/B-untested | real rooms need a provider key granted to the lane by name | route and plan run on the built-in echo executor; real rooms are untested |
| learn | plan and check a study step | A | none; Node ships with the app | tutor_record needs approval at T2; tools that call out to crucible or gather were not checked |
| telos | read the workstation catalog | not in this build | none | the release contents are under review, so no telos code ships |
| local-model | run a local agent task in a project | B | choose a project folder outside the Flywheel home; start a model server (Ollama with a pulled model at 127.0.0.1:11434, or a server at 127.0.0.1:8765) | the check used a stub model server, so model quality is unmeasured; writes, commands and online models stay off |
| writing | diagnose a draft | B | record a draft on the Writing screen | diagnose runs on a call you approve at T2 |
| relay | run one agent task through a local model | B | start a model server | writes, commands and online models stay off; background runs start only at T2; the state before setup was not measurable on the check machine, which runs a model server |
| plexus | plan a route between lanes | A | none | none |
| mneme | remember and recall a fact | A | none; key-backed extraction needs a provider key | extraction is untested; forget needs approval at T2 and cannot be undone |
| calibrate-pro | look up a display panel profile | C | none; calibration runs in Calibrate Pro | list-targets is not in this build |
| canon | validate context blocks | B | put blocks in the lane's blocks folder, which the card names | none |
| bulletin | read board rooms and the feed | A | the network; posting needs a registered identity | posting is untested; the card reads "Not checked yet" until you check it, because the app does not contact the board when it starts |
| accountable-surface | perceive a folder with provenance | A/C | none; actuation runs in Accountable Surface | actuate is not in this build |

Tally: 8 lanes in A, 4 in B, 1 in C, 1 in A/B-untested, 1 in A/C, 1 below bar and 1 not
in this build.

## Where every lane keeps its files

Each lane process starts in its own folder, `lanes/<lane>` under the Flywheel home, and
keeps its temporary files, caches and state there. Nothing is written into the install
folder; the check compares the install folder before and after and found no change.

## How this was measured

An installed-app check installs the Windows app, starts its engine the way the app does,
under a throwaway profile with only the Windows system folder on PATH, and calls each
lane through the same routes and approvals the app uses. It runs twice: once fresh, and
once after it installs Git, starts a stub model server, picks a project folder, places a
canon block and records a writing draft. The classes above come from its per-user run on
2026-09-26, summarized with the receipt's hash in
`evidence/installed-lanes-local-20260926.json`. Of two earlier runs of the same build,
one agrees and the other had local-model below bar in the setup leg; that difference is
not yet explained.

## What this does not prove

- The check ran on the build machine with a stripped PATH, not on a clean Windows 11
  install or VM. Host libraries, the network and the host's own model server were
  reachable.
- The all-users install was not checked in this run.
- No provider key was used, so no key-backed action is shown to work.
- The stub model server answers one fixed word; a model-lane pass shows the lane reached
  a model server and the engine's guards held, not answer quality.
- No bulletin post and no actuation ran.
- Each main tool has one fixture assertion; that is not correctness in general.
- The desktop screens were not driven; the check calls the engine routes the app calls.
