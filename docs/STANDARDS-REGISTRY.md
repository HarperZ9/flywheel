# Standards Registry

The standards registry is a data-only profile and assessment surface. It lets a
caller submit a versioned requirement profile, explicit applicability facts, and
bounded mappings to Flywheel controls or evidence claims. It does not fetch
sources, reason from prose, certify legal compliance, or decide institutional
approval.

Use it from a checkout with:

```bash
python -m harness.standards_cli validate examples/standards/synthetic-administrative-profile.json
python -m harness.standards_cli assess examples/standards/synthetic-administrative-profile.json context.json --as-of 2026-09-16
```

The same entrypoint is available through `scripts/run_standards.py`. JSON is
read as UTF-8. Duplicate JSON keys and non-finite numbers are refused before
validation so an input cannot silently overwrite a field.

## Profile Shape

Profiles use `schema: flywheel.standards-profile/v1`. Required top-level fields
are `profile_id`, `title`, `version`, `owner`, `instrument`, `provenance`,
`effective`, `applicability`, `requirements`, and `does_not_prove`.

`instrument` separates the source's institutional role from its binding path:

- `instrument_kind`: `statute`, `regulation`, `binding_order`, `contract`,
  `procurement_clause`, `incorporated_standard`, `voluntary_standard`,
  `guidance`, `proposal`, `internal_policy`
- `issuer_role`: `legislature`, `regulator`, `standards_developer`,
  `accreditation_body`, `conformity_assessment_body`, `customer`,
  `internal_policy_owner`
- `binding_basis`: `statute`, `regulation`, `binding_order`,
  `contract_clause`, `procurement_clause`, `incorporation_by_reference`,
  `voluntary_adoption`, `guidance`, `proposal`, `internal_policy`
- `binding_review_status`: `not_reviewed`, `reviewed_for_named_scope`,
  `accepted_pinned_basis`

`provenance.source_status` is one of `discovered`,
`official_metadata_checked`, `full_text_reviewed`, `changed`, or `superseded`.
Discovery metadata may have `source_sha256: null` with a
`raw_source_hash_null_reason`; reviewed full text requires a SHA-256 hash. A
hash only identifies captured bytes. It does not prove the requirement is true,
current, binding, sufficient, or certified.

`applicability` and each requirement `selectors` use exact-match lists for
`jurisdictions`, `operator_roles`, and `covered_uses`. The wildcard value `*`
is explicit. Missing facts are not treated as exemptions.

Each requirement names `requirement_id`, `requirement_ref`, `summary`,
`text_hash`, `selectors`, `maps_to_controls`, `maps_to_evidence_claims`,
`evidence`, `review_required`, and `does_not_prove`. Evidence statuses are
`missing`, `partial`, `observed`, `independently_reproduced`, `stale`, and
`disputed`. `observed` and `independently_reproduced` evidence require an
`artifact_sha256`; a bare assertion that evidence was observed is not enough to
make the assessment reviewable.

Unknown fields, command-shaped fields, executable imports, malformed dates,
malformed hashes, duplicate requirement IDs, and reversed effective intervals
are rejected.

## Assessment Semantics

`assess_profile(profile, context, *, as_of)` requires an explicit `as_of`
date. The implementation does not read the wall clock. Context facts are
matched only against the declared selectors:

- `jurisdiction`
- `operator_role`
- `covered_use`

Applicability is separate from software mapping. A requirement can apply even
when `maps_to_controls` names an unrecognized Flywheel control; the mapping is
then invalid and the result carries an `unrecognized_control_mapping` gap.
Only the built-in Flywheel control catalog is treated as known in this slice.
Caller-supplied `control_catalog` values are not an independent authority for
invented control IDs.

Source currency is also separate from binding applicability. A superseded
publication does not automatically become legally inapplicable when a contract
or other reviewed basis intentionally pins that older edition. In this first
slice, `binding_review_status: accepted_pinned_basis` is still a caller-reported
profile assertion unless a separate trusted review receipt has been checked.
It preserves declared applicability when facts match, but still emits
`binding_review_not_independently_verified` and keeps the result in
`NEEDS_REVIEW`. Without that reported pinned basis, a superseded source produces
a separate review gap. The registry performs no general legal reasoning and
never chooses the newest, oldest, strongest, or weakest rule on its own.

Assessment results preserve these dimensions independently:

- `source.status`: discovered, reviewed, expired, not yet effective, or
  superseded state for the submitted profile and `as_of` date
- `source.reported_status`, `source.reported_binding_review_status`, and
  `source.verification`, so the result keeps caller assertions separate from an
  independently checked review
- per-requirement `applicability`: `applies`,
  `does_not_apply_with_reason`, `needs_review`, or `conflict`
- per-requirement `applicability_basis`, which is always declared profile facts
  in this slice; `applies` is not a legal determination
- per-requirement `mapping.valid` and `unrecognized_controls`
- per-requirement `evidence.status` and gaps
- result `verdict`: `REVIEWABLE`, `NEEDS_REVIEW`, `CONFLICT`, or `INVALID`

Party or national labels that are not legal, contractual, jurisdictional, role,
or use facts are ignored by the evaluator and do not change core results.

## Synthetic Fixture

`examples/standards/synthetic-administrative-profile.json` is an invented
internal-policy fixture for administrative evidence review. It contains no
patient data, controlled technical data, facility operation, hazardous protocol,
weapon function, live control action, official endorsement, or real institutional
assessment.

The fixture intentionally starts as discovery metadata with partial evidence, so
the registry can demonstrate that a structurally valid profile still carries
review and evidence gaps.

## Limits And Follow-On Work

This slice is local library and CLI infrastructure. It does not add HTTP routes,
MCP tools, desktop/native UI, real public-standard profiles, licensed standards
text, restricted evidence handling, institutional approval workflows, or
certification records.

Future profiles for bio, nuclear, defense, finance, healthcare, aviation,
employment, education, public services, or other sectors need source capture,
applicability review, access-control review, false-success fixtures, and
independent review before they become executable profiles.
