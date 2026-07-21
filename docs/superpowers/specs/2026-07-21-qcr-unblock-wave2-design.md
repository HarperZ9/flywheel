# QCR Unblock Wave 2 Design

Status: approved for implementation by continuation of the active QCR goal

Date: 2026-07-21

Owner repository: Flywheel (`local-model`)

Related repositories: Mneme and Crucible

## Objective

Remove three concrete blockers from the quantum--classical research program:

1. replace the blank amplitude/channel template with a source-derived,
   machine-readable manifest;
2. make all five Mneme-derived Crucible measurements carry deterministic replay
   descriptors and provide an executable path that produces Crucible's existing
   assessment-bound replay pack; and
3. identify and exercise one bounded local-model endpoint using only already
   installed Windows-native infrastructure.

The work does not claim a physical result, settle the Aziz--Howl dispute, start
WSL, introduce a daemon, add a model, or create a new orchestration system.

## Verified starting state

- Flywheel already contains the two deterministic QCR `TaskSpec` oracles and the
  Lane 1 manifest template.
- Mneme schema `mneme.crucible-export/2` already emits loadable
  MATCH/DRIFT/UNVERIFIABLE measurements, but those rows have no `recheck`
  descriptor.
- Crucible already supports declarative measurement descriptors, assessment-
  bound replay templates and packs, and exact comparison of replayed
  measurements. It intentionally does not execute arbitrary commands.
- Flywheel commit `68c143feb9f5444496ec1accba3d65769c5f40d3` contains
  the QCR TaskSpecs and blank manifest template. Mneme commit
  `2facab82aa974a3f31e865b2c56400871bb3bdf4` emits schema v2 rows.
  Crucible commit `d749d76d6d793845738dffeba662466330669a2f` provides
  replay templates and assessment-bound packs.
- The existing 14B release assets are
  `E:/local-model-run/release/flywheel-local-coder-14b/Modelfile`,
  `checksums.sha256`, and `telos-coder-14b-cpt2020-q4_k_m.gguf`. The
  recorded GGUF size is 8,988,110,880 bytes and its recorded SHA-256 is
  `613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be`.
  These are release-record facts until fresh preflight re-hashes the bytes.
- Windows Ollama is installed at
  `C:/Users/Zain/AppData/Local/Programs/Ollama/ollama.exe`. The design-time
  process/port check found no listener; that observation must be repeated and
  receipted immediately before execution.

## Constraints and invariants

- Reuse existing repositories, CLIs, schemas, models, and endpoint software.
- Do not invoke WSL.
- Keep Mneme zero-runtime-dependency and keep Crucible provider/tool neutral.
- Never put a state database path or executable shell command in a replay
  descriptor.
- Keep source claims, implementation choices, and experimental results as
  separate states.
- Preserve primary-source version and content hashes without committing paper
  binaries.
- A model response is candidate output. Deterministic QCR oracles, not the
  model, decide acceptance.
- Any endpoint process started by this wave has a bounded timeout and is stopped
  at the terminal gate.
- The endpoint must bind only to an unused `127.0.0.1` port. Wildcard/LAN binds,
  firewall changes, and displacement of an existing listener are prohibited.
- No Ollama alias is created or removed in this wave. Preflight may use an
  already registered alias only when its local Ollama manifest names a model
  layer with the exact release GGUF digest and byte length. The current store
  exposes `telos-coder-14b` with layer
  `sha256:613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be`
  and 8,988,110,880 bytes; this is revalidated before startup. If no such alias
  exists, the lane records the verified artifact/profile as the identified
  endpoint target and stops before model-store mutation.

## Architecture

### Lane A: source-derived amplitude/channel manifest

Add a canonical JSON manifest at
`configs/qcr/amplitude-closure-manifest-v1.json`. JSON is used because it is
machine readable with the repository's stdlib-only runtime and is also valid
YAML. A focused test validates its required shape, unique identifiers,
cross-references, complete source provenance, and absence of unresolved `null`
placeholders.

The manifest is a protocol declaration, not an amplitude result. It records:

- exact arXiv versions, canonical URLs, retrieval timestamps, and SHA-256 hashes
  for the primary source bytes;
- the shared weak-classical-background / complex Klein--Gordon model boundary;
- the stated initial state, no-pair or fixed-number restriction, perturbative
  convention, and fourth-order Dyson boundary;
- explicit variants for same-field versus distinct species and full no-pair
  evolution versus four-branch projection;
- a row-level `amplitudes` inventory. Every row has a stable amplitude ID,
  variant ID, Dyson order, incoming branch/state, outgoing state/sector,
  field/species assignment, channel/diagram family, amplitude definition or
  source expression, exact source locus, inclusion state, and completeness-rule
  membership. Family-only placeholders do not satisfy the schema;
- included and excluded channel rows, with source-bounded reasons and the source
  location supporting each declaration. A future amplitude enumerator must be
  driveable from these rows without inventing additional channel classes;
- projection/leakage accounting and O1--O6 deterministic oracle definitions;
- tolerances split into `source_derived` and `implementation_control`. A numeric
  value is forbidden unless its provenance or convergence role is explicit;
- expected artifact names for amplitude tables, density matrices, leakage,
  convergence, and receipts. The manifest does not fabricate those outputs.

The existing QCR research document will point to the canonical manifest and
change Lane 1 from `BLOCKED: manifest unset` to
`POPULATED: BLOCKED ON NAMED TECHNICAL GATES`. The source-derived artifact is
then reviewable, but physical execution remains blocked until the Hamiltonian-
convention dispute, exhaustive generator, distinct-field/barrier definitions,
and convergence policy are resolved.

The bounded corpus contains the original disputed fourth-order proposal
(Aziz--Howl), two direct current amplitude-completeness/species/projection
analyses (Gundhi--Infantino--Bassi and Vidal--Iyer), and the current
binding/localization control analysis (Tang et al.). Only primary works directly
defining or challenging the Lane 1 model/channel boundary are eligible for v1.
The retrieval receipt must prove version, canonical URL, bytes hash, and a
declaration-to-section/equation source locus for every manifest row. Conflicts
are represented as variant or claim records; no disputed equation is installed
as benchmark truth. Expanding beyond this bounded contrast set requires a new
manifest version or an explicit coverage-review amendment.

The exact source identities are `2510.19714v3`, `2604.19696v2`,
`2607.03429v1`, and `2512.13675v2`. Their freshly retrieved PDF SHA-256 values
are, respectively,
`a26fcb9f2add435c66ab6aa0ac86bcaf049481ee3c41e87e20cefc4dd63dc391`,
`34d1159cf786454a71b2fb380e470be52468e06854a93cdcb315787cbf161bbe`,
`2d90d1101b66c0cd868bd8a36fe8b41070e393a78902a8837111aa12dda52f99`,
and `4c00093642a6a6caeb8535e1fbdd734af0156c8b43ce9e7326080794995f39ea`.
The corresponding source-bundle hashes are
`15dfdf6db4093aa12eb00e2416914e96dccddc3d0edba6169c3b3fefe93cbe32`,
`4e667a1d3c4dafbe319dc548bea1ca1ff6b885c15d307b023671bae91197865d`,
`404e6fa4b8419b541be6115cf18c6dab3cfe696ed726140f79ee2ef5f4a543ca`,
and `ef426c611f5ae32d80995c68c4a0d2181df0a867612afc8a7cf4c02e6c4c2938`.
The retrieval receipt, not this design prose, remains the authoritative proof.
The first bundle is already preserved at
`C:/dev/scratch/qcr-2026-07-21-01/2510.19714.tar`; the other binaries need not be
committed.

An unresolved source field uses a non-null tagged object:

```json
{
  "status": "unknown",
  "reason": "<bounded reason>",
  "evidence_state": "unverifiable",
  "required_review": "<named gate>"
}
```

Such an object is visible and review-blocking. It cannot occupy a field required
for `READY FOR TECHNICAL REVIEW`; it merely avoids silently ambiguous `null`.

### Lane B: Mneme-owned Crucible replay

Each exported measurement gains this declarative descriptor shape:

```json
{
  "schema": "mneme.recheck/1",
  "oracle": "mneme:drift/v1",
  "memory_id": "<stable memory id>",
  "grounding_sha256": "<hash of the original memory and grounding snapshot>",
  "measurement_contract_sha256": "<hash of the original portable measurement fields>"
}
```

`grounding_sha256` binds the original memory ID, content hash, layer, session,
tenant, extractor, criterion, ordered source identifiers, and extraction-time
source-hash map. `measurement_contract_sha256` binds `claim`, `deviation`,
`tolerance`, `method`, and `evidence` before Crucible adds a claim hash and
measurement timestamp. Both use UTF-8 SHA-256 over canonical JSON with
`sort_keys=True`, `ensure_ascii=False`, and separators `(',', ':')`, passed as a
single value to Mneme's existing `content_hash`. Golden vectors pin the exact
bytes and digests. The descriptor carries no database path, source prose,
credential, assessment seal, or command; assessment binding remains the
top-level responsibility of Crucible's existing replay-pack schema.

Mneme adds a `replay-crucible` CLI command and a pure library function. They
accept a Crucible-generated replay template plus an explicitly supplied Mneme
state path, re-run the existing `check_memory`, and emit the existing Crucible
replay-pack shape. The command does not import Crucible.

For every replay row the generator:

1. validates the template, assessment binding, oracle schema, and this exact
   chain: `claim.id == expected_measurement.claim_id == recheck.memory_id`,
   `claim.sha256 == expected_measurement.claim_sha256`, and the canonical
   expected portable measurement digest equals
   `measurement_contract_sha256`; a swapped descriptor therefore fails closed;
2. resolves the descriptor against the supplied state;
3. fails the pack-generation command if the target memory or grounding identity
   no longer matches the descriptor, because that is a claim/subject binding
   failure rather than a replayed measurement; otherwise it delegates to
   `check_memory`, which returns UNVERIFIABLE for missing sources and DRIFT for
   changed source content;
4. recomputes only `deviation` through the existing `_deviation` mapping
   (`MATCH -> 0.0`, `DRIFT -> 1.0`, `UNVERIFIABLE -> null`); and
5. copies the assessment-bound claim hash, tolerance, method, measurement time,
   and evidence from `expected_measurement` so Crucible compares the original
   measurement contract rather than a newly timestamped assertion.

The output retains the Mneme verdict and reason as non-sealed diagnostic data.
Crucible then performs its existing seal, thesis, verdict-rederivation, and
measurement-replay checks. One generic Crucible hardening is required by the
real contract review: when a selected assessment is supplied to the replay-pack
loader, omission of the pack's `assessment` object must fail closed rather than
skip the binding check. The existing exact three-field comparison remains
unchanged.

Before relying on that oracle, `check_memory` must recompute each current source
row's content hash from its actual fields (turn: role/text; memory:
text/source_ids/criterion) and compare it to both the row's stored hash and the
extraction snapshot. A row whose text was changed while its stored hash was left
stale is DRIFT, never MATCH.

The active target is the preserved schema-v2 export at
`C:/dev/scratch/qcr-2026-07-21-01/run-001/mneme-export-utf8.json` (SHA-256
`0f9b4f8345ccd012fa1540620c9ad10fede5e41347a7eca4c5cda684c2a5a0cb`)
and its state database `mneme.db` (design-time SHA-256
`6f6764296b77243c151152306736fc46d441cb7f1f6bdf1a602be6cbfa368845`).
Its five pre-change MATCH rows are, in order:

1. `da6f0d932c09dd48`
2. `561936c28ba4e7e9`
3. `48e0465411177b51`
4. `849a783ce3bd4960`
5. `18987a65c43aba4a`

Required falsifiers cover those five descriptor-bearing rows, fresh replay, raw
source-row tamper, ordinary source drift, target-memory binding change, missing
source, malformed/tampered templates, unsupported
oracles, wrong claim bindings, and exact end-to-end acceptance by Crucible.

### Lane C: bounded existing endpoint

Use the existing Flywheel 14B Q4_K_M GGUF with installed Windows-native Ollama.
The endpoint lane must first verify the documented artifact SHA-256, executable
path, process state, and ports. It reuses an existing lifecycle/probe wrapper if
one is present; otherwise direct `ollama.exe` commands are acceptable because
they add no infrastructure.

The bounded run is:

1. prove TCP port `11439` is unused and record all existing Ollama processes;
2. re-hash the GGUF, require at least 12 GiB free GPU memory as an explicit
   implementation safety control, and confirm from the read-only local Ollama
   manifest that an existing alias (currently `telos-coder-14b`) resolves to the
   exact GGUF layer without mutating the model store;
3. set `OLLAMA_HOST=127.0.0.1:11439` and start `ollama serve` hidden only if the
   preflight is clean;
4. within 60 seconds, require a listener owned by the wave-started process on
   `127.0.0.1:11439`; reject `0.0.0.0`, `::`, a different PID, or any firewall
   mutation;
5. record `/api/tags` health and the exact registered model identity;
6. run exactly `branch_entanglement_invariants` with temperature `0`, seed `7`,
   its declared `max_new_tokens=512`, and a 180-second generation timeout. Use
   the existing proposer/TaskSpec/oracle APIs or existing live benchmark command;
   do not add a QCR endpoint wrapper;
7. evaluate the candidate with that TaskSpec's existing hidden pytest oracle
   under its 60-second process-tree-cleaning bound;
8. write a receipt containing artifact/model identity, request hash, response
   hash, latency, resource observations, oracle verdict, and failure state; and
9. issue the model-only stop request, stop only the server process started by
   this wave, and prove port `11439` is closed. Do not remove any alias.

After the server process starts, a 360-second overall lifecycle deadline covers
every remaining phase. `/api/tags` has a 10-second HTTP deadline. Cleanup runs
from `finally` regardless of health, generation, oracle, or receipt failure:
`ollama stop <verified-existing-alias>` is bounded to 15 seconds, normal
termination of the recorded wave PID is bounded to 15 seconds, and a still-live
recorded PID is force-terminated by PID within 5 seconds. A final port-closure
poll is bounded to 10 seconds. No process discovered independently of the
recorded wave PID may be terminated. The receipt records cleanup escalation and
fails the lifecycle gate if `127.0.0.1:11439` remains open.

The first endpoint is intentionally 14B because it is already packaged and
satisfies the small-local-model preference. GPU identity, free memory, and the
12-GiB safety gate are fresh preflight evidence, not design-time capability
claims. If the alias or resource gate is absent, the verified GGUF/profile is
reported as the bounded identified target and no server is started.

## Coordination and ownership

- Flywheel worktree owns the source manifest, its validator, research-doc link,
  and the endpoint receipt.
- Mneme worktree owns descriptor creation, replay generation, CLI/docs, golden
  vectors, and the synthetic five-row fixture.
- Crucible worktree owns the minimal fail-closed assessment-presence check plus
  its CLI/docs/tests. Its replay template/pack schema remains the compatibility
  pin and its CLI produces the shared template in the scratch run directory.
- Workspace scratch owns the run-001 state input and the new run-002 export,
  registry, replay template, pack, result, endpoint profile, and receipts.
- Crucible remains integration-test evidence only unless its existing pack
  contract demonstrably fails.
- Source research, replay-contract analysis, endpoint discovery, and baseline
  diagnosis may run in parallel. Edits within each repository remain serial.

## Verification gates

### Manifest gate

- source files are retrieved from canonical primary URLs and hashed;
- focused schema/semantic tests pass;
- every required field is populated or explicitly represented as a bounded
  exclusion/unknown, never silently omitted;
- `git diff --check` passes.

### Replay gate

- red tests fail for missing descriptors and replay generation before code;
- focused Mneme tests pass after implementation;
- the five named run-001 rows appear in Crucible's replay plan and all five replay successfully
  against unchanged state;
- drift/tamper tests fail closed;
- full Mneme and Crucible regressions pass; and
- `git diff --check` passes in each touched repository.

### Endpoint gate

- no WSL process or command is invoked;
- artifact hash and model identity are recorded;
- the endpoint is loopback-only and becomes healthy within the 60-second startup bound;
- one deterministic TaskSpec request reaches a terminal success or explicit
  bounded failure state;
- the deterministic oracle result and resource/latency receipt are preserved;
  and
- process cleanup is verified.

## Stop conditions

- Stop manifest promotion if a field would require guessing beyond the primary
  sources.
- Stop replay generation if any template/descriptor/assessment binding is
  ambiguous.
- Stop endpoint startup if the target port is owned by an unrelated process,
  the GGUF hash differs from its release record, or GPU memory preflight is
  unsafe.
- A bounded endpoint failure is evidence, not permission to install another
  runtime or invoke WSL.

## Durable outputs

- canonical source-derived amplitude/channel manifest and validation tests;
- populated five-row Mneme export with executable replay workflow;
- assessment-bound Crucible replay plan/pack/result receipts;
- bounded local endpoint and TaskSpec execution receipt;
- exact test commands and current commit/worktree identities; and
- a checkpoint listing any remaining physics-review or runtime blocker without
  overstating completion.
