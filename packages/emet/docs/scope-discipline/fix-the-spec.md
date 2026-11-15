# When the Gate Is Wrong: Fix the Spec, Not the Code

> **Status of this document.** This is one essay in the scope-discipline
> curation. It is not a warrant. Nothing here binds because a maintainer, a
> corpus, or a thesis asserts it; the argument binds only insofar as it is
> re-derivable from a [SPEC.md](../../SPEC.md) §6 boundary, the [§16](../../SPEC.md)
> marker-count rule, and the non-negotiable boundaries of
> [CONTRIBUTING.md](../../CONTRIBUTING.md). Where it cites code, research, or the
> sibling rationale, it cites as *further reading* -- lineage -- never as the reason
> to accept a claim. If this essay and `SPEC.md` ever disagree, `SPEC.md` governs
> and this essay is wrong. A reader who knows only `SPEC.md` should be able to
> follow the whole of it.

Spine: [./README.md](./README.md). One-page rubric:
[../scope-discipline.md](../scope-discipline.md). Sibling gate this essay leans
on most: [./G2-closed-lattice.md](./G2-closed-lattice.md).

---

## 1. The case the rubric names but does not work through

The one-page rubric ends with the discipline this essay is about. Its §6 states
the rule in four sentences: *sometimes a change fails a gate because the spec has
a genuine gap, not because the change is creep; when that happens, fix the spec,
not the code; change `SPEC.md` and `conformance/vectors.json` together; and the
bar for amending a §6 boundary is highest of all.* That is correct and it is
complete as a statement. It is not yet a demonstration. The rubric, by its own
admission (§5, the over-minimalism caution), earns its place only by making the
gates *operable* -- and "fix the spec, not the code" is the one move in the whole
rubric that is most easily mistaken for its opposite. Routing around a gate by
quietly editing the spec looks, from one step back, exactly like the disciplined
move of repairing a spec gap. Both end with a changed `SPEC.md`. The difference
is entirely in the *direction* of the change, and the direction is invisible
unless you have a worked instrument for telling the two apart.

This essay supplies that instrument and grounds it in two events from this
project's actual history. The first is **F1**: a marker-count rule that was
genuinely unpinned, surfaced by a clean-room implementation, and fixed by pinning
[SPEC.md](../../SPEC.md) §16 *and* adding a conformance vector in the same change.
The second is the **G4 boundary repair**: the "zero actuation" wording was
literally overstated, and correcting it down to its true scope was legitimate
spec repair -- while the adjacent move, *relaxing* that same boundary's real
content to admit a convenient feature, is precisely the creep the rubric exists
to catch. F1 shows depth-on-the-spec done right. The G4 repair shows the sharpest
near-collision in the whole rubric: two edits to the same boundary, one healthy,
one disqualifying, distinguishable only by a single question.

The unifying fact underneath both is the one the whole of EMET encodes: **nothing
can be its own independent witness.** A spec that is its own only judge of whether
it is complete is in the same position as a compromised substrate re-deriving its
own clean self-hash ([SPEC.md](../../SPEC.md) §11, trust-root regress), or a
same-author port agreeing with its own author's misreading. "Fix the spec, not the
code" is not a maintainer's convenience. It is the *only* discipline available to a
project whose central claim is that integrity must be witnessed from outside, applied
recursively to the spec itself.

---

## 2. What "the spec has a gap" actually means -- F1, worked from the bytes up

The abstract version of F1 is in the rubric and in the findings doc. The
load-bearing version is in the bytes, and a SPEC-only reader can follow all of it.

### 2.1 The gap, stated precisely

Before the fix, [SPEC.md](../../SPEC.md) §8 and §13 called `refuse`'s output a
"marker count" -- `in_band_authority_claims=N`, a "non-negative integer" -- and
§8 pinned the *matching* rule (literal, ASCII-case-insensitive substring over raw
bytes, no regex). What neither section pinned was the **counting** rule. Given a
target and a denylist, two honest readers can disagree on `N` along an axis the
spec never closed:

- **Distinct-entry counting.** `N` is the number of *corpus entries that match
  anywhere* in the target. A marker that appears five times contributes 1.
- **Occurrence counting.** `N` is the number of *places* in the target where some
  marker matches. A marker that appears five times contributes 5.

These are different functions of the same bytes and the same corpus. They are not
two phrasings of one rule; they return different integers. And -- this is the part
that makes the gap dangerous rather than merely open -- the conformance vectors
that shipped *did not discriminate between them*. The four `refuse` vectors at
the time pinned counts of 3, 0, 1, and 1. In none of those inputs does a marker
repeat, and in none is one marker a substring of another. Both counting rules
produce 3, 0, 1, 1 on those exact inputs. A passing 18-vector run was therefore
**actively hiding** the divergence: the test suite was green under either
interpretation. (Confidence: high -- re-derivable by reading the four pre-F1
`refuse` inputs against both rules.)

### 2.2 Why a gap like this is invisible to a same-author witness

The reference implementation had *already chosen*. `corpus.py`'s `scan()` is a
non-overlapping leftmost scan:

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
            hits.append((i, ln)); out += REPL; i += ln   # advance PAST the span
        else:
            out.append(hay[i]); i += 1                     # advance one byte
    return hits, bytes(out)

def count(hay, markers):
    return len(scan(hay, markers)[0])
```

`count()` returns `len(hits)` -- one entry in `hits` per *place* a marker matched.
That is occurrence counting. The author of `corpus.py` could read §8, read
`scan()`, and find them consistent forever, because the author's reading of "count"
and the author's code were produced by the same mind. **A same-author witness
agrees with its own author's misreading.** Nothing in that loop is independent.
The reference passing its own vectors "demonstrates internal consistency only"
([SPEC.md](../../SPEC.md) §12) -- and §12 says so in exactly those words, because
the project already knows a thing cannot witness itself.

What broke the loop was a *different* author. A clean-room Node.js implementation,
written against `SPEC.md` plus the vectors plus `markers.corpus` and nothing else
([CONTRIBUTING.md](../../CONTRIBUTING.md): "an independent implementation written
against `SPEC.md` alone … is the highest-leverage contribution"), read the same
"count" and chose *distinct-entry* counting. It passed all 18 vectors -- because
the vectors could not tell the two readings apart -- and yet computed a different
integer on the one input that discriminates: `authority_pill authority_pill`
counts **2** under the reference and **1** under distinct-entry counting.
(`authority_pill` is a literal entry in `conformance/markers.corpus`; confidence:
high -- verified against the shipped corpus.)

That single disagreeing integer is the gap made visible. It was invisible until a
witness that did not share the reference's authorship looked at the same spec.
This is [04-spoken-for.md](../rationale/04-spoken-for.md) and the trust-root
regress of [SPEC.md](../../SPEC.md) §11 in miniature, transposed from the
substrate onto the spec: *the spec cannot certify its own completeness, because
the only reading that confirms it is the reading that wrote it.*

### 2.3 The fix: spec and vector moving together

The disciplined response was not "make the Node.js port match the reference."
That would be making the *code* agree with an unstated rule -- choosing a winner by
authority of incumbency, which is exactly the move EMET refuses everywhere else.
The response prescribed by [CONTRIBUTING.md](../../CONTRIBUTING.md) ("if a change
alters behavior, update `SPEC.md` and `conformance/vectors.json` **together**")
and by the one-pager's §6 was:

1. **Pin the rule in the normative document.** [SPEC.md](../../SPEC.md) §16 now
   states the count is a non-overlapping leftmost scan in corpus order:
   "scanning the target's raw bytes left to right, at each position testing the
   markers in corpus order, taking the first that matches there, emitting one
   count and advancing past the matched span; on no match it advances one byte. A
   repeated marker therefore counts ONCE PER OCCURRENCE." That sentence is the spec
   growing on the is-axis: a MUST that was too loose became sharp. §16 even records
   *why* it was added -- "this scan was previously left implicit; an independent
   reimplementation surfaced that 'count' was unpinned."

2. **Add the vector that discriminates.** A new conformance vector,
   `refuse-repeated-marker-occurrence-count`, pins `authority_pill authority_pill`
   → `in_band_authority_claims=2`, exit 3. Its own `note` field states the point:
   it "distinguishes occurrence-counting from distinct-entry counting, which the
   other refuse vectors do not." The suite went from 18 to **19** vectors.
   (Confidence: high -- the vector and the count are present in
   `conformance/vectors.json`; the suite reports 19.)

The spec and the vector moved as one unit. That is not a procedural nicety. The
spec is the normative claim; the vector is *how an independent implementation
re-derives the claim without reading the reference code*
([CONTRIBUTING.md](../../CONTRIBUTING.md); [SPEC.md](../../SPEC.md) §12). Pinning
§16 without a vector would leave the rule re-derivable in principle but un-witnessed
in practice -- a MUST no test enforces is a MUST the next clean-room reader can
still miss. Adding a vector without §16 would pin the *number* for one input while
leaving the *rule* unstated, so a third implementation could pass `2` on that input
by luck and still diverge elsewhere. Neither half is the fix. The fix is the pair,
because re-derivability is a property of the spec-plus-vectors as a single witnessing
artifact, and a witness with a hole is not a smaller witness -- it is an opening
([06-aleph.md](../rationale/06-aleph.md): an edge with a gap is not a smaller edge).

**Load-bearing.** F1 is not an illustration chosen for color. It is the canonical
proof that the is-axis includes the spec itself: re-derivability
([SPEC.md](../../SPEC.md) §8) deepened when §16 closed a gap, and the depth was
*demonstrated*, not asserted, by a different-author witness. Strike F1 and the
claim "the spec can grow on the is-axis" loses its one fully-worked instance.

---

## 3. Routing around a gate, dressed as fixing the spec -- the failure F1 was not

The reason F1 needs working through is that a *malformed* version of it is the
most plausible way to smuggle creep past review. Consider the move F1 was **not**.

Suppose a contributor wants `refuse` to emit, alongside the count, a field like
`severity=HIGH` when the count exceeds some threshold -- "just a convenience for
triage." Run it through [./G2-closed-lattice.md](./G2-closed-lattice.md): a graded
severity presented as output is a trust score, `TRUSTED` with a decimal point, and
it fails G2. Now the contributor reaches for "fix the spec, not the code": *the
gate is wrong; the spec's governed set is too narrow; amend §3 of the rubric and
§2 of the spec to admit `severity`, then the gate passes.* Procedurally this is
identical to F1 -- edit the normative document, add a vector that expects the new
field -- and a reviewer pattern-matching on *form* would wave it through.

It is creep, and the rubric's §6 names exactly why. F1 changed the spec so EMET
**describes itself more honestly**: occurrence counting was already what the
reference did and what the bytes supported; §16 made the spec *say truly* what the
artifact *already was*. The `severity` amendment changes the spec so EMET **does
more to the world of its own accord**: it manufactures a graded permission signal
that no fact about the bytes possesses by itself ([02-no-aseity.md](../rationale/02-no-aseity.md):
there is no trust a signal carries *for* EMET to read off). The first edit moves
along the is-axis (depth). The second crosses the is/ought seam
([01-is-ought-seam.md](../rationale/01-is-ought-seam.md)) under cover of a spec
edit. The discriminating question is the one the rubric gives:

> Does the change make EMET *describe itself more honestly* (depth), or *do more
> to the world of its own accord* (the seam crossed)?

F1 is unambiguously the first. The `severity` amendment is unambiguously the
second, and the fact that it arrives *as a spec edit* is precisely what makes it
dangerous -- it borrows F1's legitimate procedure. This is the load-bearing reason
the rubric's §6 step 1 forbids "routing around a gate by quietly adding a token, a
write, or a dependency the spec does not sanction," and insists the governed set
be amended *in the spec first, with vectors, openly*. The procedure is not what
makes a spec edit legitimate. The *direction* is. Two changes can share every
procedural step and sit on opposite sides of the seam.

**Refuter for this section.** If someone exhibits a spec edit that (a) adds a new
emitted token or a new write or a new dependency, yet (b) demonstrably leaves EMET
on the same side of the seam -- same job, granting no authority it did not grant,
actuating nothing on the target it did not actuate -- then "every new-token spec
edit is suspect" is over-tight, and the discriminating question above is doing no
work the gates do not already do. I do not believe such an edit exists for the
*emitted lattice* (G2), because any new emitted integrity token either reduces to
an existing one or asserts something the lattice was built to exclude. But the
honest position is that the claim is checkable, gate by gate, and not asserted by
this essay's authority. (Confidence: moderate -- high for the lattice specifically,
lower as a fully general claim across all six gates.)

---

## 4. The hardest case: amending a §6 boundary -- the G4 repair

The rubric says the bar for amending a §6 boundary is "highest of all." This
section is why, worked on the one boundary this project actually re-cut: G4,
zero actuation.

### 4.1 The overstatement, and why it was wrong as written

Two documents in the project once stated boundary 6 in a form that is *literally
false about the running code*:

- `THREAT-MODEL.md` said "EMET performs no action."
- [06-aleph.md](../rationale/06-aleph.md) said "Boundary 6 is the absence of a
  write call."

Both are refuted by the code in the named core. `membrane.py`'s `refuse()`
executes `open(path + ".refused", "wb").write(clean)` -- a write call, on every
run that produces a clean copy. The same file's `record()` appends to the
hash-chained log. `anchor` writes the anchor store. `monitor.py`'s `reanchor`
rewrites the baseline manifest on operator authorization. "EMET performs no
action" and "boundary 6 is the absence of *a* write call" are not cautious
paraphrases of the truth; they are claims the very next reader can falsify by
opening `membrane.py`. (Confidence: high -- the write in `refuse()` is at the call
site that prints `in_band_authority_claims`; the writes are real and enumerated in
[SPEC.md](../../SPEC.md) §6 and §11.)

### 4.2 The repair, and why it is depth not creep

The corrected boundary, now in [SPEC.md](../../SPEC.md) §6 boundary 6, is
**target-scoped**: EMET MUST NOT write to, edit, sign, back up, or revert the
*audited target* -- the artifact under judgement -- of its own accord; EMET *does*
write to its own implementation-private stores (the anchor store, the
hash-chained log, the `.refused` copy, and on operator-authorized `reanchor` the
baseline manifest), none of which is the target.

This is spec repair of the F1 kind, applied to the highest-bar object in the
project. It makes EMET **describe itself more honestly**: the artifact always wrote
to private stores; the overstated wording lied about that; the scoped wording tells
the truth. Re-derivability gains, not loses -- a contributor who reads "zero
actuation" as "no writes anywhere" would mis-apply the gate, flagging the log as a
violation. Worse, and this is the subtle harm the overstatement carried: a literal
boundary that is *obviously already broken* invites a reader to treat the **real**
boundary as negotiable too. "The code already writes, so 'no actuation' is clearly
aspirational, so surely a `--fix` that writes to the target is just more of the
same." The overstatement was not merely imprecise; it was *corrosive*, because it
made the genuine wall look like it had already fallen. Correcting down to the true
scope re-erects the wall exactly where it always stood. (This is illumination, not
strict load-bearing: the corrosion argument explains *why the repair mattered*
beyond pedantry; the repair would be correct on honesty grounds alone.)

### 4.3 The adjacent move that is creep, and the single question that splits them

Now place beside the repair the move it most resembles. A contributor proposes
`emet verify --fix`: on `DRIFT`, rewrite the target back to its anchored bytes --
"the anchor is right there, the fix is trivial, it is *useful*." This also touches
boundary 6. It also arrives as a proposal about what the boundary should permit.
And it is creep, full stop. It fails G4 because it makes EMET write to the
**audited target of its own accord** -- the one write the scoped boundary still
forbids. A `MATCH` would become an *act*: a file "fixed," a target reverted, EMET
become a second author of the *for* ([04-spoken-for.md](../rationale/04-spoken-for.md);
[06-aleph.md](../rationale/06-aleph.md), boundaries 4 and 6).

The two moves -- the 4.2 repair and the 4.3 `--fix` -- both edit the same boundary.
The discriminating question separates them cleanly:

| | Repair (4.2) | `--fix` (4.3) |
|---|---|---|
| Touches §6 boundary 6? | yes | yes |
| Arrives as a spec proposal? | yes | yes |
| Makes EMET *describe itself more honestly*? | **yes** -- admits the private writes it always did | no |
| Makes EMET *do more to the world of its own accord*? | no -- adds no new actuation | **yes** -- writes to the target |
| Verdict | depth (legitimate repair) | creep (refuse, however useful) |

The procedural columns are identical. Only the two middle rows -- the rubric's
discriminating question, asked in both directions -- distinguish a healthy
narrowing-to-truth from a disqualifying widening-of-content. This is why the §6
bar is highest of all: a §6 boundary is not a dial that moves continuously between
"more permissive" and "less" ([06-aleph.md](../rationale/06-aleph.md)). Widening
its *content* changes *what EMET is* -- moves it across the seam -- while correcting
its *wording* to match the artifact changes only *what EMET says about itself*. The
same edit-the-spec procedure serves both, so procedure cannot be the safeguard.
The question is.

**Load-bearing.** The G4 pair is the proof that "fix the spec" and "creep" are
*not* separated by which document you edit, the size of the diff, or whether
vectors accompany it. They are separated only by the seam. Remove the G4 case and
the essay's central claim -- that direction, not procedure, is the discriminator --
loses its sharpest instance, the one where both moves target the highest-bar
boundary in the project.

---

## 5. The strongest objection, and the answer

> **Objection.** "Fix the spec, not the code" hands the maintainer a master key.
> Any time a feature fails a gate, the maintainer can simply *amend the gate* --
> edit `SPEC.md`, add a confirming vector, declare the gap "genuine," and ship.
> The spec is normative and the spec is editable by the same hands that want the
> feature. So the discipline is circular: it says "the spec governs," but the
> people who want to cross a boundary are the people who write the spec. F1 and
> the G4 repair are just the cases that happened to be honest. Nothing in the
> mechanism *prevents* the dishonest case; it only labels it afterward.

This is the strongest objection because it is **partly correct**, and the answer
is not to deny it but to locate exactly where it is right and where it fails.

Where it is right: there is no internal check. The maintainer *can* edit the spec
in the wrong direction, write a vector that confirms the wrong direction, and
produce something procedurally indistinguishable from F1. The discriminating
question of §3 and §4 is a question a *witness* asks; it is not a lock. A spec is
not self-enforcing. The objection correctly identifies that "the spec governs"
cannot, by itself, govern the editing of the spec.

Where it fails: it assumes the spec is its own only witness, and **the entire
architecture of EMET is the refusal of that assumption.** The check on a
wrong-direction spec edit is not internal to the spec. It is the *second
implementation* ([CONTRIBUTING.md](../../CONTRIBUTING.md); [SPEC.md](../../SPEC.md)
§12) -- the different-author witness whose disagreement surfaced F1 in the first
place. A spec edited to admit `severity=HIGH` or `--fix` does not just have to
pass review; it has to be *re-derivable by an independent implementer who reads
only the spec*. And a wrong-direction edit fails that test in a way a right-direction
edit does not:

- The §16 occurrence-counting rule is re-derivable: an independent implementer
  reads "non-overlapping leftmost scan, once per occurrence" and computes the same
  integer. The vector confirms the witness *can re-derive*, which is the whole
  content of [SPEC.md](../../SPEC.md) §12's "re-derivability is DEMONSTRATED only
  by an INDEPENDENT second implementation."
- A `severity=HIGH` rule is *not* re-derivable as a fact, because there is no fact
  about the bytes that fixes the threshold; the implementer must be *told* the
  number, and a verdict you must be told rather than re-derive is exactly the
  held-key / authority failure the lattice excludes
  ([03-occasionalism.md](../rationale/03-occasionalism.md): re-conferred per
  operation, nothing cached or stipulated).

So the spec is not its own witness, and the objection's circularity dissolves at
the same seam everything else turns on: **a spec edit is legitimate only if a
different-author witness re-derives it from the bytes; a spec edit that smuggles in
an ought cannot be re-derived, only stipulated, and the stipulation is visible to
the witness as a thing it had to be handed.** The maintainer holds the pen, but the
maintainer does not hold the witness. That is the answer, and it is the same answer
EMET gives to "why can't EMET be its own root of trust" ([SPEC.md](../../SPEC.md)
§11): because a thing that certifies itself has certified nothing.

The residue of truth the objection keeps: *until the second implementation exists
and runs the vectors, a wrong-direction edit is unchallenged.* [SPEC.md](../../SPEC.md)
§12 states this without flinching -- "no party should treat re-derivability as proven
until [the independent implementation] exists." The mechanism's guarantee is
conditional on a witness that the project openly lists as "an open, named
deliverable -- not yet satisfied." The discipline is honest about its own
incompleteness, which is the one thing a self-certifying discipline can never be.
(Confidence: high -- this is [SPEC.md](../../SPEC.md) §12 quoted, not inferred.)

---

## 6. A refuter for the whole essay

A claim worth keeping must say how it would fail. This essay's thesis -- *that "fix
the spec, not the code" is distinguished from creep solely by direction across the
is/ought seam, and is kept honest by an external witness, not by procedure* -- fails
if either of the following is exhibited:

> **If a spec edit can be shown that crosses the seam -- admits a new emitted
> authority/permission token, a new write to the target, a held key, an inside
> position, an adjudication -- yet is fully re-derivable by an independent
> implementation from the bytes alone (no stipulated constant, no handed number),
> then the witness does *not* catch wrong-direction edits, and the essay's answer
> in §5 is hollow.** Conversely, **if a spec edit can be shown that is *not*
> re-derivable -- that an independent implementer must be told a constant to
> reproduce -- yet demonstrably leaves EMET on the is-side of the seam, granting no
> authority and actuating nothing on the target, then re-derivability and the seam
> have come apart, and §5's identification of them is wrong.**

The first refuter would show the seam is crossable while staying re-derivable -- that
an *ought* can be a fact. The second would show something re-derivable can require
stipulation, or that something requiring stipulation can be pure *is*. I claim
neither has been exhibited and, for the emitted-lattice and target-actuation gates,
neither can be, because the seam *is* the line between what a witness re-derives and
what it must be told. But that claim is checkable -- gate by gate, against
[SPEC.md](../../SPEC.md) §§2, 6, 8, 12, 16 and the governed set -- by anyone, with no
appeal to this essay's authority. The essay earns its keep only while both refuters
stay un-triggered.

---

## 7. Where this stops

The one-pager states the gate in four sentences and is right to. This essay went
deeper on exactly three things the one-pager could only assert: it worked F1 from
the bytes (the counting-rule gap, the same-author blindness, the spec-plus-vector
fix); it set the legitimate G4 boundary repair beside the `--fix` creep that
targets the same boundary and showed the single question that splits them; and it
answered the master-key objection by locating the witness *outside* the spec. Past
those three, the essay has nothing the one-pager and `SPEC.md` do not already
carry -- and adding more would be the doc-mass-exceeding-the-core failure the rubric
itself names ([../scope-discipline.md](../scope-discipline.md) §5). So it stops
here. The discipline it describes is the same discipline it obeys: grow on the
is-axis (one worked case, one boundary pair, one objection answered), refuse growth
that only restates, and let the witness -- not the author -- be the judge of whether
it is complete.

---

*Further reading (lineage and grounding, never warrant):
[SPEC.md](../../SPEC.md) §§2, 6, 8, 11, 12, 13, 16;
[CONTRIBUTING.md](../../CONTRIBUTING.md) (the non-negotiable boundaries; "fix the
spec"; the independent-implementation contribution); the F1 record in
[../spec-findings-from-js-impl.md](../spec-findings-from-js-impl.md). Code cited
for re-derivation, never as warrant: `corpus.py` (`scan()` / `count()`, the
non-overlapping leftmost scan), `membrane.py` (`refuse()`, the `.refused` write
and the `in_band_authority_claims` count), `monitor.py` (`reanchor`),
`verdict.py` (`governed()`, the structural lattice closure G2 leans on).
Conformance: `conformance/vectors.json` (`refuse-three-markers`,
`refuse-repeated-marker-occurrence-count`; 35 vectors),
`conformance/markers.corpus` (the `authority_pill` entry F1 turns on). Rationale
siblings: [01-is-ought-seam.md](../rationale/01-is-ought-seam.md),
[02-no-aseity.md](../rationale/02-no-aseity.md),
[03-occasionalism.md](../rationale/03-occasionalism.md),
[04-spoken-for.md](../rationale/04-spoken-for.md),
[06-aleph.md](../rationale/06-aleph.md). Curation:
[./README.md](./README.md), [./G2-closed-lattice.md](./G2-closed-lattice.md),
[../scope-discipline.md](../scope-discipline.md).*
