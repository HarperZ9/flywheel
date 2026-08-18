# Truth-first lane repair and cross-harness benchmark design

Date: 2026-08-11

Status: APPROVED

Base commit: `d164aa8`

## Decision

Repair the two known lane-truth defects, then execute the existing four-task
cross-harness pilot. Do not create a second benchmark framework and do not
expand Flywheel's component graph before the pilot identifies which integration
matters.

This work is isolated to Flywheel. Creative-site files, shader sources, session
scratch space, and external outreach remain outside the change boundary.

## Why this slice comes first

Flywheel already has task-set, adapter, endpoint, benchmark-profile,
execution-matrix, coverage, and outcome-report schemas. It also has an approved
execution-contract plan for the missing executor. The shortest durable path is
to make lane health truthful and complete that spine, not wrap it in another
script or begin a broad Mneme, EMET, Relay, and Plexus integration pass.

The result is an orchestration-stack comparison. The Codex role calls the Codex
CLI directly. The Flywheel role uses the same requested model through
Flywheel's routing and agent loop. The comparison therefore measures the whole
orchestration path, not a pure one-variable harness ablation.

## Boundaries

### In scope

- Correct source-checkout resolution for lane commands and source installs.
- Forward the CLI `--probe` request into the lane roster.
- Probe an available source checkout even when its package is not globally
  installed.
- Preserve typed `live`, `stale`, `declared`, and `missing` results with exact
  failure detail.
- Implement the already-designed cross-harness executor and deterministic
  oracles over the existing manifests.
- Run a two-task admission smoke, then the approved 24-row Spark pilot if the
  smoke passes.
- Probe configured 14B and 32B routes and record each as executed or typed
  unavailable.
- Produce raw artifacts, a refreshed integration map, methodology, comparison,
  and experimental conclusion in an operator-supplied artifact root outside
  the published repository.

### Out of scope

- Portfolio, Retro, shader, or creative-session changes.
- Website deployment or outreach dispatch.
- Adding Mneme, EMET, Relay, or Plexus to the lane registry.
- New benchmark, task-set, scorecard, or receipt schemas unless an existing
  schema cannot represent a required typed outcome and the spec is revised
  before code changes.
- The planned 84-attempt matrix before the pilot passes every acceptance gate.
- Model publication, weight changes, fine-tuning, or credential changes.
- Claims that a blocked route scored zero or that this is a pure harness-only
  ablation.

## Lane truth architecture

### Source repository resolution

One helper owns source-checkout resolution. Callers do not concatenate
`REPO.parent` and `source_repo` independently.

The helper evaluates public-clean candidates in order:

1. an explicit `FLYWHEEL_WORKSPACE_ROOT` joined to the declared source path;
2. the workspace-root candidate inferred from the Flywheel checkout and the
   declared source path;
3. a sibling-repository candidate when the declared leading directory equals
   the current repository container, such as `public/learn` beside
   `public/flywheel`.

It returns only an existing directory. If none exists, package or bare-command
fallbacks retain current behavior. The implementation never hardcodes a host
path and never treats a nonexistent inferred path as installed.

The helper is shared by command resolution, source-presence checks, and
source-profile installation so the three paths cannot drift.

Command resolution returns a launch specification, not only an argument list.
The specification carries `argv`, an optional working directory, and bounded
environment overrides. Node lanes use an absolute script path under the
resolved checkout. Python lanes use the current interpreter and declared
module, set the subprocess working directory to the resolved checkout, and
prepend that checkout to the child process's `PYTHONPATH`. The parent process
environment is never mutated. The MCP stdio transport accepts these launch
fields explicitly. Tests prove the child can import the source module when the
package is absent from the active interpreter and that no host path leaks into
the public roster artifact.

### Probe flow

```text
CLI --probe
  -> lane_roster(probe=True)
  -> lane_status(probe=True)
  -> resolve source/package-aware MCP command
  -> MCP initialize + list_tools + status/doctor call
  -> flywheel.lanes/v1 row
```

When `probe=False`, a row says install or source presence only. When
`probe=True`, an available source checkout is probed even without a global
package install. A successful handshake and status/doctor response is `live`.
A reachable server whose health call errors remains `stale`. A present package
or source checkout whose probe fails remains non-live with the exact failure.
An absent package and absent source checkout is `missing`.

No new optimistic fallback is allowed. The note and human report must identify
whether the roster was presence-only or live-probed.

## Benchmark data flow

The existing artifacts remain authoritative:

```text
agentic-task-set/v1
  -> cross-harness manifest
  -> adapter runtime matrix
  -> endpoint/auth gates
  -> benchmark profile manifest
  -> benchmark execution matrix
  -> cross-harness attempt artifacts and receipts
  -> comparison input + closed-loop seed
  -> comparison report + closed-loop outcome report
```

The executor consumes the existing manifest rather than inventing a task or
score schema. Every attempt records:

- source commit, run identifier, provider role, requested model, adapter;
- task, prompt, declared tool-policy, actual adapter-enforcement, and input
  hashes;
- repetition and declared cache state;
- raw output and tool-trace hashes;
- deterministic completion-oracle result and secondary rubric result;
- elapsed time and available resource observations;
- tokens and cost, or an explicit null with reason;
- orthogonal execution, oracle, and receipt states;
- derived primary outcome, receipt path, and re-check verdict.

## Pilot contract

### Admission smoke

Run `agt-001` and `agt-003` once for each reachable target role. The smoke must
prove adapter launch, authorization, artifact shape, deterministic oracle,
receipt verification, and comparison-key agreement before the pilot starts.

### Spark pilot

Use the existing approved task set:

- `agt-001`
- `agt-003`
- `agt-009`
- `agt-010`

Run `codex_harness` and `flywheel_harness` three times per task for 24 planned
rows. Both roles request `5.3-Codex-Spark`. Typed unavailable rows remain in the
matrix but outside performance denominators.

The roles receive the same declared allowed-tool policy, but the controls are
not assumed equivalent. Direct Codex exposes its verified CLI sandbox and
observed tool surface; Flywheel exposes its `ToolGate`, step budget, and
proposer boundary. Each actual enforcement description has its own hash. The
pilot is labeled policy-non-equivalent unless independent fixtures and live
traces prove equal effective capabilities. A matching declared-policy hash is
not reported as matching enforcement.

The local baseline is separate from the 24-row Spark comparison. It uses
`local_14b` and `local_32b`, the same four task identifiers, and one repetition,
for eight additional planned rows. These rows are descriptive because one
repetition cannot establish comparative reliability. Each configured endpoint
first receives its existing bounded generation gate. A passing gate authorizes
the two-task admission smoke and then its four local baseline attempts. A
failed gate produces one typed unavailable row for each planned task, with
role, backend, model reference, attempted gate, and failure reason. It does not
delay the report and it never enters the 24-row Spark comparison.

### Stop-before-84 rule

Do not run the 84-attempt expansion unless all of these are true:

- every compared Spark attempt has identical task, prompt, input, and declared
  tool-policy hashes across roles, with distinct actual-enforcement hashes
  reported rather than collapsed;
- every compared row declares cache and randomness control;
- every compared row has a completed deterministic oracle;
- every receipt re-checks;
- shared comparison keys are nonempty;
- no admission, endpoint, authorization, artifact-shape, or hygiene gate is
  unresolved;
- the pilot report states denominators, intervals or observed ranges, and what
  the experiment does not prove.

## Outcome semantics

Each row stores three orthogonal state axes:

- `execution_state`: `not_started`, `unavailable`, `launched`, `returned`,
  `timeout`, `malformed`, or `internal_error`;
- `oracle_state`: `not_run`, `pass`, `fail`, or `unverifiable`;
- `receipt_state`: `not_emitted`, `verified`, or `drift`.

For compact tables, one `primary_outcome` is derived with this precedence:
`unavailable`, `timeout`, `internal_error`, `malformed`, `receipt_drift`,
`unverifiable`, `oracle_fail`, then `completed`. The source axes remain in the
artifact, so a receipt failure cannot erase the observed oracle result and an
oracle failure cannot masquerade as a transport failure.

The reports use separate denominators:

- availability: admitted, planned, blocked, and launched rows;
- execution reliability: well-formed returned rows divided by launched rows;
- deterministic quality: oracle passes divided by oracle passes plus oracle
  failures, limited to well-formed rows with verified receipts;
- latency and resource use: well-formed returned rows, with statuses and sample
  count named; timeouts and unavailable rows reported separately.

Missing provider usage remains null rather than estimated. Unverifiable,
malformed, drifted, timed-out, blocked, and internal-error rows remain visible
without entering the deterministic quality denominator.

## Test strategy

### Lane tests

- Red tests first for workspace-root, sibling-layout, explicit-root, and absent
  source resolution.
- Red test proving `lanes --probe` forwards `probe=True`.
- Red test proving a source checkout without a global package still reaches the
  MCP probe.
- Launch-spec tests proving Python source probing uses a child-only working
  directory and `PYTHONPATH`, while Node probing uses an absolute script.
- Negative tests for probe timeout/failure and missing source/package.
- Report tests proving presence-only and live-probed rosters cannot be confused.

### Executor and oracle tests

- Dry, unavailable, successful, timeout, malformed, oracle-fail, unverifiable,
  and receipt-tamper fixtures.
- Identical comparison-key enforcement across provider roles.
- Deterministic oracle tests over portable task fixtures.
- Endpoint-gate ingestion for reachable and blocked local roles.
- Comparison and outcome synthesizer tests consuming real executor output
  shapes.
- Denominator tests proving unavailable rows cannot lower quality scores.

### Repository gates

- focused lane, CLI, manifest, runtime-matrix, executor, oracle, comparison,
  coverage, and outcome tests;
- full Python test suite;
- file-size gate;
- stdlib verifier gate;
- public claim-language gate;
- standalone public-instruction gate;
- Flywheel disproof/rewitness gate;
- secret and host-path scan over changed public files and generated public
  artifacts.

## Artifact and report contract

Raw artifacts live outside the published repository under an operator-supplied
dated root. The root contains:

- environment and commit receipt;
- lane roster before and after repair;
- endpoint/auth gate artifacts;
- frozen task-set and adapter-contract copies or hashes;
- admission-smoke attempts;
- all 24 planned Spark rows, including unavailable rows;
- all eight planned local 14B/32B rows, including unavailable rows;
- comparison input, closed-loop seed, profile, coverage, execution matrix, and
  outcome report;
- command ledger with exit code, start/end time, and redacted environment
  inventory.

The final methodology and comparison reports separate verified observation,
inference, unknown, and blocked state. They include raw artifact pointers,
denominators, limitations, and the explicit next-loop decision.

## Rollback and safety

The repair lands on an isolated branch. No package, tag, release, website,
endpoint credential, or external communication changes. Benchmark work uses
temporary task workspaces and read-only/ephemeral provider modes where the
adapter supports them. A failed live run leaves its artifact and receipt; it
does not trigger an unplanned retry sweep.

## Acceptance

The design is implemented only when:

1. the live probe reports source-layout truth on the current workspace without
   `public/public` paths;
2. CLI `--probe` behavior is covered by a failing-before/passing-after test;
3. the two-task smoke passes for each reachable role or emits a valid typed
   unavailable row;
4. the 24-row Spark pilot is either executed with re-checkable evidence or
   completed as an honest matrix containing typed unavailable rows;
5. all eight planned local 14B/32B rows are executed or recorded blocked from
   fresh gates, without entering the Spark comparison;
6. the full suite and repository gates pass, with any pre-existing failure
   separated from introduced failures;
7. independent review approves code, artifacts, calculations, and conclusions;
8. the 84-attempt expansion remains unexecuted unless every pilot gate passes.
