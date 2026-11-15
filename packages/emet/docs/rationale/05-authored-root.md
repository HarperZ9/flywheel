# 05 -- The Authored Root: EMET Is Not Its Own Root of Trust

> **Status of this document.** This is a derivation you can re-walk, not a
> warrant you must accept. Nothing here is true because a corpus says it; it is
> true only to the extent the argument below survives your attempt to break it.
> Pointers into `research/` are *further reading* -- lineage for the ideas -- never
> the ground of the claim. Per Boundary 1, this essay has exactly as much
> authority as its reasoning earns and not one byte more. If this essay and
> `SPEC.md` ever disagree, `SPEC.md` governs and this essay is the thing that is
> wrong.

---

## 1. Thesis

EMET cannot be its own root of trust. The integrity it can establish for itself
runs only as deep as the substrate it runs on; one level beneath that floor --
the level at which the substrate could already be compromised -- EMET has nothing
to offer but a self-consistent story, and a self-consistent story is exactly
what a compromised substrate produces for free. The check of record for EMET
*itself* must therefore live outside EMET: an external verifier, ideally a
second author re-deriving the same verdicts from the spec alone. The integrity of
the tool is, in the precise sense this essay develops, *esse ab alio* -- being
held from another -- not *esse a se*, being held from itself.

This is not a confession of weakness bolted onto a finished design. It is the
design. EMET's `selftest` does one honest thing and refuses a second tempting
one: it emits its own source hash and *explicitly asserts no authority* over the
question of whether that hash should be believed. The refusal is the feature. An
integrity verifier that certified itself would be making, about its own
trustworthiness, precisely the in-band authority claim it exists to strip out of
everything else (see [./01-is-ought-seam.md](./01-is-ought-seam.md) and
[./02-no-aseity.md](./02-no-aseity.md)). The discipline EMET applies to the
world it would be incoherent to suspend for the one artifact that applies it.

**Status of the mapping in this essay: load-bearing.** Removing it does not
merely make EMET less elegant; it changes what EMET *is*. A self-rooting EMET is
a different object -- one that has quietly re-introduced the aseity its whole
output type was built to deny.

---

## 2. The law, in the operator's vocabulary

Two derivations meet at the same point here, and it is worth keeping them
separate so you can see they are not one argument wearing two hats.

### 2.1 No-aseity, turned reflexively on the tool

The foundational move of this whole curation (developed in
[./02-no-aseity.md](./02-no-aseity.md)) is that nothing stands on its own
footing: to be is to be conferred, relationally and dependently. In the
scholastic idiom this is *esse ab alio* -- a thing's existence received from
another rather than possessed in itself, contrasted with the *esse a se* that the
tradition reserves for a first cause alone. The Madhyamaka form is the denial of
*svabhāva*, intrinsic own-being: nothing carries its own nature inside itself,
sealed off from what sustains it.

Apply that to EMET, and apply it to *EMET's own trustworthiness* -- not to the
artifacts EMET checks, but to the standing of EMET's verdict about itself. If
nothing has aseity, then EMET's integrity has none either. Its integrity is a
conferred, relational fact: it holds *relative to* an uncompromised substrate,
*relative to* an honest byte channel, *relative to* a reader who actually
re-derives the hash. Strip the relations away and ask whether EMET is
trustworthy "in itself," on its own footing, and the question has no answer,
because there is no "in itself" for the answer to be about. The verifier that
tried to confer trust on itself would be claiming the one ontological status --
self-standing being -- that the rest of the design spends every boundary
denying. **No-aseity, applied reflexively, forbids a self-root.** That is the
first derivation, and it is purely from L1 turned inward.

> *Further reading (lineage, not warrant):* L1 No-Aseity in
> `research/CATALOG.md`; Aquinas on *esse ab alio* (*De Ente et Essentia*); the
> denial of *svabhāva* in Nāgārjuna's *Mūlamadhyamakakārikā* and Westerhoff,
> *The Non-Existence of the Real World* (2020). These name where the intuition
> comes from. The argument above stands or falls on its own.

### 2.2 The authored-root regress (the security half)

The second derivation reaches the identical conclusion from a direction that
shares no premises with the first -- and that independence is itself load-bearing
(I return to it in §5.3). It is the regress argument about *where authority comes
from* in any chain of authentication.

Run it slowly. Suppose every element in some hierarchy of trust gets its
authority by validating an incoming signal against a higher element. Element B
trusts a command because element A signed it; A's signature is trusted because a
still-higher element C vouched for A's key; and so on. Now ask: where does the
chain end? It must end -- an infinite tower has no first floor to stand on -- and
the terminus has a property nothing else in the tower has. **The terminus cannot
derive its authority from a signal it received and authenticated**, because doing
so would just be one more rung, continuing the regress rather than ending it. The
root of the chain is, by construction, the one element whose authority is *not*
read off an incoming signal: it is the first fold, the place where authorization
is posited rather than relayed.

This is a real, load-bearing term of art in security: the **root of trust** is
the element whose authority is axiomatic *because there is nothing higher to
validate it against*. Measured boot, attestation, every PKI: each terminates in
something whose honesty is assumed, not proven, because to "prove" it would
require yet another root, and that one would need its own, forever.

The relay/origination distinction is the whole point. A chain of seams each
authenticating the next can *relay* authority indefinitely -- pass it along,
gate it, attenuate it -- but it can never *originate* it. Relay presupposes
something to relay; the origin is the one seam whose authorization is authored,
not received. (This is the *spoken-for* of [./04-spoken-for.md](./04-spoken-for.md)
seen from the trust side: a *for* is authored at a standpoint, never read off the
substrate that carries it.)

So far this is a general claim about authority chains. Here is the step that
makes it bite for EMET specifically: **EMET is not the authored root of its own
trust chain, and it must not pretend to be.** When EMET checks an artifact, it is
a relay -- it re-derives a fact (these bytes hash to this value) and reports it.
When EMET checks *itself*, it is tempted to become the root: to be the seam that
authorizes its own authority. But it cannot legitimately occupy that position,
because the position is defined by being unvalidatable from within the chain, and
EMET trying to validate itself is, transparently, validation from within the
chain. The authored root of EMET's trustworthiness is somewhere EMET is not: in
the operator who chose to rely on it, in the external verifier who re-derives its
verdicts, in the second implementation that agrees from independent code. EMET
can *be* a root of trust for someone else's chain (the operator may treat its
hash as axiomatic). It cannot be the authored root of its own.

> *Further reading (lineage, not warrant):* the authored-root passage in
> `research/dissertation/membrane-through-line.md` §4 ("relay of authority
> presupposes authority to relay … the terminus cannot be a signal it received
> and authenticated"); "root of trust" as a security term of art (any standard
> treatment of measured boot / hardware roots).

---

## 3. The strongest objection, and the answer

**Objection (the self-test-as-self-root move).** "You are overcomplicating
this. EMET already ships a `selftest`. It hashes its own source and reports that
hash. Re-running it reproduces the hash. That *is* a ground: EMET grounds its own
integrity in its own re-derivable self-hash. The hash is stable, public, and
checkable. Why isn't that EMET being its own root of trust -- and a perfectly good
one?"

The objection is the strongest available because it is *almost* right. `selftest`
genuinely does something real, and what it does is genuinely re-derivable (that
re-derivability is the subject of [./03-occasionalism.md](./03-occasionalism.md):
the name is the hash; recompute it and you get the same name or a different one,
with no held secret in between). The objection's error is not about whether the
self-hash is real. It is about *what a re-derived self-hash can and cannot
establish*.

**Answer.** A compromised substrate re-derives a compromised self-hash
*consistently*. Walk the failure through. Suppose an adversary has altered the
machine EMET runs on -- patched the Python interpreter, hooked the file-read
syscall, replaced `membrane.py` with a tampered copy that nonetheless behaves
identically on every observable input. Now run `selftest`. It reads "its own
source," hashes it, and prints a hash. That hash is internally consistent: it is
a correct SHA-256 of whatever bytes the (compromised) read channel handed back.
Re-run it: same hash, every time. The audit chain is INTACT; the self-test
"passes." **Everything EMET can observe agrees with everything else EMET can
observe -- and that agreement is exactly what a competent compromise produces.**
A tampered substrate does not announce itself by making the math fail; a
competent one makes the math succeed against the tampered values. Self-agreement
is not evidence of integrity, because integrity-failure of this kind is invisible
to any check conducted *on the failing substrate*.

This is precisely the limit `SPEC.md` §11 discloses, in the tool's own words, as
a thing that MUST be disclosed rather than papered over:

> *"selftest proves the integrity of EMET only relative to an uncompromised
> substrate; a compromised substrate re-derives a compromised self-hash
> consistently. An EXTERNAL verifier MUST be the check of record for EMET itself;
> EMET MUST NOT be its own root of trust."* (SPEC §11)

And it is the reason `selftest`, in `membrane.py`, says the two things it says
after printing the hash (lines 206–209):

```
emet_self_sha256=<hex>
membrane_self_sha256=<hex>  (deprecated alias; removed at 2.0)
note=re-derive this hash from the source files to check this build.
note=emet reports hashes and verdicts; it grants no permission.
```

Read those two notes as the answer to the objection, encoded in the running
tool. The first sentence relocates the root *outward*: "re-derive this hash from
the source files" -- the verification is something *you* do, from *outside*, against
the source; the hash is a credential offered for external checking, not a verdict
EMET renders on itself. The second sentence is the no-authority refusal: EMET
does not, even here, even about itself, cross into asserting that the hash *ought*
to be believed. The self-hash is an *is* (these bytes hash to this value); whether
to trust the tool that produced it is an *ought* that lives on the far side of the
seam EMET refuses to launder across (see [./01-is-ought-seam.md](./01-is-ought-seam.md)).
`selftest` hands you the fact and explicitly declines the authority. That decline
is the answer to the objection: the self-hash was never offered as a root, only
as something a root -- you, the operator, an independent verifier -- can use.

So the self-test is not falsified by this essay; it is *correctly scoped* by it.
It does its real job (publish the credential) and refuses the fake one (certify
itself). The objection mistakes "EMET can re-derive a stable fact about itself"
for "EMET can ground its own trustworthiness." The first is true and useful; the
second is the aseity-claim no-aseity forbids, and the compromised-substrate case
is the concrete demonstration that the second does not follow from the first.

---

## 4. What this forces in EMET

The element this law forces is `SPEC.md` §11's trust-root regress disclosure,
together with the exact shape of `selftest` in §13–§14. Three concrete features
of the design are not stylistic; they are this argument, compiled:

1. **`selftest` emits a hash and asserts no authority.** It prints
   `emet_self_sha256=` and then *declines*, in band, to claim that the hash
   warrants trust. The closed verdict lattice (§2) has no `TRUSTED` for
   `selftest` to emit *about itself* any more than about anything else -- which is
   the no-aseity boundary of [./02-no-aseity.md](./02-no-aseity.md) doing its
   work at the reflexive case. A `selftest` that printed `TRUSTED` or
   `SELF_VERIFIED` would be the design defect this essay exists to forbid.

2. **The trust-root regress is a *disclosed limit*, not a hidden caveat.**
   §11 lists it among the "Honest limits (MUST be disclosed)," beside denylist
   incompleteness and the raw-byte-channel dependency. A tool that buried this
   would be claiming an aseity it does not have. EMET states the floor of its own
   guarantee out loud: integrity "only relative to an uncompromised substrate."
   The honesty is itself a load-bearing part of the design, because the
   alternative -- implying self-certification -- is the failure mode.

3. **The check of record is required to be external.** §11 does not say an
   external verifier is *nice to have*; it says one MUST be the check of record
   for EMET itself. This is the positive content of the negative claim: "not its
   own root" means "rooted in another," and the other is named -- an external
   verifier, with the strongest available form being an independent
   re-derivation. That requirement is the bridge to §5.

---

## 5. The bridge: from disclosed limit to demonstrated re-derivability

§11 says the check of record must be external. §12 says what the *strongest*
external check is, and the README turns it into an open call. This is where the
authored-root argument stops being a caveat and becomes a research program.

### 5.1 Why self-agreement carries zero independent weight (L10)

The README is blunt about its own current state: the project ships four
implementations -- the Python reference, a from-scratch Rust port, a Node.js port, and a stdlib-only, clean-room Go port -- that agree
on all 35 conformance vectors in CI. And it immediately refuses to over-claim from
that agreement:

> *"they share an author, so that agreement shows the spec is implementable, not
> yet that it is independently re-derivable."* (README, "Call for an independent
> implementation")

Why isn't two-implementations-agreeing enough? Because of a result worth stating
on its own terms (it is L10 in `research/CATALOG.md`, the trust–attack duality,
but the argument is self-contained): **the agreement of two artifacts that share
a model carries zero *independent* confirmatory weight.** When the same author
writes both the Python and the Rust, the two share an enormous amount: the same
reading of the spec, the same mental model of what "exact raw bytes" means, the
same blind spots, the same idea of what the corner cases even *are*. If the author
misread the spec, *both* implementations encode the misreading, and they agree --
confidently, reproducibly, in CI -- on the wrong answer. Their agreement confirms
that the author was self-consistent. It says nothing about whether the author was
*right*, because there is no second model for the first to have been checked
against. Self-consistency is, once again, exactly what a competent error produces
for free -- the same structure as the compromised substrate in §3, now at the
level of authorship rather than execution.

The confidence labelling matters here, so: the claim that same-author agreement
carries *zero independent* weight is the load-bearing one and is high-confidence
(it follows directly from the absence of an independent model). The further L10
claim -- that the architect's minimized trust and the adversary's maximized attack
yield *co-locate by construction* -- is corpus lineage I am citing as
illumination, not leaning on as warrant; treat my paraphrase of it as
moderate-confidence and check it against the source if you want to rely on it.
The part this essay needs is only the first, self-standing part.

### 5.2 What an independent implementation converts, and from what to what

Now the positive move. §12 names the bar precisely:

> *"A conformance claim by the REFERENCE implementation against its OWN vectors
> demonstrates internal consistency only. Re-derivability is DEMONSTRATED only by
> an INDEPENDENT second implementation passing the same vectors. That second
> implementation is an open, named deliverable -- not yet satisfied -- and no party
> should treat re-derivability as proven until it exists."* (SPEC §12)

A different-author implementation, written from `SPEC.md` *alone* (not by reading
the existing code), introduces the second model that L10 says is missing. Its
author reads the spec without the reference author's particular blind spots and
encodes a *different* understanding of the same words. If that independent
understanding nonetheless produces the same verdict on every vector, the
agreement now means something it could not mean before: the fact being re-derived
is robust across *independent* models of it, not just self-consistent within one.
This is the move that **converts re-derivability from *asserted* to
*demonstrated*** -- the README's own phrasing. Before the independent
implementation, "same bytes, same verdict" is a claim EMET makes about itself
(self-agreement, zero independent weight). After it, "same bytes, same verdict"
is a fact two unrelated parties have separately confirmed (the external check of
record §11 demands).

Note the structural symmetry with §3. The compromised-substrate case said: EMET
checking itself *on* the substrate cannot detect substrate compromise, because the
check runs on the thing it would have to be independent of. The same-author case
says: an implementation checking itself *against its own author's* second
implementation cannot detect authorial misreading, because the second
implementation is not independent of the author it would have to be independent
of. **In both cases the fix is the same in form: move the check to something the
failure mode cannot have already corrupted.** For substrate compromise, that is an
external verifier on a different machine. For authorial misreading, that is an
independent implementation by a different author from the spec alone. The README's
"Call for an independent implementation" is not a marketing flourish; it is the
authored-root argument naming the one artifact that would discharge the most
important external check the design requires.

This is also why the README's framing of its own status is the *only* honest one
for a tool of this kind, and is itself an application of [./02-no-aseity.md](./02-no-aseity.md):

> *"For a tool whose only credential is reproduction, an inflated claim would
> refute itself -- so the claim is scoped to exactly what CI reproduces today."*
> (README, "Status")

An over-claim of self-grounded trust, in an integrity verifier, is the exact
in-band authority pattern the tool strips from others. Scoping the claim to "what
CI reproduces today" -- and naming the not-yet-satisfied independent
implementation as the open deliverable -- is the tool declining to be its own root
in the one place it would be most tempting to cheat: its own README.

### 5.3 An aside on why two derivations matter (and a refusal to over-claim it)

I separated §2.1 (no-aseity, reflexive) from §2.2 (the authored-root regress)
because they reach the same conclusion from premises that genuinely do not
overlap -- one is a metaphysical claim about own-being, the other a structural
claim about authority chains in security. When two analyses sharing *no model*
converge, the convergence carries evidentiary weight that two same-model
analyses (§5.1) do not. That is the honest, self-contained version of the point.
The corpus states a stronger, framed version of this (the philosophy×security
convergence of L10); I am flagging that I am *not* leaning on the stronger framed
version as warrant -- I cite it only as lineage. What this essay actually rests on
is the weaker, checkable observation: a metaphysical argument and a security
argument both say EMET can't self-root, and you can verify each independently
above without taking either on authority.

---

## 6. The refuter

State the condition under which this entire essay is wrong, so that it is
refutable rather than merely asserted (the discipline of every essay in this
curation; see [./GLOSSARY.md](./GLOSSARY.md) on *the authored stop* and on the
load-bearing/illumination distinction).

**The claim fails if authentication goes all the way down -- if there is no
authored root, only relay.** Concretely: if it could be shown that every root of
trust derives its authority from a prior verified signal, with no first fold
anywhere -- an infinite, self-supporting regress of authentication that originates
authority while only ever relaying it -- then "the terminus cannot be a signal it
authenticated" would be false, there would be no privileged authored root for
EMET to fail to be, and the whole basis for "EMET cannot self-root because no
self-validating root is coherent" would collapse. The authored-root argument is a
*bet* that authority chains must terminate in an authored fold and cannot close
into a self-supporting loop. It is contentful because it could be wrong: exhibit
the loop -- relay that originates with no author -- and §2.2 dies, taking the
security half of the derivation with it.

The metaphysical half (§2.1) has its own refuter, inherited from
[./02-no-aseity.md](./02-no-aseity.md): exhibit a thing with genuine aseity --
self-standing own-being owing nothing to anything -- and "EMET's integrity has no
aseity either" loses its premise. Note that the two refuters are independent: you
would have to defeat *both* the regress argument *and* the no-aseity argument to
rehabilitate a self-rooting EMET, which is the §5.3 point cashed out as
resilience. Defeating one leaves the other standing, and the conclusion with it.

A narrower, more practical refuter also applies, against the design rather than
the philosophy: show that `selftest` ever emits authority -- that it prints
`TRUSTED`, or that any codepath lets a passing self-test *substitute* for the
external check §11 requires (e.g., a deployment that treats "selftest passed" as
licensing trust with no external verifier) -- and the design has crossed the line
this essay says it must not cross. That would not refute the philosophy; it would
refute the *implementation's fidelity to it*, which is the more immediately
fixable kind of failure.

---

## 7. Close

EMET's integrity is *esse ab alio*: held from another, never from itself. The
tool's most reflexive act, `selftest`, is built to honor this rather than evade
it -- it publishes a credential and explicitly refuses to certify it, relocating
the root of trust outward to the operator, the external verifier, and above all
the independent re-derivation that has not yet happened. The two ways of seeing
why this must be so -- no-aseity turned on the tool, and the regress that says no
authority chain can authorize its own first fold -- converge from unrelated
premises on the same verdict, and their convergence is itself a small instance of
the only kind of agreement that carries weight: agreement across models that share
nothing.

The discipline applies, finally, to this very essay. Its standing is conferred,
not aseitic. It is not true because it is in a `docs/` folder, nor because a
corpus lends it authority -- it has exactly the authority its argument earns under
your attempt to break it, and no more. The check of record for *this document* is
the same as the check of record for EMET: an external one. Re-derive it. If it
disagrees with `SPEC.md`, `SPEC.md` is right and this essay is the thing that is
wrong -- which is precisely the relationship a thing with no aseity has to the
sources that confer its standing.

---

*Reading order:* previous -- [./04-spoken-for.md](./04-spoken-for.md) ·
next -- [./06-aleph.md](./06-aleph.md). Map and full reading order in
[./INDEX.md](./INDEX.md); terms in [./GLOSSARY.md](./GLOSSARY.md). The worked
proof that `selftest` publishes-and-declines in a live run is annotated in
[./07-walkthrough.md](./07-walkthrough.md).
