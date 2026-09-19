# Gather (Flywheel lane: perception)

> Native-feature documentation for the `gather` lane as it lives inside Flywheel.
> Scope note: statements are marked observed (read from code in `public/gather`
> and `public/flywheel/harness`) or proposed (a change not yet in the code).
> Version claims track gather `1.6.1` and the lane registry entry at that version.

## One sentence

Gather is Flywheel's perception lane: it pulls research material out of the
sources most tools break on (gated APIs, paywalls, JavaScript-walled pages,
scanned PDFs, audio, arXiv, feeds, local docs) and hands the rest of the
platform a witnessed digest where every item records how it was obtained.

## One paragraph

Inside Flywheel, gather is the afferent organ. Its job is to bring information
in and record provenance before any downstream lane reasons over it. Each kind
of intake sits behind one `Source` shape (a string in, a list of receipted
`Item`s out), so awkward access is an adapter problem rather than a platform
problem. Every `Item` carries a `Provenance` receipt with a `method` field that
is mechanically enforced: a fetch cannot be relabelled an inference and an
inference cannot pose as a quote. A run folds its items' receipts into a
`Digest` with a re-checkable seal, and that seal is the contract downstream
lanes consume. Gather is registered as the `gather` lane in
`harness/lanes_registry.py` (organ `perception`), reachable over MCP stdio with
seven tools, and it is the intake half of the research bench that pairs with the
`crucible` verification lane. The core is pure standard library with zero
third-party runtime dependencies; capability backends (`fast`, `browser`,
`stealth`) are opt-in edges, and a missing edge is reported as UNVERIFIABLE, not
faked. Observed.

## Feature list (each bound to code)

- **One-shape source adapters.** Every intake kind is a `Source` protocol
  implementation (`gather.source.Source`): `video`, `web`, `feed`, `docs`,
  `arxiv`, `pdf`, `api`, `browser`, `ocr`, `transcribe`. The last five are
  isolated external-tool edges (an external program does the work, never a
  Python dependency). Observed: `src/gather/source.py`, `ARCHITECTURE.md`.
- **Mechanically enforced method ladder.** `make_item` refuses an inconsistent
  receipt: a `direct` item cannot carry `derived_from`, a `derived` item cannot
  lack it. Observed: `src/gather/item.py`, `src/gather/method.py`.
- **Witnessed, re-checkable digest.** `digest` folds item receipts into a
  `Digest` with an order-independent `seal` covering every receipt field;
  `verify_digest` re-derives it and returns False if anything was altered.
  Observed: `src/gather/digest.py`.
- **Extract any page to LLM-ready Markdown with a per-block receipt.**
  `gather extract` binds every Markdown block to its source node path and
  content hash; `gather markdown` prints the Markdown alone. Observed:
  `src/gather/extract.py`, `src/gather/cli.py`.
- **Resumable, hash-chained crawl.** `gather crawl <url> --depth N --max-pages M`
  emits an append-only, hash-chained crawl ledger as JSON, with robots.txt,
  sitemap discovery, dedup, and per-host throttling. Observed:
  `src/gather/crawl.py`.
- **Structured extraction with a hallucination check.** `schema_extract` binds
  schema fields to source nodes; `verify_record` rejects any proposed field
  value not grounded in the fetched content. Observed:
  `src/gather/schema_extract.py`, `src/gather/run.py`.
- **Element tracking across page redesigns.** Fingerprint a scraped element and
  relocate it in a later version of the page, returning a typed MATCH /
  RELOCATED / DRIFT / GONE verdict. Observed: `src/gather/track.py`.
- **Scholarly-graph federation.** `gather scholar` queries OpenAlex, Semantic
  Scholar, and Crossref, dedupes by normalized DOI (never a fuzzy title match),
  and captures citation edges with `--edges`. Observed: `src/gather/scholar.py`.
- **Source-federation planning, offline.** `gather federation validate | plan |
  policy | entity` audits a closed-contract registry, compiles one deterministic
  capture plan per source, and seals the snapshot; no probe fires. A registry
  row is never reported as coverage or availability. Observed:
  `src/gather/federation.py`, `src/gather/federation_cmd.py`.
- **Durable content-addressed corpus.** `--store DIR` writes bodies at
  `objects/ab/cdef...` keyed by sha256 (natural dedup, temp-then-rename,
  fsync), with an append-only `catalog.jsonl` of one row per distinct receipt.
  `gather corpus list | verify | digest | runs | search | stats | prune |
  availability` inspects and re-checks it. Observed: `src/gather/store.py`,
  `src/gather/corpus_cmd.py`.
- **Availability rung.** `witness_availability` attaches `{status, checked_at,
  sha256}` to each receipt and folds it into the seal; `assess_availability`
  reports AVAILABLE only when the bound hash matches, else CHANGED /
  UNAVAILABLE / UNWITNESSED. Observed: `src/gather/availability.py`.
- **Witnessed multi-source run.** `gather run config.json` orchestrates many
  `(source, target)` jobs, a scope filter, and optional synthesis into one
  `RunRecord` with its own seal, re-checkable from disk. The clock is injected,
  so replay is deterministic. Observed: `src/gather/run.py`,
  `src/gather/run_config.py`.
- **Accountable pilot evidence engine.** `gather pilot run | refresh | verify |
  bundle` drives a closed manifest through source-isolated capture into a
  content-addressed corpus, writes a redacted report plus a hash-chained
  receipt, monitors sources for NEW / CHANGED / UNCHANGED, and packages shared
  or full bundles a third party re-verifies offline. Observed: `src/gather/pilot.py`,
  `src/gather/pilot_bundle.py`, `docs/PILOT.md`.
- **Credential discipline.** Secrets enter only through `require_secret(name)`,
  read from the environment by name, never logged, never written into a receipt
  or URL. Observed: `src/gather/credentials.py`.
- **SSRF-aware network edge.** `http_get` allows only http/https, blocks
  private, loopback, link-local, and reserved hosts on the initial URL and on
  every redirect hop, refuses caller-supplied routing headers, and strips
  credentials on a cross-origin redirect. Observed: `src/gather/net.py`.
- **Three surfaces, one engine.** CLI (`gather`), MCP stdio (`gather mcp`, seven
  tools), and a plain Python API re-exporting the stable seams from
  `gather/__init__.py`. Observed.
- **Zero-dependency core, opt-in backends.** `dependencies = []` in
  `pyproject.toml`; `fast` (lxml), `browser` (Playwright), `stealth`
  (curl_cffi) are extras. `gather caps` reports what the install can actually
  do; a missing capability degrades to UNVERIFIABLE. Observed: `pyproject.toml`,
  `src/gather/backends.py`.

Honest null: the README's "roughly 2x on large documents" for the `fast` backend
is described in the repo itself as informal and unpublished. Treat it as
unverified, not a benchmark.

## Stepwise usage (how a user runs it)

Gather runs the same three ways whether or not Flywheel is present.

1. **Install.**
   ```bash
   pip install gather-engine        # installs the `gather` command and `import gather`
   ```
   Or from a source checkout: `python -m pip install -e ".[dev]"`. Python 3.11+.
   From a checkout without install, `python -m gather` runs the same CLI.

2. **Check what the install can do.**
   ```bash
   gather caps                      # fast / browser / stealth capability report
   gather status --json             # Project Telos operator-spine status envelope
   gather doctor --json             # operator-spine readiness checks
   ```

3. **Extract one page to Markdown with a per-block receipt.**
   ```bash
   gather extract https://example.com/article
   ```
   The JSON output carries `blocks` (each with `path`, `sha256`, `tag`),
   `content_sha256`, `markdown_sha256`, `method`, and `url`.

4. **Build a mixed-source corpus and re-check it.**
   ```bash
   gather web  "https://example.com/article" --store ./corpus
   gather arxiv "2301.12345"                 --store ./corpus
   gather docs ./notes --scope "monotile,tiling" --store ./corpus
   gather corpus list   ./corpus             # every item with source, method, hash
   gather corpus verify ./corpus             # re-hash every body; non-zero exit on corruption
   ```

5. **Run a witnessed multi-source session.**
   ```bash
   gather run config.json                    # many sources, scope filter, optional synthesis
   ```

6. **Drive a pilot when the evidence must survive an offline re-check.**
   ```bash
   gather pilot run MANIFEST --output DIR     # capture once, write report + receipt
   gather pilot verify DIR                    # network-free verification of the whole root
   gather pilot bundle DIR --output FILE --visibility shared
   ```
   Exit codes: manifest refusal exits `2`; a required-source failure or a
   verification failure exits `1`; success exits `0`.

7. **Serve the lane to a host over MCP.**
   ```bash
   gather mcp
   ```
   Inside Flywheel this launch is what the lane layer spawns; a user rarely runs
   it by hand.

## Piecewise reference (each capability, what it does)

### CLI verbs
Observed in `src/gather/cli.py` (two subparser groups: operator-spine and data).

- **Operator spine:** `status`, `doctor`, `demo`, `corpus` (with actions
  `list | verify | digest | runs | search | stats | prune | availability`),
  `federation` (with actions `validate | plan | policy | entity`).
- **Data verbs:** `parse` (offline yt-dlp info.json), `video`, `web`, `feed`,
  `docs`, `arxiv`, `scholar`, `pdf`, `api`, `browser`, `ocr`, `transcribe`,
  `run`, `caps`, `extract`, `markdown`, `crawl`, `monitor`, `mcp`, `pilot`.

Each data verb prints a receipt as JSON. Any fetch verb accepts `--store DIR`
to write into a corpus.

### MCP tools
Seven tools, observed in `src/gather/mcp.py` and declared in
`src/gather/flagship.py`:

- `gather.status` — Project Telos flagship-action status envelope.
- `gather.doctor` — readiness checks (zero-dependency core, JSON receipts,
  offline docs intake, pilot engine).
- `gather.docs` — read a local file or directory of text, offline.
- `gather.arxiv` — fetch papers from the arXiv API by id or query.
- `gather.federation` — validate a registry or compile capture plans, offline.
- `gather.run` — run a multi-source session from an inline or file config.
- `gather.pilot` — run / refresh / verify / bundle a pilot evidence root.

### Python API
Stable seams re-exported from `gather/__init__.py`: `make_item`, `Item`,
`Provenance`, `content_hash`, `Corpus`, `Digest`, `digest`, `digest_of_receipts`,
`verify_digest`, `gather_run`, `RunRecord`, `verify_record`, `recall`,
`recall_audited`, `Query`, `Source`, `Catalog`, `filter_scope`, `in_scope`,
`derive`, `synthesize_item`, `Synthesizer`, `NullSynthesizer`,
`witness_availability`, `assess_availability`, `stored_probe`,
`ProvenanceProvider`, `NullProvenanceProvider`.

### Composition seams (default to Null so gather stands alone)
Observed in `ARCHITECTURE.md` and the modules named:

- **Synthesizer** (`gather.derive`) — a real model plugs in behind this seam to
  produce a `synthesized` item; the default `NullSynthesizer` performs a
  deterministic extractive compilation and invents nothing.
- **ProvenanceProvider** (`gather.provenance`) — an external origin verdict
  (forged / re-encoded / authentic) folds into a run's sealed `origins` field.
- **Scope filter and store** (`gather.scope`, `gather.store`) — pluggable, Null
  by default.
- **Availability probe** (`gather.availability`) — the default reads the
  corpus's own object store; a live re-fetch probe plugs into the same seam.

## Composition tutorial: gather inside the application

### Which lane it is
Gather is the `perception` organ in the lane layer. Observed in
`harness/lanes_registry.py`:

```python
"gather": Lane(
    "gather", "gather-engine", "gather", ("mcp",), "pip", "1.6.1",
    "research intake + provenance receipts (verified-data flywheel intake)",
    "perception", source_repo="public/gather", py_module="gather.cli"),
```

It is the first entry in the flagship spine (`SPINE` in `harness/gateway.py`) and
the intake half of the research bench, paired with the `crucible` verification
lane. The distribution name `gather-engine` maps to the `gather` command; the
lane layer resolves this asymmetry when it spawns the MCP server. Observed:
`harness/lanes.py`, `tests/test_lanes.py`.

### What it consumes from peers
- **Targets from the operator or a federation registry:** URLs, local paths,
  arXiv ids, run configs, and pilot manifests. A federation registry row is a
  catalog fact, never treated as coverage until a capture runs.
- **A Synthesizer, when one is wired:** a model behind the `Synthesizer` seam can
  turn gathered items into a `synthesized` item. Absent one, gather compiles
  deterministically and labels the result `compiled`.
- **A ProvenanceProvider, when one is wired:** an external origin verdict folds
  into the run's sealed `origins`.

### What it emits for peers
- **A witnessed `Digest` seal** that downstream lanes re-check. This is the
  contract `index`, `crucible`, and `refine` consume (stated in
  `ARCHITECTURE.md` and `gather/__init__.py`).
- **A durable corpus** other lanes read through `recall` / `recall_audited`,
  which re-verify each body before returning it.
- **Flagship next-actions** that route the platform onward. Observed in
  `src/gather/flagship.py`: status points to `index map` ("map workspace context
  for gathered sources"), doctor points to `crucible assess` ("verify repeated
  claims from gathered sources"), demo points to `forum route`.

### Where gather is already wired into Flywheel
Observed in `public/flywheel/harness`:

- **Intake to build candidates** (`intake.py`): loads a gather-style catalog,
  ranks it through the scout, and turns the top threads into falsifier-gated
  build candidates, with a content-addressed digest over the ingested feed.
- **Cross-domain live feeds** (`live_feeds.py`): shells `gather feed <url>
  --json` so every roster item carries gather provenance; a dead feed is a named
  error, not a fake heartbeat. Surfaced at the gateway `/api/feeds`.
- **Discourse over a gather corpus** (`chorus_bridge.py`): the `chorus` satellite
  reads a gather corpus and returns a weighted, clustered discourse digest with
  its own receipt. Surfaced at `/api/discourse`, `/api/discourse/corpora`, and
  `/api/discourse/digests`. Note: `chorus` is integrated as a shelled satellite
  over a gather corpus, not as a registry lane, so it is a contrast to gather's
  full lane registration rather than a template gather still needs to follow.
- **Source-context routing** (`source_context_route.py`, `source_context_gather.py`):
  a `GatherPathAdapter` is meant to call gather's corpus inspection while
  Flywheel holds retained-root authority. See the integration gap below.
- **Desktop card** (`desktop/lib/models/lane_identity.dart`): gather has a
  presentation identity (title `Gather`, surface "research corpus + federation"),
  and the Science and Discourse and Feeds desktop views render gather-sourced
  material.

### Worked example: gather to crucible, both native lanes
Goal: gather a body of sources with provenance, then let the verification lane
re-check a repeated claim without trusting gather's word for it.

```bash
# 1. Perception lane: capture a mixed corpus with a sealed run record.
gather run study.json --store ./corpus
#    study.json lists several (source, target) jobs and a scope; the run emits
#    a RunRecord whose seal covers every item receipt.

# 2. Confirm nothing drifted before anyone reasons over it.
gather corpus verify ./corpus          # MATCH per body, non-zero exit on corruption

# 3. Pull a scoped, re-verified subset for the claim under test.
gather corpus search ./corpus --terms "aperiodic tiling" --method http-get --json
```

The contract handed across the seam is the content hash on each receipt and the
digest seal over the run. The verification lane (`crucible`) consumes those
claims and re-checks them; because each claim is bound to the hash of what
gather actually fetched, a claim that was never grounded in the corpus fails
closed rather than passing on reputation. The flagship envelope makes this
routing explicit: gather's `doctor` next-action is `crucible assess`, "verify
repeated claims from gathered sources." Observed: `src/gather/flagship.py`,
`src/gather/corpus_cmd.py`, `src/gather/recall.py`.

For a discourse-shaped question instead of a claim, the same corpus feeds the
`chorus` satellite through `/api/discourse`, which returns a themed digest with
its own re-runnable receipt. Observed: `harness/chorus_bridge.py`.

## Native-lane wiring status (modeled on the chorus registration question)

Gather is already a native lane, so most of the wiring the question asks about
exists. Present and verified:

- **Lane registry entry** — `LANES["gather"]` in `harness/lanes_registry.py`,
  organ `perception`, version `1.6.1`, `py_module="gather.cli"`,
  `source_repo="public/gather"`.
- **Expected-set test** — `tests/test_lanes.py::test_registry_covers_the_expected_lanes`
  asserts `gather` is in the lane set, and
  `test_install_name_to_command_asymmetry_is_mapped` pins `gather-engine` to the
  `gather` command.
- **Desktop app card** — `laneIdentities['gather']` in
  `desktop/lib/models/lane_identity.dart`.
- **Readiness receipt** — `scripts/run_gather_readiness.py` with
  `tests/test_gather_readiness.py`, producing `harness.gather-readiness/v1`.

What is still missing or in flight (proposed work, not present on the working
checkout's main):

- **`gather.context` module.** `harness/source_context_gather.py` imports
  `inspect_corpus`, `select_context`, `CorpusRootDescriptor`, and
  `CorpusRootIdentity` from `gather.context`, and that module does not exist in
  gather `1.6.1`. The descriptor path therefore raises
  `SOURCE_CONTEXT_GATHER_UNAVAILABLE` (mapped to HTTP 503 in
  `source_context_route.py`). Proposed fix: either ship `gather.context`
  exposing those four names, or repoint the adapter at seams gather does export
  (`gather.recall`, `gather.store`, `gather.run`).
- **Payload manifest pin.** `packaging/python-lane-payloads.jsonl` and its
  checker `scripts/check_python_lane_payload_manifest.py` are present only in a
  Codex worktree, not on the flywheel main checkout. The checker's
  `EXPECTED_LANES` lists `gather`, so once that manifest lands, gather needs a
  source-pin row (`sha256-canonical-source-manifest/v1`). Until then gather has
  no landed payload pin.
- **Version lockstep.** The `1.6.1` string in `lanes_registry.py` is a
  hand-maintained constant. It must be bumped in the same change as gather's
  `pyproject.toml` version, or `lane_status` reports STALE against the installed
  package.

## Boundary

Gather may collect material from live sources, but outward-facing receipts
prefer source references, content hashes, timestamps, and verdicts. Raw private
payloads, secrets, credentials, and material whose license or privacy posture
forbids redistribution stay in the local adapters and never reach a published
receipt or bundle. The `browser` adapter is the most exposed edge: its host
guard covers only the first navigation, so it is not pointed at untrusted URLs
in an environment with reachable internal services. Observed: `USAGE.md`,
`ARCHITECTURE.md`, `src/gather/net.py`.

Independent-project note: gather is its own repository (`gather-engine` on PyPI,
`public/gather` in the workspace) with its own tests and release cadence. It
composes with Flywheel through clean protocol seams; it does not absorb the
platform and is not absorbed by it.