# Changelog

## Unreleased - 2026-10-23 - Plain notes and a scope list

The selftest notes and the rebind and receipt usage text use plain words. The
Flywheel reporter's records name their coverage list `scope` and say what each
record covers: emet-flywheel-evaluation-record, the process-audit packet record
and the packet commitment move to version 2. Version 1 records named the same
list `does_not_prove`. The reporter reads Flywheel input that names the list
either `scope` or `does_not_prove`.

## Unreleased - 2026-10-23 - Licence change to AGPL-3.0-only

The code and the software documentation move from MPL-2.0 to the GNU Affero
General Public License, version 3 only (AGPL-3.0-only), on the author's
decision of 2026-10-23. Every commit in the history is the author's own, so
the author can make this change alone.

Released versions keep their licence. Version 1.3.1 and every earlier release,
on PyPI and as GitHub tags, stay under MPL-2.0. AGPL-3.0-only applies from the
next release. The written works listed in `LICENSE-TEXT` stay CC BY 4.0.

Changed: `LICENSE`, the SPDX headers in source files, `license` in
`pyproject.toml` and `impl/rust/Cargo.toml`, the PyPI classifier, and the
licence lines in `README.md`, `SPEC.md`, `CONTRIBUTING.md`, `LICENSE-TEXT` and
the explainer page. Dated plans under `docs/superpowers/` and the deposited
paper keep their original wording as records.

## 1.3.1 - 2026-10-22 - README and package metadata

No code or spec change. The README opening now says what emet does and who it
is for, with a first run from PyPI, a comparison with sha256sum, Sigstore,
in-toto and SLSA, and its limits. The `refuse` example sets `EMET_CORPUS`,
because the wheel ships without the marker list. The PyPI summary matches the
new description, and the package author is Zain Dana Harper with
a contact address.

## 1.3.0 - 2026-09-13 - Flywheel evaluation receipts ship in the wheel

The Flywheel reporter now ships in `emet.reporters.flywheel`. It binds exact
Flywheel Inspect evidence reports, incident-simulation command outputs, and final
process-audit packet bytes to bounded metadata records and EMET witness receipts.

Added:

- **Flywheel evaluation artifact witness reporter.** `mint_receipt(raw)` accepts
  bounded UTF-8 JSON bytes for `flywheel.inspect-evidence/v1` and
  `flywheel.incident-sim-command/v1`, returns an EMET witness receipt plus fixed
  raw/metadata artifact bytes, and keeps `verdict_record` empty.
- **Process-audit packet commitment helper.** `mint_packet_receipt(raw)` accepts
  `flywheel.incident-sim-process-audit/v1` packet bytes and returns a receipt,
  fixed artifact bytes, and a commitment containing the packet hash, record hash,
  receipt id, and required whole-receipt SHA-256. The whole receipt hash, or a
  full commitment containing it, must be retained outside the packet-local digest
  graph; `receipt_id` is supplementary.
- **Bounded writer convenience.** `write_packet_artifacts(...)` writes only fixed
  packet artifact names, validates the artifact key set before creating the
  output directory, refuses existing outputs including dangling links, and uses
  exclusive creation so raced outputs fail closed. Partial reserved files may
  remain for inspection.

Boundaries:

- EMET does not import Flywheel, run Inspect, execute incident simulations, call
  scorers, access the network, independently store commitments, authenticate
  producer identity, or certify semantic truth.
- The adapter validates only the bounded projected fields it records. It is an
  integrity/provenance witness over bytes and metadata, not an approval or
  process-authority layer.
- Core dependencies remain `[]`; `SPEC_VERSION` and `spec_version` remain
  `1.0.0`; the byte-hash core and selftest TCB stay unchanged.

## 1.2.0 - 2026-08-04 - DeepEval reporter ships in the wheel

The DeepEval reporter now installs with the package. Through 1.1.0 it lived in
`adapters/deepeval_reporter.py`, which was NOT in the wheel (`[tool.setuptools]
packages = ["emet"]`), so `pip install emet[deepeval]` did not actually give a
user the reporter file. It now ships and imports after a plain install. The spec
contract stays frozen at 1.0.0 (`spec_version` unchanged); this is a
distribution-and-packaging change, not a new capability.

Changed:

- **The reporter graduated to the shipped `emet.reporters` subpackage.**
  `adapters/deepeval_reporter.py` moved to `emet/reporters/deepeval.py`, so the
  public import is now `from emet.reporters.deepeval import mint_receipt,
  build_eval_record, evaluate_and_mint`. The wheel enumerates the subpackage
  explicitly (`packages = ["emet", "emet.reporters"]`); the old `sys.path` shim is
  gone (the reporter is importable in-package). The eval receipts it mints and the
  four `eval-receipt` conformance vectors are unchanged: they verify through `emet
  check`, independent of the reporter's import path.

- **The minimal-TCB boundary is preserved (SPEC section 10).** `emet.reporters` is
  a separate, clearly-labeled OUT-OF-CORE package, not part of the named core
  (membrane, organs, monitor, corpus, verdict, report). Core `dependencies` stay
  `[]`; DeepEval stays the optional `deepeval` extra, imported LAZILY inside the
  function that runs an evaluation; no core module imports the reporter; and the
  reporter is excluded from the selftest artifact-of-record (`membrane.CORE_SRC`,
  SPEC s.14), so the zero-dependency and self-hash guarantees are unchanged.
  `emet/reporters/__init__.py` has no side effects and imports nothing heavy.

- **Version bump to 1.2.0** across `pyproject.toml`, `emet/__init__.py`
  `__version__`, and `emet/report.py` `EMET_VERSION` (the `--json` envelope's
  `emet_version`). `SPEC_VERSION`/`spec_version` remain 1.0.0.

## 1.1.0 - 2026-07-07 - Portable witness receipts, cross-language parity, experimental rebind

Verdicts now travel: a receipt made on one machine re-derives on another, in
three of the four implementations, with zero shared state. The spec contract
stays frozen at 1.0.0 (`spec_version` is unchanged); this release adds
sections 17 and 18 as new capabilities on top of it. Rebind is EXPERIMENTAL.

Added:

- **Portable witness receipt** (SPEC section 17): `emet receipt --from-json
  <file|->` turns a `verify`/`anchor`/`coherence`/`corroborate --json` envelope
  into a self-contained, content-addressed JSON receipt that a DIFFERENT party
  re-derives and checks on their own machine with the new stateless verifier
  `emet check <receipt.json> [--recompute-from-paths]` - zero shared state, zero
  trust in the producer, zero network. This lifts the section 15 limit that the
  anchor store is implementation-private so a verdict could not leave the machine
  that made it. `receipt_id` content-addresses the receipt
  (`sha256(canonical(receipt minus receipt_id, signature, and witness))`, s.17.2);
  tampering any addressed field re-hashes to a different id. An optional HMAC-SHA256 `signature` keyed by
  `EMET_RECEIPT_SIGNING_KEY` adds integrity when producer and verifier share a
  key channel. The check emits the new closed `RECEIPT` lattice
  (`RECEIPT_VALID` -> exit 0, `RECEIPT_TAMPERED` -> 1, `RECEIPT_UNVERIFIABLE` ->
  2), which maps to no authority word. Core in `emet/witness_receipt.py`; optional
  offline re-verifier convenience wrapper in
  `adapters/witness_receipt_portable.py`.

- **Stripped-credential rebind** (SPEC section 18, EXPERIMENTAL): `emet rebind
  <naked> --manifest <m.json> [--claim <identity>]` re-establishes a MATCH on
  naked bytes whose embedded provenance was stripped (the C2PA failure mode). EMET
  never bound to embedded metadata: it anchors the sha256 of the raw bytes out of
  band, so rebind re-derives the naked bytes' content hash and rebinds it to a
  known anchor in a portable, content-addressed rebind manifest
  (`emet-rebind-manifest/v1`). Verdicts are the closed primary lattice: `MATCH`
  (rebound to a known anchor) -> exit 0, `DRIFT` (a claimed identity with
  substituted bytes, or right bytes under a wrong claimed name) -> 1,
  `UNVERIFIABLE` (no known anchor - the honest default - or a manifest whose
  `manifest_id` does not re-derive) -> 2. `MATCH` is a fact of re-derivation, never
  trust, and maps to no authority word. A rebind verdict seals into a witness
  receipt (section 17) unchanged, and rides the existing tamper-evident log. Build
  manifests with `emet rebind --build-manifest <path>=<identity> ...`. Core in
  `emet/rebind.py`; four `capability: "rebind"` conformance vectors; behavior tests
  in `test_rebind.py`. Cross-language (Rust/Node/Go) parity is SPECced as follow-on
  in `docs/REBIND-SPEC.md` and is NOT yet a required conformance capability.

- **Cross-language receipt parity (Rust + Node.js).** `receipt`/`check` are now
  ported to the Rust (`impl/rust/emet.rs`) and Node.js (`impl/js/emet.js`)
  implementations, so three of the four impls can emit and offline-verify a
  receipt. The content address (`receipt_id`) is **byte-identical across
  implementations** for the same subject/verdict/spec/issued_at. Rust composes
  HMAC-SHA256 over its own hand-rolled SHA-256 (no external crate; pinned to RFC
  4231) and Node.js uses the built-in `crypto`, so both verify signed receipts as
  well as unsigned ones. Five new conformance vectors (`receipt-valid`,
  `receipt-tampered-id-flip`, `receipt-tampered-signature`,
  `receipt-unverifiable-malformed`, `receipt-subject-drift`) lock the cross-impl
  behavior; the suite is now 40 vectors. The Go implementation passes the 35 core
  vectors and does not yet implement `receipt`/`check` (its 5 receipt vectors are
  skipped by capability via `EMET_SKIP_CAPABILITIES=receipt`), the remaining
  parity item.

Changed:

- **Receipt content address excludes the `witness` block (SPEC s.17.2).** The
  per-implementation `witness` (implementation name + that implementation's own
  artifact-of-record `self_sha256`) is producer identity, not a
  re-derivation-governed field; including it made `receipt_id` intrinsically
  per-implementation and would have broken the byte-identical-across-impls
  guarantee. The address is now `sha256(canonical(receipt minus receipt_id,
  signature, and witness))`; the witness block still travels as descriptive
  metadata. Surfaced while porting to Rust/Node.js (fix-the-spec).

- **Proof-surface bundle witness** in `adapters/proof_surface_receipt.py`: a new
  `bundle <bundle.json>` subcommand that re-derives a content-addressed
  `proof-surface-bundle/v0` manifest. For every `files[]` entry it recomputes the
  sha256 of the sibling file next to `bundle.json` and compares it to the recorded
  digest. It emits an EMET witness receipt in the existing receipt shape and keeps
  the closed lattice: `MATCH` when every file re-derives, `DRIFT` when a recorded
  digest no longer matches the file on disk, `UNVERIFIABLE` when a listed file is
  missing/unreadable or the manifest is malformed or off-schema. The witness runs
  entirely in EMET (it does not import proof-surface) and preserves the
  no-authority contract: an authority-shaped token anywhere in the manifest is
  refused and the verdict never becomes `TRUSTED`.

Docs:

- **Visual-identity refresh:** a spectrum banner (`.github/assets/banner.svg`)
  now heads the README, and the static version badge is replaced with a live
  PyPI downloads badge so the README never pins a stale version.
- **README overhaul:** rewritten feature-first (a current introduction, what
  the tool does before how it is built), while keeping the honest maturity
  language: the different-author re-derivability bar (SPEC section 12) is
  still open, and the delivery contract test now covers the new surface.

## 1.0.0 - 2026-06-30 - Frozen contract, four implementations

First tagged release. The spec is frozen at 1.0.0; the reference implementations
are production-grade. 1.0.0 asserts a stable contract and solid implementations -
NOT that re-derivability is independently proven (SPEC section 12's
different-author bar stays open; the call for it stands).

Breaking (no prior tagged release existed, so no installed base to migrate):

- **Exit-code split (SPEC s.5):** `0` held; `1` a negative finding (DRIFT,
  VIEW_DIFFERS_FROM_SOURCE, QUARANTINE_READ_PATH_DIVERGENCE, BROKEN); `2`
  UNVERIFIABLE; `3` markers; `64` usage. Previously DRIFT/UNVERIFIABLE/etc. all
  collapsed to `2`. verify uses a precedence rule (a difference dominates an
  inability to check). organs and monitor adopt the same semantic.
- **selftest token rename (SPEC s.14):** the canonical token is
  `emet_self_sha256=`; the legacy `membrane_self_sha256=` alias is still emitted
  through the 1.x window and removed at 2.0. The Python artifact-of-record is now
  the sorted concatenation of the core source files, not just `membrane.py`.

Added:

- **`--json` envelope (SPEC s.13):** a machine-readable canonical-JSON output mode
  (sorted keys, `", "`/`": "`, ensure_ascii) whose governed fields are
  byte-identical across implementations; the closed lattice holds in JSON too.
- **A fourth implementation, Go** (`impl/go/emet.go`, stdlib-only, clean-room from
  the spec), joining the Python reference, Rust, and Node.js. All four pass the
  same 35 conformance vectors in CI.
- **Packaging:** installable as `emet` with an `emet` console script,
  zero runtime dependencies; the run-from-checkout story is preserved.

Freeze hardening (SPEC): pinned the reason-code enum (s.9), the audit prev-linkage
check and UTF-8 canonical-hash encoding (s.7), the `.refused` replacement token
and filename (s.4), the absent-log genesis behavior (s.13), and a warning that
default JSON encoders do not produce the canonical form. New vectors enforce the
reason codes, the governed `spec_version`, and multi-path verify precedence.

An adversarial verification pass then pinned four more edge cases with vectors and
aligned all four implementations on them: a logged fact containing an astral
(surrogate-pair) character audits INTACT (s.7); an unparseable log line is BROKEN,
not UNVERIFIABLE (s.7); `verify` of an absent+unanchored path reports E_NO_ANCHOR
(anchor-relative, s.13); and `coherence` carries the failing leg as
`source:`/`view:` in its reason (s.13). It also corrected the docs to stop listing
`self_sha256` among the cross-impl byte-identical fields - it is a per-implementation
identity (s.14), never compared across implementations. 35 conformance vectors, all
four implementations.

## 2026-06-29 - EMET Forward Delivery Contract

- Added a root delivery regression test for README, usage, changelog, funding,
  authorship, contribution, license, CI, and visual asset coverage.
- Added README sections for public value, usage, and developer workflow.
- Added the `assets/emet-hero.svg` visual identity asset.
- Renamed credential-shaped illustrative variables in documentation examples.
- Added `public-surface-sweeper` as the local delivery verification gate.
- Preserved EMET's advisory-only witness boundary and closed verdict lattice.

## Current Status

- Visibility: public-facing advisory integrity witness.
- Runtime posture: stdlib-only external verifier; no enforcement, deployment,
  signing, or actuation.
- Verdict posture: closed lattice only: `MATCH`, `DRIFT`, `UNVERIFIABLE`.
