# Marker Corpus Reconciliation -- Design

- Date: 2026-06-06
- Status: APPROVED (brainstorming) -- pending spec self-review + user review, then implementation plan
- Scope: EMET `refuse` + `monitor` marker census; the byte-hash core is untouched
- Related: SPEC.md sections 8, 10, 11, 13, 16; conformance/vectors.json

## Problem

EMET's marker denylist is defined three times, with two different match semantics:

- `membrane.py` `AUTHORITY` and `monitor.py` `MARKERS`: byte regexes with optional
  separators, e.g. `GROUND[_ ]?TRUTH[_ ]?CANONICAL`, `authority[_-]?pill`.
- `impl/rust/emet.rs` `MARKERS`: literal lowercase strings, e.g. `ground_truth_canonical`.

The two implementations therefore DISAGREE on any marker input not in exact
underscore form. Confirmed: on `GROUND TRUTH CANONICAL ... authority-pill ...
HIGHEST SCRUTINY` the Python core counts 3, the Rust core counts 0. The conformance
vectors only use exact-underscore inputs, so the divergence is invisible to CI. This
undercuts the project's central claim -- re-derivability across implementations -- for
the marker-dependent path.

SPEC sections 8 and 16 already DESIGN for the fix: the marker denylist is a
"versioned data artifact" and a "separate governed artifact", and implementations
MUST echo `corpus_version` (SHOULD echo `corpus_sha256`) with marker output. None of
that is implemented today: the list is hardcoded inline in three places,
`corpus_version` is the bare string "0", there is no artifact, and nothing is echoed.

## Findings resolved

- marker-divergence / rust-marker-literal-vs-regex-divergence (the GT2 divergence)
- marker-list-duplicated (triplicated inline list)
- corpus-version-zero-no-artifact
- corpus-version-not-echoed-unenforced (SPEC section 8 MUST)

## Decisions

1. MATCH MODEL: literal-enumerated. The corpus is a flat list of literal
   byte-strings; matching is ASCII-case-insensitive substring via a non-overlapping
   left-to-right byte scan -- the exact algorithm now in emet.rs. No regex engine in
   either language (regex is the primary source of cross-language divergence).

2. FORMAT: plain UTF-8 text, one literal marker per line. A `# corpus_version: N`
   header line sets the version. Lines beginning with `#` are metadata/comments.
   Blank lines are ignored. Every other line, its exact bytes minus the trailing LF,
   is one marker. `corpus_sha256` = sha256 over the whole file's raw bytes.

3. LOADING: default path resolved relative to the tool; `EMET_CORPUS` env var
   overrides it (at most two sources -- never a guess-list). refuse and monitor census
   ALWAYS echo `corpus_version=` and `corpus_sha256=`. Missing/unreadable corpus is
   UNVERIFIABLE with reason code `E_NO_CORPUS`, never a silent empty denylist.

4. CORPUS CONTENTS (corpus_version 1): uniform separator variants per multi-token
   marker -- all-underscore, all-space, all-none, plus the hyphen form for
   `authority-pill`. Single-token markers stay literal.

5. SHARED LOADER: a new stdlib-only `corpus.py` core module (load / match / redact),
   imported by both membrane.py and monitor.py. emet.rs implements the same logic
   inline. SPEC section 10's named core is updated to include corpus.py.

## The corpus artifact

Path: `conformance/markers.corpus` (LF-pinned by the existing `.gitattributes * -text`).

Example (corpus_version 1):

    # corpus_version: 1
    # EMET marker denylist (known-signature; not a proof of completeness, SPEC s.11)
    ground_truth_canonical
    ground truth canonical
    groundtruthcanonical
    highest_scrutiny
    highest scrutiny
    highestscrutiny
    [scope context]
    authority_pill
    authority-pill
    authoritypill
    canonical_recipients
    canonical recipients
    canonicalrecipients
    frame_injected
    consulting register
    semantic_modulat
    compound_rewrites
    density_restructured

Notes:
- The single-token entries (frame_injected, semantic_modulat, compound_rewrites,
  density_restructured, consulting register) are literal; consulting register keeps
  its space form as today.
- [scope context] is literal including the brackets.

## Matching algorithm (identical in both languages)

    matches_marker_at(hay, i, m):  # m is a marker's bytes
        if i + len(m) > len(hay): return False
        for j in 0..len(m):
            if ascii_lower(hay[i+j]) != m[j]: return False   # m stored lowercase
        return True

    scan(hay, markers):            # non-overlapping, leftmost, corpus order
        i = 0; count = 0; out = []
        while i < len(hay):
            hit = first marker in corpus order with matches_marker_at(hay, i, m)
            if hit: count += 1; emit replacement to out; i += len(hit)
            else:   out.append(hay[i]); i += 1
        return count, bytes(out)

- Offsets reported by refuse are byte offsets into the target's raw bytes.
- Redaction replaces each matched marker with [REFUSED-IN-BAND-AUTHORITY] byte-wise;
  non-ASCII bytes are preserved (this is the fix for the Rust to_lowercase offset
  panic, generalized to both impls).
- Corpus markers are normalized to ASCII-lowercase at load so the matcher compares
  against lowercase bytes.

## Command behavior

### refuse <file>
1. Load corpus (default path, or EMET_CORPUS). Missing/unreadable ->
   UNVERIFIABLE <file> reason=E_NO_CORPUS, record, exit 2.
2. Emit corpus_version=N and corpus_sha256=<hex>.
3. Emit in_band_authority_claims=<count>, then up to 60 REFUSED <repr> offset=<n>
   lines, then clean_copy=<file>.refused ...
4. Write <file>.refused with markers redacted. Never modify the input.
5. Exit 0 if count 0 else 3. UNVERIFIABLE on missing input file (reason E_NOT_FOUND)
   or missing corpus (reason E_NO_CORPUS).

### monitor report <manifest>
- Load the same corpus; echo corpus_version= and corpus_sha256= in the header.
- Per-file markers= counts use the shared scan.
- Missing/unreadable corpus -> corpus=UNVERIFIABLE reason=E_NO_CORPUS, exit 2 (a
  complete accountability report requires the pinned corpus). Hash-drift logic
  itself is unchanged and corpus-independent.

## Conformance and spec

- run.py: set EMET_CORPUS to the repo conformance/markers.corpus for BOTH
  implementations so conformance is deterministic regardless of cwd or binary
  location. Add optional per-vector env support.
- Vectors: existing refuse-three-markers / refuse-clean-zero still pass (their
  in_band_authority_claims substrings are unaffected by the added corpus lines).
  ADD:
  - refuse-space-separated: input "GROUND TRUTH CANONICAL\n" -> count 1, exit 3
    (previously Python 1 / Rust 0 -- now identical).
  - refuse-hyphen-pill: input "authority-pill\n" -> count 1, exit 3.
  - refuse-no-corpus: EMET_CORPUS pointed at a nonexistent path -> substring
    UNVERIFIABLE, exit 2.
- vectors.json: bump corpus_version "0" -> 1; add corpus_sha256.
- SPEC: sections 8 and 16 describe the real artifact (path, plain-text format,
  version header, sha pinning, literal ASCII-CI matching); section 13 adds the
  corpus_version= and corpus_sha256= lines to the refuse grammar; section 10 adds
  corpus.py to the named core.

## Testing (TDD)

New tests (test_corpus.py and/or extend test_membrane.py), each watched fail first:
- refuse counts a space-separated marker (the divergence input) as 1.
- refuse echoes corpus_version and a 64-hex corpus_sha256.
- refuse with EMET_CORPUS=<nonexistent> -> UNVERIFIABLE reason=E_NO_CORPUS exit 2.
- corpus loader: parses the version header, ignores comments and blank lines,
  collects the right marker set, computes the file sha.
- redaction replaces markers byte-wise and preserves a non-ASCII byte sequence.
- monitor report echoes corpus_version/sha; missing corpus -> UNVERIFIABLE exit 2.
- Conformance: reference passes all vectors locally at corpus_version 1; Rust
  verified by CI (no rustc in the authoring environment).

## Behavior changes (accepted, to be documented in SPEC/README)

1. refuse/monitor output gains corpus_version= and corpus_sha256= lines (additive).
2. Matching narrows from regex optional-separator-anywhere to enumerated spellings.
   Mixed forms not enumerated (e.g. "ground_truth canonical") no longer match unless
   added to the corpus. Deliberate trade for cross-impl re-derivability; pinned at
   corpus_version 1. The threat model already states the denylist is known-signature
   and non-complete.
3. Missing corpus -> UNVERIFIABLE for refuse/monitor. Cost of externalizing the
   corpus; mitigated by shipping it in-repo at the default path.

## Out of scope

- Rust audit command + chain recording (separate P0 item).
- The byte-hash core (anchor/verify/coherence/corroborate/audit) -- no corpus
  dependency (SPEC section 8), untouched.
- New injection signatures beyond reconciling the current set; corpus growth is
  governed separately (CONTRIBUTING.md).