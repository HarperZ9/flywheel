# Enterprise parity gap report: the five spine flagships (2026-07-09)

Read-only audit of index, forum, gather, crucible, and telos. No repo was
modified. Every claim cites a file path or a command run against the working
trees at C:\dev\public\ on 2026-07-09. Incumbent feature claims (Sourcegraph,
ctags, DeepWiki, LangGraph, CrewAI, AutoGen, firecrawl, crawlee, Scrapling,
promptfoo, braintrust, DeepEval) are from model knowledge and are labeled
moderate confidence; everything about the repos was verified directly.

This is the companion to the earlier
C:\dev\local-model\project-docs\reports\ENTERPRISE-PARITY-GAPS-2026-07-09.md
(mneme, relay, plexus). The roll-up at the end spans all eight flagships.

## Baseline receipt (for continuity, not the primary evidence)

C:\dev\local-model\artifacts\exe\tool_readiness.local.md already scores these
five, and the pattern is the whole story:

| Tool | Verdict | Score | Core | Enterprise | Integration |
|---|---:|---:|---:|---:|---:|
| index | PROTOTYPE_WITH_GAPS | 0.5556 | 1.0 | 0.125 | 0.8333 |
| forum | PROTOTYPE_WITH_GAPS | 0.6667 | 1.0 | 0.25 | 1.0 |
| gather | PROTOTYPE_WITH_GAPS | 0.5882 | 1.0 | 0.125 | 1.0 |
| crucible | PROTOTYPE_WITH_GAPS | 0.5882 | 1.0 | 0.125 | 1.0 |
| telos | INCOMPLETE_STATIC | 0.3529 | 0.25 | 0.125 | 0.8 |

Core and Integration are strong or maxed; the Enterprise sub-score is pinned near
0.125 for all five. The receipt is a metadata-only static scan
(tool_readiness.local.md line 5, "tool source bodies are not read"), so telos's
Core 0.25 is an artifact of a Python-centric scanner reading a Node repo, not a
real core deficit (this audit reads the source and finds a large, tested Node
surface). The deep reads below say the same thing the receipt does: the only weak
axis is enterprise hardening, and it is weak in the same way for every flagship.

## Cross-cutting finding: the five spine flagships are already shipped

Unlike mneme/relay/plexus (none on a registry), four of these five are LIVE on
PyPI at versions that match their working trees, verified by HTTP against the
PyPI JSON API on 2026-07-09:

- index-graph 2.9.0 (pypi.org/pypi/index-graph/json returns 200, latest 2.9.0;
  matches C:\dev\public\index\src\index_graph\__init__.py line 10).
- forum-engine 1.13.0 (200, latest 1.13.0; matches
  C:\dev\public\forum\pyproject.toml line 7).
- gather-engine 1.6.1 (200, latest 1.6.1; matches
  C:\dev\public\gather\pyproject.toml line 8).
- crucible-bench 1.2.0 (200, latest 1.2.0; matches
  C:\dev\public\crucible\pyproject.toml line 7). Note: the memory shard that says
  crucible shipped at 1.1.0 is stale; 1.2.0 is live.
- telos is the exception: project-telos-mcp is NOT on npm
  (registry.npmjs.org/project-telos-mcp returns 404), and its only tag is v0.1.0
  even though package.json line 3 says 0.2.0.

So the P0 for the four Python flagships is not "register and publish" (as it was
for the prior three); it is enterprise hardening plus, in three cases, finishing
a merge or a dirty tree. telos's P0 is genuinely distribution.

Two gaps are universal across all five (and, per the prior report, across all
eight): zero structured logging and no verbose/diagnostic flag, and no SECURITY.md
(forum is the sole exception, it has one). Every repo uses print-to-stderr or
console.error only; a grep for `import logging` in each src tree returns zero
files.

---

## 1. index

### Identity

- What: an evidence-built repo and documentation atlas for multi-repo
  workspaces. Nine-ecosystem dependency graph, symbol graph, a verified single-repo
  wiki (`index wiki`), context lens/packs, an LSP-style navigation surface, and an
  architecture-as-CI-gate. Fully offline, zero runtime dependencies
  (C:\dev\public\index\README.md lines 3, 44-72; pyproject.toml line 21
  `dependencies = []`). 107 Python modules, roughly 11,550 source lines under
  src\index_graph\.
- Version: 2.9.0, distribution `index-graph`, import package `index_graph`,
  console script `index` (pyproject.toml lines 6, 27, 38; version single-sourced
  from src\index_graph\__init__.py line 10, dynamic in pyproject).
- Published: LIVE on PyPI at 2.9.0 (matches). Remote
  https://github.com/HarperZ9/index.git. On branch main, working tree clean,
  main == origin/main. 15 tags v0.1.0 through v2.9.0, all pushed. Five unmerged
  local feature branches that read as superseded, not release blockers.
- MCP: src\index_graph\mcp.py (578 lines), `index mcp`, stdio.
- License: FSL-1.1-MIT (pyproject.toml line 11, LICENSE present).

### Enterprise axes

- Docs: strong. README with a 5-minute quickstart (README.md lines 16-38),
  USAGE.md (47 KB flag and Python-API reference), docs\PROTOCOL.md (artifact
  schemas), docs\INTRODUCTION.md, docs\ENTERPRISE-READINESS.md (operator guide),
  CHANGELOG.md (current, 2.9.0). Gaps: no SECURITY.md despite shipping an HTTP
  server (`index serve`) and an MCP server that ingest untrusted repos;
  CONTRIBUTING.md is a 358-byte stub. Doc drift: README.md line 141 claims "585
  tests"; actual collected count is 600.
- Tests + CI: 600 tests collected (594 `def test_` across tests\). CI (.github\
  workflows\ci.yml) is a single cell: ubuntu-latest, Python 3.12 only, no matrix.
  For a package that claims 3.11+ and is developed on Windows, CI proves neither
  Windows nor the version floor. release-artifacts.yml publishes to PyPI on v*
  tags via a token (env `pypi`, `PYPI_API_TOKEN`), not OIDC, and does not assert
  that the tag equals `__version__` before publishing.
- Error handling/logging: 0 bare except, 4 broad `except Exception` (one
  documented as "never let a transient FS error kill the loop", freshness\
  watch.py line 117). No `import logging` anywhere; the `--diagnostics
  {off,messages,verbose}` flag (cli_parser.py line 359) is print-based, not a
  leveled logging channel.
- File-size gate: 3 modules exceed 300 lines (mcp.py 578, cli_parser.py 408,
  internals\modules.py 337).
- License/packaging: consistent FSL-1.1-MIT; wheel + sdist built and
  twine-checked on tag. Untracked stale dist\ artifacts under the pre-rename name
  `workspace_repo_map-*`, but dist\ is gitignored so nothing ships.

### The one missing user-facing feature vs Sourcegraph/ctags/DeepWiki

No workspace-wide code or symbol search, and symbol navigation is Python-only.
There is no `search` command in the CLI (grep of cli_parser.py finds none), and
symbols\build.py line 20 filters `language == "python"`, so go-to-def/refs/impls
and the per-symbol wiki pages are Python-only (README.md line 56). The dependency
graph spans nine ecosystems (graph\resolvers\ has cpp/csharp/go/java/javascript/
php/python/ruby/rust), so a polyglot team gets a rich cross-language dependency
map but can only navigate symbols in Python and cannot search by name or text at
all. Universal code search is exactly what Sourcegraph is built around and what
ctags delivers across 40-plus languages (moderate confidence). DeepWiki parity is
already met by `index wiki`; search is the gap.

### Quick wins (each under 1 hour)

1. README.md line 141: fix "585 tests" to 600, or stop hardcoding the count.
2. Add SECURITY.md (the tool ships a network server; state disclosure contact and
   supported versions).
3. Add a tag-equals-version guard step to release-artifacts.yml before publish.
4. Expand the 358-byte CONTRIBUTING.md with dev setup and the test command.

### Build order

- P0 (agent-fixable): widen the CI matrix to windows-latest and macos-latest plus
  Python 3.11/3.13 (ci.yml); fix the test-count drift; add SECURITY.md; add the
  release version guard.
- P1: `index search` over the existing symbol and module graph (needs operator
  design sign-off; the single highest-leverage adoption unlock). A real leveled
  logging channel behind the existing `--diagnostics` flag (agent-fixable).
- P2: extend symbol resolution past Python (start with JS/TS or Go, reusing the
  existing resolvers; needs operator, large). Split the 3 over-300-line files.

---

## 2. forum

### Identity

- What: model-agnostic multi-agent orchestration with a replayable, verifiable
  causal ledger. Hash-chained, content-addressed ledger with `verify`,
  `verify(deep=True)`, `replay`, `checkpoint`; routing, planning, roster, policy;
  HTTP and MCP surfaces that dispatch into the same core. Zero runtime
  dependencies (pyproject.toml line 14; CLAUDE.md "pure zero-dependency core").
  58 modules, roughly 9,631 source lines.
- Version: 1.13.0, distribution `forum-engine`, console script `forum`
  (pyproject.toml lines 6-7, 20).
- Published: LIVE on PyPI at 1.13.0 (matches). Remote
  https://github.com/HarperZ9/forum.git. Checked out on feat/flight-recorder, NOT
  main, 5 commits ahead of main and fully pushed; working tree clean. Tags
  v1.0.0 through v1.13.0 pushed. The newest work (src\forum\flight_recorder.py,
  gradable_export.py, grade.py, bench_deep_verify.py plus tests) sits on the
  branch, unmerged to main. PyPI 1.13.0 predates this branch, so a pip user cannot
  reach the flight-recorder or gradable-export features.
- MCP: src\forum\mcp_surface.py (470 lines), 18 canonical `forum.*` tools
  (mapping at mcp_surface.py lines 111-128), a stdio adapter over the HTTP surface
  so the two cannot drift.
- License: Forum Fair-Source License v1.0 (LICENSE line 1), commercial use
  reserved.

### Enterprise axes

- Docs: the strongest set of the five. README, ARCHITECTURE.md (321 lines),
  RUNNING.md, USAGE.md, SECURITY.md (present, the only one of the five that has
  it), RELEASING.md, CONTRIBUTING.md (28 lines, thin), docs\INTRODUCTION.md,
  docs\ENTERPRISE-READINESS.md, plus 23 runnable examples. No generated API
  reference. Doc drift: README.md line 115 claims 533 tests, actual is 556; the
  README command list (line 68) omits the `import-trace` and `mine` subcommands
  that exist in cli.py.
- Tests + CI: 556 tests collected (552 `def test_`, 78 files). ci.yml runs on
  push-to-main and PRs, Python 3.11/3.12 but ubuntu-latest only despite shipping
  "Windows-safe command parsing" and command_split.py; steps ruff, mypy, pytest
  with `--cov-fail-under=85`, demo smoke. release.yml on v* tags builds and
  smoke-installs the wheel, asserts roster==28, and publishes to PyPI via OIDC
  trusted publishing. This is a mature release pipeline.
- Error handling/logging: 0 bare except, 12 broad `except Exception` mostly
  recorded to the ledger with rationale; one genuine silent swallow at daemon.py
  line 125 (`except Exception: pass` around socket teardown). No `import logging`;
  diagnostics are print-to-stderr (about 27 sites in cli.py); no `--verbose`.
- File-size gate: 6 files exceed 300 lines, led by cli.py at 1,034 (a monolithic
  argparse dispatcher), engine.py 609, mcp_surface.py 470, http_surface.py 465,
  dispatch.py 371, delivery_profile.py 313.
- Packaging: wheel and sdist built and verified in release.yml. No py.typed marker
  despite being an importable library with a mypy config (PEP 561 gap: consumers
  of forum-engine get no type information).

### The one missing user-facing feature vs LangGraph/CrewAI/AutoGen

No per-agent tool-calling loop. The Executor protocol (src\forum\executor.py) is
`async run(Assignment) -> Result` where `Result.output` is a single text string;
a grep for `tool_call|function_call|tool_use|tool_choice` in src\forum finds
nothing in the executor path, and there is no streaming. LangGraph, CrewAI, and
AutoGen are built around tool-using agents that invoke a tool, observe the result,
and iterate ReAct-style (moderate confidence). Forum orchestrates the routing,
planning, and accountability layer around agents that emit exactly one completion
each, so an enterprise evaluating "agent orchestration" screens forum out at "can
the agents call tools?" before reaching the ledger, which is forum's real moat.
The differentiated version of this feature would be a tool loop where every tool
call is witnessed to the ledger (auditable tool use).

### Quick wins (each under 1 hour)

1. README.md line 115: fix "533 tests" to 556, or stop hardcoding.
2. Add an empty src\forum\py.typed and list it in package-data (pyproject.toml
   lines 29-30). Ships type info to consumers, about 2 lines.
3. Document the `import-trace` and `mine` subcommands in the README command list.
4. Narrow the silent swallow at daemon.py line 125 to `except (OSError,
   ConnectionError)` or add a rationale comment.

### Build order

- P0: merge and release feat/flight-recorder (5 pushed unmerged commits; operator
  decides merge-to-main and tag, the CHANGELOG "Unreleased" section is already
  staged). Add windows-latest (and macos-latest) to the CI matrix. Add py.typed.
  Reconcile the test-count drift.
- P1: introduce a `logging`-based diagnostic layer with `--verbose/--debug` on the
  daemon and CLI (top operator-facing observability gap). Split cli.py (1,034
  lines) into per-command modules.
- P2: a tool-calling executor loop witnessed to the ledger (the adoption gap, and
  the one that would actually be differentiated); streaming; a generated API
  reference.

---

## 3. gather

### Identity

- What: accountable research intake for difficult sources, with provenance
  receipts and witnessed digests. arXiv, docs, transcripts, OCR, a headless-browser
  edge, crawl, extract, corpus, and federation. Zero-dependency core with opt-in
  capability extras (pyproject.toml line 17 `dependencies = []`; lines 23-26
  fast=lxml, browser=playwright, stealth=curl_cffi). 56 modules, roughly 7,726
  source lines.
- Version: 1.6.1, distribution `gather-engine`, console script `gather`
  (pyproject.toml lines 6-8, 28-29).
- Published: LIVE on PyPI at 1.6.1 (matches, no version lag). Remote
  https://github.com/HarperZ9/gather.git. Checked out on release/v1.6.1 with a
  DIRTY tree: README.md, src\gather\method.py, src\gather\run_config.py modified,
  and an untracked Discord adapter (src\gather\discord.py 340 lines, tests\
  test_discord.py). The committed README and run_config contain zero references to
  Discord while the working-tree versions reference it 8-plus times, so the
  committed docs describe code that exists only as an untracked file; a clean
  checkout of the release tag would not ship Discord at all. Local main is 2
  commits behind origin/main. Only 3 of 16 local tags are on origin (v1.5.0,
  v1.6.0, v1.6.1).
- MCP: src\gather\mcp.py (256 lines), 6 tools (status, doctor, docs, arxiv,
  federation, run).
- License: Gather Fair-Source (LICENSE), commercial use reserved.

### Enterprise axes

- Docs: strong. README, USAGE.md, ARCHITECTURE.md (with a threat model),
  docs\INTRODUCTION.md, docs\ENTERPRISE-READINESS.md, docs\WEB-ENGINE-UPLIFT.md
  (roadmap and benchmarks), CHANGELOG.md, CONTRIBUTING.md (thin, 7 lines). No
  SECURITY.md, which is notable because ARCHITECTURE.md documents an SSRF surface,
  a browser edge that is SSRF-unsafe on redirects (browser.py lines 33-41), and
  handling of bot tokens and API credentials. Doc drift: README.md line 173 claims
  "417 tests"; the collected `def test_` count is 402.
- Tests + CI: 402 `def test_` across 50 files. ci.yml is ubuntu-only, Python
  3.11/3.12, `--cov-fail-under=78`, demo smoke, and does not build a wheel.
  release.yml on v* tags builds and smoke-installs the wheel and publishes to PyPI
  via OIDC trusted publishing.
- Error handling/logging: 0 bare except, 14 broad `except Exception` annotated at
  untrusted seams (for example run.py line 114 `# noqa: BLE001 - a provider is an
  untrusted seam`). No `import logging`; 76 print calls; no `--verbose`.
- File-size gate: scholar.py is 727 lines (the untracked discord.py is 340); all
  other tracked files are at or under 288.
- Packaging: wheel and sdist built and smoke-verified in release.yml.

### The one missing user-facing feature vs firecrawl/crawlee/Scrapling

No anti-blocking layer and no interactive browsing. The browser edge is a single
non-interactive DOM dump: browser.py lines 56-66 shell to `chromium --headless=new
--virtual-time-budget --dump-dom <url>`, and a grep for `click|scroll|wait_for|
infinite|paginate|fill_form` finds zero hits, so it cannot click "load more",
infinite-scroll, wait for a selector, fill a login form, or paginate. There is no
proxy, session, or fingerprint rotation (no proxy module in the tree; fetch.py
line 18 deliberately sends a User-Agent that identifies gather rather than a
browser), and a grep for `captcha|cloudflare|anti-bot|challenge` across src\ finds
zero hits. crawlee, Scrapling, and firecrawl are built around exactly this
(rotating proxies and sessions, fingerprint evasion, Cloudflare handling,
interactive actions) (moderate confidence), so a `gather crawl` against a defended
site gets blocked where they succeed, on precisely the gated/paywalled/JS-walled
surface gather markets. The `[stealth]` curl_cffi extra is a single TLS-
impersonation transport, not a rotation or anti-bot layer. Secondary gap: the
6-tool MCP surface lags the CLI (no extract/crawl/scholar/corpus over MCP).

### Quick wins (each under 1 hour)

1. Resolve the dirty tree: land the Discord adapter as its own commit or revert
   the README/run_config edits so committed docs stop describing uncommitted code
   (needs operator intent call).
2. Add SECURITY.md, reusing the SSRF and browser-edge threat notes already written
   in ARCHITECTURE.md.
3. README.md line 173: fix the "417 tests" claim or make it dynamic.
4. Push the 13 missing tags to origin so release history matches local (operator).
5. Sync local main (2 behind origin/main) to avoid a stale-branch mistake.

### Build order

- P0: resolve the uncommitted Discord feature (operator decides commit vs revert;
  the release branch documents code that is not committed). Add SECURITY.md
  (agent-fixable).
- P1: structured logging plus `--verbose/--debug` (agent-fixable); widen CI to
  Windows and macOS; split scholar.py (727 lines); grow the MCP surface toward CLI
  parity.
- P2: interactive browser actions and an anti-blocking rotation layer (the
  adoption differentiator; operator-scoped, agent-implementable); expand
  CONTRIBUTING and add CODE_OF_CONDUCT.

---

## 4. crucible

### Identity

- What: a judgment engine. Register a thesis, steelman each claim, measure against
  a substrate, refine the weakest axis, and emit a verdict of MATCH, DRIFT, or
  UNVERIFIABLE that recomputes from a sealed record. Zero-dependency core
  (pyproject.toml line 18). 42 modules, roughly 6,209 source lines.
- Version: 1.2.0, distribution `crucible-bench`, console script `crucible`
  (pyproject.toml lines 6-7, 24).
- Published: LIVE on PyPI at 1.2.0 (matches; the memory shard that says 1.1.0 is
  stale). Remote https://github.com/HarperZ9/crucible.git. Checked out on
  release/v1.2.0, working tree clean. Tags v0.5.0 through v1.2.0; about 6 unmerged
  local feature branches.
- MCP: src\crucible\mcp.py plus mcp_tools.py, 13 tools (README.md line 137).
- License: LicenseRef-Fair-Source (pyproject.toml line 11).

### Enterprise axes

- Docs: ARCHITECTURE.md (thorough), CHANGELOG.md, README, docs\INTRODUCTION.md,
  docs\ENTERPRISE-READINESS.md, docs\RELEASE-READINESS.md. USAGE.md is thin (1 KB)
  and CONTRIBUTING.md is a 484-byte stub with no dev setup or PR template. No
  SECURITY.md, notable given the subprocess-execution edge (subprocess_edges.py).
  README's "330 tests" claim is accurate, no drift.
- Tests + CI: 330 tests collected (316 `def test_` plus parametrization). ci.yml
  is Python 3.11/3.12, `--cov-fail-under=85`, ruff, mypy, demo smoke, no wheel
  build. release.yml publishes via OIDC trusted publishing (action pinned by SHA)
  on GitHub Release.
- Error handling/logging: 0 bare except, 7 broad `except Exception` all annotated
  fail-closed impure edges. No `import logging`, no `--verbose`.
- File-size gate: passes. The largest file is 295 lines (mcp_tools.py, assess.py).
  crucible is the only one of the five that satisfies the 300-line gate.
- Packaging: wheel built in release.yml only, twine-checked, OIDC publish.

### Credibility of the verifier (verified against code)

The sealing and recheck layer genuinely fails on tampering, and the verdict is a
real threshold function, not a rubber stamp. `verdict_for` (src\crucible\
verdict.py line 82) computes `margin = (tolerance - deviation) / tolerance` and
emits DRIFT when the margin is negative; the demo shows `DRIFT deviation 8 exceeds
tolerance 0.5` (README.md lines 52-59). `recheck_assessment` re-derives every
verdict from stored measurements (assess.py lines 216-243) and catches a flipped
verdict.

The concern is narrower and real: no shipped oracle executes the steelman's
proposed refutation. measure.py has zero references to `refutation` (grep clean);
run_cmd.py computes refutations only to write them into the record, never to feed
the measure step, so the "steelman proposes the test the measurement runs"
narrative is decorative in shipped code. In the offline path, deviations are
author-supplied (examples\measurements-binary-search.json hardcodes deviation 0.0
and 8.0; the TableMeasure path reads author-declared observed numbers rather than
running the algorithm). crucible itself admits this in code: registry_ops.py lines
125-148 (`_match_provenance`) split MATCH verdicts into `witnessed` (a replayable
recheck descriptor), `asserted` (author-supplied deviation alone), and
`asserted_zero` ("author-supplied-perfection rows a confident registry is most
likely to be padded with"). So a MATCH from the shipped or offline path is only as
sound as the author's input; "cannot fail" is too strong, "as sound as the input"
holds.

### The one missing user-facing feature vs promptfoo/braintrust/DeepEval

A batteries-included, executing measurement and grader layer, which is the same
thing as the credibility gap above. promptfoo runs providers and applies built-in
assertions from one command; DeepEval ships metrics that score out of the box
(hallucination, faithfulness, answer-relevancy, G-Eval); braintrust ships
dataset sweeps and a hosted results UI (moderate confidence). crucible ships none:
the defaults are NullMeasure and NullSteelman (measure.py lines 48-58, steelman.py
lines 51-65), JudgeMeasure's backend defaults to None which yields UNVERIFIABLE
(judge.py lines 83-84), and no grader library (exact-match, regex, JSON-schema,
embedding-similarity) ships. There is no results UI beyond a static
examples\crucible-demo.html and no dataset-driven sweep runner. A user must bring
their own model call, their own substrate numbers, and their own rubric parser
before crucible produces anything but UNVERIFIABLE.

### Quick wins (each under 1 hour)

1. Add SECURITY.md (the subprocess-execution edge makes this expected).
2. Document, in README near line 143 and in the steelman.py docstring, that
   `Refutation.measurable` is advisory and not auto-executed by the measure step,
   to close the gap between the narrative and the wiring.
3. Expand CONTRIBUTING.md (484 bytes) and USAGE.md (1 KB) into a real dev-setup and
   CLI reference.

### Build order

- P0: ship an executing oracle layer: built-in graders (exact-match, regex,
  JSON-schema, embedding-similarity) plus a default JudgeMeasure backend with a
  shipped prompt and parser, so a MATCH can arise from an executed test rather than
  an author-declared number, and either wire `steelman.measurable` into the measure
  step or formally mark it advisory. Needs operator direction; graders are
  agent-implementable. This closes both the credibility and the adoption gap.
- P1: add `import logging` and a `--verbose/--debug` flag through cli.py; add
  SECURITY.md; add a dataset-driven sweep runner and a non-static results viewer.
- P2: API reference, expand USAGE and CONTRIBUTING, branch and tag hygiene, build
  the wheel in CI as a packaging smoke check.

---

## 5. telos

### Identity

- What: the shared workbench and primary engine of the spine. A stdio MCP server
  exposing 41 native `telos.*` tools plus a manifest that launches gather, index,
  forum, and crucible beside it for 69 tools total; four proof lanes with pure
  verifiers, nine doctors, a creative engine, model-foundry and learning-forge
  lanes, context tooling, and native workstation control. Zero dependencies,
  hand-rolled JSON-RPC (README.md lines 11, 17; package.json has no deps key).
  Node-dominant: 171 JS/MJS/TS files versus 8 Python files; roughly 17,268
  non-test source lines.
- Version: 0.2.0, package `project-telos-mcp`, bin `telos` and `telos-mcp`,
  engines node >=20 (package.json lines 2-3, 7-13). MCP entrypoint
  demo\telos-mcp.mjs (366 lines). All 41 tools declare `emptyInputSchema`
  (telos-mcp.mjs lines 12-16, 18-224): every tool is a zero-argument, read-only
  report or receipt emitter, so the surface is very wide but not a parameterized
  "do work" API.
- Published: NOT on npm (registry.npmjs.org/project-telos-mcp returns 404). The
  bin entries make it structured to be npx-runnable, but `npx project-telos-mcp`
  fails today. glama.json is present but minimal (schema plus maintainer only).
  Remote https://github.com/HarperZ9/telos.git. Checked out on
  style/spectrum-banner, 2 commits ahead of origin/main. Only tag is v0.1.0; no
  v0.2.0 tag despite the 0.2.0 version; docs\RELEASE-NOTES-0.2.0.md is a draft.
- Working tree: 91 uncommitted entries. The bulk is the native-control lane in a
  half-committed dual-use state (staged-deleted captcha.mjs; untracked auth.mjs,
  vault.mjs, outreach.mjs, guarded-send.mjs, redteam\, plus about 70 untracked
  outreach receipt artifacts under docs\outreach\receipts\; there is also a
  tools\captcha-solve.py). This is the operator-owned sensitive lane; per the
  memory shards it must not be auto-committed or executed. It is uncommitted and
  not CI-covered.
- License: FSL-1.1-ALv2 (package.json line 6, LICENSE).

### Enterprise axes

- Docs: rich. README (feature-first, quickstart works via `node demo\run.mjs`),
  USAGE.md, CONTRIBUTING.md, RELEASING.md, PRODUCT.md, CHANGELOG.md (26 KB), and 94
  markdown files under docs\ (INTRODUCTION, HOW-IT-WORKS, ARCHITECTURE, PROOF-
  LANES, CURRENT-STATE, roadmaps, registries). Gap: no static tool-catalog or
  reference doc for the 41 (or 69) tools; the authoritative map is runtime-only
  (`node demo\catalog.mjs`), which is a discoverability wall for an integrator
  reading the repo cold. Doc drift: README.md line 118 claims "over 60 test files
  run individually in CI"; 61 exist but only about 40 run in CI.
- Tests + CI: 61 tracked `*.test.mjs` files, roughly 2,720 assert calls. ci.yml
  (ubuntu-latest, Node 24, checks out all four sibling repos plus Python 3.11 for
  a room smoke) runs only about 40 of the 61 by hand-enumerated lines; roughly 20
  test files never run, including tests behind shipped MCP tools (model-foundry,
  learning-forge, learning-forge-labs, creative-kernels, display-calibration,
  browser-evidence, revival-registry, and the causal/embodied/quantum research
  packets). There is no `npm test` aggregate, so new test files silently drift out
  of CI. release.yml is correctly manual and operator-gated: it builds an npm-pack
  tarball and a demo zip on dispatch or a published release and does not automate
  npm publish.
- Error handling/logging: the MCP server has clean try/catch discipline with
  proper JSON-RPC error codes (telos-mcp.mjs lines 298-345). But observability is
  thin: no structured logging and no `--verbose/--debug` on a server that fans out
  to five subprocess servers; a spawned tool failure surfaces only
  `result.stderr||result.stdout`.
- File-size gate: 14 non-test source files exceed 300 lines, led by
  demo\proof-build.mjs (853), demo\viable-viz\reconcile.mjs (712),
  demo\proof-visual.mjs (629), demo\proof-research.mjs (600),
  demo\effects-engine.js (549), demo\model-adapter.js (521).
- Packaging: npx-runnable by construction (bin telos-mcp) but not on npm. The
  files allowlist in package.json is well scoped for `npm pack`. Dockerfile is
  thin and pins node:20 while CI and README advertise Node 24.

### The one missing user-facing feature (biggest adoption blocker)

It is not published to npm. For an MCP server positioned as the primary engine,
the standard adoption path is a host config running `npx -y <pkg>`; the registry
returns 404, so the package.json bin entries are unreachable to any host and the
README quickstart falls back to `git clone` plus `node demo\...`. That is fine for
a demo but is a hard stop for enterprise MCP adoption, where servers are wired by
package spec. This is an operator-only decision (name, publish, tag v0.2.0).
Second-order, once installed: 69 zero-argument read-only tools with no static
catalog present a wide, undifferentiated, undocumented list, so a getting-started
that names the 3 to 5 tools to call first would materially cut time-to-value.

### Quick wins (each under 1 hour)

1. README.md line 118: change "over 60 test files run individually in CI" to the
   true count run by ci.yml (about 40), or fix CI so it is true.
2. Close the CI gap: add an `npm test` script that globs `demo\*.test.mjs` via
   `node --test` and call it from ci.yml so new tests auto-enroll (package.json
   lines 24-30, .github\workflows\ci.yml).
3. Dockerfile line 1: bump `FROM node:20-alpine` to node:24 to match CI and README.
4. Add docs\TOOLS.md generated from the telos-mcp.mjs `tools[]` array (name,
   description, verdict semantics) as a static catalog for the 41 tools.

### Build order

- P0 (operator): decide the npm name (`project-telos-mcp` versus scoped
  `@harperz9/telos`), publish to npm, then tag v0.2.0. Commit or quarantine the 91
  uncommitted files, especially the dual-use native-control lane (do not
  auto-commit or execute). Merge style/spectrum-banner into main.
- P1 (agent-fixable): the CI coverage fix and `npm test` aggregate; a static
  tool-reference doc; server-side structured error logging and a verbose mode;
  reconcile the version/tag/release-notes state.
- P2 (agent-fixable): split the 14 over-300-line files (start with proof-build.mjs
  853 and reconcile.mjs 712); enrich glama.json; harden the Dockerfile.

---

## Summary table

| Axis | index | forum | gather | crucible | telos |
|---|---|---|---|---|---|
| Distribution | index-graph 2.9.0 | forum-engine 1.13.0 | gather-engine 1.6.1 | crucible-bench 1.2.0 | project-telos-mcp 0.2.0 |
| On registry (matched) | PyPI, yes | PyPI, yes | PyPI, yes | PyPI, yes | npm, NO (404) |
| Branch checked out | main (clean) | feat/flight-recorder | release/v1.6.1 (dirty) | release/v1.2.0 (clean) | style/spectrum-banner |
| Tests (collected) | 600 | 556 | 402 | 330 | 61 files, ~40 in CI |
| CI matrix | 1 OS, 1 Python | 1 OS, 2 Python | 1 OS, 2 Python | 1 OS, 2 Python | 1 OS, Node 24 |
| Release publish | PyPI token on tag | PyPI OIDC on tag | PyPI OIDC on tag | PyPI OIDC on release | operator-gated, no auto |
| MCP tools | via mcp.py | 18 | 6 | 13 | 41 (69 via manifest) |
| Structured logging | no | no | no | no | no |
| SECURITY.md | no | yes | no | no | no |
| 300-line gate | 3 over | 6 over | 1 over | passes | 14 over |
| Unmerged/uncommitted | 5 stale branches | 5-commit release branch | uncommitted Discord | ~6 stale branches | 91 files, sensitive lane |
| Missing headline feature | cross-language search | agent tool-calling loop | anti-blocking browsing | executing grader layer | npm publish + tool catalog |

---

## Roll-up across all eight flagships

Across all eight flagships (mneme, relay, plexus from the prior report, plus
index, forum, gather, crucible, telos here), the single most common gap is the
absence of an observability layer: every one has zero structured logging (no
`import logging` in any Python src tree, no console-based structured logging in
telos) and no verbose or debug flag, so an operator running any of these as an
unattended agent host has only print-to-stderr and a final error string to debug
with. The next most common gaps are a missing SECURITY.md (seven of eight; forum
is the sole exception) and README self-reported test counts that have drifted
stale (index, forum, gather, and telos all overstate or misstate their counts).
The shortest path to "all flagships at enterprise parity" splits cleanly into two
tracks. The first is a single cross-repo hardening sweep that is almost entirely
agent-fixable and mechanical: drop one shared `logging` plus `--verbose`
convention into all eight, add a SECURITY.md template to the seven that lack it,
stop hardcoding test counts, and widen the single-cell CI matrices to Windows and
macOS. That sweep alone lifts the uniformly-pinned Enterprise sub-score (about
0.125 in tool_readiness.local.md) for every repo at once, because Core and
Integration are already strong. The second track is a small set of decisions only
the operator can make: publish telos to npm (name plus tag), resolve relay's taken
PyPI name, register the mneme and plexus PyPI trusted publishers, and land the
unmerged or uncommitted release work (forum's flight-recorder branch, plexus's
0.2.0 branch, gather's Discord adapter, and telos's 91-file tree including the
sensitive native-control lane that must be quarantined, not auto-committed). The
four Python spine flagships are already live on PyPI at matching versions, so for
them parity is a hardening sweep plus a merge, not a launch. The per-flagship
headline features (index search, forum's witnessed tool loop, gather's
anti-blocking browser, crucible's executing grader, telos's tool catalog) are
genuine P1/P2 adoption unlocks but are not what the readiness receipt is scoring;
they are the difference between "shipped and hardened" and "wins the bake-off
against the incumbent."
