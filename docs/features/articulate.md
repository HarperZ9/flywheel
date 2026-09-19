# Articulate (Flywheel native feature)

> Status note. Articulate ships today as a standalone repo and a PyPI package
> (`articulate-writing` 0.1.0). It is **not_integrated** into Flywheel: no lane
> registry entry, no desktop card, no expected-set test, and no admitted-tool
> manifest exist yet. Every claim in "What it is" and "Feature reference" below
> is observed from the repo source. Every claim under "How it composes" and
> "Wiring it needs" is **proposed** and carries that label.

## One sentence

Articulate is a local, standard-library prose screener that flags AI-writing
tells and plain-writing-standard violations, scores how machine-textured a
passage reads, and issues a re-derivable Match/Drift/Unverifiable receipt for
each screening.

## One paragraph

Articulate reads prose and reports the rhetorical devices and register tells
that make text read as machine-generated, under a register profile that decides
which findings block. The detector core runs with no third-party dependency and
no network call (`src/articulate/detector.py`, `dependencies = []` in
`pyproject.toml`). An optional editor layer (`judge`, `fix`, `polish`) reads
judgment-level failures and rewrites toward the standard when an LLM backend is
configured. Every screening can emit a receipt that pins the exact text hash and
a fingerprint of the whole ruleset, so anyone replays the verdict on the same
text with no trust in the issuer. Inside Flywheel, Articulate fits the same seam
Chorus uses: a bridge shells the installed CLI, returns the tool's own JSON
verbatim with its receipt, and reports an honest error when the CLI is absent.
The boundary is fixed. A clean gate means the prose was screened under a named
ruleset. It never asserts that a claim, a proof, or a result is correct.

---

## Feature reference (observed, code-bound)

Each item names the capability and the source that implements it.

### Detection

- **Three-tier deterministic detector.** `check_text` and `scan_lines` in
  `src/articulate/detector.py` classify findings HIGH (banned devices and named
  register words), MEDIUM (frontier-model register, stock transitions, marketing
  superlatives, participial closers, email and blog tells), and LOW (advisories
  that also fire on innocent prose, surfaced only with `--verbose`). Verified by
  `tests/test_detector.py`.
- **Keyword-free parallel-negation detection.** The detector flags a
  parallel-negation contrast pair by structure, without a keyword list
  (`detector.py`; `docs/features.md`).
- **Document-level signals.** Uniform cadence, repeated sentence openers,
  passive density, and adverb density accumulate as document-level evidence
  (`detector.py`, `tests/test_detector.py`).
- **Graded texture score.** Alongside the pass/fail gate, the detector emits a
  0-100 machine-texture score that accumulates weak evidence by density. The
  score grades and feeds the benchmark. It never changes the clean/flagged
  verdict (`detector.py`; `docs/features.md`).
- **Per-finding location.** Every finding carries a line, a column, and a
  character span, so an editor places a squiggle and a receipt pins the exact
  offset (`detector.py`, `tests/test_spans.py`).

### Register control

- **18 register profiles.** `src/articulate/profiles.py` `PROFILES` defines
  `flavored` (default), `procedure`, `error-message`, `commit`, `changelog`,
  `release-notes`, `api-docs`, `normative-spec`, `research`, `proof`,
  `model-card`, `readme`, `legal`, `journalism`, `social`, `chat`, `essay`,
  `narrative`. A profile sets which tiers block, a term-of-art allowlist, and
  provenance fields.
- **Three gate levels.** `GATE_TIERS` in `detector.py` maps `off` (blocks
  nothing), `flavored` (blocks HIGH), `strict` (blocks HIGH and MEDIUM). A
  profile selects one.
- **Profile resolution.** `profiles.resolve` picks a profile from an explicit
  `--profile`, an in-file `writing-profile:` tag, or the file path
  (`profiles.py` `PATH_RULES`).
- **29 writing modes.** `src/articulate/modes.py` crosses a domain register with
  an articulation need (for example `memo/argue`, `technical-docs/explain`,
  `academic/prove`). A mode is a base profile plus a delta of terms of art,
  categories to block, and editor guidance. `articulate modes` lists them.
- **6-genre axis.** `src/articulate/genres.py` `GENRES` reads narrative and
  expressive prose by its own convention: `literary-fiction`, `genre-fiction`,
  `ya-fiction`, `memoir`, `screenplay`, `poetry`. Under a fiction genre, quoted
  speech is masked out of the device passes, craft devices report without
  blocking, and a report-only lexicon flags generation artifacts. Screenplay
  classifies Fountain roles so only action lines face the gate. Poetry reads by
  the line. Verified by `tests/test_genres.py`.

### Science and mathematical writing

- **Proof and technical-exposition modes.** `academic/prove` and
  `science-writing/explain` (in `modes.py`) target hard exposition. The proof
  mode routes to `judge` and keeps `fix` opt-in, because a wrong change to a
  quantifier or an inequality changes a theorem. Verified by
  `tests/test_science.py`.
- **Math-span masking on `.tex`.** The editor masks every math span before a
  rewrite and splices it back byte for byte, so a formula is never altered
  (`src/articulate/editor.py`; `docs/features.md`).
- **Stated boundary.** A clean gate on a proof means the prose was screened. It
  says nothing about whether the theorem is true (`docs/boundaries.md`).

### Editor layer (needs an LLM backend)

- **`judge`.** Reports judgment-level failures a regex cannot see: confident
  emptiness, vague abstraction, uncommitted hedging, weak verbs, a buried point
  (`editor.py`, `tests/test_editor.py`).
- **`fix`.** Rewrites to the plain-writing standard, preserves every number,
  name, citation, term of art, and code span, then re-runs the detector until
  clean (`editor.py`).
- **`polish`.** A monotonic loop that accepts a pass only when the gate stays
  clean and no quality score drops. It scores five qualities: concreteness,
  commitment, economy, rhythm, and a restatable fact per paragraph
  (`editor.py`, `src/articulate/mcp_server.py` `do_polish`).
- **Injection trust boundary.** The document is treated strictly as data. A
  trust boundary is appended to every model call, so a directive embedded in the
  text is edited as content and never obeyed. Verified by
  `tests/test_injection.py`.
- **Backends.** The editor defaults to a local model where configured, or the
  `claude` CLI (`editor.py`; README).

### Receipts and audit

- **Re-derivable receipt.** `src/articulate/receipt.py` `make_receipt` records
  the text hash, a ruleset fingerprint (`detector.ruleset_fingerprint()`), the
  profile, the findings, and the gate. Schema `articulate/receipt/v1`.
- **Closed verdict set.** `verify_receipt` returns `Match` (same text, same
  ruleset, identical findings and gate), `Drift` (same text and ruleset,
  re-derived findings differ), or `Unverifiable` (ruleset moved, hash mismatch,
  unknown schema, or below the signal floor). There is no `Trusted` or
  `Approved` value (`receipt.py`, `tests/test_receipt.py`).
- **Content-free audit receipt.** `--redact drop` or `--redact hash` produces
  schema `articulate/receipt/audit/v1`, which keeps no verbatim matched
  substring and no offsets, only the rule, tier, category, and line. It still
  replays to `Match`, and `verify_receipt` rejects a receipt that smuggles a
  verbatim `match` field into an audit schema (`receipt.py`,
  `tests/test_audit_hardening.py`).
- **Local audit query.** `articulate audit <dir>` queries committed receipts
  with no server; `--reverify --gate` re-checks each against its source and
  fails only when a source drifted (`src/articulate/cli.py`,
  `tests/test_audit.py`, `tests/test_audit_cli.py`).
- **Reviewer attribution.** `--reviewer` records a named human sign-off; absent
  that, the CI actor from `$GITHUB_ACTOR` is recorded (`cli.py`, `receipt.py`).

### Calibration and safety

- **Per-span mixed authorship.** `--spans` scores each paragraph on its own and
  reports its line range, so one generated paragraph in a clean document is
  flagged in place (`detector.py` `analyze_blocks`/`segment_blocks`,
  `tests/test_spans.py`).
- **Sub-threshold abstention.** Below a 30-word floor a device-clean text reads
  `unverifiable`; the tool withholds a confident clean verdict there. A banned
  device still reads flagged at any length (`detector.py`,
  `tests/test_thresholds.py`).
- **Binary fail-closed guard.** A binary or unsupported document (`.docx`, PDF,
  image) is refused with an explicit reason, so the tool never returns a
  spurious clean scan of a lossy decode (`detector.binary_reason`,
  `tests/test_binary_guard.py`).
- **ReDoS guard.** Pattern safety is covered by `tests/test_redos.py`.
- **Dogfood gate.** `tests/test_dogfood.py` screens the project's own prose.

### Surfaces

- **CLI.** `articulate` console script (`cli.py:main`) with subcommands `check`,
  `score`, `receipt`, `verify`, `audit`, `modes`.
- **SARIF.** `check --sarif` emits SARIF 2.1.0 for GitHub code scanning, Azure
  DevOps, and reviewdog (`cli.py`).
- **LSP server.** `python -m articulate.lsp_server` (console script
  `articulate-lsp`) speaks LSP over stdio with no dependency, for VS Code,
  JetBrains via LSP4IJ, and Neovim (`src/articulate/lsp_server.py`,
  `tests/test_lsp.py`).
- **MCP server.** `python -m articulate.mcp_server` exposes five tools: `check`,
  `score`, `judge`, `fix`, `polish` (`mcp_server.py`). It needs the `mcp` extra
  (`fastmcp>=3`). `receipt`, `verify`, and `audit` are CLI-only and have no MCP
  tool.
- **GitHub Action and pre-commit.** `action.yml` and `.pre-commit-hooks.yaml`
  gate a change and re-verify committed receipts.
- **Benchmark.** `python -m articulate.bench` runs the detector over a labeled
  corpus (`corpus/ai`, `corpus/human`) and reports recall, specificity, and
  regressions. Exit code is the count of misclassified files, so CI gates on it
  (`src/articulate/bench.py`).

### Package facts

- Distribution `articulate-writing` 0.1.0, module `articulate`, license
  `LicenseRef-FSL-1.1-MIT`, Python `>=3.9`, core `dependencies = []`
  (`pyproject.toml`).
- Console scripts: `articulate` and `articulate-lsp`. Optional extras: `mcp`
  (`fastmcp>=3`) and `dev` (`pytest>=7`).

---

## Stepwise usage (how a user runs it)

Observed from the CLI and README. These run against the standalone package
today.

1. **Install.** `pip install articulate-writing`. For the agent surface,
   `pip install "articulate-writing[mcp]"`.
2. **Lint a file under its profile.** `python -m articulate.cli check
   path/to/doc.md --gate` exits 1 when the file is blocked under the profile the
   path or an in-file tag resolves. Add `--profile essay` or `--mode memo/argue`
   to force a register. Add `--verbose` to surface LOW advisories.
3. **Score a passage.** `echo "some prose" | python -m articulate.cli score`
   prints the 0-100 texture score with passive and adverb rates and cadence
   flags.
4. **Localize mixed authorship.** `check doc.md --spans` returns a verdict per
   paragraph with its line range.
5. **Issue a receipt.** `python -m articulate.cli receipt doc.md --profile
   research > doc.receipt.json` writes a re-derivable verdict.
6. **Replay a receipt.** `python -m articulate.cli verify doc.receipt.json
   doc.md` re-derives and exits 0 (Match), 1 (Drift), or 2 (Unverifiable).
7. **Keep a content-free record.** `receipt doc.md --redact drop --reviewer
   alice > receipts/doc.json` stores a replayable receipt with no verbatim text.
8. **Audit a directory.** `python -m articulate.cli audit receipts/ --reverify
   --gate` re-checks each committed receipt against its source and fails the gate
   if a source drifted.
9. **Wire CI.** `check "src/**/*.md" --sarif > articulate.sarif` for code
   scanning, or use `action.yml` / the pre-commit hook.
10. **Edit (needs a backend).** `judge`, `fix`, and `polish` read and rewrite
    prose when a local model or the `claude` CLI is configured.
11. **Editor squiggles.** Point an LSP client at `python -m
    articulate.lsp_server`.

---

## How it composes inside Flywheel (proposed)

Everything in this section is a proposal. None of it is wired today.

### Which seam it is

Flywheel has two integration shapes in the current code:

1. A **lane** declared in `harness/lanes_registry.py` `LANES`, spawned as an MCP
   server and reachable through `POST /api/lane/<name>/<tool>`
   (`harness/lane_call_route.py`, `harness/lane_caller.py`), gated by a
   governance tier and an exact grant.
2. A **satellite bridge**, the shape Chorus uses. `harness/chorus_bridge.py`
   shells the installed `chorus` CLI, returns its JSON digest verbatim with its
   receipt, and reports a named error when the CLI is missing. The gateway wires
   it at `/api/discourse*` and the desktop renders it in a Discourse card.
   Chorus is not in `LANES`.

Articulate needs both, for a concrete reason grounded in its code. The MCP
server exposes only `check`, `score`, `judge`, `fix`, `polish`. The
receipt-bearing surfaces (`receipt`, `verify`, `audit`, `--sarif`) live only in
the CLI. So the lane covers the five MCP tools, and a Chorus-style bridge
(`harness/articulate_bridge.py`, proposed) shells the CLI for the receipt path
that the MCP server does not carry.

Proposed lane identity: role `re-derivable prose screening and AI-tell
detection (register profiles, writing modes, receipts)`. Organ is an open
question. The existing `writing` lane holds `authoring` and `crucible` holds
`verification`. Articulate screens and verifies prose, so `verification` is the
closest existing family; a distinct `expression` organ is the alternative. The
operator makes this naming decision, and it stays open.

### What it consumes from peers

- A document or a text span. Sources in the workspace: a file, the `writing`
  lane's private author workspace (`harness/writing_mcp`), a row from a `gather`
  corpus (`gather` lane, organ perception), or the output a `relay` run produced
  before commit.
- A profile or mode selection, or the file path that resolves one.
- For `fix`/`polish`, an LLM backend the host already runs (a local model, or
  the `claude` CLI).

### What it emits for peers

- A verdict (`clean`/`flagged`) with the 0-100 texture score and per-finding
  locations, which the desktop Lint or editor surface renders as squiggles.
- Per-span verdicts for mixed-authorship localization.
- A re-derivable receipt (`articulate/receipt/v1`) or a content-free audit
  receipt (`articulate/receipt/audit/v1`) that a witnessed ledger such as
  `forum` can record and a stranger can replay.
- SARIF for a CI gate.

### Short worked example: gather to articulate to forum

This mirrors the Chorus path, which reads a `gather` corpus. Proposed flow:

1. `gather` pulls a corpus of external prose and writes it as a corpus
   directory with provenance receipts (observed: `gather` lane, organ
   perception).
2. A proposed `POST /api/prose/screen` calls the proposed
   `harness/articulate_bridge.py`. The bridge shells `articulate receipt <row>
   --profile research --redact drop` for each corpus row and returns the audit
   receipt verbatim, or a named error when the CLI is absent. This is the exact
   pattern of `chorus_bridge.discourse_digest`, which runs `chorus run <corpus>
   --verify` and returns the digest with its `verified` flag.
3. `forum` records each screening in its witnessed causal ledger (observed:
   `forum` lane, organ orchestration). A reviewer later replays any receipt with
   `articulate verify` and confirms Match without trusting the issuer.

A second useful flow, gate-on-commit: a `relay` run produces a README, `check
--profile readme --gate` blocks the commit when the prose is flagged, and the
receipt is committed beside the file for later audit.

---

## Wiring it needs to become a native lane (proposed, modeled on Chorus)

Articulate is **not_integrated**. Four pieces of wiring are missing. Each is
modeled on an existing, code-verified pattern.

### 1. Lane registry entry

Add one `Lane` to `LANES` in `harness/lanes_registry.py`. The
install-name-to-command asymmetry and the `python -m` module entry follow the
existing rows (for example `index` installs as `index-graph` and runs as
`index`). Articulate diverges in one way that must be stated: its console script
is `articulate`, and it has no `articulate mcp` subcommand, so the MCP launch uses
the module entry. Pip lanes like `gather` reach their MCP server through the
console-script-plus-`mcp` convention that Articulate lacks.

Proposed entry (illustrative, not committed):

```python
"articulate": Lane(
    "articulate", "articulate-writing", "python",
    ("-m", "articulate.mcp_server"), "pip", "0.1.0",
    "re-derivable prose screening and AI-tell detection "
    "(register profiles, writing modes, receipts)",
    "verification", source_repo="public/articulate",
    py_module="articulate.mcp_server"),
```

Two accuracy notes. The MCP surface needs the `mcp` extra, so the install target
is `articulate-writing[mcp]`, which the install path
(`harness/lanes.py` `install_lane`) would need to express. The `source_repo`
value `public/articulate` assumes the repo sits beside the other `public/*`
checkouts that `resolve_source_repo` walks; the repo is not at that path today,
so either it moves there or the resolver convention accommodates its current
location. An alternative that matches the pip-lane convention is to add an
`articulate mcp` subcommand to `cli.py`, then declare `command="articulate",
mcp_args=("mcp",)`.

### 2. Desktop app card

Add a destination, following the Discourse card. The steps, each grounded in the
current desktop code:

- Add an id to the `DestinationId` enum in
  `desktop/lib/navigation/app_route.dart` (the enum already carries `discourse`,
  `lint`, `writing`).
- Add a `DestinationSpec` to `destinationCatalog` in
  `desktop/lib/navigation/destination_catalog.dart` with a label, a two-letter
  abbreviation, and a group (`DestinationGroup.code` alongside `lint`, or
  `evidence` alongside `receipts`).
- Wire the id to a view in `desktop/lib/shell/view_factory.dart`, the way
  `DestinationId.discourse => DiscourseView(...)` is wired.
- Add the view and its model, modeled on `desktop/lib/views/discourse_view.dart`
  and `desktop/lib/models/discourse.dart`, parsing defensively so a missing
  field degrades and Drift stays visible (per `desktop/CLAUDE.md`).

Note: `desktop/lib/models/callable_lane.dart` already renders any lane the
engine names in the Lanes destination, so a registry entry alone makes Articulate
appear in the Lanes roster with its tier. A dedicated card is the richer,
verdict-rendering surface.

### 3. Expected-set test

`tests/test_lanes.py::test_registry_covers_the_expected_lanes` asserts the exact
set of lane names. Adding a lane makes that test the tripwire: the set literal
gains `"articulate"`, or the test fails. Extend it, and add lane-specific
falsifiers alongside the existing ones:

- `test_install_name_to_command_asymmetry_is_mapped` gains
  `LANES["articulate"].install_name == "articulate-writing"` and
  `LANES["articulate"].command == "python"`.
- `test_public_commands_are_portable_declared_argv` gains
  `resolve_mcp_command("articulate") == ["python", "-m",
  "articulate.mcp_server"]`.
- A bridge test modeled on the Chorus bridge covers the CLI-absent path: an
  injected `runner` stands in for the CLI so the seam is testable in CI where the
  package is not installed (see the `runner=None` seam in
  `chorus_bridge.discourse_digest`).

### 4. Payload manifest (admitted-tool set plus a seam fixture)

Two parts, both with existing precedent.

- **Admitted-tool set.** A lane launch admits tools through
  `LaunchSpec.allowed_tools` (`harness/mcp_client.py` `launch_allows_tool`); a
  tool outside the set returns `CAPABILITY_NOT_ADMITTED`. The proposed admitted
  set for Articulate is `("check", "score")` for a default, backend-free
  deployment, widening to include `("judge", "fix", "polish")` only where an LLM
  backend is configured, because those three fail without one. The governance
  tier is proposed T1: the tools take text in and return text out with no
  filesystem or network side effect, unlike the T2 actuation lane
  `accountable-surface`.
- **Seam fixture.** A recorded call-and-response fixture proves the seam without
  spawning a server, following `tests/fixtures/e2e/gather_context/*.json` and
  the `_ProbeClient` pattern in `tests/test_lanes.py`. It records a `check`
  request and the verdict-bearing response, plus a `receipt` request routed
  through the proposed bridge and the returned `articulate/receipt/v1` payload.

### Gateway route (implied, proposed)

The bridge needs a gateway endpoint, modeled on the Chorus rows in
`harness/gateway.py` (`/api/discourse`, `/api/discourse/corpora`,
`/api/discourse/digests`). A proposed `/api/prose/screen` and
`/api/prose/verify` would call `harness/articulate_bridge.py` and return the
CLI's JSON verbatim, with a 400 when the payload carries an `error`.

---

## Boundaries carried into Flywheel (observed, from `docs/boundaries.md`)

- Detection and writing quality are the goal. A lower detector score is a
  byproduct of clearer writing, never a target. Articulate is not an evasion
  tool, and the benchmark refuses to report a detector-evasion result as a
  feature.
- Exposition quality is not correctness. A clean gate on a proof or a paper says
  the prose was screened. Correctness comes from referees and proof assistants
  (Lean, Coq, Isabelle), never from this tool.
- A receipt attests that a screening ran. It carries no claim about compliance,
  and it does not stand in for a provenance attestation, an EU AI Act Article 50
  marking, or a C2PA credential.
- Content-free is not zero-leakage. The residual is the rule and the line. For a
  closed-vocabulary rule that narrows the flagged word to a small public
  candidate set. `--redact hash` keeps a dictionary-reversible sha256; use
  `--redact drop` when the flagged word must stay secret.
- English patterns and an honest ceiling. The patterns are English literals, so
  a clean result on non-English text means the English rules found nothing. The
  detector reads devices, register, and structure with regular expressions; it
  cannot read token probability, so a device-clean passage of machine writing
  can score low.

## Honest nulls

- Articulate is not wired into Flywheel. No lane entry, desktop card,
  expected-set test, bridge, or gateway route exists yet.
- The MCP server carries no `receipt`, `verify`, or `audit` tool; those are
  CLI-only, so the proposal pairs a bridge with a lane to reach them.
- The organ assignment (`verification` versus a new `expression`) is unresolved.
- The `source_repo` path convention for a lane assumes a `public/articulate`
  checkout location the repo does not occupy today.
- An offline editor backend and a labeled non-native corpus for a fairness check
  remain on the standalone repo's own roadmap (README "Status").