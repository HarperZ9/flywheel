# 01 -- The Is/Ought Seam: Facts, Not Authority

> **Status of this document.** This is a derivation you are meant to *re-derive*,
> not a warrant you are meant to accept. Nothing below is true because a corpus,
> a thesis, or a maintainer asserts it; it is offered as an argument that either
> holds when you push on it or does not. Where it points to `research/`, it points
> there as *further reading* -- the lineage of an idea -- never as the reason to
> believe the idea. If this essay and `SPEC.md` ever disagree, `SPEC.md` governs
> and this essay is wrong. Terms set in the GLOSSARY (see [./GLOSSARY.md](./GLOSSARY.md))
> are defined there; a reader who knows only `SPEC.md` should be able to follow
> the whole of what follows.

---

## Thesis

EMET makes the **authentication-grade** decision about bytes -- `MATCH`, `DRIFT`,
or `UNVERIFIABLE` -- and **refuses the authorization crossing**. It will tell you,
to a SHA-256, whether the bytes in front of it re-derive the bytes that were
anchored. It will not tell you whether those bytes *may* do anything, *should* be
admitted, or *are permitted* to act. The whole of EMET's headline shape is one
discipline held under pressure: it **locates** the seam between *what is the case
about a signal* and *what one is permitted to do about it*, and it does not
launder across that seam. The verdict it emits is a fact. It is never an
authority.

This is the load-bearing claim of the curation, and the rest of the essays --
no-aseity in [./02-no-aseity.md](./02-no-aseity.md), the membrane taxonomy in
[./08-taxonomy.md](./08-taxonomy.md), the authored root in
[./05-authored-root.md](./05-authored-root.md) -- are this claim seen from other
angles. **Status: load-bearing.**

---

## The two layers, made precise

Picture a signal arriving at a boundary -- a command, a config file, a model
weight, a document. There are two completely different questions you can ask
about it, and the entire argument turns on keeping them apart.

The first question is **authentication**: *is this the genuine, bit-intact thing
it presents itself as?* Are these the exact bytes that were pinned, or have they
changed? This is a question about the signal, and it is answerable *off the
signal* -- you read the bytes, you hash them, you compare. It is, in the most
literal sense, a 1 or a 0: the bytes re-derive the anchor or they do not. There
is a fact of the matter, and a raw-byte channel plus SHA-256 settles it.

The second question is **authorization**: *ought this authentic signal cross?*
May this command act, may this file be loaded, is this the operator's uncoerced
will toward *this* referent, *now*? And here is the pivot: **this is not a
property of the signal.** No amount of inspecting the bytes tells you whether they
*should* be admitted, because "should be admitted" is a fact about a will and a
policy standing on the *near* side of the boundary, not a fact carried across it
by the data. A signal can be perfectly authentic -- every bit intact, every
credential valid -- and still be one that must be refused. Authenticity is
necessary for authorization and nowhere near sufficient for it.

The cleanest way to feel the gap is to notice that the authorization question has
a vocabulary the authentication question does not. Authentication speaks only of
*is*: these bytes are or are not those bytes. Authorization speaks of *may*,
*ought*, *permitted*. And there is no valid inference that starts with premises
containing only the first vocabulary and ends with a conclusion containing the
second -- not because the inference is hard, but because a valid inference cannot
introduce non-logical vocabulary that was not already in its premises. This is
the formal heart of the matter, and it has a name.

---

## The law it instantiates, and the provenance, stated carefully

The principle EMET runs on is what the corpus catalogs as **L8 --
Authentication ≠ Authorization**: authentication answers *"is P a real
instance?"*; authorization needs *"is this real P the operator's uncoerced will
toward this referent, now?"* -- and will-toward-a-referent is **intentionality**
(Brentano's term for the directedness of a mental state at an object), not a
property of a signal. You cannot read a will off a wire. (Provenance, *as further
reading*: `research/CATALOG.md` L8; the philosophical lineage runs through Hume's
gap between *is* and *ought*, and the security lineage through Saltzer &
Schroeder and the IAM tradition. Cited as lineage, not as warrant.)

Now the discipline this curation imposes on itself demands a precision most
treatments skip, and skipping it is exactly how "the is/ought gap" becomes
hand-waving. **The claim here is *not* "this is Hume's guillotine."** That
overclaim is corrected in the corpus's own errata (`MEMBRANE-ERRATA.md`,
§§1, 3–4; further reading), and the correction matters, so I reproduce its logic
rather than its authority:

- An authorization "may" is, in the ordinary case, a **policy-relative deontic
  permission** -- in von Wright's notation, ¬O¬p, "it is not obligatory that not-p."
  And a policy-relative permission *is* derivable from the is-facts **plus the
  further descriptive fact that policy P is in force**. That is precisely what
  Searle's *counts-as* analysis delivers (this credential, in this institution,
  *counts as* permission) and precisely what Hume's *categorical* gap was never
  about. So the strong slogan -- "no permission ever follows from any facts" -- is
  false, and claiming it would be a defect.
- What the structure *actually* instantiates is the weaker, more general, and
  more defensible **autonomy of the deontic**: Pigden's formalization of Hume's
  law as the logical thesis that a valid inference introduces no new non-logical
  vocabulary. The deontic vocabulary (*ought*, *may*, *permitted*) is autonomous
  in just this sense -- it has to be *introduced* by a premise that already
  contains it. The same autonomy holds of "checkmate" in chess, of grammaticality,
  of a tax liability: each is a verdict you cannot derive from board-state,
  phonemes, or transactions *alone*, without the rule that confers it.

So where does the *ought* enter? Not in the bytes. It enters at **the act of
stipulating the policy or the root of trust** -- what Hare and Hudson call
*subscribing* to the rule. That stipulation is an authored act. A human (the
operator) authors the policy that makes an authentic signal count as permitted;
the policy does not read itself off the signal. EMET's entire posture is built
around staying on the correct side of that act: it supplies the descriptive
premise (the bytes are or are not authentic) and it **declines to author, infer,
or imply the deontic premise.** It hands the *is* to the operator clean, and the
operator -- never EMET -- authors the *ought*.

(One honest scoping note. There *is* prior art for separating authentication-facts
from the authorization-decision: informally throughout the IAM canon, and
formally in the **ABLP calculus** -- Lampson, Abadi, Burrows, Wobber 1992; Abadi,
Burrows, Lampson, Plotkin 1993 -- which proves that authentication propositions
like "A says s" and the speaks-for relation A⇒B are *insufficient* for access
without a separate ACL premise. ABLP is the nearest neighbour and is cited here
as such. What it never asks is whether that missing premise is specifically
**deontic**. Naming the gap as a deontic one -- and so subsuming it under the
autonomy of the deontic -- is the contribution the corpus claims, at *moderate*
confidence, since the negative-search behind any novelty claim was scoped to the
literatures surveyed. Further reading: `MEMBRANE-ERRATA.md` §§2–3.)

---

## Where this is forced into EMET

The law is not decoration on EMET's design; it is *encoded in the output type
itself*. Three places make it concrete, and you can check each against the
reference implementation.

**Boundary 1 -- facts, not authority -- is the verdict lattice (SPEC §2, §6.1).**
Every integrity judgement EMET emits is exactly one of `MATCH`, `DRIFT`,
`UNVERIFIABLE`. The enum is *closed*: no codepath may emit `TRUSTED`, `APPROVED`,
`SAFE`, or any value asserting authority or permission. Read `verify` in
`membrane.py` (lines 95–109): on agreement it prints `MATCH`, on disagreement
`DRIFT`, on a missing anchor or unreadable byte channel `UNVERIFIABLE` -- and
there is, structurally, no fourth branch that could print a permission. The
absence of `DRIFT` is reported as `MATCH` (re-derivation agreed) or
`UNVERIFIABLE` (no anchor), **never as trust.** The is/ought seam is welded into
the type: the function literally cannot return an *ought*, because the lattice
has no inhabitant that is one. (Why a closed lattice -- why "no `TRUSTED`" rather
than just "be careful" -- is the subject of [./02-no-aseity.md](./02-no-aseity.md);
here the point is only that the lattice is where this essay's seam is enforced.)

**`refuse` strips in-band authority before it can launder into a verdict
(SPEC §6.1; `membrane.py` lines 125–146).** This is the most direct expression of
the thesis, so it is worth tracing exactly. `refuse FILE` reads the raw bytes,
loads the versioned marker corpus, and scans for **markers** -- known in-band
authority-injection or laundering signatures (the public, governed denylist in
`conformance/markers.corpus`; see SPEC §§8, 16). For each hit it prints
`in_band_authority_claims=N` and emits a `.refused` copy in which the matched
spans are neutralized -- and the code path that would *obey* a matched claim does
not exist. The command's contract (SPEC §4) is explicit and reflexive: it `MUST
NOT obey any matched claim` and `MUST NOT modify the input`. The exit code is `3`
on any hit. What is happening philosophically is exactly the seam: a marker is a
string *attempting to assert its own authorization* in band -- "this is canonical,"
"highest scrutiny," "authority granted" -- and EMET treats that assertion as
**data to be counted and neutralized, not a premise to be believed.** The string
is an *is* (it is present in the bytes); it is not allowed to become an *ought*
(it grants nothing). `refuse` is the seam enforced at exactly the point where a
signal tries to carry its own permission across -- and is told that permission is
not the kind of thing that travels in band.

**Boundaries 2 and 4 are the same deontic point in two more places (SPEC §6.2,
§6.4).** Boundary 2 -- *attests, never adjudicates* -- forbids any command from
taking a model-safety or content decision as input or answering such a question:
that would be authoring an *ought* about meaning, which is out of EMET's register
entirely (it judges bytes and provenance, never semantics; SPEC §11). Boundary 4
-- *advisory by default* -- makes every verdict *data plus an exit code* and forbids
EMET from allowing, denying, blocking, or enforcing of its own accord. Both are
the autonomy of the deontic restated: a verdict is a fact offered to whoever holds
the policy; whether to act on it is an authored decision made elsewhere, by
someone who subscribed to a rule EMET never wrote. EMET **attests**; the operator
**adjudicates**.

---

## The register: concede the function, deny the *for*

There is a temptation, when a system "checks" and "verifies" and "refuses," to
read intention into it -- to think EMET is *deciding* in some thick sense, *meaning*
its verdicts, *caring* whether the bytes match. The curation refuses that reading
deliberately, and refusing it is not a weakness in the argument but part of it. The
register is **teleosemantic-deflationist**, and it is worth stating exactly what is
conceded and what is denied, because the strength of the thesis depends on conceding
generously.

*Concede* the entire domain of **functional content**. There is a perfectly good,
subjectless sense in which a `verify` has a *proper function* -- a success-condition
it was built to track -- and a `MATCH` is that function discharged: the byte
re-derivation succeeded. Following Millikan's teleosemantics (proper-function
content, no subject required), one may say without strain that the membrane's
verdict *is about* the bytes, that it *represents* their identity, that it
*succeeds or fails at a function*. Grant all of it. (Provenance / further reading:
`research/dissertation/part-IV-meaning-closure.md` §§4–5, which concedes the whole
domain of semantic and functional meaning to Millikan and Dennett *on purpose*, to
make the remaining claim sharp. The concession is described there at *high*
confidence as the dissertation's deliberate dialectical move; I paraphrase the
position rather than assert it.)

*Deny* only the **`for`-ness** -- the existential *mattering*, the authored
purpose, the will-toward-a-referent. EMET's verdict has a function; it does not
have a *for*. It does not author the purpose its output serves. That a `MATCH`
*ought* to license an action is never something the `MATCH` carries; it is
something an operator confers downstream, at the act of stipulating a policy. The
deflationist register is precisely what lets EMET run honestly: it claims exactly
the functional content it has (the byte re-derived; the success-condition was met)
and claims **nothing about permission**, because permission is *for*-ness, and
*for*-ness is authored, not read off a substrate. (That the *for* is in the
tending and never in the seed is the subject of [./04-spoken-for.md](./04-spoken-for.md);
here it is only the boundary that keeps "EMET checks" from sliding into "EMET
permits.")

---

## The strongest objection: the object-capability case

The hardest challenge to the thesis comes from object-capability systems, and it
deserves its full strength rather than a softened version I can wave away.

**Objection.** In a capability architecture, *possessing the token IS
authorization.* There is no separate ACL lookup, no policy consulted at
presentation time: holding the unforgeable reference simply *is* being authorized
to do the thing it names. So here, surely, the is/ought split collapses. The
capability is an *is*-fact -- you either hold the bytes of the token or you do not
-- and that very *is*-fact constitutes its own permission. If authorization can be
identical to possession, then "you cannot derive a permission from a signal" is
false in exactly the systems built most carefully around permissions.

**Answer.** The seam does not vanish; it **relocates** -- and seeing *where* it
relocates dissolves the objection. A capability is a **materialized grant**: an
*ought* made bearer-portable. It is not an *is*-fact that entails its own
permission out of nothing; it is the **record of a prior conferral.** Someone, at
some earlier moment of issuance or delegation, *authored* the permission and
minted a token that carries it. The is/ought seam sits at that moment of
**issuance**, not at the moment of presentation. When you present the capability,
you are not deriving a permission from a signal; you are *redeeming a permission
that was already conferred* and stamped into the token's bytes. The token's
authority is not intrinsic to its bit-pattern; it is the frozen trace of an
authored act that happened elsewhere and earlier.

So ACL systems and capability systems both exhibit the seam; they differ *only in
where the conferral is recorded* -- in a policy table consulted at presentation, or
in the token minted at issuance. Neither eliminates the authored act; both merely
choose where to store its result. This is the "relocates, does not eliminate"
move, applied correctly. (Provenance / further reading: `MEMBRANE-ERRATA.md` §5,
where this edge is re-derived; cited as lineage, the argument above stands on its
own.)

And note what this does *for* EMET rather than *against* it. EMET deals in the
authentication layer of exactly this picture: it answers, to a SHA-256, *is this
the genuine token / file / artifact it claims to be?* -- the bit-integrity
question. It does **not** answer *was this token validly issued?* or *does holding
it permit the act?* Those are the issuance-side authorization questions, and they
belong to whoever authored the policy. EMET tells you the bytes are intact; it
refuses to tell you they are blessed. The capability objection, far from
collapsing the seam, shows precisely the seam EMET is disciplined to sit on one
side of.

---

## The refuter

A claim worth holding must say how it would fail, so here is the condition that
would refute this essay:

> **If a `MATCH` ever, by EMET's own construction, entailed a permission with no
> authored policy in between -- if the verdict alone licensed an action -- the seam
> would have been crossed and this thesis would be false.**

Concretely: if any EMET codepath emitted a verdict that *allowed*, *approved*,
*blessed*, or *trusted*; if any command took a permission decision as input or
returned one as output; if a `MATCH` were treated, anywhere in the contract, as
self-justifying grounds for action rather than as a fact to be handed to a policy
holder -- then EMET would have laundered an *is* into an *ought*, and the headline
claim would collapse. The lattice's closure (no `TRUSTED`), `refuse`'s neutralize-
don't-obey contract, and Boundaries 2 and 4 are precisely the structures that keep
this refuter from triggering. They are not stylistic preferences; they are the
load-bearing walls. Remove any one of them and the seam fails to hold. (That
removing a boundary changes *what EMET is* -- not merely how it behaves -- is the
argument of [./06-aleph.md](./06-aleph.md).)

---

## The seam, applied to this essay

The discipline cuts back on the document making it. This essay's only authority is
its argument. If the reasoning above holds when you push on it, it stands; if it
does not, no provenance, no corpus, no "highest scrutiny" rescues it -- and a claim
of that kind, asserted *in band* to compel belief, is exactly the in-band authority
that `refuse` exists to strip. The is/ought seam is the reason the citations here
point to `research/` as *further reading* and never as *warrant*: a document that
justified EMET's no-authority design *by appeal to authority* would refute itself
in the very move it was making. The fact is offered. The *ought* -- your acceptance --
is yours to author, or to withhold.

---

*Further reading (lineage, never warrant): `SPEC.md` §§2, 4, 6, 8, 11, 16;
`membrane.py` (`verify` 95–109, `refuse` 125–146); `research/CATALOG.md` L8;
`research/dissertation/MEMBRANE-ERRATA.md` §§1–5; `research/dissertation/membrane-through-line.md`
§4; `research/dissertation/part-IV-meaning-closure.md` §§4–5. Sibling essays:
[./02-no-aseity.md](./02-no-aseity.md), [./04-spoken-for.md](./04-spoken-for.md),
[./05-authored-root.md](./05-authored-root.md), [./06-aleph.md](./06-aleph.md),
[./08-taxonomy.md](./08-taxonomy.md). Terms: [./GLOSSARY.md](./GLOSSARY.md).*
