# 14 -- The Witness Walkthrough: One Arc, End to End

> **Status of this essay.** A worked derivation you are meant to *re-walk*, not a
> warrant you are meant to accept. The transcript embedded below is **generated**,
> not asserted: a stdlib-only script
> ([`witness-walkthrough/render.py`](witness-walkthrough/render.py)) runs three
> real demonstrations against the real repository and writes
> [`witness-walkthrough/transcript.txt`](witness-walkthrough/transcript.txt),
> which you can regenerate and check byte-for-byte. Where this essay points to
> `research/`, to a named thinker, or to a sibling document, it points as *further
> reading* -- lineage for an idea -- **never** as the reason to believe it. This is
> the philosophy layer (the *why*); the engineering layer is the six gates in
> [`../scope-discipline/`](../scope-discipline/README.md). If this essay and
> [`SPEC.md`](../../SPEC.md) ever disagree, `SPEC.md` governs and this essay is the
> thing that is wrong. A reader who knows only `SPEC.md` should be able to follow
> the whole of what follows.

---

## 0. What this essay is, and why it is not essay 07

There are two walkthroughs in this curation, and they are not the same walkthrough
twice. [§7](./07-walkthrough.md) takes a single crafted artifact -- a file that
asserts its own authority in-band -- and traces it through the membrane *commands*,
showing the philosophy operative on **one object**: the lattice has no `TRUSTED`
to give, `refuse` strips the injection without obeying it, `selftest` won't vouch
for itself. That essay's subject is the *artifact under judgement*.

This essay's subject is **EMET judging itself** -- and the discovery that it
structurally cannot, alone. Where §7 watched the tool work *on* a file, §14
watches the project's *scope discipline* work on the tool: a gate catches a leak
that had shipped, a **run** (not a review) confirms the fix, and the same fix --
checked thrice -- turns out to share an author with two of its three checks, which
relocates the real witness to a place that does not yet exist. This is the arc the
title names: **the rubric catches a leak, the run is the independent witness, the
seam is located.** None of it is in 00–08. It is the engineering register and the
philosophy register meeting on a single, runnable thread, and the thread is the
contribution. **Status of the arc as a whole: load-bearing.**

The unifying thesis, stated once and held throughout: **integrity is witnessed,
not self-attested -- nothing can be its own independent witness.** Every step below
is one face of that single fact. The fact is not decoration on the design; it is
the design's load-bearing wall, and this essay's job is to show it *bearing load*
in real output rather than in argument alone.

---

## 1. The thesis, stated so it can be checked

A thing cannot witness itself. Spell out why, because the whole arc hangs on it,
and because the reasons are independent -- which is itself the point.

- **At the level of execution.** A compromised substrate re-derives a compromised
  self-hash *consistently* (SPEC §11, the trust-root regress;
  [§5](./05-authored-root.md) is the full derivation). Everything the tool can
  observe agrees with everything else it can observe -- and that agreement is
  exactly what a competent compromise produces for free. Self-agreement is not
  evidence of integrity; it is what integrity-failure *of this kind* looks like
  from inside.
- **At the level of authorship.** A second implementation written by the *same
  author* agrees with that author's misreading, because it inherited the
  misreading. Two artifacts that share a model carry zero *independent*
  confirmatory weight ([§5](./05-authored-root.md) §5.1): their agreement confirms
  the author was self-consistent, never that the author was right.
- **At the level of the tool's own enforcement.** A boundary held by *review* --
  "a human will notice if someone emits `TRUSTED`" -- is the tool attesting its own
  discipline. It holds exactly as long as the reviewer's attention does. The
  reviewer is not independent of the change; the reviewer is *in the loop being
  reviewed*.

The first two are derived elsewhere in this curation. The third is this essay's
opening: **the tool's *enforcement of its own scope* is itself a candidate for
self-attestation, and the same thesis applies to it.** If EMET merely *promises*
to emit no authority, that promise is a self-attestation no better than a
compromised substrate's self-hash. The remedy is the same in form at all three
levels: **move the check to something the failure mode cannot have already
corrupted.** For the substrate, an external verifier on a different machine. For
authorial misreading, an independent re-derivation. For the tool's own scope, a
*structural* gate that fails inside the trusted core -- so the discipline is not
*trusted* to hold but *unable* to break. (Mark: that the three remedies share one
*form* is **illumination**; that each specific remedy discharges its specific
failure is **load-bearing**, and is what the transcript below demonstrates.)

The line the whole project rides is the is/ought seam ([§1](./01-is-ought-seam.md)):
EMET may grow without bound on the **is-axis** (depth -- more re-derivable, more
covered) and is disqualified the moment it grows on the **ought-axis** (width --
authority, adjudication, enforcement, actuation). The scope-discipline rubric is
the seam kept under pressure as the tool grows; its six gates are six segments of
that one perimeter. This essay walks the two gates the arc actually fires:
[**G2**](../scope-discipline/G2-closed-lattice.md) (stays in the closed lattice;
emits no authority) and [**G4**](../scope-discipline/G4-advisory.md) (advisory;
zero actuation on the target).

---

## 2. The arc, before the transcript

State the three movements in prose first, so the captured output reads as
*confirmation* of a claim and not as the claim itself. (That ordering is not
stylistic: a walkthrough that asked you to read the verdict *off* its own
transcript would be doing in-band exactly what `refuse` strips -- letting an
artifact vouch for itself. The claim is argued; the run is the witness; you
re-derive the run.)

1. **The structural gate (G2).** A leak that *had shipped* --
   [`organs.py`](../../organs.py)'s `gate` command once emitted `ALLOW` / `BLOCK`,
   permission-class words -- was caught by the scope rubric and closed by making
   the verdict lattice **structural** rather than reviewed. The mechanism is
   [`verdict.py`](../../verdict.py)'s `governed()`: every token is now emitted
   through one function that *raises inside the trusted core before a byte reaches
   stdout* if the token asserts authority. The transcript's first capture is that
   raise, live: `governed(LATTICE, "TRUSTED")` does not print a tainted line that
   review might catch -- it **fails to construct the line at all**.

2. **The independent witness (G4 + the run).** The fix replaced the permission
   words with `REVERTIBLE` / `NOT_REVERTIBLE` -- the re-derivable *fact* that a
   clean operator revert path exists, never a grant. But a *claim* that the organs
   report a fact and actuate nothing is, again, a self-attestation. The
   independent witness is [`test_organs.py`](../../test_organs.py) **run**: a
   behavior proof that *executes* the organs in a throwaway sandbox and confirms
   the tokens and exit codes from the outside. The transcript's second capture is
   that run passing -- and the load-bearing word is *run*. A green test you
   *execute* is a witness; a test you *read* is one more review.

3. **One witness thrice -- and the located seam (the thesis, cashed).** The same
   conformance vectors, run against the Python reference and the Node port, both
   print `CONFORMANCE 35/35`. They **agree**. And the annotation that makes this
   essay honest rather than triumphant: *they share an author.* Their agreement
   demonstrates the spec is **implementable**, not that it is **independently
   re-derivable** (SPEC §12). The seam -- the exact location where a real
   independent witness is still missing -- is thereby *located*: it is the
   different-author implementation the README calls for and does not yet have. The
   walkthrough ends not at a checkmark but at a **named absence**, which is the
   only honest place for a witness-essay to end.

The three movements are one statement: *EMET's discipline is made structural (so
it cannot self-attest at the enforcement level), confirmed by a run (not a review),
and the one check that would be a true independent witness is named as not-yet-
existing.* Now the run.

---

## 3. The transcript

The block below is **generated**, not hand-written. The renderer copies nothing it
cannot re-derive: it runs the structural-gate probe from an isolated temp sandbox,
runs the organs behavior proof and the conformance runner from the repository
root, normalizes the two volatile fields (the sandbox path and unittest's
wall-clock duration), and writes the transcript next to itself. Regenerate and
verify with:

```sh
python docs/rationale/witness-walkthrough/render.py          # regenerate
python docs/rationale/witness-walkthrough/render.py --check   # assert it re-derives byte-for-byte
```

This is the essay practicing its own thesis. A pasted transcript you must *trust*
would betray the claim that integrity is witnessed by re-derivation. So the
transcript is held to that claim: same `verdict.py` / `organs.py` / `membrane.py`
/ `emet.js` bytes, same vectors → byte-identical output, the same drift-guard
discipline §7's transcript runs under. The demonstration is itself an EMET-shaped
artifact: believed only insofar as you can reproduce it.

<!-- BEGIN GENERATED TRANSCRIPT -->
<!-- Generated by docs/rationale/witness-walkthrough/render.py (see commands above). -->
```text
# (1) THE STRUCTURAL GATE  -  Boundary 1 fails inside the TCB
$ python -c 'import verdict; verdict.governed(verdict.LATTICE, "TRUSTED")'
raised VerdictError: Boundary 1 (SPEC s.2): refused to emit authority verdict 'TRUSTED'
governed(REVERT, 'REVERTIBLE') -> 'REVERTIBLE'  (verbatim: True)
(exit 0)

# (2) THE INDEPENDENT WITNESS  -  the run, not a review
$ python test_organs.py
test_gate_absent_path_is_revertible_exit_0 (__main__.OrgansBehavior.test_gate_absent_path_is_revertible_exit_0) ... ok
test_gate_present_untracked_is_not_revertible_exit_2 (__main__.OrgansBehavior.test_gate_present_untracked_is_not_revertible_exit_2) ... ok
test_observe_emits_new_unchanged_drifted_and_gone (__main__.OrgansBehavior.test_observe_emits_new_unchanged_drifted_and_gone) ... ok

----------------------------------------------------------------------
Ran 3 tests in <dur>s

OK
(exit 0)

# (3) ONE WITNESS THRICE  -  same vectors, membrane.py
$ python conformance/run.py membrane.py
CONFORMANCE 35/35 vectors pass
(exit 0)

# (3) ONE WITNESS THRICE  -  same vectors, impl/js/emet.js
$ python conformance/run.py impl/js/emet.js
CONFORMANCE 35/35 vectors pass
(exit 0)
```
<!-- END GENERATED TRANSCRIPT -->

---

## 4. Reading the transcript, step by step

### 4.1 Capture (1) -- the gate that fails *inside* the tool (G2)

Read the first two lines of output against
[G2](../scope-discipline/G2-closed-lattice.md), the gate that owns the question
*what verdict tokens may leave EMET's mouth?*

```
raised VerdictError: Boundary 1 (SPEC s.2): refused to emit authority verdict 'TRUSTED'
governed(REVERT, 'REVERTIBLE') -> 'REVERTIBLE'  (verbatim: True)
```

**What just happened, and why it is the thesis and not a unit test.** The probe
imported the repository's own [`verdict.py`](../../verdict.py) and asked it to emit
`TRUSTED` on the primary integrity lattice. It did not return a string a downstream
reader might trust; it **raised**, and the exception is a subclass of
`AssertionError` thrown at *construction time*, inside the named core
(SPEC §10) -- before a byte could reach stdout. This is Boundary 1
([§1](./01-is-ought-seam.md), [§2](./02-no-aseity.md)) made **structural**: the
is/ought seam is welded into the *type*, because the set `{MATCH, DRIFT,
UNVERIFIABLE}` has no inhabitant that is an *ought*, and `governed()` refuses every
authority word in `FORBIDDEN` outright besides.

The distinction that matters -- and the reason this is the *witness* essay's first
capture -- is the one G2 §3 draws: until recently the closure was held by **review**.
The tokens were bare literals; a codepath that emitted `TRUSTED` would have been a
review *miss*, caught only if a human's attention held. **A review-enforced
boundary is self-attestation.** It is the tool promising to be disciplined, with
the promise's only witness being a reviewer who is inside the loop being reviewed --
exactly the structure the thesis distrusts at every level. The raise you see is the
promise replaced by an *inability*: the tool is no longer *trusted* to emit only
facts, it is *unable* to emit anything else. The witness moved from a person's
attention (corruptible, in-loop) to the type system (structural, re-derivable by
anyone who runs the probe). That move *is* "nothing is its own witness" applied to
the tool's own scope enforcement. **(Load-bearing.** The structural-vs-review
distinction is the whole reason this capture leads the essay. **Illumination:** the
framing of review as "self-attestation" -- true and useful, but the load is carried
by the raise itself, which you can reproduce without the framing.)

The second line is the quieter, equally necessary fact: `governed(REVERT,
"REVERTIBLE")` returns the token **verbatim** (`verbatim: True`). The gate guards
*what* may be emitted and changes *nothing* about the bytes emitted -- same text,
spacing, order, every stdout byte unchanged (G2 §3, property 2). This is why
making the closure structural needed no spec amendment and broke no shipped output:
it enumerated the existing governed set and gated emission against it without
renaming a single token. A guard that *altered* output would itself be a change
needing conformance review; this one is byte-neutral by construction, and the
`verbatim: True` is that neutrality, checkable in one line.

### 4.2 Capture (2) -- the run that is the witness (G4)

```
$ python test_organs.py
... ok / ok / ok ... OK
(exit 0)
```

This capture is keyed to [G4](../scope-discipline/G4-advisory.md) (advisory; zero
actuation on the target) and to the *fix* the structural gate of §4.1 enabled.
Recall the leak G2 §4.2 narrates: `organs.py gate` once emitted `ALLOW` / `BLOCK`.
`ALLOWED` is in `FORBIDDEN`; `ALLOW` is its imperative; `BLOCK` *sounds like*
enforcement even though the code does nothing -- so the words straddled both G2 (a
permission token) and G4 (an actuation-sounding verdict). The fix changed the
**fact, not the spelling**: `gate` reports `REVERTIBLE` / `NOT_REVERTIBLE` -- the
re-derivable fact that a clean operator VCS revert path already exists *before* a
proposed action lands -- and actuates nothing (it reads bytes, runs read-only `git`
queries, hands the operator the *recipe* `git checkout -- file` as a string it does
**not** run; G4 §2).

Here is the move that makes this capture the *independent witness* and not a fourth
restatement. The claim "the organs report a fact and perform nothing" is, on its
own, a **self-attestation** -- the docstring saying so, the maintainer believing so.
[`test_organs.py`](../../test_organs.py) converts that claim into something
**witnessed**, and the witness is the *run*, not the source:

- It builds a throwaway sandbox that is *deliberately not a git repo*, so
  `git ls-files --error-unmatch` fails and a present-but-untracked file genuinely
  has no VCS revert path. It then **executes** `organs.py gate` as a subprocess and
  asserts the real stdout matches `^REVERTIBLE ` / `^NOT_REVERTIBLE ` and the real
  exit code is `0` / `2`. The absent path is `REVERTIBLE` (revert = delete the new
  file); the present-untracked path is `NOT_REVERTIBLE` -- *and no permission token
  is emitted in either case* (the test's own comment pins this as Boundary 1).
- It executes `observe` and asserts the four perception tokens
  (`NEW` / `UNCHANGED` / `DRIFTED` / `GONE`) all appear against a hand-built
  manifest.

The `... ok` you see three times is the difference between *reviewing* the gate and
*witnessing* it. A reader of `organs.py` who reasons "this looks like it only
reads" is performing a review -- in-loop, corruptible by the reader's own blind
spots, exactly the self-attestation the thesis forbids. The test **runs the code
against bytes it controls and reads the verdict off behavior**, from outside the
reasoning that wrote the code. That is the witness relation specialized to a
behavior claim: a property re-derived by an actor independent of the property's
author. (Mark: **load-bearing** -- "the run, not the review, is the witness" is the
G4-side instance of the unifying thesis. **Illumination:** the sandbox-is-not-a-git-
repo detail is a nice touch that makes the negative case real, but the load is the
*execution*, not the cleverness of the fixture.)

Note what G4 *also* guarantees here and what it does **not**. It guarantees the
organs touch no target byte -- the gate hashes current bytes (a read) and writes
nothing to the path under judgement (G4 §2, load-bearing and checkable: no
`open(..., "w")` on a target, no `git checkout` run, only reads, prints, an exit
code). It does **not** claim the organs are *useless* at the moment of action -- the
exit code *is* the integration point an operator may choose to halt on. That is the
single-actuator model working as designed ([§4](./04-spoken-for.md), SPEC §11): the
operator authors the *for*; EMET supplies a clean *is*. `REVERTIBLE` is the *is*
(re-derivable from `git ls-files` + `git status`); "you may proceed" is the *ought*
the organs decline to author. The run witnesses that the tokens emitted are facts
and the exit codes are advisory -- never a grant, never an act.

### 4.3 Capture (3) -- one witness thrice, and the located seam

```
$ python conformance/run.py membrane.py
CONFORMANCE 35/35 vectors pass

$ python conformance/run.py impl/js/emet.js
CONFORMANCE 35/35 vectors pass
```

Two implementations -- the Python reference and the from-scratch Node port -- run the
*same* 35 conformance vectors through the *same* language-agnostic runner
([`conformance/run.py`](../../conformance/run.py)) and **agree** completely. The
runner is honest about what it tests: its own docstring states that "a second,
INDEPENDENT implementation passing these vectors is what DEMONSTRATES
re-derivability (SPEC §12); the reference implementation passing them proves
internal consistency only."

This is the capture where a triumphalist essay would stop and a *witness* essay
cannot. **The agreement is real and it is not yet the witness that matters.** Both
implementations share an author. By the same-author result ([§5](./05-authored-root.md)
§5.1), two artifacts that share a model carry **zero independent** confirmatory
weight: if the author misread the spec, *both* encode the misreading and agree --
confidently, reproducibly, 35/35 in CI -- on the wrong answer. Their agreement
confirms the author was self-consistent; it says nothing about whether the author
was *right*, because there is no second model for the first to have been checked
against. The README states exactly this scoping and declines to over-claim from it:
the three implementations "share an author, so that agreement shows the spec is
implementable, not yet that it is independently re-derivable." This is the
load-bearing claim of the capture, and it is **high-confidence**: it follows
directly from the absence of an independent model. (The stronger, framed corpus
version -- the philosophy×security convergence of L10 -- I cite as **illumination**,
not warrant; the part this capture rests on is only the self-standing first half.)

So the "one witness thrice" is precisely *one* witness, played three times -- and
that is the point of the heading. Three runs agreeing is not three witnesses; it is
one author's single reading, re-rendered. **The seam is thereby located.** The arc
does not end at `35/35`; it ends at the named coordinate where a genuine
independent witness is still missing: a *different-author* implementation, written
from `SPEC.md` alone (not by reading the existing code), passing the same vectors.
That is the README's open "Call for an independent implementation" and SPEC §12's
not-yet-satisfied deliverable. Locating that absence -- naming exactly *where* the
witness has to come from and admitting it is not here -- is what converting
re-derivability from *asserted* to *demonstrated* requires ([§5](./05-authored-root.md)
§5.2), and it is the only honest terminus for a walkthrough about witnessing.

The structural symmetry across all three captures is the essay in one line, and it
is worth stating because it is the through-line and not a flourish: **in each case,
self-agreement is exactly what the failure mode produces for free, and the remedy
is to move the check to something the failure cannot have already corrupted.** A
review attesting the lattice is closed (corrupted by the reviewer's blind spots) →
a structural raise (capture 1). A docstring attesting the organs actuate nothing
(corrupted by the writer's reasoning) → a behavior run (capture 2). Same-author
implementations attesting the spec is re-derivable (corrupted by the shared model)
→ a different-author re-derivation, named as missing (capture 3). One thesis, three
altitudes.

---

## 5. What the run proves, and what it does not

It proves the discipline is **operative and structural**, not merely intended: the
lattice really *raises* on an authority verdict inside the core, the organs-gate
fix really emits a re-derivable fact and actuates nothing under a run that exercises
both branches, and two implementations really agree on all 35 vectors. Each is a
fact you regenerate, not a sentence you trust.

It does **not** prove the things a witness-essay must be careful never to claim:

- **It does not prove EMET is independently re-derivable.** Capture (3) proves the
  opposite is still open -- agreement among same-author implementations is internal
  consistency, and the independent implementation that would discharge the real
  check does not yet exist (SPEC §12). The run *locates* the missing witness; it
  cannot *be* it.
- **It does not prove `governed()` decides what *belongs* in a channel set.** The
  structural gate closes the *review-miss* failure (an unsanctioned token slipping
  an existing set); it cannot close the *spec-divergence* failure (the set itself
  drifting from SPEC §2). A maintainer who added `"OK"` to `LATTICE` would make
  `governed(LATTICE, "OK")` pass. That residue is a human's, governed by the
  rubric's "fix the spec first, then the code" procedure (G2 §3, §6) -- and it is a
  *disclosed* limit, not a hidden one, which is itself the discipline.
- **It does not prove the input or the repository is "clean" in any deeper sense.**
  The marker corpus is a denylist of known signatures, not a proof of completeness
  (SPEC §11); absence of a flag is never absence of a problem. EMET reports the
  facts it can re-derive and refuses to assert the ones it cannot. The honesty of
  *that* limit is the same discipline the rest of the run demonstrates.

> **Self-application caveat.** This is a worked example, not a warrant. The point
> is emphatically *not* "trust the conclusions because the transcript looks
> convincing" -- that is the in-band-authority move the whole project strips. The
> point is that you can **generate the transcript yourself** and check it against
> these bytes. If your run and this page disagree, this page is wrong; re-derive
> it. An essay about refusing self-attestation that asked you to take its own
> output on its word would refute itself in the act.

---

## 6. The refuter

A walkthrough worth keeping must say how it would fail. State the conditions under
which the *arc* -- not just one capture -- is wrong, in a form anyone can check
against the code with no appeal to this essay's authority.

> **(a) The arc fails if any capture's claim is self-attested rather than
> witnessed.** Concretely: if the structural gate did *not* actually raise -- if
> `governed(LATTICE, "TRUSTED")` returned a string instead of throwing inside the
> core -- then capture (1) would be a review rule wearing a structural costume, and
> the "moved the witness to the type" claim collapses. *Run the probe.* It raises;
> the claim stands. If it ever stops raising, the essay is wrong and the leak is
> back.

> **(b) The arc fails if the "independent witness" is not independent.** If
> `test_organs.py` merely *re-imported and inspected* `organs.py`'s constants
> instead of **executing** the gate as a subprocess and reading verdicts off real
> behavior, then capture (2) would be a review calling itself a run. *Read the
> test:* it spawns `organs.py` with `subprocess.run` against a sandbox it controls
> and asserts on real stdout and exit codes. The witness is the execution; if a
> future edit replaced the subprocess with a source inspection, the witness would
> have quietly become a review, and this section is how you'd catch it.

> **(c) The arc fails if "one witness thrice" is ever sold as three witnesses.**
> The load-bearing honesty of capture (3) is that same-author agreement carries
> *zero independent weight*. If this essay (or the README, or the SPEC) ever
> treated `19/19 × N implementations` as demonstrating re-derivability while those
> implementations share an author, the seam would have been *un*-located -- the
> missing witness papered over rather than named. *The refuter is discharged the
> moment a different-author implementation passes the vectors;* until then, the
> only correct claim is the one the run supports: the spec is implementable, and
> the independent check is open.

All three are checkable, capture by capture, against `verdict.py`,
`test_organs.py`, and `conformance/run.py` -- by anyone, with no appeal to the
authority of this document, which is the only way a document about refusing
authority is permitted to argue. If none fires, the arc holds; if one fires, the
code or the claim changes, never the other way around.

---

## 7. Where this sits in the curation

This walkthrough is the seam where the two registers meet. The **engineering
layer** -- [`../scope-discipline/`](../scope-discipline/README.md), the six gates --
supplies the *what*: [G2](../scope-discipline/G2-closed-lattice.md) (the closed
lattice, made structural in `verdict.py`) and
[G4](../scope-discipline/G4-advisory.md) (advisory; the organs-gate worked case)
are the two segments of the perimeter this arc fires. The **philosophy layer** --
this curation, [§1](./01-is-ought-seam.md) (the is/ought seam EMET locates and
won't launder), [§2](./02-no-aseity.md) (no `TRUSTED` to give), and above all
[§5](./05-authored-root.md) (EMET is not its own root of trust; the independent
re-derivation that has not yet happened) -- supplies the *why*. Essay
[§7](./07-walkthrough.md) is this one's sibling: it runs the philosophy on an
*artifact*; §14 runs it on the *tool*, and ends where §5 says any honest
witness-account must -- at the named, not-yet-built independent check.

Like every page here, this one has no standing of its own. Its transcript is
believed only insofar as it re-derives; the moment it stops matching the bytes, it
is *met* -- an inscription with its animating letter withdrawn. The arc's whole
content is that nothing -- not a substrate, not a same-author port, not a reviewer's
attention, and not this essay -- can be its own witness. Re-run it, or discard it.

---

*Reading order:* this is the runnable companion to [§7](./07-walkthrough.md); read
[§5](./05-authored-root.md) for the authored-root derivation it cashes out, and the
gate spine [`../scope-discipline/README.md`](../scope-discipline/README.md) for the
engineering side. Map and full reading order in [./INDEX.md](./INDEX.md); terms in
[./GLOSSARY.md](./GLOSSARY.md).

*Further reading (lineage and grounding, never warrant):* [SPEC.md](../../SPEC.md)
§§2, 6 (boundaries 1, 4, 6), 9, 10, 11, 12, 13; the code this arc runs --
[`verdict.py`](../../verdict.py) (`governed()`, `FORBIDDEN`, `VerdictError`),
[`organs.py`](../../organs.py) (`gate`, `revertible`),
[`test_organs.py`](../../test_organs.py) (the behavior witness),
[`conformance/run.py`](../../conformance/run.py) (the language-agnostic runner);
[README.md](../../README.md) ("Call for an independent implementation"). Gate
siblings (engineering): [G2](../scope-discipline/G2-closed-lattice.md),
[G4](../scope-discipline/G4-advisory.md). Philosophy siblings:
[§1](./01-is-ought-seam.md), [§2](./02-no-aseity.md), [§4](./04-spoken-for.md),
[§5](./05-authored-root.md), [§7](./07-walkthrough.md). Named thinkers cited in the
lineage above (Aquinas on *esse ab alio*, Nāgārjuna on *svabhāva*, Hume on
is/ought, the security tradition's "root of trust") are *further reading* via the
siblings, never the warrant for any claim here.*
