# G5 -- Named-core stays stdlib-only; integrations live in separate packages

> **Status of this document.** One essay in the scope-discipline curation, a
> sibling layer to the rationale curation in [../rationale/](../rationale/). It
> develops a single gate of the [one-page rubric](../scope-discipline.md) in
> depth; it does not restate it. The rubric is the litmus you run on a diff in a
> minute; this is the argument you read once so the litmus means something. The
> warrant for everything below is re-derivation, not citation: where it points to
> [SPEC.md](../../SPEC.md), to code, or to a rationale sibling, it points as
> *lineage*, never as the reason to accept the claim. If this essay and `SPEC.md`
> §10 ever disagree, **`SPEC.md` governs and this essay is wrong.** A reader who
> knows only `SPEC.md` should be able to follow every step.

---

## The gate, stated

EMET's named core -- `membrane.py`, `organs.py`, `monitor.py`, `corpus.py`,
`verdict.py` -- **MUST depend only on the language runtime and standard library,
and MUST add no third-party runtime dependency.** An adapter that genuinely needs
an outside dependency -- signing, SARIF or in-toto emission, fuzzing -- **MAY pull
that dependency, but MUST live in a separate package**, and the minimal-TCB
guarantee continues to apply to the named core alone.

That is SPEC.md §10 (Trusted Computing Base), quoted nearly verbatim, and it is
the fifth boundary `CONTRIBUTING.md` makes non-negotiable in spirit when it asks
that the checks run on a stdlib-only core (`python test_membrane.py`, `python
conformance/run.py membrane.py`, `python membrane.py selftest`) and that the
highest-leverage contribution be "another implementation … written against
`SPEC.md` alone."

The one-page rubric states the pass condition and the failure modes in a
paragraph. This essay does the thing the rubric cannot afford to: it asks *why a
dependency count is a boundary at all* -- why a line about imports sits next to
lines about authority, enforcement, and held keys, as though `import requests`
and `emit TRUSTED` were the same kind of mistake. The claim of this essay is that
they are the same kind of mistake, and that seeing why is the whole point of the
gate.

---

## Why an import is on the ought-axis at all

The scope-discipline frame (rubric §1; [../rationale/01-is-ought-seam.md](../rationale/01-is-ought-seam.md))
splits all growth into two axes. The **is-axis** is depth: more re-derivable,
more covered, better specified -- and EMET may grow on it without bound. The
**ought-axis** is width: authority, adjudication, inside position, enforcement, a
held key, actuation on the target -- and any growth there disqualifies EMET no
matter how useful. The asymmetry is the heart of the rubric.

A third-party dependency looks, at first glance, like neither. It does not emit a
verdict. It does not enforce. It does not write to the target. It just helps the
core do its job -- parse a format, sign a blob, talk to a log. So why is G5 a
*gate*, and not merely good hygiene a maintainer applies when convenient?

Because of what EMET's only assurance actually is. EMET offers exactly one thing:
that **every verdict it emits can be reproduced by someone who did not write
EMET.** Not reproduced by EMET -- a tool agreeing with itself is worth nothing
([../rationale/02-no-aseity.md](../rationale/02-no-aseity.md): nothing has the
standing to vouch for itself). Reproduced by a *second author*, working from
`SPEC.md` alone, who never read the reference code. That second author is the
witness, and the witness is load-bearing for the entire project: a verdict no
independent party can re-derive is a self-attestation wearing a verifier's
clothes, and self-attestation is the precise thing EMET exists to refuse.

Now ask what a third-party import costs the witness. The second implementer must
reproduce EMET's behavior. Every line of the core is surface they must
re-derive -- and they can, because the core is stdlib, and the stdlib is the
shared substrate any two Python authors already hold in common. But an `import
some_third_party_parser` in the core is surface the second author **cannot
re-derive from the spec**: they must either reproduce that library's exact
behavior (now they are re-implementing someone else's code, not EMET's spec) or
**trust** that the library does what its name says. And trust -- believing a claim
you did not re-derive -- is the one move EMET is built to never make. A core that
depends on a library the witness must trust has imported the trust-requirement
into the very thing whose job is to eliminate it.

**This is the load-bearing claim of the gate, and it is the reason an import sits
on the ought-axis with `TRUSTED` and `--fix`:** a dependency the witness cannot
re-derive is a small held key. It is a fact the core *has* (this library is
installed, and behaves) rather than a fact the core *re-derives*. G5 is G1 --
"no held key, re-derivable from bytes" -- projected onto the dependency tree.
Where G1 forbids the *verdict* from resting on something un-re-derivable, G5
forbids the *implementation* from resting on it. Same seam, two surfaces.

*(Load-bearing.)* The mapping "third-party import → held key → ought-axis" is the
spine of the gate; if it fails, G5 is mere hygiene and belongs in a style guide,
not the rubric.

---

## Grounded in EMET's actual code

The abstract argument is only as good as the artifact. Here is the real shape, as
it stands in the tree, with the imports I read off the source.

### The core is stdlib-only, and `verdict.py` is import-free

Every named-core module imports only the standard library plus its sibling core
modules. From the source (high confidence -- read directly):

- `membrane.py`: `import sys, os, json, hashlib, subprocess` then `import corpus`
  and `from verdict import …` -- stdlib plus two core siblings.
- `monitor.py`: `import sys, os, json, hashlib` then `import corpus`, `from
  verdict import …`.
- `organs.py`: `import sys, os, json, subprocess, hashlib` then `import verdict`.
- `corpus.py`: `import os, hashlib`.
- `verdict.py`: **no imports at all.**

`hashlib`, `json`, `os`, `sys`, `subprocess` are exactly the stdlib surface
SPEC §10 names as the reference set. There is no `requests`, no `cryptography`,
no parser library, no SARIF SDK anywhere in the core. The gate is not aspirational
here; it is the measured state of the tree.

That `verdict.py` carries *zero* imports is not incidental -- it is the gate made
maximal at the one place it matters most. `verdict.py` is the module added to the
named core to make Boundary 1 (the closed lattice) **structural rather than
reviewed**: every governed token is emitted through `governed(channel, token)`,
which raises `VerdictError` if the token is outside that channel's closed
frozenset, and denies `TRUSTED`/`APPROVED`/`SAFE` outright (see
[./G2-closed-lattice.md](./G2-closed-lattice.md) for that gate). The module that
*enforces the closed lattice for the whole TCB* has no dependency of its own -- so
the witness re-deriving the lattice guarantee needs to reproduce nothing but a
set-membership test against named frozensets. A held key in `verdict.py` would be
the worst possible place for one: it would mean the structural guard over every
emitted verdict itself rested on something un-re-derivable. Its emptiness is the
gate's strongest single instance.

*(Load-bearing.)* The zero-import state of `verdict.py` is the worked proof that
the gate is satisfiable at the hardest point, not a decoration.

### The seam, shown: `adapters/attest.py`

The gate is not "EMET may never touch in-toto, SARIF, or a signature." It is
"those live in a separate package." The tree carries the canonical example of the
*right* side of the seam: `adapters/attest.py`.

`attest.py` wraps an EMET verdict as an in-toto v1 Statement so the verdict is
consumable by cosign, slsa-verifier, and Sigstore policy-controller with no
EMET-specific code on their side. It is **out-of-core by construction**: it lives
in `adapters/`, not beside `membrane.py`; its own docstring states "this adapter
lives outside the core (SPEC §10): the minimal-TCB guarantee covers membrane,
organs, and monitor, not this file"; and it reaches the core only by
*subprocess* -- it shells out to `python membrane.py selftest` and `python
membrane.py verify …`, parsing the pinned stdout. It does not `import membrane`.
The core does not know the adapter exists. That is the seam working: the adapter
can grow a dependency tree as fat as in-toto and Sigstore require, and **none of
it lands in the TCB the witness must re-derive.**

As it happens, `attest.py` as written is stdlib-only too (`os, sys, json,
hashlib, subprocess`). That is a coincidence of this particular adapter, not the
point. The point is the *location*: were the same in-toto emission welded into
`membrane.py`, it would pass no differently in behavior and fail G5 outright,
because the guarantee is about *what must be believed to trust the core*, and an
adapter is outside that set while a core import is inside it. The rubric's own
worked-DEPTH case names this exactly: "the *adapter* is depth; the same SARIF
emission welded into the stdlib-only core would fail G5."

So the gate draws a line that has nothing to do with the *function* (attestation
is welcome) and everything to do with the *membrane* (it stays outside the named
core). Depth is "EMET's governed verdicts, now consumable as in-toto." Creep is
"the same emission, now a thing the witness must reproduce to re-derive the core."

---

## The objection that has to be answered

Take the gate at its strongest adversary, because a gate that only survives weak
objections is not load-bearing.

> **The objection.** "You are fetishizing the standard library. The stdlib is not
> some pre-trusted bedrock -- `hashlib`, `json`, and `subprocess` are *also* code
> the witness did not write, also code that could be wrong, also a dependency.
> CPython's `hashlib` is a wrapper over OpenSSL; `subprocess` is thousands of
> lines of platform glue. If your argument is 'a dependency the witness must
> trust is a held key,' then the stdlib is a held key too, and G5 is an arbitrary
> line drawn at one particular pile of other-people's-code. Worse: a *good*
> third-party library -- a battle-tested, formally-audited SARIF parser -- might be
> more re-derivable in practice than a gnarly stdlib corner. The gate optimizes
> the wrong variable."

This is the right objection, and the honest answer concedes its premise and
denies its conclusion.

**Concede:** the stdlib is not magically trustworthy, and "stdlib-only" does not
mean "dependency-free." `hashlib` can be wrong. SPEC §11's trust-root regress
already admits the deeper version of this -- EMET on a compromised substrate
re-derives a compromised self-hash consistently, and the substrate includes the
interpreter and its stdlib. The gate does not claim the stdlib is a root of
trust. Nothing is EMET's own root of trust; that is the whole project.

**Deny the conclusion, via the actual mechanism.** The gate is not "trust the
stdlib because it is good." It is "**the stdlib is the substrate the witness
already shares, so depending on it adds nothing the witness must *additionally*
acquire.**" The second implementer writing against `SPEC.md` in any language
*already has* a SHA-256, a JSON serializer, a path API, a subprocess primitive --
these are table stakes of the language they chose, present before EMET existed. A
core built on them asks the witness to reproduce EMET's *logic*, against
primitives they already hold. A core built on `import some_sarif_sdk` asks the
witness to *additionally obtain and reproduce that SDK's behavior*, which is not
table stakes, is not in `SPEC.md`, and may not even exist in their language. The
boundary is not "audited vs. unaudited code." It is **"the shared floor every
implementer already stands on" vs. "a particular artifact only some implementers
can get."** That floor is exactly what makes a *different-author* witness possible
at all.

And the "good library is more re-derivable than a gnarly stdlib corner" point
inverts under this lens. Re-derivability is not measured by how well-audited the
dependency is; it is measured by whether the *second author*, from the spec
alone, lands on the same behavior. A formally-verified SARIF SDK the witness must
install, version-match, and reproduce is *less* re-derivable for EMET's purpose
than a "gnarly" stdlib call the witness's own language already provides an
equivalent for -- because the spec can say "SHA-256 the bytes" and any
implementer's stdlib answers, but the spec cannot say "do what this SDK does"
without making the SDK the spec. The variable G5 optimizes is *witness
reproducibility from the spec*, and on that variable the shared floor wins by
construction, not by faith.

*(Load-bearing.)* This concession-and-denial is the gate's real defense; the
"stdlib is a held key too" objection is the one a careless maintainer will
accept, and accepting it dissolves G5 into hygiene.

---

## A second-order point the example forces: `attest.py`'s silent default

There is a wrinkle in the worked example worth naming, because it sharpens *why*
the adapter must stay an adapter and feeds a separate is-axis argument.

`attest.py` parses the core's stdout to recover the verdict. Its `first_verdict()`
helper scans the lines for a known token and -- **on a parse miss -- returns
`"UNVERIFIABLE"`** rather than failing loudly (the function's final `return
"UNVERIFIABLE"`, reached when no governed token is found in any line). That is a
*silent default*: if the core's output format drifted, or the adapter's token
list fell out of sync, the adapter would emit a confident `UNVERIFIABLE`
attestation that was really "I couldn't parse the output," with no reason code
distinguishing the two.

Two things follow, and they cut in opposite directions, which is why the example
is honest rather than tidy.

First, this is a **mild argument for the gate, against the objection.** SPEC §9 is
emphatic: inability MUST be reported as `UNVERIFIABLE` *with a stable machine
reason code*, never a silent substitution -- "inability is never trust." The core
honors this; `attest.py`, a peripheral adapter, fudges it by collapsing
"couldn't-parse" into the same bare `UNVERIFIABLE` it would emit for a genuine
no-anchor result. That an adapter drifts from the core's own discipline is
*exactly* the reason adapters live outside the TCB: the witness re-deriving EMET's
guarantee re-derives the **core**, where §9 holds structurally, and is not asked
to vouch for an adapter's parsing shortcuts. The silent default is contained
*because* the seam holds. Pull the in-toto emission into the core and that same
sloppiness would be inside the thing the witness must trust.

Second -- and this is the is-axis lesson -- the silent default is **an argument for
the machine-readable JSON envelope** the rubric and SPEC §13 already name as
depth. The adapter only resorts to string-scraping because it consumes
*human-pinned stdout*. Were the core to emit its governed verdict in a structured
envelope (the same `MATCH`/`DRIFT`/`UNVERIFIABLE`, wrapped -- no new token, so
[./G2-closed-lattice.md](./G2-closed-lattice.md) is untouched), the adapter would
read a field, not guess from prose, and the silent-default failure mode would have
nowhere to live. That is depth done correctly: it makes the *existing* governed
fact *more consumable* without adding authority, a key, an inside position, or a
core dependency -- and it removes a real defect in a real adapter. The wrinkle in
the example is therefore not a smudge on the gate; it is the gate pointing at the
next honest is-axis move.

*(Illumination.)* The envelope connection is genuine but secondary; G5 stands
whether or not the envelope ever ships. I mark it illumination so a reader does
not take "fix the envelope" as a *condition* of the gate.

---

## When the gate is wrong: fix the spec, not the core

A change can fail G5 for a good reason: the core genuinely needs something the
stdlib does not provide, and the honest move is not to smuggle the import in. It
is to ask whether the *capability* belongs in the core at all -- and almost always
the answer is "it belongs in an adapter," which is the gate resolving itself, not
blocking the work. The attestation, signing, and SARIF cases all resolve this way:
the function ships, in `adapters/`, and the core never grows the dependency.

If a maintainer ever believes the core *itself* cannot do its job stdlib-only --
that some integrity fact is genuinely un-derivable without a third-party
primitive -- then the discipline inherited from `CONTRIBUTING.md` applies: **fix
the spec, not the code.** Do not quietly add the import. Change `SPEC.md` §10 and
the conformance vectors *together*, in the open, with the argument for why the
shared-floor guarantee must be widened -- because widening §10 changes *what the
witness must hold*, which changes what EMET is. The bar is highest of all here, as
it is for any §6/§10 boundary: a boundary is not a dial. (High confidence: this is
the same "fix the spec, not the code" mechanism the rubric's §6 sets out for every
gate; G5 inherits it unchanged.)

---

## The symmetric failure: over-minimalism

The gate has a wrong direction on *both* sides, and a maintainer who only fears
creep will fall into the other ditch (rubric §5).

The over-minimalist reading of G5 is: "stdlib-only forever, so EMET ships no
adapters at all -- no in-toto, no SARIF, no signing helper -- because each is a
dependency and dependencies are creep." That is the freeze mistaken for the seam.
G5 does **not** say integrations are forbidden; it says they live in separate
packages. A maintainer who blocks `adapters/attest.py` "to stay minimal" has
disqualified EMET along the *is-axis* -- refused real consumability, real coverage,
real reach -- exactly as surely as a maintainer who welds in-toto into the core
disqualifies it along the ought-axis. The adapter is **required** depth, not
tolerated bloat: a verifier no CI system and no Sigstore policy can consume
cleanly is pure in a way that helps no one, and "verifies only toy fixtures, talks
to no real pipeline" is the over-minimalism the rubric names by hand.

The gate's actual job is to keep the *membrane* in the right place -- adapters out,
core stdlib -- so that integrations stay **available without enlarging what must be
believed.** Both directions are growth; only one is safe; and refusing the safe
one is its own disqualification.

---

## Refuter

A gate worth keeping says how it would fail. G5 fails if either of these is shown:

> **If a third-party dependency added to the named core can be shown to leave the
> witness's burden categorically unchanged -- to add nothing the second author,
> working from `SPEC.md` alone, must additionally acquire or trust beyond the
> shared language floor -- then G5 is over-tight, a freeze dressed as discipline,
> and it is blocking the is-axis growth §5 warns against.** Conversely, **if an
> adapter kept dutifully out-of-core can nonetheless be shown to enlarge the TCB
> the witness must re-derive -- if "separate package" turns out not to contain the
> trust-requirement after all -- then the seam G5 draws is in the wrong place, and
> the gate does not protect what it claims to.**

The first refuter is the one to watch in practice, because it is where a tempting
"but everyone has this library" argument lives. Test it the gate's own way: can
the second implementer, in an arbitrary language, from the spec alone, reproduce
the behavior *without* obtaining that specific library? If yes, the dependency was
never on the ought-axis and G5 was over-tight on that case. If no -- if they must
install it, version-match it, or trust it -- the import is a held key and the gate
is right. The refuter is checkable, by anyone, against SPEC §10 and the import
list of the core, with no appeal to the authority of this document.

---

## What this gate is, in one line

G5 is **G1 projected onto the dependency tree**: where G1 forbids a *verdict* from
resting on anything the witness cannot re-derive, G5 forbids the *core's
implementation* from resting on anything the witness cannot re-derive -- and the
shared standard library is precisely the floor every second author already stands
on, while a third-party import is a small held key the witness must additionally
trust. `verdict.py` carries zero imports because the module that makes the closed
lattice structural is the last place a held key should live; `adapters/attest.py`
shows the seam, function welcome, membrane held. Integrity is witnessed, not
self-attested -- and a core no second author can re-derive has quietly become its
own witness, which is the one thing EMET refuses to be.

---

*Siblings (cross-links, not warrant): the spine [./README.md](./README.md); the
one-page rubric [../scope-discipline.md](../scope-discipline.md); the kindred
gates [./G1-re-derivable.md](./G1-re-derivable.md) (the held-key boundary this
gate projects) and [./G2-closed-lattice.md](./G2-closed-lattice.md) (the closed
lattice `verdict.py` enforces). Further reading (lineage and grounding, never
warrant): [SPEC.md](../../SPEC.md) §§9, 10, 11, 13; [CONTRIBUTING.md](../../CONTRIBUTING.md)
(the stdlib-only checks; "fix the spec"). Rationale layer:
[../rationale/01-is-ought-seam.md](../rationale/01-is-ought-seam.md),
[../rationale/02-no-aseity.md](../rationale/02-no-aseity.md). Code grounding the
worked example: `verdict.py` (zero imports; `governed()`), `adapters/attest.py`
(out-of-core in-toto adapter; the `first_verdict()` silent default at the final
`return "UNVERIFIABLE"`), and the core import lines of `membrane.py`,
`monitor.py`, `organs.py`, `corpus.py`.*
