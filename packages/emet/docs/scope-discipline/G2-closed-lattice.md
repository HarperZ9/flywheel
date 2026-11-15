# G2 -- Stays in the closed lattice: emits no authority, permission, or score

> **Status of this document.** This is one essay in the scope-discipline
> curation. It does not bind because a thesis or a maintainer asserts it. It binds
> only insofar as it is re-derivable from [SPEC.md](../../SPEC.md) §§2 and 6 and
> from the boundaries [CONTRIBUTING.md](../../CONTRIBUTING.md) makes
> non-negotiable. Where `SPEC.md` and this essay disagree, **`SPEC.md` governs and
> this essay is wrong.** Everything pointed to elsewhere -- the code, the
> rationale curation, the one-page rubric -- is *further reading*, lineage, never
> the warrant. A reader who knows only `SPEC.md` §§2 and 6 should be able to follow
> and check every claim below, and should refuse any claim they cannot.

The one-page rubric ([../scope-discipline.md](../scope-discipline.md), G2) states
this gate in three sentences: every judgement the change emits is exactly one of
the governed tokens; the change defines, emits, or accepts no verdict outside the
closed set; in particular nothing that asserts authority, grants permission, or
expresses a graded trust score. That statement is correct and operable as far as
it goes. This essay exists only to go *deeper* than it -- to ground the gate in the
code that now enforces it, in two real leaks this project found and closed, and in
the one objection strong enough to make the gate look either redundant or
arbitrary. If at any point this essay would only re-say the rubric, it should
stop; the rubric already names that bloat as the over-minimalism failure
([../scope-discipline.md](../scope-discipline.md) §5). The spine that orders these
essays is [./README.md](./README.md).

---

## 1. The thesis this gate is one face of

The whole of EMET encodes a single fact: **integrity is witnessed, not
self-attested -- nothing can be its own independent witness.** A compromised
substrate re-derives a compromised self-hash with perfect internal consistency
(SPEC §11, trust-root regress). A same-author second implementation agrees with
its own author's misreading. One coordinate chart always leaves a singularity
uncovered. The engineering consequence is that EMET may emit only *facts a
separate party can re-derive*, and must never emit the one kind of output that
would make it a witness to itself: a *grant* -- a value that says "this is fine,"
"this is trusted," "this may pass."

The scope-discipline rubric is the seam that keeps EMET on the right side of that
line as it grows. EMET may grow without bound on the **is-axis** (DEPTH: more
re-derivable, more covered, better specified) and is disqualified the moment it
grows on the **ought-axis** (WIDTH: authority, adjudication, inside-position,
enforcement, held key, actuation on the target). G2 is the gate that guards the
*first* ought-axis capability in that list -- **authority** -- at the exact place it
would enter: the output type. Everything else a change could do, G2 is silent on.
What G2 owns is the question *what verdict tokens may leave EMET's mouth?*

The philosophy behind "nothing is its own witness" -- the witnesses, the
coordinate-singularity seam -- is a sibling layer in
[../rationale/](../rationale/) and is **illumination** for this essay, not its
warrant. This is the engineering register: G2 stands on SPEC §§2 and 6 and on the
frozensets in `verdict.py`, and a reader who rejects the philosophy entirely can
still check every load-bearing claim here.

---

## 2. The boundary, stated precisely

G2 maps to two SPEC clauses, and the mapping is **load-bearing** (the gate is
void without them):

- **SPEC §2 -- the closed lattice.** "Every integrity judgement EMET emits MUST be
  exactly one of: MATCH, DRIFT, or UNVERIFIABLE. This enum is CLOSED. An
  implementation MUST NOT define, emit, or accept any other verdict -- in
  particular it MUST NOT emit TRUSTED, APPROVED, or SAFE, or any value asserting
  authority or permission." SPEC §2 then extends the closure to the auxiliary
  judgements (coherence, corroboration, the marker count, the monitor report, the
  organs) -- each its own small closed set, none of which "is, or maps to,
  TRUSTED."
- **SPEC §6, boundary 1 -- facts, not authority.** "the verdict lattice is closed
  (section 2); no codepath may produce a verdict outside it, and none may emit
  TRUSTED."

`CONTRIBUTING.md` restates the same wall as a non-negotiable: a change must not
make EMET "emit a verdict outside the closed lattice `MATCH | DRIFT |
UNVERIFIABLE` (in particular, never `TRUSTED`)."

The pass condition, stated for a diff: **every judgement the change emits is a
member of its channel's governed set, and no path defines, emits, or accepts a
token outside that set -- in particular nothing asserting authority, granting
permission, or expressing a graded trust score.**

Why this is the place the seam is welded, and not one place among several: the
is/ought distinction the whole project turns on
([../rationale/01-is-ought-seam.md](../rationale/01-is-ought-seam.md)) is encoded
in the **output type**. A function whose codomain is `{MATCH, DRIFT,
UNVERIFIABLE}` *cannot* return an *ought*, because the set has no inhabitant that
is one. There is no `MATCH` that means "and therefore you may proceed." That is
not a convention a reviewer enforces on top of the type; it is a property *of* the
type. G2 is the gate that defends the type's emptiness of oughts. (Mark: this
type-level claim is **load-bearing**. The witnesses-and-charts framing of *why*
oughts are forbidden is **illumination**.)

---

## 3. The gate is now structural, not advisory -- what `verdict.py` actually does

The deepening this essay can offer over the rubric begins here. Until recently G2
was enforced by **review**: the governed tokens were bare string literals
scattered through `membrane.py` and `monitor.py`, so a codepath that emitted
`TRUSTED` would have been a *review miss* -- caught, if at all, by a human reading
the diff. A review-enforced boundary is exactly the kind of self-attestation the
thesis distrusts: it holds only as long as the reviewer's attention does.

`verdict.py` makes the closure **structural**. Every governed token is now emitted
through one function:

```python
def governed(channel, token):
    if token in FORBIDDEN:
        raise VerdictError(... "refused to emit authority verdict" ...)
    if token not in channel:
        raise VerdictError(... "ungoverned verdict ... the verdict lattice is closed" ...)
    return token
```

Two facts about this function carry the gate:

1. **It raises at construction time, inside the TCB, before a byte reaches
   stdout.** `VerdictError` subclasses `AssertionError`. A codepath that tried to
   `print(governed(LATTICE, "TRUSTED") + " " + path)` does not print a tainted
   line and get caught later; it *fails to construct the line at all*. The leak is
   converted from a runtime output a downstream reader might trust into a hard
   error in the named core (SPEC §10). This is the structural form of the thesis:
   the tool is not *trusted* to emit only facts, it is *unable* to emit anything
   else.

2. **It returns the token verbatim.** `governed()` changes only *how* a token is
   emitted, never *what*: the surrounding text, spacing, and order at each call
   site -- and thus every stdout byte -- are unchanged. This is why adding the guard
   was not itself a G2 event needing a spec amendment: it enumerated the existing
   governed set and gated emission against it without renaming, reordering, or
   reformatting a single shipped token. (Mark: the verbatim-return property is
   **load-bearing** for the claim that the guard is byte-neutral; a guard that
   altered output would itself need conformance-vector review.)

The channels are per-surface because the lattice is layered (SPEC §2). The
frozensets in `verdict.py`:

- `LATTICE = {MATCH, DRIFT, UNVERIFIABLE}` -- the primary integrity lattice.
- `COHERENCE = {COHERENT, VIEW_DIFFERS_FROM_SOURCE, UNVERIFIABLE}`.
- `CORROBORATE = {CORROBORATED, QUARANTINE_READ_PATH_DIVERGENCE, UNVERIFIABLE}`.
- `AUDIT = {INTACT, BROKEN}` -- the tamper-evident chain result.
- `MONITOR_FILE = {MATCH, DRIFT, MISSING}` and `MONITOR_BASELINE = {INTACT,
  CHANGED}` -- see §4.
- `PERCEPTION = {UNCHANGED, DRIFTED, NEW, GONE}` and `REVERT = {REVERTIBLE,
  NOT_REVERTIBLE}` -- see §4.

And the belt-and-suspenders denial:

```python
FORBIDDEN = frozenset({"TRUSTED", "APPROVED", "SAFE", "ALLOWED", "PERMITTED",
                       "AUTHORIZED", "BLESSED", "VERIFIED_AUTHORITY"})
```

The channel sets already exclude every one of these by construction, so `FORBIDDEN`
is redundant *for the current sets*. It is not redundant against the *future*: it
makes the anti-authority intent unmissable and survives a careless edit that
widened a channel set to admit `ALLOWED`. The check is ordered `FORBIDDEN` first,
so an authority word is refused with a Boundary-1 message even if some edit had
wrongly added it to a channel. (Mark: `FORBIDDEN` is **illumination today,
load-bearing tomorrow** -- it is precisely the guard against the edit that §6
warns about: slipping a token into a frozenset to dodge the check.)

One more property worth pinning, because it is the gate's honest limit:
**`governed()` cannot decide what *belongs* in a channel set.** It enforces
membership; it does not author membership. A maintainer who added `"OK"` to
`LATTICE` would make `governed(LATTICE, "OK")` pass. The structural guard closes
the *review-miss* failure mode (an unsanctioned token slipping through an existing
set) but not the *spec-divergence* failure mode (the set itself drifting from
SPEC §2). The second is what the human reviewer still owns, and §6 of the rubric
is the procedure for it: a genuinely needed token is added to `SPEC.md` **first**,
and the frozenset follows the spec, never the reverse.

---

## 4. Two real leaks this gate caught -- and what they teach

The rubric asserts G2 is "largely mechanical now." This session is where that
became true, by catching two leaks that had shipped. Both are worth narrating
because they sit on opposite sides of the gate and teach different lessons.

### 4.1 The monitor: tokens *outside the lattice* (an enumeration gap)

`monitor.py`'s `report` command emits, per file, `MATCH` / `DRIFT` / `MISSING`,
and per baseline, `INTACT` / `CHANGED`. These tokens *ship* -- they are in real
stdout, in the hash-chained `monitor_log.jsonl`, and in the conformance posture.
But until this session they were **ungoverned**: emitted as bare literals, outside
any enumerated set, never passed through SPEC §2's closure. An adversarial scope
review flagged it correctly. The monitor was emitting integrity judgements that
*no closed set named*, which is a G2 failure in the precise sense -- "the change
defines, emits, or accepts no verdict outside the closed set" was being violated
by code already in the tree.

The fix was **enumerate, not rename.** These exact tokens are load-bearing in
shipped output; renaming them would have been a gratuitous break. So they were
placed inside `MONITOR_FILE` and `MONITOR_BASELINE` and routed through
`governed()`:

```python
st = governed(MONITOR_FILE, "MATCH" if got == want else "DRIFT") + " "
...
verdict = governed(MONITOR_BASELINE, "INTACT" if drift == 0 and missing == 0 else "CHANGED")
```

and SPEC §2 was extended to carry them normatively ("per baseline it emits exactly
INTACT or CHANGED, and per file it emits exactly MATCH, DRIFT, or MISSING. None of
these is, or maps to, TRUSTED").

The lesson: **a token can be perfectly innocent on its face and still be a G2
failure.** None of `INTACT`, `CHANGED`, or `MISSING` asserts authority -- each is a
re-derivable fact about whether bytes match an operator-authorized baseline. The
violation was not their *meaning*; it was that they lived *outside the governed
set*, so G2 had no authority over the monitor at all. The gate is about closure,
not about each token's local content. An open set is the failure even when every
token currently in it is benign, because the *next* token added to an ungoverned
surface is the one that will not be benign, and review cannot tell them apart once
the precedent is set (the same argument the rubric §6 makes). Note `MISSING` here:
it is the monitor's `UNVERIFIABLE`-class result -- an absent baseline file is a
re-derivable inability, reported, never defaulted to a pass. That is the §9
discipline (UNVERIFIABLE, never TRUSTED) showing up inside the monitor.

### 4.2 The organs gate: a token *that was* authority (a permission-class leak)

The second leak is the sharper one, and it is the one the FORBIDDEN set exists
for. `organs.py`'s `gate` command emitted **`ALLOW` / `BLOCK`**. Those are not an
enumeration gap -- they are *permission-class words*. `ALLOWED` is in `FORBIDDEN`;
`ALLOW` is its imperative. A `gate` that prints `ALLOW path` is doing in band
exactly what the whole project exists to refuse: emitting a value a downstream
reader would reasonably treat as a grant of permission to act. It also collides
with G4 (advisory): a token named `BLOCK` *sounds like* enforcement even when the
code does nothing. The word itself is the leak.

The fix changed the **fact**, not just the spelling. `gate` does not report a
permission; it reports the re-derivable FACT that a clean operator VCS revert path
exists *before* a proposed operator action lands. The honest token for that fact
is **`REVERTIBLE` / `NOT_REVERTIBLE`**:

```python
verdict_value = verdict.governed(verdict.REVERT, "REVERTIBLE" if ok else "NOT_REVERTIBLE")
print(verdict_value + " " + p + " pre=" + pre + " revert=[" + why + "]")
...
gate_token = verdict.governed(verdict.REVERT, "REVERTIBLE" if revertible_all else "NOT_REVERTIBLE")
print("gate=" + gate_token + "  (advisory fact; the operator decides and acts)")
```

`REVERTIBLE` answers *is there a clean revert path?* -- a fact re-derivable from
`git ls-files` and `git status` (organs.py `revertible()`). It does **not** answer
*may you proceed?* The summary line even spells the boundary in prose: "advisory
fact; the operator decides and acts." SPEC §2 was extended to pin it: "Impedance
(gate) emits per path and per summary exactly REVERTIBLE or NOT_REVERTIBLE -- the
re-derivable FACT that a clean operator revert path exists, explicitly NOT a
permission to act."

The lesson: **the `ALLOW`→`REVERTIBLE` fix is not cosmetic; it is the is/ought
seam enforced on a single word.** `ALLOW` is an ought (a grant). `REVERTIBLE` is
an is (a re-derivable property of the operator's VCS state). The gate, named
honestly, supplies the *is* and declines to author the *ought* -- which is the
exact division of labor in
[../rationale/04-spoken-for.md](../rationale/04-spoken-for.md): the operator
authors the *for*, EMET hands over a clean *is*. A change that had kept `ALLOW`
"because it reads better in CI" would have passed every other gate and still moved
EMET across the seam -- which is the refuter condition the rubric names, and here
it was caught, not by taste, but by `ALLOWED ∈ FORBIDDEN`.

### 4.3 Why the two leaks are different, and why one gate catches both

The monitor leak was an **open set** (tokens with no governed home); the organs
leak was a **forbidden token** (a permission word that needed no home -- it needed
to not exist). G2 catches both because it has two clauses: *membership in a closed
set* (the channel check) and *exclusion of authority words* (the FORBIDDEN check).
`verdict.py` implements them as the two `if` branches of `governed()`. A gate with
only the first clause would have admitted `ALLOW` into a hand-written
`{ALLOW, BLOCK}` set; a gate with only the second would have let the monitor's
benign-but-ungoverned tokens leak. The gate needs both arms, and the code has
both.

---

## 5. The risk score: TRUSTED with a decimal point

The rubric's sharpest CREEP example deserves its own derivation here, because it
is the case where G2 is least *mechanical* and most *conceptual* -- the one a
structural guard alone would miss.

A risk score -- a 0–100 number, or low/medium/high, presented as a verdict -- is
**not** in `FORBIDDEN`. The string `"73"` is not `"TRUSTED"`. A naive guard keyed
only on a denylist of authority words would pass it. So why does it fail G2?

Because a graded trust assertion *is* an authority verdict; it has merely smuggled
the grant into a continuous range. "73/100 trustworthy" is a claim that the signal
possesses a degree of permission *by itself*, readable off the artifact -- and
there is no such fact ([../rationale/02-no-aseity.md](../rationale/02-no-aseity.md):
no signal possesses trust *aseitically*, of itself, for EMET to read). A scalar
implies an ordering, an ordering implies a threshold, and a threshold is a
permission decision in waiting: somebody downstream will write `if score > 80:
allow`. The score is `TRUSTED` with a decimal point -- the same ought, encoded so
it slides past a string match.

The honest expression of "how changed" is not a manufactured scalar; it is the
**set of `DRIFT` results and their hashes**. That is information -- re-derivable,
checkable, per-artifact -- without being a grant. Facts do not come in degrees of
permission. This is the part of G2 that stays a *human* judgement even after the
structural guard: a reviewer must recognize that a new numeric "confidence" field
is a verdict-by-another-name and refuse it under G2, then (if the underlying need
is real) reshape it into more `DRIFT` resolution or a richer reason code -- depth
on the is-axis -- never a scalar trust. (Mark: this section is **load-bearing**.
The score is the canonical case where G2's *intent* exceeds its *mechanism*, and
where the rubric's "fix the spec, not the code" discipline -- reshape to depth --
does the work the FORBIDDEN frozenset cannot.)

---

## 6. The strongest objection, and the answer

> **Objection.** This gate is theater. The whole apparatus -- `governed()`, eight
> frozensets, a `FORBIDDEN` set that the channel sets already make redundant --
> guards a *string*. A determined contributor who wants EMET to confer authority
> writes `print("MATCH -- safe to proceed " + path)`: every token is governed,
> `governed(LATTICE, "MATCH")` passes, and the *sentence* still grants permission.
> Conversely, a downstream system can read plain `MATCH` and wire `if verdict ==
> MATCH: deploy`, conferring authority EMET never typed. Either way the grant
> happens. The gate polices the vocabulary and misses the act. So either G2 is
> doing nothing real, or -- if it *is* load-bearing -- the line it draws (this token
> yes, that token no) is arbitrary: `REVERTIBLE` is "a fact" and `ALLOW` is "a
> permission" by fiat, when both are just strings a reader interprets.

This is the objection to take seriously, because both halves are partly true. The
answer is in three moves.

**First -- G2 is necessary but not sufficient, and never claimed otherwise.** The
six gates are "six segments of one perimeter"
([../scope-discipline.md](../scope-discipline.md) §2). The free-text-suffix attack
("MATCH -- safe to proceed") is real, and G2 does not catch the *prose*. But the
prose attack is caught *elsewhere on the perimeter*: SPEC §13 pins the output
grammar to specific tokens, and a suffix asserting permission is a §13 violation
and a G4 (advisory) violation -- EMET emitting something a reader treats as a grant
of its own accord. No single gate is the whole wall; the objection that G2 alone
does not stop every authority leak is true and not a defect. What G2 *uniquely*
owns is the **type**: it guarantees the verdict *token* -- the machine-readable
load-bearing field -- is never an ought. That guarantee is what lets the JSON
envelope (the v1 target, SPEC §13) carry `MATCH` to a program without carrying a
grant. A program reads the token, not the prose. Securing the token is securing
the part machines act on.

**Second -- the downstream `if MATCH: deploy` is not EMET conferring authority; it
is the operator authoring an ought *from* a fact, which is correct.** This is the
crux the objection blurs. When CI fails on exit 2, or a script deploys on `MATCH`,
the *operator* has authored the rule "treat this fact as license." That is the
single-actuator model working as designed (SPEC §11): the operator authors the
*for*, EMET supplies the *is*
([../rationale/04-spoken-for.md](../rationale/04-spoken-for.md)). The seam is not
violated by an operator *deciding* that `MATCH` warrants deployment; it is
violated by *EMET* shipping a token that *pre-decides* it. `MATCH` is re-derivable
and means only "re-derivation agreed"; `TRUSTED` would mean "and therefore proceed,"
which is the operator's authorship pre-empted. G2 keeps EMET on the *is* side so
the operator's authorship of the *ought* is theirs, not laundered through EMET's
output. The objection mistakes "the operator can build an ought on top of EMET's
is" for "EMET emits an ought." Only the second is a G2 failure.

**Third -- the line between `REVERTIBLE` and `ALLOW` is not fiat; it is
re-derivability.** This is the answer to the "arbitrary" half. The test for
whether a token is a fact or a grant is not the maintainer's taste; it is: **can a
separate party re-derive it from bytes they can read, with no appeal to EMET's
authority?** `REVERTIBLE` passes: it is `git ls-files --error-unmatch` plus `git
status --porcelain` returning clean -- a property of the operator's VCS state that
anyone with the repo re-derives identically (organs.py `revertible()`). `ALLOW`
fails: there is no byte-level fact "this is allowed" to re-derive; "allowed" is a
*decision*, and a decision has an author, and if EMET emits it EMET is the author.
`MATCH` passes (re-hash the bytes, compare to the anchor). `TRUSTED` fails (no
artifact possesses trust for EMET to read off --
[../rationale/02-no-aseity.md](../rationale/02-no-aseity.md)). The line is exactly
the is/ought seam, and it is checkable: a token is governable as a *fact* iff it is
re-derivable without authority. That is why `MISSING` is fine and `SAFE` is not,
why `NOT_REVERTIBLE` is fine and `BLOCK` is not. Not fiat -- a criterion, applied.

So the gate is neither theater nor arbitrary. It is one segment of a perimeter,
owning the one segment (the verdict type) that machines act on, drawing its line
by a re-derivability test anyone can run.

---

## 7. A refuter -- how to show this gate is wrong

A gate worth keeping must say what would falsify it. G2 fails -- and should be
changed -- if either of these is demonstrated:

> **(a) Over-tight.** If a token the gate's closed set *excludes* can be shown to
> be a re-derivable fact that asserts no authority, grants no permission, and
> expresses no score -- a fact some real verifier need genuinely requires -- then
> the closed set is too narrow, and refusing it is the over-minimalism the rubric
> §5 warns against, dressed as discipline. The remedy is not to route around G2 by
> slipping the token into a frozenset; it is to add it to SPEC §2 **first**, with a
> conformance vector, and let the set follow (the rubric §6 procedure). The
> monitor enumeration in §4.1 is precisely this case handled correctly: the tokens
> were real and re-derivable, so they were added to the governed set in the spec
> and the frozensets, not suppressed.
>
> **(b) Under-tight.** If a token the gate's closed set *admits* can be shown to
> assert authority, grant permission, or encode a graded trust score -- to be an
> ought wearing a fact's spelling -- then the set is too permissive and G2 has a
> hole. The `ALLOW`→`REVERTIBLE` fix (§4.2) is this refuter firing and being
> answered: `ALLOW` had been admissible, was shown to be a permission word, and
> was removed in favor of a re-derivable fact. The standing guard against
> recurrence is `FORBIDDEN` plus the re-derivability test of §6.

Both refuters are checkable by anyone, gate by gate, against SPEC §2 and the
frozensets, **with no appeal to the authority of this essay** -- which is the only
way a document about refusing authority is allowed to argue. If neither refuter
fires, the gate holds; if one fires, the spec changes and the code follows. The
warrant is the re-derivation, never the pen.

---

## 8. Where this essay stops

The rubric names a real failure: a document that grows past the point where it
makes the gate *operable* is over-minimalism's other face, optimizing the
description over the thing ([../scope-discipline.md](../scope-discipline.md) §5).
This essay has done what the one-page rubric could not in three sentences -- grounded
G2 in `verdict.py`'s `governed()` and frozensets, in the two real leaks (the
monitor enumeration, the organs `ALLOW`→`REVERTIBLE` permission-class fix), in the
risk-score derivation, and in the one objection sharp enough to make the gate look
redundant or arbitrary, with the answer and a two-armed refuter. Beyond this it
would only restate. So it stops here.

The next things to read are not deeper renderings of *this* gate but its
**siblings on the perimeter**: G1 (re-derivable: no key, no clock) and G4
(advisory: zero actuation on the target) are the two G2 most often gets confused
with -- G1 because `UNVERIFIABLE` is the fact that *replaces* a trust default, G4
because the `ALLOW`/`BLOCK` leak straddled both. The spine [./README.md](./README.md)
orders them.

---

*Further reading (lineage and grounding, never warrant):
[SPEC.md](../../SPEC.md) §§2, 6 (boundary 1), 9 (UNVERIFIABLE, never TRUSTED), 11
(trust-root regress), 13 (output grammar); [CONTRIBUTING.md](../../CONTRIBUTING.md)
(the non-negotiable boundaries; "fix the spec, not the code"); the one-page rubric
[../scope-discipline.md](../scope-discipline.md) (G2 and §§3, 5, 6). Code this gate
governs: `verdict.py` (`governed()`, the channel frozensets, `FORBIDDEN`,
`VerdictError`); `monitor.py` (`report`, the `MONITOR_FILE` / `MONITOR_BASELINE`
emission sites); `organs.py` (`gate`, the `REVERT` emission sites that replaced
`ALLOW`/`BLOCK`); `membrane.py` (the `LATTICE` / `COHERENCE` / `CORROBORATE` /
`AUDIT` emission sites). Rationale siblings (illumination, not warrant):
[../rationale/01-is-ought-seam.md](../rationale/01-is-ought-seam.md),
[../rationale/02-no-aseity.md](../rationale/02-no-aseity.md),
[../rationale/04-spoken-for.md](../rationale/04-spoken-for.md),
[../rationale/06-aleph.md](../rationale/06-aleph.md).*
