# index (the structure lane)

*Native feature documentation for `index` as it lives inside Flywheel.*

Integration status: **native lane**. `index` is registered in `harness/lanes_registry.py`, covered by the lane expected-set test in `tests/test_lanes.py`, driven by a desktop bridge (`harness/index_bridge.py`), served over HTTP (`harness/index_route.py`, wired at `harness/gateway.py:1963`), given a durable job path (`harness/index_jobs.py`), and folded into the workspace knowledge graph (`harness/knowledge_graph.py:150`). Source repo: `public/index`. PyPI distribution: `index-graph`. Console command: `index`. Python module: `index_graph`.

---

## 1. Description

**One sentence.** `index` is Flywheel's structure lane: it reads a repository or a whole workspace from files, manifests, and real imports, and emits maps, dependency and symbol graphs, budgeted context envelopes, and verified single-repo wikis, where every edge and page carries the file, line, and hash that lets a stranger re-derive it.

**One paragraph.** Inside Flywheel, `index` is the lane that answers "what is the shape of this code, and what should an agent actually load." It scans nine language ecosystems (Python, JavaScript and TypeScript, Rust, Go, Java, C#, Ruby, PHP, C and C++) through `src/index_graph/graph/resolvers/`, records each dependency edge with the file and line behind it, and grades edges by whether a manifest and an observed import agree. On top of the graph it derives four kinds of artifact: an inventory map, a dependency and symbol graph, a budget-bounded context envelope with typed omission codes, and a commit-pinned verified wiki that a `--verify` pass re-checks as MATCH, DRIFT, or UNVERIFIABLE. It ships as pure Python 3.11 standard library with an empty `dependencies` list in `pyproject.toml`, writes self-contained offline HTML, and never calls a model or the network to reach its verdicts. Flywheel consumes it two ways: as an MCP satellite in the lane roster, and as a synchronous desktop bridge that shells the CLI and returns its JSON verbatim so the app reads the engine's own answer rather than a reconstruction.

---

## 2. Feature list (each bound to code)

- **Repository inventory map.** `index map` builds a workspace catalog: repo count, dirty count, per-language class counts, and a `root_sha256_prefix` fingerprint. Handler `src/index_graph/cli_handlers/maps.py`; MCP tool `index.map`; Flywheel summary at `harness/index_bridge.py` `index_summary`.
- **Cross-repo dependency graph with roles and cycles.** `index graph` and `index viz` build relations, salience, roles, and cycle membership from manifests and observed imports. Code in `src/index_graph/graph/build.py`, `graph/roles.py`, `graph/cycles.py`, `graph/edges.py`; nine resolvers in `graph/resolvers/`; MCP tool `index_graph`.
- **Two-layer atlas (code plus docs).** `index atlas` places every Markdown doc as a node next to the repo it lives in and derives four edge kinds, each from a real source: depends-on (import or manifest line), describes (doc location), links-to (a wiki-link in the body), mentions (a name in prose). Described in `README.md`; rendered sample `examples/atlas-demo.html`.
- **Single-page workbench.** `index workbench` renders map, rendered docs, context lens, and a health panel into one offline HTML file, with page-weight budgets that print what they dropped as "N of M" and are overridable (`--max-doc-bodies`).
- **Single-repo verified wiki.** `index wiki` derives one repo's wiki from the module and symbol graph and generates no prose. It seals a commit-pinned manifest; `index wiki --verify` re-checks it and returns MATCH, DRIFT, or UNVERIFIABLE with exit codes 0, 1, 2. A git URL is shallow-cloned, derived, and cleaned up. MCP tool `index.wiki`.
- **Context lens and context envelope.** `index lens` replays the greedy budget rule live in the browser; `index context` packs repo-level dependency context; `index context-envelope` mints a budgeted packet where each retained repo carries hashed source references and each omission carries a typed code such as `budget_exceeded`, and `--verify` re-fingerprints a cached envelope and exits non-zero if the map drifted. Code in `src/index_graph/context/lens.py`, `context/envelope.py`, `context/pack.py`, `context/select.py`; MCP tools `index.context`, `index.context.envelope`, `index.select`.
- **Symbol navigation and LSP.** `index symbols` gives go-to-definition, find-references, and find-implementations with `file:line` on every hop, from the CLI or over a hand-rolled stdio LSP server (`index lsp`) with no new dependencies. An unresolved reference returns empty rather than a guessed jump. Code in `src/index_graph/cli_handlers/symbols.py`, `cli_handlers/lsp.py`, `internals/`; MCP tools `index.symbol-graph`, `index.symbol-definition`, `index.symbol-references`, `index.symbol-implementations`, `index_internals`, `index_focus`.
- **Architecture as a testable rule.** `index check` measures the real graph against layer, forbid, require, and `max_cycles` rules declared in `.index.toml`, reports each breach with file and line, and exits non-zero for CI. Code in `src/index_graph/arch/check.py`, `arch/criteria.py`.
- **Drift, freshness, and invalidation.** `index snapshot` then `index drift` diff the shape over time; `index check --freshness` stamps a workspace-fingerprint certificate that `index freshness` later answers FRESH or STALE; `index invalidate` names exactly which artifacts a change invalidated with typed reasons (schema `index.invalidation/1`). Code in `src/index_graph/drift/`, `freshness/`, `certify/`; MCP tools `index.invalidate`, `index_verify`.
- **Router doc.** `index router` derives a deterministic `CLAUDE.md`/`AGENTS.md` workspace map from the graph and docs. MCP tool `index_router`.
- **On-demand wiki server.** `index serve` binds loopback, serves any repo by its forge path, derives the wiki that moment by the same path as `index wiki`, and discards it. Code in `src/index_graph/cli_handlers/serve.py`.
- **Operator surface.** `index status`, `index doctor`, `index demo`, and `index bench` expose machine-readable envelopes; `index bench` reports `edge_grounding`. Code in `src/index_graph/flagship.py`, `bench/economy.py`; MCP tools `index.status`, `index.doctor`.
- **MCP server.** `index mcp` serves the map, context, envelope, selection, wiki, symbol, and verification surfaces as native tools. Code in `src/index_graph/mcp.py`; 18 tool definitions in `_tool_defs()`.
- **Zero runtime dependencies, deterministic, private by default.** `pyproject.toml` `dependencies = []`. Same input gives the same bytes. Paths are root-relative, the local root reduces to a short hash, and credential-shaped fragments in remote URLs are redacted. A test keeps the dependency count at zero; the suite collects 585 tests (self-reported in `README.md`).

---

## 3. Stepwise usage

**Install.**

```bash
pip install index-graph
```

Python 3.11 or newer. No other runtime dependency.

**Map one unfamiliar repo and re-check it.**

```bash
index wiki --root path/to/repo --out wiki.html
index wiki --verify wiki.html --root path/to/repo
# verdict=MATCH pages=N edges=M   (exit 0; DRIFT=1, UNVERIFIABLE=2)
```

Edit a source file and verify again; the verdict turns DRIFT and the exit code turns 1, naming the page and rule that failed.

**Map a whole workspace onto one page.**

```bash
index workbench --root path/to/workspace --out workbench.html
# or individual surfaces:
index atlas --root path/to/workspace --format html --out atlas.html
index viz   --root path/to/workspace --format html --out graph.html
```

**Mint and verify a context envelope for an agent.**

```bash
index context-envelope --root path/to/workspace --budget 8000 --focus my-repo --json > envelope.json
index context-envelope --verify envelope.json --root path/to/workspace   # exit 1 if the map drifted
```

**Put architecture in CI.** Declare layers in `.index.toml` (see `example.index.toml`), then:

```bash
index check --root path/to/workspace   # non-zero on any breach, with file:line
```

**Inside Flywheel.** The lane is launched by the roster, not by hand. Its status is read through the lane layer:

```bash
python -m harness.lanes            # prints the lane roster
python -m index status --json      # the same operator envelope, from a source checkout
```

The desktop reads a project card through the HTTP route:

```bash
curl -s localhost:PORT/api/index/summary -d '{"root":"path/to/workspace"}'
```

---

## 4. Piecewise reference

**CLI commands** (full flag reference in `USAGE.md`, artifact schemas in `docs/PROTOCOL.md`):

| Command | What it does |
| --- | --- |
| `index` | Bare run writes `INDEX.json` and prints its path first. |
| `index map` | Repository inventory: repos, file and class counts, dirty state, root fingerprint. |
| `index graph` | Dependency and knowledge graph: relations, roles, salience, cycles. |
| `index viz` | Render the graph to HTML, SVG, Mermaid, or all; `--focus`, `--no-external`. |
| `index atlas` | Two-layer map joining docs to code, four derived edge kinds. |
| `index workbench` | Map, docs, lens, and health on one HTML page under page-weight budgets. |
| `index wiki` | Single-repo verified wiki from the graph; `--verify` re-checks a sealed artifact. |
| `index serve` | Loopback on-demand wiki server; derives per request, discards after. |
| `index lens` | Live replay of budgeted context assembly. |
| `index context` | Repo-level dependency context pack. |
| `index context-envelope` | Budgeted envelope with hashed source refs and typed omission codes; `--verify` re-checks freshness. |
| `index select` | Path selection with typed rejection receipts. |
| `index internals` / `index internals-symbols` | Intra-repo module and call graphs, with cycles and coverage. |
| `index symbols` | Go-to-definition, find-references, find-implementations with `file:line`. |
| `index lsp` | Stdio LSP server for editors, zero new dependencies. |
| `index check` | Measure the graph against `.index.toml` rules; non-zero on breach. |
| `index snapshot` / `index drift` | Capture shape, then diff two snapshots. |
| `index freshness` / `index invalidate` | Answer FRESH/STALE from a certificate; name what a change invalidated. |
| `index verify` | Ground a `depends`/`exists` claim: MATCH/REFUTED/UNVERIFIABLE with evidence. |
| `index router` | Deterministic `CLAUDE.md`/`AGENTS.md` workspace map. |
| `index bench` | Faithfulness metrics including `edge_grounding`. |
| `index status` / `doctor` / `demo` | Operator envelopes, machine-readable with `--json`. |
| `index mcp` | Serve the surfaces above as MCP tools. |

**MCP tools** (from `src/index_graph/mcp.py` `_tool_defs()`): `index.map`, `index.context`, `index.context.envelope`, `index.select`, `index.invalidate`, `index.wiki`, `index.symbol-graph`, `index.symbol-definition`, `index.symbol-references`, `index.symbol-implementations`, `index.status`, `index.doctor`, `index_graph`, `index_focus`, `index_verify`, `index_router`, `index_internals`. Three tools cache behind fingerprints: `index.map`, `index.context`, `index.context.envelope`.

**Flywheel bridge functions** (`harness/index_bridge.py`): `index_view(root, view)` runs one of three views (`map`, `graph`, `symbols`) and returns the engine JSON under `result` (schema `flywheel.index-view/v1`); `index_summary(root)` returns a compact card (`repo_count`, `dirty_count`, `class_total`, `root_sha256_prefix`; schema `flywheel.index-summary/v1`). Durable workspace-map jobs live in `harness/index_jobs.py` (schema `flywheel.index-workspace-map-job/v1`).

**HTTP routes** (`harness/index_route.py`, dispatched at `harness/gateway.py:1963`): `POST /api/index` and `POST /api/index/summary` for the synchronous card, `POST /api/index/workspace-map/{start,status,result,cancel,resume}` for durable jobs.

---

## 5. Composition tutorial: index inside the application

**Which lane it is.** In `harness/lanes_registry.py` the entry reads:

```python
"index": Lane(
    "index", "index-graph", "index", ("mcp",), "pip", "2.10.0",
    "workspace map + symbol graph + verified wiki (the catalog lane)",
    "structure", source_repo="public/index", py_module="index_graph"),
```

So the lane's organ is `structure` and its role is the catalog lane. It is a `pip` lane whose distribution name (`index-graph`) differs from its command (`index`), an asymmetry the roster maps explicitly and the expected-set test pins (`tests/test_lanes.py:30-38`). Because index is read-only over MCP (map, graph, wiki, verify), it sits below the T2 actuation gate that `harness/lane_caller.py` enforces; a T1-classified run can call its tools, unlike the `accountable-surface` lane.

**What it consumes from peers.** A filesystem root: one repo, or a workspace directory of repos. It reads manifests and real imports; it does not require another lane's output to run. It optionally reads an `.index.toml` for classification, scan tuning, privacy rules, and the architecture block. It can map any directory tree, including a `gather` corpus directory.

**What it emits for peers.** Deterministic, evidence-backed artifacts other lanes and the desktop consume:

- The map and summary that `harness/knowledge_graph.py` folds into the workspace knowledge graph and the desktop project card.
- The graph and symbol surfaces that the desktop bridge and HTTP route serve.
- A budgeted `context.envelope` with hashed source references and typed omission codes, which an execution lane loads instead of a blind file dump.
- A sealed, commit-pinned wiki and a set of verdict artifacts (`index.invalidation/1`, freshness certificates) that a downstream check re-runs.

**Worked example: index + gather + an execution lane.** A concrete flow that uses only real tool names:

1. The `gather` lane (organ `perception`) runs an intake and writes a corpus with provenance receipts under a run root.
2. `index context-envelope --root workspace --budget 8000 --focus target-repo --json > envelope.json` mints a budgeted packet. Retained repos carry hashed source references; anything dropped carries a code such as `budget_exceeded`, so a reader can ask for more rather than inherit confidence from a missing file.
3. An execution lane (the bundled `local-model` engine, or the `relay` agent) receives that envelope as its context, so its run starts from a bounded, receipt-backed view of the workspace.
4. Before the run acts, `index context-envelope --verify envelope.json --root workspace` re-fingerprints the repos and exits non-zero if the map moved under the envelope. Stale context is caught by a check instead of acted on by mistake.

The same seam works over MCP: a host calls `call_lane_tool("index", "index.context.envelope", {...})` (`harness/lane_caller.py`) and gets the identical envelope the CLI produces.

**Wiring status against the chorus model.** The task's reference case, `chorus`, is wired as a bridge (`harness/chorus_bridge.py`), a gateway route (`/api/discourse`, `harness/gateway.py:1973`), and an expected-set test (`tests/test_chorus_bridge.py`), but it is not a lane. index carries that same bridge and route pattern and adds the two pieces that make it a full native lane:

- **lanes_registry entry.** Present (`harness/lanes_registry.py:68-71`).
- **Expected-set test.** Present (`tests/test_lanes.py:22-38` pins the roster membership, install-name-to-command asymmetry, and version 2.10.0).
- **Desktop card and route.** Present (`harness/index_bridge.py`, `harness/index_route.py`, `harness/index_jobs.py`, dispatched at `harness/gateway.py:1963`).
- **Payload manifest and schemas.** Present: MCP tools declared in `src/index_graph/mcp.py`, artifact schemas in the index repo's `docs/PROTOCOL.md`, and the Flywheel wrapper schemas `flywheel.index-view/v1`, `flywheel.index-summary/v1`, `flywheel.index-workspace-map-job/v1`.

No new lane wiring is required. The remaining items are corrections, not integration work, and are recorded in the integration-gap note: a version-string skew between the source (2.10.0) and the README/CHANGELOG (2.9.0), a dead `relation_count` field the project card reads but the summary never sets, and a desktop bridge that covers three of the CLI's surfaces while the rest reach Flywheel through the MCP lane and CLI.
