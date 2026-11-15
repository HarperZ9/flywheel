<!--
SPDX-License-Identifier: AGPL-3.0-only
-->
# Stripped-credential rebind: cross-language parity (follow-on spec)

STATUS: EXPERIMENTAL. The rebind capability is shipped in the Python reference
implementation (`emet/rebind.py`, `emet rebind`, conformance vectors tagged
`capability: "rebind"`). This document specs the cross-language (Rust / Node / Go)
port contract as follow-on work. It is NOT yet a required conformance capability;
until a second independent implementation passes the rebind vectors, the format
below is provisional.

The normative behavior is SPEC.md section 18. This document restates the parts a
porter must reproduce byte-for-byte and calls out the parity hazards the receipt
port already surfaced (see `docs/spec-findings-from-receipt-port.md`).

## What is shipped (Python reference)

- `emet/rebind.py`: `build_manifest`, `load_manifest`, `manifest_id_hash`,
  `rebind`, `rebind_manifest`. Stdlib-only, named-core sibling.
- `emet rebind <naked> --manifest <m.json> [--claim <id>]` and
  `emet rebind --build-manifest <path>=<identity> ...` in `emet/membrane.py`.
- Conformance vectors: `rebind-stripped-copy-matches`,
  `rebind-claim-wrong-bytes-drifts`, `rebind-unknown-is-unverifiable`,
  `rebind-tampered-manifest-unverifiable`.
- Behavior tests: `test_rebind.py` (library + CLI + receipt-seal).

## Byte-exact obligations for a port

1. **Manifest content address.** `manifest_id` = `sha256(canonical(manifest
   without manifest_id))`, where `canonical` is the SPEC section 7 byte form
   (sorted keys, `", "` / `": "` separators, `ensure_ascii`). A port MUST produce
   the byte-identical `manifest_id` for the same records + issued_at. The Python
   reference manifest for the single record
   `{"digest": sha256("original raw image bytes\n"), "identity": "photo-2026-001"}`
   at `issued_at = "2026-07-02T00:00:00Z"` has
   `manifest_id = e8bb63f165b8096269eb682599021a358ae77a8331e13edc10f14ac512286654`.
   A port that computes a different id has drifted its canonical form.

2. **Digest normalization.** Record digests are compared case-insensitively; the
   reference lower-cases every digest at build time and lower-cases the re-derived
   digest before lookup. A port MUST match, or an upper-case-anchored manifest will
   fail to rebind lower-case re-derived bytes.

3. **The three verdicts and their precedence.** MATCH / DRIFT / UNVERIFIABLE are
   the closed primary lattice. DRIFT dominates UNVERIFIABLE. The `--claim`
   semantics (SPEC 18.3) are load-bearing: without a claim, unknown bytes are
   UNVERIFIABLE, never DRIFT; a claim against a known identity with non-matching
   bytes is DRIFT; a claim that disagrees with a matched anchor's identity is DRIFT.

4. **Manifest integrity precedes rebind.** `rebind_manifest` re-checks
   `manifest_id` first; a manifest that does not re-derive is UNVERIFIABLE
   (`E_MANIFEST_TAMPERED`), never a MATCH off a forged anchor set. A port MUST
   refuse to rebind against a manifest whose id does not re-derive.

5. **Reason codes.** UNVERIFIABLE carries a stable machine reason code, never
   prose: `E_NO_ANCHOR`, `E_MANIFEST_TAMPERED`, `E_MANIFEST_UNVERIFIABLE`, and the
   SPEC section 9 raw-channel codes (`E_NOT_FOUND`, `E_NO_RAW_CHANNEL`) for an
   unreadable naked artifact.

6. **No authority token, ever.** The verdict is drawn from the closed primary
   lattice; a port MUST route it through the governed-verdict guard so an authority
   word (TRUSTED / APPROVED / ...) fails at construction, matching `verdict.py`.

7. **Receipt seal.** A rebind `--json` envelope carries `command = "rebind"` and a
   top-level `verdict`, so the existing witness-receipt path (SPEC section 17)
   seals it unchanged. A port's receipt over a rebind verdict MUST re-check
   RECEIPT_VALID by the same content-address rule.

## Parity hazards (learned from the receipt port)

- **Canonical JSON of nested records.** The `records` array of objects must
  serialize with sorted keys at every level. The receipt port drifted on exactly
  this; re-use the shared canonical serializer, do not hand-roll.
- **`issued_at` is addressed.** It is inside the manifest body, so two manifests
  minted at different instants legitimately differ. Tests pin it via
  `EMET_REBIND_NOW` (mirror this env seam in the port for deterministic vectors).
- **The `--build-manifest` pair split.** `<path>=<identity>` splits on the FIRST
  `=` only, so an identity may contain `=`. A port MUST split once.

## Conformance runner note

`conformance/run.py` gained a `literal` vector field: tokens listed there are
passed to the tool verbatim rather than tmp-path-joined (needed for a `--claim`
identity, which is not a file). A port's runner integration inherits this for
free because the runner is language-agnostic; a port only supplies the executable.
