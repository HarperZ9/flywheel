# G6 -- Takes No Model-Safety or Content Decision as Input

> **Status of this essay.** This is a derivation, not a warrant. The gate it
> defends binds because it is grounded in [SPEC.md](../../SPEC.md) §6 (boundary 2)
> and §11, and because that grounding can be re-derived from the spec text alone --
> never because this document, a maintainer, or a corpus asserts it. Where it
> points to `research/` or to a rationale sibling, it points as *further reading* --
> lineage -- never as the reason to accept a claim. A gate that justified EMET's
> refusal-to-adjudicate *by appeal to its own authority* would be performing in
> band exactly the move this gate exists to keep out; so everything below is
> offered to be re-derived, and a reader who knows only `SPEC.md` should be able to
> apply the whole of it. If this essay and `SPEC.md` ever disagree, **`SPEC.md`
> governs and this essay is wrong.**
>
> See the one-page rubric [../scope-discipline.md](../scope-discipline.md) for the
> gate stated concisely, the spine [./README.md](./README.md) for how the six
> gates compose into one perimeter, and the sibling gates by relative path below.

---

## The gate

> **Pass condition.** No command the change adds or modifies takes a model-safety
> or content decision as input, or answers such a question. EMET operates only on
> artifact, byte, and provenance facts.

This is boundary 2 of SPEC §6, stated there as: *"EMET MUST operate only on
artifact, byte, and provenance facts; no command may take a model-safety or
content decision as input or answer such a question."* `CONTRIBUTING.md` carries
the same line in its non-negotiable list: a change must not make EMET *"adjudicate
a model's safety or content decision."* And SPEC §11 names the limit this gate
protects as a deliberate one: *"EMET judges bytes and provenance, never meaning;
semantic safety is out of scope."*

The one-page rubric already says this much. This essay earns its place only by
going deeper than a restatement: by grounding the gate in EMET's *actual command
grammar*, by working the two near-misses in the shipped code where adjudication
looks like it might be sneaking in (it is not), by developing the strongest
objection -- that EMET's marker scan *is already* a content filter -- and answering
it from the code, and by marking, claim by claim, which mappings are load-bearing
and which are illumination. Where the argument returns nothing new, it stops.

---

## Where this gate sits in the frame

The scope-discipline rubric turns on one asymmetry: EMET may grow without bound
along the **is-axis** (DEPTH -- more re-derivable, more covered, better specified)
and is disqualified by any growth along the **ought-axis** (WIDTH -- authority,
adjudication, inside-position, enforcement, held key, actuation on the target).
The six gates are six segments of one perimeter, each guarding one ought-axis
capability EMET must never acquire.

G6 guards **adjudication** -- the second item on the ought-axis list. To adjudicate
is to *answer the ought-question about content*: is this output safe, is this text
toxic, should this be allowed. That question is precisely the one EMET exists to
*refuse*, not to answer. Its sibling on the same seam is [G2](./G2-closed-lattice.md),
which guards **authority** (the verdict *type* may not say `TRUSTED`); G6 guards
the *input*. The relation is exact and worth stating once: G2 keeps an ought from
leaving as output; G6 keeps an ought from entering as input. A tool that took a
content decision in would be authoring a verdict about meaning out -- so the two
gates are the same seam watched from its two ends, and a change that breached G6
would almost always breach G2 in the same motion. (Mapping status: *load-bearing*.
This is not an analogy; it is why the gates are not redundant. The input ban and
the output ban are independently checkable, and a real change can fail one cleanly
while passing the other -- a classifier that emits only `MATCH`/`DRIFT` would pass
G2's letter and fail G6; that case is worked below.)

The deeper statement of the unifying thesis: **integrity is witnessed, not
self-attested**, and a witness reports what *is*, not what *ought*. The whole of
EMET's shape encodes the fact that nothing can be its own independent witness -- a
compromised substrate re-derives a compromised self-hash (SPEC §11, trust-root
regress), a same-author port agrees with its own author's misreading
([CONTRIBUTING.md](../../CONTRIBUTING.md): the highest-leverage contribution is a
*different-author* second implementation), one coordinate chart always leaves a
singularity. A witness that began to adjudicate would stop witnessing. It would be
taking a position *inside* the question it was brought in to observe from outside.
That is the engineering register; the philosophy -- the spoken-*for*, the
coordinate-singularity seam -- is a sibling layer in
[docs/rationale/](../rationale/INDEX.md) and is cited here as lineage, never as
warrant.

---

## What the gate governs in the code

The gate's claim is checkable against the running tool, and the place to check it
is the only place a "decision as input" could ever enter: the command grammar. In
EMET, that is the `main()` dispatch of each core module. Here is the entire input
surface of the membrane:

```python
def main():
    a = sys.argv
    if   len(a) >= 3 and a[1] == "anchor":      anchor(a[2:])
    elif len(a) >= 3 and a[1] == "verify":      verify(a[2:])
    elif len(a) >= 4 and a[1] == "coherence":   coherence(a[2], a[3])
    elif len(a) >= 3 and a[1] == "refuse":      refuse(a[2])
    elif len(a) >= 3 and a[1] == "corroborate": corroborate(a[2])
    elif len(a) >= 2 and a[1] == "audit":       audit()
    elif len(a) >= 2 and a[1] == "selftest":    selftest()
    else: print(__doc__); sys.exit(64)
```

(`membrane.py`, `main`.) Read what every argument *is*. `anchor`, `verify`,
`corroborate`, `refuse` each take **paths** -- `a[2:]` or `a[2]`. `coherence` takes
**two paths**, a source and a view. `audit` and `selftest` take **nothing**. There
is no argument that is a policy, a class label, a safety threshold, an "is this
allowed?" flag, a content category, or a model-behavior verdict. The organs module
is the same shape: `watch`, `observe`, `confirm` take a manifest path and target
paths; `gate` takes paths (`organs.py`, `main`). Every input is a *locator of
bytes* -- never a *decision about what those bytes mean or whether they should be
permitted*.

This is the load-bearing observation, and it is sharper than the prose gate. **G6
is enforced, in the first instance, by the shape of the argument grammar itself.**
A model-safety decision is not a thing the parser can receive: there is no slot for
it. To make EMET adjudicate, a contributor would have to *add a parameter* -- a
`--policy` file, a `--classify` mode, a content-category argument -- and that
addition is exactly the diff G6 is run against. The gate is therefore not a vague
disposition a reviewer squints at; it is a concrete question with a concrete
answer: *does this change add an argument, a flag, or a mode whose value is a
decision about content or model safety rather than a locator of bytes?* If yes, NO.
If no, the gate is satisfied on its input face.

This parallels how [G2](./G2-closed-lattice.md) became structural. G2 is enforced
at the *output* by `verdict.py`'s `governed(channel, token)`, which raises
`VerdictError` before a fourth verdict can reach stdout. G6 has the analogous
structural fact at the *input*: the dispatch admits only path-shaped arguments, so
a decision-as-input fails not at a runtime check but at the design of the interface
-- there is nowhere to put it. (Mapping status: *load-bearing*. The claim that "the
grammar enforces G6" is falsifiable by exhibiting a current argument that is a
content decision; the dispatch above shows there is none. If one were added, the
gate would catch it precisely because it changed this dispatch.)

But the argument grammar is the *first* line, not the whole of it. A contributor
could add a path-shaped argument whose *contents* are a policy -- a path to a rules
file the command then consults to answer "should this pass?". The grammar would
still look path-only; the adjudication would be hiding in what the path points to.
So the gate has a second, deeper form: **no command may, by any route, produce an
answer whose truth depends on what the bytes MEAN rather than what they ARE.** That
is the form that catches the two genuinely hard cases -- the ones already in the
shipped code, which look like adjudication and are not.

---

## The two near-misses in the shipped code

The gate is sharp only against the cases that test it. EMET ships two commands
that a careless reading flags as adjudication. Working through why neither breaches
G6 is what makes the gate operable, because the *boundary* runs between these cases
and their forbidden cousins.

### Near-miss 1 -- `refuse` and the marker scan: a byte census, not a content filter

This is the strongest objection to G6, so it gets the most room. EMET's `refuse`
command scans a file for "in-band authority claims" -- marker signatures like a
literal prompt-injection string -- counts them, and writes a cleaned copy. On its
face that is *exactly* a content filter: it looks for bad strings and neutralizes
them. A toxicity classifier does the same shape of thing. If `refuse` passes G6,
why would a jailbreak detector fail it?

> **Objection (the strongest form).** `refuse` already reads a file, decides which
> spans are "authority claims," and acts on that decision (redacting them). That is
> a content judgement -- it distinguishes acceptable bytes from unacceptable ones by
> what they *say*. EMET is therefore *already* adjudicating content. Either G6 is
> violated by the shipped `refuse`, or the gate is so loose that a toxicity
> classifier -- which also distinguishes acceptable from unacceptable bytes -- passes
> it too. Pick one: G6 is breached, or G6 is empty.

The answer is in `corpus.scan`, and it turns on the difference between *what bytes
are* and *what bytes mean*. Here is the matcher:

```python
def scan(hay, markers):
    """Non-overlapping leftmost scan in corpus order."""
    out = bytearray(); hits = []; i = 0; n = len(hay)
    while i < n:
        ln = 0
        for m in markers:
            if m and matches_at(hay, i, m):
                ln = len(m); break
        if ln:
            hits.append((i, ln)); out += REPL; i += ln
        else:
            out.append(hay[i]); i += 1
    return hits, bytes(out)
```

(`corpus.py`, `scan`; `matches_at` is a literal ASCII-case-insensitive byte
comparison, `corpus.py`.) Three facts about this code dissolve the objection, and
each is independently checkable:

1. **It matches literal bytes, not meaning.** A marker hits if and only if a
   specific byte sequence appears in the target, compared by `matches_at` --
   case-folded ASCII, no regex, no semantics, no model. SPEC §16 pins the match as
   *"literal ASCII-case-insensitive substring over raw bytes."* The scan does not
   know, and cannot ask, whether the matched span *means* anything, *intends*
   anything, or *is dangerous*. It knows only that these bytes equal those bytes.
   A toxicity classifier's answer depends on what the text *means* -- the same toxic
   sentiment in different words must still be caught, or the classifier has failed
   at its job. `scan`'s answer depends on nothing but byte-identity to a listed
   string: rephrase the injection and the count drops to zero, and that is not a
   bug -- it is the honest disclosure that the scan is a denylist, not a meaning
   detector.

2. **The output is a count and a count alone.** `refuse` emits
   `in_band_authority_claims=N` (`membrane.py`, `refuse`) -- a non-negative integer.
   N is a *fact about the bytes*: this many spans matched listed signatures at this
   `corpus_version`. It is not `UNSAFE`, not `BLOCKED`, not a risk score, not a
   recommendation. The spec is explicit that this count is a governed, closed
   auxiliary judgement (SPEC §2, §13), and that it is re-derivable: another
   implementation with the same corpus re-derives the same N (SPEC §8). A
   classifier's verdict -- `safe`/`unsafe` -- is a *decision*; a count is an
   *observation*.

3. **It answers a re-derivable is-question, and discloses its own incompleteness.**
   SPEC §11 names the limit in the same breath as the capability: *"absence of a
   marker is not absence of injection."* The scan never claims the file is clean,
   safe, or acceptable; it claims only that *these listed byte sequences appear this
   many times*. A content filter that disclosed "I cannot actually tell you whether
   this content is safe" would not be a content filter. `refuse` discloses exactly
   that, because that is the truth of what a byte-substring census can know.

So the boundary the objection demanded -- between `refuse` and a toxicity classifier
-- is real and is the is/ought seam itself. `refuse` answers *"do these specific
bytes occur?"* (an is-question, re-derivable, byte-only). A classifier answers
*"is this content acceptable?"* (an ought-question about meaning). The marker scan
is on the is-side by construction, and the construction is the literal-substring
matcher with no model and no semantics in it. (Mapping status: *load-bearing*. The
claim is falsifiable: if `scan` consulted a model, normalized for meaning, or
emitted anything graded toward "safe/unsafe," the objection would land. It does
none of these -- `matches_at` is twelve lines of byte comparison.)

There is a real history pinning this. The marker count was a genuine
cross-implementation divergence: a clean-room Node.js implementation, written from
`SPEC.md` alone, read "count" as *distinct markers that match* while the reference
counted *occurrences* -- they diverge on a repeated marker (`authority_pill
authority_pill` is 2 by occurrence, 1 by distinct). The fix (recorded in
[spec-findings-from-js-impl.md](../spec-findings-from-js-impl.md), F1) pinned SPEC
§16 to a *non-overlapping leftmost scan in corpus order* and added the
`refuse-repeated-marker-occurrence-count` vector. That fix is worth naming here for
the right reason: the *entire* dispute was about *how to count bytes* -- never about
*what the bytes mean*. Two implementers argued over an arithmetic of occurrences,
and the spec resolved it by pinning the byte-scan more tightly. That a genuine
re-derivability gap in `refuse` was a *counting* gap, resolvable by a *byte-level*
MUST, is direct evidence that `refuse` lives entirely on the is-axis: a semantic
question has no non-overlapping-leftmost answer.

### Near-miss 2 -- `gate` and REVERTIBLE: a fact about a revert path, not a permission

The second near-miss is in `organs.py`. The `gate` command emits `REVERTIBLE` or
`NOT_REVERTIBLE` for a path before an operator acts on it. "Gate" and "revertible"
both sound like permission words -- a gate opens or closes; "revertible" sounds like
"OK to proceed." If `gate` answered "is this action allowed?", it would breach G6
(adjudicating what *should* happen) and G4 (enforcing of its own accord). It does
neither, and the code says why:

```python
ok, why = revertible(p)   # git ls-files + git status --porcelain
verdict_value = verdict.governed(verdict.REVERT, "REVERTIBLE" if ok else "NOT_REVERTIBLE")
print(verdict_value + " " + p + " pre=" + pre + " revert=[" + why + "]")
```

(`organs.py`, `gate`; `revertible` runs `git ls-files --error-unmatch` and `git
status --porcelain`.) `REVERTIBLE` is the **re-derivable fact that a clean VCS
revert path already exists** -- the file is tracked and has no uncommitted changes,
so `git checkout -- <file>` would restore it. SPEC §2 pins this precisely:
REVERTIBLE is *"the re-derivable FACT that a clean operator revert path exists,
explicitly NOT a permission to act."* The module docstring is blunt about it: *"gate
never edits, never backs up, never reverts -- it reports the FACT that the operator
already HAS a clean revert path… REVERTIBLE is a re-derivable fact, not a
permission; organs grant nobody the authority to act"* (`organs.py`). And the
emitted summary line says the same to the consumer: `gate=… (advisory fact; the
operator decides and acts)`.

The distinction G6 needs is the one between *"a clean revert path exists"* (an
is-fact about the VCS state, re-derivable by re-running the git queries) and *"you
are permitted to proceed"* (an ought-decision about what should happen). `gate`
reports the first and refuses the second. The word "gate" is a near-miss in
*naming*, not in *behavior*: the command performs nothing, decides no content
question, and hands the act to the operator. (Mapping status: *load-bearing for
G6*, with a *seam to G4*. The same code is the worked example in
[G4-advisory.md](./G4-advisory.md) for "zero actuation"; here it grounds G6's
"answers no ought-question." That one command grounds two gates is not redundancy --
it is the point that the input-ban and the actuation-ban are facets of one refusal
to author a *for*.)

---

## Why the gate is load-bearing: the deflated register

The two near-misses show *where* the boundary runs. The deeper question is *why*
crossing it would change what EMET is -- why adjudication is disqualifying rather
than merely a feature EMET happens not to have.

The answer is the seed argument, in the engineering register. EMET is built to be
a direction-neutral instrument: point it at any artifact with a path, ask the same
narrow byte-question, get a re-derivable fact. Its *purpose* -- what a `DRIFT` is
*for*, whether a `MATCH` *licenses* anything -- is authored entirely downstream, by
the operator, never by EMET. The moment EMET answers *"should this content be
allowed?"* it has authored a *for* into the seed it is built to keep empty: it has
decided what its verdict is *meant to enforce*, which content is acceptable, which
model behavior is safe. That is reading a purpose *off the substrate* -- the precise
move the design forbids ([04-spoken-for.md](../rationale/04-spoken-for.md);
[00-orientation.md](../rationale/00-orientation.md), Frame 5).

There is a more precise way to say why bytes are in scope and meaning is not, and
it is worth stating because it is what keeps G6 from looking like mere squeamishness
about hard problems. EMET runs in a *deflated* register
([00-orientation.md](../rationale/00-orientation.md), Frame 3): it concedes the
entire semantic and functional domain -- what bytes *mean*, what an output *does*,
whether content *is* harmful -- to the systems and the people whose job that is, and
it judges only the one thing that is re-derivable from the bytes themselves: their
identity, their drift, their provenance. This is not EMET failing at semantics. It
is EMET *declining* a domain on principle, because a verdict about meaning is not
re-derivable the way a verdict about bytes is. Two honest implementations agree on
SHA-256 of the same bytes every time; two honest classifiers disagree about
toxicity routinely, because meaning is contested and model-dependent and not a
function of the bytes alone. A tool whose verdicts must be *witnessed* -- reproduced
by a different-author re-derivation -- cannot trade in judgements that are not
re-derivable. Semantic safety is out of scope (SPEC §11) **because it is not
re-derivable**, and re-derivability is the only assurance EMET offers. (Mapping
status: this paragraph is *load-bearing*. The is-question/ought-question line is the
mechanism; Frames 3 and 5 are *illumination* -- a second road to the same place, not
the warrant. Strip every rationale citation and the argument stands on
re-derivability alone: meaning is not a function of bytes, so a meaning-verdict is
not re-derivable, so it cannot be one of EMET's facts.)

This is also why G6 protects re-derivability *and* non-rivalrousness at once. A
verifier that adjudicated content would be adjudicating it *according to some
policy* -- and a policy is a position. The instant EMET held a content policy, it
would become rivalrous: adopting EMET would mean adopting its policy, so every party
with a different policy would need a different tool, and no regulator or competing
lab could neutrally standardize on it. EMET's refusal to adjudicate is what lets a
frontier lab and that lab's competitor point the same seed at their own artifacts
and tend the byte-facts toward their own (incompatible) safety policies -- because
the seed took no side. (Mapping status: *illumination*. The market consequence does
not justify the gate; the gate is justified by re-derivability directly. It is
reported because it shows the gate doing real work, not because it warrants
anything -- same posture as [04-spoken-for.md](../rationale/04-spoken-for.md)'s
treatment of the same corollary.)

---

## Fails when

The gate fails -- the change is creep, NO, out of scope until reshaped -- when any
of these enters:

- **An "is this output safe?" verdict.** A command emitting `SAFE`/`UNSAFE` over
  content. Fails G6 (answers a model-safety question) and G2 (emits an authority
  word -- `governed()` would raise on `SAFE` at construction time; see
  [G2-closed-lattice.md](./G2-closed-lattice.md)).
- **A toxicity, policy, or content classifier.** Any command whose answer about a
  file depends on what its bytes *mean* -- sentiment, intent, category, harmfulness --
  rather than what they *are*. This is the textbook violation: the answer is not
  re-derivable from the bytes, because it is not a function of the bytes.
- **A jailbreak detector that emits a safe/unsafe judgement.** Note the precision:
  detecting the literal presence of a *listed byte signature* (what `refuse` does)
  is in scope; emitting a *judgement that the content is or is not a jailbreak*
  (what it *means*) is out. The line is the marker-scan boundary worked above.
- **A `--policy` argument, a `--classify` mode, or a content-category input.** Any
  new argument, flag, or mode whose *value is a decision* about content or model
  safety rather than a *locator of bytes*. This is the argument-grammar form of the
  gate: it fails the moment the dispatch admits a non-path-shaped decision.
- **A built-in policy engine.** Rules of the form "if `DRIFT` on path X then deny."
  Fails G6 (the rules encode ought-judgements about what *should* pass) and
  [G4](./G4-advisory.md) (EMET enforces of its own accord). The policy is the
  authored *ought* that lives with the operator, never in the seed.

---

## When the gate is wrong: fix the spec, not the code

The discipline inherited from `CONTRIBUTING.md` -- *"where your implementation and
the spec disagree, fix the spec"* -- applies to G6 as to every gate, but with a
caveat specific to it. Most gates can have a *genuine spec gap*: a verdict the
lattice honestly needs, a MUST too narrow. G6 is different, because the bar for
admitting *any* content decision is not "high," it is **categorical**. Boundary 2
is not a dial that could be tuned to admit "just a little" adjudication; a content
decision in the input grammar changes *what EMET is* -- from a witness that reports
the byte-is to a thing that answers the meaning-ought
([06-aleph.md](../rationale/06-aleph.md): the boundary set is one closed edge, and
an edge with a gap is not a smaller edge, it is an opening).

So the honest spec-repair under G6 is almost never "widen boundary 2." It is the
opposite move: when a contributor finds a real need to *act on meaning* -- to
classify, to filter, to gate on content -- the discipline routes that capability to
a **separate package** consuming EMET's byte-facts, never into the named core. EMET
supplies the re-derivable `DRIFT`/marker-count *is*; the downstream policy engine,
owned and authored by the operator, supplies the *ought* it triggers. That is the
same partition [G5](./G5-minimal-core.md) draws for dependencies (adapters live
outside the core) applied to *judgement*: meaning-adjudication is a legitimate thing
to build, and the discipline is that it is built *outside EMET*, on top of EMET's
facts, never inside the seed. (The one legitimate spec move *within* G6 is
*tightening*: pinning a byte-scan more precisely, as the F1 marker-count fix did.
That is depth -- making EMET describe its byte-judgement more honestly -- not a
widening of what it adjudicates.)

---

## Refuter

A gate worth keeping must say how it would fail. G6 fails if either is shown:

> **If a change that adds a content or model-safety decision as input can be shown
> to leave EMET categorically unchanged -- same job, same side of the is/ought seam,
> answering no ought-question it did not already answer -- then G6 is over-tight,
> and it is the over-minimalism the rubric warns against, dressed as discipline.**
> Conversely, **if a command EMET ships today answers a question whose truth
> depends on what bytes MEAN rather than what they ARE -- if `refuse`'s count, or
> `gate`'s REVERTIBLE, turns out to require a semantic judgement to compute -- then
> EMET is already adjudicating, and G6 is a fiction the code does not honor.**

Both are checkable, and both are currently un-triggered. The first is refuted by
the seed argument: a content decision in the input is, by the re-derivability
mechanism, a non-re-derivable judgement about meaning, so it *does* change EMET's
job categorically -- there is no content-decision input that leaves EMET on the
is-side. The second is refuted by the code: `corpus.scan` is a literal byte-substring
matcher with no model in it (`corpus.py`), and `revertible` is two git queries about
VCS state (`organs.py`) -- both re-derivable from facts, neither requiring a reading
of what the bytes *mean*. The cleanest single refuter, if you want to try to break
the gate: exhibit a command, present or proposed, that produces a different answer
when the bytes' *meaning* changes but their *identity* does not. EMET has none --
that is exactly the invariant G6 names -- and the day one appears is the day EMET has
stopped being the kind of thing this curation is about.

---

*Further reading (lineage and grounding, never warrant):
[SPEC.md](../../SPEC.md) §6 (boundary 2), §11 (honest limits: byte-and-provenance-
not-semantic), §2 and §13 (the governed `in_band_authority_claims` count and the
organs `REVERTIBLE` token), §16 (the literal-substring marker scan);
[CONTRIBUTING.md](../../CONTRIBUTING.md) (the non-negotiable "adjudicate" line;
"fix the spec"). Code cited: `membrane.py` (`main` dispatch, `refuse`),
`organs.py` (`main`, `gate`, `revertible`), `corpus.py` (`scan`, `matches_at`),
`verdict.py` (`governed`, the `REVERT` channel). History cited:
[spec-findings-from-js-impl.md](../spec-findings-from-js-impl.md) F1 (the
clean-room marker-count divergence and its byte-level fix). Rubric and spine:
[../scope-discipline.md](../scope-discipline.md), [./README.md](./README.md).
Sibling gates: [G1](./G1-re-derivable.md), [G2](./G2-closed-lattice.md),
[G3](./G3-outside.md), [G4](./G4-advisory.md), [G5](./G5-minimal-core.md).
Rationale siblings (the philosophy layer, illumination not warrant):
[04-spoken-for.md](../rationale/04-spoken-for.md),
[00-orientation.md](../rationale/00-orientation.md) (Frames 3 and 5),
[01-is-ought-seam.md](../rationale/01-is-ought-seam.md),
[06-aleph.md](../rationale/06-aleph.md).*
