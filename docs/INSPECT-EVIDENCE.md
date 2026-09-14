# Review an Inspect evaluation in Flywheel

`flywheel import-inspect` reads an Inspect JSON log and emits a local evidence
report. It preserves run status and scorer results as reported claims, with the
source hash and JSON pointers needed to locate them. It does not rerun a model,
execute a scorer, or establish that an answer is correct.

See [Independence](INDEPENDENCE.md) for the separate boundaries of custody,
reproduction, semantic validation and reviewer independence.
The [METR interoperability reference](METR-INTEROP.md) describes the execution
route and the additional evidence needed beyond log import.

This is an evidence import. It is not a METR Task Standard executor or a
replacement for Inspect's evaluator and sandbox. The CLI and native desktop
import panel both review exported Inspect JSON; neither reruns Inspect or unpacks
native `.eval` archives.

## Use

For Inspect's native `.eval` format, first use Inspect's supported exporter:

```text
inspect log dump run.eval > run.json
flywheel import-inspect run.json
flywheel import-inspect run.json --expected-sha256 <previously-recorded-digest>
flywheel import-inspect run.json --unit-contract run.unit.json
```

Use a shell that preserves UTF-8 when redirecting JSON. Inspect's Python
`read_eval_log` and `write_eval_log(..., format="json")` APIs are another export
route. Flywheel does not unpack `.eval` archives or require Inspect at runtime.
The digest in this report binds the JSON export bytes, not the original `.eval`
archive. Retain the original archive and conversion provenance separately.

The report goes to stdout. Nothing is posted to Bulletin, Slack, or a provider.
Treat it as private: task names, model identifiers, sample IDs, scorer values,
and error messages can contain sensitive information. Messages, prompts, targets,
and raw model API payloads are not copied. This selection is not a general-purpose
redactor.

## Reading the result

- `semantic_verification: UNVERIFIABLE` means no independent correctness check
  has been performed, even if the run status is `success`.
- `reported_status` retains Inspect's status. Started, cancelled, failed, or
  partially covered runs do not become completed evaluations.
- Inspect's `invalidated` flag is retained. An invalidated log remains incomplete
  even if its status says `success` and all samples have scores.
- Source pointers are RFC 6901 JSON pointers into the exact imported JSON. A
  source value is attached so a reviewer can compare it with the retained file.
- Scorer values remain reported values. For example, a successful run can contain
  both a correct (`C`) and incorrect (`I`) result. Run completion is not accuracy.
- If an Inspect score carries edit history, the per-score `score_history` field
  reports only safe history fields: score `value`, edit `reason`, and provenance
  `author`, `reason` and `timestamp`. Raw score answers, explanations and
  metadata are not copied; `redacted_fields` names omitted fields when present.
  A legitimate score edit does not make the run incomplete by itself. The edit
  history is reported provenance, not proof of fraud, author identity,
  wall-clock truth or disclosure completeness.
- When any score history field is observed, `scoring_coverage.score_history`
  distinguishes `present`, `empty` and `missing` for that import. Empty means
  the imported log explicitly carried an empty history array. Missing means this
  importer did not observe a history field for that score, not that no edit ever
  happened. Legacy logs with no score history fields keep their earlier coverage
  shape.

The report selects per-sample scores and reported coverage counts. Aggregate
metric values, scorer configuration, and transcripts remain in the original
log; this report is not a lossless replacement for that file.

An optional `flywheel.inspect-scorer-unit-contract/v1` sidecar can be supplied
when a reviewer needs to distinguish the unit that Inspect scored from the unit
an evaluator intended to claim. With `--unit-contract`, the report adds
`scorer_unit_analysis`. Its `mapping_consistency` verdict checks byte binding,
source pointers, decoded JSON string spans, duplicate, omission and overlap
controls. Its `score_unit_relationship` can report that 10 Inspect rows map to
556 Python test-function definitions through a many-to-one aggregation, while
`definition_score_coverage` remains `UNVERIFIABLE` unless separate
per-definition score evidence exists. Without the sidecar, the importer does
not infer an intended denominator from `scored_samples`, and row scores remain
row scores.

Exit `0` means a structurally complete report was imported, not that its claims
were independently verified. Exit `3` retains an incomplete or failed run for
review. Exit `2` rejects malformed, unsupported, oversized, or changed input.
Automation must inspect the report rather than treat exit zero as score approval.

## Supported boundary

The importer supports version 2 JSON logs, bounded to 16 MiB. It rejects duplicate
JSON keys, malformed records and non-finite numeric values. Inspect can emit NaN
or infinity in some logs; those exports currently need a separate explicit
normalization with retained provenance, not silent value replacement. Unknown
future log versions fail closed.

Score edit history is bounded for reviewability. A score history longer than 128
events, or provenance text fields longer than 4096 characters, is rejected as
outside the supported import size for this evidence view. That limit is not an
Inspect schema claim.

Source: [Inspect log documentation](https://inspect.aisi.org.uk/eval-logs.html).

## Reproduce the integration check

Install `inspect-ai==0.3.263` only in a separate development environment, then run:

```text
python scripts/run_inspect_import_acceptance.py --out <new-empty-directory>
python scripts/run_inspect_import_acceptance.py --epochs 2 --out <another-empty-directory>
```

The check uses real Inspect evaluation, scoring, score editing, `.eval`
serialization and JSON export with a mock model returning deterministic text. It
exercises format interoperability; it does not measure a frontier model, certify
governance compliance, or establish production-scale performance.

The Inspect JSON interoperability workflow repeats these checks on Linux and
Windows using the pinned producer version. Its artifacts contain generated mock
evidence, not operator evaluation logs. A passing run establishes compatibility
with this producer version and these cases, not every possible Inspect task.

## Versioned fixtures and drift

The repository retains reviewed, derived fixtures in `tests/fixtures/inspect/v1`.
They cover single and repeated samples, with both ordinary and invalidated logs.
Those checked-in v1 files are historical fixtures for the original score-value
projection and are not silently rewritten when the importer learns a new
allowlisted field. Newly generated fixtures record the additive score-history
projection profile when score history is included.
Run the offline check without installing Inspect:

```text
python scripts/check_inspect_fixtures.py --root tests/fixtures/inspect/v1
```

Each fixture records its producer version, original JSON hash, projected JSON
hash and fixture hash. The manifest pins fixture bytes and expected importer
results. The projection removes selected fields from generated mock runs; it
is not the original log and is not a general redaction tool for private logs.

The checker reports byte, schema, producer and importer-result disagreements.
It never refreshes the baseline. An expected invalidated result can satisfy the
fixture contract while the imported evaluation remains incomplete and its
semantic verification remains `UNVERIFIABLE`.

Hashes detect changes against the supplied baseline. They do not authenticate
the baseline's author or establish that its expected results are correct.
Review changes to fixtures, their expected results and the checker together;
retain the source logs privately when publication would expose sensitive data.
