# Lean oracle task binding: follow-up (2026-09-23)

Status: open. Found while adding the leanchecker replay rung on branch
`fix/lean-leanchecker-replay`. That branch fixes nothing in this record.

## The defect

`LeanOracle.verify(candidate, task)` never reads `task`
(`harness/lean_oracle_adapter.py`, `verify`). The default registry routes the
`math` domain to `LeanOracle()` (`harness/oracle_registry.py`, the
`reg.register("math", LeanOracle(), ...)` line). So the math oracle accepts any
closed theorem. It does not check that the candidate proves the task's theorem.

Observed on 2026-09-23 with Lean 4.34.0 on Windows. The task was
`tasks/example_pass`, whose prompt asks for a Python `add(a, b)`. The candidate
was `theorem unrelated : True := trivial`. The verdict was `PASS` at
`validation_level` `leanchecker_replay`.

The registry's `does_not_prove` line names the formalization gap: the statement
may not be the intended theorem. That line describes a statement the task
supplied and the candidate misformalized. Here the task supplies no statement
at all, so any true proposition passes.

## Two routes the replay rung leaves open

Both routes below pass `lean_check` after the replay change. Both close with the
same fix.

1. A `def` over an axiom that a metaprogram added. The candidate builds the
   axiom's name from string parts, adds it with `run_meta addDecl
   (Declaration.axiomDecl ...)`, and then states `def bad : False := evil`. The
   hygiene regex sees no `axiom` keyword. The footprint audit reads source-named
   `theorem` and `lemma` declarations only, so it never asks about `bad`.
   leanchecker replays an axiom as a valid declaration. Observed receipt:
   `passed: true`, `axiom_footprint: {}`, `validation_level: exit_code`.
   The probe:

   ```lean
   import Lean
   open Lean

   def axName : Name := Name.mkSimple ("ev" ++ "il")

   run_meta addDecl (Declaration.axiomDecl
     { name := axName, levelParams := [], type := mkConst ``False, isUnsafe := false })

   def bad : False := evil
   ```
2. Separate elaborations. The kernel run, the `#print axioms` audit and the
   `.olean` compile each elaborate the candidate again. A metaprogram can tell
   the runs apart by its file name, by the text appended for the audit, or by
   the build directory. It can then emit different declarations in each run.
   This route comes from reading how the three runs start. Nobody has
   written an exploit for it.

## The fix

Bind the proof to a pinned challenge, the way `leanprover/comparator` does:

- The task pins a challenge: a theorem name and its statement, as Lean source
  that the task fixes before any candidate exists.
- Compile the candidate once, to one `.olean`. Every rung below judges that
  single artifact.
- Statement match: the constant with the pinned name exists in the compiled
  module, and its type is the pinned statement's type.
- Axiom audit from the artifact: collect the axioms that the pinned constant
  depends on, from the compiled environment and not from the source text. Allow
  the classical trio only. This closes route 1, because an added axiom shows up
  in the dependency set whatever declared it.
- Replay: leanchecker on the same `.olean`, as the branch does now.
- Later rungs: build inside a sandbox, and check with an external kernel
  (nanoda or lean4lean). That is the reference's fourth rung,
  `comparator_external` in the receipt ladder.

Merging the kernel run and the compile into one `lean -o` call also removes one
elaboration per check. On the measuring machine, the replay rung adds
about 3 to 4.5 s to each candidate that reaches it (median of n=3 per file,
two files, baseline measured in the same window).

## Decision record

- Decision: whether a math-domain `PASS` may count toward a promotion or a
  public claim before the task binding exists.
- Owner: the operator.
- Baseline: today any closed theorem passes the math domain, whatever the task
  says.
- Change trigger: the first task that pins a challenge statement, or the first
  use of a math-domain `PASS` outside a local experiment.
- Recheck: a regression test in which a true but unrelated theorem fails
  against a pinned challenge, and the route 1 probe fails the artifact axiom
  audit.
