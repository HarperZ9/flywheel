# Changelog

## 0.4.0, 2026-10-03

- New `plexus pick "REQUEST"` picks a tool for a plain-language request from what each manifest emits and consumes, with a probability for every tool, and abstains when no tool matches or the top probability is under `--threshold`. On a 51-request held-out set it picked the right tool 57% of the time, abstained on 10%, and abstained requests carried 2.7 times the error of picked ones. Details and the bar set before the run: `docs/PICK.md`.
- The Claude plugin folder now carries the server code at `client-plugin/server/src/plexus/`, so an install of the folder alone starts. `python scripts/build_client_package.py --sync-vendored` rewrites that copy from `src/`, and a test fails when it drifts. The launcher no longer looks outside the plugin folder; a missing copy prints a one-line message and exits with status 1. A test keeps every code and text file under 256 KiB, images under 2 MB, and the folder at 512 files or fewer.
- The skill and the MCP tool descriptions say "tool" where they said "organ".
- The Claude plugin manifest adds the plugin directory listing fields: display name, keywords, homepage, repository, documentation, support, privacy and terms links, and a 1024 px icon. Plexus takes no launch settings, so the manifest declares no `userConfig`. Portable and Codex manifests are unchanged.
- The client README adds a data and network table derived from the code: Plexus reads built-in and caller-selected manifests, stores nothing, makes no network call and sends no telemetry. Stale binding instructions are removed.
- The client README and PRIVACY.md add a "What this plugin runs and handles" section covering hooks, the exact launch command, network, files and environment variables. A test fails if the served package starts importing a network or process module or reading the environment.
- The environment disclosure now names the six variables Python's standard library reads at startup (`COLUMNS` and `LINES` from `argparse`; `LANGUAGE`, `LC_ALL`, `LC_MESSAGES` and `LANG` from `gettext`), separate from Plexus's own code, which reads none. A test traces the packaged server through every tool and fails on any undisclosed read.

## 0.3.0 - 2026-10-01

- Adds portable, Claude and Codex client manifests, a scoped skill, privacy guidance and troubleshooting.
- Adds deterministic source plugin ZIPs and self-contained Windows x64 ZIP/MCPB candidates with runtime licenses, checksums and dependency provenance. Source ZIPs still require Python.
- Keeps discovery, wiring, plans and routes declarative. Native fixtures verify discovery, forward routing, reverse-route refusal and plan ordering. These checks do not prove installation, runtime interoperability or successful data transfer. Optional Flywheel probe helpers are outside the native client profile.
- Adds clean, tag-bound release packaging for .0 versions. Linked inputs, untracked release payloads, state files and credential file types are refused. The release workflow attaches checked client packages alongside the product release.
- Real Windows stdio checks cover identity, source/version parity, discovery and permission refusals without a model account. Installed-client compatibility, clean-OS compatibility, signing and marketplace admission remain open gates. No publisher backend, model, network listener or service is installed.

## 0.2.2 - 2026-09-22

- Adds an OIDC trusted-publishing release workflow. No token is stored anywhere.
  A tag builds the sdist and wheel, checks the tag against the declared version,
  records artifact digests in the run log, installs the wheel into a clean venv
  and resolves every console script, then rebuilds a wheel from the sdist before
  anything is published.
- Publishes to PyPI as `plexus-mesh`. The console script stays `plexus`. No
  runtime behavior changed in this release.

## 0.2.1

Honesty repairs to the wiring surface (the credo: color/verdict vocabulary only
where a real check ran; no receipt no accept; the honest null is first-class).

- Edges are DECLARED, not probed: declarative discovery never imports,
  resolves, or runs the cited tools, so each edge is tagged
  `evidence: "declared"` and the "grounded, not asserted" / "traces back to
  real code" / "genuinely compose" wording is gone.
- Duplicate organ ids are NAMED (`discover().collisions`, `validate` reports
  `duplicate_organs` and exits 1) instead of collapsing last-writer-wins.
- `discover` stamps a re-runnable `receipt`: plexus version, UTC timestamp, and
  per-manifest source + sha256 over canonical content.
- `validate` now fails on an emit with no module evidence and never raises on a
  malformed external manifest (missing organ / capability).
- `plan_to` marks a hop `runnable: false` and names the absence instead of
  coercing an undeclared CLI into a command.
- Declare the schema-exact Mneme/Crucible replay loop:
  `crucible.replay-template/1` routes Crucible→Mneme and
  `crucible.replay-pack/1` routes Mneme→Crucible, while retaining the existing
  Mneme→Crucible thesis route.
- Refresh the Mneme declarations from public main: the native Crucible export is
  `mneme.crucible-export/2`, still consumable as `crucible.thesis/1`, and Mneme
  also declares `mneme.local-origin-recheck/1` as a terminal read-only freshness
  report capability.
- Add Canon and Relay to the declared capability catalog from public
  origin-main source, with repo-relative public paths and no live external lane probing by Plexus.
- Keep this release on the GitHub-asset track: wheel, sdist, and
  `SHA256SUMS.txt` are reviewable release assets, while PyPI publication remains
  outside this patch.

## 0.2.0

- Graph export (`to_mermaid`, `to_dot`; `plexus graph --format mermaid|dot`):
  render the mesh as a diagram, self-loops marked distinctly.
- Pipeline runner (`pipeline_script`; `plexus run --goal ORGAN`): turn a plan
  into a runnable, ordered shell script that ends at the target, with feedback
  loops surfaced as a comment.
- `COMPARISON.md`: grounded positioning vs MCP / LangGraph / Dagster / CrewAI —
  where plexus wins (decentralized, evidence-cited discovery) and where it does
  not (no execution engine).
- Manifest export (`export_all`, `plexus export`): write each flagship's
  `<organ>.interop.json` — the exact file a tool ships to join the mesh. The
  five real manifests are committed under `manifests/`, and a round-trip test
  proves discovery from the JSON files matches the in-code registry exactly
  (the format is lossless — the premise of decentralized discovery).
- MCP server (`mcp.py`, `plexus mcp`): a zero-dep stdio JSON-RPC server exposing
  discover / wiring / plan / route as MCP tools, so an agent can query the mesh
  mid-task (not just a human at a CLI). `handle()` is transport-free and tested.
- 31 falsifiers total.

## 0.1.0

Initial release.

- Manifest model (`Manifest`, `Port`) + validator: a tool's interop contract as
  plain JSON, with `consumable_as` aliasing and per-port module evidence.
- Mesh discovery (`discover`, `Mesh`): producer→consumer edges by capability,
  with self-loop marking and an `orphans()` honesty surface (unmet inputs /
  unconsumed outputs).
- Planning (`plan_to`, `route`): upstream pipeline to feed a target (Kahn
  ordering with feedback loops reported in `cyclic`), and shortest capability
  path between two tools.
- Built-in registry: five flagship manifests (gather, crucible, forum, index,
  mneme) transcribed by hand from a 2026-07-07 source survey (declared, not
  re-checked at runtime); external manifests via `load_dir` over `*.interop.json`.
- CLI: `discover`, `wiring`, `plan`, `route`, `validate`.
- 17 falsifiers; zero runtime dependencies.
