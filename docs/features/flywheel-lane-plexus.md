# plexus (Flywheel lane)

## What it is

Plexus is the Flywheel lane that reads the interop manifests of the other lanes and computes how their outputs plug into each other's inputs.

Flywheel gives an agent a flat roster of lanes, and each lane declares what it emits and what it consumes. Plexus reads those declarations and derives the wiring: for every capability a lane consumes, it finds the lanes that emit something satisfying it, and reports the result as a mesh of producer-to-consumer edges. From that mesh it plans the upstream pipeline that feeds a target lane, routes the shortest capability path between two lanes, renders a diagram, and emits a runnable shell pipeline. Every edge and every plan carries a re-derivable receipt bound to the exact manifest bytes it came from. Plexus does not import, resolve, or run the lanes it describes. Each edge is tagged `declared` and cites the module its producer names, and that citation is a claim you follow and check yourself. It holds the `wiring` role in the lane registry, and it is the one lane whose subject is the other lanes.

## Feature list

Each item cites the code it rests on. Paths are relative to the Plexus source checkout (`public/plexus`) or to the Flywheel harness.

- **Manifest model.** `Manifest` and `Port` in `src/plexus/manifest.py` hold a lane's interop contract as plain data: an organ id, an `invoke` dict, the ports it emits, the ports it consumes, and evidence file paths. A `Port` carries a capability string, a title, a `module` file:function pointer, a summary, and a `consumable_as` tuple. `Manifest.from_dict` is tolerant by contract and never raises on malformed input.
- **Capability matching.** `Port.satisfies` (`src/plexus/manifest.py`) matches by capability string: a port satisfies a wanted capability when the string equals its own capability or appears in its `consumable_as` aliases.
- **Mesh discovery.** `discover` in `src/plexus/mesh.py` builds the `Mesh`: an edge `A -> B` for capability `cap` exists when `B` consumes `cap` and `A` emits a port that satisfies `cap`. Self edges are marked with `self_loop=True`. Every edge is tagged `evidence="declared"`.
- **Wiring map.** `Mesh.wiring` returns each capability mapped to a sorted list of `(producer, consumer)` pairs.
- **Upstream and downstream lookups.** `Mesh.producers_of` and `Mesh.consumers_of` return the sorted unique lanes that feed a given lane or that consume its output, both skipping self loops.
- **Orphan surface.** `Mesh.orphans` returns `unmet_inputs` (capabilities consumed by some lane but emitted by none in the set) and `unconsumed_outputs` (capabilities emitted but consumed by none). This is the honest-null surface for an external or human input and for a terminal output.
- **Collision naming.** `duplicate_organs` in `src/plexus/manifest.py` lists organ ids declared by more than one manifest, and `Mesh.collisions` carries them. A clashing id is named in that list so the clash stays visible, while the lookup dict keeps one manifest per organ (last writer wins).
- **Manifest validation.** `validate` in `src/plexus/manifest.py` returns a list of problems (empty means valid). It flags a missing organ id, a port with no capability, a duplicate capability on one side, and an emit with no `module` evidence. It reports malformed input and never raises on it.
- **Planning.** `plan_to` in `src/plexus/plan.py` returns the upstream lanes that transitively feed a target, in dependency order from a Kahn topological sort. The acyclic prefix comes back in dependency order, and any feedback loop goes into a separate `cyclic` list that stays honest about mutual dependency. Each hop is marked `runnable` only when both ends declare a CLI; an undeclared CLI is named in the hop and left uncalled.
- **Routing.** `route` in `src/plexus/plan.py` returns the shortest capability path between two lanes from a breadth-first search over edges, with a `connected` flag and the per-hop capability chain.
- **Re-derivable receipts.** `build_plan_receipt` and `verify_plan` in `src/plexus/receipt.py` bind a plan or route to the content hash of every manifest it references plus a hash over the plan body. `verify_plan` re-derives the plan from the mesh and never trusts the stored body, so a tampered body and a manifest that changed since the plan both fail the check. The schema is `plexus.plan-receipt/1`.
- **Discovery receipt.** The CLI stamps a mesh-level `receipt` (`src/plexus/cli.py`, `_receipt`) with the plexus version, a UTC timestamp, and per-manifest source plus a sha256 over canonical content. `content_hash` in `src/plexus/manifest.py` excludes the source field, so the hash binds what was declared and a stranger can recompute it from the same bytes.
- **Diagram export.** `to_mermaid` and `to_dot` in `src/plexus/graph.py` render the mesh as a Mermaid flowchart or a Graphviz DOT digraph, with cross-lane edges solid and self loops dotted.
- **Pipeline script.** `pipeline_script` in `src/plexus/run.py` turns a plan into a commented, ordered bash script that ends at the target. A feedback loop is emitted as a labelled comment. The script is output for a human to read and run; plexus does not execute it.
- **Built-in registry.** `builtin_manifests` in `src/plexus/registry.py` returns eight lane manifests transcribed by hand from a 2026-07-07 source survey: gather, crucible, forum, index, mneme, learn, telos, and flywheel-infra. These pointers are declared citations and are not re-read at runtime.
- **External manifest loading.** `load_dir` in `src/plexus/registry.py` reads every `*.interop.json` file in a directory, recording each file path as the manifest's provenance source. `export_all` writes each built-in manifest back out as `<organ>.interop.json`, the exact file a lane would ship to join the mesh.
- **Live probe.** `probe_lane` and `probe_all` in `src/plexus/registry.py` spawn a lane's MCP server through `harness.lanes` and call `tools/list` and `status`, returning `{name, reachable, tools, error}`. This is the one path that runs a lane, and it requires the Flywheel harness on the import path and the lane's MCP server reachable.
- **Command line.** `src/plexus/cli.py` exposes `discover`, `wiring`, `plan`, `route`, `validate`, `verify`, `graph`, `run`, `export`, and `mcp`. Source flags `--builtin` and `--dir DIR` select which manifests load. `validate` exits 1 on any problem, and `verify` exits non-zero on drift, so both work as CI gates over a toolchain's wiring.
- **MCP server.** `src/plexus/mcp.py` serves a zero-dependency stdio JSON-RPC 2.0 server (protocol `2025-06-18`) exposing `plexus_discover`, `plexus_wiring`, `plexus_plan`, `plexus_route`, `plexus.status`, and `plexus.doctor`. `handle` maps a request dict to a response dict and is testable without pipes. This is how an agent queries the mesh while it works.
- **Zero runtime dependencies.** `pyproject.toml` declares an empty `dependencies` list and Python 3.11 or later. The package name is `plexus-mesh`, version 0.2.0, under the fair-source license `LicenseRef-FSL-1.1-MIT`.

## Stepwise usage

### Inside Flywheel, as a lane

Plexus is declared in `harness/lanes_registry.py` under the name `plexus`, role `wiring`, organ `plexus`, kind `pip`, version 0.2.0, with `source_repo="public/plexus"` and `py_module="plexus.cli"`. Its MCP args are `("mcp",)`, so the lane runs `plexus mcp`.

1. The lane carries `package_disabled_reason="No published PyPI distribution is available. Use a Plexus source checkout."`. Because of that, `resolve_mcp_command` in `harness/lanes.py` returns an empty argv on the public roster surface, and the runtime resolver launches the lane from the `public/plexus` source checkout, which is the admitted install profile for this lane.
2. `lane_status("plexus")` reports the lane's install or source and runtime-selection metadata. With `probe=True` it spawns the stdio MCP server and confirms it answers the `plexus.status` tool.
3. An agent connected to the roster calls the plexus MCP tools while it works: `plexus_discover` for the whole mesh, `plexus_plan` to find what feeds a target lane, and `plexus_route` to find the path between two lanes.

### As a CLI or library

```
pip install git+https://github.com/HarperZ9/plexus.git    # or use the public/plexus source checkout
```

```
$ plexus discover --builtin        # the mesh: organs, edges, orphans, receipt
$ plexus wiring   --builtin        # capability -> (producer, consumer) pairs
$ plexus plan --goal crucible --builtin
$ plexus route --from gather --to crucible --builtin
$ plexus graph --format mermaid --builtin
$ plexus run  --goal crucible --builtin     # a runnable shell pipeline
$ plexus mcp                                # the stdio MCP server
```

```python
from plexus import (builtin_manifests, discover, plan_to, route,
                    to_mermaid, pipeline_script)

mesh = discover(builtin_manifests())
mesh.edges                         # every producer -> consumer edge, tagged declared
mesh.wiring()                      # capability -> [(producer, consumer)]
mesh.orphans()                     # unmet inputs / unconsumed outputs
plan_to(mesh, "crucible")          # the upstream pipeline, plus any cycles
route(mesh, "gather", "crucible")  # the capability path between two lanes
```

### Save a plan and re-verify it later

```
$ plexus plan --goal crucible --builtin > plan.json
$ plexus verify --plan plan.json --builtin     # exit 0 if it still holds, 1 if it drifted
```

`verify` re-derives the plan from the current manifests and compares receipts, so a manifest that changed since the plan makes the drift visible and keeps the wiring from shifting under you unseen.

## Reference

### CLI commands (`src/plexus/cli.py`)

- `plexus discover [--builtin] [--dir DIR]` prints the mesh JSON: `organs`, `edges` (each with `via` module and `evidence`), `orphans`, `collisions`, and a provenance `receipt`.
- `plexus wiring [...]` prints the capability-to-pairs map.
- `plexus plan --goal ORGAN [...]` prints the upstream pipeline for a target: `order`, `hops`, `cyclic`, `sources`, and a `receipt`.
- `plexus route --from A --to B [...]` prints the shortest capability path with a `connected` flag and a `receipt`.
- `plexus validate [...]` prints per-organ problems and any `duplicate_organs`, and exits 1 when a problem exists.
- `plexus verify --plan FILE [...]` re-derives a saved plan or route from the current mesh and exits 0 when the receipt still holds, 1 on drift.
- `plexus graph --format mermaid|dot [...]` prints a Mermaid flowchart or a DOT digraph.
- `plexus run --goal ORGAN [...]` prints a runnable, commented bash pipeline that ends at the target.
- `plexus export [--dir manifests]` writes each built-in manifest as `<organ>.interop.json`.
- `plexus mcp` starts the stdio MCP server.

### Library surface (`src/plexus/__init__.py`)

- `Manifest`, `Port`, `validate` from `manifest.py`.
- `Mesh`, `Edge`, `discover` from `mesh.py`.
- `plan_to`, `route` from `plan.py`.
- `build_plan_receipt`, `verify_plan` from `receipt.py`.
- `to_mermaid`, `to_dot`, `pipeline_script` from `graph.py` and `run.py`.
- `builtin_manifests`, `load_dir` from `registry.py`.

### MCP tools (`src/plexus/mcp.py`)

- `plexus_discover`: organs, edges (producer, consumer, capability, self_loop, via module), and orphans. Optional `dir` argument loads extra `*.interop.json` manifests.
- `plexus_wiring`: the capability-to-pairs map.
- `plexus_plan`: the upstream pipeline for a `goal` organ, with feedback loops reported.
- `plexus_route`: the shortest capability path from `source` to `target`.
- `plexus.status`: server name, version, and protocol. A network-free liveness probe.
- `plexus.doctor`: the status fields plus the built-in manifest count and the exposed tool names.

### Data shapes

- `Port(capability, title="", module="", summary="", consumable_as=())`. An emit without a `module` fails `validate`.
- `Manifest(organ, invoke, emits, consumes, evidence, source)`. `invoke` holds `cli`, `mcp_server`, and `python_import` (or `node_entry`) keys.
- `Edge(producer, consumer, capability, producer_module, consumer_module, self_loop=False, evidence="declared")`.
- `Mesh(organs, edges, manifests, collisions)` with `wiring`, `producers_of`, `consumers_of`, and `orphans` methods.
- Plan receipt: `{schema: "plexus.plan-receipt/1", method_version: "plexus-plan/1", manifest_shas: {organ: sha256}, plan_sha256}`.

## Composition tutorial

### The seam plexus occupies

Flywheel's lanes fall into working roles: gather intakes evidence, crucible assesses, index verifies structure, mneme remembers, forum records traces, and the infrastructure controls seal receipts. Plexus sits above that roster as the `wiring` role. It reads the interop manifests the other lanes declare and answers a single kind of question: given these lanes, which one's output is which one's input, and in what order do they run to feed a goal.

### What it consumes from peers

Plexus consumes the declared interop manifests of the other lanes. In the built-in registry those eight manifests (gather, crucible, forum, index, mneme, learn, telos, flywheel-infra) are transcribed in `src/plexus/registry.py`. A lane can also ship its own `*.interop.json`, and `plexus discover --dir DIR` reads it, so a lane joins the mesh by dropping one file into a directory plexus reads. Through `probe_lane` it can additionally spawn a peer lane's MCP server via `harness.lanes` to confirm the lane is live, which is a separate, stronger check than the declared manifest.

### What it emits for peers

Plexus emits the mesh, the wiring map, a plan, a route, a Mermaid or DOT diagram, a runnable pipeline script, and re-derivable receipts. An agent driving the roster reads these to decide which lanes to run and in what order.

Honest null: plexus does not declare an interop manifest of its own in the built-in registry, and it is not a producer node inside the mesh it computes. Its outputs are read by the agent orchestrating the lanes, and no built-in lane declares a capability that consumes a plexus plan. Plexus reads the mesh; it is not wired into it.

### A worked example with another lane

An agent connected to the Flywheel roster wants a crucible verdict and holds gather output. It asks plexus how the two connect.

```
$ plexus route --from gather --to crucible --builtin
```

The route returns a single hop:

```json
{
  "source": "gather", "target": "crucible", "connected": true, "hops": 1,
  "path": [{"producer": "gather", "consumer": "crucible", "capability": "gather.digest/1"}],
  "receipt": { "schema": "plexus.plan-receipt/1", ... }
}
```

That edge rests on gather's declared emit `gather.digest/1` (module `src/gather/digest.py:Digest.to_json`) and crucible's declared consume of the same capability (module `src/crucible/ecosystem_measure.py:GatherDigestMeasure`). The agent then runs the gather lane, takes its digest, and feeds it to the crucible lane.

To feed crucible from scratch, the agent asks for the whole upstream pipeline:

```
$ plexus plan --goal crucible --builtin
```

Against the eight built-in manifests this returns `order: [forum, gather, crucible, index, learn, mneme, telos]` with `sources: [forum, gather]` and `cyclic: [crucible, index, learn, mneme, telos]`. The sources are the lanes with no upstream inside the set, so the agent starts there. The cyclic list holds the feedback loops (crucible and mneme exchange replay packs and templates, and the flagship-action envelope routes through index), reported as loops so the plan stays honest about their mutual dependency. The agent saves the plan, and a later `plexus verify --plan plan.json --builtin` re-derives it and exits non-zero if any of those manifests changed, which turns the wiring into a CI check.

## What is observed and what is bounded

- Observed in code: the manifest model, discovery, planning, routing, receipts, diagrams, the pipeline script, the CLI, and the MCP server, all read from `src/plexus/` at version 0.2.0. The eight built-in manifests and the lane declaration in `harness/lanes_registry.py` are present as described. Running `discover(builtin_manifests())` yields eight organs, 23 edges, and no collisions; `route(gather, crucible)` yields the single `gather.digest/1` hop above.
- Declared, not probed: every edge and every built-in module pointer is a self-reported citation. Plexus does not import or run the cited module, so a pointer goes stale silently if a lane renames a symbol after the 2026-07-07 survey. Follow the pointer yourself before trusting an edge.
- The one live check is `probe_lane`, which spawns a lane and needs the Flywheel harness and a reachable MCP server. Without them it returns `reachable: false` with the reason.
- Plexus does not execute a pipeline. `plexus run` prints a script for a human to read and run.
- Version 0.2.0 is the packaged release. The `CHANGELOG.md` "Unreleased" section describes honesty repairs (collision naming, the discovery receipt, `runnable: false` hops, the Mneme and Crucible replay loop) that are present in the working source read here and are not yet cut into a numbered release.
- Independent project: plexus is one tool in the Zentropy Labs family, fair-source licensed, with commercial use reserved. It makes no optimality claim over MCP, LangGraph, Dagster, or CrewAI; `COMPARISON.md` states it is the discovery layer above an executor and not itself an execution engine.