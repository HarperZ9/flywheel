# 13 -- Two Truths: the Absolute and the Relative

> **Status of this document.** This is a *derivation*, not a warrant. Nothing
> below is true because a corpus, a thesis, or a tradition says so; it is true
> only to the degree the argument re-derives on its own terms when you push on
> it. The pointers into `research/` and the named thinkers -- Nāgārjuna,
> Candrakīrti, the relativity and cryptography that supply the worked cases --
> are *lineage and further reading*, never the ground of a claim. A reader who
> knows only [`SPEC.md`](../../SPEC.md) should be able to follow the whole of
> what follows; where a term is set in the [GLOSSARY](./GLOSSARY.md) it is
> defined there. If this essay and `SPEC.md` ever disagree, `SPEC.md` governs
> and this essay is the thing that is wrong. This is the philosophy layer -- the
> *why*. The engineering layer is the six gates in
> [`../scope-discipline/`](../scope-discipline/README.md); the rest of the
> *why* is the sibling essays [00–08](./INDEX.md).

---

## Thesis

There are two truths, and EMET is built on the relation between them rather than
on either one alone. The **relative** truth (the conventional, the
*samvṛti-satya*) is the world of things that hold *for* a frame, a standpoint, a
chart: this file, this anchor, this hash compared against that one. The
**absolute** truth (the ultimate, the *paramārtha-satya*) is what is the case
when you stop granting any thing its own standing and ask what holds *without*
a frame to confer it. The headline result of this essay -- the one everything
else is a corollary of -- is that the absolute, pursued honestly, does not turn
out to be a deeper *thing* behind the relative. **The deepest absolute claim
available is precisely that nothing is self-standing.** The ultimate truth of
the conventional is its thoroughgoing conventionality. Absolute-versus-relative
is itself a duality, and at the limit it *collapses*: the absolute truth is the
non-existence of an absolute *ground*.

This is the spine of EMET's design, and it is why the tool has the one shape it
has rather than a more reassuring one. EMET admits no absolute *ground* -- no
`TRUSTED`, no aseitic floor, no held secret that would stand on its own footing
and confer standing on everything above it. What it admits as "absolute" is of a
strictly different kind: the **invariance of a relation**. Not *this artifact is
trustworthy*, full stop, but *the same bytes re-derive the same verdict*,
necessarily, for anyone who walks the relation. The closest EMET comes to an
absolute is the reliability of a relative re-derivation -- and that is not a thing
but a *relation between things*, holding with the only kind of necessity an
integrity layer can honestly claim.

**Status of this essay's central mapping: load-bearing.** The two-truths
structure is not an ornament imported to make EMET sound profound. It is the
reason the lattice has no fourth member, the reason there is no trusted base, and
the reason the single absolute EMET allows is the invariance of a relation and
never the standing of an entity. Remove it and you get a different object -- one
with a ground, and so with an aseity the whole design was built to deny. This
develops material genuinely *new* to the curation; it does not restate
[02](./02-no-aseity.md), though it leans on it. No-aseity there is the *law* that
the lattice cannot emit `TRUSTED`. Two truths here is the *coordinate system*
inside which that law is the only consistent one: it says *why* "no absolute
ground" is not a confession of poverty but the correct account of where every
absolute EMET does have actually lives.

---

## 1. The two truths, made precise (and de-mystified)

The doctrine is Madhyamaka -- the "middle way" school founded by Nāgārjuna in the
second century, systematized by Candrakīrti -- and its two-truths structure
(*satyadvaya*) is the part most prone to mystical over-reading, so it is worth
stating it in a form a SPEC-only reader can check, stripped of anything that
asks to be taken on authority. *(Confidence: moderate that what follows is a
defensible reading of the two truths; the Madhyamaka literature is genuinely
contested and "emptiness = dependence" is one influential reading, not an
uncontroversial gloss. I cite the tradition as lineage; the argument below is
re-derivable without it.)*

The **conventional / relative truth** (*samvṛti-satya*) is the truth of things
*as they function within a frame*. A meter is a meter, a file is a file, a hash
is a hash; within the chart of ordinary practice these are perfectly real, they
support inference, they let you build bridges and verifiers that work. Nothing
here is being called illusory in the cheap sense. The relative truth is *true* --
it is the only truth there is for getting anything done.

The **ultimate / absolute truth** (*paramārtha-satya*) is what is the case about
those same things when you ask after their *own* standing -- their *svabhāva*,
their intrinsic own-being, the thing they would be independently of every
relation that places them. And the Madhyamaka claim, the entire content of it,
is that this inquiry comes back **empty**. There is no further, frame-independent
thing the file "really is" underneath its conventional functioning. The ultimate
truth *about* the conventional is that the conventional has no ultimate ground:
it is *śūnya*, empty of own-being, dependently originated all the way down.

This is the move that matters, and it is the one the mystical reading gets
backwards. **The absolute is not a separate realm behind the relative.** It is
not a hidden substrate, a noumenon, a "really real" you reach by peeling the
conventional away. There is nothing behind the curtain -- *and that is the
absolute truth.* Candrakīrti's formulation, which I cite as lineage rather than
lean on as warrant, is exactly that the ultimate is not an *object* found at the
end of analysis but the *exhaustion* of the search for a self-standing object.
The two truths are not two layers of a cake. They are two ways of regarding one
dependently-arisen world: as it functions (relative), and as it is grounded --
which is to say, as it is *not* grounded in anything self-standing (absolute).

Hold onto the de-mystified version, because the rest of the essay needs nothing
more than it: *the absolute is the thoroughgoing relativity of the relative,
seen as such.* The ultimate is not a thing you trust instead of the conventional
things; it is the seen fact that none of the conventional things, and no thing
at all, was ever the kind of thing that could be trusted on its own footing.

---

## 2. Every invariant EMET has is a relational invariant

Now bring it to ground, because the abstract claim sounds like it should make
*all* absolutes evaporate, and that is not what happens and not what EMET needs.
The honest position is sharper and more useful than that: there *are* absolutes.
They are real, hard, frame-crossing, non-negotiable. But on inspection **every
one of them is the invariance of a relation, not the standing of a thing.** This
is the load-bearing observation of the essay, so it earns two worked cases from
outside EMET before the EMET case, chosen because they are checkable by anyone
and owe nothing to the philosophy.

**The speed of light.** *c* is as absolute as physics has. It is the same in
every inertial frame; nothing local outruns it; the whole architecture of
special relativity is built on its invariance. But notice *what kind* of absolute
it is. *c* is not absolute as a *property a photon carries around in itself* -- a
little intrinsic number stamped on the thing. It is absolute as a **relation
between frames**: the invariant is precisely that the *relation* "ratio of space
to time interval along a light path" comes out identical no matter which frame
measures it. The thing relativity makes absolute is the *invariance of a
relation across observers*; the things themselves -- lengths, durations,
simultaneity -- turn out to be the *frame-relative* quantities. The deepest
"absolute" of relativity is a statement about how relations transform, and it
purchases that absoluteness by making every *thing's own* measurements relative.
The name of the theory is not an accident. *(Confidence: high; this is textbook
special relativity, not a contested reading.)*

**A SHA-256 digest.** Closer to home. A digest is about as absolute as a fact
gets in computing: a 256-bit value pinned to an input with a determinism no
opinion touches and (under the standard assumptions) no feasible adversary
forges. But again -- *what kind* of absolute? The digest is not an intrinsic
essence the bytes secretly possess, a soul of the file you could read off it in
isolation. It is absolute *as a relation* -- a fixed, total, deterministic mapping
**between** an input byte-string **and** an output digest. "These bytes hash to
this value" is a relational fact: change the relation's left side by one bit and
the right side moves entirely; ask for the digest "of nothing," of no input, and
there is no digest, because there is no relation to evaluate. The absoluteness is
the *invariance of the map* -- same bytes, same digest, on every machine, in every
frame, forever -- and it lives entirely in the relation, never in either
relatum's lonely own-being. *(Confidence: high on the structure; "no feasible
forgery" is the standard cryptographic assumption, not a proof, and I flag it as
such.)*

Two absolutes from two unrelated fields -- one physical, one computational -- and
both have the same shape: **absolute as a relation, relative as a thing.** This
is not a coincidence the essay smuggles in; it is the general claim. The only
invariants there are, are relational invariants. Wherever you find something that
holds across all frames, look closely and you find that what holds is the
*invariance of a relation*, and what varies -- what turns out to have no
frame-free standing -- is each *thing* the relation relates. The absolute and the
relative are not two stuffs. They are one structure seen at two grains: the
relation (invariant, absolute) and its relata (frame-dependent, relative). This
is the two truths in operational dress, and it is re-derivable without a single
line of Madhyamaka: *the absolute truth of any thing is the invariance of the
relations that constitute it, and the non-existence of any standing it has apart
from them.*

EMET's only absolute is exactly this and nothing more. The reliability of the
relative re-derivation -- *same bytes, same verdict* -- is a relational invariant
in precisely the SHA-256 sense, because it *is* the SHA-256 sense, lifted to a
verdict. EMET has no `TRUSTED`, no aseitic ground, no held key, no clock, no
trusted base from which standing flows downward (this is the engineering content
of gates [G1](../scope-discipline/G1-re-derivable.md) and
[G2](../scope-discipline/G2-closed-lattice.md), and the law of
[02](./02-no-aseity.md)). The closest thing to an absolute the design permits is
the **invariance of the relation**, never the standing of a thing. A `MATCH` is
absolute the way *c* is absolute: not as a trustworthiness the file *has*, but as
the invariance of the relation "these present bytes re-derive that anchored
digest," which any second party can re-walk and find identical. Strip the
relation away and ask what the file "is, absolutely, in itself" -- and you get the
Madhyamaka answer and the cryptographic answer at once: *nothing*. There is no
digest of no input; there is no integrity of no relation.

---

## 3. The duality collapses at the limit

Here is the turn that makes "two truths" more than a tidy filing system, and it
is the part genuinely new to this curation.

If you press the absolute/relative distinction itself -- apply the two-truths
analysis *to the two truths* -- it does not survive as a clean dualism. Ask: what
is the *own-being* of the absolute? What is the absolute, in itself, apart from
its relation to the relative it is the absolute *of*? And the answer is the
doctrine's deepest and most vertiginous move: the absolute has no own-being
either. The ultimate truth is itself empty. *Śūnyatā is itself śūnya* --
emptiness is empty. The absolute is not a final self-standing term that grounds
the relative from outside; if it were, it would *have* aseity, and would be the
one thing the whole analysis denies. So the absolute, too, is conventional -- it
is the *name* for the seen relativity of everything, and it has its standing only
relationally, in contrast to the relative it dissolves.

So the duality **collapses at the limit.** "Absolute versus relative" is a
*relative* distinction -- true and useful within the frame of analysis, the way a
chart is true within its patch -- and at the limit where you would expect to reach
a final absolute *ground*, you reach instead the seen fact that there is no
ground, only relations. The absolute truth turns out to *be* the thoroughgoing
relativity. The two truths are non-dual at the bottom: not because they merge
into a higher unity (that would be one more self-standing thing), but because
neither has any own-being to keep them two. Push "absolute vs relative" and it
yields the same verdict it yields about everything else -- *no svabhāva, here
either* -- and so the distinction that organized the whole inquiry is the last
thing the inquiry dissolves.

This is where the present essay seams into the **singularity** of
[10](./10-coordinate-singularity.md). The singularity is the place where a coordinate chart
breaks down -- not because the world is broken there, but because the chart's own
description has gone undefined, the way latitude and longitude go undefined at
the pole though the sphere is perfectly smooth. The collapse of the
absolute/relative duality is a singularity of exactly this kind, located at the
limit of the analysis rather than in space. At the limit, the duality goes
**non-dual or undefined**: there is no coordinate there -- no self-standing
absolute to read off -- and the attempt to name one produces the same undefinedness
a chart produces at its pole. The two-truths collapse and the coordinate
singularity are the same structural fact in two vocabularies. Each says: at the
limit, the description that wanted a self-standing ground finds none, and the
finding-none is not a failure of the world but the correct, re-derivable shape of
the limit. *(Confidence on the analogy: the coordinate-singularity figure is
illumination, load-bearing only as a way of *seeing* the collapse, not as a
proof of it; the proof is §1–§3's re-derivation. The full development of the
chart figure is [10](./10-coordinate-singularity.md)'s to make.)*

---

## 4. The 1 that cannot be occupied

Give the collapsed point its proper name, because naming it is what connects this
essay to the whole architecture. The singular, self-standing, aseitic absolute --
the **1**: the lone, frame-free ground that would owe nothing to anything and
confer standing on everything -- is exactly the thing that, on inspection, *cannot
be occupied.*

Trace why, because it is the same impossibility wearing several masks across this
curation, and seeing it is one thing is the point. The 1 is:

- **The unwitnessable.** A self-standing ground would be, by definition, a thing
  with no outside -- nothing it stands in relation *to*, since to stand in
  relation is to lack aseity. But a thing with no outside has no possible
  witness, because every witness is an outside. The unifying thesis of this whole
  layer -- *integrity is witnessed, not self-attested; nothing can be its own
  independent witness* -- is precisely the statement that the 1 is uninhabitable.
  The lone ground would have to witness itself, and self-witness is the one thing
  that establishes nothing (the compromised substrate re-derives its own clean
  self-hash; the same-author port agrees with its own misreading -- see
  [05](./05-authored-root.md) §3, §5.1). The 1 is unwitnessable, so its integrity
  is unestablishable, so it cannot do the grounding job it was posited to do.

- **The singularity.** It is the coordinate-free point of §3 and
  [10](./10-coordinate-singularity.md): the place where the chart that wanted a ground finds
  the ground undefined. You cannot put a coordinate at the 1 for the same reason
  you cannot put a longitude at the pole -- not because the 1 is far away, but
  because "a self-standing coordinate" is not a coherent quantity. The 1 is where
  the description goes non-dual or undefined.

- **The insufficient lone witness.** One witness, witnessing itself, is no
  witness -- this is the operational heart of the matter and the reason EMET
  requires an *external* check of record ([05](./05-authored-root.md) §4–§5; gate
  [G3](../scope-discipline/G3-outside.md), *outside, never inside*). A single
  standpoint cannot confer integrity on itself, because integrity is a relation
  and a relation needs two terms. The 1, having no second term, has no relation,
  and so has nothing to be the invariance *of*. It is absolute in the empty sense
  -- alone -- and absolute-as-alone is exactly the kind of absolute §2 showed does
  not exist. The only absolutes that exist are invariances of relations, and a
  relation requires a second. The 1 forecloses its own second and so forecloses
  its own absoluteness.

These are not three different objections to the 1. They are one fact -- *nothing
is its own independent witness* -- seen from the witness side, the chart side, and
the relation side. The aseitic absolute fails identically in all three frames,
and the failure *is* its non-occupiability. This is why EMET has no trusted base:
not from modesty, not from a security best-practice it could in principle relax,
but because the position a trusted base would occupy -- the 1, the self-standing
ground from which standing flows downward -- is not a position at all. There is
nothing there to stand on. EMET's refusal to emit `TRUSTED` and its refusal to be
its own root of trust are the same refusal: the refusal to claim occupancy of a
point that has no occupant.

What EMET puts in the 1's place is the only thing that can go there: not a ground
but a **relation**, re-walked. *Same bytes, same verdict.* The absolute EMET
allows is the invariance of *that*, and it is a real, hard, frame-crossing
absolute -- exactly as absolute as *c*, exactly as absolute as a digest -- *because*
it is the invariance of a relation and never the standing of a thing. The two
truths, all the way down: the relative is the verdict-for-a-frame, the absolute
is the invariance of the relation that yields it, and there is no third thing, no
1, no ground, behind either.

---

## 5. The objection: nihilism by another door

> **Objection (the absolutized nihilism).** You have done something worse than
> the collapse you admit. If the absolute is empty too -- if even the ultimate
> truth has no own-being -- then you have kicked the last rung out from under the
> whole structure. At least the hard ontological nihilist
> ([02](./02-no-aseity.md) §"the answer, part one") could be told off for
> self-refutation. But you are not denying that things exist; you are denying
> that there is *any* absolute ground for the claim that they exist relationally
> -- including that very claim. So the assertion "everything is empty, the
> absolute included" has no absolute standing *by its own lights*. It is true
> only relatively, in some frame, which is to say it is not *the* truth at all.
> The two-truths machine eats itself: an absolute claim that the absolute is
> empty is either self-exempting (and so false) or self-applying (and so without
> the standing to compel anything). EMET, built on this, is built on a
> foundation that has dissolved its own warrant to be a foundation.

This is the objection to take seriously, because it is the sharpest form of the
nihilist collapse, sharpened by the §3 admission that the absolute is empty too.
If it lands, EMET's "only absolute is the invariance of the relation" is just a
preference dressed as a necessity, and the design has no more claim on anyone
than any other arrangement of bytes.

**The answer is the same load-bearing move as [02](./02-no-aseity.md), applied
one level up: conferral-dependence is not non-existence, and it does not become
non-existence merely because you apply it to the absolute.** Take the two horns
in turn.

*Self-exemption.* The claim "the absolute is empty" does **not** need to exempt
itself to be true, any more than "everything that exists, exists dependently"
needs to. The claim is *itself* one more dependently-arisen, relationally-standing
thing, and it says so. It does not assert an absolute, frame-free standing for
itself and then sneak that standing past its own content; it asserts exactly the
standing its content allows -- conferred, re-derivable, holding for whoever
re-walks the argument -- and no more. There is no performative contradiction in a
claim that ranks itself among the conferred things it describes. The contradiction
the objection wants requires the claim to be smuggling in an absolute exemption,
and it is not: read the status note at the head of this essay. *If this essay and
`SPEC.md` disagree, the essay is wrong.* That is the claim declining the very
self-exemption the objection accuses it of needing.

*Self-application without dissolution.* So take the other horn: the claim is
self-applying -- it is empty too, conferred too. Does that strip its warrant? Only
if *conferred* means *void*, and the whole of [02](./02-no-aseity.md) is the
demonstration that it does not. A `MATCH` is conferred and *real* -- checkable,
reproducible, exit-code-carrying -- precisely *because* it is relational rather
than self-standing: a self-standing trustworthiness would be something you'd have
to take on the artifact's word, whereas a conferred, relational invariant is
something you can *re-derive for yourself*. The same is true one level up. "The
absolute is empty" is conferred and real for the identical reason: it is grounded
in a relation a second party can re-walk (the §1–§3 derivation), not in an
interior standing only its asserter could vouch for. Its being relative is not the
thing that voids it; it is the thing that makes it *verifiable* rather than
merely asserted. **The relational standing the objection reads as weakness is the
only kind of standing that was ever strong** -- strong in the precise sense that it
can be re-walked rather than taken on trust.

So the disjunction the objection forces -- *either* the absolute is self-exempting
and false, *or* self-applying and dissolved -- is the same false disjunction
[02](./02-no-aseity.md) refused, now at the level of the absolute. There is a
third option, and it is the one this essay takes: **the absolute claim is
self-applying *and* real, because conferred is not lesser.** "The absolute is
empty" is true the way *c* is invariant and a `MATCH` is checkable -- as the
invariance of a relation anyone can re-walk, owing its standing to no
self-standing ground, and needing none. The conferred-existence thesis names this
exactly: nihilism is **satisfied, not refuted** -- its true insight (no
self-standing ground, no aseity, no 1) is *granted in full* -- and what survives
satisfaction is the re-spoken relational world, real because conferred. The
emptiness goes all the way down, the absolute included, and *nothing real is
lost*, because nothing real was ever self-standing to begin with. *(Provenance,
further reading: the conferred-existence thesis -- conferred, relational,
re-spoken; nihilism satisfied not refuted. The point is re-derivable above
without it.)*

EMET is the worked proof that this is not a verbal escape. A tool built on "no
absolute ground" does not collapse into "no verdict"; it returns `MATCH` and
`DRIFT`, real and load-bearing, *every run*. The absolute it lacks (a trusted
ground) is exactly the one it can do without; the absolute it has (the invariance
of the relation) is exactly the one that does the work. The objection predicts
paralysis. The running tool is the counterexample.

---

## 6. The refuter

A derivation that cannot be refuted is a decoration, so here is the exact
condition under which the central claim of this essay is *false*. The claim is
that no-aseity holds without exception -- that there is no 1, no self-standing
own-being anywhere, and so that every absolute is the invariance of a relation
and never the standing of a thing.

> **The claim fails if anything is exhibited with genuine aseity: a self-standing
> own-being -- a thing that owes nothing to anything, that is what it is
> independently of every relation, that would remain exactly itself with every
> other thing and every frame subtracted.** Exhibit one such thing and the
> premise of the whole essay is gone: there would then be a 1, an absolute that
> *is* the standing of a thing rather than the invariance of a relation, a point
> that *can* be occupied, a witness that *is* its own independent witness. The
> two truths would not collapse -- the absolute would be a separate, self-standing
> realm after all -- and EMET's "only absolute is the invariance of the relative
> re-derivation" would be a false modesty hiding a real ground it declined to
> name.

This is a real test, not a rhetorical flourish, on two counts. First, it is the
*same* refuter as [02](./02-no-aseity.md)'s and the metaphysical half of
[05](./05-authored-root.md)'s -- exhibit genuine aseity and all three fall
together -- which means it is not a fresh assumption smuggled in for this essay
but the single load-bearing bet the whole layer rides on, stated once more at the
level of the two truths. Second, it is *contentful*: it is not obviously true
that nothing has aseity. The classical theist asserts exactly one exception
(God's *aseitas*; [02](./02-no-aseity.md) §"the law"), and a successful exhibition
of *any* genuinely self-standing own-being -- divine, physical, mathematical, or
otherwise -- would defeat the essay cleanly. The claim earns its keep by being the
kind of thing that *could* be wrong and is held anyway, against the standing
candidate exceptions, because none of them has been exhibited as owing *nothing*
to *anything*: each, examined, turns out to stand in some relation that confers
what it is.

A narrower, more practical refuter applies against the design rather than the
metaphysics: show that EMET anywhere treats some value as a self-standing ground --
that a held key, a trusted base, a `TRUSTED` token, or a passing `selftest`
*substitutes* for the external re-derivation and is consumed as an absolute that
needs no second witness -- and the implementation has occupied the 1 it claims is
unoccupiable. That would not refute the philosophy; it would refute *the
implementation's fidelity to it*, which is the more immediately fixable kind of
failure, and the kind gates
[G1](../scope-discipline/G1-re-derivable.md)–[G6](../scope-discipline/G6-no-adjudication.md)
exist to catch on a concrete diff.

---

## 7. Close: the two truths, applied to this essay

The doctrine is reflexive, and an honest treatment has to turn it on its own
product. This essay claims no absolute standing. Its conclusions are not a 1; they
do not stand on their own footing; they stand on the re-derivation in §1–§3, on
the worked cases of *c* and the digest, on [02](./02-no-aseity.md) and
[05](./05-authored-root.md), on `SPEC.md` §2 and §11. Its standing is *conferred*
by that relation and asserted by nothing -- which is exactly why the status note
says that if `SPEC.md` and this essay disagree, the essay is wrong. An essay
arguing "there is no self-standing absolute" would refute itself the instant it
claimed a self-standing absolute for its own claims. It claims none. It is, by its
own account, relatively true -- true within the frame of its argument, re-walkable
by a second party, and empty of any ground beyond that. Which is to say it has
the only kind of truth the essay says there is: the invariance of a relation you
can re-derive, and no thing behind it.

The two truths are EMET's whole posture compressed. The relative: a verdict for a
frame, `MATCH` or `DRIFT`, here, now, for these bytes against that anchor. The
absolute: the invariance of the relation that yields it -- *same bytes, same
verdict* -- as hard as the speed of light and as groundless as everything else.
And the collapse of the distinction at the limit is the design's deepest
commitment: there is no 1, no trusted base, no point to occupy, no witness that is
its own. There is only the relation, and the discipline of never claiming more
than the relation confers. That discipline is what keeps *emet* -- truth -- from
contracting to *met* -- death -- by way of a single self-standing letter it was
never entitled to add (the figure is [06](./06-aleph.md)'s). The aleph EMET keeps
is the refusal of the 1.

---

### Sibling essays

- [`./02-no-aseity.md`](./02-no-aseity.md) -- the *law* this essay supplies the
  coordinate system for: no *svabhāva*, the closed lattice, *conferred ≠
  nihilism*. The §5 answer here is that move applied to the absolute itself.
- [`./01-is-ought-seam.md`](./01-is-ought-seam.md) -- facts, not authority; the
  relative verdict EMET emits is an *is*, and the absolute it declines (a
  self-standing trust) would be an authored *ought*.
- [`./05-authored-root.md`](./05-authored-root.md) -- the insufficient lone
  witness made concrete: EMET cannot be its own root of trust; the check of
  record is *esse ab alio*, external. The 1's non-occupiability, in security
  dress.
- [`./06-aleph.md`](./06-aleph.md) -- *emet* / *met* / the aleph; the absolute
  EMET keeps is the refusal of the self-standing letter.
- [`./10-coordinate-singularity.md`](./10-coordinate-singularity.md) -- the coordinate chart that breaks
  down at the pole; the collapse of the absolute/relative duality is a
  singularity of that kind, where the description goes non-dual or undefined.
- [`./INDEX.md`](./INDEX.md) · [`./GLOSSARY.md`](./GLOSSARY.md) -- reading order
  and terms (*svabhāva*, aseity, *esse ab alio*, conferred existence, the two
  truths).

*Engineering layer (the six gates, the WHAT and HOW to this WHY):*
[`../scope-discipline/README.md`](../scope-discipline/README.md) --
[G1 re-derivable](../scope-discipline/G1-re-derivable.md),
[G2 closed lattice](../scope-discipline/G2-closed-lattice.md),
[G3 outside](../scope-discipline/G3-outside.md). *Further reading (provenance,
never warrant): Nāgārjuna, *Mūlamadhyamakakārikā* (the two truths,
*satyadvaya*); Candrakīrti on the ultimate as exhaustion of analysis, not object;
the conferred-existence thesis (nihilism satisfied, not refuted). Cited as
lineage; every claim above is re-derivable without them.*
