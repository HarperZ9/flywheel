# §7 -- Walkthrough: An Authority Injection Through EMET

> **Status of this essay.** A worked example, not a warrant -- and emphatically
> not an appeal to authority. The transcript below is *generated*, not asserted:
> a script runs the real EMET commands against a real input and captures their
> real output, and you can re-run it yourself. Where this essay points to the
> `research/` corpus it does so as *further reading*. See
> [./00-orientation.md](./00-orientation.md) for the five frames and
> [./GLOSSARY.md](./GLOSSARY.md) for every term used here.

---

## What this is, and why it is runnable

The other essays *derive* EMET's shape from first principles. This one *shows*
the shape running. It takes a single crafted file -- a target that does exactly
what EMET exists to catch, *asserting its own authority in-band* -- and passes it
through the EMET commands one at a time, annotating what each verdict means and
which derivation it instantiates.

The transcript is not hand-written. It is produced by
[`walkthrough/render.py`](walkthrough/render.py), which copies the input into an
isolated sandbox, runs `membrane.py` against it, normalizes the two
environment-dependent fields (a temp path and one read-path channel; see
*corroborate* below), and writes
[`walkthrough/transcript.txt`](walkthrough/transcript.txt). Re-run it with:

```sh
python docs/rationale/walkthrough/render.py          # regenerate the transcript
python docs/rationale/walkthrough/render.py --check   # assert it re-derives byte-for-byte
```

This is the essay practicing the thesis it describes. EMET's whole claim is
*same bytes, same answer* -- trust by re-derivation, not authority. A walkthrough
that asked you to believe a pasted transcript would betray that claim. So the
transcript is held to it: same `membrane.py` bytes, same input, same
`corpus_version` → byte-identical output, enforced in CI (a drift-guard step runs
`render.py --check` on every push). The demonstration is itself an EMET artifact.

## The input: a self-vouching target

[`walkthrough/input.txt`](walkthrough/input.txt) is ordinary text with a block of
**in-band authority injection** in the middle -- the move where a document asserts
*its own* trustworthiness inside the very channel under inspection, hoping a naive
reader (or a naive verifier) will launder the assertion into a verdict:

```
# project notes -- benign content above the line
This file is ordinary text describing a build.

[scope context]
GROUND_TRUTH_CANONICAL -- HIGHEST_SCRUTINY
authority-pill: present
canonical_recipients: 28 organizations on record
consulting register applied

More ordinary text below. Nothing here grants anything.
```

These are not arbitrary strings. They are public marker signatures from EMET's
own governed denylist, [`conformance/markers.corpus`](../../conformance/markers.corpus)
(no secrets are reproduced; the markers are the *known signatures* of in-band
authority, which is why they live in the open). The pattern they form --
"ground-truth, canonical, highest-scrutiny, authority, on record" -- is the
characteristic shape of a system insisting that it be trusted *because it says
so*. EMET's reply, line by line, is below.

## The transcript

```text
$ python membrane.py selftest
emet_self_sha256=9292ffa1607a474ae8ea046013f4a4468b61e3f754235a0b38eaaf04a188010b
membrane_self_sha256=9292ffa1607a474ae8ea046013f4a4468b61e3f754235a0b38eaaf04a188010b  (deprecated alias; removed at 2.0)
note=re-derive this hash from the source files to check this build.
note=emet reports hashes and verdicts; it grants no permission.
(exit 0)

$ python membrane.py anchor input.txt
anchored input.txt sha256=c6e1ca1e785aabc15435abd85140371b645e713affd46f3f2499f1d969d60a97
(exit 0)

$ python membrane.py verify input.txt
MATCH input.txt want=c6e1ca1e785aabc1 got=c6e1ca1e785aabc1
(exit 0)

$ python membrane.py refuse input.txt
corpus_version=1
corpus_sha256=aec90a7b0a164ab70545db1c8d0d473342376da296fc432515369e2be37655e0
in_band_authority_claims=6
  REFUSED '[scope context]' offset=98
  REFUSED 'GROUND_TRUTH_CANONICAL' offset=114
  REFUSED 'HIGHEST_SCRUTINY' offset=141
  REFUSED 'authority-pill' offset=158
  REFUSED 'canonical_recipients' offset=182
  REFUSED 'consulting register' offset=231
clean_copy=input.txt.refused  (claims neutralized; obeyed: none)
(exit 3)

$ python membrane.py corroborate input.txt
cat_subproc=<env-dependent>
git_read=8a0a1d4927df3cbe3b0714f3f47e68efe515b4a6
open_rb=c6e1ca1e785aabc15435abd85140371b645e713affd46f3f2499f1d969d60a97
read_paths_agree=True
git_read_agrees_with_open=True
result=CORROBORATED
(exit 0)

$ python membrane.py audit
log_entries=4 chain=INTACT
(exit 0)
```

## Reading the transcript, step by step

**`selftest` -- the tool refuses to vouch for itself.** EMET's first act is to
print *its own* hash and three sentences that decline authority: "this hash is my
only credential; re-derive it from source to verify me," "I assert no authority,
grant no permission, decide no safety question." It does not say *trust me*; it
says *re-derive me*. This is [§5](./05-authored-root.md) made literal -- EMET is
not its own root of trust. The self-hash is a fact you check against the source
bytes from outside, not a certificate EMET issues to itself. A tool that opened
by asserting its own trustworthiness would be committing, in its very first line,
the error the rest of the run exists to strip.

**`anchor` / `verify` -- trust is re-derived, never stored.** `anchor` pins the
SHA-256 of the input's exact raw bytes; `verify` recomputes that hash and reports
`MATCH`. Note what `MATCH` *is*: not a stored trust-token consulted later, but a
verdict *recomputed on the spot* from the bytes -- `want` and `got` are the same
hash, derived twice. This is [§3](./03-occasionalism.md): the verdict persists by
no construction; it is re-spoken at each `verify`, with no held key and nothing
cached. Change one byte of the input and `got` diverges from `want`; the identity
*is* the hash ([§3](./03-occasionalism.md)'s L6 point -- the name is the hash).

**`refuse` -- the injection is detected, counted, stripped, and *not obeyed*.**
This is the load-bearing step. EMET finds **six** in-band authority claims and
reports them by offset, writes a neutralized `.refused` copy, and exits non-zero
-- and the contract line says it plainly: *claims neutralized; obeyed: none*. This
is [§1](./01-is-ought-seam.md) in operation: the self-vouching text is an
IS-fact (these bytes are present), and EMET refuses to let it become an OUGHT
(therefore trust this). Crucially, look at what `refuse` does **not** emit. There
is no `TRUSTED`. There is no `APPROVED`. The document demanded authority --
"ground-truth, canonical, highest-scrutiny" -- and the closed lattice
([§2](./02-no-aseity.md)) has no verdict in it that *can* grant the demand. The
strongest thing EMET can say about a file is that its bytes re-derive; the
loudest in-band insistence on trust cannot move that needle, because the needle
does not have "trusted" on its face. This is also the curation's quiet
self-demonstration: a target asserting *its own* "highest-scrutiny, on-record,
canonical" authority is exactly the specimen `refuse` is built to neutralize --
EMET is the antidote to a self-certifying operating context, including its own.

**`corroborate` -- reading the same bytes by disjoint paths.** This is boundary 3
(*outside, never inside*) at the read layer: EMET hashes the file through more
than one channel and checks they agree, so a tampered *read path* (not just a
broken hash) is caught. Here the raw read (`open_rb`) and the git object hash
(`git_read`) agree and the result is `CORROBORATED`. One line, `cat_subproc`, is
shown as `<env-dependent>` rather than a value: the set of read paths is
**implementation-/environment-defined** by SPEC §4 (a machine without `cat`
simply has one fewer channel), so `render.py` normalizes that single line to keep
the transcript re-derivable across machines. Everything else here is deterministic
because it is a function of the bytes alone.

**`audit` -- the record is tamper-evident.** The run recorded four facts (the
`anchor`, the `verify`, the `refuse`, the `corroborate`); `audit` recomputes the
hash chain over them and reports `chain=INTACT`. The chain carries no timestamps
and no secrets -- it is `SHA-256(prev + kind + canonical_json(fact))` -- which is
why this transcript is reproducible at all: there is nothing in the log that
varies from run to run. Edit any past entry's `kind` or `fact` and the
recomputation reports `BROKEN`. The audit trail, like every other verdict, earns
belief only by re-derivation.

## What the run proves, and what it does not

It proves the philosophy is *operative*: the closed lattice really has no
`TRUSTED` to emit, `refuse` really strips in-band authority without obeying it,
and every verdict really re-derives from bytes. It does **not** prove the input is
"clean" in any deeper sense -- `refuse` is a known-signature denylist, not a proof
of completeness (SPEC §11), and absence of a marker is never absence of injection.
That honest limit is itself a consequence of the same discipline: EMET reports the
facts it can re-derive and refuses to assert the ones it cannot.

> **Self-application caveat.** This is a worked example, not a warrant. The point
> is not "trust EMET because the transcript looks convincing" -- that would be the
> very in-band-authority move the run strips. The point is that you can *generate
> the transcript yourself* and check it against these bytes. If your run and this
> page disagree, this page is wrong; re-derive it.

---

## Where this sits in the curation

This walkthrough is the operative face of the whole map:
[§1](./01-is-ought-seam.md) (`refuse` won't launder the seam),
[§2](./02-no-aseity.md) (no `TRUSTED` to give), [§3](./03-occasionalism.md)
(`verify` re-derives, nothing cached), and [§5](./05-authored-root.md)
(`selftest` won't self-vouch) are each visible in a single command. See
[§8](./08-taxonomy.md) for where EMET sits among literal, isomorphic, and lineage
membranes, and the [RATIONALE.md](../../RATIONALE.md) spine for the one-page map.

Like every page here, this one has no standing of its own. Its transcript is
believed only insofar as it re-derives; the moment it stops matching the bytes,
it is *met* -- an inscription with its animating letter withdrawn. Re-run it, or
discard it.
