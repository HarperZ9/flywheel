# Rowan check integrity repair

Status: implemented and locally tested, based on PR 285 at `d7aa6159`.
Pending independent review and full-suite validation before integration.

Problem: a program under test can rewrite its grading test while the check
runs. The guard then adopts that rewrite as its baseline and omits the change
from deliverables. A later passing check can label an incorrect answer verified.
A truncated protected-file scan also produces no flag when its before and after
markers match.

Decision: keep the initial grading baseline for the entire run. Record protected
changes both before and after each check. Never exclude a protected grading
change as generated output. Incomplete or unreadable grading coverage prevents
a trusted pass, even when the command succeeds.

Acceptance:

- A real bound run whose implementation rewrites a failing test must not produce
  a verified answer or verified completion projection.
- A protected change during the last check must be recorded immediately.
- Truncated scans must not yield a clean integrity result.
- Generated outputs outside the protected grading set remain supported.
- An unchanged, passing check remains trusted.

Tradeoff: updating protected snapshots during a check requires separate review;
it cannot certify the same run. Large or unreadable workspaces can still execute,
but their incomplete coverage cannot certify a trusted answer. This does not
provide filesystem isolation, detect temporary mutations restored before a
snapshot, or prove the semantic adequacy of a test.

Validation: four initial regression cases failed before the fix. The repaired
cases and affected completion, budget, native-tool, handoff, integrity and run
verdict tests passed: 277 tests in 103.01 seconds. Repository static gates and
the disproof gate passed; the latter returned PASS with rewitness MATCH.
These checks used controlled providers and temporary local workspaces. They do
not establish live-provider or installed-application acceptance.
