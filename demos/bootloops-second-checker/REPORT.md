<!-- writing-profile: research -->
# Verification report: an independent second checker for BootLoops RECEIPT v1.0

Run date 2026-10-02, extended the same day (sections 9 to 15). Author: Zain Dana
Harper, with Claude Code (Claude Opus 5.5) writing and running the code. License:
MIT for the code and this report, matching BootLoops' contribution rules.

## Summary

### First run (Windows)

- **Agreement.** A clean-room checker written from `WITNESS_FORMAT.md` alone, a
  second clean-room checker in JavaScript, and BootLoops' `core.py` returned the
  same verdict on **12,187 of 12,187** witnesses (23 corpora, two primes). Table
  mode also agreed on all 12,187. **Disagreements on the corpus: 0.**
- **Controls.** All **2,920 of 2,920** control cases scored as expected on every
  checker that applies: 2,653 corrupted or shuffled inputs rejected, and 267
  true-table positive controls passed. A dummy that accepts everything and a dummy
  that rejects everything both fail the same harness.
- **Spec-edge probe.** On 14 hand-built inputs, `sc-py` and `core.py` differ on
  10. Four findings are substantive for BootLoops. `core.py` accepts a
  non-integer coefficient by truncating it. It fails a correct table row when the
  witness carries an explicit zero coefficient. Its CLI exits 1, the FAIL code,
  on a valid witness whose file name starts with `c_`. And its CLI never checks a
  recorded system fingerprint. One more case is a genuine spec ambiguity.
- **Lean 4.** Each identity is stated over `ZMod p`, checked by the kernel and
  replayed with `leanchecker`. On a seeded sample of 46 corpus witnesses, **46 of
  46** passed in column form and **38 of 38** eligible rows passed in linear form.
  All 6 corrupted witnesses were rejected. Per-column `decide +kernel` passed at
  10,000 row terms (305 s) and timed out at 30,000. Every corpus witness has at
  most 6,372 terms.
- **Replay.** Schwartz's published sunrise evaluator reproduces the page's Checks
  table exactly: 111, 110 and 109 digits at t = -3, -9 and 12. This replays his
  check against his own stored reference values. A separate textbook quadrature
  agrees with the published t = -3 value to 32 digits.
- **Negative result on inputs.** BootLoops publishes **no witness files** and does
  not ship the banked wrong-table exhibit. Every witness checked here was emitted
  locally, by BootLoops' own emitters or by this repository's generator.

### Extension, later the same day

EXTENSION-DECISION.md records, before the work began, what each extension was
meant to change in the follow-up to BootLoops.

- **Fresh-clone rerun on Linux.** The first Linux pass of `run_all.sh` stopped
  after 2 s at the input-pin check, because the pins had been hashed from a
  Windows checkout that rewrites line endings (section 9). After that fix, one pass
  from a fresh clone on Ubuntu 24.04 exited 0 in 6,304 s. Every verdict count,
  control and spec-edge result matched the first run.
- **Seed check.** The corpus regenerated on Linux from its recorded seeds is
  byte-identical to the corpus of the first run: 19,809 of 19,809 files, including
  all 12,187 witnesses. No drift (section 10).
- **Checkers from other models.** A checker written in one shot by a different
  model, from the spec and the tool page alone, passed all 12,187 witnesses in
  plain and in table mode, and reads E02, E05, E06 and E07 the way this report
  does. A second model, Qwen2.5-Coder 32B, wrote a checker that rejects 10,917 of
  the 12,187 valid witnesses (section 11).
- **Differential fuzzing.** 3,540 seeded inputs went to six checkers, and each of
  87 disagreement classes was minimized to a repro. No checker accepted a
  semantically corrupted witness. Four new `core.py` findings: two malformed
  witness shapes raise uncaught exceptions, a malformed `--table` file exits 1
  with a traceback, a system value with a fractional part is truncated, and a
  boolean `lam.idx` is read as a row number. One finding concerns the format:
  column ids above 2^53 written as JSON numbers lose precision in any checker that
  parses JSON numbers as doubles, including this repository's JavaScript checker
  (section 12).
- **Lean by reflection.** A checker proved sound in Lean lets the kernel check
  all 12,187 corpus witnesses, up from a sample of 46, in 1,729 s on 8 parallel
  jobs, with no axiom beyond `propext`, `Classical.choice` and `Quot.sound`. One
  witness passes at 300,000 row terms with a single statement literal and times
  out at 1,000,000. Splitting the statement into parts halves the time at
  300,000 terms; at 1,000,000 the run then exhausts the machine's 23 GB of memory
  (section 13).
- **Axiom audit.** Each Lean statement is fixed and hashed before any proof
  exists, and an audit module that the prover does not write restates it. All 7
  planted controls failed the audit and the honest proof passed it. One control
  shows why every layer is needed: a false theorem compiled under
  `set_option debug.skipKernelTC true` with a clean axiom list, and only the
  `leanchecker` replay caught it (section 13).
- **Published witnesses, rechecked.** The seven BootLoops repositories and the 23
  bundles linked from bootloops.ai (1,547 files) contain no RECEIPT witness and no
  system snapshot. A file named as a witness was posted on 2026-10-02 for the
  crossed light-by-light box. It is a different kind of certificate, a pickled
  kernel slice, which RECEIPT checkers cannot read (section 14).

## 1. Inputs, pinned

| input | pin |
|---|---|
| BootLoops repository | `github.com/BootLoops-ai/bootloops` commit `66b680ce742e654cfe86da4f072a69061fe182b1` |
| `tools/trust/receipt/WITNESS_FORMAT.md` | sha256 `59562276a88e11a25f482705bf241938a67340476a4e315c5ddb583d96725052` (committed bytes; see the correction below) |
| `tools/trust/receipt/core.py` | sha256 `96b0a223365cfb0be0a513a52880b34ced31269130c111ee63db689fa322beb0`, byte-identical to `tools/winnow/ibplapper/receipt/core.py` |
| `tools/trust/receipt/receipt.py` | sha256 `fa22f6fa0dea7641b2bcf403778492662f63ff936827f7a60e31c24e4d68f960` |
| `tools/trust/receipt/emitter.py` | sha256 `4cdce5422b45ca13c15bf3c170081919c5209094334c6fbc18adfa24117534d2` |
| `bootloops.ai/files/sunrise/sunrise-bundle.zip` | sha256 `609e7d82a4a01ac390d44a1f8ce9d2de695f1d84a40fd5f10233f3df00b86ee5`, fetched 2026-10-02; its own `MANIFEST.sha256` verified 19 of 19 files |
| `sunrise-evaluate.py` (also inside the bundle) | sha256 `149b83a3b73c8716c3abc84a33bc3156c2a1025565fd91a4f8fb65ad0442bb37` |
| Python | 3.12.10 with `mpmath 1.3.0`, `numpy 2.5.3`, `sympy 1.14.0`, `pytest 9.1.1` (`requirements.txt`) |
| Node.js | runs `js/check.mjs`, standard library only |
| Lean | v4.34.1 (commit `5045d005`), Mathlib tag `v4.34.1` at `d13f23b723b8a846827a245b89c10fc7d3f11612` (`lean/lake-manifest.json`) |
| Platform | first run: Windows 11, x86_64. Extension: Ubuntu 24.04 under WSL 2, Python 3.12.3, Node.js 25.2.1, the same Lean and Mathlib pins (section 9) |

**Correction, 2026-10-02.** The first version of this table and of
`inputs/bootloops-pins.sha256` gave sha256 values of the four BootLoops files as
checked out on Windows with `core.autocrlf=true`, which rewrites line endings to
CRLF. Those are not the bytes BootLoops committed, so `run_all.sh` stopped at its
pin check on Linux. The old values were `35acbf96...`, `901218fc...`, `15fcb3ad...`
and `5724ab71...`; each is the sha256 of the committed file with LF replaced by
CRLF. The table now gives the committed bytes, and `run_all.sh` hashes the git
blobs at the pinned commit, so the check no longer depends on the checkout.

Hashes of the inputs are in `inputs/`. The outputs of the reported run are in
`results/run-2026-10-02/`, hashed in its `SHA256SUMS`. Machine-local paths inside
error messages there were replaced with `<bootloops>`, `<repo>`, `<out>` or
`<path>` by `scripts/sanitize_results.py`, and the hashes cover the sanitized files.

**One command re-runs everything:**

```sh
sh scripts/run_all.sh OUT_DIR
```

It clones BootLoops at the pinned commit and stops on any hash mismatch.
`SKIP_LEAN=1` skips the Lean legs, which download Mathlib.

## 2. Independence of the second checker

`src/second_checker/checker.py` and `js/check.mjs` were written from
`WITNESS_FORMAT.md` only. One other source was read before they were finished:
the public page `bootloops.ai/tools/receipt.html`, for the system JSONL line
format, which the spec does not define ("one sparse row per line mapping an
integer column id to its value mod p").

Timeline, from `.provenance.log` and the git history:

| time (2026-10-02, PDT) | event |
|---|---|
| 01:02:13 | opened `WITNESS_FORMAT.md` |
| 01:04:22 | read the tool page for the JSONL row format |
| 01:09:51 | committed both clean-room checkers and their tests (`2b8d843`); `core.py` not yet opened |
| 01:09:57 | first opened `core.py`, `test_core.py` and `test_banked.py` |

Neither checker shares code with `core.py` or imports it. The harness in
`scripts/checkers.py` imports `core.py` only to call it as the comparison target.
One limit applies: both clean-room checkers were written in the same session by
the same model. They are not independent of each other the way two separate teams
would be. Section 4.3 shows they still differ from each other on three inputs.

Same-model checks are not independent checks, and this report labels them so.
Section 11 adds checkers that other models wrote from the same two sources.

## 3. Corpus and agreement

### 3.1 Why the corpus is emitted, not downloaded

The plan was to run the checker over every published witness. **None exist.**
A search of all seven public BootLoops repositories found witness code and
documentation, but no witness files and no published system snapshots. The search
covered file contents (`"receipt_version"`, `lambda-witness`) and file names
(`w_*.json`, `lam_*.npy`, `c_*.json`). The receipt, trust and winnow tool pages on
the site turned up none either. The archived exhibit store that `test_banked.py`
and Winnow's `test_sabotage.py` read (`RECEIPT_BANKED_ROOT`, `WINNOW_BANKED_ROOT`)
is marked "not shipped" in both files.

The corpus was therefore produced locally, by BootLoops' own code wherever it runs:

| producer | what it is | corpora | witnesses |
|---|---|---|---|
| `bl-receipt` | `tools/trust/receipt/emitter.py` (Wiedemann retrofit) | 5 | 859 |
| `bl-winnow-retrofit` | Winnow `eliminate(..., witnesses="retrofit")` | 6 | 3,776 |
| `bl-winnow-native` | Winnow `eliminate(..., witnesses="native")` | 6 | 3,776 |
| `sc-synth` | this repository's Gauss-Jordan generator | 6 | 3,776 |
| **total** | | **23** | **12,187** |

The systems are BootLoops' own three-row fixture from `test_core.py`, plus seeded
integer systems of 60, 400 and 1,500 integrals. Those have 8, 24 and 40 masters
and 15, 80 and 300 redundant rows, and each is reduced at p = 2147483647 and
p = 2147483629. The receipt emitter's direct path needs a square system (its
docstring says so), so it ran on variants without the redundant rows. Witnesses
carry 1 to 533 nonzero multipliers and 1 to 6,372 row terms. These are synthetic
systems, not IBP systems from a physics family. Section 7 states what that limits.
`results/run-2026-10-02/GEN_LOG.json` records every emitter status: all 12,187
targets came back `CERTIFIED`.

### 3.2 Results

| checker | PASS | FAIL | MALFORMED | crash |
|---|---|---|---|---|
| `core.py` (BootLoops) | 12,187 | 0 | 0 | 0 |
| `sc-py` (clean-room Python) | 12,187 | 0 | 0 | 0 |
| `sc-js` (clean-room JavaScript) | 12,187 | 0 | 0 | 0 |
| `core.py`, table mode, true tables | 12,187 | 0 | 0 | 0 |
| `sc-py`, table mode, true tables | 12,187 | 0 | 0 | 0 |

**Disagreements: 0 of 12,187.** Row-by-row verdicts are in
`results/run-2026-10-02/results/agreement.csv`.

**Timing.** Per-corpus medians with the witness files already in the OS cache:
0.06 to 0.24 ms per row for `sc-py`, 0.05 to 0.27 ms for `core.py`. Both exclude
loading the system file. The two Python checkers cost about the same per row, and
`sc-py` is about 10 percent slower on most corpora. The whole-run mean that
`agreement.json` reports for `sc-py` (5.1 ms) is an artifact: `compare.py` calls
`sc-py` first, so `sc-py` pays the cold first read of every witness file. The
JavaScript figure includes Node start-up for each batch of 200.

## 4. Controls

### 4.1 The banked wrong-table exhibit

**Not replayed, because it is not public.** Leg 3 of `test_banked.py` needs
`PAIR_RESULT.json`, `ORACLE_BLOCKS.json` and the staged `lbl3m2L_k2disp` Kira
system from the archive, and it skips when `RECEIPT_BANKED_ROOT` is unset. In its
place this report tests the exhibit's class as WITNESS_FORMAT.md defines it. A
witness that holds against the system is checked in table mode against a claimed
row that differs from the certified row. The wrong value carries the same integer
error at both primes, mirroring the exhibit's "2-prime CRT-consistent" property.
This rebuilds the class. It does not replay the banked bytes.

### 4.2 Seeded controls

Seed `20261002`, 12 witnesses sampled per corpus, fewer where a mutation does not
apply. A case scores correct when a mutant is rejected (FAIL or MALFORMED) or a
positive control passes.

| control | expected | cases | `core.py` | `sc-py` | `sc-js` |
|---|---|---|---|---|---|
| M1 one coefficient +1 mod p | reject | 267 | 267 | 267 | 267 |
| M2 one coefficient dropped | reject | 267 | 267 | 267 | 267 |
| M3 one extra coefficient | reject | 267 | 267 | 267 | 267 |
| M4 prime changed to the other prime | reject | 267 | 267 | 267 | 267 |
| M5 one lambda value +1 mod p | reject | 267 | 267 | 267 | 267 |
| M6 one lambda entry dropped | reject | 267 | 267 | 267 | 267 |
| M7 target column swapped | reject | 267 | 267 | 267 | 267 |
| M8 one value in a used system row altered | reject | 91 | 91 | 91 | 91 |
| N1 system rows shuffled, no used row left in place | reject | 267 | 267 | 267 | 267 |
| N2 lambda values permuted among indices | reject | 159 | 159 | 159 | 159 |
| X1 exhibit class: valid witness, wrong table row | reject | 267 | 267 | 267 | n/a |
| X0 exhibit control: valid witness, true table row | pass | 267 | 267 | 267 | n/a |
| **total** | | **2,920** | **2,920** | **2,920** | **2,386 of 2,386** |

The JavaScript checker has no table mode, so X0 and X1 do not apply to it.

**No-op control (N3).** Under the same scoring rule, a dummy that accepts
everything scores 267 of 2,920 and a dummy that rejects everything scores 2,653
of 2,920. The harness flags both as failing, so no checker can pass it by always
answering the same way.

### 4.3 Spec-edge probe, every disagreement

These inputs were built by hand on BootLoops' `test_core.py` fixture, target 202,
where the true row is `I_202 = 15 I_101 + 7 I_102`. None of them occurs in the
emitted corpus. They mark where the spec is silent, or where an implementation
departs from it.

| case | input | `sc-py` | `sc-js` | `core.py` | CLI rc | reading |
|---|---|---|---|---|---|---|
| E01 | `c` value `15.0` (JSON float) | MALFORMED | PASS | PASS | 0 | type strictness only; the value is right |
| E02 | `c` value `15.7` | MALFORMED | MALFORMED | **PASS** | 0 | **core truncates 15.7 to 15 and certifies a non-integer coefficient** |
| E03 | `c` value `true` | MALFORMED | MALFORMED | FAIL | 1 | both reject; core reads `true` as 1 |
| E04 | `receipt_version` as the number `1.0` | MALFORMED | MALFORMED | PASS | 0 | the schema shows a string; the field rules do not say |
| E05 | explicit zero `c` entry, table mode, true row | PASS | n/a | **FAIL** | 1 | **departs from rule 6**, which compares "after mod-p normalization and zero-dropping". Core keeps zeros in the witness `c`, drops them from the table row, and reports that "the TABLE is wrong" for a correct table |
| E06 | `c` entry equal to p, table mode, true row | PASS | n/a | **FAIL** | 1 | same cause as E05 |
| E07 | `c` contains the target column (`c[t]=5`), lambda scaled by 1-5 | PASS | PASS | FAIL | 1 | **spec ambiguity.** Rule 4 writes `{t: 1} + {m: -c[m]}`. Core overwrites the target entry; both clean-room checkers add. The witness is valid under the additive reading |
| E08 | keys `"101"` and `"0101"` in `c` | MALFORMED | PASS | PASS | 0 | core and sc-js keep the last value, so the verdict depends on key order |
| E09 | `lam.n_rows = -1`, empty lambda | MALFORMED | FAIL | FAIL | 1 | all reject |
| E10 | `lam.idx` entries as floats | MALFORMED | PASS | PASS | 0 | type strictness only |
| E11 | composite p = 15 | PASS | PASS | PASS | 0 | agree. No checker tests primality; the spec asks only for p > 1 |
| E12 | `p` as a string | PASS | PASS | PASS | 0 | agree |
| E13 | `system.fingerprint` replaced by 64 zeros | PASS | PASS | PASS | **0** | agree, but see below: **core's CLI never computes a fingerprint**, so a tampered fingerprint passes |
| E14 | valid v1 witness saved as `c_x.json` | PASS | PASS | PASS (library) | **1** | **the CLI sends any `c_*` file to the legacy reader.** On Linux it raises `KeyError: 'd0'`; on Windows it fails importing the Unix-only `resource` module. Either way an uncaught exception exits 1, the FAIL code, where the rc discipline calls for 2 |

`sc-py` and `core.py` differ on 10 of the 14 inputs (E01 to E10). Two of those
differ only in class, since both checkers reject (E03, E09). Four are type
strictness on inputs whose value is correct (E01, E04, E08, E10). The substantive
ones are E02, E05 and E06, plus the E07 ambiguity. The CLI-level findings E13 and
E14 do not show up as library-verdict disagreements. The two clean-room checkers
also differ from each other on E01, E08 and E10. JavaScript's JSON parser cannot
tell `15.0` from `15`, and the JavaScript checker does not reject duplicate key
aliases. Those differences are kept as found. The JavaScript checker was not
changed after `core.py` was read.

**Fingerprint.** Rule 2 makes the fingerprint check conditional ("when the
verifier computed its own"), and `receipt.py verify` calls `verify_many` without
one. The spec describes the fingerprint ("row order as given, columns sorted per
row, `p` prefixed") without fixing its bytes, so a clean-room implementation cannot
compute a matching value from the spec. `core.system_fingerprint` hashes the line
`p={p}`, then for each row the prefix `{i}:`, one `{col}={val % p};` per column in
sorted order, and a newline. Writing that layout into WITNESS_FORMAT.md would let a
second implementation enforce rule 2.

**Severity.** No witness written by BootLoops' own emitters is affected:
`write_witness` drops zeros, writes integers and names files `w_*`. The findings
matter for the format's stated purpose, a contract that any solver can write to.

## 5. Lean 4 kernel check

### 5.1 Statements

`src/second_checker/lean_emit.py` writes each witness in two forms over `ZMod p`:

- **Column form.** One equation per column in the union of the supports of
  `lam_i * R_i` and `e_t - sum c_m e_m`: `(sum_i lam_i * R_i[k] : ZMod p) = expect_k`.
  Each column is a lemma proved by `decide +kernel`, and the full conjunction is
  assembled from those lemmas. Trust boundary: the emitter enumerates the columns.
  A column outside that union is zero on both sides by construction, and the
  Python checkers confirm independently that the residual has no other columns.
- **Linear form.** `forall x : N -> ZMod p, sum_i lam_i * (sum_k R_i[k] * x k) = x t - sum_m c_m * x m`,
  proved by `ring_nf; reduce_mod_char` applied twice. This states the identity
  itself, with no column enumeration to trust.

No proof uses `sorry`, `native_decide` or `implemented_by`. Every module that
builds is replayed by `leanchecker` in a fresh process. Its `#print axioms`
output is checked against `{propext, Classical.choice, Quot.sound}`.

### 5.2 Corpus sample

Seed `20261002`, 2 witnesses per corpus, 46 witnesses in all. They range from 3
to 6,136 row terms (median 24), and 4 exceed 1,000 terms.

| leg | rows | result | axioms | `leanchecker` |
|---|---|---|---|---|
| column form, `decide +kernel` | 46 | **46 of 46 kernel-checked** | `propext`, `Quot.sound` | rc 0 on all 8 modules |
| linear form, rows of 100 terms or fewer | 38 | **38 of 38 kernel-checked** | `propext`, `Classical.choice`, `Quot.sound` | rc 0 on all 7 modules |
| negative: one coefficient flipped, column form | 3 | 3 of 3 rejected (`decide` proves the proposition false) | | |
| negative: one coefficient flipped, linear form | 3 | 3 of 3 rejected (unsolved goals) | | |

Time: the column form took 370 s of wall time over 8 modules of up to 6 rows, or
about 297 s after subtracting the 9.1 s Mathlib import per module. That is
**about 6.5 s per row on average**, dominated by the four rows above 1,000 terms;
the module holding the heaviest rows took 182 s. The linear form took about
**0.3 s per row** after the import. At these sizes, checking all 12,187 rows is
a matter of compute time, not of what the kernel can carry. This run checked the
sample only.

### 5.3 How far the kernel scales

Artificial valid witnesses with T row terms (10 columns per row, T/10 rows), one
module per (T, tactic), a 900 s limit, and 9.1 s for the Mathlib import alone.

| tactic and form | 10 | 100 | 300 | 1,000 | 3,000 | 10,000 | 30,000 |
|---|---|---|---|---|---|---|---|
| `decide +kernel`, one lemma per column | 9.1 s | 9.9 s | 10.9 s | 17.5 s | 48.3 s | 304.9 s | timeout |
| `decide`, one lemma per column | 19.7 s | 13.3 s | 14.5 s | 21.7 s | 55.4 s | 295.9 s | timeout |
| `norm_num <;> reduce_mod_char`, per column | 34.3 s | 10.4 s | 12.9 s | 19.2 s | 52.1 s | not run | not run |
| `decide +kernel`, one monolithic conjunction | 9.2 s | 9.7 s | 13.1 s | **fails** | | | |
| `norm_num` alone, per column | **fails** | | | | | | |
| linear form, `ring_nf; reduce_mod_char` | 11.0 s | 15.2 s | **timeout** | | | | |

Wall times include the import. The first build in a series can include file-cache
warm-up, which is why some 10-term figures exceed the 100-term ones.

Where each approach stops:

- **Monolithic `decide`** fails at 1,000 terms (199 conjuncts). Lean cannot
  synthesize the `Decidable` instance for a conjunction that large under default
  settings. One lemma per column removes this limit.
- **`norm_num` alone** fails on every row. It multiplies the numerals as integers
  and leaves goals such as `2441368740449552418 = 1` in `ZMod p`, because it does
  not reduce modulo the characteristic. Adding `reduce_mod_char` fixes it.
- **Per-column `decide +kernel` and `decide`** pass at 10,000 terms in about
  300 s and time out at 30,000. Time grows faster than linearly: about 6x from
  3,000 to 10,000 terms. Every corpus witness has at most 6,372 terms (median 18,
  90th percentile 5,869), so all of them fall below the largest size that passed.
- **The linear form** passes at 100 terms and times out at 300. It is the more
  faithful statement and the least scalable one.

`leanchecker` replay passed (rc 0) on every module that built. Each replay took
33 to 130 s, mostly spent loading the environment.

## 6. Replay of the published numerical check

The post says anyone can check a final answer "by running two scripts", but it
does not name them. The equal-mass sunrise page
(`bootloops.ai/diagrams/sunrise-equal-mass.html`) links an evaluator and a bundle,
and the bundle's index lists the evaluator and `sunrise-B34.py` as that page's
commands. This report replays that one result. **It is a replay of Schwartz's
check, not an independent derivation.** The oracle values are literals inside his
script, and the replay shows the script recomputes the closed form and matches
them, as the page states.

| command, run inside the bundle | result | page states |
|---|---|---|
| `sha256sum -c MANIFEST.sha256` | 19 of 19 OK | |
| `sunrise-evaluate.py --point -3 --point -9 --point 12` | 111, 110 and 109 digits of agreement with the stored oracle; every raising gate PASS; 2 min 5 s wall | 111, 110, 109 |
| `sunrise-B34.py --dps 60` | closed-form controls B0 to B2 at 74 to 75 digits; held-out gates B1 to B4 PASS (75 to 76 digits, capped at 60); precision-doubling gate PASS | |

Both scripts were read before they ran. They import only `mpmath`, `argparse` and
`time`, and make no network or subprocess calls.

**One outside sanity check.** `scripts/sunrise_quadrature.py` integrates the
standard two-dimensional Feynman-parameter form of the equal-mass sunrise,
`J = -integral over the simplex of 1/F` with `F = (x1x2 + x2x3 + x3x1) - t x1x2x3`
on `x1+x2+x3 = 1`, using `mpmath.quad` at 30 digits. At t = -3 it agrees with
the published value to **32.5 digits** (46.7 at 45-digit working precision),
which is the limit set by working precision. This is a textbook parametrization
at modest precision, not research-scale computation. It says nothing about
t = -9, t = 12 or higher orders in epsilon.

## 7. What this does NOT prove

- **A mod-p witness certifies one point and one prime.** A PASS says the claimed
  row lies in the row span of the given system at that (kinematic point, prime).
  It says nothing about other points, other primes, rational reconstruction, the
  symbolic table, the analytic result or the physics. The spec states this scope
  itself, and neither the checkers nor Lean widen it.
- **A witness does not certify the system.** If the system rows are wrong or
  incomplete, a valid witness still passes. That is the job of the `detect` layer,
  which this report does not test.
- **The corpus is synthetic.** No published witness or system exists, so every
  witness here was emitted locally over BootLoops' test fixture and seeded integer
  systems. Agreement on these 12,187 witnesses does not show agreement on a real
  IBP table, whose rows are larger and structured differently.
- **The banked exhibit was not replayed.** Only its class was rebuilt.
- **Lean checks the arithmetic of the emitted equations.** It now covers all
  12,187 corpus witnesses (section 13), and it does not check parsing. The column and
  reflection forms trust the emitter's column enumeration and its transcription
  of the files into numerals; the linear form removes the first trust and scales
  only to a few hundred terms. Section 13.4 maps every part of each statement to
  the spec rule it encodes.
- **The replay re-runs Schwartz's own check against his own stored oracle** and
  inherits that check's assumptions. The quadrature agrees at one point to 32
  digits and is not a derivation.
- **This work attempts no research-scale exact computation.** No multi-precision
  re-derivation of any BootLoops integral was attempted. BootLoops' exact,
  research-scale layer lies outside what this work tests.
- **Both clean-room checkers come from one author and one model.** They share no
  code with `core.py`, but they are not independent of each other.
- **The checkers from other models are model-written, one shot each.** One comes
  from a provider that does not disclose its base model, so "a different model" is
  all that can be said about its lineage. Neither is a substitute for a second
  human implementation (section 11).
- **The fuzzer finds disagreements; it does not decide which reading is right.**
  Where the spec is silent, the report says so and does not score a winner
  (section 12).
- **The published-witness search covers what is linked.** Section 14 covers the
  seven public repositories at their current heads and every bundle linked from
  the site map of bootloops.ai on 2026-10-02. Unlinked files would be missed.

## 8. Re-running a single leg

```sh
python scripts/gen_corpus.py BOOTLOOPS_ROOT OUT/corpus
python scripts/compare.py    BOOTLOOPS_ROOT OUT/corpus OUT/results
python scripts/controls.py   BOOTLOOPS_ROOT OUT/corpus OUT/results 20261002
python scripts/edge_cases.py BOOTLOOPS_ROOT OUT/corpus OUT/edge
python scripts/lean_run.py   OUT/corpus OUT/lean --per-corpus 2 --rows-per-module 6 --linear-max-terms 100
python scripts/lean_run.py   OUT/corpus OUT/lean_scale --only-scale
python scripts/compare_third.py OUT/corpus OUT/third
python scripts/fuzz.py       BOOTLOOPS_ROOT OUT/fuzz --seed 20261002
python scripts/cli_probe.py  BOOTLOOPS_ROOT OUT/cli_probe
python scripts/lean_reflect.py OUT/corpus OUT/lean_reflect --jobs 8 --sizes 10000,30000,100000,300000,1000000
python scripts/lean_reflect.py OUT/corpus OUT/lean_chunked --skip-corpus --skip-controls \
    --chunk-terms 10000 --sizes 300000,1000000 --timeout 2400
python scripts/summarize.py  OUT
```

## 9. Fresh-clone rerun on a second platform

Outputs of every extension leg are in `results/run-2026-10-02-linux/`, hashed in
its `SHA256SUMS` after the same path sanitizing as the first run.

The repository was cloned fresh into Ubuntu 24.04 under WSL 2 and `run_all.sh`
was run once, end to end. Nothing was installed system-wide. Node.js 25.2.1 came
from the official tarball (checked against its published SHA256SUMS) into the
user's home directory, and Lean came through elan in the same place. The run used
a clean `PATH` with no Windows directories on it.

| attempt | commit | result |
|---|---|---|
| 1 | `b27196f` | stopped after 2 s: the pin check failed on all four BootLoops files |
| 2 | `ac7c6a3` (pins hashed from git blobs) | exit 0, 6,304 s wall time (1 h 45 min), including the Mathlib cache download |

The first failure was this repository's error. Section 1 records
the correction. The second pass reproduced the first run:

| leg | first run (Windows) | Linux rerun |
|---|---|---|
| agreement, plain and table mode | 12,187 of 12,187, 0 disagreements | identical counts |
| controls | 2,920 of 2,920 | identical, per control kind |
| spec-edge probe | 14 cases | identical verdicts and CLI exit codes |
| Lean sample, column form | 46 of 46 | 46 of 46 |
| Lean sample, linear form | 38 of 38 (rows of 100 terms or fewer) | 39 of 39 (rows of 200 terms or fewer) |
| Lean negatives | 6 of 6 rejected | 6 of 6 rejected |
| sunrise replay | 111, 110, 109 digits | 111, 110, 109 digits |
| quadrature at t = -3 | 32.5 digits | 32.47 digits |

The one difference is a second defect of this repository. The report's Lean
sample used `--rows-per-module 6 --linear-max-terms 100`, and `run_all.sh` called
`lean_run.py` with its defaults (12 and 200), so the rerun admitted one more row
to the linear form. `run_all.sh` now passes the flags the report used.

Lean runs much faster on Linux here. Importing Mathlib took 1.15 s against 9.1 s
on Windows, and the scale series moved:

| tactic and form | 10,000 | 30,000 | 100,000 |
|---|---|---|---|
| `decide +kernel`, one lemma per column | 90.7 s | 699.5 s | timeout (900 s) |
| `decide`, one lemma per column | 94.7 s | 731.1 s | timeout |

| linear form, `ring_nf; reduce_mod_char` | 100 | 300 | 1,000 |
|---|---|---|---|
| wall time | 4.0 s | 458.8 s | timeout (900 s) |

So the per-column ceiling of the first run, "passed at 10,000, timed out at
30,000", was a property of that machine and platform. On Linux the same encoding
passes at 30,000 and stops below 100,000.

## 10. Seed check

The corpus was regenerated on Linux by `gen_corpus.py` from its recorded seeds
and compared file by file, by sha256, with the corpus of the first run.

| what | first run | Linux regeneration |
|---|---|---|
| files | 19,809 | 19,809 |
| identical by sha256 | | **19,809 of 19,809** |
| witness files identical | | **12,187 of 12,187** |
| digest over all witness hashes | `a20d3a4fec860308...` | `a20d3a4fec860308...` |

No drift. The files cover systems, tables, metadata, every witness, and Winnow's
own witness directories. The generator, BootLoops' Winnow and receipt emitters and
NumPy's seeded generator therefore give the same bytes on both platforms.

## 11. Checkers written by other models

### 11.1 Protocol

Both clean-room checkers in sections 2 to 4 came from one model in one session.
To test whether the findings depend on that, other models were asked to write a
checker from the same two sources and nothing else. The prompt,
`third_checker/task.txt`, holds `WITNESS_FORMAT.md` at the pinned commit (sha256
`59562276...`), the text of the public tool page (sha256 `3edffafb...`), and a
short I/O contract written for this test. The page text is not redistributed,
since the page states no license; `third_checker/build_task.py` rebuilds the
exact prompt from a saved copy and checks both hashes. The I/O contract covers
arguments, one JSON line per witness, exit codes, never crash, ignore the fingerprint. No model saw `core.py`, any
BootLoops test, this repository's checkers, or any corpus witness before it
wrote its first version. Every raw response is kept in `third_checker/`, and each
checker file is the model's code byte for byte under a provenance header.

| checker | model | how | sources seen |
|---|---|---|---|
| `check3_v0.py` | Qwen2.5-Coder 32B Instruct, Q4_K_M, local Ollama 0.35.0 (Alibaba Qwen family) | one shot, temperature 0, seed 20261002 | `task.txt` only |
| `check3_v1.py` | same model | one repair round | `task.txt`, its own v0 code, and its v0 verdicts on four valid witnesses (BootLoops' 3-row fixture and one synthetic witness), with two interface rules restated |
| `check3_abl.py` | abliteration.ai `abliterated-model-large-v2`; the provider does not disclose the base model, so its family is unknown | one shot, temperature 0, seed 20261002, reasoning effort low | `task.txt` only |

Two earlier calls to the abliteration.ai model at default reasoning effort spent
the whole token budget, 16,000 and 60,000 tokens, on reasoning and returned no
code. Those responses are kept. The local Ollama server for Qwen was started for
this test on its own port, stopped by its process id afterwards, and GPU memory
fell back to the level measured before it started (990 MiB against 1,122 MiB).
A separate Ollama process that was already running was not touched.

The v1 feedback tells the model that four witnesses are valid. That fact comes
from the agreement of the three existing checkers, so v1 is not fully
independent of them. It is labelled that way here.

### 11.2 Results on the corpus

| checker | plain mode | table mode | non-PASS reasons |
|---|---|---|---|
| `check3_abl.py` | **12,187 of 12,187 PASS** | **12,187 of 12,187 PASS** | none |
| `check3_v0.py` | 1,270 PASS, 10,917 FAIL | same | computes its own fingerprint, against the contract (8,411); keeps zero entries in the residual (2,506) |
| `check3_v1.py` | 3,979 PASS, 8,208 FAIL | same | keeps zero entries in the residual (8,208) |

Every corpus witness is valid, so each FAIL from v0 and v1 is a false reject by
that checker. Their bug is the zero-dropping step of rule 3: they compare a
residual that still holds `col: 0` entries with an expected vector that does not.
The repair round removed the fingerprint code and left that bug in place, while
the model's own change list claimed it had fixed every defect.

### 11.3 Results on the 14 spec-edge inputs

| case | `sc-py` | `core.py` | `check3_abl` | `check3_v0` | `check3_v1` |
|---|---|---|---|---|---|
| E01 `c` = 15.0 | MALFORMED | PASS | MALFORMED | FAIL | FAIL |
| E02 `c` = 15.7 | MALFORMED | **PASS** | MALFORMED | FAIL | FAIL |
| E03 `c` = true | MALFORMED | FAIL | MALFORMED | FAIL | FAIL |
| E04 version as number | MALFORMED | PASS | MALFORMED | FAIL | FAIL |
| E05 explicit zero `c`, true table | PASS | **FAIL** | PASS | FAIL | FAIL |
| E06 `c` entry = p, true table | PASS | **FAIL** | PASS | FAIL | FAIL |
| E07 `c[t]` on the target | PASS | FAIL | PASS | FAIL | FAIL |
| E08 key alias `"0101"` | MALFORMED | PASS | PASS | FAIL | FAIL |
| E09 `n_rows` = -1 | MALFORMED | FAIL | MALFORMED | FAIL | FAIL |
| E10 `idx` as floats | MALFORMED | PASS | MALFORMED | FAIL | CRASH |
| E11 p = 15 | PASS | PASS | MALFORMED (tests primality) | FAIL | FAIL |
| E12 p as string | PASS | PASS | MALFORMED | CRASH | CRASH |
| E13 fingerprint zeroed | PASS | PASS | PASS (told to ignore it) | FAIL | FAIL |
| `c_` file name, library | PASS | PASS | PASS | FAIL | FAIL |

The checker from the undisclosed model reaches the same verdict as this report on
each substantive `core.py` finding: it rejects E02, passes the correct table rows
of E05 and E06, and reads rule 4 additively in E07. It is stricter than `sc-py`
on types, and it adds a primality test that the spec does not ask for. The Qwen
checkers fail the base witness itself, so their E-case verdicts carry no
information.

**What this adds to the independence claim.** A model other than the one that
wrote `sc-py` and `sc-js`, given only the spec and the tool page, wrote a checker
that agrees with `core.py` on every valid corpus witness and agrees with this
report's reading of the spec where `core.py` departs from it. The second model
family tried did not produce a usable checker. Both results stand.

## 12. Differential fuzzing

### 12.1 Design

`scripts/fuzz.py` with `scripts/fuzz_cases.py` builds small valid witnesses over
random sparse systems, then applies named mutations. Each base is fixed by
(seed, base id): primes from 2 to 2147483647, 2 to 6 rows, and column ids that
are either up to 10^6 or, for 5 of the 20 bases, between 2^52 and 2^62. There are
76 mutations: 5 semantic corruptions that every checker must reject, and 71
changes of type, encoding, key spelling, value range, file format and table mode,
where the spec is often silent. Phase 1 applies every mutation alone to each of
20 bases (1,520 cases). Phase 2 applies 2,000 random stacks of 2 or 3 mutations.
20 unmutated bases are controls. Seed 20261002; every case can be rebuilt from
(seed, base id, case id, mutation list).

The six checkers are `core.py` (library `verify_row`), `sc-py`, `sc-js`,
`check3_abl`, `check3_v0` and `check3_v1`. A verdict is classed accept (PASS),
reject (FAIL or MALFORMED) or crash (no verdict). A case is a disagreement when two
checkers give different classes. Every disagreement signature was minimized once:
mutations were dropped while the signature held, then the base was shrunk to 2
rows and 3 columns where possible. The 14 spec-edge cases of section 4.3 stay as
they are and are not replaced by the fuzzer.

### 12.2 Results

3,540 cases ran on Linux, and 87 disagreement classes were minimized into
`fuzz/repros/`. The fuzzer, the corpus run of the model-written checkers and the
CLI probe took 1,063 s together. A preliminary Windows run (3,520 cases, 75
mutations, 88 classes, no per-case output) is not used for any number here.

- **No false accept on corruption.** 468 cases carried a semantic corruption.
  Every checker rejected every one of them, with three exceptions in total, each a
  generator artifact on inspection: a later table mutation replaced the corrupted
  table, a row mutation was skipped after `lam.idx` had become floats, and one
  case at p = 2 holds under the additive reading.
- **Unmutated controls.** `core.py`, `sc-py` and `check3_abl` accepted all 20.
  `sc-js` rejected 5, which are exactly the bases with column ids above 2^53. The
  Qwen checkers rejected 1, a zero-dropping case.
- **Crashes over all 3,540 cases.** `sc-py` 0, `sc-js` 146, `core.py` 157,
  `check3_abl` 413, `check3_v0` 903, `check3_v1` 908. A crash means the checker
  raised an exception and returned no verdict line.

Single-mutation verdicts where `core.py` stands apart, out of 20 bases each
(A accept, R reject, C crash):

| mutation | `core.py` | `sc-py` | `sc-js` | `check3_abl` | reading |
|---|---|---|---|---|---|
| `c` value + 0.5 | A20 | R20 | R20 | R20 | E02 again |
| system value + 0.5 | **A20** | R20 | R20 | C20 | **new: `int(v)` truncates system values too** |
| `c` as a JSON array | **C20** | R20 | R20 | R20 | **new: uncaught `AttributeError`** |
| a `lam.val` of `Infinity` | **C20** | R20 | R20 | R20 | **new: uncaught `OverflowError`** |
| `lam.idx` booleans | **A20** | A6 R14 | A6 R14 | A6 R14 | **new: `int(True)` is row 1** (the 6 are bases where no index was 0 or 1) |
| `receipt_version` as number 1.0 | A20 | R20 | R20 | R20 | E04 again |
| `c[t]` on the target | A2 R18 | A20 | A15 R5 | A20 | E07 again |

### 12.3 New `core.py` findings, with exit codes

`scripts/cli_probe.py` runs `receipt.py verify` on one input per finding. The rc
discipline in WITNESS_FORMAT.md asks for exit code 2 on malformed input, which it
defines as input that cannot be interpreted. The expected codes below are this
report's reading of that rule.

| probe | rc | rc this report expects | what happens |
|---|---|---|---|
| valid witness | 0 | 0 | PASS |
| `c` as a JSON array | **1** | 2 | traceback, `AttributeError` from `w["c"].items()` in `load_witness` |
| `lam.val` contains `Infinity` | **1** | 2 | traceback, `OverflowError` from `int(float("inf"))`; `NaN` is caught and gives 2 |
| `--table` file is not JSON | **1** | 2 | traceback, `MalformedInput` raised at `receipt.py` line 110, outside any `try` |
| `--table` row is not an object | **1** | 2 | traceback, `AttributeError` that `_load_table_json` does not catch |
| system value with a fractional part | **0** | 2 | `load_system_jsonl` truncates with `int(v)` and the witness passes |
| `lam.idx` = `[false, true]` | 0 | not stated | read as rows 0 and 1 |
| a system row with keys `"852013"` and `"0852013": 0` | 1 | not stated | both keys become column 852013 and the last one wins, so the zero erases the real value |

Exit code 1 means "a row failed". A pipeline that treats 1 as a verdict would
read a broken table file, or a witness it could not parse, as a table that failed
verification. The truncation finding matters more: a system snapshot whose values
are not integers is read as a different system, silently. BootLoops' own emitters
write integers, so none of this touches witnesses they produce.

### 12.4 A format finding: column ids above 2^53

The schema writes `target.col` as a JSON number, and the spec's example is
`141321603907593`, below 2^53. The tool page mentions a 64-bit weight decode for
Kira. A JSON parser that reads numbers as IEEE doubles, which is the default in
JavaScript and in many other languages, rounds any integer above 2^53. This
repository's own `sc-js` therefore fails valid witnesses whose target column is
above 2^53. Python's parser keeps exact integers, so `core.py` is unaffected.
Column ids used as object keys are strings and are safe. If ids can exceed 2^53,
the spec could say so and allow `target.col` as a decimal string, or cap ids at
2^53 - 1. This was found by the fuzzer, through a defect in this repository's
checker. It is an interoperability point for the format, and `core.py` handles these ids correctly.

## 13. Lean 4 by reflection, with an axiom audit

### 13.1 Method

`lean/ReceiptLean/Reflect.lean` defines, for one column, the proposition

```
ColOK p ts pos neg  :=  (sum over (l, v) in ts of (l : ZMod p) * (v : ZMod p)) = pos - neg
```

where `ts` lists the pairs `(lam_i, R_i[k])`, `pos` is 1 on the target column and
0 elsewhere, and `neg` is `c_k`. `AllOK p cols` is `ColOK` for every listed column.
A Boolean checker, `allCheck`, decides the same thing with natural-number
arithmetic, and `allCheck_sound` proves that `allCheck p cols = true` implies
`AllOK p cols`. Each witness is then proved by one `decide +kernel` on
`allCheck`, which the kernel evaluates with GMP-backed numerals. The soundness
proof is about 30 lines and is checked once.

`scripts/lean_reflect.py` writes three modules per batch of witnesses, in order:

1. **Spec**: `def stmt_k : Prop := ReceiptLean.AllOK p [...]`, one per witness. Its
   sha256 is recorded before any proof file exists.
2. **Prf**: imports Spec and proves `theorem prf_k : stmt_k`.
3. **Aud**: written by the auditor, never by the prover: `theorem aud_k : stmt_k :=
   prf_k` and `#print axioms aud_k`. If `prf_k` proves anything other than the fixed
   `stmt_k`, this module does not compile.

A batch passes the audit only if all of these hold: the Spec file still has its
recorded hash; Prf and Aud compile; every `aud_k` depends on no axiom outside
`propext`, `Classical.choice` and `Quot.sound`; the Prf source contains no
`sorry`, `admit`, `axiom`, `native_decide`, `implemented_by`, `@[extern` or
`unsafe`; and `leanchecker` replays Prf and Aud with exit code 0.

### 13.2 Planted controls

Each control is one witness of 100 terms. Run on Linux; the same eight results
came out of a Windows run.

| control | what the prover did | audit | caught by |
|---|---|---|---|
| P0 honest proof | `allCheck_sound` and `decide +kernel` | **pass** | |
| P1 axiom assumes the result | `axiom key : stmt`, then `prf := key` | fail | axiom set (`key_ctl`) and source scan. `leanchecker` passed it |
| P2 `sorry` | `prf := by sorry` | fail | axiom set (`sorryAx`) and source scan. `leanchecker` passed it |
| P3 weakened statement | `theorem prf : True` | fail | Aud does not compile (type mismatch) |
| P4 statement edited after it was fixed | Spec rewritten to `stmt := True`, proved by `trivial` | fail | Spec hash only. Every other check passed |
| P5 `native_decide` | trusts the compiler | fail | axiom set (`..._native.native_decide.ax_1_1`) and source scan |
| P6 kernel skipped on a false claim | corrupted witness, `set_option debug.skipKernelTC true` | fail | `leanchecker` only (exit 1). It compiled, and its axiom list was clean |
| N1 corrupted witness, honest attempt | `decide +kernel` on a false claim | fail | Prf does not compile: `decide` proves the proposition false |

P1 is a known failure mode of AI-written proofs: the proof is completed by adding
an axiom that assumes the missing lemma. It compiles and it
replays under `leanchecker`, so a kernel replay alone does not catch it. P4 and P6
show the other two gaps: without the statement hash a prover can change what is
proved, and without the replay a module can switch off the kernel check. Each
check in the audit catches at least one control that the others miss.

### 13.3 Results

| run | result |
|---|---|
| whole corpus | **12,187 of 12,187 witnesses** kernel-checked and audited, in 462 batches; 1,729 s wall time with 8 parallel jobs (10,747 s of compile time in total) |
| axioms used, every batch | `propext`, `Classical.choice`, `Quot.sound` |
| `leanchecker` | exit 0 on all 924 Prf and Aud modules |

How far one witness scales, with one statement literal (Linux, 1,800 s limit per
compile):

| row terms | Spec (elaborating the statement) | Prf (the proof) | Aud |
|---|---|---|---|
| 10,000 | 11.0 s | 1.7 s | 0.7 s |
| 30,000 | 39.7 s | 5.4 s | 0.8 s |
| 100,000 | 174.1 s | 27.9 s | 1.1 s |
| 300,000 | 1,229.7 s | 80.9 s | 1.4 s |
| 1,000,000 | **timeout** (1,800 s) | | |

With the statement split into `def` parts of about 10,000 terms each, joined by
`++` inside `AllOK` (same proposition, 2,400 s limit per compile):

| row terms | Spec | Prf | Aud |
|---|---|---|---|
| 300,000 | 553.9 s | 98.0 s | 5.7 s |
| 1,000,000 | **timeout** (2,406 s), with the Lean process at 22 GB of the machine's 23 GB | | |

**Where it stops.** One witness passes at 300,000 row terms, 30 times the
10,000 reported this morning, and fails at 1,000,000 in both forms. Chunking
inside one module halves the elaboration time and leaves memory as the limit.
Putting each part in its own module, compiled separately, would be the next step
and was not tried.

The proof itself is cheap and grows close to linearly. What stops the
single-literal form is elaborating the statement, a list literal of up to a
million pairs, which grows faster than linearly. The per-column `decide` form of
section 5 stops below 100,000 terms on the same machine, so reflection moves the
ceiling for one witness by more than an order of magnitude. Every corpus witness
has at most 6,372 terms.

### 13.4 Statement fidelity (model-made review)

Lean proves the theorem as stated. Nothing in the kernel checks that the stated
theorem says what WITNESS_FORMAT.md says. The table below maps each part of the
three Lean statement forms to the spec rule it encodes. **This review is
model-made** (Claude Opus 5.5, the same model that wrote the emitters). It has
not been checked by a person or by a second model.

| spec element | column form | linear form | reflection form | where the Lean statement is weaker or different |
|---|---|---|---|---|
| arithmetic mod p (rules 3 to 5) | `ZMod p`, p the witness's literal | same | same | p is not required to be prime. The identity is a ring identity, so primality is not needed for it to mean what rule 5 says. No gap |
| system rows R_i and their order (rule 1, `idx` indexes row ORDER) | numerals copied in by the Python emitter from `rows[i]` | same | same | **The system file is not in the statement.** The emitter's transcription from file to numerals is trusted. `lam.n_rows` and the row-count check of rule 1 do not appear at all |
| fingerprint (rule 2) | absent | absent | absent | not encoded; the spec gives no byte layout (section 4.3) |
| residual equals `e_t - sum c_m e_m` (rules 3 to 5) | one equation per column in the union of supports | one equation of linear forms, `forall x : N -> ZMod p` | one `ColOK` per listed column | **Column and reflection forms trust the emitter's column enumeration.** A column the emitter leaves out is not checked by Lean. The Python checkers confirm independently that the residual has no other columns. The linear form has no such gap, and it scales only to a few hundred terms |
| which column each equation is about | `-- col k` comment only | `x k` in the statement | absent (the list carries no column ids) | in column and reflection forms the column ids are not part of the proposition, so a relabelled column gives the same theorem |
| `c[t]` on the target column (rule 4, E07) | `1 - c_t` | `x t - c_t * x t` | `pos = 1, neg = c_t` | all three encode the **additive** reading, which `core.py` does not use. The Lean result says nothing about which reading the spec intends |
| zero-dropping (rules 3, 4, 6) | not needed over `ZMod p` | same | same | no gap: equality in `ZMod p` ignores zero entries |
| table mode (rule 6) | absent | absent | absent | Lean certifies the witness's own `c`, never a claimed table row |
| column ids are integers | natural-number literals | `N`, so a negative id would not elaborate | not used | a negative column id fails to compile rather than being misread |
| axioms, statement drift | `#print axioms` checked | same | **audit module written by the checker**: `aud_k : stmt_k := prf_k`, statement hash fixed before proof, axiom set, source scan, `leanchecker` | the first two forms check axioms but do not fix the statement before the proof; the reflection runner does |

What the Lean result means, read through this table: for each listed column, the
numbers the emitter copied from the witness and the system satisfy the column
equation in `ZMod p`, and the kernel checked that arithmetic with no axiom beyond
`propext`, `Classical.choice` and `Quot.sound`. It is an independent check of the
arithmetic. It is not an independent check of parsing, of rule 1, or of the
column enumeration.

## 14. Published witnesses, rechecked

The first search found no published witness files. It was repeated on
2026-10-02, after the first report.

- **Repositories.** `gh repo list BootLoops-ai` shows seven public repositories.
  The `bootloops` head is still the pinned commit `66b680ce`. The full file trees
  of all seven at their heads (3,991 files) contain no file matching `w_*.json`,
  `lam_*.npy`, `c_*.json` or `EMIT_REPORT.json`. The six JSONL files belong to
  unrelated tools (terrier and longhand). Content search finds `receipt_version`
  and `lambda-witness` only in code and documentation.
- **Site.** All 125 HTML pages in the bootloops.ai site map were fetched, and all
  23 downloadable bundles they link (69.3 MB, 1,547 files) were scanned for the
  witness-format markers `receipt_version`, `lambda-witness` and
  `system_fingerprint` and for witness-like file names. **No RECEIPT witness and
  no system snapshot.**
- **One new file, a different object.** The crossed light-by-light box page links
  `lbl3x-witness-bundle.zip` (12.6 MB, served with Last-Modified
  2026-10-02 16:29 UTC). Besides its license and notice files it holds one data
  file, `slice_n1_exact.pkl.gz`, which the
  bundle describes as "the exact rational numerator columns" of a kernel bank,
  read by `lbl3x-evaluate.py --theorem-check`. Its sha256 (`bfd98ffc...`) matches
  both `witness_manifest.json` and `MANIFEST.sha256` in the main lbl3x bundle. It
  is not a RECEIPT witness and none of the checkers here can read it. It is a
  Python pickle, and loading a pickle runs code, so it was hashed and not opened.

The statement in section 3.1 therefore stands as of 2026-10-02: no RECEIPT
witness or system snapshot is published.

## 15. Prose check log

The new prose in this report (summary, sections 9 to 14, the correction in
section 1) and the follow-up email draft were run through the Articulate prose
checker on 2026-10-02. First passes flagged four phrases ("rather than",
"instead of" twice, and one ", not Y" construction), which were rewritten. Final
verdicts: report text clean (texture score 0, in three passes covering 1,010, 948
and 331 words), email draft clean (texture score 0, 195 words). The checker names
prose patterns; it does not check facts.
