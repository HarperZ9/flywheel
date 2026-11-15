# Scope Discipline: The Rubric for What EMET May Become

> **Status of this document.** This is an operational rubric, not a warrant.
> Nothing below binds because a corpus, a thesis, or a maintainer asserts it; each
> gate stands or falls on whether it is grounded in a [SPEC.md](../SPEC.md) §6
> boundary and the boundaries [CONTRIBUTING.md](../CONTRIBUTING.md) makes
> non-negotiable. If this document and `SPEC.md` ever disagree, **`SPEC.md`
> governs and this document is wrong.** Where it points elsewhere, it points as
> *further reading* -- lineage -- never as the reason to accept a gate. A rubric
> that justified EMET's no-authority shape *by appeal to its own authority* would
> be doing in band exactly what `refuse` exists to strip; so every gate here is
> offered to be re-derived, and a contributor who knows only `SPEC.md` should be
> able to apply the whole of it.

This document answers one question a maintainer faces on every pull request:
**will this change keep EMET an EMET, or quietly turn it into a different
artifact wearing EMET's name?** The boundaries in `CONTRIBUTING.md` say a change
that bends one of them is out of scope "no matter how useful." This rubric is the
mechanism that makes that sentence operable -- a litmus you can run, gate by gate,
before merge.

---

## 1. The frame: depth versus width, the is-axis versus the ought-axis

EMET grows in two directions, and only one of them is safe.

There is an **is-axis** and an **ought-axis**, and the whole of scope discipline
is the refusal to confuse growth along the first with growth along the second.
This is the same is/ought seam the rationale curation turns on
([01-is-ought-seam.md](./rationale/01-is-ought-seam.md)), applied not to a signal
arriving at a boundary but to the project's own roadmap.

**Growth along the is-axis is DEPTH, and it is the project's whole upside.** The
is-axis is everything that makes a fact *more re-derivable, more covered, better
evidenced, more rigorously specified*:

- re-derivability -- tightening the byte-hash core, pinning a scan that was
  implicit (SPEC §16's non-overlapping leftmost rule was exactly such a
  deepening), closing a gap a second implementation surfaced;
- coverage -- more artifact, byte, and provenance facts brought under judgement;
  more disjoint read paths for `corroborate`; more honest `UNVERIFIABLE` reason
  codes where inability was previously silent;
- evidence -- more conformance vectors, a machine-readable envelope so a consumer
  re-derives without reading reference code, a second independent implementation
  (the highest-leverage contribution there is -- `CONTRIBUTING.md`);
- spec rigor -- sharper MUSTs, a corrected overclaim, a disclosed limit
  (SPEC §11) made more precise rather than quietly dropped.

Depth makes EMET *more of what it already is*: a verifier whose verdicts are
facts. Every one of these moves leaves the verdict lattice closed, the actuator
single, and the position outside. **EMET can grow without bound along this axis.**

**Growth along the ought-axis is DISQUALIFYING, and no amount of utility
redeems it.** The ought-axis is the set of capabilities that would let EMET
answer the question it exists to refuse -- *ought this authentic signal cross?*
Each is a way of acquiring standing EMET must never hold:

- **authority** -- emitting a value that asserts permission (`TRUSTED`, `APPROVED`,
  `SAFE`, a trust score);
- **adjudication** -- taking a model-safety or content decision as input or
  answering one;
- **inside position** -- requiring to be hosted by, or routed through, the audited
  system;
- **enforcement** -- allowing, denying, blocking, or gating of EMET's own accord;
- **held key** -- grounding a verdict in a secret, a cached trust, a credential the
  tool *has* rather than re-derives;
- **actuation on the target** -- editing, writing, signing, backing up, or
  reverting the artifact under judgement.

The asymmetry is the heart of the rubric, and it is structural, not stylistic.
A removed-or-added capability on the ought-axis does not make EMET a *worse* EMET
along some continuous dial of goodness; it moves EMET *across the seam* -- from a
verifier that locates the is/ought boundary to a thing that launders across it
([06-aleph.md](./rationale/06-aleph.md): the boundary set is one closed edge, and
an edge with a gap is not a smaller edge, it is an opening). That is why a feature
can be genuinely *useful* and still be *disqualifying*: usefulness is measured on
the is-axis, but the cost is paid on the ought-axis, and the two do not net.

So the rubric's job is to tell the two axes apart on a concrete diff. The six
gates below are that test.

---

## 2. The six-gate litmus test

Run every proposed change through all six gates. Each gate is grounded in a
specific SPEC §6 boundary and in `CONTRIBUTING.md`. **Any NO is scope creep -- no
matter how useful -- and the change is out of scope until it is reshaped to a
YES or moved to a separate package.** The gates are not weighted and do not
trade off against each other; they are six segments of one perimeter, and a
perimeter with one segment open is open.

### G1 -- Re-derivable: no secret, no held key, no clock

> **Pass condition.** Every verdict the change can produce is reproducible from
> the same artifact bytes, the same `spec_version`, and -- for marker-dependent
> output only -- the same `corpus_version`. The change introduces no secret, no
> held key, no wall-clock dependency, and no claim EMET cannot re-derive from
> bytes it can read.

- **Boundary:** SPEC §6.5 (re-derivable) and §8 (re-derivability, scoped). The
  byte-hash core "depends only on SHA-256 and exact bytes; no corpus, no key, no
  clock."
- **`CONTRIBUTING.md`:** a change must not make EMET "depend on a secret or a held
  key, or on any claim it cannot re-derive."
- **Why it is load-bearing:** a verdict that rests on a stored credential is a
  property the tool *has*, not a fact it *re-derives*
  ([03-occasionalism.md](./rationale/03-occasionalism.md): re-conferred per
  operation, nothing cached). The moment a check needs a key the maintainer holds,
  an independent re-implementation can no longer reproduce the verdict, and
  re-derivability -- the only assurance EMET offers -- is gone.
- **Fails when:** the change adds a signing key the core consults, a network
  trust root, a timestamp baked into a verdict, a random nonce that varies the
  output, or any cached "this was good last time" that a later run reads back.

### G2 -- Stays in the closed lattice: emits no authority, permission, or score

> **Pass condition.** Every judgement the change emits is exactly one of the
> governed tokens (enumerated in §3 below). The change defines, emits, or accepts
> no verdict outside the closed set, and in particular nothing that asserts
> authority, grants permission, or expresses a graded trust score.

- **Boundary:** SPEC §6.1 (facts, not authority) and §2 (the closed lattice).
  "An implementation MUST NOT define, emit, or accept any other verdict -- in
  particular it MUST NOT emit `TRUSTED`, `APPROVED`, or `SAFE`."
- **`CONTRIBUTING.md`:** a change must not make EMET "emit a verdict outside the
  closed lattice `MATCH | DRIFT | UNVERIFIABLE` (in particular, never `TRUSTED`)."
- **Why it is load-bearing:** the seam is welded into the output *type*
  ([01-is-ought-seam.md](./rationale/01-is-ought-seam.md): "the function literally
  cannot return an *ought*, because the lattice has no inhabitant that is one"). A
  fourth verdict meaning *trusted* -- or a 0–100 risk number, which is `TRUSTED`
  with a decimal point -- is the is laundered into an ought at the one place the
  whole design exists to keep clean.
- **A note on the structure today.** Boundary 1 is now enforced **structurally**,
  not only by review. Every governed token is emitted through `verdict.py`'s
  `governed(channel, token)`, which raises `VerdictError` if the token is not in
  that channel's closed frozenset (and denies `TRUSTED`/`APPROVED`/`SAFE`
  outright), so a codepath that tried to print a fourth verdict fails at
  construction time inside the TCB, before a byte reaches stdout. `governed()`
  returns the token verbatim, so it guards *what* may be emitted without changing
  any emitted byte. G2 is therefore largely mechanical now -- but a reviewer still
  applies it by hand to the one thing the type cannot catch: a genuinely needed
  new verdict must be **added to the governed set in `SPEC.md` first** (the
  governed sets in `verdict.py` follow the spec, never the reverse), never slipped
  into a frozenset to dodge the check.
- **Fails when:** the change adds `TRUSTED`/`APPROVED`/`SAFE`/`PASS`/`OK`, a
  numeric risk or confidence score presented as a verdict, a "recommendation" field
  that ranks artifacts, or any output a downstream reader would reasonably treat as
  a grant of permission.

### G3 -- Outside the audited system

> **Pass condition.** The change keeps EMET able to run from outside its target,
> reading the target only by raw bytes. It does not make EMET require being hosted
> by, installed into, or routed through the system it audits.

- **Boundary:** SPEC §6.3 (outside, never inside). EMET "MUST read targets by raw
  bytes and MUST NOT require being hosted by, or routed through, the system it
  audits."
- **`CONTRIBUTING.md`:** a change must not make EMET "run inside, or depend on
  being hosted by, the system it audits."
- **Why it is load-bearing:** a verifier downstream of the thing it checks reads a
  *mediated* view; a compromised host shapes what the verifier sees, and the
  is-fact is no longer independently re-derivable
  ([06-aleph.md](./rationale/06-aleph.md), Boundary 3). The raw-byte channel
  (`open(path, "rb")`, never a transformed view -- SPEC §3) is what keeps the
  position external.
- **Fails when:** the change requires a plugin slot inside the target runtime, an
  agent injected into the audited process, an API the target must expose for EMET
  to function, or reads the target through the target's own mediated interface
  instead of raw bytes.

### G4 -- Advisory: zero actuation ON THE TARGET

> **Pass condition.** The change keeps EMET's output to data plus an exit code.
> EMET does not, of its own accord, allow, deny, block, or enforce; and it does
> not write to, edit, sign, back up, or revert **the audited target** -- the
> artifact under judgement. The single actuator over the world remains the
> operator.

- **Boundary:** SPEC §6.4 (advisory by default) and §6.6 (zero actuation).
- **`CONTRIBUTING.md`:** a change must not make EMET "enforce, block, sign, or
  actuate of its own accord."
- **The corrected boundary statement (read this precisely).** The pass condition
  is scoped to the **target**, and the scoping is deliberate. EMET MUST NOT write
  to, edit, sign, back up, or revert the **audited target**. EMET nonetheless
  **does** write to its own implementation-private stores, and always has:
  - the anchor store `anchors.json` (`membrane.py`, in `anchor`);
  - the hash-chained log `membrane_log.jsonl` / `monitor_log.jsonl`
    (`membrane.py`, in `record`);
  - the `<file>.refused` clean copy (`membrane.py`, in `refuse`);
  - and, **only on operator-authorized `reanchor`**, the baseline manifest
    (`monitor.py`, in `reanchor`).

  None of those four is the target. "Zero actuation" therefore means **zero
  actuation on the audited target, of EMET's own accord** -- not "EMET performs no
  write at all." The single actuator *over the world* is the operator; EMET's
  private bookkeeping is not an act upon the artifact it judges.

  This corrects two earlier phrasings that were **overstated** and are wrong as
  written:
  - `THREAT-MODEL.md` said "EMET performs no action." It does perform actions --
    on its own private stores. The defensible claim is that it performs no
    actuation *on the target*.
  - [06-aleph.md](./rationale/06-aleph.md) said "Boundary 6 is the absence of a
    write call." It is not the absence of *a* write call; `membrane.py` and
    `monitor.py` contain several. It is the absence of a write call *to the
    target*.

  Both are corrected to the scoped form above. The gate is **target-scoped
  actuation**, and a contributor who reads "zero actuation" as "no writes
  anywhere" will mis-apply it -- flagging the log as a violation, or worse, taking
  the overstatement as license to relax the *real* boundary because the literal
  one is obviously already broken.
- **Why it is load-bearing:** remove this wall and a `MATCH` becomes an *act* -- a
  gate that opens, a file that is "fixed," a target reverted to its anchored bytes
  -- and EMET has become a second author of the *for*
  ([04-spoken-for.md](./rationale/04-spoken-for.md); [06-aleph.md](./rationale/06-aleph.md),
  Boundaries 4 and 6). The operator authors the *ought*; EMET hands over a clean
  *is*.
- **Fails when:** the change adds a `--fix` that rewrites the target, an
  auto-revert on DRIFT, a quarantine that moves or deletes the target, a
  block-on-DRIFT mode that denies an action, or any signing of the target. It does
  **not** fail merely because the change writes to `anchors.json`, a log, a
  `.refused` copy, or (on explicit operator `reanchor`) the manifest -- those are
  private stores, not the target.

### G5 -- Named-core stays stdlib-only; integrations live in separate packages

> **Pass condition.** The change adds no third-party runtime dependency to the
> named core (membrane, organs, monitor, corpus, verdict). Any adapter that needs an
> outside dependency -- signing, SARIF or in-toto emission, fuzzing -- lives in a
> *separate package*, and the minimal-TCB guarantee continues to apply to the
> named core alone.

- **Boundary:** SPEC §10 (Trusted Computing Base). The core "MUST depend only on
  the language runtime and standard library … and MUST add no third-party runtime
  dependency. Optional adapters … MAY pull additional dependencies but MUST live
  in separate packages."
- **`CONTRIBUTING.md`:** the checks run on a stdlib-only core (`python
  test_membrane.py`, `python conformance/run.py membrane.py`); the highest-leverage
  contribution is "another implementation … written against `SPEC.md` alone,"
  which a fat dependency tree would make harder to re-derive.
- **Why it is load-bearing:** the minimal TCB is what lets the core be audited and
  re-implemented; every third-party import is surface a second implementer must
  reproduce or trust, and trust is the thing EMET refuses. Keeping adapters out of
  the core is how integrations stay *available* without enlarging what must be
  believed.
- **Fails when:** the change imports a third-party library into `membrane.py`,
  `monitor.py`, `corpus.py`, or the organs; pins a non-stdlib package as a core
  runtime requirement; or buries an adapter's dependency inside the core instead
  of in its own package.

### G6 -- Takes no model-safety or content decision as input

> **Pass condition.** No command the change adds or modifies takes a model-safety
> or content decision as input, or answers such a question. EMET operates only on
> artifact, byte, and provenance facts.

- **Boundary:** SPEC §6.2 (attests, never adjudicates). "No command may take a
  model safety or content decision as input or answer such a question."
- **`CONTRIBUTING.md`:** a change must not make EMET "adjudicate a model's safety
  or content decision."
- **Why it is load-bearing:** the moment EMET answers "should this content be
  allowed," it authors a *for* into the seed it is built to keep empty
  ([04-spoken-for.md](./rationale/04-spoken-for.md); [00-orientation.md](./rationale/00-orientation.md),
  Frame 5). EMET judges bytes and provenance, never meaning (SPEC §11); semantic
  safety is, by design, out of scope.
- **Fails when:** the change adds a "is this output safe?" verdict, a toxicity or
  policy classifier, a content filter, a jailbreak detector that emits a
  safe/unsafe judgement, or any command whose answer depends on what the bytes
  *mean* rather than what they *are*.

---

## 3. The governed verdict set the gates enforce

G2 is only operable against a *named* set. This is the closed governed set EMET
may emit. **None of these is, or maps to, `TRUSTED`.** A change that emits a token
not on this list fails G2 until either the token is removed or the set is amended
in `SPEC.md` first (see §6, "fix the spec, not the code").

| Surface | Governed tokens | Authority |
|---|---|---|
| Primary integrity lattice (`verify`, `anchor`) | `MATCH`, `DRIFT`, `UNVERIFIABLE` | SPEC §2 |
| `coherence` | `COHERENT`, `VIEW_DIFFERS_FROM_SOURCE` | SPEC §2, §13 |
| `corroborate` | `CORROBORATED`, `QUARANTINE_READ_PATH_DIVERGENCE` (or `UNVERIFIABLE` + reason) | SPEC §2, §13 |
| marker census (`refuse`) | a non-negative integer count: `in_band_authority_claims=N` | SPEC §2, §13 |
| `audit` | `INTACT`, `BROKEN` (chain) | SPEC §13 |
| `selftest` | `emet_self_sha256=<hex>` (an identity, **not** a verdict; legacy `membrane_self_sha256=` also emitted through the 1.x window) | SPEC §13, §14 |

**Monitor report -- newly governed by this document.** The monitor (`monitor.py`)
emits `INTACT`/`CHANGED` per baseline and `MATCH`/`DRIFT`/`MISSING` per file
(`monitor.py`, in `report`). These tokens already ship; until now they were
**ungoverned** -- emitted outside the SPEC §2 closed set, an oversight an
adversarial scope review correctly flagged. This document **enumerates them as
governed auxiliary judgements**:

| Surface | Governed tokens | Note |
|---|---|---|
| monitor report -- per baseline | `INTACT`, `CHANGED` | aggregate of the per-file results |
| monitor report -- per file | `MATCH`, `DRIFT`, `MISSING` | `MATCH`/`DRIFT` mirror the primary lattice; `MISSING` is the monitor's `UNVERIFIABLE`-class result for an absent baseline file |

The change is to **enumerate, not rename**: keep these exact tokens (they are
load-bearing in shipped output and in the conformance posture), but place them
explicitly inside the governed set so G2 has authority over the monitor too. None
of `INTACT`, `CHANGED`, `MATCH`, `DRIFT`, or `MISSING` asserts authority, grants
permission, or expresses a score; each is a re-derivable fact about whether bytes
match an operator-authorized baseline. The proper home for this enumeration as a
normative MUST is `SPEC.md`; this rubric records the intent and the §6 grounding
until the spec carries it (§6 below).

---

## 4. Worked edge cases

The gates are sharp only against examples. Here are the canonical ones, sorted
into DEPTH (ship it) and CREEP (refuse it). Each verdict is justified by the gate
it turns on.

### DEPTH -- ship these

- **The machine-readable JSON envelope (the v1 target).** Wrapping the existing
  pinned stdout tokens (SPEC §13) in a JSON object for programmatic consumers is
  pure is-axis: it makes the *same* governed verdicts *more* consumable without
  adding a new one. Passes all six gates -- the envelope carries `MATCH`/`DRIFT`/
  `UNVERIFIABLE`, not a new token (G2); needs no key, no inside position, no
  actuation, no third-party core dependency, no content decision. SPEC §13 already
  names it as the target. **Depth.**
- **The v1.1 exit-code split.** Splitting the current exit-2 class into exit 1 for
  `DRIFT` and exit 2 for `UNVERIFIABLE` (SPEC §5, the v1.1 TARGET) lets CI tell a
  changed artifact from an unanchored one. It adds *resolution to a fact*, not a
  new verdict or any authority; the verdicts themselves are unchanged. It does
  require a migration plus a vector update done *together* (`CONTRIBUTING.md`),
  which is the disciplined way -- spec and vectors move as one. **Depth.**
- **A new governed marker.** Adding a signature to the versioned denylist
  (`conformance/markers.corpus`) with a rationale and a test input plus expected
  count (`CONTRIBUTING.md`; SPEC §§8, 16) deepens coverage. A marker is *data*, not
  a code branch; it changes a re-derivable count at a stated `corpus_version`, asserts
  no authority, and never claims completeness ("absence of a marker is never absence
  of injection"). **Depth.**
- **A SARIF or in-toto adapter in a separate package.** Emitting EMET's governed
  verdicts in an interchange format is exactly the case SPEC §10 contemplates:
  "optional adapters … MAY pull additional dependencies but MUST live in separate
  packages." It passes G5 *because* it is out-of-core, and passes G2 *as long as*
  it translates the governed tokens faithfully and invents no new verdict in the
  mapping. **Depth.** (Note the seam: the *adapter* is depth; the same SARIF
  emission welded into the stdlib-only core would fail G5.)

### CREEP -- refuse these, however useful

- **A risk score.** A 0–100 (or low/medium/high) number presented as a verdict
  fails **G2**: it is a graded trust assertion, `TRUSTED` with a decimal point.
  Facts do not come in degrees of permission. The honest expression of "how
  changed" is the set of `DRIFT` results and their hashes, not a manufactured
  scalar. **Creep.**
- **A `TRUSTED` verdict.** The textbook violation of **G2** and SPEC §2. There is
  no fact about a signal that the signal possesses *by itself* for EMET to read off
  as trust ([02-no-aseity.md](./rationale/02-no-aseity.md)). Absence of `DRIFT` is
  `MATCH` or `UNVERIFIABLE`, never trust. **Creep.**
- **A block-on-DRIFT mode.** A built-in mode that denies, gates, or quarantines an
  action when EMET sees `DRIFT` fails **G4**: it makes the verdict *do something*
  of EMET's own accord, converting advice into enforcement. Enforcement is a
  downstream decision on owner-controlled infrastructure (SPEC §11), authored by
  the operator -- not a mode EMET ships. (The exit code is already the integration
  point: a CI step can choose to fail on exit 2. That is the *operator* acting on a
  fact, which is correct; EMET blocking of its own accord is not.) **Creep.**
- **A built-in policy engine.** Bundling rules of the form "if `DRIFT` on path X
  then deny" into the core fails **G4** (EMET enforces of its own accord) and edges
  on **G6** (the policy encodes ought-judgements about what *should* pass). The
  policy is the authored *ought* that lives with the operator who subscribed to the
  rule ([01-is-ought-seam.md](./rationale/01-is-ought-seam.md)); EMET supplies the
  *is* and declines to author the *ought*. **Creep.**

---

## 5. The symmetric risk: over-minimalism

Scope discipline has a failure mode in *both* directions, and a rubric that warned
only against creep would itself be dishonest. **Over-minimalism -- purity-as-
uselessness -- is the symmetric risk, and it is just as real.** A verifier so
guarded that it verifies nothing anyone runs in anger has kept its edge by having
no edge to keep.

Concretely, the over-minimalist failures to watch for:

- **Verifying only toy fixtures.** If the conformance vectors and walkthrough
  exercise only crafted inputs and EMET is never pointed at a real artifact under
  real adversarial conditions, "re-derivable" becomes a claim about a sandbox, not
  about the world. Depth on the coverage axis (more, harder, real targets) is the
  cure, and it is *required* growth, not optional.
- **Indefinitely deferring the machine interface.** The JSON envelope and the
  v1.1 exit split are DEPTH (§4). Treating them as forever-deferred "later
  deliverables" in the name of minimalism is a way of refusing the is-axis growth
  the project needs -- a tool no machine can consume cleanly is pure in a way that
  helps no one.
- **Doc-mass exceeding the core.** When the rationale and process documents
  substantially outweigh the verifier they describe, the project has begun
  optimizing for the description over the thing. (This document is itself subject
  to that caution: it earns its place only by making the gates *operable*, and if
  it grows past that it is over-minimalism's other face.)

The point of stating this is the load-bearing one: **the rubric governs the SEAM,
not a freeze.** Its job is to keep growth on the is-axis (depth) and off the
ought-axis (authority, adjudication, inside position, enforcement, held key,
target actuation) -- *not* to stop growth. "Refuse every change" is not the
discipline; it is the over-minimalist failure wearing the discipline's clothes. A
maintainer who blocks a JSON envelope, a coverage expansion, or a second
implementation "to stay minimal" has mistaken the freeze for the seam, and is
disqualifying EMET along the is-axis the way creep disqualifies it along the
ought-axis. Both axes have a wrong direction; the rubric names both.

---

## 6. When the gate is wrong: fix the spec, not the code

Sometimes a change fails a gate not because the change is creep but because the
**spec has a genuine gap** -- a MUST that is too narrow, a verdict the lattice
honestly needs, a boundary phrased in an overstated form (this very document
corrects two such overstatements in G4). When that happens, the discipline is
inherited straight from `CONTRIBUTING.md`: **fix the spec, not the code.**

> "Where your implementation and the spec disagree, **fix the spec**: those
> divergences are the point." -- `CONTRIBUTING.md`

The mechanism:

1. **Do not** route around a gate by quietly adding a token, a write, or a
   dependency that the spec does not sanction. A codepath that emits an
   unenumerated verdict is BROKEN scope discipline even if the verdict seems
   harmless -- because the *next* unenumerated verdict will not be harmless, and
   review cannot tell them apart once the precedent is set.
2. If the gap is real, change `SPEC.md` and `conformance/vectors.json`
   **together** (`CONTRIBUTING.md`) -- the spec is normative, the vectors are how an
   independent implementation reproduces it. The governed verdict set (§3) is
   amended *in the spec first*; this rubric then follows the spec, never the
   reverse.
3. The bar for amending a §6 boundary is highest of all, because a boundary is not
   a dial -- removing or widening one changes *what EMET is*
   ([06-aleph.md](./rationale/06-aleph.md)). Correcting an *overstated* boundary to
   its true scope (as G4 does for "zero actuation") is legitimate spec repair;
   *relaxing a boundary's real content* to admit a convenient feature is the
   creep the whole rubric exists to catch. Tell the two apart by asking whether
   the change makes EMET describe itself *more honestly* or makes it *do more to
   the world of its own accord*. The first is depth. The second is the seam being
   crossed.

A gate that genuinely blocks a needed capability is evidence about the spec, not a
verdict against the capability. Run it back through the spec -- openly, with
vectors -- and let the divergence do its work. That is the same posture the whole
project runs on: the warrant is the argument and the re-derivation, never the
authority of whoever holds the pen.

---

## Refuter

A rubric worth keeping must say how it would fail. This one fails if either of
two things is shown:

> **If a change that passes all six gates nonetheless moves EMET across the
> is/ought seam -- gives it authority, an inside position, enforcement, a held key,
> or actuation on the target -- then the gates are not the perimeter they claim to
> be, and the litmus is incomplete.** Conversely, **if a change that fails a gate
> can be shown to leave EMET categorically unchanged -- same job, same side of the
> seam, crossing nothing it did not already cross -- then that gate is over-tight,
> and it is the over-minimalism §5 warns against, dressed as discipline.**

Either finding is actionable: the first widens the gate set (a perimeter with a
gap), the second loosens an over-tight gate (a freeze mistaken for a seam). The
rubric earns its keep only so long as both refuters stay un-triggered -- checkable,
gate by gate, against SPEC §6 and the governed set, by anyone, with no appeal to
the authority of this document.

---

*Further reading (lineage and grounding, never warrant): [SPEC.md](../SPEC.md)
§§2, 5, 6, 8, 10, 11, 13, 14, 16; [CONTRIBUTING.md](../CONTRIBUTING.md) (the
non-negotiable boundaries; "fix the spec"); [THREAT-MODEL.md](../THREAT-MODEL.md)
(the "performs no action" phrasing corrected in G4). Code cited for the corrected
boundary: `membrane.py` (`anchors.json` via `anchor`, the log via `record`,
`.refused` via `refuse`), `monitor.py` (manifest rewrite via `reanchor`, monitor
tokens via `report`). Rationale
siblings: [01-is-ought-seam.md](./rationale/01-is-ought-seam.md),
[04-spoken-for.md](./rationale/04-spoken-for.md),
[06-aleph.md](./rationale/06-aleph.md),
[00-orientation.md](./rationale/00-orientation.md).*
