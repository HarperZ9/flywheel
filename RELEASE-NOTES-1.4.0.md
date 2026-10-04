# Flywheel 1.4.0

The pre-action monitor's records can now be signed by a process the agent
cannot impersonate. A small signer runs under its own OS user on Linux or its
own account on Windows, holds a key the agent cannot read, and signs every
record once. Tool-call receipts gain an `authority` field that says what
decided each action, and the verifier re-derives it instead of trusting it. The
math oracle now checks a Lean proof against the statement its task pinned.
Preregistration heads are logged in Sigstore's Rekor beside OpenTimestamps, and
every public claim a laptop can check has a one-command recheck.

## Behaviour changes to check before you upgrade

Three checks now report a result that 1.3.4 reported as a pass.

- **Receipts with no `authority` field verify as FINDING.** Every tool-call
  receipt written before this release has no `authority` field, and the agent
  loops do not fill it yet, so almost every receipt today has none. The new
  authority check, `verify_action`, reports those as `FINDING` with cause
  `NO_AUTHORITY_RECORDED`, never as a pass. An action with nothing recorded as
  deciding it has no basis anyone can check. The receipt's seal check,
  `verify_receipt`, is unchanged and still returns `MATCH` for an intact
  receipt. (#361)
- **`flywheel monitor verify` exits 3 (`UNANCHORED`) when no key is pinned.** A
  store whose seals and links all hold, verified with no trust root, used to
  report `MATCH` and exit 0. The seals are plain sha256, so anyone who can write
  the store can rewrite it and recompute them. The old result stays in the
  report as `internal_verdict`. A script that treats exit 0 as success fails
  until you pin a key with `--trust-root` or `FLYWHEEL_SIGNER_PUBKEY`, or
  accepts exit 3. (#359)
- **Lean proofs that do not match the task's pinned statement now fail.** Before
  this release the math oracle never read its task, so any closed theorem
  passed, `theorem unrelated : True := trivial` included. A proof of a
  different, weakened or renamed statement is now `FAIL`. A task that pins no
  statement is `UNVERIFIABLE` with reason `SPECIFICATION_UNPINNED`, and no Lean
  runs. No task in this repository pins a statement yet, and the evidence-packet
  path builds its task without one, so math claims through those paths now read
  `UNVERIFIABLE` where they used to read `PASS`. (#365)

One more applies only when you turn the signer on: a store from before the
signer reads `UNSIGNED_RECORD` once you pin a key. Start a fresh monitor home
when you enable it.

## Try it

```
pip install -U "flywheel-verify[signing]"
sudo scripts/signer/setup_linux.sh /path/to/python            # Linux
.\scripts\signer\setup_windows.ps1 -Python <path to python.exe> # Windows, elevated
flywheel monitor verify <monitor home> --trust-root <public key printed by setup>
```

Setup prints the two variables the agent's hook needs, `FLYWHEEL_SIGNER` and
`FLYWHEEL_SIGNER_PUBKEY`. See `docs/SEPARATE-SIGNER.md`. On Windows, install
`Flywheel-Setup-1.4.0-x64.exe` from this release.

## A signer the agent cannot impersonate (#359)

- Runs as its own OS user (Linux, systemd) or its own local account (Windows,
  a scheduled task), with its key and journal in a home the agent's user cannot
  read. It answers on a Unix socket or a named pipe and signs only record
  attestations, store heads and policy verdicts, never bytes a caller chooses.
- Signs each record's sequence number, previous seal and seal once. A request
  to re-sign, skip or re-point a sequence number is refused. A signed head
  catches a store cut short after signing (`TRUNCATED_AFTER_SIGNING`).
- Reads the caller's identity from the operating system (`SO_PEERCRED`,
  `LOCAL_PEERCRED`, the pipe client token) and puts it inside the signed bytes:
  `separate-identity`, `same-identity` or `unattested`. A signer running as the
  agent's own user still works; every record it signs says `same-identity`, and
  the verifier warns that the agent could have read the key.
- Fails closed: if the signer is configured but unreachable, refuses, or answers
  with a key other than the pinned one, the record is not written and the call
  does not run.
- One signature per record, so the newest records are never left under plain
  hashes. On one Windows 11 machine a signature took 10.3 ms median (p95
  14.3 ms, 200 calls), almost all of it the journal's fsync, against 208 ms to
  start the hook process. Linux was not measured.
- A CI job runs the signer as a real second Linux user and checks that the
  agent's user cannot read the key, list the signer's home, or write its
  journal, and that a rewritten record is caught.

## What decided an action (#361)

Tool-call receipts can carry an `authority` field. Its basis is one of
`intent` (the human's goal, quoted, with date and source), `policy:machine` (a
rule checked outside the agent), `scope` (a role or task boundary),
`policy:self` (a rule only in the agent's own instructions) or `none`.

- `none` is a FINDING and `policy:self` is UNENFORCED. Neither is a pass.
- When scope and policy disagree, the narrower decision wins. The receipt keeps
  both and names the winner, and the event goes to a sealed disagreement log.
- A confirmation counts as `intent` only when it names the thing acted on and
  the fact that matters in the human's own words. A bare "yes" or a restated
  plan counts as `scope` at most.
- `policy:machine` comes from the signer: it runs the shipped rule pack on the
  call with the owner's context file and signs the verdict. The verifier counts
  it only under the pinned key, from a separate-identity signer, for this call,
  with the signed decision. Anything else is re-labelled `policy:self`.

See `docs/ACTION-AUTHORITY.md`.

## Lean proofs bound to the pinned statement (#365)

A task pins `challenge` before any candidate exists: theorem name, statement,
optional header and optional `statement_sha256`. The candidate compiles once,
and every later step judges that one compiled artifact. A Lean program reads
the artifact as data and requires the pinned theorem's exact elaborated type,
identical definitions behind it, and imported constants from the same modules.
Axioms come from a walk of the theorem's dependencies over the artifact; any
axiom outside `propext`, `Classical.choice` and `Quot.sound` fails. leanchecker
replays the same artifact.

Receipts move to `flywheel.lean-receipt/v2` and add `statement_sha256`,
`challenge`, `binding`, `trusted_base`, `artifact_sha256` and
`spec_fidelity: UNVERIFIED`. On Lean 4.34.1, unrelated, weakened, renamed,
shadowed-definition, shadowed-instance, `prelude`, `sorry`, custom-axiom,
metaprogram-axiom and kernel-skip probes were each refused, and the real proof
passed. `lean_check` on a closed file stays unbound by design, and its receipt
now says `statement_binding: unbound`. See `docs/PROOF-AND-FORMATS.md`.

**Published receipts that relied on the hole: none found.** The search ran on
2026-10-04 over every tracked file of this repository, the published site
sources and the owner's other public repositories. Every hit was a capability
description, a `lean_check` result on a closed file that carries its own
statement, or a disclosure of this defect (the 2026-09-23 record and the 1.0.3
notes' limits). No receipt is re-issued, so no correction is needed. The search
method is in `project-docs/records/2026-09-23-lean-oracle-task-binding.md`.

## Preregistrations anchored where the author cannot redo them (#358, #366)

`artifacts/prereg/signed-head.json` had signed the log at one entry while the
log held eight. It now carries the signed head over all eight, the head the
existing OpenTimestamps anchor already covers, and every new entry replaces it.
The original one-entry head is kept byte for byte at `heads/head-0001.json`.
CI fails if the signed head and the log disagree again. No log entry changed.
(#358)

`flywheel anchor head` logs a signed head's SHA-512 and an Ed25519ph signature
in Sigstore's Rekor and submits its SHA-256 to OpenTimestamps. Only hashes, the
signature and the public key are sent; `--dry-run` prints the entry and sends
nothing. `flywheel anchor verify` rechecks the Rekor entry offline against
Rekor's pinned key (signed entry timestamp, inclusion proof, signed checkpoint)
and the OpenTimestamps proof against its stored Bitcoin header. `--online`
refetches the entry and checks the log has not rewritten the tree. The size-8
prereg head is logged at Rekor index 3077414145 under the prereg log key, and
at 3077405366 under the receipt-signing key from a first upload. Rekor entries
are permanent, so both are kept and CI checks both. See
`docs/features/rekor-anchor.md`. (#366)

## Hashes that match on every checkout (#363, #364)

Git for Windows converts line endings by default. A fresh clone with that
setting wrote 7537 files whose bytes differed from what Git stores, so hashing a
file against a preregistration pin could give a false DRIFT.

- `.gitattributes` now defaults text files to LF on every platform. No stored
  file changed, so no published hash changes meaning.
- `harness/canonical_bytes.py` hashes a file or the stored copy at a revision
  and reports `EOL_ONLY` (exit 3, never MATCH) when line endings are the only
  difference. `python -m harness.prereg_pins <prereg.md>` checks every file pin
  in a preregistration.
- 18 published values were hashes of the CRLF form of LF files. They stay
  unchanged and verify as `EOL_ONLY` with `matched_form: crlf`. See
  `docs/CANONICAL-BYTES.md`.
- The site-designer handoff and the Inspect fixtures are pinned to their
  committed bytes, and a `canonical-bytes` workflow fails on Linux and on
  Windows with conversion on if any pinned file differs from its stored copy.
  (#364)

`RECHECK.md` defines a recheck manifest: the claim, where it is published, the
exact command, the pinned commit, hash-checked inputs, the expected verdict and
a control that must fail. `python -m harness.recheck run` runs one. Seven
manifests ship in `recheck/`; on Windows 11 the six CPU manifests passed in 7 to
21 s each, with every control refused. The METR evidence verifier now retries a
Windows file-sharing refusal for about 1.5 s and reports `INSPECT_INPUT_BUSY` if
the holder stays, where it used to report a false `INSPECT_INPUT_REJECTED`.
(#363)

## Two new receipts (#356, #357)

- **PySyft job results.** A signed receipt lets an outside party check that a
  published score came from exactly the PySyft job a data owner approved,
  without access to the model or the data. The stdlib verifier reports MATCH,
  DRIFT naming each failed check, or UNVERIFIABLE. It ran for real on syft-job
  0.1.41; 16 paired tamper tests each turn MATCH into DRIFT. Before the reveal,
  a consistent lie in the rows still passes. See
  `docs/features/pysyft-result-receipt.md`. (#356)
- **Shapley placebo test.** A preregistered measure of how often exact Shapley
  attribution credits an empty, irrelevant or shuffled source. On `qwen2.5:7b`,
  0 of 80 controls got credit (Wilson 95% 0.000 to 0.046) and 16 of 16 gold
  sources were found. An exploratory run on `qwen2.5:0.5b` credited 7 of 80, so
  the test can fail. The value function is 0 or 1, so a control that shifts
  confidence without flipping the answer is invisible to it. See
  `docs/features/shapley-placebo.md`. (#357)

The README also gains a header, hero art in light and dark, and brand marks.
(#360)

## Monitor rule pack

The rule pack is unchanged from 1.3.4, so a pinned `expected_rules_digest`
stays valid. `flywheel monitor owner` prints it as `installed_rules_digest`:

```
a76b7e8995c91861e92ce2198cd62d722deede9fb8307463c68b8aa5d5cdf8c4
```

## What this release does not prove

- A root user, or a Windows administrator who takes ownership of the signer's
  home, can read the key and sign anything. The split holds only while the
  agent runs without those rights.
- The signer attests what the hook sends it. A signature shows a record was
  submitted in order and not changed afterwards, not that it is true. A call
  the hook never saw has no record to sign.
- Signer heads stay on the same machine; no off-machine export ships yet, and
  no signer head has been anchored.
- The Windows two-account signer path is not tested end to end. Its code runs in
  CI as one user, and the setup script has been syntax-checked only.
- The receipt signing key still lives under the agent's user.
- Whether a confirmation is `intent` depends on what the human wrote. The
  restatement threshold is a heuristic, not a measured boundary.
- CI installs no Lean, so the live Lean probes ran on one machine with one
  toolchain (4.34.1). `spec_fidelity` stays UNVERIFIED: the kernel cannot tell
  whether a statement means what a person intended. The candidate's
  metaprograms still run unsandboxed during its one compile.
- A Rekor or OpenTimestamps anchor bounds time from above only. It does not show
  that the head's content is correct or that the key is the author's.
- One file in the site-designer handoff, `evidence/benchmark-ci.json`, still
  fails its manifest on every checkout setting. It changed after the manifest was
  written and is left as found.
- Every recheck manifest's anchor is `self`, and the recheck timings are machine
  time on the maker's computer.
