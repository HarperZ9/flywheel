# External kernel for the Lean oracle (2026-10-04)

Status: built on branch `feat/lean-external-kernel`; not merged, not released.
Follows `2026-09-23-lean-oracle-task-binding.md` (the binding, #365) and item
B5 of the 2026-10-04 Dalrymple synthesis.

## The decision this serves

- Decision: whether a math-domain `PASS` may rest on one kernel implementation.
- Owner: the author.
- Baseline: after #365, a `PASS` meant Lean's C++ kernel accepted the compile
  and leanchecker replayed the module through the same kernel code. One kernel
  bug could produce both acceptances.
- Change made: a `PASS` now needs a second kernel that shares no code with
  Lean's (`kernels_agreeing: 2`). A missing second kernel is `UNVERIFIABLE`.
- Change trigger to revisit: nanoda or lean4export stops supporting the Lean
  line in use, or a disagreement between the kernels is observed.
- Recheck: `tests/test_lean_binding_live.py` and `tests/test_lean_sandbox.py`
  with the tools provisioned.

## Choosing the external checker

Observed 2026-10-04 from each project's GitHub repository (API metadata,
README, Cargo.toml and lean-toolchain at the named refs).

| | nanoda (`ammkrn/nanoda_lib`) | lean4lean (`digama0/lean4lean`) |
| --- | --- | --- |
| Language | Rust | Lean 4 |
| Licence | Apache-2.0 | Apache-2.0 |
| Last push | 2026-09-22 | 2026-08-29 |
| Releases | v0.3.2 (2025-09-17) newest; no Windows binary after v0.2.0; no crate | none; one tag `arena-ecb3b66` |
| Lean 4.34 | master (0.4.19) reads export format 3.1.0, which lean4export v4.34.0 writes; v0.3.2 reads 2.x only | `lean-toolchain` is `v4.33.0-rc2`; it loads `.olean` files directly, which must match the Lean build |
| Input | lean4export NDJSON | `.olean` through Lean's own loader |
| Independence | separate implementation, separate language and runtime | its README calls it derived from the C++ kernel and "not really an independent implementation" |
| Used by comparator | yes (`external_kernels`, CI builds master) | no |

Choice: nanoda. It is the only candidate that is independent of the C++
kernel in code and runtime, and the one comparator already wires in.
lean4lean was rejected on independence (its own statement) and on toolchain
lag.

Exporter: lean4export, the exporter comparator uses. It has version tags that
follow Lean's and no GitHub releases; v4.34.0 is the newest 4.34 tag.

## Pins

| Tool | Version | Source archive | Archive sha256 | Licence |
| --- | --- | --- | --- | --- |
| nanoda | 0.4.19, commit `3a2407216ee84a75f9e1aead6803d0578be06ae7` | `https://github.com/ammkrn/nanoda_lib/archive/3a2407216ee84a75f9e1aead6803d0578be06ae7.tar.gz` | `2fcf51c0fb97b909dd2b232e1a6d4c39fe0e8c9b4cb8a01c66a00e2e4b3c45c8` | Apache-2.0 |
| lean4export | v4.34.0, commit `076e8e57707e813375e8f9da8bf989799ace9680` | `https://github.com/leanprover/lean4export/archive/refs/tags/v4.34.0.tar.gz` | `ced6bf26a14dbf0c126c4d27395777eb9bd5c9e5922157f4a76f2fc9cc546617` | Apache-2.0 |

The pins live in `harness/lean_external_tools.py`. nanoda builds with
`cargo build --release --locked`, so its committed `Cargo.lock` pins every
crate. lean4export builds with `lake +leanprover/lean4:v<version> build`
under the toolchain that compiles candidates (4.34.1 here): the tag's own
`lean-toolchain` names 4.34.0, and an `.olean` loads only into the Lean build
that wrote it. The source is not modified.

Binary hashes are per machine (both builds embed their build path), so they
are not pinned in code. The provisioning script writes them to a manifest,
and every check re-hashes both binaries against it and refuses a mismatch.
On the measuring machine (rustc 1.92.0, Lean 4.34.1, Windows):
nanoda_bin `d400190e01b0fee6b1c3fcaf94c90919808abc915abb4d2075a6f98d05741176`,
lean4export `64bb8909fc93254bc51ae4780e7145dad610d3346343349b02d1f191267d5594`.

Scope note on the download approval. The approval covered official GitHub
releases or crates. lean4export publishes tags only, and no nanoda release or
crate reads the format Lean 4.34's exporter writes. Both archives came from
the projects' official GitHub repositories, pinned by commit and sha256; the
nanoda one is a commit snapshot, not a release. This is recorded so the
author can confirm or reverse it.

## What runs

After the bind check and the leanchecker replay accept, on the same `.olean`
(its hash is rechecked after this step too):

1. lean4export exports the pinned theorem's closure from the candidate's
   module and the challenge theorem from the challenge's module.
2. `harness/lean_ndjson.py` (pure Python) reads both exports. The candidate's
   declaration must be a `thm`, its alpha-invariant statement hash must equal
   the challenge's, and every constant the statement reaches must be declared
   identically in both. The export's Lean git hash must equal the compiling
   toolchain's.
3. nanoda checks the candidate's export with `permitted_axioms` set to the
   classical trio, `unpermitted_axiom_hard_error: true`, the Nat and String
   extensions on (Lean's kernel has both), and `pp_declars` naming the pinned
   theorem, so nanoda errors if it is absent.

nanoda signals a failed check by panicking (exit 101) or with `Error:` and
exit 1. Errors that mean it could not read its input are treated as judging
nothing (`UNVERIFIABLE`), not as a rejection.

Cost, one Windows machine, n=3: a bound check of the `double_eq` example took
7.8 to 8.1 s with the second kernel and 5.9 to 6.3 s without it.

## Results (live, Lean 4.34.1, Windows, 2026-10-04)

`tests/test_lean_binding_live.py` and `tests/test_lean_sandbox.py`, 30 tests,
all passed with the tools provisioned:

- the three sound proofs (`double_eq`, `True`, excluded middle with
  `Classical.choice`) pass with `kernels_agreeing: 2`;
- every #365 probe is still refused (unrelated, weakened, renamed, shadowed
  definition, shadowed instance, `prelude`, `sorry`, custom axiom,
  metaprogram axiom, kernel-skip smuggle);
- with leanchecker's replay forced to accept, nanoda alone refuses the
  kernel-skip smuggle (`bad : False`), so the pass a leanchecker miss would
  give is a `FAIL`;
- a planted disagreement (the export's proof replaced by its statement)
  gives `FAIL` with `kernels_agreeing: 1`;
- with no tools provisioned, the real proof is `UNVERIFIABLE`
  (`external-kernel-unavailable`).

The bar from B5 (every probe rejected by at least one kernel, every sound
proof accepted by both) is met on this set. No disagreement between the two
kernels on an unmodified module was observed.

## The compile's sandbox

What it does on Windows: the candidate's compile runs the toolchain's own
`lean` with a restricted (`DISABLE_MAX_PRIVILEGE`) token at low integrity,
suspended until it is inside a job object with a job memory limit (8192 MB
default), a job user-CPU limit (300 s), at most 4 active processes, the basic
UI restrictions, die-on-unhandled-exception and kill-on-close. The build
directory is labelled low integrity so the `.olean` can be written there.
Checked: a write into the user profile failed with "permission denied"; a
1,000 MB limit stopped `import Lean` (peak 2.1 GB unlimited); a 3 s CPU limit
stopped a busy loop (exit `0xC0000044`). On Linux: `RLIMIT_AS` and
`RLIMIT_CPU`; on macOS `RLIMIT_CPU` only (that macOS does not enforce
`RLIMIT_AS` is from memory, not checked here). Neither was run live with
Lean; CI runs the stubbed sandbox tests on Linux, macOS and Windows.

What it does not stop: network access, and reads of any file the user can
read. A metaprogram can read a secret and send it. Low-integrity processes
can also write to other low-integrity locations (for example
`%LOCALAPPDATA%Low`). Because of the network gap, no receipt claims
`comparator_external`; `validation_level` stays `leanchecker_replay`, and the
receipt's `sandbox` block says `network: not restricted`.

## Follow-ups

1. No-network sandbox. Windows: an AppContainer without the
   `internetClient` capability, which needs the toolchain readable by the
   container (a container-readable copy, or an ACL grant the author approves).
   Linux: a network namespace (`unshare -n`) or landrun, as comparator uses.
   With it, the bound check can claim `comparator_external`.
2. Provision the tools in CI on one runner so the live tests run there.
3. A newer Lean line needs a lean4export tag for it and a nanoda revision
   that reads its export format; both pins move together and the PR that
   moves them says why.
