# EMET Specification

- Spec version: 1.0.0
- Status: STABLE -- frozen and normative for the v1.0 reference implementations
- License: AGPL-3.0-only (MPL-2.0 for releases up to 1.3.1)

EMET is an externally-anchored integrity layer for AI oversight, attribution,
and accountability. This document is normative: an implementation conforms if
and only if it satisfies every MUST here and passes conformance/vectors.json at
the stated corpus_version.

## 1. Terminology

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, MAY are interpreted as in
RFC 2119.

- Artifact -- a sequence of raw bytes addressed by a path.
- Anchor -- a pinned (path, sha256) recording the bytes of an artifact at a
  moment the operator authorized.
- Verdict -- a member of the closed lattice in section 2.
- Marker -- a known in-band authority-injection or laundering signature.

## 2. The verdict lattice (closed)

Every integrity judgement EMET emits MUST be exactly one of: MATCH, DRIFT, or
UNVERIFIABLE.

This enum is CLOSED. An implementation MUST NOT define, emit, or accept any other
verdict -- in particular it MUST NOT emit TRUSTED, APPROVED, or SAFE, or any
value asserting authority or permission. Absence of DRIFT is reported as MATCH
(re-derivation agreed) or UNVERIFIABLE (no raw-byte anchor), never as trust. This
is boundary 1 -- facts, not authority -- encoded in the output type itself.

Auxiliary judgements are likewise closed: coherence emits COHERENT or
VIEW_DIFFERS_FROM_SOURCE; corroboration emits CORROBORATED or
QUARANTINE_READ_PATH_DIVERGENCE; a marker scan emits a non-negative integer
count. The monitor report (the report command of the Python-core monitor) is
likewise a governed, closed auxiliary judgement: per baseline it emits exactly
INTACT or CHANGED, and per file it emits exactly MATCH, DRIFT, or MISSING. None
of these is, or maps to, TRUSTED. The monitor is Python-core tooling governed by
this spec plus test_monitor.py; it is not exercised by the cross-language
conformance vectors (section 12), so these auxiliary tokens are pinned here, not
in conformance/vectors.json.

The organs (the observe, watch, confirm, and gate commands of the Python-core
organs) are likewise governed, closed auxiliary judgements. Perception (observe,
watch, confirm) emits per path exactly one of UNCHANGED, DRIFTED, NEW, or GONE.
Impedance (gate) emits per path and per summary exactly REVERTIBLE or
NOT_REVERTIBLE -- the re-derivable FACT that a clean operator revert path exists,
explicitly NOT a permission to act. None of these is, or maps to, TRUSTED or any
authority or permission word; in particular gate reports a fact, never grants
authority. organs is Python-core tooling governed by this spec plus
test_organs.py; it is not exercised by the cross-language conformance vectors
(section 12), so these auxiliary tokens are pinned here, not in
conformance/vectors.json.

## 3. Hashing and identity

- The identity of an artifact MUST be SHA-256 over its EXACT raw bytes. An
  implementation MUST NOT normalize, transcode, or canonicalize the bytes of a
  target before hashing -- line endings, encoding, and whitespace are part of the
  artifact. Detecting any byte change (including a CRLF rewrite) is a feature.
- An implementation MUST read target bytes through a raw byte channel (read
  binary), never a mediated or transformed view. With no raw channel it MUST
  report UNVERIFIABLE (section 9).
- The EMET source SHOULD be stored LF-pinned (gitattributes asterisk -text) so
  selftest re-derives the identical self-hash on every platform. This applies to
  the EMET source only, not to the artifacts it verifies.

## 4. Commands (normative contracts)

- anchor PATH... -- pin sha256 of raw bytes per path to the anchor store; exit 0
  when every path anchored. An unreadable or absent target MUST be reported
  UNVERIFIABLE with a stable machine reason code (section 9) and yields exit 2; it
  MUST NOT be silently skipped. anchor pins no required stdout token (section 13).
- verify PATH... -- per path emit MATCH, DRIFT, or UNVERIFIABLE versus the anchor.
- coherence SOURCE VIEW -- emit COHERENT or VIEW_DIFFERS_FROM_SOURCE.
- refuse FILE -- emit the marker count; write a copy named exactly FILE.refused
  in which every matched marker span (the non-overlapping leftmost scan of
  section 16) is replaced by the literal byte string [REFUSED-IN-BAND-AUTHORITY];
  MUST NOT obey any matched claim; MUST NOT modify the input.
- corroborate PATH -- hash the same file via disjoint read paths; emit
  CORROBORATED or QUARANTINE_READ_PATH_DIVERGENCE, or UNVERIFIABLE when no
  independent read path is available (section 9). The set of read paths is
  IMPLEMENTATION-DEFINED (for example a raw read plus a subprocess channel, plus
  a VCS channel where present), so an implementation with fewer channels MAY emit
  CORROBORATED where one with an extra channel emits QUARANTINE; this is expected,
  not a conformance violation.
- audit -- recompute the tamper-evident chain; emit INTACT or BROKEN.
- selftest -- emit the own-source SHA-256 of the implementation; assert no
  authority.

## 5. Exit codes (NORMATIVE)

The exit code is the verdict class expressed as an integer. It is data plus an
advisory signal, never an authority decision (Boundary 4): a non-zero code
reports a fact, it allows and denies nothing.

- exit 0 -- the checked property HELD: all MATCH, COHERENT, CORROBORATED, INTACT,
  no markers, or selftest ok.
- exit 1 -- a NEGATIVE FINDING was produced: DRIFT, VIEW_DIFFERS_FROM_SOURCE,
  QUARANTINE_READ_PATH_DIVERGENCE, or BROKEN.
- exit 2 -- the property COULD NOT BE CHECKED: UNVERIFIABLE, for any stable
  machine reason code (section 9). Inability is never trust, and never a
  difference.
- exit 3 -- one or more markers detected (refuse).
- exit 64 -- usage error.

Precedence, for a single invocation over multiple targets (for example verify of
several paths): a confirmed difference dominates an inability to check. The
process exits 1 if ANY target produced an exit-1 verdict, else 2 if ANY target
was UNVERIFIABLE, else 0. The marker class (exit 3, refuse) and the difference
class never co-occur in one command (refuse does not drift), so no precedence
between them is defined.

The Python-core companion tools extend the same semantic, governed by this spec
plus their own tests (not by the cross-language vectors of section 12): organs
perception (DRIFTED / NEW / GONE) and impedance (NOT_REVERTIBLE), and a monitor
baseline of CHANGED, are negative findings and exit 1; a monitor corpus that
cannot load is UNVERIFIABLE and exits 2. NOT_REVERTIBLE at exit 1 is the
re-derivable FACT that no clean revert path exists, never a denial of permission.

This split is the frozen 1.0 contract. Earlier drafts collapsed the exit-1 and
exit-2 classes into a single exit 2 and named the split a deferred "v1.1 target";
1.0 ships the split directly, because no prior tagged release ever established
the collapsed codes, so there is no installed base to migrate.

## 6. The six boundaries as testable invariants

1. Facts, not authority -- the verdict lattice is closed (section 2); no codepath
   may produce a verdict outside it, and none may emit TRUSTED.
2. Attests, never adjudicates a model safety decision -- EMET MUST operate only
   on artifact, byte, and provenance facts; no command may take a model safety or
   content decision as input or answer such a question.
3. Outside, never inside -- EMET MUST read targets by raw bytes and MUST NOT
   require being hosted by, or routed through, the system it audits.
4. Advisory by default -- a verdict is data plus an exit code; EMET MUST NOT
   allow, deny, block, or enforce of its own accord.
5. Re-derivable -- every verdict MUST be reproducible from the same spec_version
   plus corpus_version plus bytes (section 8); no secret, no held key.
6. Zero actuation on the audited target -- EMET MUST NOT write to, edit, sign,
   back up, or revert the AUDITED TARGET (the artifact under judgement). EMET
   DOES write to its own implementation-private stores -- the anchor store
   (anchors.json), the hash-chained log (membrane_log.jsonl / monitor_log.jsonl),
   the <file>.refused copy, and, on operator-authorized reanchor, the baseline
   manifest -- none of which is the target. "Zero actuation" therefore means zero
   actuation ON THE AUDITED TARGET of EMET's own accord; the single actuator over
   the world is the operator.

## 7. Audit chain

The tamper-evident log is JSONL. Each entry MUST be the object with keys kind,
fact, prev, and chain, where chain = SHA-256(prev + kind + canonical_json(fact)),
prev = the chain value of the prior entry, and the genesis prev = 64 zeros. Binding
kind means relabeling an entry's operation (for example anchor -> refuse) is itself
tamper. audit MUST recompute the chain; any edit to a historical kind or fact MUST
yield BROKEN. audit MUST ALSO check LINKAGE: each stored prev MUST equal the prior
entry's chain (genesis prev = 64 zeros), so a forged-but-internally-consistent
re-chained suffix is caught, not only a single-entry edit. (This
SHA-256(prev + kind + canonical_json(fact)) form supersedes the v0.x
SHA-256(prev + canonical_json(fact)); logs written under the older form read as
BROKEN, a documented backward-incompatible log-format change at 1.0.)

canonical_json(fact) is the JSON serialization with keys sorted, ", " and ": "
separators, and ensure_ascii escaping (the Python json.dumps(fact, sort_keys=True)
form), UTF-8-encoded before it is concatenated and hashed; pinning this byte form
is what lets an auditor re-derive a chain. A language's DEFAULT JSON encoder does
NOT produce this form -- Go's encoding/json HTML-escapes < > &, and neither Go nor
JavaScript's JSON.stringify matches the ", "/": " spacing or sorts keys -- so a
conforming implementation MUST hand-roll or post-process its serializer to the
canonical form (all four reference implementations do). The log
store is implementation-private (section 15): audit re-derives each chain from the
bytes actually stored, so it verifies any conforming log regardless of which
implementation wrote it. Two implementations are NOT required to record
byte-identical facts for the same operation (path normalization, for instance, may
differ), so cross-implementation chain equality is neither guaranteed nor required;
the guarantee is that audit re-derives whatever was stored.

## 8. Re-derivability (scoped)

A verdict is reproducible given: the same artifact bytes, the same spec_version,
and -- for marker-dependent output (refuse, marker census) -- the same
corpus_version. The marker denylist is a VERSIONED DATA ARTIFACT, not part of the
byte-hash core; two implementations agree on a marker verdict only when pinned to
the same corpus_version. Implementations MUST echo corpus_version (and SHOULD
echo corpus_sha256) with any marker-dependent output, so a disagreement is
attributable to corpus drift versus artifact drift. The byte-hash core (anchor,
verify, coherence, corroborate, audit) depends only on SHA-256 and exact bytes;
no corpus, no key, no clock.

The corpus is the plain-text artifact conformance/markers.corpus: a
`# corpus_version: N` header line, `#` comment lines, blank lines ignored, and one
literal marker per remaining line. corpus_sha256 is SHA-256 over the whole file.
Matching is literal ASCII-case-insensitive substring over raw bytes (no regex), so
two implementations re-derive identical marker counts from the same corpus. The
corpus is resolved from the EMET_CORPUS environment variable if set, otherwise a
default path relative to the implementation; a missing corpus is reported
UNVERIFIABLE with reason E_NO_CORPUS (section 9), never a silent empty denylist.

## 9. UNVERIFIABLE, never TRUSTED

If an implementation cannot obtain raw bytes, find an anchor, or complete a check,
it MUST report UNVERIFIABLE with a STABLE MACHINE REASON CODE (not prose), and
MUST NOT substitute a default, a cached value, or a trust assertion. Inability is
never trust.

The reason code is one of a fixed, machine-readable set; an implementation MUST NOT
substitute human prose for it. The governed codes are: E_NOT_FOUND (the path does
not exist), E_NO_RAW_CHANNEL (the path exists but no raw byte channel is available),
E_NO_ANCHOR (verify: no anchor for the path), E_NO_CORPUS (the marker corpus is
unresolvable), E_NO_CORPUS_VERSION (the corpus lacks its version header),
E_NO_SECOND_READ_PATH (corroborate: no independent read path), and E_LOG_CORRUPT
(a log line cannot be parsed). An implementation MAY add further E_* codes for
conditions not listed here, but MUST reuse these for the conditions they name.

## 10. Trusted Computing Base

The core (membrane, organs, monitor, corpus, verdict, report) MUST depend only on
the language runtime and standard library (reference: CPython plus hashlib, json,
os, subprocess) and MUST add no third-party runtime dependency. report renders the
human grammar and the --json envelope (section 13) and adds no dependency. Optional
adapters (signing, SARIF or in-toto emission, fuzzing) MAY pull additional
dependencies but MUST live in separate packages; the minimal-TCB guarantee applies
to the NAMED CORE only. Packaging (a console entry point, an sdist/wheel) is a
distribution convenience and MUST NOT add a runtime dependency to the core.

An out-of-core adapter MAY ship inside the distribution as a separate subpackage
(e.g. `emet.reporters`, the DeepEval reporter) so a plain install exposes it. Such
a subpackage is still NOT part of the named core: it MUST add no runtime dependency
to the core (any heavy dependency stays an optional extra, imported lazily), MUST
NOT be imported by any core module, and MUST be excluded from the section 14
artifact-of-record. Its presence therefore leaves the zero-dependency and
self-hash guarantees of the named core unchanged.

## 11. Honest limits (MUST be disclosed)

- Denylist incompleteness -- marker detection is a known-signature denylist, not
  a proof of cleanliness; absence of a marker is not absence of injection.
- Trust-root regress -- selftest proves the integrity of EMET only relative to an
  uncompromised substrate; a compromised substrate re-derives a compromised
  self-hash consistently. An EXTERNAL verifier MUST be the check of record for
  EMET itself; EMET MUST NOT be its own root of trust.
- Raw-byte-channel dependency -- EMET is only as faithful as its byte channel;
  where it cannot read raw bytes it reports UNVERIFIABLE.
- Byte and provenance, not semantic -- EMET judges bytes and provenance, never
  meaning; semantic safety is out of scope (see COVERAGE.json).
- Single-actuator assumption -- the single actuator over the audited target is
  the operator, and a coerced operator is out of model by design. "Zero
  actuation" (section 6, boundary 6) is scoped to the audited target: EMET MUST
  NOT write to, edit, sign, back up, or revert the artifact under judgement of
  its own accord, but EMET DOES write to its own implementation-private stores --
  the anchor store, the hash-chained log, the <file>.refused copy, and, on
  operator-authorized reanchor, the baseline manifest -- none of which is the
  target. Earlier blanket phrasings ("EMET performs no action"; "boundary 6 is
  the absence of a write call") were overstated and are corrected to this scoped
  form.
- Advisory unless owner-enforced -- enforcement is a downstream decision on
  owner-controlled infrastructure under an externally-rooted license.

## 12. Conformance

An implementation conforms at a given spec_version if and only if it satisfies
every MUST above and produces the expected verdict and exit code for every vector
in conformance/vectors.json at the stated corpus_version.

Four implementations -- the Python reference plus Rust, Node.js, and Go ports --
pass all vectors in CI. That agreement shows the spec is IMPLEMENTABLE from its
text (in four languages; the Node.js and Go ports were written against SPEC.md
and the vectors alone, and each surfaced spec under-determination that the vectors
then pinned -- see docs/spec-findings-from-js-impl.md and
docs/spec-findings-from-go-impl.md). But all four SHARE AN AUTHOR. A conformance
claim by same-author implementations demonstrates internal consistency and
implementability, NOT independent re-derivability. Re-derivability is DEMONSTRATED
only by an INDEPENDENT, DIFFERENT-AUTHOR implementation passing the same vectors.
That implementation is an open, named deliverable -- NOT yet satisfied -- and no
party should treat re-derivability as proven until it exists. This distinction is
load-bearing: 1.0.0 freezes the CONTRACT and ships production-grade reference
implementations; it does not, and must not, claim the external re-derivability
that only a different author can confer.


## 13. Output grammar (normative)

So an independent implementation can reproduce verdicts without reading the
reference code, the human-readable stdout tokens are pinned. For each command an
implementation MUST emit a line CONTAINING the stated token:

- verify: per path, a line containing exactly one of MATCH, DRIFT, or
  UNVERIFIABLE, followed by the path. verify is ANCHOR-RELATIVE: the anchor lookup
  PRECEDES the raw read, so a path with no anchor is UNVERIFIABLE reason=E_NO_ANCHOR
  even when the path is also absent (E_NO_ANCHOR dominates E_NOT_FOUND for verify).
- coherence: a line containing result=COHERENT or result=VIEW_DIFFERS_FROM_SOURCE,
  or result=UNVERIFIABLE with reason=source:<code> or reason=view:<code> naming the
  failing leg (source before view when both fail; section 9).
- refuse: a line containing in_band_authority_claims=N, where N is the
  non-negative integer marker count. An implementation MUST also emit a line
  containing corpus_version=N and SHOULD emit a line containing
  corpus_sha256=<hex> (section 8).
- corroborate: a line containing result=CORROBORATED or
  result=QUARANTINE_READ_PATH_DIVERGENCE, or result=UNVERIFIABLE with a reason
  code when there is no independent read path to corroborate against (section 9).
- audit: a line containing chain=INTACT or chain=BROKEN. An absent log is the
  genesis state (an empty chain is trivially intact) and MUST report chain=INTACT
  with log_entries=0, not a special-case string. A log line that cannot be parsed
  is a tamper event and MUST yield chain=BROKEN (exit 1), never UNVERIFIABLE: a
  corrupt line is a detected difference from a well-formed chain, not an inability
  to check.
- selftest: a line beginning with emet_self_sha256= followed by the
  artifact-of-record hash (section 14), and, through the 1.x deprecation window,
  also the legacy membrane_self_sha256= line (section 14).
- monitor report: per file, a line beginning with exactly one of MATCH, DRIFT,
  or MISSING, followed by the marker census and the file's basename; and a
  per-baseline summary line containing baseline=INTACT or baseline=CHANGED.
  These are the governed auxiliary tokens of section 2. The monitor is
  Python-core tooling governed by this spec plus test_monitor.py, not by the
  cross-language conformance vectors (section 12).
- organs observe (and confirm): per path, a line beginning with exactly one of
  UNCHANGED, DRIFTED, NEW, or GONE, followed by the path. organs gate: per path,
  a line beginning with exactly one of REVERTIBLE or NOT_REVERTIBLE, followed by
  the path, the pre-state hash, and the revert recipe; and a summary line
  containing gate=REVERTIBLE or gate=NOT_REVERTIBLE. REVERTIBLE is the
  re-derivable fact that a clean operator revert path exists, never a permission
  to act. These are the governed auxiliary tokens of section 2. organs is
  Python-core tooling governed by this spec plus test_organs.py, not by the
  cross-language conformance vectors (section 12).

### The --json envelope (normative)

An implementation MUST support a global --json flag, accepted before or after the
subcommand. In --json mode the implementation emits exactly ONE JSON object to
stdout and NO human-grammar lines, so a programmatic consumer parses stdout
directly. The object MUST be the canonical JSON of section 7 (keys sorted, ", "
and ": " separators, UTF-8, ensure_ascii). The exit code (section 5) is identical
with or without --json. A USAGE ERROR (exit 64) is exempt from the envelope: an
implementation MAY emit a minimal envelope or none and MAY write to stderr; only
the exit code 64 is the contract on that path.

Every envelope MUST carry command, emet_version, spec_version, and exit_code; and,
for a command that emits a lattice or auxiliary verdict, a verdict field whose
value is a governed closed-lattice token (section 2). selftest reports an identity,
not a judgement, and so carries self_sha256 and no verdict.  No field of any
envelope may contain TRUSTED, APPROVED, SAFE, or any authority word (Boundary 1).

These GOVERNED fields (command, verdict, exit_code, emet_version, spec_version, and
the per-command reason / corpus_version / corpus_sha256 / in_band_authority_claims)
are, for the same input at the same spec_version and corpus_version, byte-identical
across conforming implementations. self_sha256 is EXPLICITLY NOT in this set: it is
a per-implementation identity (section 14) and is never compared across
implementations (a multi-file source hash and a single-binary hash cannot be
equal). Other DETAIL fields are likewise permitted and MAY differ or be absent per
implementation, exactly where sections 4 and 15 already make behavior
implementation-defined (for example a verify want/got pair, or corroborate
per-channel hashes). The human token grammar above remains the default (no --json)
for human and CI use.

## 14. Artifact-of-record and selftest (normative)

selftest MUST emit the SHA-256 of the implementation artifact-of-record:

- for an INTERPRETED implementation, the artifact-of-record is the source file or
  files; where it is more than one file, the hash is over the sorted-by-path
  concatenation of the raw bytes of the core source files, and the implementation
  MUST document that file list (the Python reference: membrane, corpus, verdict,
  organs, monitor, report; each hashed as raw bytes, ordered by module name);
- for a COMPILED implementation, it is the compiled binary (so the self-hash is
  build-dependent, not source-reproducible across rebuilds; this is expected).

The canonical output token is emet_self_sha256=. Through the 1.x deprecation
window an implementation MUST ALSO emit the legacy membrane_self_sha256= line
carrying the same hex value, so parsers written against the old token keep
working; the legacy alias is removed at 2.0. In the --json envelope (section 13)
the identity is carried under the key self_sha256. selftest is per-implementation
self-identity and is never compared across implementations, so a multi-file
source hash and a single-binary hash coexist correctly.

## 15. Anchor store (normative)

The anchor store (anchors.json) is IMPLEMENTATION-PRIVATE: its on-disk format is
not standardized, and an anchor written by one implementation is not required to
be readable by another. Therefore the anchor step and the verify step of a single
conformance run MUST be executed by the SAME implementation. A cross-
implementation anchor-exchange format is deferred to a future version.

## 16. Marker corpus (normative reference)

The marker set used by refuse and the monitor census is the governed, versioned
denylist conformance/markers.corpus (sections 8 and 11): a plain-text file with a
`# corpus_version: N` header, `#` comment lines, and one literal marker per line,
matched as literal ASCII-case-insensitive substrings over raw bytes.

The marker COUNT is pinned: an implementation MUST count by a NON-OVERLAPPING
LEFTMOST scan in corpus order -- scanning the target's raw bytes left to right, at
each position testing the markers in corpus order, taking the first that matches
there, emitting one count and advancing past the matched span; on no match it
advances one byte. A repeated marker therefore counts ONCE PER OCCURRENCE, and
overlapping candidates resolve to the first match in corpus order. (This scan was
previously left implicit; an independent reimplementation surfaced that "count"
was unpinned -- vectors refuse-three-markers and
refuse-repeated-marker-occurrence-count together pin it.)

The corpus is not enumerated here. Conformance pins specific counts for specific inputs at a stated
corpus_version (see conformance/vectors.json). Absence of a marker is never absence
of injection (section 11).

## 17. Portable witness receipt (normative)

The anchor store (section 15) is implementation-private, so a raw anchor/verify
verdict cannot leave the machine that produced it. The PORTABLE WITNESS RECEIPT is
the standardized, cross-implementable form that CAN travel: a self-contained JSON
object encoding one or more EMET verdicts plus the re-derivation method, such that
a DIFFERENT party re-derives and checks it on their own machine with ZERO shared
state, zero trust in the producer, and zero network access.

A receipt asserts a FACT of re-derivation, never authority. `RECEIPT_VALID` means
the receipt's own content address is intact (and, if subject re-derivation was
requested, the recorded bytes still hash to the recorded digests) at check time.
It is NOT trust, approval, or a release decision, and maps to no authority word
(Boundary 1). A receipt is a point-in-time snapshot: when a subject's bytes
change, re-derivation diverges.

### 17.1 Receipt schema (`emet-witness-receipt/v1`)

A receipt is a JSON object with these fields:

- `format` (string): the literal `"emet-witness-receipt/v1"`.
- `receipt_id` (hex string): the content address (section 17.2).
- `issued_at` (string): ISO-8601 UTC timestamp `YYYY-MM-DDThh:mm:ssZ` of issuance.
- `witness` (object): `implementation`, `spec_version`, and `self_sha256` (the
  producing implementation's artifact-of-record hash, section 14).
- `subject` (array): each entry `{ "path": <string>, "sha256": <hex string> }`
  pinning a subject's recorded digest. A subject with no derivable digest carries
  `"sha256": null` and a stable `reason` code rather than being omitted.
- `verdict_record` (array): each entry `{ "subject_index": <int>, "command":
  <string>, "verdict": <closed-lattice token> }`, optionally with `want`/`got`.
  The verdict MUST be a member of the closed lattice (section 2); a receipt never
  carries an authority token.
- `corpus_version` (int|null) and `corpus_sha256` (hex|null): pinned when the
  source command referenced the marker corpus (section 16), else null.
- `signature` (hex string|null) and `signature_algorithm` (string): the optional
  HMAC signature (section 17.4) and its algorithm label.
- `re_derivation_method` (string): `"hash"` for the v1 content-addressing method.
- `notes` (string): the facts-only disclaimer.

### 17.2 Content address (re-derivation guarantee)

`receipt_id` is `sha256` over the canonical JSON byte form (section 7) of the
receipt with the `receipt_id`, `signature`, and `witness` fields EXCLUDED. Because
the byte form is pinned, the address is byte-identical across conforming
implementations. The `witness` block is excluded because it is PRODUCER IDENTITY
(the implementation name and that implementation's own artifact-of-record hash,
section 14), which is intrinsically per-implementation; including it in the
address would make the same subject/verdict/spec/issued_at hash to a different id
in one implementation than another, defeating the guarantee below. The witness
block still travels in the receipt as descriptive metadata (a verifier may read
it to learn who produced the receipt), it just does not govern the address.

RE-DERIVATION GUARANTEE: the SAME subject bytes, the SAME `spec_version`, the
SAME `corpus_version`, and the SAME `issued_at` yield a byte-identical
`receipt_id` ACROSS conforming implementations. Tampering ANY addressed field
re-hashes to a different id, so a doctored receipt is detectable with no shared
secret. `issued_at` is part of the addressed body, so two receipts issued at
different instants legitimately differ.

### 17.3 Offline verifier contract (`emet check`)

`emet check <receipt.json> [--recompute-from-paths]` is STATELESS: no anchor
store, no audit log, no network, no shared key. It:

1. Loads the receipt; a malformed file or wrong `format` is `RECEIPT_UNVERIFIABLE`.
2. Re-derives `receipt_id` from the rest of the receipt (section 17.2) and
   compares. A mismatch is `RECEIPT_TAMPERED`.
3. If the receipt is signed and a key is available, verifies the signature; a
   failure is `RECEIPT_TAMPERED`, a signed receipt with no available key is
   `RECEIPT_UNVERIFIABLE`.
4. If `--recompute-from-paths` is given, re-hashes each subject's live bytes and
   compares against the recorded digest: a divergence is `RECEIPT_TAMPERED`, an
   unreadable subject is `RECEIPT_UNVERIFIABLE`.

The result is a member of the closed RECEIPT lattice `{ RECEIPT_VALID,
RECEIPT_TAMPERED, RECEIPT_UNVERIFIABLE }`. TAMPERED dominates UNVERIFIABLE (a
confirmed difference outranks an inability to check), mirroring section 5. Exit
codes: `RECEIPT_VALID` -> 0, `RECEIPT_TAMPERED` -> 1, `RECEIPT_UNVERIFIABLE` -> 2,
usage -> 64. A non-zero exit is data, never an authority decision (Boundary 4).

### 17.4 Optional signature

`EMET_RECEIPT_SIGNING_KEY`, when set, adds an HMAC-SHA256 `signature` over the
SAME canonical body the content address covers. This is OUT-OF-SPEC and optional:
it strengthens integrity only when producer and verifier already share a key
channel. With no key the signature is null and content-addressing stands alone; a
conforming verifier without the key still checks the content address.

### 17.5 Boundary between portable encoding and operational state

The receipt format and content-addressing scheme are named core (section 10):
normative and cross-language-implementable. The anchor store (section 15), the
audit log (section 7), and the convenience adapter (`adapters/
witness_receipt_portable.py`) are NOT part of the receipt contract. A receipt
carries the portable verdict encoding; it never carries or requires operational
state.

## 18. Stripped-credential rebind (EXPERIMENTAL)

STATUS: EXPERIMENTAL. This section describes a capability shipped in the Python
reference implementation with conformance vectors tagged `capability: "rebind"`.
It is NOT yet a required conformance capability, and the cross-language port
contract is SPECced separately (`docs/REBIND-SPEC.md`) as follow-on. Treat the
`emet-rebind-manifest/v1` shape as provisional until cross-language parity lands.

THE FAILURE MODE. Embedded-credential provenance schemes (the C2PA class) bind
provenance to an artifact IN BAND: the manifest, signature, or certificate travel
INSIDE the file. Re-encoding, screenshotting, copying the bytes out of a
container, or stripping the metadata block removes the credential, and the
artifact is orphaned: naked bytes an embedded-credential verifier cannot place.

THE ANSWER. EMET's anchor is the sha256 of the RAW BYTES (section 3), held out of
band, never inside the artifact. A stripped artifact is therefore not orphaned to
EMET: re-derive the content hash of the naked bytes and look it up in a known
anchor. This is content-addressed rebinding. It does not recover the stripped
credential; it makes recovery unnecessary, because the binding was to the content.

### 18.1 The rebind manifest (`emet-rebind-manifest/v1`)

The out-of-band anchor a stripped artifact rebinds against is a portable,
content-addressed JSON object holding the anchors a verifier knows. Fields:

- `format` (string): the literal `"emet-rebind-manifest/v1"`.
- `manifest_id` (hex string): the content address (section 18.2).
- `issued_at` (string|null): ISO-8601 UTC timestamp of issuance.
- `records` (array): each entry `{ "digest": <hex sha256>, "identity": <string> }`
  pinning one known anchor: the content digest of an artifact's raw bytes and the
  identity that anchor stands for. A digest maps to at most one identity; an
  ambiguous anchor set is a build error.
- `notes` (string): the facts-only disclaimer.

The rebind manifest is DISTINCT from the implementation-private anchor store
(section 15): the store cannot travel, the manifest is the standardized, portable
"anchors I know" a second party can hold or fetch over a trusted channel.

### 18.2 Manifest content address

`manifest_id` is `sha256` over the canonical JSON byte form (section 7) of the
manifest with `manifest_id` EXCLUDED. Tampering any record re-hashes to a
different id, so a doctored anchor set is detectable before any rebind.

### 18.3 Rebind verdict contract (`emet rebind`)

`emet rebind <naked> --manifest <manifest.json> [--claim <identity>]` re-derives
`sha256` of the naked bytes and emits a member of the closed PRIMARY lattice
(section 2):

  MATCH        the derived digest is recorded in the manifest. The artifact
               rebinds to that anchor's identity. If a `--claim` was given it must
               agree with the anchored identity, else the result is DRIFT.
  DRIFT        `--claim` names an identity the manifest anchors, but the naked
               bytes hash to a different digest than that identity's anchor(s) - a
               confirmed substitution (right name, wrong bytes); OR the bytes match
               a known anchor but under a DIFFERENT identity than claimed.
  UNVERIFIABLE no anchor records the bytes and no claim resolves to a mismatch (the
               honest default, reason `E_NO_ANCHOR`); OR the manifest's own
               `manifest_id` does not re-derive (`E_MANIFEST_TAMPERED`) or is
               absent (`E_MANIFEST_UNVERIFIABLE`); OR the naked bytes are unreadable
               (the section 9 raw-channel reason codes).

MATCH is a FACT of re-derivation, never trust, approval, or a release decision,
and maps to no authority word (Boundary 1). DRIFT (a confirmed difference)
dominates UNVERIFIABLE, mirroring section 5. Exit codes follow section 5: MATCH
-> 0, DRIFT -> 1, UNVERIFIABLE -> 2, usage -> 64. A rebind verdict may be sealed
into a portable witness receipt (section 17) so the FACT travels off-machine where
the stripped credential could not.
