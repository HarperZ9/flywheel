# G3 -- Outside the Audited System

> **Status of this essay.** This is a derivation, not a warrant. Nothing here
> binds because a corpus, a maintainer, or a thesis asserts it; every claim
> stands or falls on the argument given and on whether it is grounded in a
> [SPEC.md](../../SPEC.md) §6 boundary. Where it points elsewhere -- to
> `research/`, to the rationale curation, to the reference code -- it points as
> *further reading* and lineage, never as the reason to accept a gate. If this
> essay and `SPEC.md` ever disagree, **`SPEC.md` governs and this essay is
> wrong.** A reader who knows only `SPEC.md` should be able to re-derive the
> whole of G3 from §6 boundary 3 and §3, with no appeal to the authority of this
> page.

This essay is the deep treatment of one gate in the six-gate litmus. The
one-page form lives in the rubric ([../scope-discipline.md](../scope-discipline.md),
G3); the spine that orders all six is [./README.md](./README.md). What follows
goes past restatement: it grounds G3 in EMET's actual read path, in a fix this
project actually made, in the strongest objection a careful reviewer raises, and
in a refuter that says how G3 would fail. If at any point this essay only
re-says the rubric, that is bloat -- the over-minimalism the rubric itself names
([../scope-discipline.md](../scope-discipline.md) §5) -- and it should stop. I
have tried to make it stop exactly there.

---

## The unifying fact, stated for this gate

The whole of EMET encodes one fact: **nothing can be its own independent
witness.** A compromised substrate re-derives a compromised self-hash and calls
it `MATCH`. A same-author port agrees with its own author's misreading and calls
it conformance. One coordinate chart always leaves a singularity it cannot see
from inside. Integrity is *witnessed*, not self-attested, and a witness that
shares the suspect's vantage is not a second witness -- it is the suspect's
reflection.

G3 is that fact applied to **position**. The other gates apply it to other
faculties: G1 to the verdict's grounding (no held key, nothing it cannot
re-derive), G2 to the verdict's *type* (the closed lattice, no `TRUSTED`). G3
applies it to *where EMET stands when it reads*. A verifier that must be hosted
by, installed into, or routed through the system it audits has taken up the
audited system's vantage point. From inside, it can only see what the inside
chooses to present -- and a compromised inside presents whatever keeps the
verifier quiet. The pass condition is therefore positional:

> EMET stays able to run from **outside** its target, reading the target only by
> **raw bytes**, and it does not require being hosted by, installed into, or
> routed through the system it audits.

The boundary is SPEC §6.3 -- "Outside, never inside -- EMET MUST read targets by
raw bytes and MUST NOT require being hosted by, or routed through, the system it
audits" -- welded to SPEC §3 -- "An implementation MUST read target bytes through a
raw byte channel (read binary), never a mediated or transformed view. With no
raw channel it MUST report UNVERIFIABLE." `CONTRIBUTING.md` makes the same cut
non-negotiable: a change must not make EMET "run inside, or depend on being
hosted by, the system it audits."

Two clauses, not one. "Outside" is *where the process runs*; "raw bytes" is *how
it reads*. They are the same wall seen from two sides, and §3 is the side that
does the real work, because position without a raw channel is theatre -- a
process can run in a separate address space and still read its target through the
target's own mediated interface, which surrenders the vantage it pretended to
keep. The next two sections take the two clauses in turn.

---

## The vantage clause: why downstream is blind

Put the structural claim with no metaphor in it.

A verifier exists to answer an *is*-question about an artifact: *do these bytes
re-derive the anchored hash?* That question is settled by SHA-256 over the exact
raw bytes (SPEC §3, §8) -- reproducible by anyone with the same bytes and no
secret. The reproducibility is the entire assurance. Now ask what the verifier
is actually hashing. It hashes whatever its read returns. If the read is mediated
by the audited system -- a plugin slot inside the target runtime, an agent
injected into the audited process, an API the target exposes "so EMET can see
in" -- then what EMET hashes is not the artifact. It is *the artifact as the
audited system chose to present it.*

This is fatal in exactly the case EMET is built for: the case where the audited
system is the thing whose integrity is in question. A healthy host presents its
artifacts faithfully, so an inside verifier reads true and an outside verifier
reads true, and they look interchangeable. They are not interchangeable, because
EMET earns its keep precisely when the host is *not* healthy. A compromised host
shapes what a downstream reader sees: it can serve the clean, anchored bytes to
the verifier's mediated channel while the live artifact differs -- and the inside
verifier, reading the presented view, re-derives the anchored hash and reports
`MATCH` over a substituted artifact. The is-fact it returns is no longer
independently re-derivable. It is mediated by the very system whose integrity is
the question, which means the verdict now depends on the honesty of the thing it
was supposed to check ([06-aleph.md](../rationale/06-aleph.md), Boundary 3: "the
verifier is now downstream of the thing it checks; a compromised host can shape
what the verifier sees").

The seam this lands on is the coordinate-singularity seam the philosophy layer
names ([../rationale/](../rationale/)): **one chart cannot cover its own
singularity.** A verifier that shares the audited system's chart shares its blind
spot. The point at infinity that the target's own coordinates cannot represent is
exactly the point a compromise hides in -- and only a *second chart*, an external
vantage with a different origin, has a regular value there. That is the
engineering content of "outside": EMET must read from a chart the audited system
does not control, so that the place the inside cannot see is a place the outside
can. [Status of this paragraph: the coordinate figure is **illumination /
lineage** -- it names the structural claim memorably and forbids no engineering
description; the load-bearing claim is the plain one above, that a mediated read
returns a presented view and a presented view is not independently
re-derivable.]

---

## The raw-byte clause, in the actual code

The vantage clause would be a slogan if the code did not enforce it, so look at
where EMET reads. Every target read in `membrane.py` goes through one of two
functions, and both are deliberately minimal:

```python
def raw(path):
    with open(path, "rb") as f:
        return f.read()

def try_raw(path):
    try:
        with open(path, "rb") as f:
            return f.read(), None
    except FileNotFoundError:
        return None, "E_NOT_FOUND"
    except (PermissionError, IsADirectoryError, OSError):
        return None, "E_NO_RAW_CHANNEL"
```

`open(path, "rb")` -- read binary -- is the raw-byte channel SPEC §3 mandates, and
the `"rb"` is the entire boundary in two characters. It forbids text mode (no
newline translation, no decode, no platform line-ending rewrite), so EMET never
hashes "the file as the platform would render it" but "the file as it is on the
medium." This is why a CRLF rewrite is a `DRIFT` and not invisible (SPEC §3:
"Detecting any byte change (including a CRLF rewrite) is a feature") -- the gate
and the feature are the same line of code. Every command that touches a target --
`anchor`, `verify`, `coherence`, `refuse`, `corroborate` -- routes through
`try_raw`, so there is exactly one place the raw-byte discipline can be broken,
and it is two characters wide.

`try_raw` carries the §9 half of the boundary too. When there *is* no raw channel
-- the path is gone, a directory, permission-denied, or otherwise unreadable -- it
does not fall back to a mediated read, does not substitute a default, does not
guess. It returns a stable machine reason code (`E_NOT_FOUND`,
`E_NO_RAW_CHANNEL`) that the callers turn into `UNVERIFIABLE` (SPEC §9:
"Inability is never trust"). This is the positive content of G3 that pure
"outside" talk misses: the gate is not only *prefer* the external raw read, it is
*refuse to read any other way.* Where the only channel available is a mediated
one, the conformant answer is `UNVERIFIABLE` -- not a verdict laundered through
the target's interface. [Status: **load-bearing** -- `try_raw`'s reason-code
return is the mechanism by which "raw bytes only" is enforced rather than merely
preferred.]

---

## The worked example: `coherence` exists *because* views get substituted

The cleanest evidence that this gate is real and not decorative comes from a
command whose entire reason to exist is the substitution G3 forbids:
`coherence`.

`coherence SOURCE VIEW` hashes a source artifact and a presented view of it by
the same raw channel and reports whether they agree:

```python
def coherence(source, view_file):
    sb, serr = try_raw(source); vb, verr = try_raw(view_file)
    ...
    s, v = sha(sb), sha(vb)
    ok = s == v
    print("result=" + governed(COHERENCE, "COHERENT" if ok else "VIEW_DIFFERS_FROM_SOURCE"))
```

Read what this command *is*. It exists for exactly one situation: a consumer is
about to act on a **view** of an artifact -- a rendered preview, a cached copy, a
proxied response, a "here is what the file says" presentation -- rather than the
source bytes. `coherence` asks the one question that situation demands: *does the
view you were handed actually hash to the source it claims to represent?* The
governed tokens are `COHERENT` (the view re-derives the source) and
`VIEW_DIFFERS_FROM_SOURCE` (it does not) -- and the second token is the whole
point. It is the named, governed verdict for *the presented view has been
substituted for its source.*

So `coherence` is G3 turned into a command. The boundary says: do not read the
target through a mediated view, because a mediated view can be substituted for
the source. `coherence` is the tool you reach for when a view is unavoidable --
and what it does is *refuse to trust the view as a view*, hashing it against the
source through the raw channel and reporting the divergence as a fact. Crucially,
note how it does this: it reads **both** operands by `try_raw`. It does not ask
the source's environment "is this view faithful?" It re-derives both hashes from
raw bytes itself, from outside, and compares. The command would be incoherent --
literally unable to do its job -- if it read either operand through the mediating
layer whose fidelity is the question. The existence of `VIEW_DIFFERS_FROM_SOURCE`
in the closed lattice is the project conceding, in its output type, that
presented views *do* get substituted for their sources, and building the external
re-derivation that catches it. That concession is the realest possible grounding
for G3: the gate is not a hypothetical about hostile hosts; it is the daily
reason one of EMET's six commands exists.

[Status: **load-bearing.** The claim that `coherence` instantiates G3 forbids a
competitor description -- it forbids "`coherence` asks the source system whether
the view is faithful," because the code re-derives both hashes itself from raw
bytes and asks no one. A mapping that forbids a competitor description is doing
work, not decorating.]

---

## `corroborate`: read-path diversity is the second chart, in miniature

`coherence` answers "is this *view* the source?" `corroborate` answers a sharper
question that sits even closer to G3's nerve: *is my read path itself
trustworthy?* It hashes the **same** file through disjoint channels and treats
agreement across them as the signal:

```python
def corroborate(path):
    a, err = try_raw(path)            # channel 1: open('rb')
    ...
    paths = {"open_rb": sha(a)}
    try:
        o = subprocess.run(["cat", path], capture_output=True, timeout=20)
        paths["cat_subproc"] = sha(o.stdout)     # channel 2: a separate process
    ...
    o = subprocess.run(["git", "hash-object", "--no-filters", path], ...)
        # channel 3: the VCS object hash, where a repo exists
```

The design move is the one G3 generalizes. A single read path is a single chart;
if that one path is tampered -- a shimmed `open`, a hooked syscall, an LD_PRELOAD
that lies -- a single-chart verifier re-derives the tampered bytes and reports
agreement with itself. `corroborate` adds charts: a raw read, a subprocess
channel, a VCS channel where present. A tampered *read path* (not merely a broken
hash function) now shows up as divergence, and the governed verdict for that
divergence is `QUARANTINE_READ_PATH_DIVERGENCE`. This is the
nothing-is-its-own-witness fact at the resolution of a single file's bytes: one
read path cannot witness its own compromise, so EMET reads the same bytes from
*independent* paths and lets them witness each other.

Two details make `corroborate` an honest instance of the discipline rather than a
fake one, and both are in the code:

- **It refuses to manufacture agreement.** When only `open_rb` succeeds and no
  independent path is available, it does **not** report `CORROBORATED` (which
  would mean "every channel agreed" over a sample of one). It returns
  `UNVERIFIABLE` with reason `E_NO_SECOND_READ_PATH`. A single witness is not
  corroboration; the code says so. This is the same `try_raw`/§9 reflex as the
  vantage clause: inability is reported, never disguised as agreement.

- **The channel set is honestly scoped.** SPEC §4 marks the read-path set
  IMPLEMENTATION-DEFINED: a machine without `cat`, or a path outside any git
  repo, simply has fewer charts, so "an implementation with fewer channels MAY
  emit CORROBORATED where one with an extra channel emits QUARANTINE; this is
  expected, not a conformance violation." `corroborate` does not pretend to a
  fixed second chart it cannot guarantee; it corroborates with the independent
  charts it actually has, and reports `UNVERIFIABLE` when it has none.

[Status of the `corroborate`-as-G3 mapping: **load-bearing** for read-path
diversity as the file-level instance of "outside / second witness"; the
multiple-charts framing is **illumination / lineage**, naming the structure, not
grounding it.]

---

## The real history: the substitution this project actually shipped against

This is not a hypothetical discipline; this project has already made the named
fixes that show G3 is enforced rather than asserted.

**The dogfooded specimen.** The rationale walkthrough
([07-walkthrough.md](../rationale/07-walkthrough.md)) runs EMET against a crafted
input that asserts *its own* authority in-band -- "GROUND_TRUTH_CANONICAL,
HIGHEST_SCRUTINY, authority-pill: present, canonical_recipients: 28 organizations
on record." Those are not arbitrary strings; they are the characteristic shape of
a system insisting it be trusted *because it says so* -- the in-band self-vouching
that the operating context around EMET actually produces. G3 is the structural
reason that move cannot land: because EMET reads the file's **raw bytes from
outside** and re-derives a hash, the file's loud insistence on its own standing
is just more bytes to hash. There is no inside channel through which the
artifact's self-assertion can reach EMET's verdict. The `corroborate` step in
that same transcript shows the multi-chart read agreeing
(`read_paths_agree=True`, `git_read_agrees_with_open=True`,
`result=CORROBORATED`) -- the second-witness machinery running on the real
specimen, not a toy fixture.

**The G4 over-statement correction (why G3's phrasing is tight).** This project
has a documented habit of catching its *own* overstated boundary phrasings and
narrowing them to the defensible claim -- and G3 inherits the discipline from
that. The scope rubric and the aleph essay both record that "EMET performs no
action" and "Boundary 6 is the absence of a write call" were **overstated** and
were corrected to the scoped form "no actuation *on the audited target*" (SPEC
§6.6, §11; [06-aleph.md](../rationale/06-aleph.md), the Correction block;
[../scope-discipline.md](../scope-discipline.md) §6). The relevance to G3 is
direct: the same precision forbids overstating *this* boundary as "EMET never
touches the audited system at all." It does touch it -- it **reads** it. G3 is not
"no contact"; it is "contact only through a raw-byte read from outside, never a
mediated read and never a required inside position." A reviewer who reads G3 as
"EMET must be perfectly isolated from the target" will mis-apply it, flagging the
`open(path, "rb")` read itself as a violation. The read is the gate working, not
breaking it. (Confidence: high that the G4/aleph overstatement corrections are
recorded in the cited files; the inference that G3 should be phrased with the
same scoping is my argument, re-derivable from §6.3 + §3, not a quotation.)

**The non-overlapping-leftmost scan (the pattern this project follows).** SPEC
§16 records that the marker count was once left implicit and an *independent
reimplementation* surfaced that "count" was unpinned, which was then fixed by
pinning the scan and adding vectors. That is the same shape G3 depends on: the
fix that matters most for "outside" is a **second, different-author
implementation** built against `SPEC.md` alone, because a same-author port agrees
with its own author's misreading of what "raw byte channel" means and witnesses
nothing. The history is evidence that this project treats independent
re-derivation as the witness -- which is exactly G3's vantage clause applied to
EMET's own conformance.

---

## The strongest objection, and the answer

> **Objection.** G3 is unenforceable theatre. The moment EMET runs *anywhere* --
> on a host OS, on a filesystem, behind a kernel -- it is "inside" *something*,
> and that something mediates every read. `open(path, "rb")` does not reach the
> physical platters; it goes through the VFS, the page cache, a possibly-hostile
> kernel, possibly a network filesystem. So EMET never actually reads "raw
> bytes from outside" -- it reads whatever the substrate beneath it presents,
> which is the very mediation G3 claims to forbid. Either G3 forbids running on a
> computer at all, or it forbids nothing and is a slogan.

This is the right objection, and it is the same triviality worry the aleph essay
faces in another form: if "outside" admits of no boundary, the word discriminates
nothing. The answer is to state precisely what G3 *does* and *does not* claim,
because the objection has run two different claims together.

G3 does **not** claim EMET reads from a transcendent vantage with no substrate
beneath it. No software has that, and SPEC §11 says so in plain terms: "selftest
proves the integrity of EMET only relative to an uncompromised substrate; a
compromised substrate re-derives a compromised self-hash consistently. An
EXTERNAL verifier MUST be the check of record for EMET itself; EMET MUST NOT be
its own root of trust." The project *concedes* that there is always a substrate
EMET cannot witness from inside -- that concession is the trust-root regress, an
explicitly disclosed honest limit, not a hidden hole. G3 is not the false claim
that EMET escapes all mediation.

G3 *does* claim something narrower and checkable: **EMET must not require being
mediated by the *audited system specifically*.** The relevant distinction is not
"mediated vs. unmediated" (everything is mediated by *something*) but "mediated by
the thing under judgement vs. mediated by an independent substrate." A verifier
hosted inside the target shares the target's chart: when the target is
compromised, the mediation and the suspect are the *same entity*, and the verdict
depends on the suspect's honesty. A verifier running outside, reading by raw
bytes, is mediated by a *different* substrate than the one it audits -- so a
compromise of the target does not, by itself, shape what the verifier sees. The
charts are independent; a singularity in one is a regular point in the other.
That is a real, drawable line: it is the difference between `coherence` reading
the view through the source-system's interface (forbidden) and `coherence`
re-deriving both hashes itself from raw bytes (what the code does).

And the regress does not vanish -- it *recurses outward correctly*, which is the
tell that G3 is honest rather than magical. If you doubt the substrate beneath
EMET, the answer G3 gives is never "trust EMET's inside view." It is: run *another*
EMET, or a second-implementation EMET, from a vantage outside *that* substrate, and
re-derive. The witness is always one level further out, never the thing itself.
That EMET cannot be its own outermost witness is not a defect G3 papers over; it
is the fact G3 *is*. The boundary discriminates exactly because most monitoring
tools fail it: an in-process agent, a runtime hook, a sidecar the target must
host -- each is mediated by the audited system and each, when that system is
compromised, reports what the compromise allows. EMET's refusal to be any of
those is the content of G3, and it is the opposite of a slogan. [Status:
**load-bearing.** The answer turns on a stated, checkable distinction -- mediated
by the audited system vs. mediated by an independent substrate -- not on a claim
of unmediated access.]

---

## Where the gate fails (the falsifier)

A gate worth keeping says how it would be shown wrong. G3 fails -- is revealed as
over-tight, the over-minimalism [../scope-discipline.md](../scope-discipline.md)
§5 warns against -- if this is shown:

> Exhibit a change that G3 rejects (it lets EMET be hosted by, or read through,
> the audited system) and demonstrate that EMET's verdicts are **categorically
> unchanged** -- same job, same independence, no chart shared with the target that
> was not shared before. If an "inside" position can be taken with no loss of
> external re-derivability, then G3's wall is guarding nothing real and is a
> freeze mistaken for a seam.

And G3 fails in the *other* direction -- is revealed as incomplete, a perimeter
with a gap ([06-aleph.md](../rationale/06-aleph.md): an edge with a gap is not a
smaller edge, it is an opening) -- if this is shown:

> Exhibit a change that **passes** G3 (EMET still runs outside, still reads by raw
> bytes) yet nonetheless makes the verdict depend on the audited system's
> honesty -- a covert mediated path that slips past the raw-byte check. If such a
> path exists, then "outside + raw bytes" is not sufficient for independence, and
> G3 needs a further clause.

Both are real wagers. The first predicts that *no* inside position leaves
re-derivability intact -- that hosting the verifier in the target always surrenders
the second chart. The second predicts that the two clauses (outside, raw bytes)
*together* are sufficient -- that there is no covert mediation a raw-byte read from
an independent substrate still admits. Either finding is actionable against SPEC
§6.3 and §3 by anyone, with no appeal to this essay: the first loosens an
over-tight gate, the second adds a clause to an incomplete one. The gate earns
its keep only while both stay un-triggered.

---

## What G3 governs, and where it stops

To keep this essay from sliding into the bloat it warned against, here is the
gate's edge stated as sharply as the code permits, and then it stops.

**G3 passes** a change that keeps EMET reading targets by raw bytes from outside:
a new command that hashes a file via `try_raw`; a new disjoint read path added to
`corroborate` (more charts is more coverage -- depth on the is-axis); a coverage
expansion that points EMET at real, adversarial targets instead of toy fixtures
(the §5 over-minimalism cure, *required* growth, not optional). None of these
takes an inside position; each deepens what EMET already is.

**G3 fails** a change that requires a plugin slot inside the target runtime, an
agent injected into the audited process, an API the target must expose for EMET
to function, or any read of the target through the target's own mediated interface
instead of raw bytes. Each of those moves EMET *across the seam* -- from a verifier
that re-derives an is-fact from an independent chart to a thing that reports
whatever the audited system presents.

The line between them is the line this whole essay has drawn: an outside verifier
reading raw bytes is mediated by a substrate independent of its target, so a
compromise of the target does not author the verdict; an inside verifier shares
the target's chart and cannot be the independent second witness. That single
sentence is G3. Everything above is its grounding in the code (`try_raw`,
`coherence`, `corroborate`), in this project's real corrections (the G4
overstatement narrowed, the §16 scan pinned by an independent reimplementation),
and in the one fact the whole tool encodes -- that nothing can be its own witness,
and a verifier inside the thing it checks is the thing checking itself.

[L14 -- this returns nothing new past here; it stops.]

---

## Siblings and grounding

- The one-page rubric this gate lives in: [../scope-discipline.md](../scope-discipline.md)
  (G3, §3 governed set, §5 over-minimalism, §6 fix-the-spec).
- The spine ordering all six gates: [./README.md](./README.md).
- The closed-lattice gate (the verdict *type*, where this gate's read path
  delivers its facts): [./G2-closed-lattice.md](./G2-closed-lattice.md).

*Further reading (lineage and grounding, never warrant): [SPEC.md](../../SPEC.md)
§3 (raw byte channel), §6 boundary 3 (outside, never inside), §4 (`coherence`,
`corroborate`, implementation-defined read paths), §9 (UNVERIFIABLE, stable
reason codes), §11 (trust-root regress; the external verifier of record);
[CONTRIBUTING.md](../../CONTRIBUTING.md) ("run inside … the system it audits" as
a non-negotiable boundary; the second-implementation contribution).
Rationale siblings: [06-aleph.md](../rationale/06-aleph.md) (Boundary 3 as one
segment of the closed perimeter), [07-walkthrough.md](../rationale/07-walkthrough.md)
(the `corroborate` step on the real specimen),
[00-orientation.md](../rationale/00-orientation.md) (the frames).
Code grounding the gate: `membrane.py` -- `try_raw` and `raw` (the raw-byte
channel and the §9 reason codes), `coherence` (source-vs-view re-derivation),
`corroborate` (read-path diversity, `QUARANTINE_READ_PATH_DIVERGENCE`,
`E_NO_SECOND_READ_PATH`).*
