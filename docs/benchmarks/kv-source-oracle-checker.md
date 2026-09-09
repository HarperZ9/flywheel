# KV source-only oracle checker

`kv_source_derived_strict_json/v1` is a cross-harness oracle checker for the
first synthetic KV-cache diagnostic task family. It is source-only: it loads a
model-visible `flywheel.kv-source-only-fixture/v1` or
`flywheel.kv-source-only-fixture/v2-token-admitted` fixture, derives the
expected result from `source_records`, and compares the submitted
`report.json.result` after the existing common envelope checks have passed.

The checker is deliberately packet-specific. It contains twelve task-id
branches for the accepted source-only KV task ids:

- `kv-msr-001-incident-reconstruction`
- `kv-msr-002-route-reconstruction`
- `kv-rap-001-policy-precedence`
- `kv-rap-002-release-approval`
- `kv-cdr-001-retention-authority`
- `kv-cdr-002-endpoint-authority`
- `kv-sta-001-endpoint-gate-argv`
- `kv-sta-002-manifest-argv`
- `kv-rsm-001-lane-symbol-match`
- `kv-rsm-002-checker-reference-match`
- `kv-abst-001-f16-settings-missing`
- `kv-abst-002-frontier-comparison-missing`

It reuses the existing cross-harness seams for raw envelope validation,
duplicate-key rejection, artifact hash accounting, fixture hash binding, and
citations. The result object must be the direct `ANSWERED` or `UNVERIFIABLE`
object under `report.json.result`. Citation arrays are treated as unordered sets
unless the oracle spec explicitly sets `citation_order` to `ordered_array`.

The v2 token-admitted schema is accepted only with the current packet shape:
`schema`, `task_id`, `family`, `question`, `citation_order`,
`source_input_ref`, `source_input_sha256`, and `source_records`. That keeps the
compatibility path explicit rather than accepting any future schema string.

The fixture must not contain private oracle outputs, wrong-answer controls,
copy-trap material, or fields that look like embedded reference answers. The
structured-command tasks derive `cwd` from the source records, using
`path-contract:temp-only.cwd`. Older v1 fixtures for the structured tasks remain
compatible only if they already carry that field. `path-contract:temp-only.root`
is the output artifact root and is not a script repository cwd fallback. A
regenerated packet that needs a working directory must carry it as a source
record field.

This checker only establishes whether a submitted artifact matches the
source-derived oracle for these task ids. It does not establish that a task
packet is token-admitted, executable by a given model route, or comparable across
runtime configurations.
