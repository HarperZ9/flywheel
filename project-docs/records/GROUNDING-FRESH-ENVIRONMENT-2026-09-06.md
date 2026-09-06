# Rebuilding an ancestor's oracle environment from its own receipt

2026-09-06. Branch `feat/grounding-fresh-env-20260906`, off `main` at `652483a`.

## The problem

`recheck_grounding` re-witnesses every cited ancestor before it lets a task be
accepted. To re-run an ancestor's oracle it needs somewhere to run it, and it
took that from the caller: a `workdirs` entry per ancestor, mapping task id to
a workdir and a candidate path. Missing entry, fail closed, UNVERIFIABLE.

That is the right failure, and it is why `grounding_recheck` could not be
turned on by default. A default-on flag with a caller-supplied precondition
marks every grounded task unverifiable the moment the caller does not know to
supply it.

## What was built

`harness/oracle_inputs.py` captures the fixture set the oracle reads, before
the oracle runs, and restores it into a fresh temp directory at re-check time.

Capture is bounded because a receipt may be published: 64 files, 32 KB per
file, 128 KB total, text only, with build directories skipped. Entries that
break a bound are dropped whole rather than truncated, since half a fixture is
not a smaller fixture, it is a different one. Binary files are dropped on
`UnicodeDecodeError` rather than encoded, which keeps the receipt readable and
keeps a large opaque blob out of it.

Timing is the substance of the change, not an implementation detail. Capture
runs before the oracle. After the run the workdir also holds the candidate and
`_oracle_junit.xml`, and `canonical_hash` reads outcomes back out of that junit
file. A receipt permitted to carry one would arrive in the fresh directory
already graded.

Restore re-applies every bound capture applied. Capture runs on our side of the
trust boundary; restore reads a file someone else wrote, so it inherits none of
capture's guarantees. It re-checks the path, the exclusions, the type, and both
caps. Traversal is refused rather than sanitised: a rewritten path that still
writes somewhere invents an environment nobody sealed, while refusing costs a
confirmation and can never grant one.

## The asymmetry

Reproducing the stored canonical hash in a directory built from the receipt
alone proves the environment was sufficient, so it earns MATCH. Failing to
reproduce it proves nothing, because a missing fixture and a real tamper are
the same observation from there. That outcome degrades to UNVERIFIABLE with its
reason recorded, and is never reported as DRIFT.

Strength depends on the oracle. For `pytest` the canonical hash folds every
test id and outcome, so reproducing it in a bare directory says a lot. For an
oracle whose canonical form is empty the hash covers the return code only, and
a fresh-environment MATCH there is worth "it exited the same way".

## The false accept this opened, and what closed it

Rebuilding an environment out of a receipt makes the fixture set an input to
the verdict. Left unsigned, a republisher could ship a test file with the same
test ids and gutted assertions. `_pytest_canonical` folds ids and outcomes, so
that reproduces the stored canonical hash against a tampered candidate.

Measured on `tasks/example_pass` rather than argued from the code: seal an
ancestor, rewrite `candidate` to a version that multiplies instead of adding,
rewrite the carried `tests/test_solution.py` so every assertion reads
`assert True` with the ids untouched, and the re-check returns **MATCH**. The
first attempt at this probe was malformed, using invented test ids, and
returned UNVERIFIABLE; the ids have to match for the attack to work, which is
the whole shape of it.

Two changes close the in-place version.

**The fields are inside both digests.** `candidate_path` and `oracle_inputs`
are folded into the claim and content preimages, under a drop-when-default
rule: a post-hoc field is dropped from both preimages *while it holds its
default*. A receipt written before the field existed hashes exactly as it did
then, so every signature over it still verifies, and a receipt that carries the
field signs it like any other claim. Unconditional exclusion would have been
simpler and would have left the fixture set rewritable.

**A receipt has to hash to its own name.** Envelopes are filed as
`{task_id}-{content_hash}.json`, so an in-place edit to any digest-covered
field moves the hash off the filename. `grounding._load_intact` drops such a
receipt before any oracle runs, and drops it whole, so its own `retrieved[]`
never steers the citation walk.

`resolve_ancestors` now reports an absent receipt and an edited one apart. Both
fail closed; they call for different responses from whoever reads the run.

## The refiling gap, and the pin that closes it

The name check does not stop an editor who refiles the receipt under its new
hash. The receipt is then self-consistent and the swap lands.
`tests/test_grounding_receipt_integrity.py::test_a_refiled_receipt_is_not_stopped_by_this_check`
asserts that outcome rather than leaving it implied.

The cause is that a citation named a task id and nothing else, so the store
answered with whichever sealing of that id was newest. `Retrieved` now carries
`digest`, the content hash of the receipt the citer actually read, and a pinned
source resolves to that one filename or to nothing. A rewrite filed under its
own new hash is nothing.

The pin lives inside `retrieved[]`, which was already folded into both digests,
so stripping a pin to make a citation swappable again moves the citing
receipt's hash and runs into the same check one level up. An editor who wants
the swap has to rewrite every descendant that pins it, and each of those moves
its own filename in turn. That is the actual value: the edit stops being local.
It does not stop an editor who rewrites the whole cone, and one externally held
copy of any node in it is what catches that.

Cost, asserted rather than implied. An unpinned citation still resolves by
newest sealing and is still swappable, which is the state every receipt sealed
before today is in. `digest` is dropped from the serialised citation while it
holds its default, so those receipts hash exactly as they did.
`tests/test_citation_pin.py` carries the closed case, the unpinned cost, and a
positive control that an untouched pinned cone still reaches MATCH.

Where pins come from without a caller asking: `run_loop` already recorded
`envelope:{content_hash}` into the `VerifiedPool` on acceptance, and the pool
now keeps the digest as a digest rather than inside a display string, so the
memory-to-context edge hands the next run a pinned citation.

Two orderings are conservative on purpose. A cone that names two digests for
one source resolves that source to nothing, and so does one that mixes a pinned
citation with an unpinned citation resolved to a different sealing. Both are
ambiguous, and re-resolving on the second reading would be a guess. Refusing
costs a confirmation; the other direction could grant one.

The mechanism is not new and this record does not claim it is. An in-toto
Statement binds to its artifacts through `subject[].digest`, and the spec says
subjects are matched purely by digest regardless of content type. Layout MATCH
rules go further and bind one step's materials to a previous step's products by
hash equality, which is the same edge this pin covers, published years earlier.
Both were read live on 2026-09-06, at the two URLs below. What was missing here
was the application, not the idea: the citation edge carried a task id while
the environment it rebuilds was already hash-covered, and the mismatch is what
the refiling attack lived in.

- https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md
- https://github.com/in-toto/docs/blob/master/in-toto-spec.md

Signature verification is what closes the whole-cone case, and it is now wired
into the re-check path behind a `trusted_keys` mapping the caller supplies. See
`GROUNDING-SIGNATURES-2026-09-06.md` for what it establishes and what it leaves
to key distribution.

## Two consequences worth stating

Receipts now carry workdir text. That is a disclosure surface on anything
published, bounded by the caps above and switchable with
`capture_oracle_inputs=False`. The section below narrows it further.

A re-check now executes more third-party content than before, because a
restored `conftest.py` runs at pytest collection. The boundary was already
crossed: re-witnessing writes `envelope.candidate` and runs
`envelope.oracle_cmd` under a shell, from the same untrusted receipt. This
widens it rather than opening it.

## Credentials are withheld from the capture

The caps keep a snapshot small. Nothing about them keeps it safe, and a `.env`
in a working directory is a few hundred bytes, so it would have gone into a
receipt and been signed with the rest of it.

`harness/receipt_secrets.py` answers one question: may this file travel in a
receipt. Two rules, because they miss different things. A name rule covers
`.env`, `id_rsa`, `.npmrc`, `wrangler.toml` and key material by extension,
whatever those files hold, which is the half that still works when a password
is too short for any pattern to match. A content rule runs
`credential_scanner.scan_text` and covers a key pasted into a file named
nothing in particular. `.env.example` is exempt, since the engineering standard
requires a repo to commit it and its whole purpose is to be readable.

Withheld whole, never masked. A masked fixture looks complete and runs
differently, and under the asymmetry above a fixture that is present but
altered is worth less than one that is absent. Restore applies the same rule,
so a receipt someone else wrote cannot get a credential written onto our disk
in exchange for a fixture the sealer was never supposed to carry.

What got withheld is recorded on the envelope as `withheld_inputs`, a path and
a reason per entry and never the matched text, folded into both digests under
the same drop-when-default rule. Stripping the marker to make a partial capture
read as a complete one moves the hash. The path of a withheld file is itself
disclosed, which is the same disclosure every carried file already makes;
a caller who cannot accept that turns capture off.

The cost is a false withhold, asserted in the tests rather than left to be
found. A fixture that legitimately assigns a password of eight characters or
more reads as a leak, gets dropped, and costs its task fresh-environment reach.
Fail closed is the right direction, and it is not free.

That cost surfaces as an UNVERIFIABLE, which is the verdict a tamper produces
too, and the hash cannot tell those apart. So the reason string carries the
fact: `_rewitness_in_fresh_env` counts what the seal withheld and what this end
refused on the way back in, and names both beside the verdict. Without it a
reader spends their time looking for an attacker who was never there.

The headline test does not check the rule. It seals a task whose workdir holds
an AWS key and asserts that the key's text appears nowhere in the serialised
receipt, because a rule test only proves the rule does what I meant.

## Reach

Authored tasks under `tasks/`, meaning tasks with both an `oracle_cmd` and a
`candidate_path`, excluding run outputs under `.flywheel-run/` and
`artifacts/`:

```
tasks with oracle_cmd + candidate_path:  7
whose fixture set is now carried:        7   (0 before this change)

  tasks/example_pass              1 file   185 bytes
  tasks/grpo-proof/add            1 file   121 bytes
  tasks/grpo-proof/count_vowels   1 file   128 bytes
  tasks/grpo-proof/factorial      1 file   138 bytes
  tasks/grpo-proof/is_even        1 file   141 bytes
  tasks/grpo-proof/max_of_list    1 file   132 bytes
  tasks/grpo-proof/reverse_string 1 file   131 bytes
```

Every one of them runs `pytest tests/`, so before this change the candidate
alone rebuilt nothing and the fallback confirmed none of them. A historical
flat-layout run directory under `artifacts/` captures the same way: two files,
511 bytes, junit excluded.

## Cost

Linear chains of `tasks/example_pass`, each link citing the one below it, sealed
and then re-checked with `workdirs={}` so every ancestor takes the fresh
environment path. Three timed repeats per depth, median reported, one Windows
machine:

```
depth  ancestors  median_s  per_ancestor_s  verdict
    1          0     0.000             n/a  MATCH
    2          1     0.790           0.790  MATCH
    4          3     2.322           0.774  MATCH
    8          7     5.581           0.797  MATCH
```

About 0.79 s per cited ancestor, flat from one to seven. An ungrounded task
costs nothing, since there is no cone to walk.

That figure is a pytest subprocess and almost nothing else. An earlier
measurement on self-contained ancestors, whose candidate carried its own test
and needed no restore, came to 0.82 s per ancestor. Writing the fixture set to
a temp directory is below the noise in a per-ancestor number dominated by
interpreter startup and collection.

The shape is what matters for the default. Cost grows with the size of the
cone, so a deep chain pays in proportion, and each link pays the oracle's own
runtime rather than a fixed overhead. A cone of slow oracles costs what those
oracles cost.
