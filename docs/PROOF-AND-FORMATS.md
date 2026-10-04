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
`lean_check` in `harness/lean_oracle.py` judges Lean that a model wrote, and
the math domain oracle (`LeanOracle`) runs the same rungs against the statement
its task pinned (see "Binding a proof to its task" below). That source can run its own programs while Lean elaborates
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

Four details of how the replay runs:

- leanchecker comes from the installation that `lean --print-prefix` names for
  the `lean` that compiled the module. An `.olean` file belongs to the toolchain
  that wrote it.
- leanchecker's `LEAN_PATH` is the toolchain's library, then every entry of
  the `LEAN_PATH` the harness was started with, then the build directory. The
  kernel run and the compile read the inherited entries (`lake env` puts
  Mathlib there), so the replay reads them too. Without them, a sound proof
  that imports from one of those entries came back `FAIL`.
- The build directory goes last because the candidate's code can write into
  it. When it came first, a planted `Init` package there shadowed the real
  one. Last in line, it only has to supply the name `Candidate`. If an
  earlier entry also holds a `Candidate` module or directory, the replay
  stops with `UNVERIFIABLE`. leanchecker would read that module in place of
  the one the compile wrote: a harmless `Candidate.olean` placed there let
  the file above pass the replay (exit 0).
- It runs in plain mode. Plain mode checks the candidate's own declarations
  again and trusts the toolchain modules it imports. `--fresh` replays the
  imports too. On one machine it took 153 s on a one-line file (one run),
  where plain mode took 1.7 to 3.1 s (three runs on each of two files).

A leanchecker exit other than 0 is `FAIL`, and so are a leanchecker timeout
and an `.olean` compile that fails. A replay that judged nothing gives
`UNVERIFIABLE`, never `PASS`, and `unverifiable_reason` names the step:

| `unverifiable_reason` | Cause |
| --- | --- |
| `leanchecker-unavailable` | the toolchain has no leanchecker, or it will not start |
| `lean-compile-unavailable` | `lean` would not start for the `.olean` compile |
| `leanchecker-import-unresolved` | leanchecker could not load a module the compile loaded |
| `replay-module-shadowed` | an earlier search path entry holds a `Candidate` module |

The import case is matched on the line right after leanchecker's `found a
problem` header. There a kernel refusal starts with `while replaying
declaration`, so a declaration name cannot make a refusal read as an import
failure. The replay adds about 3 to 4.5 s to each candidate that
reaches it (median of three runs on each of two files, one machine).

`validation_level` names the highest rung cleared with every rung below it
cleared too. The axiom rung reads named `theorem` and `lemma` declarations. A
file with none of them gives it nothing to read, so the level stays `exit_code`
even when the replay accepts the file. The receipt also carries
`validation_ladder`, the four rung names in order, and a `leanchecker` block
with `mode`, `module`, `exit` and `version`. leanchecker has no version flag,
so `version` is the toolchain's `lean --version` line, and `version_source`
says so.

### Binding a proof to its task

Until 2026-10-04 the math domain oracle never read its task, so any closed
theorem passed: `theorem unrelated : True := trivial` earned `PASS` at the
replay rung against a task that asked for Python (record
`project-docs/records/2026-09-23-lean-oracle-task-binding.md`). The oracle now
judges a candidate only against a challenge the task pins before any candidate
exists, the way `leanprover/comparator` does. A task carries it in
`task.json`:

```json
"challenge": {
  "theorem": "double_eq",
  "header": "def double (n : Nat) : Nat := n + n",
  "statement": "∀ n : Nat, double n = 2 * n",
  "statement_sha256": "optional: the hash a receipt reported for this statement"
}
```

A task with no challenge gives `UNVERIFIABLE` with reason
`SPECIFICATION_UNPINNED`, attributed to the harness, and no Lean runs. With a
challenge, `harness/lean_binding.py` runs these steps, each only after the one
before it passed:

1. The source screen for `sorry`, `axiom` and the other escape hatches.
2. One compile of the candidate to one `.olean`. An error or a `sorry` warning
   is `FAIL`. Every later step reads this artifact, and its SHA-256 is
   checked again after each of them; a change is `FAIL`.
3. The challenge compiles in a fresh directory as the header followed by
   `theorem <name> : <statement> := sorry`.
4. A Lean program (`harness/lean_bind_script.py`, run with `lean --run`) reads
   the candidate's `.olean` as data, so none of the candidate's code runs in
   it. It refuses the candidate unless the module declares a top-level
   theorem with the pinned name whose elaborated type equals the challenge's
   exactly. It then follows every constant that type reaches. A constant the
   challenge header declares must be declared identically by the candidate (a
   redefined `double` is refused). A constant from an imported module must
   come from the same module on both sides (a `prelude` file that declares
   its own `True` is refused).
5. The same program walks every constant the pinned theorem depends on, from
   the artifact, and lists the axioms it reaches. It reads neither
   `#print axioms` nor the precomputed axiom table an `.olean` can carry. Any
   axiom besides `propext`, `Classical.choice` and `Quot.sound` is `FAIL`;
   this catches an axiom a metaprogram added under a name built from parts.
6. leanchecker replays the same `.olean`, as above.
7. A second kernel, nanoda, checks an export of the same `.olean` (next
   section). A `PASS` needs both kernels to accept.

The receipt (`flywheel.lean-receipt/v2`) adds:

| Field | Content |
| --- | --- |
| `statement_binding` | `pinned`; `lean_check` on a closed file says `unbound` |
| `challenge` | the theorem name, `challenge_sha256` over the pinned header, statement and name, and `statement_canonical`, the statement as the toolchain elaborated it |
| `statement_sha256` | SHA-256 of `statement_canonical` |
| `binding` | `bound` or `refused`, with every refusal reason |
| `trusted_base` | Lean version and git hash, the kernel and replay used, `axioms_used`, `axioms_allowed`, and where the axioms came from |
| `spec_fidelity` | always `UNVERIFIED`: whether the statement says what its author meant is a human review |
| `artifact_sha256` | the compiled module every step judged |
| `external_kernel` | the second kernel's tool, version, source commit, binary SHA-256 and licence, the exporter's, its `verdict`, the statement hash it checked, and how many declarations it checked |
| `kernels_agreeing` | how many independent kernels accepted the pinned theorem in this artifact; `PASS` needs 2 |
| `sandbox` | the limits the candidate's compile ran under, its peak memory and CPU time, and what the limits do not stop |

The candidate compiles once, so the second route in the record (a metaprogram
that tells separate elaborations apart) has only one elaboration to act in.
Measured on one Windows machine (2026-10-04): a warm bound check took 5 to 8 s;
the first `lean --run` after a cold start took 84 s once, so the bind step has
a 300 s limit.

Three limits of the binding. A challenge header must not use `private`
declarations, whose compiled names carry the module name and so never match.
A candidate written as a `module` file is `UNVERIFIABLE`
(`binding-unsupported`), because its proofs can sit in a part of the compiled
module the check does not read. A constant from an imported module is matched
by module name, which trusts both sides to load the same files.

### A second kernel

Lean's kernel judges the compile, and leanchecker replays the module through
the same kernel code. A bug in that kernel could accept a false proof at both
steps. So after the replay, the same compiled module goes to nanoda, a Lean 4
type checker written in Rust that shares no code with Lean's C++ kernel:

1. lean4export writes the pinned theorem and everything it depends on from
   the candidate's `.olean`, and the challenge's theorem from the challenge's.
2. A Python reader (`harness/lean_ndjson.py`) parses both exports. The
   candidate's declaration must be a theorem, its statement must hash the
   same as the challenge's (the hash ignores binder names, as Lean's own
   comparison does), and every constant the statement reaches must be
   declared identically in both.
3. nanoda type-checks every declaration in the candidate's export, permits
   only `propext`, `Classical.choice` and `Quot.sound`, and must find the
   pinned theorem among them.

| nanoda says | Result |
| --- | --- |
| accepted | `PASS`, `kernels_agreeing: 2` |
| rejected, or the exported statement differs | `FAIL`: the kernels disagree, so the check fails closed and the disagreement is a finding to investigate |
| not installed, timed out, or could not read its input | `UNVERIFIABLE` (`external-kernel-unavailable` or `external-kernel-error`); one kernel never makes a `PASS` |

Install the pinned tools once:

```sh
python scripts/provision_external_kernel.py --fetch
```

This downloads two source archives from their GitHub repositories, checks
each SHA-256 against the pin in `harness/lean_external_tools.py`, builds
nanoda with `cargo build --release --locked` and lean4export with the Lean
toolchain that compiles candidates, and writes a manifest with each binary's
SHA-256. Every check re-hashes both binaries against that manifest. It needs
cargo and elan. The pins:

| Tool | Version | Source | Licence |
| --- | --- | --- | --- |
| nanoda | 0.4.19 | `ammkrn/nanoda_lib` at `3a2407216ee84a75f9e1aead6803d0578be06ae7` | Apache-2.0 |
| lean4export | v4.34.0 | `leanprover/lean4export` at `076e8e57707e813375e8f9da8bf989799ace9680` | Apache-2.0 |

nanoda 0.4.19 has no tag or release: its last release, 0.3.2, reads an older
export format than lean4export writes for Lean 4.34. lean4export publishes
version tags and no releases. lean4lean, the other external checker, is
written in Lean, describes itself as derived from the C++ kernel and "not
really an independent implementation", and targeted Lean 4.33 when this was
built, so it was not chosen.

Measured on one Windows machine (2026-10-04, n=1 each): lean4export wrote the
`double_eq` example's export (72,567 lines) in 0.9 s, and nanoda checked its
1,428 declarations in 0.14 s.

Two agreeing kernels rule out a bug in either kernel alone producing a pass.
They do not rule out:

- a fault in how the module is read. Both kernels see the module through
  Lean's own `.olean` loader, nanoda through lean4export's export of it, so a
  loader or exporter fault that shows both the same wrong declarations passes
  both;
- a soundness bug the two implementations share, or a flaw in Lean's type
  theory itself;
- that the statement says what its author meant. `spec_fidelity` stays
  `UNVERIFIED`.

### The compile's sandbox

The candidate's code runs once, while Lean elaborates it in the one compile.
That compile now runs under limits (`harness/lean_sandbox.py`):

- On Windows: a restricted token at low integrity, which cannot write to the
  user's files or the Lean toolchain, only to the build directory (and other
  low-integrity locations); and a job object with a memory limit (8 GB by
  default, `FLYWHEEL_LEAN_SANDBOX_MEMORY_MB`), a CPU time limit (300 s,
  `FLYWHEEL_LEAN_SANDBOX_CPU_SECONDS`), at most 4 processes, the basic UI
  restrictions, and kill on close, so nothing the candidate starts outlives
  the compile.
- On Linux: `RLIMIT_AS` and `RLIMIT_CPU` with the same values. On macOS:
  `RLIMIT_CPU` only, and the receipt's memory limit is empty, because macOS
  is not known to enforce `RLIMIT_AS`. No write limit on either.
- If the limits cannot be applied, the candidate is not compiled and the
  result is `UNVERIFIABLE` (`sandbox-unavailable`).

Checked on one Windows machine (2026-10-04): a metaprogram writing into the
user's profile got "permission denied"; `import Lean` peaked at 2.1 GB and
failed under a 1,000 MB limit; a 3 s CPU limit stopped a busy loop.

The sandbox does not stop network access or reads of any file the user can
read: the candidate's code can still read a secret and send it out. A
no-network sandbox is the next step. Until it exists the receipt says
`network: not restricted`, and `validation_level` stops at
`leanchecker_replay`, short of `comparator_external`.

### What a Lean accept does not say

- The replay trusts every imported `.olean` file as it sits on disk: the
  toolchain's own, and any found through the inherited `LEAN_PATH`. The
  compile's sandbox stops the candidate from writing those files on Windows;
  on other platforms the candidate's code ran with the user's rights and
  could have changed them.
- For `lean_check` on a closed file, the axiom rung covers named `theorem` and
  `lemma` declarations only. A `def`, or a declaration that a metaprogram
  added, can rest on an axiom the audit never reads, and the replay accepts
  an axiom as a valid declaration. The math oracle's bound check walks the
  pinned theorem's dependencies from the artifact instead.
- The math oracle checks the proof against the pinned statement. Whether the
  statement is the theorem its author meant (the formalization gap) is not
  checked, and every receipt says `spec_fidelity: UNVERIFIED`.
- The `comparator_external` rung needs a sandbox without network access as
  well as the second kernel. The second kernel runs; the no-network sandbox
  does not exist yet, so no receipt reaches that rung.
