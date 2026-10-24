# Scope migration: `does_not_prove` to `scope`

Started 2026-10-23 on branch `feat/scope-migration`. Author decision, 2026-10-23:
every tool says what its result covers, in positive plain words. Articulate #71,
BuildLang #109, Emet #34 and Telos #83 already made this change. This file is the
checklist the workspace rule asks for before any project-wide rename.

## What changes

A record used to carry `does_not_prove`: a list (sometimes a string) of limits,
each phrased as a negative sentence or a `NOT_PROVES_*` code. A record now carries
`scope`: the same slot, with every entry rewritten to say what the result covers.
A bare key rename is wrong, because every value is negative; each value gets a
positive rewrite written from what the module checks.

## Rules

1. **Field.** New records write `scope`, with the same type the old field had
   (list stays list, string stays string). A record never carries both names.
2. **Values.** Each entry states what the result covers or what was checked. A
   conditional limit becomes a conditional coverage entry, present when the
   covered condition holds. A boundary with no positive counterpart is stated as
   a fact about the record ("the chain is unsigned; its links detect accidental
   change"). Entries never use "does not prove" or "not prove". `NOT_PROVES_X`
   codes become codes that name the covered property (for example
   `NOT_PROVES_EXACTNESS`, appended when the predicate is inexact, becomes
   `PREDICATE_EXACT`, appended when it is exact).
3. **Versions.** A schema whose records change gets its version bumped
   (`x/v1` to `x/v2`). Writers emit only the new version. Readers and verifiers
   accept both versions and read each with its own vocabulary: the old version
   with `does_not_prove`, the new version with `scope`. Where a module already
   enforces a field contract, a record carrying the other version's name fails
   that contract. Records with no version id are listed as unversioned; their
   readers accept both names through `scope_of`.
4. **Reader.** `harness/scope.py` holds `scope_of`, `scope_list`, `scope_key`
   and `LEGACY_SCOPE_KEY`. Every Python reader of a persisted or received record
   goes through it. The desktop app has the same helper in
   `desktop/lib/models/scope_field.dart`.
5. **The older name in code.** The literal `does_not_prove` appears only in
   `harness/scope.py`, the desktop helper, the allowlisted artifacts below, and
   historical documents. `scripts/check_scope_migration.py` enforces it in CI.
6. **Identifiers.** `DOES_NOT_PROVE` constants become `SCOPE`; `does_not_prove()`
   functions become `scope()` (or a module-local name when `scope` is taken);
   `OracleResult.does_not_prove` becomes `OracleResult.scope`. Test names follow.
7. **Printed text.** The `limits:` heading from #429 becomes `scope:`.
8. **Sealed bytes.** Every artifact listed under "Kept bytes" stays byte for
   byte. Its verifier reads it with the old vocabulary and it still verifies.

## Kept bytes

These artifacts are sealed, anchored, hash-pinned, captured from a real run, or
historical records. They keep their exact bytes and their old field name.

- [x] `artifacts/anchor/head-0008-*.json`: anchored tree head and Rekor entries.
- [x] `artifacts/audit/`, `artifacts/closeout/FW-2026-08-02-CLOSEOUT/**`: closeout receipts.
- [x] `artifacts/pool/zarankiewicz/*/run_manifest.json`, `artifacts/prereg/determinism-pins.json`: preregistered runs.
- [x] `project-docs/lanes/evidence/*.json`, `project-docs/records/**`: CI and local evidence records.
- [x] `tests/fixtures/raw_native/**`, `tests/fixtures/superstack/receipt.json`, `tests/fixtures/pysyft_receipt/**`, `tests/fixtures/receipt_v3_legacy_fixtures.json`: captured receipts.
- [x] `tests/fixtures/native_agent_trace/**`, `tests/fixtures/gateway_effect_evidence/**`, `tests/fixtures/gateway_run_outcome/**`: v1 projections, kept as the old-version fixtures.
- [x] `desktop/test/fixtures/*.json`: v1 desktop fixtures, kept as old-version fixtures.
- [x] `docs/art/receipts.json`: sealed by the art producer.
- [x] `harness/_vendor/superstack.py`: vendored, pinned in `VENDORED.sha256`; changes upstream first.
- [x] `desktop/assets/rowan/action-cues/**`: recorded voice pack; the clip id names a recorded line.

- [x] `packaging/bundled-lanes/relay.json`: v1 descriptor, hash-pinned in `harness/bundled_lane_expectations.py`; the builder emits its frozen v1 list.
- [x] `harness/shapley_far.py` and `scripts/shapley_placebo_run.py`: pinned by their LF bytes in the Shapley placebo preregistration. `harness/incentive_manifest.py` keeps `SCHEMA` (v1) and its older list beside `SCHEMA_V2`/`SCOPE`, and `attribution_far.py` keeps the `FAR_DOES_NOT_PROVE` alias, because the pinned file names them.
- [x] `docs/schemas/environment-incentive-manifest-v1.json`: the v1 schema, beside the new v2 file.
- [x] The byte manifest `tests/fixtures/scope_migration_kept_bytes.sha256` (71 files, recorded from origin/main) is checked by `tests/test_scope_migration.py`.

## Schemas

Per cluster: schema id, old version, new version, reader change, and the test
that reads an old record.

- [x] Every cluster below is migrated; each row comes from that cluster's report.
### Core (receipts, oracles, certificates)

| schema | old -> new | reader change | old-record test |
|---|---|---|---|
| flywheel.receipt | v4 -> v5 (v3, v4 still read) | `Receipt.scope()` derives positive codes (receipt_scope.py); v3/v4 read with their sealed `NOT_PROVES_*` list; the other version's key is refused | test_receipt_v3_compatibility, test_scope_migration v4 round trip |
| flywheel.routed-receipt | v1 -> v2 | lane scope codes; v1 keeps its lane limits and digest | test_a_v1_routed_receipt_still_reads_with_its_limits |
| flywheel.unverifiable-record | v1 -> v2 | writer only | test_unverifiable_record |
| flywheel.oracle-qa-card | v2 -> v3 | card hash per version; v2 reads with its key | test_a_v2_card_reads_back_with_its_older_name_and_hash |
| flywheel.receipt-operations (MCP output) | v1 -> v2 | per-outcome scope | test_local_mcp |
| flywheel.run-budget, flywheel.run-completion | v1 -> v2 | gateway readers accept v1 and v2 | gateway fixtures (v1) |
| flywheel.product-e2e-run | v1 -> v2 | writer only | test_e2e_gather_context_journeys |
| flywheel.receipting-cost | v1 -> v2 | offline_suites reads through `scope_list` | test_benchmark_surface |
| OracleResult, certificate results, why, flywheel_op, Lean and measurement oracles | unversioned | `.scope`; `BOUND_FROM_SUBMITTED_OBJECT` replaces the optimality code | test_certificate_base, test_instance_binding, test_why |
| superstack receipts (raw lane) | unchanged | vendored schema keeps its field and limits until superstack moves | test_scope_migration superstack receipts |

### Witnesses, anchors, ledger, bundles, journeys, evidence packets

| schema | old -> new | reader change | old-record test |
|---|---|---|---|
| flywheel.byte-witness-chain-verification | v1 -> v2 | verifier output only; no reader | n/a (no stored v1) |
| flywheel.acp-witness | v1 -> v2 (`WITNESS_SCHEMA_V1` kept) | no reader of the summary | n/a |
| flywheel.dap-witness | v1 -> v2 | no reader | n/a |
| flywheel.lsp-witness | v1 -> v2 | no reader | n/a |
| flywheel.lsp-edit | v1 -> v2 (`EDIT_SCHEMA_V1`) | no reader | n/a |
| flywheel.anchor | v1 -> v2 (`SCHEMA_V1`) | readers never read the field | kept artifacts/anchor/head-0008-anchor.json untouched; test_anchor / test_flywheel_anchor_cli pass |
| flywheel.rekor-anchor | v1 -> v2 (`SCHEMA_V1`) | `verify_record` never reads the field or schema | kept head-0008-rekor-*.json untouched; rekor tests pass |
| flywheel.signer-anchor | v1 -> v2 (`RECEIPT_SCHEMA_V1`) | no reader | n/a |
| flywheel.audit-receipt | v1 -> v2 (`SCHEMA_V1`, `SCHEMAS`) | `verify_audit_receipt` accepts both; v1 must carry the old key only, v2 `scope` only | tests/test_audit_receipt.py: resealed v1, mixed-name refusal, and the v1 audit receipts inside desktop/test/fixtures/process_audit_resealed_*.json verify MATCH |
| flywheel.audit-run | v1 -> v2 (`AUDIT_RUN_SCHEMA_V1`) | route response; Dart reads it | n/a |
| flywheel.check-receipt | v1 -> v2 (`SCHEMA_V1`); field `CheckReceipt.scope`, constant `SCOPE` | no stored reader | n/a |
| flywheel.bundle | v1 -> v2 (`SCHEMA_V1`); `LIMITS` -> `SCOPE` | `verify_bundle` returns `scope_list(manifest)` | test_bundle: v1 manifest still MATCH |
| flywheel.evidence-packet (journey packets) | v1 -> v2 | new `harness/evidence_packet_vocab.py` holds both vocabularies (v1 lists frozen byte for byte, incl. the old PYTHON_LIMITS text); verifier dispatches on criterion schema; mixed names DRIFT | new tests/test_evidence_packet_scope_versions.py |
| flywheel.evidence-check | v1 -> v2 (`CHECK_SCHEMA_V1`) | none | n/a |
| flywheel.evidence-packet + custody manifest/receipt | packet v1 -> v2, custody-manifest v1 -> v2, custody-receipt v1 -> v2; profile custody/v2 unchanged | new `harness/journey_packet_vocab.py`; verifier picks vocabulary by manifest schema; exact key set per version | tests/test_journey_packet_v2.py: rewritten v1 packet rechecks MATCH, v1 manifest with `scope` fails |
| flywheel.evidence-journey-export | v2 -> v3 (`EXPORT_SCHEMA_V2`) | none in Python | n/a |
| unversioned: journey_projection fact/claim/check records (inside hash-chained events) | either name, never both | `scope_of` + both-names refusal | test_journey_projection_v2: legacy-key record reduces, both-names fails |
| flywheel.pysyft-job-result | v1 -> v2 (`SCHEMA_V1`, `SCOPE_V1` frozen) | `jr.scope_for(schema)` + `has_both`; failure code `schema_or_limits` -> `schema_or_scope` | kept tests/fixtures/pysyft_receipt/receipt.json verifies; new tests/test_job_result_scope_versions.py (v2 resigned MATCH, both names DRIFT) |
| flywheel.red-check | v1 -> v2 (`SCHEMA_V1`) | none | n/a |
| flywheel.rederive-verdict | v1 -> v2 (`VERDICT_SCHEMA_V1`) | none | n/a |
| flywheel.harness-edit-receipt | v2 -> v3 (`SCHEMA_V2`; SCHEMAS has v1, v2, v3) | verifier accepts all three | tests/test_self_improve_library.py v1 GOOD passes |
| flywheel.verification-share-report | v1 -> v2 (`REPORT_SCHEMA_V1`) | renderer uses `scope_of` | n/a |
| flywheel.verified-bench / verified-frontier / replicate-sd | v1 -> v2 each (`*_V1` kept) | skill_evidence already accepts bench v1+v2 | n/a |
| flywheel.source-context-private / -projection / -worker-payload | v1 -> v2 each (binding unchanged) | store accepts both private schemas; `projection_for` projects a v1 private record in v1 vocabulary so stored v1 records still validate | test_source_context_payload_ranges: v1 private -> v1 projection |
| flywheel.subagent-swarm | v1 -> v2 (`SWARM_SCHEMA_V1`, `SWARM_SCHEMAS`) | subagent_store load, subagent_fanin recheck, pm_roadmap accept both | test_pm_roadmap keeps a v1 row |
| flywheel.subagent-route-evidence | v1 -> v2 | none | n/a |
| flywheel.bundled-lane-component-summary | v1 -> v2 | in-process only | n/a |
| unversioned: tree_head / ledger / rekor / zenodo / anchor_zenodo / acceptance_criteria / byte/action witness scope() functions, router_agent action_witness block, tool_mcp status, self_improve gate/stream, acp turn | renamed, positive codes | n/a | n/a |

### Gateway, continuation, context, routing, endpoint, sessions

| schema | old -> new | reader change | old-record test |
|---|---|---|---|
| flywheel.gateway-agent-mcp-admission | v1 -> v2 | `_validate_plan` picks the tool key by schema (`_TOOL_SCOPE_KEY`); v1 tool rows need the older key, v2 rows need `scope`; mixed fails `AGENT_BINDING_DRIFT` | `server_scope_v1_still_validates` in tests/test_gateway_agent_mcp_admission.py |
| flywheel.gateway-mcp-discovery-receipt | v1 -> v2 | `freeze_receipt` closes the field set per version (`_RECEIPT_SCOPE_KEY`) | `test_v1_discovery_receipt_still_loads_and_mixed_names_fail` |
| flywheel.gateway-agent-mcp-admission-review | v1 -> v2 | review reads plan tools through `scope_list` (v1 plans project fine) | via the v1 plan test above |
| flywheel.agent-mcp-catalog | v1 -> v2 | response only (desktop reads it) | n/a (live response) |
| flywheel.agent-mcp-discovery-response | v1 -> v2 | receipt review reads `scope_list(receipt)` | n/a (live response) |
| flywheel.gateway-agent-model-call | v1 -> v2 | `subagent_gateway_child.route_evidence` accepts both (`_MODEL_CALL_SCHEMAS`) | existing subagent tests |
| flywheel.gateway-native-provider-response | v1 -> v2 | no reader of the list | n/a |
| flywheel.gateway-agent-projection | v1 -> v2 | `projection(..., schema=)`; `validate_projection` rebuilds with the submitted version's vocabulary; `gateway_effect_binding` and `gateway_effect_offline` accept `SCHEMAS` | `test_kept_v1_projection_fixtures_still_validate` (tests/fixtures/native_agent_trace/*.json), `test_v2_projection_names_scope_and_rejects_the_older_key` in tests/test_gateway_scope_versions.py |
| flywheel.gateway-effect-evidence | v1 -> v2 | `derive_effect_evidence(..., schema=)`; `validate_effect_evidence` recomputes in the submitted version | `test_effect_evidence_v1_recomputes_and_v2_carries_scope_label` |
| flywheel.gateway-agent-trace-detail | v1 -> v2 | route response only | n/a |
| flywheel.rowan-handoff | v1 -> v2 | response only; `DOES_NOT_PROVE` -> `SCOPE` | n/a |
| flywheel.codex-managed-no-auth-bootstrap-receipt | v1 -> v2 | written, not read back | n/a |
| flywheel.codex-config-inspection | v1 -> v2 | `.does_not_prove` property -> `.scope` | n/a |
| flywheel.context-memory-preflight | v1 -> v2 | Canon reply read via `scope_list(canon)`; scripts/frozen_gateway_context_smoke.py accepts both | smoke tests use a v1 fake and pass |
| flywheel.native-continuation-context, -context-projection, -runner-context, -intake, -private-context, -start | v1 -> v2 each | `continuation_agent_handoff._runner` accepts `RUNNER_CONTEXT_SCHEMAS` | `test_a_v1_runner_context_still_hands_off` |
| flywheel.endpoint | v1 -> v2 | family results read with `scope_list(r)`; scripts/render_report.py already accepts v1 and v2 | tests/test_anchor_confirmatory.py builds a v1 doc and passes |
| harness.local-finalizer-invocation-accounting | v1 -> v2 | no reader | n/a |
| harness.native-routing-task-family-manifest | v1 -> v2 | `render_markdown` reads `scope_list(manifest)`, heading `## Scope` | n/a |
| flywheel.pytest-runtime | v1 -> v2 | `validate_runtime_descriptor` closes the field set per version (`_VERSIONS`), v1 must carry `RUNTIME_SCOPE_V1` | `test_v1_descriptor_still_validates_and_mixed_names_fail` |
| flywheel.runtime-identity (rerun witness) | v1 -> v2 | no reader of the list | n/a |
| harness.ollama-manifest-digest-provenance | v1 -> v2 | `validate_release_identity_provenance` accepts both (`RELEASE_IDENTITY_SCHEMAS`) | `test_v1_release_digest_provenance_still_validates` |
| m7-routing-split-plan | v1 -> v2 | no reader of the list | n/a |
| harness.session-summary | v1 -> v2 | `render_markdown` reads the window via `_window` and the list via `scope_list` | `test_v1_summary_renders_its_window_and_older_list` |
| harness.cross-harness-fixture.shared-task-artifact-v2-participant | v1 -> v2 | closed limitation ids renamed in checker, fixture and test together | see note below |
| unversioned: gateway_cli_events.NativeEvents.finish result | rename | `scope: [TRACE_AS_RECORDED, SINGLE_CLI_SESSION]` | n/a |
| unversioned: loop_closure.loop_closure result | rename | string stays string | n/a |
| unversioned: served_model_provenance.analyze result | rename | `SMP_DOES_NOT_PROVE` -> `SMP_SCOPE` | n/a |
| unversioned: python_execution_containment.unavailable_result (`flywheel.evidence-check/v1`, shared with evidence_packet) | rename | `LIMIT` -> `SCOPE` | tests/test_evidence_packet_containment.py |
| unversioned: router_agent action_witness block (schema `flywheel.byte-witness/v1`) | rename | uses `action_witness.scope()` | see open items |
| unversioned: run-budget and run-completion reports read by gateway_run_outcome / gateway_completion_outcome | reader only | key set closed as base keys plus exactly one of `scope` / older key; schema accepted from `{current, .../v1}` | tests/fixtures/gateway_run_outcome/stopped_projection.json (v1 budget report) still derives |
| unversioned: pytest receipt extra list | reader only | `pytest_result_validation` reads `receipt.extra_scope` and accepts the full `PYTHON_SCOPE` or `PYTHON_SCOPE_V1` | evidence packet tests |

### Bulletin, incident sim, institutional access, decisions, domain packs, standards, monitor gate

| schema | old -> new | reader change | old-record test |
|---|---|---|---|
| flywheel.bulletin-access-denial | v1 -> v2 (`DENIAL_SCHEMA`, `DENIAL_SCHEMA_V1`) | writer only, no Python reader | none (no reader) |
| flywheel.bulletin-model-campaign | v1 -> v2 (`SCHEMA`, `SCHEMA_V1`) | writer only | none (no reader) |
| flywheel.outcome-bulletin-request | v1 -> v2 (`REQUEST_INPUT_SCHEMA`, `_V1`) | `_normalize` takes each version with its own key only (`_SCOPE_BY_SCHEMA`). v1 renders the list under "Limits:", v2 under "Scope:" | `tests/test_outcome_bulletin.py` (INDEX_OUTCOME stays v1, its body still says "Limits:"); `tests/test_outcome_bulletin_scope.py` (v2 renders "Scope:", wrong key per version refused) |
| flywheel.outcome-bulletin-preview | stays v1 | the preview has no scope field; a v2 request's body says "Scope:" | covered by the two tests above |
| flywheel.outcome-bulletin-publication | v1 -> v2 (`PUBLICATION_SCHEMA`, `_V1` in outcome_bulletin.py; signed_transport and media_core import it; outcome_bulletin_media.py constant updated) | writer only in Python | `test_publication_records_are_v2_with_scope` |
| flywheel.bulletin-media-review | v1 -> v2 (`REVIEW_SCHEMA`, `REVIEW_SCHEMA_V1` in media_core; outcome_bulletin_media.py constant updated) | no Python reader of the review's scope | none in Python; Dart reads it (see below) |
| flywheel.bulletin-task-result | v1 -> v2 (`RESULT_SCHEMA`, `_V1`); `LIMITS` -> `SCOPE` | `bulletin_task_review` reads it through `scope_list` | none (no stored v1 results in repo) |
| flywheel.bulletin-task-review | v1 -> v2 (`REVIEW_SCHEMA`, `_V1`); its Journey facts, claims and checks carry `scope` | `tests/test_bulletin_model_fixture.py` updated to v2 | needs cluster A's Journey v2 reader to accept `scope` (it does now; tests pass) |
| flywheel.decision-result | v1 -> v2 (`RESULT_SCHEMA`, `RESULT_SCHEMA_V1`); `DOES_NOT_PROVE` -> `SCOPE` | `decision_evaluation._valid_result` takes v1 with the older key and v2 with `scope`, exact key set per version | `test_v1_and_v2_results_are_each_read_with_their_own_key`; the `case()` helper still builds v1 results |
| flywheel.decision-evaluation | v1 -> v2 (`EVALUATION_SCHEMA`, `_V1`) | writer only | n/a |
| flywheel.decision-control-report | v1 -> v2 (`CONTROL_REPORT_SCHEMA`, `_V1`); `_CONTROL_DISCLAIMERS` -> `_CONTROL_SCOPE` | writer only | n/a |
| unversioned: grant_route record_claim command | claim item carries exactly one of `scope` or the older key | `_client_item` accepts either key, never both, and keeps the client's key | existing grant tests send the older key and pass |
| unversioned: grant_route concluded payload | `conclusion.scope` | Journey projection stores it as given | n/a |
| flywheel.incident-proposed-graph | v1 -> v2 (`PROPOSAL_SCHEMA`, `_V1`) | no Python reader; graph_sha256 covers it, persisted proposals stay immutable | desktop fixtures keep v1 bytes |
| flywheel.incident-sim-command | v1 -> v2 (`COMMAND_SCHEMA`, `_V1`) | stdout report only | n/a |
| flywheel.incident-sim-verify-command | v1 -> v2 (`VERIFY_COMMAND_SCHEMA`, `_V1`) | stdout report only | n/a |
| flywheel.incident-sim-evaluation | v1 -> v2 (`SCHEMA`, `SCHEMA_V1`) | packet verifier is digest-only | desktop fixtures keep v1 bytes and their digests still recheck |
| flywheel.audit-receipt (cluster A) | A's v2; packet now calls `build_audit_receipt(scope=...)` (A wrote that line) | `incident_sim_packet_verify._AUDIT_KEYS` orders both keys through `LEGACY_SCOPE_KEY`/`SCOPE_KEY` | A's tests |
| flywheel.incident-sim-process-audit | stays v1 | packet has no top-level scope field; nested components carry their own versions | existing packet tests |
| flywheel.institutional-access-assessment | v1 -> v2 (`ASSESSMENT_SCHEMA`, `_V1`); `_DOES_NOT_PROVE` -> `_ASSESSMENT_SCOPE` | `incident_sim_process_audit_route._declared_access`: a v1 list is appended to `limits` (old behavior); a v2 list goes to `declared_access.scope` | `test_review_route_reads_a_v1_assessment_list_as_limits` |
| flywheel.incident-sim-process-audit-review | v1 -> v2 (`REVIEW_SCHEMA`, `_V1`); `_DOES_NOT_PROVE` -> `_REVIEW_SCOPE` | response only | n/a |
| flywheel.domain-pack (manifest) | v1 -> v2 (`SCHEMA`, `SCHEMA_V1`, `SCHEMAS`) | `_scope_field` picks the key per version and refuses the other key; QA accepts both | `test_v1_manifest_is_admitted_with_its_older_key`, `test_a_v2_manifest_carrying_the_older_key_is_refused`, `test_a_v1_manifest_carrying_scope_is_refused` |
| flywheel.domain-pack-qa | v1 -> v2 (`QA_SCHEMA`, `_V1`) | writer only | `tests/test_first_domain_packs.py` updated to read `qa["scope"]` |
| flywheel.environment-incentive-manifest | v1 -> v2 (`SCHEMA_V2`, `SCHEMA_V1`; **`SCHEMA` stays the v1 id**, see note) | `validate` picks the key per version (`SCOPE_KEY_BY_SCHEMA`), exact field set per version | `test_v1_manifest_with_its_older_key_still_validates_and_rechecks`; mutation cases refuse v2+older key and v1+scope |
| unversioned: incentive_manifest.recheck result | `scope: SCOPE` | n/a | n/a |
| flywheel.non-coercive-environment-certificate | v1 -> v2 (`NCEC_SCHEMA`, `NCEC_SCHEMA_V1`); `CED_DOES_NOT_PROVE` -> `CED_SCOPE`, `NCEC_DOES_NOT_PROVE` -> `NCEC_SCOPE`, `MANIFEST_BOUND` -> `MANIFEST_SCOPE` | `_validate_certificate` takes v1 with the older key and its exact v1 text (`_NCEC_V1_BOUND`, verbatim) and v2 with `scope` and `NCEC_SCOPE` | `test_v1_certificate_with_its_older_key_and_bound_still_verifies` |
| unversioned: coercive_environment.detect / verify_certificate results | `scope` | n/a | n/a |
| flywheel.receipt (lead) inside flywheel.monitor-gate-result | gate doc stays v1; its receipt is v5 with `extra_scope=SCOPE`; `LIMITS` -> `SCOPE` (positive codes) | `verify` rebuilds an older v4 receipt with its sealed `_V4_EXTRA` codes | `test_a_v4_gate_result_still_rederives_with_its_sealed_codes` |
| flywheel.monitor-outcome | v1 -> v2 (`SCHEMA`, `SCHEMA_V1`, `SCHEMAS`); `DOES_NOT_PROVE` -> `SCOPE` | `attach_outcomes` and `exclude_samples` accept both versions | none added (no stored records) |
| flywheel.norvane-capture-review | v1 -> v2 (`SCHEMA`, `SCHEMA_V1`); `LIMIT` -> `SCOPE_TEXT` | no reader | `test_v2_review_names_scope_once_per_record` |
| flywheel.standards-profile | v1 -> v2 (`PROFILE_SCHEMA`, `_V1`, `PROFILE_SCOPE_KEYS`) | `standards_profile.profile_scope_key`; root and requirement field sets get the version's key only | `test_v1_and_v2_profiles_each_validate_with_their_own_key` |
| flywheel.standards-profile-validation | v1 -> v2 (`VALIDATION_SCHEMA`, `_V1`; registry fail-closed path uses it) | writer only | `tests/test_standards_cli.py` updated |
| flywheel.standards-assessment | v1 -> v2 (`ASSESSMENT_SCHEMA`, `_V1`) | per-requirement `scope`: the requirement's own string for a v2 profile; a fixed positive sentence (`_V1_REQUIREMENT_SCOPE`) for a v1 profile, so a v2 assessment never carries v1 limit text | `test_requirement_scope_follows_the_profile_version` |

### Evaluation guard, inspect, skills, workstream, writing lane

| schema | old -> new | reader change | old-record test |
|---|---|---|---|
| `flywheel.evaluation-admission` | v1 -> v2 (`SCHEMA`, `SCHEMA_V1`; `LIMIT` -> `SCOPE`) | writer only; no repo reader | none needed (no stored readers) |
| `flywheel.memory-context` | v1 -> v2 | writer only (evolutionary_flywheel metadata) | none needed |
| `flywheel.frontier-axes` | v1 -> v2 | writer only | none needed |
| `flywheel.inspect-evidence` | v1 -> v2 (`SCHEMA_V1` kept); `_does_not_prove` -> `_scope`, adds "complete coverage" entry when coverage is complete | `desktop/tool/installed_launch_inspect.py` accepts v1 and v2 | `tests/test_inspect_desktop_contract.py`: kept v1 desktop fixture compared to fresh v2 output, field by field |
| `flywheel.inspect-scorer-unit-analysis` | v1 -> v2 (`REPORT_SCHEMA_V1` kept) | writer only in Python | none in Python |
| `flywheel.plan-run-receipt` / `plan-run-result` | v2 -> v3 (`*_V2` kept); `PLAN_LIMITATIONS` -> `PLAN_SCOPE`, old list kept as `PLAN_LIMITATIONS_V2` | `verify_plan_result` maps result schema to receipt schema and reads each with its own key and list; exact field set per version | `tests/test_plan_run_contract.py::test_a_stored_v2_result_still_verifies_and_only_under_its_own_key` |
| `flywheel.pm-roadmap` | v1 -> v2 (`SCHEMA_V1` kept) | `render_markdown` reads `scope_list(doc)`; heading `## Limits` -> `## Scope` | rendering goes through `scope_list`, reads either name |
| `flywheel.skill-gate` | v2 -> v3 (`SCHEMA_V2`, v1 `LEGACY_SCHEMA` kept); `LIMIT` -> `SCOPE`, old text `LIMIT_V2` | `verify_skill_gate` accepts v1 (UNVERIFIED), v2 (older key == `LIMIT_V2`, no `scope`), v3 (`scope` == `SCOPE`, no older key) | `tests/test_skill_evidence_binding.py::test_a_sealed_v2_row_still_verifies_under_its_own_key_and_text` |
| `flywheel.verified-bench` (read by skill_evidence) | owned by A; accepts v1 and v2 | `skill_evidence` reads `scope_of(bench)`, `BENCH_SCHEMAS = (v1, v2)` | existing bench tests (A's producer) |
| `flywheel.task_set_executability` | v1 -> v2 (`SCHEMA_V1` kept) | `render_markdown` reads `scope_list`; heading `## Limits` -> `## Scope`; `scripts/run_harness_cli.py` catalog lists v2 | none needed (no stored reader) |
| `flywheel.workstream` (receipt) | v1 -> v2 (`SCHEMA_V1` kept) | CLI reads `scope_list`; `limits:` -> `scope:` | CLI rendering reads either name |
| `flywheel.workstream.audit` | v1 -> v2 (`AUDIT_SCHEMA_V1` kept) | same | same |
| `flywheel.writing-{project-brief, source-packet, revision, reader-flow-diagnostic, scoped-revision, revision-candidate, decision, review, export}` | v1 -> v2 (`SCHEMAS_V1`, `LEGACY_SCHEMAS`); `flywheel.writing-section/v1` unchanged (no list) | `writing_types.scope_field(value)` picks the key by version; `_exact` field sets enforce it, so v1 must carry the older key and v2 must carry `scope`; error code `SCOPE_INVALID` | `tests/test_writing_type_controls.py::test_v1_artifacts_still_validate_under_the_older_key_and_only_there` |
| `flywheel.writing-project-view` | v1 -> v2 | the nested source packet carries its own key (`scope_key(packet): scope_of(packet)`) | covered by route tests |
| unversioned: `writing_projection._apply_decision` revision row | carries the candidate's own key; schema v1/v2 follows the candidate | `scope_key(candidate)` | via v1/v2 validation |
| unversioned: `writing_reader_flow.scope_replacement_plan` | `scope` string | validator checks verdict only | n/a |
| unversioned: `writing_artifacts` journey fact | `scope` | A's `journey_projection._require_record` now reads `scope_of` | journey tests |
| unversioned: `writing_lint` JSON / MCP lint record | `DOES_NOT_PROVE` -> `SCOPE`, key `scope` | no repo reader | n/a |
| unversioned: attribution_far, dataset_provenance, internal_consistency, internalization_gap, intervention_ablation outputs | `*_DOES_NOT_PROVE` -> `*_SCOPE`, key `scope` | no repo reader | n/a |
| Articulate host-edit receipt (read in `tests/test_articulate_published_baseline.py`) | pinned Articulate v0.6.0 writes the older key; #71 writes `scope` | test reads either: older key gets the `semantic equivalence` check, `scope` gets a non-empty check | the v0.6.0 staged-source test itself (skips when source is not staged) |

### Statistics, Shapley, pool, cost floor, contests, cross-harness, train/

| schema | old -> new | reader change | old-record test |
|---|---|---|---|
| flywheel.classifier-split-manifest | v1 -> v2 (`MANIFEST_SCHEMA_V1`, `MANIFEST_SCHEMAS`), `DOES_NOT_PROVE` -> `SCOPE` | `train/classifier_encoder_cli.py` accepts `MANIFEST_SCHEMAS` | `tests/test_classifier_encoder_cli.py::test_cli_accepts_a_v1_split_manifest_under_the_older_scope_key` (needs torch; skipped here, torch is not installed) |
| flywheel.classifier-probability-metrics | v1 -> v2 (`SCHEMA_V1`) | no reader | n/a |
| flywheel.classifier-linear-baseline | v1 -> v2 (`ARTIFACT_SCHEMA_V1`); exact key sets `ARTIFACT_KEYS` / `ARTIFACT_KEYS_V1` | `from_json_dict`: a v1 artifact must carry the legacy key and match its own v1 checksum, then loads as a v2 model under the v2 checksum. A v1 record that carries `scope` fails. | `tests/test_classifier_model.py::test_a_v1_artifact_loads_under_its_own_checksum_and_rejects_tampering` |
| flywheel.classifier-score-envelope | v1 -> v2 (`SCORE_SCHEMA_V1`, `SCORE_SCHEMAS`) | `proposal_from_score_envelope` accepts both | n/a (covered by existing envelope tests) |
| flywheel.classifier-training-report | v1 -> v2 (`TRAINING_REPORT_SCHEMA[_V1]`) | no reader | n/a |
| flywheel.classifier-workflow-shadow | v1 -> v2 (`WORKFLOW_SHADOW_SCHEMA[_V1]`), string | no reader | n/a |
| unversioned: classifier_calibration.fit_temperature / select_threshold | string renamed | no reader | n/a |
| flywheel.contest-series | v1 -> v2 (`SERIES_SCHEMA[_V1]`), `SERIES_LIMITS` -> `SERIES_SCOPE` (codes WRITTEN_OBJECTIONS_COUNTED, LOGGED_CONTESTS_ONLY) | no reader | n/a |
| flywheel.cost-floor | v1 -> v2 (`SCHEMA_V1`), `DOES_NOT_PROVE` -> `SCOPE` (string). The summary id stays `flywheel.cost-floor/v1#summary` (`SUMMARY_SCHEMA`) because the summary carries no scope list. | no reader | n/a |
| harness.null-floor-report | v1 -> v2 (`SCHEMA_V1`) | `scripts/run_harness_cli.py` schema list -> v2 | n/a |
| harness.cross-harness-output-diagnostics | v1 -> v2 (`SCHEMA`/`SCHEMA_V1` added); nested `runtime.length_cap_reached.scope` | no reader | n/a |
| harness.cross-harness-postrun-comparison | v1 -> v2 (`SCHEMA_V1`) | no reader | n/a |
| harness.cross-harness-postrun-intended-matrix | v1 -> v2 (`SCHEMA_V1`, `SCHEMAS`) | `harness/cross_harness_postrun_checks.py` accepts `INTENT_SCHEMAS` | the existing `tests/test_cross_harness_postrun.py::test_postrun_validator_rejects_byte_valid_oracle_and_metrics_artifact_mismatch` writes a v1 matrix |
| flywheel.graded_metric_report | v1 -> v2 (`SCHEMA_V1`), `DOES_NOT_PROVE` -> `SCOPE`; `## Limits` -> `## Scope` | `render_markdown` reads through `scope_list` | `tests/test_graded_metric_report.py::test_a_v1_record_still_renders_its_list_under_the_older_key` |
| flywheel.statistics (between_seed_sd, sd_from_range, cluster_bootstrap, mcnemar_mde, mcnemar_plan) | v1 -> v2 (`SCHEMA_V1`). The `NOT_PROVES_*` codes become ONE_PIPELINE_ONE_MACHINE, RANGE_DERIVED_SIGMA, D2_CONVERSION, WITHIN_PASS_VARIANCE, DESIGN_SENSITIVITY, PLANNED_ON_RECORDED_DISCORDANCE | `harness/verified_bench.py:215` reads `stat["scope"]` (one-line edit) | n/a (no persisted v1 records) |
| flywheel.pair-voiding, flywheel.holm-bonferroni | v1 -> v2 (`*_SCHEMA_V1`), codes MODEL_OBSERVED_FROM_EVENTS, CROSS_ARM_EQUALITY, DECLARED_FAMILY_ONLY | no reader | n/a |
| flywheel.paired-comparison | v1 -> v2 (`SCHEMA_V1`), codes THIS_TASK_SET, PER_TASK_DESCRIPTIVES; `flywheel.inner-call-budget/v1` unchanged (it has no scope list) | no reader | n/a |
| unversioned: pool.Pool | method `does_not_prove()` -> `scope()`, codes GENERATION_SETTINGS_PINNED, CANDIDATES_ONLY, THESE_TASKS | the only caller was a test | n/a |
| flywheel.pool-arm | v1 -> v2 (`SCHEMA_V1`), pass_at_k code FIXED_POLICY_SAMPLING | `scripts/render_report.py` (F) already accepts v1 and v2 | the existing test_render_report / test_anchor_confirmatory v1 stubs |
| unversioned: reward_gap.analyze | `ERG_DOES_NOT_PROVE` -> `ERG_SCOPE` | no reader | `tests/test_reward_gap.py::test_a_v1_manifest_under_the_older_key_still_analyzes` (a v1 incentive manifest as input) |
| unversioned: scorecard_rebuild.rebuild | `DOES_NOT_PROVE` -> `SCOPE`. Not bumped: the document carries `harness.cross-harness-task-scorecard/v1`, which many other writers emit without a scope list. | readers use `rows` only | n/a |
| flywheel.classifier-benchmark | v1 -> v2 | no reader | n/a |
| flywheel.classifier-synthetic-corpus-manifest | v1 -> v2 (`CORPUS_MANIFEST_SCHEMA[_V1]`), `DOES_NOT_PROVE` -> `SCOPE` | no reader | n/a |
| flywheel.classifier-encoder-artifact | v1 -> v2 (`ARTIFACT_SCHEMA_V1`, `MANIFEST_KEYS_V1`) | `_check_manifest_shape` uses the exact key set for each version; the checksum covers the stored body | none run (torch-gated module) |
| flywheel.classifier-encoder-training-report | v1 -> v2 | no reader | n/a |
| flywheel.classifier-encoder-score-envelope | v1 -> v2 in `train/classifier_encoder.py` (`SCORE_SCHEMA_V1`) | no reader | n/a |
| flywheel.classifier-token-experiment | v1 -> v2 | no reader | n/a |
| flywheel.classifier-workflow-development-corpus | v1 -> v2, `DOES_NOT_PROVE` -> `SCOPE` | no reader | n/a |
| flywheel.classifier-workflow-experiment | v1 -> v2. The old string label `"scope": "synthetic_local_state_machine"` moves to `"scope_label"` with its value unchanged, and the list takes `scope`. A v1 record still reads right, because `scope_key` prefers the legacy key when both names are present. Nothing read the old label. | no reader | n/a |
| unversioned: classifier_workflow_outcome check_outcome result | `DOES_NOT_PROVE` -> `SCOPE` | no reader | n/a |
| unversioned: classifier_model / classifier_dataset / classifier_corpus / classifier_workflow_data constants | `DOES_NOT_PROVE` -> `SCOPE` | no importers outside the tests | n/a |

### Preaction and trace observation

| schema | old -> new | reader change | old-record test |
|---|---|---|---|
| `flywheel.preaction-hold` | v1 -> v2 (`HOLD_SCHEMA_V1` kept) | `records.HOLD_SCHEMAS`, `ALLOW_SCHEMAS`, `ASSESSMENT_SCHEMAS`; verify.py, coverage.py (liveness join), witness.py (`_PRE`), trace_flag.verify_chain, overrides_report accept both | `test_preaction_escalate::test_v1_pre_records_still_count_for_readers` |
| `flywheel.preaction-allow` | v1 -> v2 (`ALLOW_SCHEMA_V1` kept) | same as hold | same test |
| `flywheel.preaction-outcome` | v1 -> v2 (`OUTCOME_SCHEMA_V1`, `OUTCOME_SCHEMAS`) | overrides.record_outcome duplicate check and overrides_report index accept both | covered by the same reader path (no dedicated v1 outcome test) |
| `flywheel.openshell-import` | v1 -> v2 (`IMPORT_SCHEMA_V1`) | no in-repo reader of the summary's scope; only tests compare `IMPORT_SCHEMA` | none needed (no reader) |
| `flywheel.preaction-traceflag` | v1 -> v2 (`TRACEFLAG_SCHEMA_V1`, `TRACEFLAG_SCHEMAS`) | trace_flag.verify_chain accepts both | `test_trace_observation_hook::test_v1_observation_receipt_in_an_existing_chain_still_reads` |
| `flywheel.preaction-witness` | v1 -> v2 (`WITNESS_SCHEMA_V1`) | no reader filters on it | none needed |
| `flywheel.observation-receipt` | v1 -> v2 (`receipt.SCHEMA_V1`, `SCHEMAS`; `trace_flag.OBSERVATION_SCHEMA_V1`, `OBSERVATION_SCHEMAS`) | `ObservationLedger.receipts` and `verify_chain` read both; `append` writes v2 only | same hook test (v1 receipt listed, seal verifies, backs a v1 flag) |
| `flywheel.measured-gap` | v1 -> v2 (`access_gap.SCHEMA_V1`) | observe.py reads `scope_of(gap)` for the receipt and the printed `scope:` line | via scope_of (no stored gaps outside receipts) |
| `flywheel.trace-regression` | v1 -> v2 (`REGRESSION_SCHEMA_V1`, `REGRESSION_SCHEMAS`) | `regression_report(..., schema=V1)` rebuilds a v1 report byte for byte; skill_evidence accepts both; skill_gate checks the bound digest against `summary_source_digests` (both versions) | `test_trace_bench::test_v1_regression_report_rebuilds_byte_for_byte`, `test_a_skill_gate_bound_to_a_v1_report_still_verifies` |
| `flywheel.trace-export` | v1 -> v2 (`trace_export_verify.SCHEMA_V1`) | verifier reads neither field name and never checked the schema; root digest covers whichever key is present | `test_trace_export::test_a_v1_manifest_still_verifies` |
| unversioned: escalate.review_payload | key renamed, positive `REVIEW_SCOPE` | TtyApprover reads `scope_of(payload)` | n/a (computed fresh; its digest is sealed in the decision record, never re-derived) |
| unversioned: overrides_report.summarize | key renamed | cli_overrides prints `scope: ...` | n/a |
| unversioned: trace_observation.channel.ReasoningRecord.to_dict | key renamed, `RECORD_SCOPE` | no reader | n/a |
| unversioned: behavioral.consistency / eval_awareness / observation, openweight.analysis results | key renamed, positive values | no reader | n/a |

### Scripts, packaging, packages, examples

| schema | old -> new | reader change | old-record test |
|---|---|---|---|
| flywheel.bundled-lane-component | v1 -> v2 (producer `scripts/_lane_payload_source.py` + `_lane_payload_row.py`, `SCOPE` with `T1_TOOLS_SERVED_AND_ALLOWED` etc.) | `harness/bundled_lane_descriptor.validate_descriptor` admits v1 and v2 (`COMPONENT_SCHEMAS`, `descriptor_scope_key`; the other version's key is refused); `scripts/check_python_lane_payload_manifest.py` same | relay.json stays v1 and admits (test_bundled_relay_*, test_lane_pins_*) |
| packaging/python-lane-payloads.jsonl rows | regenerated through `scripts/generate_python_lane_payload_row.py` at each row's pinned `owner_commit` from the C:/dev lane checkouts; only `component_descriptor` (schema, scope) and `component_descriptor_sha256` changed in all 12 rows; re-pinned | test_lane_payload_regenerate passes byte for byte | n/a (rows are now v2) |
| flywheel.fault-injection-audit | v1 -> v2 (`SCOPE`, `SCHEMA_V1`) | no reader | artifacts/audit kept v1 |
| service-desk-incident-env-review | v1 -> v2 (`REPORT_SCHEMA[_V1]` in review_report.py) | `harness/enterprise_envs/service_desk_review_route.py` accepts both (`REPORT_SCHEMAS`); review_html reads `scope` | route tests with a v1 `_complete_report` still pass |
| service-desk-task-review | v1 -> v2 | none | n/a |
| unversioned: review_consistency layer, source_integrity layer | renamed + positive | review_html | n/a |
| flywheel.native-mcp-bundle (payload-binding.json) | v1 -> v2 (`BINDING_SCHEMA[_V1]`) | check_native_mcp_bundle accepts both | n/a |
| flywheel.native-mcp-qualification | v1 -> v2 | none | n/a |
| flywheel.frozen-tool-mcp | v1 -> v2 (`SCHEMA[_V1]`) | check_installed_tool_profiles accepts both; reads tool output via `scope_list` | test_installed_tool_profiles mocks v1, passes |
| flywheel.frozen-articulate-check | v1 -> v2 | none | n/a |
| flywheel.frozen-gateway-smoke | v1 -> v2 | none (check_installed_canon_context builds its own v1 stub with no list; left) | n/a |
| flywheel.frozen-lane-smoke | v2 -> v3 (`SCHEMA_V2`) | none | n/a |
| flywheel.frozen-receipt-parity | v1 -> v2 | none | n/a |
| flywheel.source-tool-plugin (SOURCE.json) | v1 -> v2 | none | n/a |
| flywheel.source-tool-plugin-acceptance | v1 -> v2 | none | n/a |
| flywheel.codex-managed-no-generation-acceptance | v1 -> v2 (`SCOPE`, `SCHEMA_V1`) | none | n/a |
| arms report (flywheel.pool-arm, schema owned by D_stats) | key `family_not_proven` -> `family_scope`; per-rung `scope` with `UPLIFT_FROM_HELD_OUT_ARM_ONLY`, `PER_RUNG_NUMBERS` | render_report reads `family_scope` or `family_not_proven` (`_family_scope`), accepts pool-arm v1/v2 and endpoint v1/v2, prints `Scope:` | test_a_v1_arms_block_renders_its_family_list |
| compute_endpoint submit result | `scope` from `result.scope` (BOUND_FROM_SUBMITTED_OBJECT) | harness/endpoint.py (B) | n/a |
| flywheel.monitor-outcome-demo | v1 -> v2; reads record via `scope_list` | none | n/a |
| flywheel.determinism-pins | v1 -> v2 (`SCOPE`, `SCHEMA_V1`) | witness/baseline are field-agnostic | test_the_committed_v1_pin_file_still_reads (artifacts/prereg/determinism-pins.json kept) |
| flywheel.installed-app-lane-acceptance | v1 -> v2 (`installed_lane_verdict.scope()`, `SCOPE`) | make_installed_lanes_evidence accepts both (`RECEIPT_SCHEMAS`) | n/a |
| flywheel.installed-lanes-ci-evidence-summary | v1 -> v2 (`SCOPE`) | test_release_drafts reads committed v1 summary via `scope_list`; shape test maps the old key | test_release_drafts, test_make_installed_lanes_evidence |
| flywheel.acceptance-command | v1 -> v2 | none | artifacts/closeout kept v1 |
| flywheel.bulletin-e2e-controls (mjs) | v1 -> v2, emits `scope` | no Python reader of results.json exists in the repo (grep) | n/a |
| unversioned: run_closed_loop_benchmark_seed step record | string `scope` | none | n/a |
| harness.cross-harness-integration-map | v1 -> v2, `## Scope` | harness/schematic_drift.py accepts either marker (`INTEGRATION_MAP_SCHEMAS`) | n/a |
| harness.endpoint-auth-status | v1 -> v2 (nested ladder `scope` string) | integration map `PRIOR_SCHEMAS` admits v1; run_harness_cli lists v2 | test_a_v1_endpoint_auth_status_is_still_observed |
| flywheel.demo-pool-run | v1 -> v2 (`SCOPE`: CANDIDATES_CACHED, RUN_KIND_STAMPED) | none | artifacts/pool manifests kept v1 |
| unversioned: run_inspect_import_acceptance receipt | string `scope` | none | n/a |
| flywheel.skill-bundle (both builders) | v1 -> v2 | none | n/a |
| examples/index-outcome-bulletin.json | request v1 -> v2 (C1 reader) | C1 | C1 tests |
| examples/standards/synthetic-administrative-profile.json | standards-profile v1 -> v2 (C1 reader) | C1 | test_standards_* pass |
| packs/*/domain-pack.json (3) | domain-pack v1 -> v2 (C1 reader); no hash pin found | C1 | test_domain_pack, test_first_domain_packs, test_pack_admission pass |

## Re-pins and regenerated records

- [x] `scripts/source_tool_closure.json`: 12 reviewed modules changed and two joined (`harness/scope.py`, `harness/receipt_scope.py`); the closure holds 85 modules. The only new imports are those two modules.
- [x] `packaging/python-lane-payloads.jsonl`: 12 rows regenerated with the repo's generator at each pinned commit.
- [x] `harness/ollama-manifest-digest-provenance-v2.json` is the packaged record, with a recomputed self-hash; the self-hashed v1 file stays beside it with its bytes.
- [x] `docs/benchmarks/report.json`, `docs/BENCHMARKS.md`, `README.md`, `site/benchmarks.html`: regenerated with `scripts/run_offline_benchmarks.py` and `scripts/build_benchmark_page.py`. The run also folds in an `uplift_bench` entry that had already changed on main without a regeneration, and the timing figures are this machine's.

## Follow-ups outside this change

- superstack's receipt format (`harness/_vendor/superstack.py`) still names its list `does_not_prove`; the raw lane writes it with its original limits. It moves when superstack does.
- The site record keeps its `doesNotProve` field, which harperz9.github.io reads.
- The Rowan voice pack event `verify.does_not_prove` names a recorded line.

## Desktop, docs and gates

- [x] `desktop/lib/models/*.dart` parsers accept both names and both schema versions.
- [x] Public docs that describe the field say `scope`; historical plans, specs,
      release notes and records stay as written.
- [x] `scripts/check_scope_migration.py` runs in CI and passes.
- [x] `tests/test_scope_migration.py`: `scope_of` reads both names; old-version
      artifacts from "Kept bytes" still verify.
- [x] CHANGELOG carries the migration note.

## Counts

`python scripts/check_scope_migration.py --count` prints the occurrence count.

| | files | occurrences |
|---|---|---|
| before (origin/main d81cb104) | 615 | 1408 |
| after (feat/scope-migration), all allowlisted | 120 | 254 |
