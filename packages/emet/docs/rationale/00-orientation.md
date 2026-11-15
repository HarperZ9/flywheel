# 00 -- Orientation: The Five Frames

> **Status of this document.** This is a *primer*, and like everything in this
> curation it is a derivation you are meant to *re-derive*, not a warrant you are
> meant to accept. Nothing below is true because a corpus, a thesis, a tradition,
> or a maintainer asserts it; it is offered as argument that either holds when you
> push on it or does not. Where it points to `research/`, it points there as
> *further reading* -- the lineage of an idea -- never as the reason to believe the
> idea. "Because the corpus says so" is, in this project, a defect, not a citation.
> If this primer and `SPEC.md` ever disagree, `SPEC.md` governs and this primer is
> wrong. It assumes no dissertation and no prior reading: a person who knows only
> `SPEC.md` (the closed verdict lattice, the six boundaries, re-derivability) should
> be able to follow the whole of it, and the terms it uses in italics are defined
> in [`./GLOSSARY.md`](./GLOSSARY.md).

---

## Why a primer at all

EMET is a small program with an unusually opinionated shape. It judges bytes and
emits exactly one of three verdicts -- `MATCH`, `DRIFT`, `UNVERIFIABLE` -- and it
refuses, structurally, to emit a fourth one meaning *trusted*. It will not edit,
sign, or revert a target. It will not take a model-safety question as input. It
insists it cannot be its own root of trust. To an engineer these look like
tasteful restraint: a careful tool, modestly scoped. They are not restraint. Each
is *forced* -- not chosen for elegance but driven by a specific argument, such that
relaxing it would change not how EMET behaves but **what EMET is**.

This document lays out the five frames those arguments stand on, plainly and
without the apparatus, so the numbered essays that follow can do the load-bearing
work without re-explaining their own foundations. A frame here is a posture toward
a question -- a way of seeing -- not yet the full derivation; the derivation lives in
the essay each frame points to. Read this once and the rest of the curation is a
sequence of consequences.

One discipline runs through all five and is worth stating before any of them: **the
warrant is the argument, never the source.** A rationale that justified EMET's
no-authority design *by appeal to the corpus's authority* would refute itself -- it
would be doing in band the exact thing EMET's `refuse` command exists to strip out.
So every frame below is offered to be re-derived and, where it leans on a contested
philosophical position, the lean is **confidence-labelled** so you can weigh it
rather than swallow it.

---

## Frame 1 -- No-aseity: nothing stands on its own footing

*Aseity* (Latin *a se*, "from itself") is the property of existing entirely on
one's own footing, owing one's being to nothing else. The first frame is the denial
that anything in EMET's domain has it. Trust, in particular, has no *svabhāva* -- no
own-being, no intrinsic standing it carries in itself. To exist, on this view, is to
be *conferred*, relationally, by something other than oneself; nothing is its own
ground.

The engineering consequence is the closed verdict lattice (SPEC §2). Because trust
has no own-being, there is no fact about a signal that the signal possesses *by
itself* and that EMET could read off and report as `TRUSTED`. So the lattice has no
such inhabitant: it can report that a re-derivation agreed (`MATCH`), disagreed
(`DRIFT`), or could not be performed (`UNVERIFIABLE`), and it has no fourth thing to
say. The closure is not a coding-style preference; it is the type-level encoding of
no-aseity.

The objection this frame must survive is that it proves too much. **Objection:** if
nothing is self-standing, then nothing is trustworthy, and a verifier built on that
must collapse into "everything is `UNVERIFIABLE`" -- it would say nothing at all.
**Answer:** conferral-dependence is not non-existence. Hard nihilism ("nothing is
real") is self-refuting and is not what is claimed; no-*aseity* says only that what
is real is real *relationally*, conferred rather than self-grounded. A `MATCH` is
fully real -- and fully conferred, produced by an act of re-derivation against an
anchor the operator authorized. "No `TRUSTED`" is a claim about *which verdicts
exist*, not a claim that *no verdict is ever true*. The frame would be **refuted**
by any codepath that emitted a verdict outside the lattice, or any value that
asserted authority. (Provenance, *further reading only*: Nāgārjuna's emptiness and
the denial of *svabhāva*; Jan Westerhoff, *The Non-Existence of the Real World*;
Aquinas on *esse ab alio*, being-from-another. The Nāgārjuna and Westerhoff
readings here are *moderate*-confidence paraphrases of contested positions, given as
lineage; the argument stands on its own re-derivation, not on their authority. Full
derivation: [`./02-no-aseity.md`](./02-no-aseity.md).)

---

## Frame 2 -- The is/ought seam: authentication is a fact, authorization is authored

This is the headline frame, and the crux the whole curation turns on. Two utterly
different questions can be asked of a signal arriving at a boundary, and everything
depends on not confusing them.

The first is **authentication**: *is this the genuine, bit-intact thing it presents
itself as?* This is a question *about the signal*, answerable *off the signal* -- you
read the bytes, you hash them, you compare. It is, literally, a 1 or a 0: the bytes
re-derive the anchor or they do not. There is a fact of the matter.

The second is **authorization**: *ought this authentic signal cross?* May this
command act; may this file load; is admitting it the operator's uncoerced will,
*now*? And the pivot of the entire frame is that **this is not a property of the
signal.** No amount of inspecting bytes tells you whether they *should* be admitted,
because "should be admitted" is a fact about a will and a policy standing on the
*near* side of the boundary, not a fact carried across by the data. A signal can be
perfectly authentic and still be one that must be refused. The seam between the two
is the line EMET *locates* and refuses to launder across: it makes the
authentication-grade decision (`MATCH`/`DRIFT`/`UNVERIFIABLE`) and declines to
author the authorization. The verdict it emits is a *fact*; it is never an
*authority* -- that is Boundary 1 (SPEC §6.1), and `refuse` (SPEC §4) is the same
seam enforced where a signal tries to carry its own permission in band.

A precision this frame insists on, because skipping it is how the idea becomes
hand-waving: **the claim is not "this is Hume's guillotine."** A *policy-relative*
permission really is derivable from is-facts *plus* the further descriptive fact
that a policy is in force -- that is just Searle's *counts-as*. What the seam
instantiates is the weaker, more defensible **autonomy of the deontic** (Pigden's
reading of Hume's law): a valid inference introduces no new non-logical vocabulary,
so the deontic words -- *ought*, *may*, *permitted* -- must be *introduced* by a
premise that already contains them. That premise is authored, by the operator, at
the act of stipulating a policy; EMET supplies the descriptive premise and declines
to author the deontic one.

**Objection** (the hardest, from object-capability systems): *possessing the token
IS authorization* -- holding the unforgeable reference simply is being permitted, so
the is/ought split collapses. **Answer:** the seam does not vanish, it *relocates*.
A capability is a *materialized grant* -- an *ought* made bearer-portable, the frozen
record of a *prior* authored conferral at issuance. Presenting it redeems a
permission already conferred; it does not derive one from a bit-pattern. The seam
sits at issuance, not presentation. The frame would be **refuted** if a `MATCH` ever
entailed a permission with no authored policy in between -- if the verdict alone
licensed an action. (Provenance, *further reading only*: Hume's is/ought gap; Charles
Pigden on the autonomy of the deontic; John Searle on *counts-as*; Franz Brentano on
intentionality, *will-toward-a-referent*; the ABLP authentication calculus as nearest
security-side neighbour; Millikan, conceded -- see Frame 3. The "autonomy of the
deontic" reading is given at *moderate* confidence as the corpus's own correction of
an earlier overclaim. Full derivation: [`./01-is-ought-seam.md`](./01-is-ought-seam.md).)

---

## Frame 3 -- Teleosemantic deflationism: concede the function, deny the *for* (conceded, not fought)

This frame is unusual in being a **concession the curation makes on purpose**, not a
position it defends against an opponent. The temptation, when a system "checks" and
"verifies" and "refuses," is to read thick intention into it -- to think EMET *means*
its verdicts, *cares* whether the bytes match. The frame names exactly how much of
that reading to grant, so that what remains is sharp.

*Concede* the whole domain of **functional content**. Following Ruth Millikan's
teleosemantics -- proper-function content, no subject required -- there is a perfectly
good, subjectless sense in which a `verify` has a *proper function* (a
success-condition it was built to track) and a `MATCH` is that function discharged.
One may say without strain that the verdict *is about* the bytes, *represents* their
identity, *succeeds or fails at a function*. Grant all of it. This frame does not
fight teleosemantics; it *adopts* it as EMET's working register.

*Deny* only the **`for`-ness** -- the existential mattering, the authored purpose,
the will-toward-a-referent. EMET's verdict has a function; it does not have a *for*.
It does not author the purpose its output serves. That a `MATCH` *ought* to license
an action is never something the `MATCH` carries; it is conferred downstream, by an
operator, at the act of stipulating a policy. Conceding the function generously is
precisely what makes the denial of *for*-ness load-bearing rather than evasive: EMET
claims exactly the functional content it has and claims **nothing** about permission,
because permission is *for*-ness and *for*-ness is authored, not read off a
substrate. There is no separate objection-and-refuter to rehearse here, because the
frame is conceded ground -- it is the register in which Frames 2 and 5 do their work;
to state it and its boundary is to be done with it (a section ends when it returns
nothing new). (Provenance, *further reading only*: Ruth Millikan, *Language, Thought,
and Other Biological Categories*; the dissertation's part-IV meaning-closure argument,
which concedes the whole semantic/functional domain to Millikan and Dennett
deliberately to make the remaining claim -- the denial of existential *for*-ness --
sharp. That this is a *deliberate dialectical concession* is described in the source
at *high* confidence; I paraphrase the position rather than assert it. Most directly
in play in [`./01-is-ought-seam.md`](./01-is-ought-seam.md) and
[`./04-spoken-for.md`](./04-spoken-for.md).)

---

## Frame 4 -- Occasionalism: a verdict persists by no construction, re-conferred per operation

The fourth frame is about *tempo*. A verdict in EMET persists by no construction.
There is no stored "this file is good" that a later run reads back, no trust object
that, once minted, sits accruing standing. Each time you ask EMET whether an
artifact still matches what the operator anchored, EMET **re-derives** the answer
from the artifact's present raw bytes, the spec it implements, and -- for
marker-dependent output only -- the corpus version, and from nothing else. No secret,
no held key, no clock in the byte-hash core. The verdict is recomputed **per
operation**, and between operations it does not exist.

The corpus borrows the name *occasionalism* -- from al-Ghazālī, the doctrine that a
thing does not carry its own persistence from one moment to the next but is
re-conferred -- for exactly this feature: continuous re-conferral. A defense that
holds only while it is being performed is occasionalist in precisely that sense.
This frame is what makes EMET's re-derivability (SPEC §5, §8) a *philosophical*
commitment and not merely a caching choice: the verdict is a **process** maintained
per operation, never a **property** held between them.

A crucial precision, and the place a careless statement of this frame goes wrong:
the tempo is **per operation, never "each instant."** The corpus's own correction
strikes "re-spoken each instant" as false to any biological substrate, where a
membrane plainly holds across many spikes between metabolic re-enactments. EMET is
the clean *engineered* case where per-**operation** re-conferral is *literally
exact*: there is no instant-by-instant story to get wrong, because re-derivation
happens once, on demand, per `verify`. State it at that tempo and nowhere looser.
The frame is reinforced by a second, intrinsic move: the identity it re-derives is
the SHA-256 of the artifact's *exact raw bytes* (SPEC §3) -- the name *is* the hash --
so the check is not *about* the thing but *is* the thing, read again. **Objection**
(the substrate-tempo correction): "re-spoken each instant" is simply false, so the
analogy is broken. **Answer:** concede the biological tempo entirely; EMET is not
that case -- it is the engineered one where per-operation re-conferral is the literal
mechanism, nothing cached, no held key. The frame is **refuted** by any
normalization before hashing (a CRLF or encoding rewrite makes identity *extrinsic*
and breaks re-derivation), or by any verdict that survived, cached, between runs.
(Provenance, *further reading only*: al-Ghazālī on occasionalism, with *kun fayakūn*
-- existence-as-utterance -- in the background; content-addressing and Merkle trees
for "the name is the hash." The occasionalism reading is *moderate*-confidence as a
paraphrase of a contested theological position, borrowed for one feature only.
Full derivation: [`./03-occasionalism.md`](./03-occasionalism.md).)

---

## Frame 5 -- The spoken-*for*: purpose is authored, never read off the substrate

The last frame is the one that holds the others together: **a purpose is in the
tending, never in the seed.** The *for* of a thing -- what it is *for*, what it is
*meant* to do -- is not a property latent in its substrate waiting to be read off; it
is conferred, authored, by something that takes the thing up and directs it. A seed
has no *for* of its own; the tending supplies it. Maximum generativity and minimum
intrinsic *for* are the same condition seen twice: the more direction-neutral a
thing is, the less *for* it carries on its own, and the more its purpose must be
authored downstream.

EMET is built to be exactly such a seed. It performs *zero actuation* (SPEC §6.6):
it does not edit, write, sign, back up, or revert a target -- the single actuator is
the operator. Its "for" is left *undecided by design*. EMET authors no purpose into
the artifacts it judges; it hands the operator a clean *is* and the operator authors
the *ought*, the use, the *for*. This is why EMET is standardizable and non-rival in
a way an opinionated tool could not be: it carries almost no *for*, so almost any
operator's *for* can be authored on top of it without conflict.

**Objection** (Sartrean arbitrariness): if the *for* is merely authored, then it is
merely *willed* -- conjured arbitrarily, ungrounded, *ex nihilo*. **Answer:**
conferral is not arbitrary minting. To author a *for* is to *re-speak* from a
thrown, answerable position -- under constraint, accountable to a referent -- not to
invent value from nowhere. The operator authors the *for* under constraint; EMET
authors none at all. (That conferral can be non-arbitrary without being aseitic is
the Wolf/Metz move on meaning: conferred, yet answerable.) The frame is **refuted**
by any command that took a model-safety or content decision as input (SPEC §6.2):
the moment EMET answered a "should this be allowed" question, it would have authored
a *for* into the seed it is built to keep empty. (Provenance, *further reading only*:
the seed/tending figure of authored purpose; *kun fayakūn*, existence-as-authored-
utterance; Susan Wolf and Thaddeus Metz on meaning as conferred-yet-not-arbitrary;
catalogued as L2, the spoken-*for*, and L3, direction-neutral generativity. The
"conferred yet not arbitrary" reading is given at *moderate* confidence. Full
derivation: [`./04-spoken-for.md`](./04-spoken-for.md).)

---

## How the five frames fit

The frames are not five separate doctrines; they are one posture seen from five
angles, and it is worth seeing the joints before moving on.

No-aseity (Frame 1) says nothing stands on its own footing -- which is *why* trust
must be conferred and the lattice cannot emit it. The is/ought seam (Frame 2) says
the conferral in question, *authorization*, is an authored act that cannot be read
off a signal -- which is *why* an authentication fact must never launder into a
permission. Teleosemantic deflationism (Frame 3) is the register that lets EMET
concede everything functional and still deny the one thing -- existential *for*-ness --
that would let a fact become an authority. Occasionalism (Frame 4) says the
conferral is not done once and stored but re-enacted *per operation* -- which is *why*
re-derivability, not a cached trust object, is the mechanism. And the spoken-*for*
(Frame 5) names the conferring act itself: the *for* is authored in the tending,
which is *why* EMET stays a seed and leaves the actuation, and the purpose, to the
operator.

Read in that order, the curation is a single argument: because nothing is
self-standing (1), authorization must be authored across a seam EMET locates and
will not launder (2); EMET runs honestly in the deflated functional register that
concedes function and denies *for* (3); it maintains its verdicts as a re-conferred
process rather than a held property (4); and it leaves the *for* -- the purpose, the
permission, the action -- to be authored downstream by the one actuator there is (5).

A closing note in the frames' own spirit. This primer's standing is itself
conferred, not aseitic: it has exactly the authority its arguments earn when you
re-derive them, and not one increment more. If a frame holds when you push on it, it
stands; if it does not, no provenance and no "highest scrutiny" rescues it -- and a
claim of that kind, asserted in band to compel belief, is the very in-band authority
EMET's `refuse` exists to strip. The frames are offered. Their acceptance is yours
to author, or to withhold.

---

*Further reading (lineage, never warrant): `SPEC.md` §§2, 3, 4, 5, 6, 8;
`research/CATALOG.md` (Laws L1, L2, L3, L6, L8, L11); `research/dissertation/`
(`MEMBRANE-ERRATA.md`, `membrane-through-line.md`, `part-IV-meaning-closure.md`).
The numbered essays: [`./01-is-ought-seam.md`](./01-is-ought-seam.md),
[`./02-no-aseity.md`](./02-no-aseity.md), [`./03-occasionalism.md`](./03-occasionalism.md),
[`./04-spoken-for.md`](./04-spoken-for.md), [`./05-authored-root.md`](./05-authored-root.md),
[`./06-aleph.md`](./06-aleph.md), [`./08-taxonomy.md`](./08-taxonomy.md). Terms:
[`./GLOSSARY.md`](./GLOSSARY.md).*
