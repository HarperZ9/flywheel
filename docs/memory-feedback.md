# Scoped memory in a task workflow

A later task can receive the candidate from an accepted prior task when the
caller names that exact source. This makes the input observable and reusable.
It does not establish that a model used the content, that a prior oracle proves
universal correctness, or that the model improved.

## Existing Python workflow

Use `harness.flywheel.spin` with already configured tasks, proposer and oracle:

```python
from harness.cache import ReceiptCache
from harness.flywheel import spin


def run_scoped_tasks(seed_task, dependent_task, proposer, oracle):
    return spin(
        [seed_task, dependent_task], proposer, oracle,
        cache=ReceiptCache("run/cache"), turns=1,
        envelopes_dir="run/envelopes",
        memory_sources_by_task={dependent_task.task_id: [seed_task.task_id]},
        context_budget=4096,
        context_byte_budget=16384,
    )
```

Order the tasks so a source has passed before its dependent task runs. Each spin
call owns an in-process pool and shared envelope directory. Source IDs are exact,
case-sensitive identifiers using letters, digits, underscores, periods and
hyphens, at most 128 characters, beginning with a letter or digit. A family or
prefix grants no content access. An omitted map leaves memory disabled and the
trace reports that state. At the lower-level `run_loop` API, pass a shared
`VerifiedPool`, `envelopes_dir` and `memory_sources` explicitly.

The allowlist authorizes sending each source candidate to the configured
proposer, including a remote model if that is your proposer. It is caller-owned
disclosure authority, not tenant authentication. Choose a private artifact root
with appropriate filesystem permissions. Envelopes are existing plaintext local
artifacts; this feature introduces no encrypted or cross-tenant memory service.

## What reaches the proposer

The resolver reads a bounded artifact through the pinned filesystem reader and
checks the source ID, short content identifier, full accepted claim SHA-256 and
PASS verdict. Legacy unpinned admissions, missing or modified artifacts and
content matching the existing secret scanner are unavailable. The scanner is a
heuristic, not a guarantee that content is safe to disclose.

Only the source candidate is eligible. Receipt prose, oracle fixtures and
caller-supplied retrieved text are not substituted for it. JSON-encoded content
is marked as untrusted evidence. That label is an instruction boundary, not a
sandbox or a guarantee against prompt injection.

The existing context governor budgets the original system instructions, base
prompt and evidence together. System/base pins remain intact; evidence that
does not fit is omitted. Token counts are estimates. A byte limit also excludes
oversized evidence. If pins alone exceed a budget, the governor records the
overflow and adds no evidence; it does not truncate the owner's instructions.

The `memory_context` chain stage records included sources, full claim bindings,
omission reasons, budget accounting, the assembled prompt hash and whether the
proposer was called. It records exposure, not semantic consumption. Cache hits
reuse a candidate and still run current checks; the stage explicitly says the
proposer was not called. Direct and search proposals use the same assembled
prompt. The regular prompt-addressed cache binds that prompt. An explicit
`run_loop(proof_addressed=True)` call may reuse a rechecked candidate across
memory-disclosure changes when its proof-cache inputs remain unchanged. Such a
hit does not establish a new memory-conditioned proposal: inspect the current
stage's disclosure status and `proposer_called`, not merely task acceptance.

## What the check establishes

`measure_loop` executes a deterministic reader on a dependent fixture task and
runs the same task with retrieval disabled. Its memory edge closes only if the
source appears in the actual input, the input changes, the enabled task passes
and the disabled task fails. Replacing retrieval with a no-op must open the edge.
These are instrument controls, not a model benchmark. Configuration proposals
remain unapplied and corpus exports do not constitute training.

Native sessions and `session_tools.resume_context` are not wired to this content
authorization path. Their citation plumbing must not be described as automatic
memory-conditioned proposals. No model calls, training or provider publication
are part of the deterministic test suite.
