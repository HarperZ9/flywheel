# Enterprise parity gap report: mneme, relay, plexus (2026-07-09)

Read-only audit. No repo was modified. Every claim cites a file path or a command
run against the working trees on 2026-07-09. Incumbent feature claims (mem0, letta,
aider, MCP routers) are from model knowledge and are labeled moderate confidence;
everything else was verified directly.

Inputs consumed:
- C:\dev\local-model\artifacts\exe\enterprise_readiness_report.local.json and .md
  (verdict HARDENING_REQUIRED for all three; scores mneme 0.60, relay 0.2778,
  plexus 0.2941)
- C:\dev\local-model\artifacts\exe\tool_readiness.local.md (enterprise column 0.0
  for all three; core 1.0 for all three)
- The repos at C:\dev\public\mneme, C:\dev\public\relay, C:\dev\public\plexus

## Cross-cutting finding: the readiness receipt is stale on entrypoints

The receipt (enterprise_readiness_report.local.json) records for relay
`"cli": ["python serve.py"]` and `"mcp": []`, and for plexus `"cli": []` and
`"mcp": []`. Both are wrong against the repos today:

- relay ships a console script `relay = "relay.local_agent_cli:main"`
  (C:\dev\public\relay\pyproject.toml) and a stdio MCP server with 3 tools
  (C:\dev\public\relay\src\relay\local_mcp.py; `relay --mcp` in
  local_agent_cli.py line 156).
- plexus ships a console script `plexus = "plexus.cli:main"`
  (C:\dev\public\plexus\pyproject.toml) and a stdio MCP server
  (C:\dev\public\plexus\src\plexus\mcp.py, on branch feat/graph-run-compare).
- mneme is recorded as `"cli": []` yet ships `mneme = "mneme.cli:main"`
  (C:\dev\public\mneme\pyproject.toml) with 19 subcommands
  (src\mneme\cli.py lines 72-167).

Consequence: the integration scores in tool_readiness.local.md (relay 0.1667,
plexus 0.2) are depressed by stale contract data, not only by real gaps. Regenerate
the tool contract before using these numbers as a baseline.

All three test suites are green as of this audit (run with
`python -m pytest -q -p no:cacheprovider`): mneme 82 passed in 1.42s, relay 53
passed in 4.30s, plexus 31 passed in 0.10s.

---

## 1. mneme

### Identity

- What: accountable agent memory. 4-tier layered memory (L0 turn, L1 atom, L2
  scenario, L3 persona), hybrid BM25 + vector retrieval with RRF fusion,
  provenance receipt on every memory, re-derivable recall receipt, self-flagging
  drift, hash-chained auditable forgetting, temporal supersede/history, entity
  graph, token-economics benchmark, MCP server. Zero runtime dependencies
  (C:\dev\public\mneme\README.md; src\mneme\ has 18 modules, 2,243 lines total).
- Version: 0.1.0, package name `mneme-memory`, console script `mneme`
  (C:\dev\public\mneme\pyproject.toml).
- Published where: GitHub only. Remote https://github.com/HarperZ9/mneme.git,
  tag v0.1.0 exists locally and on origin (`git ls-remote --tags origin` shows
  refs/tags/v0.1.0 at 1dc9fc7, which is HEAD of main). NOT on PyPI:
  https://pypi.org/pypi/mneme-memory/json returns HTTP 404 (checked 2026-07-09).
  The publish job in .github\workflows\release.yml is deliberately gated on the
  repo variable `PYPI_ENABLED == 'true'` and a trusted publisher that has not
  been configured (latest commit 1dc9fc7 "ci: gate PyPI publish job until
  trusted publishing is configured"). README line 8 says "PyPI release imminent"
  and gives the pip-from-GitHub install.
- Working tree clean on main. One unmerged pushed branch: chore/interop-manifest,
  a single commit adding mneme.interop.json (62 lines) for the plexus mesh.

### Enterprise axes

- Docs: strongest of the three. README covers positioning, install, CLI
  quickstart, library API, MCP, benchmark, ecosystem composition, guarantees,
  license (README.md). CHANGELOG.md present. DELIVERY.md is a verified release
  checklist. examples\tour.py exists and CI runs it as a smoke test
  (.github\workflows\ci.yml step "example tour runs"). Missing: an API
  reference (no docs\ directory), a troubleshooting section, an operator guide
  for the MCP server beyond one paragraph, CONTRIBUTING.md, SECURITY.md.
- Doc drift (three internal contradictions, all verified):
  1. README.md line 135 lists 4 MCP tools (remember, recall, drift, provenance)
     but src\mneme\mcp.py defines 6 (adds mneme.forget line 68, mneme.audit
     line 74).
  2. CHANGELOG.md line 42 says "62 tests"; DELIVERY.md line 8 says "42
     falsifiers"; the actual count is 82 test functions across 15 files in
     tests\ (grep "def test_", all passing).
  3. CHANGELOG.md line 3 says "0.1.0 (unreleased)" while the v0.1.0 tag is
     pushed to origin.
- Tests + CI: 82 tests, green. CI matrix 3 OS x 3 Python plus a wheel-install
  job that runs the packaged CLI (.github\workflows\ci.yml). Release workflow
  verifies tag == pyproject version, smokes the wheel, publishes via OIDC
  (.github\workflows\release.yml). This is the best pipeline of the three.
- Error handling/logging: no bare excepts; the single broad
  `except Exception` is at the MCP transport boundary with an intent comment
  (src\mneme\mcp.py line 128). No `import logging` anywhere in src\ (grep
  confirmed). No verbose/diagnostic mode.
- Versioning/changelog: CHANGELOG.md present and detailed; version pinned in
  pyproject.toml; tag matches; the release workflow enforces tag/version match.
- License: MIT (LICENSE, pyproject license field). Matches memory-shard policy
  that brick utilities are MIT.
- Packaging: builds a wheel in CI; PyPI publish is one operator action away
  (trusted publisher + PYPI_ENABLED, documented in DELIVERY.md lines 25-36).
- Security posture: .gitignore covers .env, .env.*, *.key, *.token, and *.db
  ("never commit a user's memory DB"). No hardcoded credentials in src\ (grep).
  DELIVERY.md line 10 records a clean credential scan. No SECURITY.md.
- File-size quality gate: all modules under 300 lines (largest cli.py at 276,
  `wc -l`).

### The one missing user-facing feature vs mem0/letta

No real semantic embedding shipped. src\mneme\embed.py is explicit that the
zero-dep n-gram channel is "FUZZY / lexical-similarity matching, not semantics.
It will not connect 'car' and 'automobile'" (embed.py lines 10-13). A real
embedder must be hand-injected as a Python callable
(`AgentMemory(embedder=fn)`, README.md line 78). mem0 and letta ship
configured embedding-provider integrations (OpenAI-compatible endpoints,
local models) so semantic recall works out of the box (moderate confidence,
from model knowledge). For an adopter comparing recall quality on day one,
this is the gap that loses the bake-off despite mneme winning every
accountability axis. The fix that preserves the zero-dep floor: an optional
env-configured OpenAI-compatible embeddings endpoint
(EMBED_BASE_URL + EMBED_API_KEY) as a built-in embedder factory, plus an
optional extra (e.g. `mneme-memory[st]`) for a local sentence-transformers
edge. Keep the n-gram channel as the dependency-free default.

### Quick wins (each under 1 hour)

1. README.md line 135: list all 6 MCP tools (add forget, audit).
2. CHANGELOG.md line 42 and DELIVERY.md line 8: correct the test count to 82
   (or state "82 and counting" once) and drop "(unreleased)" from CHANGELOG
   when publish happens.
3. Merge chore/interop-manifest (one pushed commit, adds mneme.interop.json;
   closes the loop with plexus manifests\mneme.interop.json).
4. Operator action, minutes not code: create the PyPI trusted publisher
   (project mneme-memory, owner HarperZ9, repo mneme, workflow release.yml),
   set PYPI_ENABLED=true, re-push the tag or cut v0.1.1. DELIVERY.md already
   scripts this.
5. Add SECURITY.md stating the posture already implemented (no network calls,
   no secrets stored, DB is user-owned).

### Build order

- P0: execute the PyPI release (trusted publisher + PYPI_ENABLED + tag). The
  entire pipeline exists; only the operator-side registration is missing.
- P0: fix the three doc-drift items (MCP tool list, test counts, unreleased
  marker). Accountability tooling with stale self-description undermines the
  pitch.
- P1: shipped embedding edge (env-configured OpenAI-compatible endpoint +
  optional extra) to close the semantic-recall gap vs mem0/letta.
- P1: API reference page (module docstrings are strong; generate or hand-write
  docs for AgentMemory, receipts, drift verdicts) and a troubleshooting section.
- P2: SECURITY.md, CONTRIBUTING.md, framework adapters (LangChain/LlamaIndex
  memory interface) as adoption doorways.

---

## 2. relay

### Identity

- What: zero-dependency accountable coding agent for any model endpoint. Tier
  ladder local -> subscription CLI -> API -> gateway -> cloud with failover
  (src\relay\endpoints.py), gated tool loop with repo_map/edit_file/read/list
  plus off-by-default write/exec behind a denylist (src\relay\local_tools.py
  lines 28-55), hash-chained re-verifiable session ledger
  (src\relay\local_session.py), git anchoring (src\relay\local_git.py), test
  repair loop via --test-cmd (src\relay\local_loop.py lines 24-28), stdio MCP
  server with 3 tools (src\relay\local_mcp.py lines 24-32). 1,523 source lines.
- Version: 0.1.0, package name `relay-agent`, console script `relay`
  (C:\dev\public\relay\pyproject.toml).
- Published where: GitHub only, https://github.com/HarperZ9/relay.git. No tags
  local or on origin (`git tag` empty; `git ls-remote --tags origin` empty).
  Not on PyPI under its own name, and worse, see the blocker below.
- Branch state: checkout is feat/test-repair, 1 commit ahead of main (71987fd,
  pushed). main is the 0.1.0 initial commit (3dad879). A second branch
  feat/glm-provider exists on origin. The newest shipped feature (--test-cmd
  autonomous test repair) is not on main.

### Blocker: the PyPI name is taken by someone else

`https://pypi.org/pypi/relay-agent/json` returns HTTP 200 for an unrelated
project: "relay-agent 0.1.0, Open-source autonomous AI agent: label an issue,
get a tested pull request", homepage thinknextsoftware.com, repo
Thinknext-Software-Solutions/Relay (verified 2026-07-09). The name
`relay-agent` in C:\dev\public\relay\pyproject.toml can never be published.
This is a distribution-name decision for the operator, not a code fix, and per
the global no-rename-without-a-plan rule it needs a small checklist: pyproject
name, README install line, egg-info regeneration, and the readiness contract
row. The console script can stay `relay`; only the PyPI distribution name must
change (candidates: relay-coder, relay-ladder, harperz9-relay).

### Enterprise axes

- Docs: README.md covers positioning, install, the tier table, agent tools,
  the ledger wedge, MCP, and library use, in 74 lines. Missing entirely: a
  CHANGELOG (none in repo root), examples\ (none), configuration reference
  (the <PROVIDER>_* env matrix is only half-documented in the README table),
  troubleshooting, API reference, SECURITY.md, CONTRIBUTING.md. Thinnest doc
  set of the three.
- Tests + CI: 53 tests, green in 4.30s. CI matrix 3 OS x 3 Python plus wheel
  install job, hermetic ("no network, no GPU, no model",
  .github\workflows\ci.yml). No release.yml, so there is no release gate at
  all: no tag protocol, no version check, no publish path.
- Error handling/logging: disciplined. Typed BackendError with narrow except
  clauses per transport (endpoints.py lines 48-52, 168-171); broad excepts
  only at the tool boundary ("a tool must never crash the loop",
  local_tools.py line 101) and the MCP boundary (local_mcp.py line 76). No
  `import logging`; no --verbose flag; failures over the ladder are silent to
  the user beyond the final error.
- Versioning/changelog: version exists in pyproject only. No CHANGELOG.md, no
  tags, no releases. This is the receipt gap the readiness report scores.
- License: MIT (LICENSE, pyproject).
- Packaging: wheel builds in CI; blocked from PyPI by the name collision.
- Security posture: keys only from environment (endpoints.py: _k() reads
  os.environ; PROVIDERS table lines 177-188 holds no secrets). Subscription
  tiers invoke the operator's own authenticated CLI and "never proxies or
  replays that client's tokens" (endpoints.py lines 147-150). .gitignore
  covers .env, *.key, *.token and ledgers ("*.jsonl ... never commit a run
  ledger by accident"). Two posture notes: (a) the Gemini backend puts the API
  key in the URL query string (endpoints.py line 135), which leaks into
  proxies and any URL logging; Google accepts the x-goog-api-key header
  instead (moderate confidence). (b) the session ledger stores full turn and
  tool content verbatim with no redaction pass (local_session.py), so a run
  over a file containing a secret persists it into the saved JSONL.
- File-size gate: all modules under 300 lines (largest local_agent.py at 294).

### The one missing user-facing feature vs aider/opencode

No interactive agent session with diff review. relay has a REPL, but it is
chat-only (local_agent_cli.py lines 69-75 read a line and call agent.send);
the coding agent runs only as a one-shot `--agent GOAL` with default
max_steps=6 (local_agent_cli.py lines 140-145). aider's core UX, and
opencode's, is a persistent session where the model proposes edits, the user
sees the diff each turn, approves or refines, and git history accumulates
(moderate confidence, from model knowledge). relay already owns the pieces
(SessionLedger is resumable, local_git.py anchors commits, edit_file is
precise): the missing surface is an agent-mode REPL that shows a unified diff
per edit_file call and asks approve/skip before applying when a tty is
present. That single feature moves relay from "runs a task" to "pairs with a
developer", which is what the incumbents are used for.

### Quick wins (each under 1 hour)

1. Merge feat/test-repair into main (1 pushed, green commit); main currently
   lacks the headline test-repair feature.
2. Add CHANGELOG.md (backfill 0.1.0 from the two commit messages).
3. Copy mneme's .github\workflows\release.yml (tag/version check + OIDC gate);
   it is repo-name parameterized in four places.
4. Move the Gemini key from the query string to the x-goog-api-key header
   (endpoints.py line 135, one header dict change plus its test).
5. Add an examples\ script exercising ledger save + verify() so the wedge is
   demonstrable without credentials.
6. Delete or .gitignore the committed src\relay_agent.egg-info\ build artifact
   directory if tracked (verify with git ls-files first; it may already be
   ignored via *.egg-info/).

### Build order

- P0: resolve the PyPI distribution-name collision (operator decision plus a
  rename checklist) and add the release workflow. Until then relay cannot be
  "shipped" in the enterprise sense at all.
- P0: merge feat/test-repair to main so the public default branch carries the
  differentiator.
- P1: interactive agent session with per-edit diff approval (the adoption gap
  vs aider/opencode).
- P1: CHANGELOG, examples, full configuration reference for the
  <PROVIDER>_MODEL / _PROVIDER_BASE_URL / _CLOUD_BASE_URL / _CLOUD_KEY matrix.
- P2: ledger redaction option, logging/--verbose diagnostics for ladder
  failover decisions, SECURITY.md, decide feat/glm-provider (merge or close).

---

## 3. plexus

### Identity

- What: capability discovery and auto-wiring for agent toolchains. Tools ship
  JSON interop manifests declaring emits/consumes; plexus derives the
  producer-to-consumer mesh, plans pipelines, routes between tools, renders
  mermaid/dot graphs, emits runnable pipeline scripts, and serves the mesh
  over stdio MCP (README.md; src\plexus\ 8 modules, 770 lines).
- Version: 0.2.0 on the checked-out branch feat/graph-run-compare
  (pyproject.toml); main is still 0.1.0 (`git show main:pyproject.toml`).
  The branch is 3 commits ahead of main (5e7b145 0.2.0, 555cfe9 manifest
  export, eceba69 MCP server), all pushed to origin, none merged. The MCP
  server, graph export, runner, COMPARISON.md, and the five committed
  manifests do not exist on main.
- Published where: GitHub only, https://github.com/HarperZ9/plexus.git. No
  tags local or remote. Not on PyPI: https://pypi.org/pypi/plexus-mesh/json
  returns HTTP 404 (checked 2026-07-09).

### Enterprise axes

- Docs: README.md is complete for the surface (problem, CLI walkthrough,
  manifest format with a worked example, grounding/honesty section, install,
  library API). COMPARISON.md is a genuinely honest positioning page vs
  MCP/LangGraph/Dagster/CrewAI including a "where plexus does not win" section.
  CHANGELOG.md covers 0.1.0 and 0.2.0. examples\tour.py exists and CI runs it.
  Missing: a formal interop.json schema document (the format is only shown by
  example in README lines 71-84), an MCP operator guide, API reference,
  SECURITY.md, CONTRIBUTING.md.
- Tests + CI: 31 tests ("falsifiers", per CHANGELOG line 21), green in 0.10s.
  CI matrix 3 OS x 3 Python plus wheel-install job running the packaged CLI
  (.github\workflows\ci.yml). No release.yml.
- Error handling/logging: single broad except at the MCP boundary with intent
  comment (src\plexus\mcp.py line 72). No logging module. The manifest
  validator exists (README line 38 lists `validate`; src\plexus\manifest.py).
- Versioning/changelog: CHANGELOG maintained; no tags, no releases, and the
  version split between main (0.1.0) and the feature branch (0.2.0) means the
  public default branch understates the tool.
- License: MIT (LICENSE, pyproject).
- Packaging: wheel builds in CI; nothing published.
- Security posture: no credentials anywhere in src\ (grep); .gitignore covers
  .env, *.key, *.token. plexus reads local JSON manifests and never touches
  the network, which is worth one SECURITY.md paragraph to state explicitly.
- File-size gate: all modules under 300 lines (largest registry.py at 170).

### The one missing user-facing feature vs MCP routers/meshes

No live MCP introspection. Today the mesh comes from two sources only: the
built-in registry of the five HarperZ9 flagships (src\plexus\registry.py) or
hand-authored *.interop.json files loaded from a directory
(src\plexus\manifest.py, README lines 67-69). Incumbent MCP
aggregator/routers (MetaMCP, mcp-router class tools) point at a user's
existing running MCP servers and enumerate their tools automatically
(moderate confidence, from model knowledge). A new user with zero HarperZ9
tools gets an empty mesh and a manifest-authoring chore before any value
appears. The missing feature: `plexus discover --mcp "<server cmd>"` that
spawns a stdio MCP server, calls tools/list, and synthesizes a manifest from
the tool schemas (emits from output descriptions, consumes from input
schemas), flagging synthesized edges as lower-evidence than authored ones.
That turns plexus from a demo over five sibling tools into a layer any MCP
user can point at their existing toolchain, which is the entire adoption
funnel.

### Quick wins (each under 1 hour)

1. Merge feat/graph-run-compare to main (3 pushed, green commits; the memory
   shard's "v0.2.0 MERGED to main" claim is wrong against git state, so this
   also corrects the record).
2. Copy mneme's release.yml and tag v0.2.0 after the merge.
3. Extract the interop.json format into a short SCHEMA.md (or a JSON Schema
   file) so third-party tools can author manifests without reading README
   prose.
4. Add SECURITY.md: local-only, no network, no secrets.
5. Add `plexus --version` output assertion to a test if not present (CI
   already smokes it, .github\workflows\ci.yml package job).

### Build order

- P0: merge the 0.2.0 branch to main, add release.yml, tag, and publish
  plexus-mesh to PyPI (name is free as of 2026-07-09). All content exists;
  this is assembly.
- P1: live MCP introspection (`discover --mcp`), the one feature that opens
  the mesh to non-flagship users.
- P1: interop.json schema doc plus a validating `plexus validate` example in
  README so external manifests are first-class.
- P2: SECURITY.md, CONTRIBUTING.md, a second executor target for
  pipeline_script (e.g. emit a LangGraph or Makefile skeleton) to make the
  "composes with executors" thesis in COMPARISON.md line 54 concrete.

---

## Summary table

| Axis | mneme | relay | plexus |
|---|---|---|---|
| Version (branch checked out) | 0.1.0 main | 0.1.0 feat/test-repair | 0.2.0 feat/graph-run-compare (main 0.1.0) |
| Tests (all green) | 82 | 53 | 31 |
| CI matrix + wheel job | yes | yes | yes |
| Release workflow | yes (gated) | no | no |
| Tag pushed | v0.1.0 | none | none |
| CHANGELOG | yes (stale counts) | no | yes |
| Examples | yes | no | yes |
| On PyPI | no (404) | blocked (name taken) | no (404) |
| License | MIT | MIT | MIT |
| SECURITY.md | no | no | no |
| Unmerged pushed work | 1 commit | 1 commit + 1 branch | 3 commits |
| Missing headline feature | shipped semantic embedder | interactive diff-review agent | live MCP introspection |
