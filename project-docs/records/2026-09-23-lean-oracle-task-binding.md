# Lean oracle task binding: follow-up (2026-09-23)

Status: fixed. The fix merged to main on 2026-10-04 as #365 and ships in
1.4.0 (see "Update, 2026-10-04" at the end). Found while adding the leanchecker
replay rung on branch `fix/lean-leanchecker-replay`. That branch fixes nothing
in this record.

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

## Update, 2026-10-04: the fix, its recheck, and the published-receipt search

The fix follows the design above, in `harness/lean_binding.py`,
`harness/lean_binding_judge.py` and the Lean program in
`harness/lean_bind_script.py`. `docs/PROOF-AND-FORMATS.md`, section "Binding a
proof to its task", describes the steps and the receipt fields.

- A task pins `challenge` (theorem name, statement, optional header). A task
  without one is `UNVERIFIABLE` with reason `SPECIFICATION_UNPINNED`, and no
  Lean runs.
- The candidate compiles once. The bind program reads that `.olean` as data,
  matches the pinned theorem's elaborated type to the challenge's, and
  follows every constant the statement reaches: header definitions must be
  identical, imported constants must come from the same module.
- Axioms come from a walk of the pinned theorem's dependencies over the
  artifact. This deliberately does not use `#print axioms`: that command reads
  a precomputed table, and for the candidate's own declarations the table
  comes from the candidate's own `.olean`.
- leanchecker replays the same `.olean`; its hash is rechecked after each step.

Recheck, run live on Lean 4.34.1, Windows, 2026-10-04
(`tests/test_lean_binding_live.py`, 14 tests, all passed):

| Probe | Result | Refused by |
| --- | --- | --- |
| `theorem unrelated : True := trivial` | FAIL | binding: no top-level `double_eq` |
| weakened statement (`double n = n + n`) | FAIL | binding: different proposition |
| renamed theorem, different statement | FAIL | binding: no top-level `double_eq` |
| `double` redefined, same statement text | FAIL | binding: `double` differs from the challenge |
| higher-priority `HMul` instance, same statement text | FAIL | binding: different proposition |
| `prelude` file declaring its own `True` | FAIL | binding: `True` resolves to the candidate, not `Init.Prelude` |
| `sorry` | FAIL | source screen; with the screen skipped, the compile's `sorry` warning (the bind program run on such a module lists `sorryAx`, observed in exploration) |
| custom `axiom cheat` | FAIL | source screen; the artifact audit alone names `cheat` |
| route 1, metaprogram-added axiom `evil` | FAIL | artifact axiom audit names `evil` |
| `debug.skipKernelTC` smuggle, pinned `bad : False` | FAIL | leanchecker replay |
| the real proof of the pinned statement | PASS | `leanchecker_replay`, axioms `propext`, `Quot.sound` |

That meets the bar this record set (3 of 3) and the wider set above. CI
installs no Lean, so these live tests skip there; `tests/test_lean_binding.py`
pins every exit with an injected runner and runs in CI.

Route 2 (separate elaborations) has one elaboration left to act in on the
bound path. Nobody has written an exploit for it, before or after.

Still open: the `comparator_external` rung (a sandboxed build and an
independent kernel). Update, 2026-10-04: the independent kernel (nanoda) and a
resource and write sandbox for the compile landed; the no-network part of the
sandbox did not. See `2026-10-04-external-kernel-rung.md`. `lean_check` on a
closed file (gateway `/api/lean`,
`harness/loops.py`, `harness/workstream_lean.py`) stays unbound by design, and
its receipt now says `statement_binding: unbound`.

Published receipts that depended on the hole: none found. Searched on
2026-10-04 with `git grep` over every tracked file of this repository at
c3da4962 (receipts, artifacts, records, release notes, changelog, docs, site,
benchmarks, tasks, datasets) for `LeanOracle`, `lean-receipt`,
`leanchecker_replay`, `kernel-checked`, `axiom_footprint`, `math` domain
results and `Lean kernel`, and over the published site sources and the other
public repositories of the same owner. Every hit was a capability
description, a `lean_check` result on a closed file whose statement the file
itself supplies (the 2026-07-14 conjecture sweep), or a disclosure of this
defect (this record; `RELEASE-NOTES-1.0.3.md`, Limits). No receipt is
re-issued, so no correction note is needed. Two public resume lines describe
the math domain as live without this caveat; they claim no result.
