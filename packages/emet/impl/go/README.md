# EMET -- Go fourth implementation

A clean-room fourth implementation of the EMET core, written against `SPEC.md`,
`conformance/vectors.json`, and `conformance/markers.corpus` ONLY -- without
reading the Python reference (`membrane.py`, `report.py`), the Rust port
(`impl/rust/emet.rs`), or the Node port (`impl/js/emet.js`). Pure Go, standard
library only (`crypto/sha256`, `encoding/hex`, `os`, `os/exec`), zero
third-party dependencies.

Purpose: an INDEPENDENT fourth codebase, in a fourth language, that passes the
same conformance vectors. Every additional independent implementation that
agrees converts re-derivability (SPEC section 12) further from asserted toward
demonstrated.

## Build and test

Standard library only, `CGO_ENABLED=0`:

    go build -o emet.exe emet.go
    python ../../conformance/run.py ./emet.exe

Expected: `CONFORMANCE 27/27 vectors pass`.

Status: built and PASSING 27/27 with Go 1.23.4 on Windows (windows/amd64).

## Design notes

- **Byte-hash core.** `verify`, `coherence`, `corroborate`, `anchor`, and
  `audit` depend only on SHA-256 over exact raw bytes (`os.ReadFile`, never a
  transformed view). No normalization, no transcoding -- a lone CRLF rewrite
  drifts, by design (SPEC s.3).

- **Verdict lattice is closed** (SPEC s.2). The only integrity verdicts emitted
  are `MATCH | DRIFT | UNVERIFIABLE`, plus the closed auxiliary tokens
  `COHERENT / VIEW_DIFFERS_FROM_SOURCE`,
  `CORROBORATED / QUARANTINE_READ_PATH_DIVERGENCE`, and `INTACT / BROKEN`. No
  codepath emits `TRUSTED`, `APPROVED`, `SAFE`, or any authority word.

- **UNVERIFIABLE reason codes are a fixed machine enum** (SPEC s.9), never
  prose: `E_NOT_FOUND`, `E_NO_RAW_CHANNEL`, `E_NO_ANCHOR`, `E_NO_CORPUS`,
  `E_NO_CORPUS_VERSION`, `E_NO_SECOND_READ_PATH`, `E_LOG_CORRUPT`.

- **Second read path for `corroborate`.** The disjoint channel is a child
  process of this same binary (the hidden `__rawhash` internal subcommand)
  that re-reads and re-hashes the target. This satisfies "hash the same file
  via disjoint read paths" (SPEC s.4). With only two channels available this
  impl emits `CORROBORATED` where a VCS-aware impl might emit `QUARANTINE`;
  SPEC s.4 declares the read-path set implementation-defined, so this is
  expected, not a violation.

- **Audit chain** (SPEC s.7): `chain = SHA-256(prev + kind + canonical_json(fact))`,
  `prev` = the prior entry's chain, genesis `prev` = 64 zeros. The `kind` is
  bound into the chain, so relabeling an operation is tamper (`BROKEN`). `audit`
  re-derives each chain from the bytes actually stored, so it verifies any
  conforming log regardless of which implementation wrote it. An absent log is
  genesis: `chain=INTACT log_entries=0`, exit 0.

- **Marker count** (SPEC s.16): a non-overlapping leftmost scan in corpus order.
  At each byte position the markers are tested in corpus order; the first that
  matches (ASCII case-insensitive substring over raw bytes) is counted and the
  cursor advances past the matched span; on no match the cursor advances one
  byte. A repeated marker counts once per occurrence.

- **`refuse`** writes a `<file>.refused` copy with every matched span replaced by
  the byte string `[REFUSED-IN-BAND-AUTHORITY]`, and NEVER modifies the input
  (SPEC boundary 6). It obeys no matched claim.

- **selftest** hashes the **compiled binary** (`os.Executable` + read), because
  a compiled implementation's artifact-of-record is the binary (SPEC s.14) --
  build-dependent, not source-reproducible across rebuilds. It emits both the
  canonical `emet_self_sha256=` line and, through the 1.x deprecation window,
  the legacy `membrane_self_sha256=` alias with the identical hex.

- **`--json` envelope** (SPEC s.13): a global `--json` flag, accepted before or
  after the subcommand and stripped from argv. In `--json` mode exactly one
  canonical-JSON object is written to stdout and no human lines. Canonical JSON
  is hand-rolled to match `python json.dumps(obj, sort_keys=True)` byte-for-byte
  (keys sorted, `", "` / `": "` separators, `ensure_ascii` escaping, and NO
  escaping of `<` `>` `&` -- which Go's default `encoding/json` would escape).
  The exit code is identical with or without `--json`.

## Honest limits

Same as the spec's section 11: the marker denylist is not a proof of
cleanliness; selftest proves integrity only relative to an uncompromised
substrate (an external verifier must be the check of record); EMET judges bytes
and provenance, never meaning.
