# Evaluation Engineering

An eval is a criterion made executable. Evaluation engineering is the
discipline of building evals as calibrated instruments: designed to be
able to refuse, audited for their blind spots, sealed before their
results exist, version-pinned so old results stay comparable, and
honest about what they cannot decide. The register of instruments in
this repository is live at `GET /api/instruments`, and every entry
reads from a receipt you can open.

## Why the discipline needs a name

The field's own numbers, gathered and adversarially verified in the
2026-07-14 domain dossiers (docs/research/):

- A flagship software benchmark required 38.3% and 61.1% of raw tasks
  to be flagged before a usable subset existed.
- False-pass patches were found behind 24.4% of one leaderboard's
  entries when the tests were strengthened after the fact.
- 398 certified-defective statements were found across five published
  Lean benchmarks.
- Choice of judge model moves published faithfulness scores by 25 or
  more points, and the disagreement is routinely averaged away instead
  of reported.

None of these are statistics subtleties. They are engineering defects:
uncalibrated instruments, unaudited judges, unpinned versions. The
remedy is the same one every measuring discipline adopted: treat the
eval as an instrument that can itself be wrong, and ship it with the
receipts that would prove it so.

## The instruments

Each instrument below exists in this repository, is exercised in
anger, and reports itself in the live register. Absence is reported
honestly: a rotted instrument reads absent, never fabricated.

1. **Admission gates** (`harness/task_curator.py`). A task enters a
   lane only through six gates: the reference passes its own hidden
   tests, a derived stub FAILS them (a verifier that cannot fail
   verifies nothing), determinism across fresh workdirs, no solution
   leak into the prompt, minimum edge coverage, and behavioral
   deduplication. Falsifiability as code.
2. **Oracle strength audits** (`scripts/oracle_strength_audit.py`).
   A non-solution battery (empty module, stub, constant returns,
   one-operator mutants) runs against every oracle in a lane. Hard
   flags mean the oracle accepted nothing-code; mutant passes are
   classified line by line into neutral mutations and coverage gaps.
   The first audit of the 110-task hard lane: zero hard flags, 96/110
   fully clean, five gap candidates named for the next lane version.
3. **Sealed claims, adjudicated without rescue** (`docs/claims/`).
   Predictions are content-hashed before the result exists;
   interpretations are frozen in an addendum before the judge speaks;
   the verdict rule admits no narrative rescue. The discipline's proof
   this is real: a sealed prediction missed its band by 0.0009 and
   shipped as DRIFT.
4. **Version-pinned lanes** (`tasks/curated/`, artifact
   `comparison_key`). Every bench artifact pins its oracle source
   hash. Strengthening a lane's tests happens in an explicit version
   bump, never in place, so every published number stays re-checkable
   against the exact oracle that produced it.
5. **The measurement-tension ledger** (`GET /api/tension`). Two
   measurements of one quantity, each carrying a frozen source hash,
   earn one verdict: tension, consistent, or unverifiable. An
   unverifiable pair is never banked. Disagreement is kept
   re-checkable instead of argued away, and a resolved tension stays
   in the ledger as a consistent entry rather than vanishing.
6. **Generation under witness** (`POST /api/invent`,
   `harness/conjecture_forge.py`). Where the eval's subject is
   generative, novelty itself is graded on an earned ladder (proved;
   proved and corpus-absent; corpus-absent and beyond the cheap
   decision procedure), with the kernel as sole judge.

## Practice rules

- A verifier that cannot fail verifies nothing. Prove refusal before
  trusting acceptance.
- Seal the prediction before the result exists; freeze the
  interpretation before the judge speaks; no rescue after.
- Pin the oracle. A number without its oracle's hash is an anecdote.
- Keep the nulls. An interval that includes zero is a result, not an
  embarrassment.
- Witness disagreement between judges; never average it into false
  confidence.
- Audit the instrument on a schedule, and publish the audit whichever
  way it falls.
- Claims carry expiry dates. A claim's status can change while its
  text does not; date every status.

## Honest boundaries

- The novelty ladder's top rung (resists a budgeted baseline prover)
  is declared, not implemented.
- The five oracle coverage gaps found by the first strength audit are
  flagged but not yet fixed; the fix lands as a lane version bump.
- A two-judge faithfulness disagreement surface is designed
  (docs/research/2026-07-14-build-queue-2.md) but not built.
- This discipline measures instruments, not people. Nothing here
  grades a human; it grades the tools humans are asked to trust.
