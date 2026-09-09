# Product E2E journey framework

This document describes the first reusable Flywheel product E2E journey seam. It is intentionally narrow: it runs real product interfaces through CLI and MCP stdio adapters, records lifecycle and oracle outcomes separately, and leaves richer HTTP, browser, native, device, and authenticated journeys as future adapters.

The first implemented product journey is Gather 1.7 readable context selection from an operator-owned local text fixture. The journey proves that an installed Gather 1.7 CLI or MCP server can acquire a local docs corpus, inspect readable rows, select an explicit row range, and refuse a tampered corpus body. It does not prove source truth, claim support, semantic completeness, downstream model behavior, or all Gather commands.

## Reused Flywheel contracts

The implementation reuses the existing harness seams instead of introducing a second execution or provenance engine:

- `harness/mcp_client.py`: `LaunchSpec`, `MCPClient`, and `MCPAllowlist` for MCP stdio startup, `tools/list`, and `tools/call`.
- `harness/cross_harness_process.py`: `_child_env` and `run_process` for shell-free CLI execution with bounded process ownership.
- `harness/cross_harness_artifacts.py`: `preflight_artifact_root`, bounded `snapshot_source_tree` calls over declared resources, `create_attempt_workspace`, `bind_attempt_receipt`, and `write_artifact_index`.
- `harness/cross_harness_types.py`: `sanitize_evidence` for bounded report payloads.
- `harness/cli_entry.py`: one packaged dispatch row for `e2e-journey`.

## Public schema

Manifest schema: `flywheel.product-e2e-journey/v1`.

Run result schema: `flywheel.product-e2e-run/v1`.

The manifest vocabulary includes these runtime kinds:

- Implemented now: `cli_process`, `mcp_stdio`.
- Known but blocked until real adapters exist: `mcp_http`, `authenticated_http`, `browser`, `native`, `device`.

Run lifecycle status is separate from semantic/oracle status. A run can be lifecycle `completed` while `semantic_status` is `fail`; wrong-body calibration depends on that distinction. Missing, wrong-version, editable, unsupported, timeout, and cancelled runtimes remain explicit denominators rather than skipped successes.

Source snapshots are bounded to the manifest file and `allowed_resource_paths`. Running a checked-in manifest from the repository root does not snapshot the whole checkout, ignored siblings, private scratch files, or unrelated concurrent work. A manifest fails closed if a declared resource resolves outside the permitted source root.

## Implemented modules

- `harness/e2e_journey_manifest.py`: schema constants, dataclasses, path containment, fixture validation, and unsupported-runtime vocabulary.
- `harness/e2e_adapters.py`: CLI process adapter, MCP stdio adapter, and real Gather MCP `tools/list` schema validation.
- `harness/e2e_runner.py`: journey orchestration, installed-runtime preflight, artifact writing, receipt/index binding, oracle checks, wrong-body calibration, and tamper-refusal calibration.
- `harness/e2e_cli.py`: `validate`, `run`, and `list` commands.
- `tests/fixtures/e2e/gather_context/**`: trusted operator-owned fixture text and CLI/MCP manifests.

## Gather 1.7 runtime requirements

The runner requires an explicit installed Gather 1.7 executable path through the manifest's `runtime.executable_env`, normally `FLYWHEEL_E2E_GATHER17_EXE`.

Runtime preflight checks all of the following before launching the journey:

- the executable exists;
- `gather --version` matches the expected version prefix;
- the distribution metadata resolves from the executable's own venv Python;
- `direct_url.json` is present as provenance, and when a wheel hash is declared the wheel archive itself hashes to the expected SHA-256;
- installed package and metadata files are compared byte-for-byte against the pinned wheel archive, excluding generated RECORD state;
- the executable launcher SHA-256 is recorded and, when `expected_executable_sha256` is declared, enforced before launching;
- editable installs are rejected when `forbid_editable` is true;
- parent `PYTHONPATH` is rejected when `forbid_pythonpath` is true;
- child processes run with Flywheel's allowlisted `_child_env`, excluding `PYTHONPATH`.

## Gather 1.7 journey behavior

The CLI journey uses the verified Gather 1.7 command shape:

```text
gather docs <sample.txt> --store <owner-state/corpus> --json
gather corpus context <owner-state/corpus> --json
gather corpus context <owner-state/corpus> --select <ROW_REF:START:LIMIT> --expect-digest <DIGEST> --json
gather corpus context <owner-state/corpus> --select <ROW_REF> --expect-digest <DIGEST> --json
```

The MCP journey uses the verified Gather 1.7 MCP shape:

```text
gather mcp
initialize
tools/list
validate gather.context inputSchema
tools/call gather.run with inline {jobs:[{source:"docs", target:"<sample.txt>"}], scope:[], store:"<owner-state/corpus>"}
tools/call gather.context with {corpus:"<owner-state/corpus>"}
tools/call gather.context with {corpus:"<owner-state/corpus>", select:["<ROW_REF:START:LIMIT>"], expected_corpus_digest:"<DIGEST>"}
```

The selected-text oracle reads the actual product response and checks:

- schema is `gather.readable-context/v1`;
- selected text exactly equals the independently derived source span between the configured start and end markers;
- expected and observed selected-text SHA-256 values match;
- selected text includes the Alpha sentinel;
- selected text excludes the Beta sentinel;
- `selection_digest` is present as 64 lowercase hexadecimal characters;
- `verified` is true.

Wrong-body calibration selects the full row and must make the same oracle fail because the Beta sentinel appears. Tamper-refusal calibration modifies only the run-owned corpus object, then selection must fail or return an MCP error containing the corrupt-body/body-status refusal evidence. Completed workspaces are retained by default until a separate lifecycle policy exists.

## Acceptance commands

Run from a Flywheel source checkout. Use an artifact root outside the source tree because `preflight_artifact_root` rejects in-tree artifacts.

```powershell
$env:FLYWHEEL_E2E_GATHER17_EXE = '<path-to-verified-gather-1.7-venv>/Scripts/gather.exe'
$env:PYTHONPATH = ''
$artifactRoot = '<artifact-root-outside-source-tree>'
python -m pytest tests/test_e2e_journey_manifest.py tests/test_e2e_adapters.py tests/test_e2e_runner.py tests/test_e2e_cli.py -q
python -m pytest tests/test_e2e_gather_context_journeys.py -q
python -m harness.e2e_cli validate tests/fixtures/e2e/gather_context/gather-cli-context.json
python -m harness.e2e_cli run tests/fixtures/e2e/gather_context/gather-cli-context.json --artifact-root $artifactRoot --run-id acceptance-cli --strict
python -m harness.e2e_cli run tests/fixtures/e2e/gather_context/gather-mcp-context.json --artifact-root $artifactRoot --run-id acceptance-mcp --strict
python -m harness.cli_entry e2e-journey validate tests/fixtures/e2e/gather_context/gather-cli-context.json
```

Expected acceptance result with a verified Gather 1.7 wheel/venv:

- CLI and MCP runs return lifecycle `completed`;
- `primary_outcome` is `semantic_pass`;
- `semantic_status` and `oracle.status` are `pass`;
- wrong-body calibration status is `pass` with its inner oracle status `fail`;
- tamper-refusal calibration status is `pass`;
- runtime metadata reports version `1.7.0`, editable `false`, executable SHA-256, matching wheel archive SHA-256, matching installed-file aggregate SHA-256, and matching wheel hash when declared;
- run artifacts include manifest, steps, oracle, calibration, source snapshots, result, receipt, and artifact index;
- the attempt workspace remains available for review.

## Coordination seam

Other product or enterprise-environment E2E tracks should reuse these functions instead of adding another runner:

```python
load_journey_manifest(path: Path, *, repo_root: Path) -> JourneyManifest
validate_journey_manifest(manifest: JourneyManifest) -> list[ValidationIssue]
run_journey(manifest: str | Path | JourneyManifest, *, artifact_root: str | Path, repo_root: str | Path | None = None, run_id: str | None = None) -> JourneyRunResult
```

Stateful environment journeys can share lifecycle/result vocabulary and artifact layout while keeping product-specific action/state/hidden-control logic in their own modules. This slice owns only the E2E journey modules, tests, fixtures, docs, and the single `cli_entry` dispatch row.


