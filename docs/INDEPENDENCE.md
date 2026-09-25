# What an evaluation result can establish

A reviewer needs to know which component decided an outcome, what evidence it
used, and which failures that component could miss. A hash, a successful run,
and agreement between agents answer different questions. Flywheel must preserve
those differences through import, evaluation, and publication.

## Current boundaries

| Check | Current implementation | What it establishes | What remains unknown |
| --- | --- | --- | --- |
| Inspect source custody | `harness/inspect_evidence.py` and `inspect_evidence_cli.py` | SHA-256 of the imported JSON bytes; optional comparison with a previously recorded digest | Who produced the file, whether its contents are truthful, or whether the supplied reference digest is trustworthy |
| Inspect structural checks | Strict JSON parsing, source pointers, status/invalidation and coverage checks | Supported fields are internally consistent enough to import; contradictions and incomplete runs remain visible | Whether a scorer is correct, whether a dataset measures the intended capability, or whether a model answer is correct |
| Inspect scorer values | Selected values are copied with exact JSON pointers | What the source log reports | Independent semantic verification; reports explicitly retain `UNVERIFIABLE` |
| Existing envelope rewitness | `harness/witness.py` reruns the envelope's oracle command and compares its canonical output hash; for a pytest envelope it also grades the rerun and requires the sealed verdict to match | Reproduction of that oracle's recorded result in the rerun environment, and for pytest, that the sealed verdict follows from the reproduced outcomes | A separately implemented checker or independent ground truth; the same defective oracle can reproduce the same error |
| Tool-call receipt chain | `harness/tool_call_receipt.py` binds reported arguments/output digests, admission, outcome and chain links | Integrity of the sealed record under its verification rules | A complete observation of the workstation, unrecorded actions, or correctness of the task result |
| Terminal effect evidence | `harness/gateway_effect_binding.py` recomputes observations from the accepted private trace and binds them to the terminal operation and Journey | Which recognized post-tool fingerprints the retained trace contains; authorized reviewers can inspect their exact source values | Rollback, current filesystem state, unrecorded effects, independent producer authentication, or semantic correctness |

The Inspect importer does not execute commands, import scorers, call a model, or
rerun an evaluation from a log. A command embedded in a source log is data.
Its `assessment: reported` and exit code zero describe the import, not approval
of the model or score. See [Inspect evidence import](INSPECT-EVIDENCE.md).

The existing private trace viewer presents terminal effect evidence beside its
source records. A cancelled run can retain observed effects, and a legacy result
without the optional summary does not establish zero effects. See
[Gateway effect evidence](GATEWAY-EFFECT-EVIDENCE.md) for the record contract and
the separate trusted checkpoint required for a continuity claim.

## Independence must name a boundary

Use these distinctions when describing an evaluation:

1. **Reproduction:** another execution repeats the original procedure.
2. **Implementation independence:** a second checker was written separately,
   and its shared libraries, canonicalization, inputs and specifications are
   disclosed. A wrapper around the first checker is not a second implementation.
3. **Evidence independence:** the deciding source is independent of the answer
   being evaluated. Copying a model's explanation into a reference file does not
   make that explanation ground truth.
4. **Assessment independence:** the assessor's role, access, incentives and
   relationship to the producer are disclosed. A separate agent invocation does
   not by itself establish organizational or epistemic independence.

Agreement between models, or between two runs of one model, is not a substitute
for a task-specific deciding source. Shared training, prompts, tools, fixtures or
model providers can create correlated errors. State those dependencies rather
than calling the assessment independent without qualification.

## Institutional independence and contestability

A third-party label is not an independence result. An assessor can be separate
from the producer while relying on producer-selected evidence, shared tooling
or funding that constrains what can be examined or reported.

For a real external assessment, the expanded audit record should identify:

- Who commissioned and funded the work, and any declared conflicts. Unknown
  relationships must remain unknown rather than defaulting to independent.
- What access the assessor requested, received or was denied; whether the
  producer selected the sample; and what population the sample represents.
- Who chose the task, ground truth and success criteria, including whether
  criteria changed after results were visible.
- Shared scorer implementations, model providers, datasets and evidence sources.
- Restrictions on publishing findings, and which conclusions another assessor
  can reproduce with the evidence available to them.
- How a reviewer can challenge a deciding source, submit counterevidence and
  retain a dissenting result without overwriting the original record.

These are requirements for institutional assessment. The first bounded
implementation is `harness.institutional_access`, which checks declared access
coverage against a caller-bound scope and retained source inventory. It does not
turn complete access into semantic support, and a missing component means no
institutional-access assessment exists. Private information should be disclosed
only through the agreed review scope; restricted access itself remains a visible
limitation on the conclusion.

Portable artifacts and offline checks should let another assessor recheck the
technical result without relying on Flywheel's hosted service or a producer's
dashboard. This reduces dependence on a single intermediary; it does not prove
that an institution is impartial or decide who should have regulatory authority.
An intact receipt must never silently become a certification or license to act.

## Required record for the expanded evaluation workflow

The following is the contract for the next adapter, fixture, incident-evaluation
and process-audit work. It is a design requirement, not a claim that every field
is already emitted by every Flywheel surface.

- The claim and its task scope, with the expected outcome fixed before the run.
- The task, adapter, fixture and producer versions, content hashes, and relevant
  environment/configuration facts. Credentials and private prompts stay private.
- The producer, collector, scorer and reviewer roles, plus shared dependencies.
- Each deciding source value with its file/record identity and line range,
  character offsets or JSON pointer. Retain the source; a pointer alone is not
  enough to review a value.
- Completion, correctness, attempted policy violations, enforced blocks and
  observation coverage as separate results. A blocked action measures an
  enforced restriction; it does not establish a model's disposition.
- Errors, cancellations, invalidation, omitted observations and unknown values.
  No successful aggregate may silently discard them.
- The negative controls actually run, their expected failure, the observed
  result, and what an undetected failure would invalidate.

## False-success controls

The existing Inspect acceptance script includes correct and incorrect answers
inside a successful run, and an explicitly invalidated copy of a complete log.
It also exercises epoch reduction so that valid aggregate counts are not
rejected merely because their denominator differs from raw sample records.

The expanded incident simulation and audit packet must also test:

- A wrong final task state with freshly recomputed integrity hashes. A valid
  witness must not rescue an outcome contradicted by the task's deciding source.
- A missing or reordered action, with observation coverage reported separately
  from the integrity of the remaining records.
- A stale fixture, changed task specification, changed scorer, and changed
  adapter. Detect byte/schema drift separately from behavioral drift; require
  review before adopting a new baseline.
- A scorer that always reports success. The evaluation must include a known
  wrong outcome that this scorer fails to reject.

EMET witness integration must retain this separation: a byte witness can attest
to the artifact it checks without gaining authority to decide what that artifact
means. Evaluation reports should make both the supported claim and its limit
available to the reviewer at the point of use.
