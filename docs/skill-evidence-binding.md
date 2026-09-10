# Skill evidence bindings

A reviewer needs to distinguish a stored association from an independently
evaluated procedure. The skill registry associates an admitted, seal-checked
lesson with submitted benchmark evidence. It does not execute the lesson or
authenticate the evaluator.

## Bind actual producer evidence

`POST /api/skills/bind` accepts a `lesson` object, an `evidence` object, and
optional `bound_at`. Supply the complete `flywheel.verified-bench/v1` object
emitted by `harness.verified_bench.run_benchmark` or returned as `bench` by
`POST /api/bench/run`. A few passing flags or a made-up benchmark digest are
insufficient. The bind route never executes the supplied `gate_cmd`.

The validator checks the benchmark seal, unique task and endpoint identities,
integer seeds and repetition indices, randomness-control consistency, one gate
command per task, and complete task × endpoint × replicate coverage. Every
denominator dimension must match the actual records. Proposal digests must be
well formed; gate references must be nonblank. All current attempts must report
`gate_pass: true`. A proposal digest is not a check of proposal contents: the
producer document does not retain those contents.

For `flywheel.trace-regression/v1` evidence, additionally supply `prior_bench`
and `current_bench`. Both must be complete producer documents. The report must
reproduce exactly from them, with the same tasks, endpoints, seeds and gate
commands. Current failures are rejected even when a summary calls FAIL → FAIL
stable. The trace producer collapses repeated attempts to task/endpoint pairs,
so only single-replicate trace comparisons qualify. For multiple replicates,
bind the complete current benchmark directly. An initial trace report with no
prior producer document is insufficient; its current benchmark can be bound
directly. These restrictions affect skill binding, not benchmark execution.

## What the stored row and response mean

New rows use `flywheel.skill-gate/v2`. They retain lesson/source digests and a
compact projection with task identities, endpoints, seeds, attempt outcomes,
proposal digests, and hashed command/reference strings. They omit command and
proposal contents. Identifiers may still be private; inspect them before sharing.
`tasks_bound` counts distinct tasks; `attempts_bound` counts all cells.
`all_passed` records the submitted current flags, not authenticated execution.

`verify_skill_gate(row)` recomputes the seal and projected coverage. `MATCH`
means internal integrity and consistency only. Its `source_binding` is
`NOT_RECHECKED`. Supply the original `evidence` and, for traces, both source
benches to revalidate the complete documents against the stored projection;
then `source_binding` can be `MATCH` too. Neither check changes
`independent_evaluation: UNVERIFIED` or `procedure_application: UNKNOWN`.
A coherently fabricated benchmark can pass these consistency checks. No trust
anchor outside the submitted material establishes who ran it or which lesson
procedure it used.

The bind acknowledgement has separate `assurance`. `GET /api/skills` preserves
the existing `skills` and `count` fields and adds `assurance` keyed by
`gate_sha256`. Legacy v1 rows with matching seals remain readable and retain
their exact stored payloads; their separate assurance verdict is `UNVERIFIED`
with `source_binding: LEGACY_NOT_VALIDATED`. They are never silently resealed
as v2. Tampered or malformed rows still refuse to load. Registry and roadmap
counts are stored bindings, not counts of independently evaluated skills.
The desktop consumes these list/count fields without a v1-specific parser.

## Independent evaluation is a separate operation

The existing `/api/bench/run` gateway operation binds tasks, endpoints and timeout
through its execution grant. It calls `run_private_benchmark`, then
`subprocess_gate`, in temporary per-attempt workspaces. An operator can authorize
a fixed task set and checker through that seam. Importing a benchmark into the
skill registry does not invoke or grant that operation.

The current producer's gate reference hashes command/output, and its temporary
proposal workspace is discarded. It does not retain a separately authenticated
receipt binding an exact lesson procedure, task contract, checker source,
proposal artifact and outcome. An independently authenticated skill rerun is
therefore unavailable through this binding API. Adding it requires explicit
artifact custody and evaluator authority, not another self-supplied digest.

## Local controls

From a checkout:

```console
python -m pytest tests/test_skill_gate.py tests/test_skill_route.py tests/test_skill_evidence_binding.py -q
```

The tests use actual producer documents. A fixed test-owned subprocess checker
accepts one synthetic proposal and rejects the wrong proposal. Other controls
reject malformed seals, resealed contradictory counts/cells, mismatched source
documents and trace summaries that conceal failures. A deliberately coherent
fabrication remains explicitly unauthenticated. No live model is called.

This improves inspectability and prevents unsupported passing assertions from
masquerading as complete benchmark records. It does not demonstrate model
alignment, general safety, skill usefulness or commercial adoption.
