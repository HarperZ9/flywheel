# G4 -- Advisory: Zero Actuation ON THE TARGET

> **Status of this document.** This is one essay in the scope-discipline
> curation -- the engineering register of EMET's no-authority shape. It does not
> bind because a maintainer, a corpus, or a thesis asserts it. It binds only so
> far as it is re-derivable from a [SPEC.md](../../SPEC.md) §6 boundary and from
> the code it describes, both of which a reader can open and check. Where it
> points to `research/`, the rationale curation, or any sibling, it points as
> *further reading* -- lineage -- never as the reason to accept the gate. The
> one-page rubric ([../scope-discipline.md](../scope-discipline.md)) states G4 in
> a paragraph; if you only need the litmus, read that. This essay exists to go
> **deeper**: to ground the gate in EMET's actual `gate()` code, in the named
> fixes this project actually made, and in the strongest objection it survives.
> If at any point this essay only restates the one-pager, it has failed its own
> discipline (L14: stop when it returns nothing new) -- and you should stop
> reading, because so did the argument.

---

## 0. Where this gate sits

G4 is the fourth of six gates in the scope-discipline litmus
([../scope-discipline.md](../scope-discipline.md) §2; spine:
[./README.md](./README.md)). It maps to **[SPEC.md](../../SPEC.md) §6 boundaries
4 and 6** -- *advisory by default* and *zero actuation on the audited target* --
and to the disclosed limit in **§11** (the single-actuator assumption). Its
governing claim is one sentence:

> EMET's output is data plus an exit code; EMET does not, of its own accord,
> allow, deny, block, or enforce, and it does not write to, edit, sign, back up,
> or revert **the audited target** -- the artifact under judgement. The single
> actuator over the world is the operator.

The unifying thesis of the whole curation is that **integrity is witnessed, not
self-attested** -- nothing can be its own independent witness. G4 is the place
that thesis touches the *hand* rather than the *eye*. A witness that also acts
on what it witnesses has stopped being a witness: it has become a party to the
event, and a party cannot be the independent corroborator of its own
intervention. G4 keeps EMET's hands off the artifact so that its account of the
artifact stays an outside account. The philosophy of why the witness must stay
outside is a sibling layer ([../rationale/04-spoken-for.md](../rationale/04-spoken-for.md),
[../rationale/06-aleph.md](../rationale/06-aleph.md)); this essay is the
engineering of the wall.

---

## 1. The fact this gate protects: a verdict is not an act

Begin with the asymmetry between what EMET produces and what an enforcer
produces, because the whole gate lives in the gap between them.

`verify` produces the string `DRIFT` and an exit code. That is a **fact**: the
bytes at this path no longer hash to the bytes the operator anchored. The fact
is true or false independent of anyone's response to it; it changes nothing in
the world; it can be re-derived by anyone with the same bytes and the same
anchor. An *enforcer* would take that same fact and do something with it of its
own accord -- revert the file, block the deploy, quarantine the artifact. The
moment that happens, two things change at once:

1. **The verdict acquires a consequence EMET authored.** `DRIFT` no longer
   *describes* a state; it *causes* a state change. The is-fact has become an
   ought-act.
2. **EMET becomes a second author of the artifact's history.** If EMET reverts
   the file, the next observer cannot tell whether the operator chose the
   anchored bytes or EMET imposed them. EMET has written itself into the
   provenance it was supposed to witness from outside.

The second consequence is the deeper one, and it is why G4 is not merely a
safety preference. An auditor who edits the books cannot audit them. A witness
who moves the body cannot testify to where it lay. EMET's entire value is that
its account of the artifact is an **outside** account -- re-derivable by a third
party who trusts neither EMET nor the operator. Let EMET touch the artifact and
that account is contaminated at the source: the artifact's state now includes
EMET's intervention, and EMET can no longer be the independent corroborator of a
history it helped write. This is the same structural fact the unifying thesis
states in general (nothing is its own witness) specialized to actuation: **an
actor on X cannot be an independent witness to X.**

So the load-bearing claim of G4 is not "actuation is dangerous" (it is, but that
is a consequence). The claim is **categorical**: an EMET that actuates the
target is no longer the *kind of thing* EMET is. It has moved across the
is/ought seam ([../rationale/01-is-ought-seam.md](../rationale/01-is-ought-seam.md)),
from a verifier that *locates* the boundary to an enforcer that *crosses* it.
That is why §4's worked-cases list puts "useful but disqualifying" features
under this gate: a `--fix` flag is genuinely useful, and still disqualifying,
because usefulness is measured on the is-axis and the cost is paid on the
ought-axis, and the two do not net (rubric §1).

---

## 2. The worked case: `organs.py gate` performs nothing

The cleanest demonstration that EMET can be *useful at the moment of action* and
*still actuate nothing* is the impedance gate in
[`organs.py`](../../organs.py). It is worth reading the function in full,
because the gate is the strongest possible test of G4 -- it is the one command in
EMET whose entire purpose is to be consulted *immediately before an operator
edits a file*, the exact moment where an enforcer would intervene.

```python
def gate(paths):
    print("PRE-ACTION IMPEDANCE GATE (organs perform nothing; the operator acts)")
    revertible_all = True
    for p in paths:
        p = os.path.normpath(p)
        if os.path.isfile(p):
            pre = sha(raw(p))[:12]; ok, why = revertible(p)
        else:
            pre = "absent"; ok, why = (True, "new file - revert = delete")
        verdict_value = verdict.governed(verdict.REVERT, "REVERTIBLE" if ok else "NOT_REVERTIBLE")
        print(verdict_value + " " + p + " pre=" + pre + " revert=[" + why + "]")
        revertible_all = revertible_all and ok
    gate_token = verdict.governed(verdict.REVERT, "REVERTIBLE" if revertible_all else "NOT_REVERTIBLE")
    print("gate=" + gate_token + "  (advisory fact; the operator decides and acts)")
    sys.exit(0 if revertible_all else 2)
```

Read what `gate` actually does, line by line:

- It hashes the **current** bytes of each path (`pre = sha(raw(p))[:12]`) -- a
  **read**, `open(p, "rb")`, never a write.
- It calls `revertible(p)`, which runs three read-only `git` queries --
  `ls-files --error-unmatch` (is the path tracked?), `status --porcelain` (are
  there uncommitted changes?) -- and on success returns the *recipe a human would
  type*: the literal string `"git checkout -- " + os.path.basename(p)`. It does
  **not run** that recipe. It hands the operator a sentence.
- It emits, per path, `REVERTIBLE` or `NOT_REVERTIBLE` -- the **re-derivable
  fact** that a clean operator revert path already exists (committed VCS state),
  the pre-state hash, and the revert recipe.
- It emits a summary `gate=REVERTIBLE` / `gate=NOT_REVERTIBLE` and exits 0 or 2.

That is the whole function. It **computes whether a clean operator revert path
exists and performs nothing.** The reversibility it reports is not a property
EMET creates -- it is the operator's *already-committed VCS state*. The git
working tree is the safety net; `gate` only reports whether the net is already
strung. The docstring of `organs.py` states the invariant precisely: *"gate
never edits, never backs up, never reverts -- it reports the FACT that the
operator already HAS a clean revert path (committed VCS state) and records the
pre-state hash. The operator VCS is the reversibility; organs only report
whether it exists. Many eyes, one hand, the hand is the operator."*

This is the gate's worked case for G4 because it would be the *easiest* command
to push across the line, and it doesn't. An enforcer's instinct, faced with
"this edit has no clean revert path," is to **refuse the edit** -- to make
`NOT_REVERTIBLE` *deny*. EMET refuses that instinct structurally: the only
consequence of `NOT_REVERTIBLE` is `sys.exit(2)` and a printed sentence. **The
exit code is the integration point** -- a CI step or a pre-commit hook *can*
choose to halt on exit 2, but that halt is the *operator's* policy acting on
EMET's fact, configured on owner-controlled infrastructure, not a wall EMET
builds of its own accord ([SPEC.md](../../SPEC.md) §11, "advisory unless
owner-enforced"; rubric §4, "the exit code is already the integration point").

> **Load-bearing.** The claim that `gate` actuates nothing is load-bearing for
> G4, and it is checkable: read `gate()` and `revertible()` and confirm there is
> no `open(..., "w")`, no `git checkout`, no `os.replace`, no `shutil` call --
> only reads, prints, and an exit code. If you find a write to one of the
> *paths under judgement*, G4 is violated and the essay is wrong.

### 2.1 The token is a fact, not a permission -- and the type enforces it

There is a subtler way `gate` could fail G4 without ever writing a byte: by
emitting a token the downstream reader would treat as a *grant*. `REVERTIBLE`
sits one synonym away from `SAFE-TO-EDIT`, and `SAFE-TO-EDIT` is permission
wearing a fact's clothes. The defense here is the same structural one that
backs G2 ([./G2-closed-lattice.md](./G2-closed-lattice.md)): the token is
emitted through `verdict.governed(verdict.REVERT, ...)`, and `REVERT` is the
frozenset `{"REVERTIBLE", "NOT_REVERTIBLE"}` in
[`verdict.py`](../../verdict.py). That set excludes every authority word
(`TRUSTED`, `APPROVED`, `SAFE`, `ALLOWED`, `PERMITTED`, …) by construction, and
`governed()` raises `VerdictError` at construction time -- inside the TCB, before
a byte reaches stdout -- on any token outside the set. [SPEC.md](../../SPEC.md)
§2 pins the meaning in words: `REVERTIBLE` is *"the re-derivable FACT that a
clean operator revert path exists, explicitly NOT a permission to act … gate
reports a fact, never grants authority."*

> **Illumination (cross-gate).** This paragraph is G2's machinery doing G4's
> work at one remove. It is included because the two gates share a seam at the
> impedance command -- an actuation gate could be smuggled in either as a write
> (G4 proper) or as a permission-token (G2). Marking it *illumination* keeps the
> essay honest: the structural guarantee here is G2's; G4's own guarantee is the
> absence of the write.

---

## 3. The named fix: the zero-actuation claim was overstated, and this session corrected it

The most important thing this essay can do that the one-pager cannot is to show
that **G4's own statement was wrong, was caught, and was repaired** -- because
that is the project's discipline (rubric §6: *fix the spec, not the code*)
applied to G4 itself, and it is the difference between a gate that is asserted
and a gate that is earned.

### 3.1 What the overstatement was

Two shipped documents claimed EMET writes *nothing at all*:

- **[THREAT-MODEL.md](../../THREAT-MODEL.md)** (Elevation of privilege) read
  *"EMET performs no action."*
- The rationale essay
  **[06-aleph.md](../../docs/rationale/06-aleph.md)** said *"Boundary 6 is the
  absence of a write call."*

Both are **false as written**, and the falsity is checkable in thirty seconds by
opening the code. EMET performs writes -- several of them -- to its own stores. A
contributor who took either phrasing literally would either (a) flag the
accountability log as a boundary violation, or, far worse, (b) notice the
phrasing is *obviously* already violated and conclude the boundary is soft --
using the overstatement as license to relax the *real* wall. An overstated
invariant is not a stricter invariant; it is a **weaker** one, because it
invites the reader to discount it.

### 3.2 What EMET actually writes (and why none of it is the target)

EMET writes to exactly four implementation-private stores, and the gate's true
scope is that **none of them is the artifact under judgement**:

| Store | Written by | Where | Is it the target? |
|---|---|---|---|
| Anchor store `anchors.json` | [`membrane.py`](../../membrane.py) | `anchor()` → `json.dump(db, open(ANCHORS, "w", …))` | No -- EMET's own pin of *(path, sha256)* |
| Hash-chained log `membrane_log.jsonl` / `monitor_log.jsonl` | [`membrane.py`](../../membrane.py) `record()`; [`monitor.py`](../../monitor.py) `_record()` | append `open(LOG, "a", …)` | No -- EMET's own tamper-evident account |
| `<file>.refused` clean copy | [`membrane.py`](../../membrane.py) | `refuse()` → `open(path + ".refused", "wb").write(clean)` | No -- a *new sibling* file; the input is untouched (SPEC §4: *"MUST NOT modify the input"*) |
| Baseline manifest | [`monitor.py`](../../monitor.py) | `reanchor()` → `json.dump(new, open(manifest, "w", …))`, **only on operator-authorized `reanchor`** | No -- EMET's own baseline, and rewritten only when the operator commands it |

Look closely at the two that are easiest to misread:

- **`refuse` writes `<file>.refused`, not `<file>`.** The line
  `open(path + ".refused", "wb").write(clean)` creates a *new* path; the audited
  input is never opened for writing. This is exactly the `--fix`-without-actuation
  pattern: EMET hands the operator a *clean copy to inspect and choose*, and
  declines to overwrite the original. The artifact under judgement keeps its
  bytes; the operator decides whether to adopt the clean copy. SPEC §4 makes
  "MUST NOT modify the input" normative for `refuse` specifically.
- **`reanchor` rewrites the manifest, and the manifest is EMET's baseline, not
  the target.** Worse, it only runs *when the operator types `reanchor`* -- it is
  the operator authoring a new authorized state, with EMET doing the bookkeeping
  the operator asked for. `report`, the command that actually *judges*, never
  writes the manifest; it only reads it (`json.load`) and appends to the log.
  The write and the judgement are in different commands, and only the operator
  invokes the writing one.

### 3.3 The corrected statement

The repair was to scope the boundary to the **target**, in three places at once
(spec and its satellites moving together, the disciplined way):

- **[SPEC.md](../../SPEC.md) §6 boundary 6** now reads: *"Zero actuation on the
  audited target -- EMET MUST NOT write to, edit, sign, back up, or revert the
  AUDITED TARGET (the artifact under judgement). EMET DOES write to its own
  implementation-private stores … none of which is the target."*
- **[SPEC.md](../../SPEC.md) §11** carries the same scoped form as a disclosed
  limit (the single-actuator assumption), and explicitly labels the earlier
  blanket phrasings *"overstated and … corrected to this scoped form."*
- **[THREAT-MODEL.md](../../THREAT-MODEL.md)** now carries a `CORRECTION` block
  in the Elevation-of-privilege section: *"an earlier phrasing here read 'EMET
  performs no action,' which was overstated."*

The corrected gate is therefore **target-scoped actuation**, and its precise
fail/pass shape is:

> **Fails** when a change writes to, edits, signs, backs up, or reverts the
> *artifact under judgement* of EMET's own accord; or adds a built-in
> allow/deny/block/enforce. **Does not fail** merely because a change writes to
> `anchors.json`, a log, a `.refused` sibling, or (on explicit operator
> `reanchor`) the manifest -- those are private stores, not the target.

> **Load-bearing.** This correction is the spine of G4 and is itself the
> project's discipline in action. Note *which kind* of spec change it was: rubric
> §6 distinguishes *correcting an overstated boundary to its true scope*
> (legitimate spec repair -- the change makes EMET describe itself **more
> honestly**) from *relaxing a boundary's real content* to admit a convenient
> feature (the creep the rubric exists to catch -- the change makes EMET **do
> more to the world**). The §6/§11 correction is unambiguously the first:
> EMET's actual behavior did not change by one byte; only the *description* of
> it became accurate. A reader can verify this by checking that the corrected
> spec licenses no new write to any *target* -- only an honest account of writes
> that were always happening to *stores*.

---

## 4. The strongest objection, and the answer

A gate is only as good as the best argument against it. Here is the strongest
one I can construct, stated at full strength before it is answered.

> **The objection (the "private store is a distinction without a difference"
> argument).** You concede EMET performs writes. You concede `reanchor` can
> *overwrite an operator's baseline manifest* and `refuse` can *create a file on
> the operator's disk*. The line you draw -- "but none of them is the *target*"
> -- is a definitional dodge. From the operator's filesystem's point of view,
> EMET *is* an actuator: it mutates disk state of its own accord (every `verify`
> appends a log line without being asked to). "Zero actuation on the target" is
> just "zero actuation, except the actuation we've decided to rename as
> bookkeeping." If the boundary can be preserved by relabeling which writes
> count, it constrains nothing -- you could license a `--fix` tomorrow by
> declaring the fixed file a "private remediation store."

This is the objection that, if it landed, would trigger the rubric's own
refuter (one-pager §Refuter: *if a change that passes a gate leaves EMET
categorically unchanged, the gate is over-tight; if a change that fails it
crosses the seam anyway, the gate is incomplete*). So it must be answered on the
merits, not waved off.

**The answer has three parts, and each is checkable.**

1. **The target/store line is not a relabeling; it is the witness/event
   distinction, and it has an operational test.** Ask: *after EMET runs, can a
   third party who trusts neither EMET nor the operator still re-derive the
   facts EMET reported about the artifact?* For the four private stores, the
   answer is **yes** -- the artifact's bytes are exactly what they were, so any
   verifier can recompute the same hash and reach the same verdict. EMET's
   writes left the *evidence* untouched. For a `--fix` that rewrites the target,
   the answer is **no** -- the artifact now holds EMET's bytes, and the original
   evidence is gone; no third party can re-derive what EMET claimed about the
   *pre-fix* artifact, because EMET destroyed it. **That is the difference the
   line tracks: writes that preserve the re-derivability of the verdict versus
   writes that destroy it.** It is not "which writes we renamed"; it is "which
   writes a downstream witness can still see past."

2. **The stores are EMET's own account, and an account *of* events is not an
   intervention *in* events.** A camera that records a crime and writes a video
   file to its own SD card has not acted on the crime scene; a camera with a
   robot arm that tidies the scene has. The log, the anchor store, and the
   `.refused` sibling are EMET's SD card. They are append-mostly, they are
   EMET-private (SPEC §15: the anchor store's on-disk format is not even
   standardized across implementations), and crucially **they sit beside the
   artifact, never over it.** `refuse` is the sharpest proof: it had every
   opportunity to overwrite `<file>` and instead writes `<file>.refused`,
   leaving the operator to choose. That is a deliberate *refusal* to actuate the
   target at the one command where actuation would be most tempting.

3. **The `reanchor` case is the operator actuating, with EMET as scribe -- which
   is the gate working, not failing.** `reanchor` rewrites the manifest *only
   when the operator runs the `reanchor` command* (`monitor.py main()`: the
   manifest write lives behind `a[1] == "reanchor"`, never behind `report`). The
   write is the operator authoring a new authorized baseline; EMET performs the
   keystrokes the operator commanded. "Of its own accord" is the operative
   phrase in the boundary, and `reanchor` is *not* of EMET's own accord -- it is
   the operator's accord, logged so the baseline change is itself accountable.
   The gate's wording was chosen precisely to admit this: it forbids actuation
   *of EMET's own accord*, not all writes that ever touch operator files.

So the line holds: it is the re-derivability-preservation test (part 1), it
tracks witness-vs-event (part 2), and "own accord" excludes operator-commanded
writes (part 3). None of the three could be used to launder a `--fix` in,
because a target rewrite fails test 1 (it destroys the evidence), fails test 2
(it writes over the artifact, not beside it), and `--fix`-on-DRIFT would fire
*of EMET's own accord*, failing test 3. The objection's "you could rename
anything" rests on there being no test; there is a test, and `--fix` fails it.

---

## 5. The refuter (how G4 itself would fail)

Honesty requires stating the conditions under which this gate is wrong, in a
form anyone can check.

> **G4 is over-tight if** a change it forbids can be shown to leave EMET
> categorically unchanged -- same job, same side of the is/ought seam, destroying
> no re-derivability, acting of no one's accord but the operator's. *Candidate:*
> someone might argue the append to `membrane_log.jsonl` on every `verify`
> already "actuates" and so the gate should forbid *that* too. It should not:
> the log write passes all three tests in §4, so a gate that forbade it would be
> the over-minimalism the rubric's §5 warns against -- purity bought by making
> EMET unable to keep the accountable history that is half its purpose. If the
> gate is ever read to forbid the log, it is being mis-applied.

> **G4 is incomplete if** a change that *passes* it -- touches no target byte,
> emits only governed tokens, exits with a code -- can still be shown to make
> EMET a second author of the *for*. *Candidate:* a "recommended action" string
> in `gate`'s output (e.g. printing `ACTION: revert now`) writes no byte and
> exits cleanly, yet nudges the operator toward a decision EMET has no standing
> to author. If such a string is ever added, G4 as the *write*-gate would pass
> it while the *advisory* half of boundary 4 is breached -- which means the gate
> must be read as **boundary 4 AND boundary 6 together** (data-plus-exit-code
> *and* no target write), not boundary 6 alone. The present output is clean:
> `gate` prints facts and recipes (`revert=[git checkout -- file]`), never an
> imperative *do this*. The first imperative is the refuter firing.

Both refuters stay un-triggered against the code as it stands today. The gate
earns its keep only so long as that remains checkable, command by command,
against [SPEC.md](../../SPEC.md) §6 and the `organs.py`/`membrane.py`/`monitor.py`
write sites -- by anyone, with no appeal to the authority of this document.

---

## 6. What this gate does *not* say (the over-minimalist trap)

A maintainer who reads G4 as "EMET must never write anything" has made the exact
mistake the overstated phrasings invited, and would block the project's own
core. The cure is to hold the *scope* of the gate precisely:

- The **accountability log is required growth**, not a tolerated exception. A
  verifier that kept no tamper-evident history of what it witnessed would be
  *less* of an EMET, not a purer one. The log write is depth on the is-axis
  (more provenance brought under judgement), and G4 must not be wielded to
  forbid it.
- The **`.refused` clean copy is a feature, not a violation.** It is the
  is-axis answer to "what do I do about an injected marker" -- produce a
  neutralized copy *to inspect*, while refusing to overwrite the evidence. A
  maintainer who flagged it under G4 would have mistaken the gate's scope.
- **Adding an exit-code resolution** (the v1.1 split of exit-2 into DRIFT=1 /
  UNVERIFIABLE=2, [SPEC.md](../../SPEC.md) §5) is *more* advisory signal for the
  operator to act on, not more actuation by EMET. It passes G4 cleanly: it adds
  resolution to the fact EMET hands over, and changes nothing about who acts on
  it.

G4 governs the **seam**, not a freeze (rubric §5). Its job is to keep EMET's
growth on the is-axis (more facts, better-recorded, more consumable) and off the
ought-axis (acting on the target of its own accord) -- *not* to stop EMET from
writing the stores that make it an accountable witness.

---

## 7. Summary: the hand is the operator's

G4 reduces to one sentence the curation's thesis makes inevitable: **a witness
cannot be a party to the event it witnesses.** EMET keeps its hands off the
audited target so its account of that target stays an outside account,
re-derivable by a third party who trusts no one in the room. The `organs.py`
gate is the worked proof -- the one command built to be consulted at the instant
of action, which computes whether a clean operator revert path exists and
*performs nothing*, leaving the exit code as the operator's integration point
and the git working tree as the operator's safety net. The "zero actuation"
claim was once overstated to "no action at all," was caught, and was corrected
to its true scope -- EMET writes its own anchor store, its hash-chained log, its
`.refused` sibling, and (only on operator command) its baseline manifest, and
**never the artifact under judgement**. That correction is the gate's own
discipline turned on itself: describe more honestly, never do more to the world.

A block-on-DRIFT mode, a `--fix` that rewrites the target, an auto-revert, a
quarantine that moves the artifact -- each is useful, and each is disqualifying,
because each makes EMET a second author of the *for* the operator alone should
write. Many eyes, one hand; the hand is the operator's.

---

*Further reading (lineage and grounding, never warrant):
[SPEC.md](../../SPEC.md) §§2, 4, 5, 6 (boundaries 4 and 6), 11, 13, 15;
[CONTRIBUTING.md](../../CONTRIBUTING.md) (the non-negotiable boundaries; "fix the
spec"); [THREAT-MODEL.md](../../THREAT-MODEL.md) (the "performs no action"
phrasing corrected here). Code: [`organs.py`](../../organs.py) (`gate`,
`revertible` -- the advisory worked case), [`membrane.py`](../../membrane.py)
(`anchor`/`anchors.json`, `record`/the log, `refuse`/`.refused`),
[`monitor.py`](../../monitor.py) (`report`/read-only judge, `reanchor`/manifest
on operator command), [`verdict.py`](../../verdict.py) (`governed(REVERT, …)` --
the token-as-fact guard). Sibling gates:
[./G2-closed-lattice.md](./G2-closed-lattice.md) (the token machinery G4 borrows
in §2.1); the one-page rubric [../scope-discipline.md](../scope-discipline.md);
the spine [./README.md](./README.md). Rationale siblings (the philosophy of why
the witness stays outside): [../rationale/04-spoken-for.md](../rationale/04-spoken-for.md),
[../rationale/06-aleph.md](../rationale/06-aleph.md),
[../rationale/01-is-ought-seam.md](../rationale/01-is-ought-seam.md).*
