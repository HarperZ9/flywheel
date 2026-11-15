# G1 -- Re-derivable: no secret, no held key, no clock

> **Status of this document.** This is a *derivation*, not a warrant. The gate it
> develops binds only to the degree it re-derives from [SPEC.md](../../SPEC.md)
> §6.5 and §8 and from the non-negotiable boundaries in
> [CONTRIBUTING.md](../../CONTRIBUTING.md). Nothing here is true because a
> maintainer, a corpus, or this curation asserts it. The one-page rubric
> ([../scope-discipline.md](../scope-discipline.md)) states this gate in a
> paragraph; the job of this essay is to go *deeper* -- into the actual code the
> gate governs and the actual history that exercised it -- and to **stop** the
> moment it would only restate the rubric. The philosophy layer (witnesses, the
> coordinate-singularity seam) is a sibling in [../rationale/](../rationale/) and
> is cited as lineage, never as warrant. If this document and `SPEC.md` disagree,
> **`SPEC.md` governs and this document is wrong.** A reader who knows only
> `SPEC.md` should be able to apply the whole of this gate.

---

## The gate, stated once

> **Pass condition.** Every verdict the change can produce is reproducible from
> the same artifact bytes, the same `spec_version`, and -- for marker-dependent
> output only -- the same `corpus_version`. The change introduces no secret, no
> held key, no wall-clock dependency, and no claim EMET cannot re-derive from
> bytes it can read.

- **Boundary:** `SPEC.md` §6.5 ("Re-derivable -- every verdict MUST be reproducible
  from the same `spec_version` plus `corpus_version` plus bytes; no secret, no held
  key") and §8 (the byte-hash core "depends only on SHA-256 and exact bytes; no
  corpus, no key, no clock").
- **`CONTRIBUTING.md`:** a change must not make EMET "depend on a secret or a held
  key, or on any claim it cannot re-derive."

That is the whole rule, and a careful reader could apply it from the rubric alone.
What the rubric cannot do in a paragraph -- and what the rest of this essay does --
is show *why* the rule is the load-bearing one, ground it in the bytes of
`membrane.py` and `corpus.py`, and exhibit the one moment in this project's real
history where the gate's failure mode actually occurred and was caught only by
running a second author's code.

---

## The unifying thesis, stated in this gate's terms

EMET's entire shape encodes one fact: **integrity is witnessed, not
self-attested -- nothing can be its own independent witness.** Three forms of that
one fact recur across the curation, and `SPEC.md` §11 names all three as honest
limits, not as incidental caveats:

- a compromised substrate re-derives a compromised self-hash *consistently*
  (§11, trust-root regress);
- a same-author port agrees with its own author's misreading (the conformance
  posture of §12: the reference passing its own vectors proves only internal
  consistency);
- one coordinate chart always leaves a singularity uncovered (the
  coordinate-singularity figure in [../rationale/](../rationale/), the philosophy
  sibling).

G1 is the gate that keeps the *second witness possible at all.* This is the
connection the rubric states but does not develop, and it is the spine of this
essay: **a held key makes a verdict a property the tool *has* rather than a fact
anyone *re-derives*, and that is precisely what kills the second-witness check.**
If `verify` consulted a key only the maintainer holds, then an independent
re-implementation -- the different-author witness `CONTRIBUTING.md` calls "exactly
what the project still needs" -- could no longer reproduce the verdict. It would
have to *trust the holder of the key.* And the one thing EMET exists to refuse is
trust as a substitute for re-derivation. So G1 is not one boundary among six
that happen to coexist; it is the boundary that the witness requirement reduces
to in the byte-hash core. Re-derivability *is* the witness requirement, expressed
in the only currency a verifier of bytes has: the bytes, the spec, and (for
marker output) the versioned corpus -- and nothing else.

---

## What the code actually does, and why it is already a G1 pass

The gate governs `membrane.py`'s `sha` and `verify`, and the byte-hash core they
sit in. The core is small enough to read in full, which is the point: the smaller
the thing that must be believed, the less there is to take on faith. Here is the
hash primitive and the inputs that reach it.

```python
def sha(b):
    return hashlib.sha256(b).hexdigest()
```

`sha` takes bytes and returns a hex digest. It reads no environment, no file, no
clock, no network, no random source. Given the same bytes it returns the same
string on every platform, in every process, forever. That is the entire
re-derivability guarantee in one function: the verdict's positive content is a
pure function of bytes the verifier can itself read.

Now `verify`, which is the closed three-way fork the whole lattice resolves to.
The lines that matter for G1 are the inputs to the comparison:

```python
def verify(paths):
    db = json.load(open(ANCHORS, encoding="utf-8")) if os.path.exists(ANCHORS) else {}
    bad = 0
    for p in paths:
        p = _key(p); want = db.get(p)
        if want is None:
            print(governed(LATTICE, "UNVERIFIABLE") + " " + p + " reason=E_NO_ANCHOR"); bad += 1; continue
        b, err = try_raw(p)
        if err:
            print(governed(LATTICE, "UNVERIFIABLE") + " " + p + " reason=" + err)
            record("verify", {"path": p, "result": "UNVERIFIABLE", "reason": err}); bad += 1; continue
        got = sha(b); ok = got == want
        print(governed(LATTICE, "MATCH" if ok else "DRIFT") + " " + p + " want=" + want[:16] + " got=" + got[:16])
        record("verify", {"path": p, "result": "MATCH" if ok else "DRIFT"}); bad += 0 if ok else 1
    sys.exit(0 if not bad else 2)
```

Two inputs decide the verdict: `want`, the hash the operator pinned at anchor
time, and `got`, `sha(try_raw(p))` recomputed *now* over the present raw bytes.
The verdict is `got == want`. Trace every input to that equality and ask the G1
question of each -- *can a second party re-derive it from bytes it can read?*

- `got` is `sha` of `try_raw(p)`. `try_raw` is `open(path, "rb").read()` (§3's
  raw-byte channel) with the failure paths routed to `UNVERIFIABLE` and a stable
  machine reason code. Pure function of the artifact's bytes. **Re-derivable.**
- `want` comes from `anchors.json`, which §15 declares *implementation-private*.
  This is the one input a contributor might mistake for a held key -- and the
  distinction is exactly the gate. `want` is not a secret EMET *withholds*; it is
  the operator's own pinned hash of the operator's own bytes, recorded at a moment
  the operator authorized (`anchor`). It carries no entropy the operator did not
  put there. A second implementation cannot read *this* `anchors.json` (its format
  is unstandardized -- §15 requires anchor and verify in one conformance run be the
  *same* implementation), but it re-derives the *same `want`* by re-running
  `anchor` on the same bytes: `want` is `sha` of the bytes at pin time. The anchor
  store caches a re-derivation; it does not hold a secret. The verdict remains a
  fact anyone with the bytes reconstructs, not a property this install possesses.

So `verify` is already a G1 pass, and tracing *why* is the gate in action: there
is no branch in which `got == want` depends on anything but bytes the verifier
read and a hash the operator pinned of bytes the operator read. No clock enters
(`record` writes a chained log entry but the *verdict* -- the printed token and the
exit code -- never reads wall-clock time; the chain is `SHA-256(prev + kind +
canonical_json(fact))`, no timestamp). No network enters. No random nonce enters.
`selftest` makes the same point reflexively: it prints `sha(raw(__file__))` and
calls it "my only credential; re-derive it from source to verify me" -- the tool's
own identity is a re-derivable hash, not a held key, which is why §11 can admit
that a compromised substrate re-derives a compromised self-hash and still keep
EMET coherent. The credential being re-derivable is *exactly* what lets an
external witness check it.

**This mapping is load-bearing**, not illumination: G1 is not an analogy laid over
the code, it is the property the code's input set must have, and you verify it by
enumerating the inputs to the verdict-deciding line and confirming each is
bytes-or-pinned-hash. Strip the property and `verify` would have an input no
second party could reproduce, and the second-witness check would be gone.

---

## The real history: the F1 marker-count divergence

The strongest case for G1 is not the part of the code that already passes it
trivially -- `sha` could hardly hold a secret -- but the part where re-derivability
was *quietly broken* and only a second author caught it. That is the
marker-census path, and it happened in this project on 2026-06-08. It is recorded
in [../spec-findings-from-js-impl.md](../spec-findings-from-js-impl.md), finding
**F1**, "Marker count was unpinned." (Confidence: high -- the finding, the
resolution, and the locking vector are all in the repository.)

Here is the failure, precisely. `SPEC.md` §8/§16 called the `refuse` output
`in_band_authority_claims=N` a "marker count" matched by "literal
ASCII-case-insensitive substring." It did not say whether `N` is the number of
**distinct** corpus entries that match, or the number of **occurrences**. The four
`refuse` vectors then in the suite (counts 3/0/1/1) could not tell the two apart:
no marker repeated and none was a substring of another, so distinct-counting and
occurrence-counting returned *identical* numbers on every pinned input. The suite
was green and the gap was invisible.

A clean-room Node.js implementation, written against `SPEC.md` plus the vectors
plus `markers.corpus` *alone* -- no reference code read, the §12 different-author
witness -- had to guess, and chose **distinct**. The Python reference,
`corpus.py`'s `scan()`, counts **occurrences**: it is a non-overlapping leftmost
scan that emits one count per matched span and advances past it.

```python
def scan(hay, markers):
    """Non-overlapping leftmost scan in corpus order.
    Return (hits, redacted_bytes) where hits is a list of (offset, length)."""
    out = bytearray()
    hits = []
    i = 0
    n = len(hay)
    while i < n:
        ln = 0
        for m in markers:
            if m and matches_at(hay, i, m):
                ln = len(m)
                break
        if ln:
            hits.append((i, ln))
            out += REPL
            i += ln
        else:
            out.append(hay[i])
            i += 1
    return hits, bytes(out)
```

On `authority_pill authority_pill` the reference returns **2**; the clean-room
distinct-counter returned **1**. Same bytes, same `spec_version`, same
`corpus_version` -- *divergent verdict.* That is a G1 failure in its purest form,
and the crucial detail is **how it was caught**: not by reading the spec harder,
not by review, but by *running a second author's code on the same input and
observing the numbers disagree.* The spec text under-determined the verdict, so
the verdict was not, in fact, re-derivable from "bytes plus `spec_version` plus
`corpus_version` alone" -- there was a hidden fourth input, the implementer's
*choice* of counting discipline, and a choice is exactly the kind of un-witnessed
state G1 forbids. An implementer's guess is a held key with extra steps: a
verdict-determining input that lives in one author's head and that no second party
can reproduce without asking that author what they meant.

The resolution is the model G1 prescribes, and it is the model the rubric's §6
("fix the spec, not the code") names: the gap was real, so **the spec was fixed,
not routed around.** `SPEC.md` §16 now pins the count to "a non-overlapping
leftmost scan in corpus order," and a new conformance vector,
`refuse-repeated-marker-occurrence-count`, locks it: input
`authority_pill authority_pill`, expected `in_band_authority_claims=2`, exit 3
(`conformance/vectors.json`, raising the suite from 18 to 19 vectors). All four
implementations -- Python reference, Rust port, aligned Node.js, Go port -- now re-derive the
same count. The hidden input was eliminated by making the counting discipline part
of the bytes-plus-spec the verdict is a function of.

The deeper reading is the one that connects F1 back to the thesis. The reference
implementation had passed *its own* vectors the whole time -- and §12 says exactly
why that proves nothing: "a conformance claim by the reference implementation
against its own vectors demonstrates internal consistency only." A same-author
test agrees with its own author's unstated assumption, because the assumption is
shared between the code under test and the test that checks it. The
occurrence-vs-distinct choice was *invisible to the author* precisely because the
author made the same choice in both places. It took a **different author** --
literally a different person's clean-room reading -- to make the unstated
assumption visible, by holding a different one. This is the second witness made
concrete: not a metaphor about epistemology, but a Node.js process printing `1`
where the reference printed `2`. **Re-derivability is the witness requirement, and
the witness has to be a different author or it witnesses nothing but its own
echo.** G1 is the gate that keeps that witness able to exist; F1 is the moment the
gate's necessity stopped being theoretical.

---

## The corpus is data, and that is the subtle half of the gate

The marker path is also where G1's exact scope is easiest to misread, so the
distinction earns a paragraph. The byte-hash core (`anchor`, `verify`,
`coherence`, `corroborate`, `audit`) depends on "SHA-256 and exact bytes; no
corpus, no key, no clock" (§8). The marker census (`refuse`) depends on *one more
thing* -- the versioned `markers.corpus` denylist -- and that is **not** a G1
violation. The denylist is a "versioned data artifact" (§8), sha-pinned and echoed
on every marker-dependent line: `corpus.py` returns `(version, sha256, markers)`,
and `refuse` prints `corpus_version=` and `corpus_sha256=` alongside the count.
A second implementation pinned to the same `corpus_version` re-derives the same
verdict; a disagreement is therefore *attributable* -- to corpus drift versus
artifact drift -- rather than mysterious.

This is the line G1 actually polices, and it is finer than "no external inputs."
The pass condition is **not** "the verdict depends on nothing but the artifact." It
is "the verdict depends on nothing the verifier cannot *re-derive from bytes it can
read*, and every such input is *versioned and echoed* so a second party reproduces
it." A `corpus_version` is a legitimate input because it is bytes-on-disk with a
published hash, not a secret in the maintainer's keyring. The boundary G1 draws is
between **re-derivable inputs** (the bytes, the spec, the versioned corpus) and
**held inputs** (a key, a cached trust, a clock reading, an implementer's unstated
choice). The first set may grow without bound -- that is is-axis depth. The second
set must stay empty -- any member of it is the ought-axis creep G1 exists to catch.

---

## The strongest objection, and the answer

> **Objection.** Re-derivability is a luxury that costs the tool its strongest
> features. A signed verdict -- EMET holds a private key, signs each `MATCH`, and a
> consumer verifies the signature -- is *more* trustworthy than an unsigned one, not
> less: it proves the verdict came from a genuine EMET and was not forged by a
> man-in-the-middle. Likewise a cached "this artifact was `MATCH` last run, skip the
> rehash" makes a CI gate orders of magnitude faster on a large tree. G1 forbids
> both for a purity that buys nothing a real deployment wants. You are refusing a
> signing key to protect a witness that, in practice, no one ever runs.

This is the objection to take seriously, because both features are genuinely
useful, and "useful but disqualifying" is the exact shape the rubric warns is
possible. The answer is not that signing and caching are bad engineering; it is
that each *relocates the verdict from a re-derived fact to a held property*, and
that relocation is the seam being crossed.

Take the signing key first. A signature does not make the verdict more
re-derivable; it makes it more *attributable to a key-holder* -- which is the
opposite move. With an unsigned `MATCH`, a consumer who doubts the verdict
**recomputes it**: same bytes, same `sha`, same answer, no permission needed from
anyone. With a signed `MATCH`, a consumer who doubts the verdict must **verify the
signature against the key** -- and now the verdict's authority flows from *who holds
the key*, not from *what the bytes are.* The second-witness check has been
inverted: instead of "anyone re-derives this," it is "trust that the holder of this
key computed it honestly." That is precisely the property §11 and §12 forbid EMET
to have about *itself* -- "EMET MUST NOT be its own root of trust" -- now smuggled in
at the verdict level. A signed verdict is a verdict that asserts its own provenance
by authority, which is `TRUSTED` wearing a cryptographic disguise. (Note the seam
G5 draws alongside: a *signing adapter in a separate package*, translating EMET's
re-derivable verdicts into a signed envelope for transport, is fine -- the verdict
stays re-derivable and the signature is a downstream operator's choice. The
violation is the *core* consulting a key to *produce* the verdict. See
[./G5-minimal-core.md](./G5-minimal-core.md).)

Now the cache. "This was `MATCH` last time, skip the rehash" sounds like an
optimization, but read what it does to the verdict's truth-conditions. The cached
run emits `MATCH` *without recomputing `got`* -- so the printed verdict is no longer
"`sha` of the present bytes equals the anchor"; it is "the present bytes equal the
bytes as of whenever the cache was written." If the artifact changed *after* the
cache entry and before this run, the cache emits `MATCH` over `DRIFT`-truth. The
verdict has become a stored property of a past run rather than a fact re-derived
now, and §9 names the prohibition exactly: an implementation "MUST NOT substitute a
default, a cached value, or a trust assertion." A cache is a `MATCH` you are asked
to take on the cache's word -- un-witnessed, un-re-derived, and wrong the instant
the world moved under it. The honest fast path is not a verdict cache; it is the
operator choosing, on owner-controlled infrastructure, which paths to re-verify --
an *operator* decision on a re-derivable tool, not the tool holding state that
shortcuts its own re-derivation.

The answer, in one line: **both features improve a number the deployment cares
about -- trust-of-provenance, or wall-clock speed -- by paying in the one currency
G1 protects, the verdict's re-derivability. The two do not net, because they are
measured on different axes.** Usefulness is is-axis; the cost is ought-axis; the
rubric's whole point is that you cannot trade across the seam.

---

## The refuter

A gate worth keeping must say how it would fail. G1 fails -- is shown to be either
incomplete or over-tight -- if either of these is exhibited:

> **Over-tight (the over-minimalism failure §5 of the rubric names):** if a change
> that G1 blocks can be shown to leave every verdict *exactly as re-derivable as
> before* -- same bytes-plus-spec-plus-corpus function, no new held input, no
> witness lost -- then G1 was misapplied as a freeze, not a seam. The clearest
> probe: a change that adds a *re-derivable* input (a second versioned data
> artifact echoed with its own hash, on the model of `corpus_version`) is **depth**,
> and a reviewer who reflexively blocks it "because the core takes no external
> input" has mistaken §8's *byte-hash core* scope for a ban on the marker path that
> §8 itself sanctions. Blocking the F1 fix's new vector, or a second governed
> corpus, "to stay minimal" would be this failure.

> **Incomplete (the perimeter-gap failure):** if a change *passes* G1 -- introduces
> no key, no clock, no cache, no unversioned input -- and yet a second independent
> implementation, pinned to the same `spec_version` and `corpus_version`, *cannot
> reproduce some verdict it emits*, then G1 as written does not catch every
> re-derivability break and the gate is incomplete. F1 is the live example that
> this failure is real, not hypothetical: the pre-F1 spec passed every "no secret,
> no key, no clock" reading and *still* harbored a verdict two authors computed
> differently, because the hidden input was a *guess the spec under-determined*,
> not a key. The patch to the gate is the patch the project already applied -- pin
> the under-determined behavior in the spec and lock it with a discriminating
> vector -- but the refuter stands as a standing reminder: **the only proof that
> G1's perimeter has no gap is a different-author implementation passing the
> vectors, and `SPEC.md` §12 records that this witness "is not yet satisfied."**

Both refuters are mechanically checkable against `SPEC.md` §6.5, §8, §9, §12 and
the conformance vectors by anyone, with no appeal to the authority of this
document. The gate earns its keep only so long as both stay un-triggered -- and the
honest posture, which the thesis demands, is that the second refuter is *not yet
discharged*, because the different-author witness the whole gate exists to keep
possible has caught one divergence (F1) and may catch another. G1 is the
discipline that keeps it able to.

---

## Where this gate stops

The rubric states G1 in a paragraph; this essay added the four things the
paragraph cannot hold: the trace of every input to `verify`'s deciding line
(showing the anchor store is a cached re-derivation, not a held key); the F1
history (showing the witness requirement is operational, not metaphorical, and
that a same-author suite hid the divergence a different author surfaced); the
corpus-as-data distinction (showing G1 polices *held vs re-derivable* inputs, not
*zero vs nonzero* inputs); and the signing/caching objection (showing why two
genuinely useful features pay in the currency the gate protects). Beyond this the
essay would only re-walk `membrane.py` or restate
[../scope-discipline.md](../scope-discipline.md), which is the bloat the rubric's
§5 names as over-minimalism's other face. It stops here.

---

*Further reading (lineage and grounding, never warrant): the spine
[./README.md](./README.md) and the one-page rubric
[../scope-discipline.md](../scope-discipline.md); sibling gates
[./G2-closed-lattice.md](./G2-closed-lattice.md) (the closed lattice; a verdict's
*type* and its *re-derivability* are the two halves of "facts, not authority"),
[./G5-minimal-core.md](./G5-minimal-core.md) (the signing-adapter seam referenced
above). `SPEC.md` §§3, 6.5, 8, 9, 11, 12, 15, 16; `CONTRIBUTING.md` ("the most
valuable contribution: another implementation"; "fix the spec");
[../spec-findings-from-js-impl.md](../spec-findings-from-js-impl.md) finding F1.
Code cited: `membrane.py` (`sha`, `verify`, `try_raw`, `selftest`), `corpus.py`
(`scan`), `conformance/vectors.json`
(`refuse-repeated-marker-occurrence-count`). Philosophy siblings in
[../rationale/](../rationale/): [../rationale/03-occasionalism.md](../rationale/03-occasionalism.md)
(re-derivability as its own law -- re-conferred per operation, nothing cached, no
held key), [../rationale/05-authored-root.md](../rationale/05-authored-root.md)
(EMET is not its own root of trust; the external witness),
[../rationale/02-no-aseity.md](../rationale/02-no-aseity.md) (a conferred verdict
is real *because* it is re-derivable, not asserted).*
