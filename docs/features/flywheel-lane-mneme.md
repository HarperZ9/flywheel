# Mneme (Flywheel memory lane)

## What it is

Mneme is Flywheel's memory lane: a local, zero-runtime-dependency SQLite memory library that layers agent conversation into turns, atoms, scenarios, and a persona, retrieves with BM25 plus an optional vector channel, and attaches a re-checkable receipt to every stored memory, every recall, and every deletion.

Mneme fills the `memory` role in the Flywheel lane layer. It records raw turns, extracts atomic facts from them, clusters those facts into scenario blocks, and synthesizes a persona, with each layer citing the sources beneath it. Retrieval fuses a pure-Python BM25 ranker with an optional embedding channel by Reciprocal Rank Fusion, and each recall returns a receipt that a third party re-runs to reproduce the ranking. Every stored memory snapshots the content hash of its sources at extraction time, so a drift check re-reads the current store and reports whether each grounding still holds. Deletions and edits land in a hash-chained audit log, so a forget is itself checkable. The deterministic floor runs with no model and no network call. An embedding model or an LLM extractor plugs in as an optional edge, and neither is required.

## How it lives inside Flywheel

Flywheel treats each engine as a lane with a declared role. Mneme is declared in `harness/lanes_registry.py` under the key `mneme`:

- Role: `memory`. Lane summary: "accountable memory: recall with re-derivable ranking receipts + drift verdicts".
- Organ field: `mneme`. Install name: `mneme-memory`. Command: `mneme`. MCP args: `("mcp",)`. Kind: `pip`. Version: `0.2.0`.
- Source repo: `public/mneme`. Python module entry: `mneme.cli`.
- `package_disabled_reason` is set: the PyPI name belongs to a different project, so inside Flywheel the pip-install argv is withheld and the lane runs from a HarperZ9 Mneme source checkout. `resolve_mcp_command("mneme")` returns an empty argv for that reason, and the runtime resolver launches the lane from the checked-out source.

The lane advertises its wiring in `mneme.interop.json` at the repo root, which names the invoke surfaces (`cli: mneme`, `mcp_server: mneme.mcp:serve`, `python_import: mneme`) and lists what the lane emits and consumes. The Flywheel application also lists `mneme` in the platform spine tuple in `harness/gateway.py` and in the lesson-source set in `harness/lesson.py`.

Version note: the lane registry and `pyproject.toml` both pin `0.2.0` (moderate confidence). `CHANGELOG.md` still headers an earlier `0.1.0 (unreleased)` entry, so the changelog lags the manifest.

Distribution facts, from `pyproject.toml`:

- Package name `mneme-memory`, version `0.2.0`, `requires-python >= 3.11`.
- `dependencies = []`. The only runtime import is the standard-library `sqlite3`. `pytest` is the sole declared test dependency.
- License `LicenseRef-FSL-1.1-MIT` (fair-source: readable and runnable, commercial use reserved). This is an independent project; it does not depend on the other lanes to run.

## Feature list

Each feature is bound to the module that implements it. Paths are relative to the Mneme repo root.

1. **Four-tier layered memory.** L0 turns, L1 atoms, L2 scenarios, L3 persona, stored in one SQLite database. Tables and DDL: `src/mneme/schema.py` (`SCHEMA_VERSION = "4"`, tables `turns`, `memories`, `meta`, `audit`). Storage wrapper: `src/mneme/store.py` (`LAYERS = ("L0","L1","L2","L3")`).

2. **Deterministic rule extraction (L0 to L1).** `src/mneme/extract.py` `RuleExtractor` (name `rule/v1`) pulls fact-shaped sentences from user turns using first-person and preference cues, deduplicated in stable order. The same turns yield the same atoms. An `Extractor` protocol lets a different extractor be injected.

3. **Optional LLM extractor edge.** `src/mneme/llm_extract.py` supplies a pluggable extractor for richer atoms. It is an optional edge over the deterministic floor, which keeps working on its own.

4. **Hybrid retrieval.** `src/mneme/recall.py` runs Okapi BM25 (pure Python, `k1=1.5`, `b=0.75`) and an optional cosine vector channel, fused by Reciprocal Rank Fusion (`rrf_k=60`). Strategies: `keyword`, `vector`, `hybrid`. Ties break by memory id, so the ranking is stable. With no embedder present, `hybrid` falls back to keyword and the receipt records the fallback.

5. **Zero-dependency local vector channel.** `src/mneme/embed.py` `NgramEmbedder` (`dim=256`, `n=3`) builds a character n-gram frequency vector hashed into fixed buckets, enabled with `embed="ngram"`. The module states its scope: this is fuzzy lexical-similarity matching. It will not link "car" and "automobile"; a real embedding model plugs in as an edge for semantic matching.

6. **Re-derivable recall receipt.** `src/mneme/receipt.py` `RecallReceipt` (schema `mneme.recall/1`) carries the ranked hits, each with bm25, vector, recency, and fused scores, the exact fusion rule, the corpus size, and a `def_sha256` that binds the scorer definition. `verify_recall` (`src/mneme/recall.py`) re-runs the same scorer over the supplied rows and confirms the ranking is reproduced. A tampered ranking fails even when its `def_sha256` is left matching, because the check re-derives the ranking from the rows themselves. A store that changed no longer reproduces.

7. **Recency-weighted recall.** `recall(..., recency_weight>0)` adds a scale-free recency channel (RRF over the `ord` counter, newest first) scaled by the weight. The recency component rides each hit and the rule is written into the receipt, so the ranking stays reproducible.

8. **Provenance receipt per memory.** `src/mneme/receipt.py` `ProvenanceReceipt` names the source ids, the extractor, the criterion, and a content hash over text plus sources plus criterion. `src/mneme/store.py` `add_memory` snapshots each source's content hash at write time, so a later change to a source is detectable.

9. **Self-flagging drift.** `src/mneme/drift.py` `check_memory` and `drift_report` (schema `mneme.drift-report/1`) re-read each memory's grounding and return `MATCH`, `DRIFT`, or `UNVERIFIABLE`. The check re-hashes the source's actual fields, so a direct SQLite edit that leaves a stale stored hash is caught. It fails closed: a memory with no verifiable source verdicts `UNVERIFIABLE`. The overall verdict folds to `DRIFT` if any memory drifted, else `UNVERIFIABLE` if any is unverifiable, else `MATCH`. The CLI exit code is 0 for `MATCH` and 1 for any other overall verdict.

10. **Accountable forgetting and editing.** `src/mneme/store.py` `forget` and `update` leave a tombstone in an append-only, hash-chained audit log (schema `mneme.audit/1` via `memory.audit()`). `verify_audit` re-derives the chain and checks it still ends at the committed head anchor (count plus last entry hash), so a deleted, edited, reordered, or truncated tombstone breaks the chain.

11. **Temporal memory.** `src/mneme/temporal.py` and `src/mneme/store.py` keep a changed fact with a validity window. `supersede` closes the old memory's validity and keeps it for history; `forget` erases the text for GDPR-style deletion and keeps only a tombstone. `history` returns the ordered timeline; `recall(as_of=N)` reconstructs the memory state at ordinal `N`. When an unscoped history spans more than one tenant, the scalar `current` and `transitions` are withheld as null, because a single-subject answer cannot span tenants.

12. **Multi-user and multi-session isolation.** The `memories` table carries a `user` column. `add_memory` refuses a cross-tenant overwrite and refuses a same-id write with different content (that routes through `update`). `recall(user=..., session=...)` scopes retrieval; `user=X, session=None` recalls across one tenant's sessions. Consolidation, persona, scenarios, and the entity graph partition by tenant even when the read is unscoped.

13. **Consolidation.** `src/mneme/consolidate.py` (schema `mneme.consolidation/1`) merges near-duplicate atoms above a Jaccard overlap threshold (`dup_threshold=0.6`), keeping the newest and forgetting the rest with audit tombstones. Contradiction candidates (same predicate, differing object) are surfaced for review and left for an LLM edge or the operator to resolve. Merges and contradictions are partitioned by user.

14. **Grounded entity graph.** `src/mneme/entity.py` (schema `mneme.entity-graph/1`) extracts typed relations (`lives_in`, `works_in`, `prefers`, `allergic_to`, `uses`, `likes`) and named entities, with every edge citing the source atom. The module states its scope: this is cue-based structured extraction. It stops short of general named-entity recognition; a real NER or LLM extractor plugs in as an edge for coreference and entity linking.

15. **L2 scenarios.** `src/mneme/scenario.py` clusters a session's atoms into scene blocks by shared salient tokens using a union-find pass, deterministically. Each scenario cites its member atoms, so it is drift-checkable through the same L2-inherits-L1 path.

16. **L3 persona.** `src/mneme/memory.py` `persona` groups a session's atoms into a profile whose lines are bound to their source atom ids, so the persona is drift-checkable and traces to its atoms. The deterministic floor needs no model.

17. **Provenance chain to an external source.** `src/mneme/ingest.py` `from_gather` binds an accountable-intake origin receipt (`{source, ref, method, sha256}`) to each ingested turn, then extracts atoms. `provenance_chain` (schema `mneme.provenance-chain/1`) walks atom to source turn to origin receipt. It fails closed: a memory with no source links, or an origin hash that is not even sha256-shaped, is reported as not externally grounded. The recheck is stated: re-fetch the ref, re-hash, confirm it equals the origin sha256. Mneme never imports the intake tool; any tool emitting that dict shape composes.

18. **Token-reduction benchmark.** `src/mneme/bench.py` (schema `mneme.bench/1`) reports `token_reduction` and `answer_recall` together, with per-probe detail and a `receipt_sha256`. A reduction is reported only alongside its answer recall, so a number that drops the needed fact is disqualified. The token estimator is a stated word-plus-punctuation count by default; a real tokenizer plugs in via `token_fn`. A built-in scenario runs with no configuration; `--turns` and `--probes` point it at your own conversation.

19. **Crucible export.** `src/mneme/compose.py` `to_crucible_thesis` (schema `mneme.crucible-export/2`) emits claims and drift-derived measurements (`MATCH` maps to deviation 0.0, `DRIFT` to 1.0, `UNVERIFIABLE` to null) plus a declarative `mneme.recheck/1` descriptor. Bounded claim, stated in the module: Crucible recomputes its verdict from Mneme's measurement and does not independently re-read the source unless an external recheck oracle is attached. Mneme never imports Crucible.

20. **Assessment-bound Crucible replay.** `src/mneme/replay.py` `replay_crucible` (emits `crucible.replay-pack/1`) re-runs a Crucible replay template against explicitly supplied Mneme state. It requires a read-only, immutable snapshot: `src/mneme/store.py` materializes a process-owned SQLite backup, fingerprints the source before and after, and refuses WAL or journal sidecars and hardlink aliases. Replay fails closed when the assessment triple, claim binding, descriptor, measurement contract, or target grounding differs.

21. **White-box HTML inspector.** `src/mneme/inspect.py` renders a self-contained HTML view of the memory store, written via `mneme inspect --out`.

22. **MCP server.** `src/mneme/mcp.py` `serve` speaks JSON-RPC 2.0 over stdio (MCP protocol version `2025-06-18`). The state database path comes from the `MNEME_STATE` environment variable (default `mneme.db`). Exposed tools: `mneme.remember`, `mneme.recall`, `mneme.drift`, `mneme.provenance`, `mneme.forget`, `mneme.audit`, `mneme.status`, `mneme.doctor`. Unknown arguments are rejected loudly so a dropped scope value does not misfile a write. A tool error rides the result payload; the transport still returns success. Honest scope: the MCP surface is eight tools, a subset of the full CLI and library surface.

23. **Deterministic, clock-free ordering.** `src/mneme/store.py` uses a monotonic `ord` counter persisted in `meta`, so no wall clock or randomness enters a stored hash or a ranking. The same inputs rebuild the same store, byte for byte.

24. **In-place schema migrations.** `src/mneme/schema.py` `MIGRATIONS` and `src/mneme/store.py` `_migrate` add any newer column to an older database in place and stamp the version, so a format change does not surface as a raw sqlite traceback. Read-only opens validate the required columns first.

Test coverage: 24 test files under `tests/`, one per behavior above (for example `test_verify_recall.py`, `test_drift_content.py`, `test_audit_integrity.py`, `test_crucible_replay.py`, `test_scope_isolation.py`).

## Usage

### Install

Inside Flywheel the lane runs from a source checkout, because the PyPI name is disabled in the lane registry. From the README:

```bash
pip install git+https://github.com/HarperZ9/mneme.git
```

Or clone the repo and `pip install -e .`. Python 3.11 or newer is required. There are no runtime dependencies to resolve.

### Library

```python
from mneme import AgentMemory

mem = AgentMemory("mem.db")                 # or ":memory:" for an ephemeral store
mem.remember("alice", [
    {"role": "user", "text": "I live in Denver and love dark roast."},
])

receipt = mem.recall("coffee preference")   # a RecallReceipt you can re-derive
print(mem.drift()["overall"])               # MATCH until a source changes
```

Turn on the local vector channel with `AgentMemory("mem.db", embed="ngram")`, or pass a real embedding model with `embedder=fn`. Pass an LLM extractor with `extractor=...`.

Re-derive a recall to confirm it:

```python
from mneme import recall, verify_recall

rows = [{"id": m["id"], "text": m["text"], "layer": m["layer"],
         "ord": m["created_ord"], "content_sha256": m["content_sha256"]}
        for m in mem.store.memories(layer="L1")]
r = recall("deploy steps", rows, strategy="hybrid")
assert verify_recall(r, rows)               # re-runs the scorer over the rows
```

### CLI

```bash
mneme remember alice session.json           # record turns, extract atoms
mneme recall "where does the user live" --json
mneme drift                                 # exit 1 if any memory drifted
mneme persona alice
mneme provenance <memory_id>
mneme audit                                 # hash-chained forget/update history
mneme bench                                 # token reduction AND answer recall
mneme mcp                                   # serve over MCP stdio
```

The default state database is `mneme.db`; override it with `--state PATH`. Every command prints its receipt as JSON.

### MCP

```bash
MNEME_STATE=mem.db mneme mcp
```

A host config points one server at one memory store. A recall over MCP returns the same re-derivable receipt as the library, so the calling agent or its operator can see and re-check why a memory was surfaced.

## Reference

Each capability, with its interface, module, output schema, and stated bound.

### remember (L0 to L1)
- CLI `mneme remember SESSION TURNS [--user U]`; library `AgentMemory.remember(session, turns, user="")`; MCP `mneme.remember`.
- Module: `src/mneme/memory.py`, `src/mneme/extract.py`.
- Returns a summary dict with per-atom provenance receipts. Idempotent by content id.

### recall
- CLI `mneme recall QUERY [--strategy keyword|vector|hybrid] [--top-k N] [--embed ngram] [--recency W] [--user U] [--session S] [--layer L] [--as-of N] [--json]`; library `AgentMemory.recall(...)`; MCP `mneme.recall`.
- Module: `src/mneme/recall.py`, `src/mneme/receipt.py`. Schema: `mneme.recall/1`.
- Returns a `RecallReceipt`. Verify with `verify_recall(receipt, rows, embedder=..., rrf_k=...)`. A vector or hybrid receipt needs the same embedder to re-derive; a keyword receipt is self-contained.

### drift
- CLI `mneme drift [--layer L1]`; library `AgentMemory.drift(layer="L1")`; MCP `mneme.drift`.
- Module: `src/mneme/drift.py`. Schema: `mneme.drift-report/1`.
- Verdicts per memory (`MATCH`, `DRIFT`, `UNVERIFIABLE`) and an overall fold. Fails closed on absent grounding. CLI exit code is 0 for `MATCH`, 1 otherwise.

### provenance and chain
- CLI `mneme provenance MEMORY_ID`; `mneme chain MEMORY_ID`. Library `AgentMemory.provenance(id)`, `AgentMemory.provenance_chain(id)`. MCP `mneme.provenance`.
- Module: `src/mneme/receipt.py`, `src/mneme/ingest.py`. Chain schema: `mneme.provenance-chain/1`.
- `provenance` returns the receipt (sources, extractor, criterion, hash). `chain` walks back to the external origin receipt and reports `externally_grounded` (fail-closed).

### forget, update, audit
- CLI `mneme forget MEMORY_ID [--reason R]`, `mneme update MEMORY_ID TEXT [--reason R]`, `mneme audit`. Library `AgentMemory.forget/update/audit`. MCP `mneme.forget`, `mneme.audit`.
- Module: `src/mneme/store.py`, `src/mneme/memory.py`. Audit schema: `mneme.audit/1`.
- `forget` erases text and leaves a tombstone; `update` edits text, keeps provenance, records before and after hashes. `audit` reports `chain_intact` from `verify_audit`.

### supersede and history (temporal)
- CLI `mneme supersede MEMORY_ID TEXT [--reason R]`, `mneme history [--contains X] [--predicate P] [--user U]`. Library `AgentMemory.supersede/history`, and `recall(as_of=N)`.
- Module: `src/mneme/temporal.py`, `src/mneme/store.py`. History schema: `mneme.history/1`.
- `supersede` keeps the old value with a validity window; `history` returns the timeline; `as_of` reconstructs a past state. Scalar answers are withheld when an unscoped read spans tenants.

### scenarios (L2) and persona (L3)
- CLI `mneme scenarios SESSION [--min-shared N] [--user U]`, `mneme persona SESSION [--user U]`. Library `AgentMemory.build_scenarios/persona`.
- Module: `src/mneme/scenario.py`, `src/mneme/memory.py`.
- Both return a summary dict (no schema tag) and store a memory row that cites its sources, so both are drift-checkable. Available through the CLI and library; the MCP server does not expose them.

### entity-graph
- CLI `mneme entity-graph [--user U] [--session S]`; library `AgentMemory.entity_graph(...)`.
- Module: `src/mneme/entity.py`. Schema: `mneme.entity-graph/1`.
- Typed relations and named entities, every edge citing its source atom. Cue-based structured extraction, available through the CLI and library. The MCP server does not expose it.

### consolidate
- CLI `mneme consolidate [--session S] [--user U] [--plan]`; library `AgentMemory.consolidate(...)`.
- Module: `src/mneme/consolidate.py`. Schema: `mneme.consolidation/1`.
- Merges near-duplicates with audit tombstones; surfaces contradictions without resolving them. `--plan` shows the plan without applying it. Never merges across tenants.

### ingest (accountable intake)
- CLI `mneme ingest SESSION ITEMS`; library `AgentMemory.ingest_gather(session, items)`.
- Module: `src/mneme/ingest.py`.
- Consumes intake items shaped `{id, text, source, ref, method, sha256}`. A malformed item is skipped with its reason. Binds each origin receipt to the turn, then extracts atoms.

### to-crucible and replay-crucible
- CLI `mneme to-crucible [--session S] [--layer L1]`, `mneme replay-crucible TEMPLATE --out PACK`. Library `AgentMemory.to_crucible(...)`, `AgentMemory.replay_crucible(template)`.
- Module: `src/mneme/compose.py`, `src/mneme/replay.py`. Schemas: `mneme.crucible-export/2`, `crucible.replay-pack/1`, and the `mneme.recheck/1` descriptor.
- Export separates measurement from assessment; Crucible recomputes and does not re-read the source unless an external oracle is attached. Replay requires a read-only immutable snapshot and fails closed on any binding mismatch.

### bench
- CLI `mneme bench [--turns FILE] [--probes FILE] [--top-k N] [--strategy ...]`; library `run_bench(...)`.
- Module: `src/mneme/bench.py`. Schema: `mneme.bench/1`.
- Reports `token_reduction` and `answer_recall` together, with `receipt_sha256`. The absolute token count is a stated estimate; the ratio holds across estimators, and the receipt names the one used.

### inspect
- CLI `mneme inspect [--out FILE]`; library `build_inspect`, `render_inspect_html`.
- Module: `src/mneme/inspect.py`.
- Renders a self-contained HTML view of the store.

### mcp, status, doctor
- CLI `mneme mcp`; MCP `mneme.status`, `mneme.doctor`.
- Module: `src/mneme/mcp.py`.
- `status` reports server name, version, and protocol without touching the network. `doctor` adds the configured state path and the tool list.

## Composition

### Which seam it is

Mneme is the `memory` lane in the Flywheel lane layer. Lanes compose through declared capabilities. A lane names what it emits and what it consumes in its interop file, and the Flywheel harness reads those dict-shaped outputs through adapters that never import the lane they read. Mneme's declarations live in `mneme.interop.json`.

### What it consumes from peers

From `mneme.interop.json`:

- `gather.items/1`: accountable-intake items, consumed by `src/mneme/ingest.py:from_gather`. This is how research intake becomes memory with an end-to-end source chain.
- `conversation-turns/1`: raw turns to remember, consumed by `src/mneme/memory.py:AgentMemory.remember`.
- `crucible.replay-template/1`: an assessment-bound replay template plus explicitly supplied Mneme state, consumed by `src/mneme/replay.py:replay_crucible`.

### What it emits for peers

From `mneme.interop.json`:

- `mneme.crucible-export/2`: memory as a Crucible thesis with drift measurements and `mneme.recheck/1` descriptors; consumable as `crucible.thesis/1` (`src/mneme/compose.py:to_crucible_thesis`).
- `crucible.replay-pack/1`: an assessment-bound drift replay pack (`src/mneme/replay.py:replay_crucible`).
- `mneme.provenance-chain/1`: the memory-to-source-origin chain (`src/mneme/ingest.py:provenance_chain`).
- `mneme.recall/1`: the re-derivable recall receipt (`src/mneme/receipt.py:RecallReceipt.as_dict`).
- `mneme.drift-report/1`: the per-memory faithfulness verdicts (`src/mneme/drift.py:drift_report`).

### Worked example: intake, memory, and the learning loop

Two composition paths run in the Flywheel application today.

Path one is the provenance chain from intake to sealed recomputation. An accountable intake tool (gather, the sibling research lane) emits items carrying an origin receipt. Mneme ingests them, and each resulting memory traces back to the exact bytes fetched:

```bash
mneme ingest research items.json          # gather-shaped {id,text,source,ref,method,sha256}
mneme recall "where is the user based"
mneme chain <memory_id>                    # -> the source url + content hash it came from
mneme to-crucible --session research > thesis.json
```

The `to-crucible` output is consumable as a Crucible thesis, so the verification lane can independently recompute `MATCH`, `DRIFT`, or `UNVERIFIABLE` from Mneme's measurement. Mneme imports neither gather nor Crucible; the seam is the shared dict shape.

Path two is the organizational learning loop, wired in `harness/lesson_mappers.py`. The `drift_lessons` mapper reads a `mneme.drift-report/1` dict and derives a Lesson for each `DRIFT` or `UNVERIFIABLE` memory:

```python
from harness.lesson_mappers import drift_lessons

report = mem.drift()                        # mneme.drift-report/1
lessons = drift_lessons(report)             # one lesson per drifted/unverifiable memory
```

The mapper binds each lesson to a content-addressed digest of the exact verdict bytes, sets `rationale` to null because Mneme records no decision rationale, and produces zero lessons for a clean store (all `MATCH`). That empty result is the honest null: no drift means no lesson, and the absence itself is meaningful. The mapper does not import Mneme; if Mneme's dict shape changes, the mapper's projection changes with it.

This is the coupling Flywheel is built on: an adversarial or accountability finding in one lane, here a memory that drifted from its source, feeds a named artifact in another, here a lesson in the learning loop, without the two lanes depending on each other's code.