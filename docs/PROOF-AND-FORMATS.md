# Documents in, documents out, and a proof the kernel reads

An answer rarely arrives as a `.json` file. It arrives as the memo, the filing,
or the PDF somebody is about to send. The check reads the answer out of the
document it came in, writes its report back into a document of the same kind,
and can emit the whole check a second time as a Lean 4 file that a kernel
settles on its own.

Nothing here changes a verdict. `PASS`, `FAIL`, and `UNVERIFIABLE` mean what
[OUTPUT-VALIDATION.md](OUTPUT-VALIDATION.md) says they mean.

## Reading the answer out of a document

`--answer` takes any of four suffixes.

| Suffix | Where the answer is |
| --- | --- |
| `.json` | the whole file |
| `.md`, `.markdown` | a fenced block tagged `flywheel-answer`, else the first `json` block holding an object |
| `.tex`, `.latex` | a `flywheelanswer` environment |
| `.pdf` | the JSON stream a Flywheel PDF carries |

```bash
flywheel check-output --contract task.contract.json --answer memo.md
```

A marked block wins over an unmarked one, because a memo shows the reader an
illustration first and the answer second, and taking the first `json` block
would check the illustration. In LaTeX the environment may be commented line by
line so it does not typeset, and it may wrap a `verbatim` block. Both still
parse.

Prose is never mined. A sentence reading "the tax is 4169 per the 2025 table"
is refused rather than turned into a field. Lifting a value out of a sentence is
a guess, and a wrong guess would arrive at the checker wearing the checker's own
authority.

The same holds for a PDF page. A PDF that Flywheel wrote carries the answer as
an attached stream, and that is what gets read. A PDF from anywhere else is
refused instead of reconstructed from its layout.

## Writing the report into a document

`--report` picks the format from the suffix: `.txt`, `.md`, `.tex`, `.pdf`, or
`.json`.

```bash
flywheel check-output --contract c.json --answer filing.tex --report review.pdf
```

Every format opens on the verdict and the release decision, lists the fields
worst first, and names the fields that blocked release. An unverified field
outranks a passing one in that ordering even when it is advisory, because
criticality decides what a non-PASS blocks rather than how bad it is.

No format carries the authoritative value. That property holds in the report,
in the retry feedback, and in the Lean file, for the reason given in
OUTPUT-VALIDATION.md: an attempt that copied the right number out of its own
failure report would pass the check while learning the opposite lesson.

The `.tex` output is a fragment, not a document. It goes inside a filing that
already has a preamble. Nothing is typeset and no LaTeX toolchain is required.

The `.pdf` output is written directly, with no compression and no creation
timestamp, so the same report produces the same bytes on every run and the file
can be hashed into a receipt. It carries the answer it vouches for as an
attachment, because a page and the values it speaks about travelling separately
is how a filing ends up attached to the wrong return.

## The check as a Lean file

```bash
flywheel check-output --contract c.json --answer a.json \
  --lean Answer.lean --verify-lean
```

`--lean` writes the file. `--verify-lean` runs `lean` on it and folds the
result into the report and the exit code. `--lean-bin` names a specific
binary. Without `--verify-lean` the file is written and nothing runs it, since
running Lean means running a program and this asks for the grant the same way a
command authority does.

The file has three kinds of declaration in it, and the division between them is
the whole point.

**Definitions** are what the answer states. Each numeric field becomes an `Int`
in one fixed-point scale, and each source, method, and unit becomes a `String`.

**Theorems** are what the kernel settles by itself, closed `by decide`. A
required method, a stated unit, and every relation the contract declares land
here. These are decided in the kernel and rest on nothing.

**Axioms** are what something outside decided. A table lookup ran in a
subprocess. Calling its result a theorem would put a kernel's name on a
subprocess's word, so it enters as a named axiom over one opaque predicate:

```lean
axiom Decided : String → Int → Prop
axiom tax_decided : Decided "irs-2025-tax-table-single" tax
```

One `theorem confirmed` conjoins every obligation, and the file ends with
`#print axioms confirmed`. That single line enumerates the entire trust
surface. What it lists is exactly what you are taking on faith, by name.

A field the check did not confirm produces no axiom at all. It appears in an
`unconfirmed` list instead, so the file states what went unchecked rather than
falling silent about it.

## Reading the axiom list

```
'Flywheel.Answer.confirmed' depends on axioms: [Decided, tax_decided]
```

That is a closed file resting on one outside decision, named. A file resting on
nothing at all prints "does not depend on any axioms", which is the strongest
result available and happens when every obligation was decidable.

```
'Flywheel.Answer.confirmed' depends on axioms: [sorryAx]
```

`sorryAx` is Lean's own name for an obligation that did not close. It reaches
the axiom list through the same channel a real assumption does, which is why
the list is what gets read rather than the exit code.

## Two readings of one answer

The Python check and the Lean file are built from different code and read the
same answer. Where they disagree, one of them is wrong, and finding that out is
the reason the second reading exists.

The exit code takes the worse of the two, and only when `--verify-lean` was
asked for. A kernel that refuses an obligation the report passed turns a clean
run into a `FAIL`. The reverse cannot happen: a proof cannot make a run
cleaner than the check found it.

If `lean` is not installed, times out, or fails in a way that is not a
statement about the file, the proof comes back `UNVERIFIABLE` and never `PASS`.
The file is written out either way, since a caller who asked for a proof and
got a refusal wants to read the file that was refused.

## Relations

A contract may state relations that must hold among the answer's own values.
They become theorems the kernel settles.

```json
{"relations": ["0 <= tax", "tax <= taxable_income",
               "total = subtotal + tax"]}
```

A single `=` is the spelling, because that is what a contract author writes. A
chain becomes one claim per link, so a failure names the link rather than the
chain. A relation this module will not read is refused rather than
approximated, which covers a multiplication of two fields, an exponent, a
function call, and anything naming a field the answer does not have.

## The fixed-point scale

Every numeric field is carried as an `Int` in one scale for the whole file, so
no sum ever mixes cents with dollars. `decide` settles integer arithmetic in
the kernel, and floats are not an ordered field.

A value that will not fit that scale exactly is dropped and named in an
`unrepresentable` list. It is never rounded. A rounded number in a proof is a
proof about a number nobody stated. A relation naming a dropped field is
refused rather than skipped, since saying nothing about it would read as
proved.

## What the proof does not say

It says the answer is internally consistent, that the values relate the way the
contract requires, and that the sources it rests on are exactly the ones named
in the axiom list.

It does not say those sources are right. A table can be out of date and a
checker program can be wrong, and the kernel has no opinion about either. The
axiom list is there so the reader can see what remains to be trusted, which is
a smaller and more specific claim than "verified".

## Judging Lean that someone else wrote

The file `--verify-lean` checks is one Flywheel wrote. It holds definitions,
theorems closed `by decide`, and named axioms, and it runs no code of its own.
The math domain oracle, `lean_check` in `harness/lean_oracle.py`, judges Lean
that a model wrote. That source can run its own programs while Lean elaborates
it, and an exit code or an axiom list cannot see everything those programs do.

This file proves `False`, and before the replay rung below the oracle passed it:

```lean
import Lean
open Lean Meta

def optName : Name := Name.mkStr (Name.mkSimple "debug") "skipKernelTC"

run_meta do
  withOptions (fun o => o.setBool optName true) do
    addDecl (Declaration.thmDecl {
      name := `smuggled
      levelParams := []
      type := mkConst ``False
      value := mkConst ``True.intro })

theorem bad : False := smuggled
```

The metaprogram stores `smuggled : False` with the kernel check switched off.
It spells the option as a name built from parts, so a text screen for
`debug.skipKernelTC` finds nothing. `lean` exits 0 with no warning.
`#print axioms bad` reports no axioms, because it reads the same environment
the metaprogram wrote.

So `lean_check` climbs the validation ladder from the Lean reference's
"Validating Proofs" chapter one rung further. A text screen for `sorry`,
`axiom`, `native_decide` and the other escape hatches runs first. After it,
each rung runs only when the rung below it passed.

| Rung | `validation_level` | What it refuses |
| --- | --- | --- |
| Kernel exit | `exit_code` | an error, or a `sorry` warning on an exit of 0 |
| Axiom list | `print_axioms` | a named theorem resting on any axiom besides `propext`, `Classical.choice` and `Quot.sound` |
| Replay | `leanchecker_replay` | a stored declaration whose value does not have its stored type |
| Comparator | `comparator_external` | not implemented here |

The replay compiles the candidate to an `.olean` file in a temporary directory
and runs `leanchecker Candidate` on it. leanchecker ships in the Lean toolchain.
It reads the compiled module in a separate process and sends every declaration
the module adds back through the kernel. On the file above it stops with
`declaration type mismatch, 'smuggled' has type True but it is expected to have
type False`, and the verdict is `FAIL`.

Three details of how the replay runs:

- leanchecker comes from the installation that `lean --print-prefix` names for
  the `lean` that compiled the module. An `.olean` file belongs to the toolchain
  that wrote it.
- `LEAN_PATH` lists the toolchain's library before the build directory. The
  candidate's code can write into the build directory. When that directory
  came first, a planted `Init` package there shadowed the real one.
- It runs in plain mode. Plain mode checks the candidate's own declarations
  again and trusts the toolchain modules it imports. `--fresh` replays the
  imports too. On one machine it took 153 s on a one-line file (one run),
  where plain mode took 1.7 to 3.1 s (three runs on each of two files).

A leanchecker exit other than 0 is `FAIL`, and so is an `.olean` compile that
fails. A toolchain with no leanchecker, or one that will not start, gives
`UNVERIFIABLE` with `unverifiable_reason: leanchecker-unavailable`. It never
gives `PASS`. The replay adds about 3 to 4.5 s to each candidate that
reaches it (median of three runs on each of two files, one machine).

`validation_level` names the highest rung cleared with every rung below it
cleared too. The axiom rung reads named `theorem` and `lemma` declarations. A
file with none of them gives it nothing to read, so the level stays `exit_code`
even when the replay accepts the file. The receipt also carries
`validation_ladder`, the four rung names in order, and a `leanchecker` block
with `mode`, `module`, `exit` and `version`. leanchecker has no version flag,
so `version` is the toolchain's `lean --version` line, and `version_source`
says so.

### What a Lean accept does not say

- The replay trusts the toolchain's own `.olean` files as they sit on disk. The
  candidate's code ran with the user's rights while Lean elaborated it and
  could have changed files. Catching that takes a sandboxed build, which is
  the comparator rung.
- The axiom rung covers named `theorem` and `lemma` declarations only. A `def`,
  or a declaration that a metaprogram added, can rest on an axiom the audit
  never reads, and the replay accepts an axiom as a valid declaration.
- The math oracle does not read its task. It accepts any closed theorem, and
  the theorem need not be the one the task asked for. Binding a proof to a
  pinned challenge statement, as `leanprover/comparator` does, is open work.
