# Spec findings from the Node.js clean-room implementation

- Date: 2026-06-08
- Source: `impl/js/emet.js`, written against `SPEC.md` + `conformance/vectors.json` +
  `conformance/markers.corpus` ALONE (no reference code read at authoring time, SPEC §12).
- Purpose: per the README -- "where your implementation and the spec disagree, the spec is
  wrong … those divergences are the point." This is that punch-list. The spec is a draft
  (v0.2.0-draft); these are clarifications to make before it freezes.

Building the third implementation from the spec text alone is a differential oracle: every
place the implementer had to *guess* is a place the spec under-determines behavior. Most
guesses happened to match the reference (because the vectors constrain them); one did not,
and that one was a genuine cross-implementation divergence the existing vectors could not
catch. It is fixed; the rest are recommendations.

## F1 -- Marker count was unpinned (RESOLVED -- real divergence)

**Severity: high (re-derivability).** SPEC §8/§16 called `in_band_authority_claims=N` a
"marker count" with literal ASCII-case-insensitive substring matching, but never said
whether `N` is the number of **distinct** corpus entries that match, or the number of
**occurrences**. The four refuse vectors (counts 3/0/1/1) do **not** discriminate: no marker
repeats and none is a substring of another. The clean-room reader chose *distinct*; the
reference (`corpus.py`'s `scan()`, a non-overlapping leftmost scan) counts *occurrences*. They
diverge on a repeated marker -- e.g. `authority_pill authority_pill` is **2** (reference) vs
**1** (distinct). An invisible re-derivability gap.

**Resolution (done):**
- SPEC §16 now pins the count to a **non-overlapping leftmost scan in corpus order** (matches
  the Python reference and the Rust port).
- New conformance vector `refuse-repeated-marker-occurrence-count` (`authority_pill
  authority_pill` → `in_band_authority_claims=2`, exit 3) locks it. 18 → **19** vectors.
- `impl/js/emet.js` was aligned to the pinned scan; all three implementations now agree.

## F2 -- §13 grammar is stricter than the vectors (spec is correct; vectors are loose)

`coherence`/`corroborate` MUST emit `result=<TOKEN>` per §13, but the vectors' `expect_substr`
are the **bare** tokens (`COHERENT`, `CORROBORATED`, …). A bare-token emitter would pass every
vector yet violate the normative grammar. No spec change needed (the impl emits `result=`),
but **the vectors under-test the grammar**. Recommend either tightening the affected
`expect_substr` to include `result=`, or a note that the bare token is an intentional
substring check.

## F3 -- `.refused` copy is under-specified (impl-defined; pin before freeze)

§4 mandates a `.refused` copy "with markers replaced" but pins no replacement string, no
output-filename convention, and no overlapping-match rule, and **no vector inspects
`.refused` contents**. The reference uses `[REFUSED-IN-BAND-AUTHORITY]`; the Node.js impl uses
`[REFUSED]` -- both conform. The only hard constraint the vectors + boundary 6 enforce is that
the **input is never modified**. Recommend pinning the replacement token and the `<file>.refused`
filename in §4 (or explicitly declaring them implementation-defined) before freeze.

## F4 -- Audit prev-linkage is not stated explicitly (both impls do it)

§7 defines `prev` = the prior entry's chain and genesis `prev` = 64 zeros, and says editing a
historical `kind`/`fact` yields BROKEN. It does **not** explicitly require `audit` to check
that each stored `prev` equals the prior recomputed/stored chain (a *linkage* check) in
addition to recomputing each entry's own chain. Recompute-from-stored-prev alone passes every
pinned vector; a separate linkage check additionally catches a forged-but-self-consistent
re-chained suffix. The reference (`membrane.py`'s `audit()`) and the Node.js impl both do linkage.
Recommend §7 state the linkage requirement explicitly so an independent impl cannot legally
omit it.

## F5 -- `canonical_json` byte encoding before SHA-256 is unstated (immaterial today)

§7 pins `canonical_json(fact)` as the `json.dumps(fact, sort_keys=True)` *string* but not the
byte encoding hashed. Under `ensure_ascii` the output is pure ASCII, so UTF-8 / ASCII / latin-1
are byte-identical and the choice is immaterial -- but it would matter if `ensure_ascii` were
ever relaxed (which §7 forbids). Recommend stating "UTF-8 encode the concatenation before
SHA-256" for completeness.

## F6 -- `anchor` has no pinned stdout token; `selftest` failure path is unspecified

§13 pins stdout tokens for verify/coherence/refuse/corroborate/audit/selftest but lists none
for `anchor` (no vector checks anchor stdout -- `anchor-then-audit` inspects only the resulting
log). That is fine, but worth stating: `anchor` conforms with exit 0 + a chained log entry and
no required token. Separately, only `selftest`'s **success** token + exit 0 are pinned; its
failure exit code is unconstrained. Recommend pinning a failure exit (the UNVERIFIABLE/exit-2
class) for symmetry.

## F7 -- `corroborate` read-path set is implementation-defined (by design)

§4 already states the read-path set is implementation-defined and that an impl with fewer
channels MAY emit CORROBORATED where one with more emits QUARANTINE. Only the agree-case is
vector-pinned; QUARANTINE and the no-second-path UNVERIFIABLE case are unpinned **by design**.
The Node.js impl uses a disjoint child-process re-read as its second channel (no git/cat
dependency), which keeps the single pinned vector deterministic across platforms. No change
recommended -- recorded so the asymmetry is not mistaken for a gap.

---

*All findings are against `SPEC.md` v0.2.0-draft. F1 is fixed in this change; F2–F6 are
recommendations for the pre-freeze pass; F7 is by-design. The most valuable output of the
exercise was F1 -- a divergence the passing 18-vector run actively hid.*
