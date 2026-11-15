# GLOSSARY -- Corpus Terms, Defined and Pointed

> **How to read this glossary.** Each entry is a *definition you can use*, not a
> *warrant you must accept*. A definition fixes what a word means in this
> curation so the essays can be read self-contained; it does not make any claim
> true by naming a source. Every entry carries exactly one **provenance pointer**
> under *Further reading* -- the lineage of the idea, the place to see it worked
> at length -- and that pointer is **never the reason to believe anything.** If a
> claim built on a term holds, it holds because the argument in the essay holds;
> `research/` is further reading, full stop. A reader who knows only
> [`SPEC.md`](../../SPEC.md) should be able to read every essay through these
> definitions and the primer in [`00-orientation.md`](./00-orientation.md)
> without ever opening `research/`. If a definition here and `SPEC.md` ever
> disagree, `SPEC.md` governs.
>
> **Two reading aids, used throughout.**
> - **Mapping status.** Where a term names a bridge from a corpus idea to an
>   EMET element, the entry marks the bridge **load-bearing** (the idea is the
>   *mechanism*: remove it and an EMET claim collapses) or **illumination /
>   lineage** (the idea *names* or *brands* a shape that some other mechanism
>   already secures: remove it and no claim is lost). Terms that are purely
>   conceptual -- vocabulary the essays use, not mappings into EMET -- are marked
>   *vocabulary*.
> - **Confidence labels.** Any definition that paraphrases a *contested* position
>   (one a competent reader could reasonably dispute, or one the corpus itself
>   corrected) carries a one-word confidence label -- *high / moderate / low* -- on
>   the paraphrase, so a borrowed reading is never mistaken for a settled fact.

The terms are alphabetical. The crux of the whole curation -- that EMET is a
membrane in the literal 1|0 sense for byte integrity (`MATCH`/`DRIFT`),
disciplined to the **authentication** register, refusing to become the
**authorization** membrane -- recurs across several entries; it is defined once at
**authentication ≠ authorization** and cross-referenced from there.

---

### aleph / *emet* / *met*

A figure from Hebrew: *emet* (אמת, "truth") is written aleph–mem–tav; erase the
leading letter, the *aleph*, and what remains is *met* (מת, "dead"). The *aleph*
is the lightest mark in the alphabet -- a near-silent glottal stop -- so the figure
pictures an edge that is *near-nothing in substance yet total in consequence*,
sitting exactly where one state is divided from another. In this curation it
brands the claim that EMET's six boundaries (SPEC §6) are the smallest edge whose
removal does not weaken the tool but changes what it *is*.
**Mapping status: illumination / lineage** -- the figure names the smallest-edge
intuition memorably; it tests nothing and grounds no claim. The load-bearing work
is done by the structural fact that an open perimeter confers nothing, argued
without theology in [`06-aleph.md`](./06-aleph.md).
*Further reading (lineage, never warrant):* the *emet / met / aleph* abstract in
`research/CATALOG.md`; the canonical source of the
"seal of God is *emet*" motif is Babylonian Talmud, *Shabbat* 55a [confidence:
high -- a textual citation, not an interpretation]; the Golem-of-Prague erasure is
**folklore, not Talmud** [confidence: high that it is later folkloric tradition].

### aseity / *esse ab alio*

*Aseity* is the property of existing **from oneself** -- of standing on one's own
footing, owing one's existence to nothing else (literally *a se*, "from itself").
Its denial is *esse ab alio*, "being from another": to exist only as conferred,
relationally and dependently. The curation's foundational move is that nothing in
EMET -- least of all trust -- has aseity; standing is always held *from* something
else and must be re-derived, never assumed. **Vocabulary** (the term frames every
no-aseity derivation; it is not itself a mapping into a single EMET element).
*Further reading (lineage, never warrant):* Aquinas's *esse ab alio* (the
classical contrast of *esse a se* with *esse ab alio*), referenced via L1 in
`research/CATALOG.md`.

### authored root

The terminus of a chain of trust that is **stipulated**, not authenticated -- the
first fold, where someone *authors* the policy or the root rather than reading it
off a prior verified signal. The point of the term is that an authored root
cannot be a signal it authenticated: if every root derived its authority from a
yet-earlier verified signal, there would be no root at all, only relay
("authentication all the way down"). EMET refuses to be its own authored root --
its `selftest` emits its source hash and asserts no authority -- so the check of
record for EMET itself must live outside it. **Mapping status: load-bearing** (the
regress is the mechanism that forces the external verifier; remove it and a
self-rooting EMET re-introduces the aseity its output type denies).
*Further reading (lineage, never warrant):* the trust-root regress in `SPEC.md`
§11, derived in [`05-authored-root.md`](./05-authored-root.md); lineage in the
authored-root regress of `research/dissertation/membrane-through-line.md` §4.

### authentication ≠ authorization

**Authentication** answers an *is*-question about a signal -- *are these the exact
bytes that were pinned?* -- and is settled off the signal, by reading bytes and
comparing a hash; it is, literally, a 1 or a 0. **Authorization** answers an
*ought*-question -- *may this authentic signal cross; is it the operator's
uncoerced will toward this referent, now?* -- and is **not** a property of the
signal at all, but a fact about a will and a policy on the near side of the
boundary. This is the **crux** of the curation: EMET makes the
authentication-grade byte decision (`MATCH`/`DRIFT`/`UNVERIFIABLE`) and *refuses
the authorization crossing* -- it locates the seam and will not launder an *is*
into an *ought*. **Mapping status: load-bearing** (it is encoded in EMET's output
type -- the closed lattice cannot emit a permission).
*Further reading (lineage, never warrant):* L8 in
`research/CATALOG.md`, derived in
[`01-is-ought-seam.md`](./01-is-ought-seam.md); the security lineage runs through
the **ABLP calculus** (Lampson–Abadi–Burrows–Wobber 1992; Abadi–Burrows–Lampson–
Plotkin 1993), which proves authentication propositions insufficient for access
without a separate policy premise [confidence: high on ABLP's result; *moderate*
on the corpus's further claim that the missing premise is specifically *deontic*,
since that novelty was scoped to the literatures surveyed].

### autonomy of the deontic (Pigden)

The thesis that deontic vocabulary -- *ought*, *may*, *permitted* -- is
**autonomous**: a valid inference can introduce no new non-logical vocabulary, so
a conclusion containing a *may* must rest on a premise that already contains one.
It is the careful, defensible form of "Hume's law": not the strong slogan that
*no* permission ever follows from *any* facts (false -- a *policy-relative*
permission does follow from the facts *plus* the descriptive fact that the policy
is in force, exactly as Searle's *counts-as* delivers), but the weaker structural
claim that the deontic premise has to be *authored in*, never derived from a
signal alone. EMET supplies the descriptive premise (the bytes are or are not
authentic) and declines to author the deontic one. **Mapping status:
load-bearing** (it is why `verify`/`refuse` emit facts and never permissions, and
why Boundaries 2 and 4 forbid EMET from adjudicating).
*Further reading (lineage, never warrant):* Pigden's formalization of Hume's law,
referenced via `research/dissertation/MEMBRANE-ERRATA.md` §§2–3 [confidence: high
that the corpus holds the claim at *autonomy of the deontic* and explicitly
*declines* the stronger "this is Hume's guillotine" reading].

### conferred existence

The positive name for the denial of aseity: to exist is to be **conferred** --
held in being relationally and dependently, never self-standing (see **aseity /
*esse ab alio***). The term matters because it blocks a slide: conferral-
dependence is *not* non-existence and *not* "nothing is real." A `MATCH` is real
*and* conferred -- re-derived from bytes that genuinely are what they are -- which
is why no-aseity yields "no `TRUSTED`," not "no verdict." **Vocabulary**.
*Further reading (lineage, never warrant):* L1 (Conferred Existence / No-Aseity)
in `research/CATALOG.md`; the long form in
`research/conferred-existence/thesis/conferred-existence-thesis.md`.

### direction-neutral generativity (L3)

The principle that an instrument's **generativity** (how many things it can become
or be turned to) and its intrinsic **direction** (the *for* it carries) are
inversely related: the more an idea can become, the less *for* it carries on its
own. A pile of sand can become glass, concrete, a filter, an hourglass -- maximally
generative, minimally *for* anything; a finished hourglass is *for* timing and
almost nothing else. EMET is built toward the generative end -- a verifier that can
be pointed at any artifact with a path -- so the *for* of any verdict is authored
downstream, never carried by the tool. **Mapping status: load-bearing** (it forces
the advisory and zero-actuation boundaries; an EMET that authored a *for* would
have spent its generativity).
*Further reading (lineage, never warrant):* L3 in
`research/CATALOG.md`, derived in
[`04-spoken-for.md`](./04-spoken-for.md).

### intrinsic substitution (L6)

The design discipline of **replacing an extrinsic check with an intrinsic property
whose existence entails what the check verified** -- collapsing the gap between a
thing and its verification. The canonical illustration EMET uses is
content-addressing: *the name is the hash*, so a wrong byte is a different name
and there is no certificate to forge, no template to compare, no stale "still
valid" lookup. **Mapping status: load-bearing** (it is what makes re-derivability
exact: the verdict re-derives the artifact's *own identity*, not a separable claim
about it).
*Further reading (lineage, never warrant):* L6 and the *Intrinsic-over-Extrinsic*
abstract in `research/CATALOG.md`; the engineering
lineage is the Merkle / content-addressing tradition (Merkle 1979; git's object
model). Read against `SPEC.md` §3 and the `sha()` function in `membrane.py`, where the warrant
actually lives, in [`03-occasionalism.md`](./03-occasionalism.md).

### literal / isomorphic / lineage

The three-way discipline for grading any mapping the curation draws, so that the
word "membrane" never becomes a universal solvent. A mapping is **literal** when
the predicate genuinely applies and *forbids a competitor description* -- calling
`MATCH`/`DRIFT` a 1|0 byte decision forbids "EMET grades trust" or "EMET makes a
judgement call," because it does neither. It is **isomorphic** when the structure
matches but the substrate differs (the same shape in another medium), and
**lineage** when a source only *brands or names* an intuition and does no
argumentative work (a figure, an etymology, a story). **Vocabulary** (this is the
grading scheme itself; every other mapping is marked against it).
*Further reading (lineage, never warrant):* the literal / isomorphic / lineage
discipline in `research/dissertation/membrane-through-line.md` §§4–6, placed in
[`08-taxonomy.md`](./08-taxonomy.md). The test -- *literal only if it forbids a
competitor description* -- is the load-bearing rule.

### materialized grant

An *ought* made **bearer-portable**: a token (a capability) that carries a
permission someone authored at an earlier moment of issuance. The term answers the
object-capability objection -- "possessing the token *is* authorization, so the
is/ought split collapses." It does not collapse; it **relocates**: a capability is
not an is-fact that mints its own permission from nothing, it is the *frozen record
of a prior authored conferral*, so the seam sits at issuance, not at presentation.
EMET answers only the authentication-side question about such a token (*are these
the genuine bytes?*), never the issuance-side question (*was it validly granted?*).
**Mapping status: load-bearing** (the "relocates, does not vanish" move is what
keeps the capability case from refuting the is/ought seam).
*Further reading (lineage, never warrant):* the materialized-grant / relocation
argument in `research/dissertation/MEMBRANE-ERRATA.md` §5, used in
[`01-is-ought-seam.md`](./01-is-ought-seam.md).

### no-aseity (L1)

The foundational law that **nothing exists on its own footing**: to exist is to be
conferred, relationally and dependently (see **aseity / *esse ab alio***,
**conferred existence**). Applied to EMET, no-aseity is why the verdict lattice is
*closed* and cannot emit `TRUSTED`: trust would be a standing read off a signal,
and no standing is self-standing. Crucially, no-*aseity* is conferral-dependence,
**not** hard nihilism -- the self-refuting "nothing is real" -- so the verdict it
forbids is `TRUSTED`, not *every* verdict; `MATCH` and `UNVERIFIABLE` remain, both
conferred and real. **Mapping status: load-bearing** (it forces the closed
lattice; an emitted `TRUSTED` would refute it).
*Further reading (lineage, never warrant):* L1 in
`research/CATALOG.md`; the defensible reading of
ontological nihilism in Westerhoff and the Madhyamaka tradition (see ***svabhāva***),
derived in [`02-no-aseity.md`](./02-no-aseity.md) [confidence: high that the corpus
reads L1 as conferral-dependence surviving the self-refutation that sinks "nothing
exists," not as nihilism].

### occasionalism (al-Ghazālī; per-operation tempo)

The doctrine that a thing does not carry its own persistence from one moment to the
next but is **continuously re-conferred**; the curation borrows exactly one feature
of it -- continuous re-conferral -- and *nothing else*. The tempo matters and is
fixed precisely: **per operation**, never "each instant." A verdict in EMET is
recomputed inside each command invocation and does not exist between invocations;
the next `verify` reads the bytes again and re-derives rather than reading back a
cached result. **Mapping status: load-bearing at the per-operation tempo**
(re-conferral-every-operation is the mechanism behind "no cache, no held key"); the
"each instant" reading is **illumination / lineage** only, and the curation does
not lean on it.
*Further reading (lineage, never warrant):* occasionalism (al-Ghazālī), with the
*kun fayakūn* motif of existence-as-utterance in the background, via L11 and the
Abstracts in `research/CATALOG.md`. The corpus
*itself* strikes the per-instant tempo as false to substrate (metabolic, not
per-instant) in `research/dissertation/membrane-through-line.md` §2 [confidence:
high -- this is the corpus's own stated correction, not a reading imputed to it];
the engineered per-operation case is derived in [`03-occasionalism.md`](./03-occasionalism.md).

### process over property (L11)

The law distinguishing two kinds of defense. A **property-defense** *terminates*:
once built, it holds by construction (content-addressed bytes cannot disagree with
their hash). A **perimeter-defense** does *not* terminate: it is re-enacted every
operation, paid continuously, and **persists by no construction** -- stop performing
it and it lapses. EMET's verdicts are the second kind: re-derived per operation
from public inputs, with no secret and no held key, so between operations the
verdict is genuinely absent (only the operator's anchor persists, and an anchor is
a fact to re-derive *against*, not a stored verdict). **Mapping status:
load-bearing** (recompute-every-call, store-no-verdict is the mechanism; a cached
verdict surviving between runs would refute it).
*Further reading (lineage, never warrant):* L11 in
`research/CATALOG.md`, read against `SPEC.md` §8 and
the `verify()` function in `membrane.py` in [`03-occasionalism.md`](./03-occasionalism.md).

### proper function (Millikan)

A **subjectless** notion of function and content: a mechanism has a *proper
function* -- a success-condition it was selected or built to track -- and its output
can be said to be *about* something and to *succeed or fail*, with **no subject,
no intention, no caring** required. In EMET's register one may say without strain
that a `verify` has a proper function (re-derive the bytes) and a `MATCH` is that
function discharged -- and that is *all* one is entitled to say: functional content,
not authored purpose. **Vocabulary** (the term fixes exactly what is conceded -- see
**teleosemantic deflationism**).
*Further reading (lineage, never warrant):* Millikan's teleosemantics (proper-
function content without a subject), via `research/dissertation/part-IV-meaning-closure.md`
§§4–5 [confidence: high that the corpus *concedes* the whole functional-content
domain to Millikan on purpose; the concession is a deliberate dialectical move, not
a contested inference].

### residual structural aseity

The honest remainder the curation refuses to hide: the *small, irreducible* sense
in which EMET still rests on *something* -- an uncompromised substrate and an
external verifier of record -- that it cannot itself authenticate. The term names
why "no-aseity" is applied *reflexively and completely*: EMET is not its own root
of trust precisely because a compromised substrate would re-derive a compromised
self-hash consistently, so whatever standing EMET has is held *from another*, never
from itself. **Mapping status: load-bearing** (it is the reflexive application of
L1 that forces the external check of record).
*Further reading (lineage, never warrant):* `SPEC.md` §11 (trust-root regress) and
L10 (trust–attack duality: self-agreement carries zero independent weight) in
`research/CATALOG.md`, derived in
[`05-authored-root.md`](./05-authored-root.md).

### the authored stop (L14)

The principle governing *when an argument ends*: "enough" is **spoken, not
discovered** -- there is no objective seam-count that certifies completion. The
discipline cuts both ways: rigor demands examining what is actually *brought*
(stopping early out of cowardice is a failure), but it forbids *manufacturing*
reasons never to conclude (compulsive padding is the opposite failure). A section
ends at the seam that *returns carrying nothing new*. In this curation it is the
rule against padding: an essay or entry stops when it has derived its claim,
answered its objection, and stated its refuter -- not before, and not after.
**Vocabulary** (a methodological commitment, applied to the curation's own prose).
*Further reading (lineage, never warrant):* L14 in
`research/CATALOG.md`.

### the spoken-*for* (L2)

The law that **purpose/authorization is authored** and cannot be read off any
capability or substrate: "the *for* is in the tending, never in the seed." The
seed (a capability, an abstraction) is totipotent and silent about what it is
*for*; the *for* arrives only when someone takes a position and authors it. The
standard worry -- Sartrean arbitrariness, "if the *for* is merely authored it is
merely willed" -- is answered by noting that conferral is *re-speaking from a
thrown, answerable position*, not minting *ex nihilo*: the operator authors the
*for* under constraint, and EMET authors none at all. **Mapping status:
load-bearing** (it forces *advisory* and *zero actuation*; a command that took a
content or safety decision as input would author a *for* into the seed).
*Further reading (lineage, never warrant):* L2 in
`research/CATALOG.md`, with the *kun fayakūn* motif
(existence as authored utterance); on conferred-yet-not-arbitrary standing, Susan
Wolf and Thaddeus Metz are the lineage [confidence: *moderate* on the Sartrean
"merely willed" framing as a faithful statement of the objection -- it is a
reconstruction the essay answers, not a quotation]. Derived in
[`04-spoken-for.md`](./04-spoken-for.md).

### *svabhāva*

A Sanskrit term from Madhyamaka Buddhist philosophy for **intrinsic, independent
own-being** -- the self-standing essence a thing would have if it existed on its own
footing. The Madhyamaka claim (and the corpus's foundational reading) is that
nothing has *svabhāva*: all things are *empty* of intrinsic existence, existing
only dependently. In the curation it is the precise name for what *trust* lacks:
trust has no *svabhāva*, no own-being to be read off a signal -- which is why the
verdict lattice cannot emit `TRUSTED`. **Vocabulary** (it sharpens **no-aseity**;
it is not a separate mapping).
*Further reading (lineage, never warrant):* Nāgārjuna's account of emptiness
(*śūnyatā*) and the absence of *svabhāva*, and Westerhoff's reconstruction (*The
Non-Existence of the Real World*), via L1 in
`research/CATALOG.md` [confidence: *moderate* on the
gloss of *svabhāva* as "intrinsic own-being" -- it is a standard but interpretively
loaded rendering of a contested term].

### teleosemantic deflationism

The exact register EMET runs in: **concede the entire domain of functional /
semantic meaning** (see **proper function**) -- grant that a verdict has a function,
is *about* bytes, and *succeeds or fails* -- and **deny only existential *for*-ness**:
the authored purpose, the mattering, the will-toward-a-referent. "Deflationism"
because it deflates "meaning" to subjectless proper-function and claims nothing
above it; the concession is *generous on purpose*, because the strength of the
is/ought thesis depends on giving away everything except the authored *ought*.
EMET claims exactly the functional content it has (the byte re-derived) and nothing
about permission, because permission is *for*-ness, and *for*-ness is authored.
**Mapping status: load-bearing** (the concede-the-function / deny-the-*for* split is
what lets EMET run honestly without smuggling intention into its verdicts).
*Further reading (lineage, never warrant):* `research/dissertation/part-IV-meaning-closure.md`
§§4–5, which concedes the whole functional domain to Millikan and denies only
existential *for*-ness [confidence: high that this is the dissertation's deliberate
position]. The frame is introduced in [`00-orientation.md`](./00-orientation.md) and
used in [`01-is-ought-seam.md`](./01-is-ought-seam.md).

---

### A note on the provenance pointers themselves

Each *Further reading* line points into `research/` (or to a named thinker) as
**lineage** -- where an idea was worked, who is associated with it -- and never as
**warrant**. This is not a stylistic tic; it is the thesis of the project applied
to its own glossary. A glossary that defined EMET's terms *by the corpus's
authority* -- "this means X because the thesis says so" -- would commit exactly the
in-band-authority error that `refuse` exists to strip, and would refute itself in
the act of defining. So the definitions stand on their own statements, usable by a
reader who never opens a single linked file; the pointers are there for the reader
who wants to see the argument at length, and for no other reason. The glossary's
standing, like everything else in the curation, is conferred and re-derivable -- not
aseitic.

---

*Siblings:* [`00-orientation.md`](./00-orientation.md) ·
[`01-is-ought-seam.md`](./01-is-ought-seam.md) ·
[`02-no-aseity.md`](./02-no-aseity.md) ·
[`03-occasionalism.md`](./03-occasionalism.md) ·
[`04-spoken-for.md`](./04-spoken-for.md) ·
[`05-authored-root.md`](./05-authored-root.md) ·
[`06-aleph.md`](./06-aleph.md) ·
[`07-walkthrough.md`](./07-walkthrough.md) ·
[`08-taxonomy.md`](./08-taxonomy.md) ·
[`INDEX.md`](./INDEX.md)
