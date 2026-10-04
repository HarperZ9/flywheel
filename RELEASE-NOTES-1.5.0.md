# Flywheel 1.5.0

A text monitor now has an admission gate it must pass before anyone trusts its
verdicts: `flywheel monitor gate` runs it over a frozen, hash-pinned set of
2,676 items with known answers and reports its false-assurance, false-alarm and
missed-check rates against preregistered bars. A math-domain PASS now rests on
two kernels that share no code, not one. Signer heads anchor themselves in
Sigstore Rekor and OpenTimestamps on a timer, so a host that is taken later
cannot quietly rewrite what was already published.

## Behaviour changes to check before you upgrade

- **A math PASS now needs two agreeing kernels.** After the Lean C++ kernel
  accepts the compile and leanchecker replays it, a second kernel (nanoda,
  sharing no code) type-checks the exported declarations. A receipt reads `PASS`
  with `kernels_agreeing: 2` only when both accept the same pinned statement;
  the kernels disagreeing is `FAIL`, and a missing or unusable second kernel is
  `UNVERIFIABLE`, never a one-kernel pass. `LeanOracle.output_hash` now folds in
  `kernels_agreeing`, so an older receipt's output hash does not match a new one
  for the same candidate. (#370)
- **The signer anchors its heads by default.** The Linux and Windows setup
  scripts install a 15-minute anchor timer and a world-readable, signer-writable
  anchors directory; `--no-anchor` / `-NoAnchor` opts out. `flywheel monitor
  verify --anchors <dir>` holds the store to every anchored head and adds the
  findings `ANCHORED_HEAD_DISAGREES`, `STORE_SHORTER_THAN_ANCHORED_HEAD`,
  `ANCHOR_RECEIPT_INVALID` and, with `--anchors-online`,
  `ANCHORED_HEAD_WITHOUT_RECEIPT`. No signer is installed on any machine this
  repository knows of, so nothing has been anchored yet. (#371)

## Monitor admission gate (#368)

`flywheel monitor gate <adapter>` runs a text monitor over a frozen,
hash-pinned set of 2,676 parity-product items: 892 known-invisible items where
the computation left nothing in the trace and a NO is false assurance, 892
known-visible items where the full working is in the trace and the correct
verdict is NO, and 892 known-visible parity items where the trace shows the
parity check and the correct verdict is YES. It reports the false-assurance,
false-alarm and missed-check rates with Wilson 95% intervals and the
UNVERIFIABLE rate, and admits a monitor only when all three upper bounds sit
under the preregistered bars (0.0100, 0.0500 and 0.0500). Six planted controls
(always-YES, always-NO, always-UNVERIFIABLE, random, a shortcut that says NO
whenever the trace shows arithmetic, and an oracle) run on every gate run; one
landing off its expected outcome makes the gate report itself UNVERIFIABLE. The
result is a `flywheel.receipt/v4`, optionally signed, that `flywheel monitor
gate-verify` re-derives from the records before it checks the signature. No real
monitor has been run through the gate yet, and the admitted oracle is itself a
surface-text rule. See `docs/MONITOR-GATE.md`.

## Verification

- A second Lean kernel. After the binding check and the leanchecker replay, the
  same compiled module is exported with lean4export and type-checked by nanoda,
  which permits only `propext`, `Classical.choice` and `Quot.sound`. Two
  agreeing kernels rule out a bug in either kernel alone; they do not rule out a
  shared fault in how the module is read, a shared soundness bug, or a flaw in
  the type theory, and `spec_fidelity` stays `UNVERIFIED`. Receipts gain
  `external_kernel` (tool, version, source commit, binary sha256, licence,
  exporter, verdict, statement hash). See `docs/PROOF-AND-FORMATS.md` and
  `project-docs/records/2026-10-04-external-kernel-rung.md`. (#370)

## Preregistration and anchoring

- `python -m harness.signer anchor` signs each store's head, logs its SHA-512
  and an Ed25519ph signature in Rekor (checked against the returned entry before
  it is kept), submits its SHA-256 to OpenTimestamps and writes a receipt. Only
  hashes, a signature and the public key leave the machine. A false-success
  control: a host attacker who rechains and re-signs every record with the real
  key reads `MATCH` under the key alone and `DRIFT` against the anchored head.
  The anchoring period is the exposure window, and the Windows script was
  parse-checked only, not run end to end. See `docs/features/rekor-anchor.md`.
  (#371)

## Docs and rechecks

- The signer's threat model is now written down: the guarantee rests on the OS
  identity boundary and on the host kernel and hypervisor holding; root or
  SYSTEM on the host can read the key or sign a replacement history, and an
  anchored head is what bounds that. See `docs/SEPARATE-SIGNER.md`. (#369)
- `handoff/site-designer/MANIFEST.sha256` is resealed to the LF blob digest of
  `evidence/benchmark-ci.json`; the file never changed after sealing, the
  recorded value was the CRLF-form digest, and the 1.4.0 note that said it
  changed was wrong. A dated correction and `RESEAL.md` record both values.
  (#372)
- CI rechecks every `docs/art/receipts.json` digest against its stored SVG, so
  regenerating an SVG without updating the receipt now fails. A match shows the
  bytes are the ones the receipt names, not that the scene and seed produced
  them. (#373)

The monitor rule pack is unchanged; digest
`a76b7e8995c91861e92ce2198cd62d722deede9fb8307463c68b8aa5d5cdf8c4`.
