# Spec findings from the Go (fourth) clean-room implementation

This records every place SPEC.md (and conformance/vectors.json) under-determined
behavior while building `impl/go/emet.go` clean-room, and how each gap was
resolved. This is the most valuable output of a clean-room port: it surfaces
where an independent reader had to make a choice the spec did not force.

The Go implementation passes CONFORMANCE 27/27 (Go 1.23.4, windows/amd64).

## A note on version skew (spec vs vectors)

The committed `SPEC.md` header says `Spec version: 0.2.0-draft` and
`conformance/vectors.json` carries `"spec_version": "0.2.0-draft"` and
`"tool": "membrane.py"`. But the SPEC body (sections 5, 13, 14) describes the
FROZEN 1.0 contract: the exit-1/exit-2 split "is the frozen 1.0 contract"
(s.5), the `emet_self_sha256=` canonical token with a "1.x deprecation window"
legacy alias (s.14), and the `--json` envelope carrying `emet_version` /
`spec_version` (s.13). The task brief pins the envelope's governed values to
`"emet_version": "1.0.0"` and `"spec_version": "1.0.0"`.

**Resolution.** The envelope emits `emet_version: "1.0.0"` and
`spec_version: "1.0.0"` as instructed. The conformance vectors never assert the
value of these two fields (they only assert `"verdict"`, `"exit_code"`,
`"in_band_authority_claims"`, and `"self_sha256": "` substrings), so the version
choice does not affect the 27/27 result. **Finding:** the spec-version string is
governed and byte-compared across implementations (s.13), yet the vectors do
NOT pin it, and the SPEC header (`0.2.0-draft`) disagrees with the frozen-1.0
body. A future vector SHOULD assert `"spec_version": "1.0.0"` in an envelope so
the governed value is actually enforced, and the SPEC header should be bumped to
match its own body.

**Resolved at 1.0.0.** The SPEC header and `vectors.json` `spec_version` are now
`1.0.0`, and the `envelope-spec-version` vector asserts `"spec_version": "1.0.0"`
in a `--json` envelope. The `verify-no-anchor-reason-code` and
`refuse-missing-reason-code` vectors now enforce the s.9 reason enum, and
`verify-multipath-precedence-json` pins the multi-path dominant verdict (findings
6 and 8). The default-encoder warning (finding 2) is now in SPEC s.7.

## 1. `--json` envelope SHAPE is per-command, only substrings are pinned

SPEC s.13 lists the GOVERNED keys (command, verdict, exit_code, emet_version,
spec_version, plus per-command reason / corpus_version / corpus_sha256 /
self_sha256 / in_band_authority_claims) and says DETAIL fields "MAY differ or be
absent per implementation." The vectors assert only substrings
(`"verdict": "DRIFT"`, `"exit_code": 1`, `"in_band_authority_claims": 3`,
`"self_sha256": "`). So the exact object shape (which detail fields exist, e.g.
`results`, `want`/`got`, `channels`, `hits`, `broken_at`) is under-determined.

**Resolution.** Followed the shapes named in the task brief (results array with
want/got or reason; coherence subject/source/view; refuse subject +
in_band_authority_claims + corpus_version + corpus_sha256 + hits + clean_copy;
corroborate channels + read_paths_agree + git_read_agrees_with_open; audit
verdict + log_entries + broken_at; selftest self_sha256 + notes, no verdict).
The canonical JSON serializer was byte-verified against
`python json.dumps(obj, sort_keys=True)` for every command. **Finding:** because
detail fields are explicitly implementation-defined, cross-impl envelope
equality holds ONLY on the governed subset; the vectors correctly test only that
subset via substring, but this means two conforming impls can emit structurally
different envelopes and both pass. That is by design (s.13) but worth stating.

## 2. Canonical JSON: Python does NOT escape `<` `>` `&`; Go's default does

SPEC s.7/s.13 define canonical JSON as "the Python json.dumps(fact,
sort_keys=True) form" with ensure_ascii. A naive Go implementation using
`encoding/json.Marshal` FAILS this: Go's encoder HTML-escapes `<`, `>`, and `&`
to `<` etc. by default, and does not sort map keys with the Python
separator spacing. The spec names the Python form but does not warn about this
divergence.

**Resolution.** Hand-rolled the serializer (`writeCanonString`) to match Python
exactly: sort keys, `", "` / `": "` separators, escape only
`" \ \n \r \t \b \f` and control chars `< 0x20`, `\uXXXX` for `>= 0x80` (with
surrogate pairs for astral code points), and leave `< > &` and `0x7f`
untouched. Byte-verified against Python. **Finding:** the spec should explicitly
warn that a language's default JSON encoder (Go, and JS `JSON.stringify` differs
too) will NOT produce the canonical form and must be hand-rolled or
post-processed. The Go impl proves the canonical form is reproducible, but only
with care.

## 3. Anchor store on-disk format is unspecified (and correctly so)

SPEC s.15 declares `anchors.json` implementation-private and NOT standardized;
anchor and verify of one run must use the same impl. The name is `anchors.json`
but the spec pins no format.

**Resolution.** Used a JSONL of canonical `{"path": ..., "sha256": ...}` lines
(last write per path wins), written with the same canonical serializer. This is
internally consistent and never crosses an implementation boundary. **Finding:**
no gap -- the spec deliberately leaves this open. Noting it so a reader knows the
`.json` extension does not imply a single JSON document.

## 4. The audit-log fact SHAPE for anchor/verify is unspecified

The `anchor-then-audit` vector requires that `anchor` writes a hash-chained log
entry that `audit` then reads as INTACT, but the spec does not pin what `fact`
an anchor entry records. The seeded `audit-intact` vector shows verify facts
shaped `{"path": ..., "result": "MATCH"}`, but anchor facts are never shown.

**Resolution.** Anchor writes `{"path": p, "sha256": h}`; verify writes
`{"path": p, "result": "MATCH"|"DRIFT"}` (matching the seeded vector's shape);
coherence/corroborate/refuse also append facts. Because SPEC s.7 guarantees only
that "audit re-derives whatever was stored" and s.15 makes the store private,
the exact fact shape is free. The chain formula
`SHA-256(prev + kind + canonical_json(fact))` was verified against the seeded
`62831bbd...` chain before writing any code. **Finding:** no conformance gap, but
the audit-chain re-derivation across implementations (s.7 says audit "verifies
any conforming log regardless of which implementation wrote it") is only true
because the audit re-parses the stored fact and re-serializes it canonically --
which requires a general-enough JSON reader. A log written with non-canonical
spacing by another impl would still audit correctly here because the Go reader
re-parses the fact object and re-serializes it canonically rather than
byte-comparing the stored substring. The spec could state this normalization
requirement explicitly.

## 5. `corroborate` read-path set is implementation-defined; genuinely disjoint?

SPEC s.4 says the read paths are implementation-defined (raw read + subprocess +
optional VCS) and that fewer channels MAY yield CORROBORATED where more channels
yield QUARANTINE. The one corroborate vector (`corroborate-read-paths-agree`)
only exercises the agree path.

**Resolution.** Channel 1 = in-process `os.ReadFile`; channel 2 = a child process
of this same binary re-reading via the hidden `__rawhash` subcommand. Two
processes reading the same bytes via the same OS call are not strongly
independent (both trust the same filesystem), but they ARE two distinct read
paths as the spec permits. **Finding:** the spec's notion of "disjoint read
path" is weak -- a subprocess of the same binary using the same syscall counts.
This is acceptable per s.4's implementation-defined latitude, but the security
value of corroboration is limited when both channels share a substrate (s.11's
trust-root regress applies here too). A stronger impl would add a git-blob
channel (`crypto/sha1` over `blob <len>\0<bytes>`); the task marked that
optional and this impl omits it. No vector exercises QUARANTINE, so the divergence
path is untested by conformance.

## 6. `E_NOT_FOUND` vs `E_NO_RAW_CHANNEL`: which for a missing file?

SPEC s.9 defines `E_NOT_FOUND` = "the path does not exist" and
`E_NO_RAW_CHANNEL` = "the path exists but no raw byte channel is available." The
UNVERIFIABLE vectors (missing source, missing refuse file, unreadable anchor
target) assert only the substring `UNVERIFIABLE` and exit 2 -- they do NOT pin
which reason code.

**Resolution.** `readRaw` returns `E_NOT_FOUND` when `os.Stat` reports
not-exist, `E_NO_RAW_CHANNEL` when the path exists but is a directory or is
unreadable. This matches the s.9 definitions precisely. **Finding:** the reason
code is governed and byte-compared across implementations per s.13, yet no vector
asserts a SPECIFIC code (the vectors only check the `UNVERIFIABLE` substring).
So an impl that returned `E_NO_RAW_CHANNEL` for a truly-absent file would still
pass conformance while violating the s.9 definition. A future vector SHOULD
assert `reason=E_NOT_FOUND` for an absent target to actually enforce the enum.
(The task brief separately pins `verify` no-anchor to `reason=E_NO_ANCHOR`,
which this impl emits and which IS distinguishable in output, but again is not
asserted by a vector.)

## 7. Human-grammar detail beyond the pinned token is unspecified

SPEC s.13 pins only that each command's stdout must CONTAIN a stated token (e.g.
`result=COHERENT`, `in_band_authority_claims=N`, `chain=INTACT`). The rest of the
human line is free.

**Resolution.** Emitted useful but unpinned extras (e.g. `verify` prints
`MATCH <path>`; `refuse` also prints `corpus_sha256=` and `clean_copy=`;
`coherence` prints the two hashes; `audit` prints `log_entries=N`). The
`UNVERIFIABLE` lines carry `reason=E_*` even in human mode, so the machine reason
code is never hidden. **Finding:** no gap; noting that the human grammar's
freedom means CI parsers must key off the pinned token substring only.

## 8. `verify` multi-path precedence in `--json`: what is the top-level verdict?

SPEC s.5 pins the EXIT-CODE precedence over multiple paths (1 if any DRIFT, else
2 if any UNVERIFIABLE, else 0). The task brief pins the top-level JSON `verdict`
to the dominant `DRIFT > UNVERIFIABLE > MATCH`. SPEC s.13 alone does not state
how the top-level verdict is chosen when the per-path results disagree.

**Resolution.** Top-level `verdict` = dominant by `DRIFT > UNVERIFIABLE > MATCH`,
mirroring the exit precedence. No multi-path `--json` vector exists to enforce
this. **Finding:** the multi-path top-level `verdict` selection is spec-silent
and only fixed by the task brief; a vector with two paths (one DRIFT, one
UNVERIFIABLE) in `--json` mode would pin it.

## 9. selftest `notes` content is unspecified

SPEC s.13/s.14 say the selftest envelope carries `self_sha256` and no verdict;
the task brief shows `"notes":[...]`. The content of `notes` is not pinned.

**Resolution.** Emitted two honest-limit notes (trust-root regress; build-
dependent binary hash). `notes` is a detail field and is not asserted by any
vector. **Finding:** no gap; `notes` is purely advisory detail.

## Summary of recommended spec/vector tightening

1. Bump the SPEC header from `0.2.0-draft` to `1.0.0` to match its own frozen-1.0
   body, and update `vectors.json` `spec_version` accordingly.
2. Add vectors that assert the SPECIFIC governed reason code
   (`reason=E_NOT_FOUND` for an absent target, `reason=E_NO_ANCHOR` for verify
   without an anchor) -- currently the machine enum (s.9) is defined but not
   enforced by conformance.
3. Add an envelope vector asserting `"spec_version": "1.0.0"` and
   `"emet_version": "1.0.0"` so the governed version strings (s.13) are actually
   byte-compared.
4. Add a multi-path `verify --json` vector (one DRIFT + one UNVERIFIABLE) to pin
   the top-level dominant verdict.
5. Warn in s.7/s.13 that a language's default JSON encoder (Go `encoding/json`,
   JS `JSON.stringify`) does NOT produce the canonical form (HTML-escaping,
   key order, separators) and must be hand-rolled or post-processed.
6. Add a QUARANTINE_READ_PATH_DIVERGENCE vector so the corroborate divergence
   path is exercised by conformance, not just the agree path.
