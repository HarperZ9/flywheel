# shared_task_artifact/v2

`shared_task_artifact/v2` is a diagnostic checker for the shared-task scorecard artifact. It leaves `shared_task_artifact/v1` and the original `agt-003-codex-flywheel-shared-task` task unchanged.

The v2 diagnostic task is `agt-003-shared-task-artifact-v2-diagnostic`. It still asks for `codex_flywheel_shared_task_scorecard.json` and `codex_flywheel_shared_task_scorecard.md`, but it grades only pre-oracle participant facts: input hashes, raw prompt hash, tool-policy hash, contained raw artifact and receipt paths, pre-oracle orthogonal states, closed claim bindings, and Markdown that must exactly equal the verifier-owned canonical render.

The participant does not submit `markdown_render_sha256`. The verifier computes `verifier_markdown_render_sha256` as oracle evidence from its independent canonical render and compares the submitted Markdown bytes against that render.

The checker rejects unsupported prose that v1 could miss, including comparison, equivalence, final pass, verified receipt, and no-failure claims before the oracle has run. It also rejects arbitrary JSON fields, claim labels, freeform limitation values, unsupported limitation ids, participant-submitted render hashes, and Markdown that does not match the deterministic verifier render.

This diagnostic is a prerequisite for a later same-task Codex-vs-Flywheel comparison. It does not by itself prove that the original `agt-003` post-run acceptance scope completed.

The staged fixture carries the complete participant/verifier split: exact participant claim objects, authority strings, Markdown template, JSON serialization rule, and the verifier evidence hash preimage rule. `benchmarks/fixtures/cross-harness/shared-task-v2-producer.py` is a verifier-side reference helper for reproducing the allowed participant envelope from `benchmark/context.json`; it is not a staged task input or an admitted participant command under the current read-only tool policy.

Passing this diagnostic measures preservation of a typed participant envelope and rejection of false or unsupported claims. It does not measure independent model report construction, admitted participant command execution, or the original cross-harness comparison.
