# 03 -- Process over Property: Re-derivability, and the Name that Is the Hash

> **Status of this essay:** load-bearing. It derives two EMET elements from two
> corpus laws: the re-derivability of every verdict (recomputed per operation,
> nothing cached, no held key) from **L11, Process over Property**; and the
> byte-hash identity (SHA-256 over the exact raw bytes -- the name *is* the hash)
> from **L6, Intrinsic Substitution**. Both mappings are marked **load-bearing**
> below. As with every essay in this curation, the warrant is the argument you
> can re-run, not the corpus's say-so; `research/` is cited only as further
> reading. See [./00-orientation.md](./00-orientation.md) for the frames and
> [./GLOSSARY.md](./GLOSSARY.md) for every term used here.

---

## 1. Thesis

A verdict in EMET persists by no construction. There is no stored "this file is
good" that a later run reads back; there is no trust object that, once minted,
sits in a store accruing standing. Each time you ask EMET whether an artifact
still matches what the operator anchored, EMET **re-derives** the answer from the
artifact's present raw bytes, the spec it implements, and (for marker-dependent
output only) the corpus version -- and from nothing else. No secret participates.
No held key participates. No clock participates in the byte-hash core. The
verdict is recomputed *per operation*, and between operations it does not exist.

The second half of the thesis is what makes the first half exact rather than
aspirational. The reason EMET *can* re-derive the answer instead of trusting a
stored token is that the identity it checks is **intrinsic**: the name of an
artifact is the SHA-256 of its exact raw bytes. There is no gap between the thing
and the check, because the check is not *about* the thing -- it *is* the thing,
read again. Change one byte and you have a different name; that is not a failure
mode to be detected later, it is the definition of identity. The hash is not a
certificate stapled to the bytes. It is what the bytes *are*, computed.

These two moves -- re-derive rather than store, and make identity intrinsic rather
than extrinsic -- are one design instinct seen twice. Together they are why EMET
is a *process* maintained per operation, never a *property* held between them.

---

## 2. The law, in the operator's vocabulary

### 2.1 L11 -- Process over Property

The corpus draws a line between two kinds of defense. A **property-defense**
terminates: you build it, and once built it holds *by construction*. The bytes of
a content-addressed blob cannot disagree with their hash, because the hash is
computed from them; the property is settled and stays settled with no further
work. A **perimeter-defense** does not terminate. It is re-enacted on every
operation, paid continuously, and -- this is the load-bearing phrase -- it
*persists by no construction*. Stop performing it and it lapses. The perimeter
has no aseity (see [./02-no-aseity.md](./02-no-aseity.md)); it is defended
*occasionally*, re-spoken for the life of the channel.

The corpus reaches for **occasionalism** to name this tempo. In its theological
source (al-Ghazālī, with the *kun fayakūn* motif of existence-as-utterance in the
background), occasionalism is the doctrine that a thing does not carry its own
persistence from one moment to the next; it is re-conferred. The corpus borrows
exactly one feature: continuous re-conferral. A defense that holds only while it
is being performed is occasionalist in precisely that sense -- withdraw the
performance and it is gone, not weakened.

> **Provenance (further reading, not warrant):** L11, *Process over Property*, in
> `research/CATALOG.md` (Law L11); occasionalism in `research/CATALOG.md`
> (Abstracts) and the corrected-tempo discussion in
> `research/dissertation/membrane-through-line.md` §2. Cited so you can check the
> lineage -- *not* so the claim stands because the corpus made it. The claim
> stands or falls on §3 and §4 below, where EMET's actual bytes do the deciding.

### 2.2 L6 -- Intrinsic Substitution

The corpus's second relevant law is a design discipline: **prefer replacing an
extrinsic check with an intrinsic property whose *existence entails* what the
check verified.** Collapse the gap between the thing and its verification. The
canonical illustrations are a family: with an object-capability, *possession is
the proof* (there is no separate permission table to consult); with a
zero-knowledge proof, *nothing is shown* yet the property holds; with
content-addressing, *the name is the hash*; with a corticomuscular-coherence
witness, the coupling either obtains or it does not. In each, a check that could
have been a separate, forgeable, lose-able artifact is dissolved into a property
the thing cannot have-and-also-fail.

Content-addressing is the member of that family EMET uses, and the only one it
needs. A wrong byte is a different name. There is no certificate to forge, no
template to compare against, no lookup that could return a stale "still valid."
The verification is not adjacent to the artifact; it is the artifact's identity,
recomputed.

> **Provenance (further reading, not warrant):** L6, *Intrinsic Substitution*,
> and the *Intrinsic-over-Extrinsic* and *Content-addressing / Merkle log*
> entries in `research/CATALOG.md`; the cryptographic primitive is SHA-256 and
> the Merkle/content-addressing lineage (Merkle, 1979; git's object model is the
> familiar engineering instance). Again: lineage, not authority. The warrant is
> the `sha` function in `membrane.py` and SPEC §3, read below.

---

## 3. The objection -- and the corpus's answer

The sharpest objection to importing occasionalism here is not skepticism about
EMET; it is a correction the corpus made *to itself*, and getting it right is the
discipline this essay must honor.

### 3.1 The objection: the substrate-tempo correction

> **Objection.** "Re-spoken *each instant*" is false. The occasionalist tempo you
> are borrowing from al-Ghazālī -- fresh creation every instant, nothing
> persisting between moments -- does not survive contact with the substrate the
> corpus itself studies. A neuron's membrane does not re-establish its resting
> potential instant by instant. The Na⁺/K⁺-ATPase sets up the ionic gradients
> *slowly*, and at any given instant the potential is fixed by the standing
> ion permeabilities. Freeze the pump and the membrane still holds its potential
> for *many spikes* before it runs down. So the honest tempo is metabolic, not
> per-instant: "continuously sustained against entropy, or it decays on its own
> timescale." If your foundational analogy already overstated the immediacy of
> re-conferral, why should I trust the tempo claim you make about EMET?

This is a fair hit, and the corpus concedes it without flinching. In
`research/dissertation/membrane-through-line.md` §2, the per-instant reading is
explicitly *struck*: al-Ghazālī's "each instant" is demoted from **evidence** to
**intuition-lineage**. The theology supplied the *idea* of continuous
re-conferral; the biology supplies the *actual tempo*, and they are not the same
tempo. (Confidence: high -- this is the corpus's own stated position in §2, not a
paraphrase I am imputing to it.)

### 3.2 The answer: EMET is the clean engineered case, and its tempo is *per operation*

Here is the move, and it is the reason this essay can use occasionalism at all.
**Concede the biological tempo entirely.** The neuron is not a per-instant
occasionalist system, and no honest account should pretend it is. But EMET is not
a neuron, and it is not under metabolic load. EMET is the **clean engineered
case** -- the artifact *built* to be a deciding seam -- where the re-conferral tempo
is neither "each instant" (false, as the substrate showed) nor "metabolic, decays
on its own timescale" (true of biology, but still a *property held between
performances*). In EMET the tempo is **exactly per operation**, and it is exact
because it is engineered to be.

What does "per operation" mean precisely? It means: the unit of re-conferral is
one invocation of one command. When you run `verify`, the verdict is computed
inside that call and exists for the duration of that call. It is not held over
to the next call. The next `verify` does not consult the result of the last one;
it reads the bytes again and recomputes. There is no metabolic interval during
which a previously-conferred verdict coasts. Between operations, the verdict is
*nothing* -- not a decaying potential, not a cached value with a half-life, but
genuinely absent, because the only thing persisted is the anchor (a pinned
`(path, sha256)` the operator authorized), and an anchor is a *fact to re-derive
against*, not a verdict.

So the engineered case is *cleaner* than the biological one, not a looser
analogy of it. The biology forced the correction "not each instant"; the
engineering then realizes the disciplined remainder -- continuous re-conferral --
at a tempo so exact that the unit is countable: one operation, one re-derivation.
That is the tempo this curation uses throughout, and it is the only tempo the
objection leaves standing.

> **Discipline note.** This is why every essay in the curation says **per
> operation** and never "each instant." The phrase "each instant" is the
> corpus's own discarded overstatement; repeating it would re-import the exact
> error `research/dissertation/membrane-through-line.md` §2 cut. The mapping from
> occasionalism to EMET is **load-bearing**, but only at the corrected tempo. At
> the per-instant tempo it would be **lineage** at best -- a branding, not a
> mechanism -- and we do not lean on it there.

---

## 4. The EMET element this forces

The thesis is not satisfied by the laws alone; it is satisfied by reading EMET's
actual bytes and its specification and finding that they implement exactly this
process-not-property, intrinsic-not-extrinsic shape. Two SPEC sections and two
spans of `membrane.py` do the deciding.

### 4.1 Identity is intrinsic -- SHA-256 over the exact raw bytes (SPEC §3; the `sha` function in `membrane.py`)

SPEC §3 is unambiguous: the identity of an artifact MUST be SHA-256 over its
**exact raw bytes**. An implementation MUST NOT normalize, transcode, or
canonicalize the bytes before hashing -- line endings, encoding, and whitespace
are part of the artifact, and detecting any byte change (including a CRLF
rewrite) is a *feature*, not a nuisance to be smoothed away. The target bytes
MUST be read through a raw byte channel; with no raw channel, the implementation
reports UNVERIFIABLE (SPEC §9).

The code is two lines, and they are the whole of identity:

```python
def sha(b):
    return hashlib.sha256(b).hexdigest()
```

That is the `sha` function in `membrane.py`. There is no preprocessing. The argument `b` is the
raw bytes returned by `try_raw`, which opens the path `"rb"` -- binary -- and
returns the bytes verbatim or a stable reason code on inability
(the `try_raw` function in `membrane.py`). The name of an artifact, in EMET, is just `sha(those
bytes)`. This is L6 made literal: **the name is the hash**, and the existence of
the name *entails* what an extrinsic certificate would have had to assert
separately -- namely, "these are those bytes." There is nothing to forge between
the bytes and their name, because there is nothing between them.

> **Mapping status: load-bearing.** L6 → SPEC §3 → the `sha` function in `membrane.py` is a
> mechanism, not an illustration. Remove the intrinsic-identity property -- let
> EMET compare against a stored certificate, or hash a normalized view -- and the
> re-derivability claim of §4.2 collapses, because the thing being re-derived
> would no longer *be* the artifact's identity.

### 4.2 Verdicts are re-derived per operation -- no cache, no key (SPEC §8; the `verify` function in `membrane.py`)

SPEC §8 scopes re-derivability precisely. A verdict is reproducible given the
same artifact bytes, the same `spec_version`, and -- for marker-dependent output
only (`refuse`, the marker census) -- the same `corpus_version`. The byte-hash
core (anchor, verify, coherence, corroborate, audit) **depends only on SHA-256
and exact bytes: no corpus, no key, no clock.** That sentence is the engineering
statement of L11: the verdict is not a thing held; it is a thing redone, from
inputs that are all present and public.

Read `verify` and watch it re-derive:

```python
def verify(paths):
    db = json.load(open(ANCHORS, encoding="utf-8")) if os.path.exists(ANCHORS) else {}
    bad = 0
    for p in paths:
        p = _key(p); want = db.get(p)
        if want is None:
            print("UNVERIFIABLE " + p + " reason=E_NO_ANCHOR"); bad += 1; continue
        b, err = try_raw(p)
        if err:
            print("UNVERIFIABLE " + p + " reason=" + err)
            record("verify", {"path": p, "result": "UNVERIFIABLE", "reason": err}); bad += 1; continue
        got = sha(b); ok = got == want
        print(("MATCH " if ok else "DRIFT ") + p + " want=" + want[:16] + " got=" + got[:16])
        record("verify", {"path": p, "result": "MATCH" if ok else "DRIFT"}); bad += 0 if ok else 1
    sys.exit(0 if not bad else 2)
```

That is the `verify` function in `membrane.py`. Three observations carry the whole thesis, and each
is checkable against those exact lines:

1. **What is stored is an anchor, not a verdict.** The anchor store `db` maps a
   path to `want` -- a *prior hash* the operator authorized, the pinned
   `(path, sha256)` of SPEC §1. It does not store "MATCH." A previous run's
   *verdict* is nowhere in `db`. The audit log does record that a `verify`
   happened and what it concluded (`record("verify", {"result": ...})`), but that
   is a tamper-evident *history of operations*, read by `audit`, never read back
   by `verify` as a substitute for recomputing. The next `verify` ignores it
   entirely.

2. **The verdict is recomputed inside the call.** `got = sha(b)` hashes the bytes
   *read in this operation*; `ok = got == want` is the comparison, performed now.
   Nothing about `ok` survives the loop iteration except as printed output and a
   logged fact. There is no memoization, no "if we checked this recently, skip."
   Re-run `verify` and `try_raw` reads the file again and `sha` runs again. That
   is per-operation re-conferral, literally.

3. **No secret, no key, no clock.** Everything `verify` consumes is the anchor
   (public, the operator's own pin), the bytes (public, the artifact itself), and
   SHA-256 (a public function). There is no key material; nothing about the
   verdict depends on holding a secret, which is exactly why an independent
   implementation could re-derive the same MATCH/DRIFT from the same inputs
   (SPEC §12). The byte-hash core touches no clock: `verify` produces no
   timestamp and its result does not vary with when you run it. This is the
   operational meaning of "persists by no construction" -- there is no held thing
   that *could* persist; there are only inputs, re-combined on demand.

A fourth observation ties this back to [./02-no-aseity.md](./02-no-aseity.md):
when the answer cannot be re-derived -- no anchor, or no raw channel -- `verify`
emits **UNVERIFIABLE**, never a substituted default and never a trust assertion
(SPEC §9: "Inability is never trust"). The process having no fallback to a stored
trust is the no-aseity discipline and the process-over-property discipline
meeting at the same line of code.

> **Mapping status: load-bearing.** L11 → SPEC §8 → the `verify` function in `membrane.py` is the
> mechanism by which EMET is a process and not a property. It is not an
> illustration of occasionalism; it is per-operation re-conferral implemented.
> The occasionalist *vocabulary* (re-conferral, no aseity-of-the-perimeter) is
> the **illumination/lineage** that named the shape; the *mechanism* -- recompute
> from public inputs every call, store no verdict -- is what bears the weight, and
> it would bear it under any other name.

---

## 5. The refuter

A load-bearing claim must say what would falsify it. Two failures would refute
this essay, and each maps to one of the two laws.

**Refuter for L6 (intrinsic identity).** *Any normalization before hashing makes
identity extrinsic and breaks re-derivation.* If EMET ever lower-cased, stripped
whitespace, rewrote CRLF to LF, transcoded an encoding, or canonicalized JSON
*on the target* before computing its hash, then the hash would no longer be the
artifact's identity -- it would be the identity of a *derived view*, and the
artifact and its name could quietly diverge. Two implementations applying
different normalizations would disagree on the same bytes, and re-derivability
across implementations (SPEC §12) would be lost. Detecting a CRLF rewrite is a
*feature* (SPEC §3) precisely because the absence of normalization is what keeps
identity intrinsic. Show EMET normalizing a target before `sha`, and the L6
mapping is refuted. (Note the one *permitted* normalization is the anchor-store
*key* -- the `_key` function in `membrane.py` forward-slashes the path so `anchors.json`
is portable across platforms. That normalizes the *lookup key*, never the
*bytes hashed*; the byte channel `try_raw` feeds `sha` raw. The distinction is
the whole point: identity is intrinsic, addressing is conventional.)

**Refuter for L11 (process over property).** *Any cached verdict that survives
between runs makes EMET a property-defense and refutes the per-operation tempo.*
If `verify` ever consulted a stored MATCH/DRIFT and returned it without rehashing
-- a verdict cache, a "skip if unchanged" shortcut keyed on mtime, a trust object
persisted to disk -- then the verdict would persist *by construction* between
operations, and the occasionalist reading would be false. The honest tempo would
no longer be "per operation"; it would be "until the cache is invalidated," which
is a metabolic-style coast, the very thing the engineered case was supposed to be
cleaner than. Show a verdict that outlives the call that produced it, and the
L11 mapping is refuted.

Both refuters are *operational*: you do not need to argue about al-Ghazālī to run
them. Read the code; run the command twice; check that nothing but the anchor and
the bytes determined the answer.

---

## 6. Why two rows, one essay

This essay covers two rows of the Rationale Map -- re-derivability (L11) and the
SHA-256-over-exact-bytes identity (L6) -- and they belong together rather than in
two essays because *they are not independent*. Re-derivability is only exact
*because* identity is intrinsic. If the name were an extrinsic certificate, then
"re-derive the verdict" would mean "re-check the certificate," and a certificate
can be stale, forged, or separated from its bytes -- re-derivation would inherit
all the gaps L6 exists to collapse. It is the intrinsic identity (L6) that makes
the re-derivation (L11) a recomputation of the *thing itself* rather than a lookup
of a *claim about the thing*. Process-over-property and
intrinsic-over-extrinsic are two statements of one discipline: do not hold what
you can recompute, and do not certify what you can *be*. The byte-hash core of
EMET is what that single discipline looks like when it is implemented in two
lines of hashing and fifteen lines of verifying, and nothing else.

L14 (the authored stop) says a section ends when it returns nothing new. This one
has: the two rows are derived, the objection is answered at the corrected tempo,
the EMET elements are read off the actual bytes, and the refuters are stated. The
seam carries nothing further, so it stops here.

---

## 7. Self-application

This essay is itself a process, not a property. Its standing is not held; it is
re-derived each time a reader runs the argument -- reads the `sha` and
`verify` functions in `membrane.py`, checks SPEC §3, §8, §9, and confirms that no verdict is cached and no
byte is normalized. If you do not re-run it, the essay confers nothing; it is
not a certificate of correctness you can cite, only a derivation you can repeat.
That is the same shape as the thing it describes, and it is deliberate: a
rationale for re-derivability that asked to be *trusted* rather than *re-derived*
would refute itself on contact, in exactly the way a `MATCH` that asked to be
believed without rehashing would. The argument here has no more authority than
the bytes it points you to earn back.

---

### Related

- [./00-orientation.md](./00-orientation.md) -- the five frames, including
  occasionalism at the per-operation tempo.
- [./02-no-aseity.md](./02-no-aseity.md) -- why there is no `TRUSTED`; the
  UNVERIFIABLE-never-trust discipline that this essay's `verify` path obeys.
- [./05-authored-root.md](./05-authored-root.md) -- re-derivability is necessary
  but not self-grounding: a compromised substrate re-derives a compromised hash
  consistently, so an external verifier is the check of record.
- [./08-taxonomy.md](./08-taxonomy.md) -- where EMET sits as a literal engineered
  membrane.
- [./GLOSSARY.md](./GLOSSARY.md) -- `process over property (L11)`,
  `intrinsic substitution (L6)`, `occasionalism (al-Ghazālī; per-operation
  tempo)`, `the authored stop (L14)`, and the load-bearing / illumination /
  lineage marking convention.
