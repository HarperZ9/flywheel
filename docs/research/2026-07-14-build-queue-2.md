# Build queue 2: what the six dossiers earned (2026-07-14)

Source: six adversarially verified domain dossiers (this directory, same
date), 18 agents, every claim checked against its cited source, dropped
findings counted and never reproduced. This queue orders the 24 surviving
build candidates by leverage and by what already exists to anchor them.
Each item names its smallest committable slice. Depth work from the same
day that already shipped: the conjecture forge with POST /api/invent, the
measurement-tension ledger with GET/POST /api/tension holding the real
Hubble, W-mass, and g-2 pairs on frozen sources, and the learning-loop
idempotence fix.

## P0: anchored on mechanisms that shipped today

1. **Novelty ladder in the conjecture forge** (lean-invention). The field's
   novelty definitions are mechanical and weak; make ours graded and honest.
   Rungs: L0 compiles, L1 corpus-absent, L2 not closable by the cheap
   tactic ladder, L3 not closable by a budgeted baseline prover. Slice:
   rung field in the forge receipt (schema v2), L0-L2 with the existing
   judge, one test showing corpus-absent but tactic-closable lands L1.
2. **Published-pair sigma fixtures** (physics-tension). The ledger already
   recomputed 5.80, 0.59, and 5.37 sigma live, matching the published
   characterizations. Slice: pytest fixtures encoding the three real pairs
   so the recomputation is a regression, not a demo.
3. **Stale-claim dataset** (physics-tension). Six dated nulls (g-2, CDF W,
   S8, Hubble shape, DESI, CMD-3) as records with claim text, as-of date,
   status, sources. Slice: dataset/physics_tension_claims.jsonl, no
   harness wiring.

## P1: the bench's own floor, and the unclaimed quadrant

4. **Oracle strength audit** (agent-reliability). UTBoost found false-pass
   patches behind 24.4% of a major leaderboard; audit our own hard set the
   same way. Slice: scripts/oracle_strength_audit.py runs a non-solution
   battery (empty, constant stubs, one-line mutants) against every hard_v2
   oracle, writes a per-task false-pass report, flags admission records.
5. **Distributional pass@k forecaster with sealed predictions**
   (agent-reliability). The dossier's strongest null: nobody pairs a
   measured per-model diversity coefficient with sealed pre-registered
   best-of-n forecasts. That is the eta program. Slice: fit mode in
   scripts/passn_model.py over the per-task outcome vectors, held-out
   forecast as a content-addressed artifact, loud failure when held-out
   error exceeds the iid baseline.
6. **Assisted/unassisted split in eval receipts** (learning-academy). The
   field's central measurement defect is conflating assisted practice with
   unassisted outcomes (the -17% Bastani result is the warning). Slice:
   two schema fields plus a validator that rejects uplift claims citing
   only the assisted channel.

## P2: new modules, each one committable slice

7. **Fold-with-receipt context ledger** (context-provenance): fold returns
   summary + sha256 + byte length, unfold returns exact bytes, round-trip
   test.
8. **Constraint pinning across compaction** (context-provenance): measured
   elsewhere, compaction raises constraint violations from 0 to 30%;
   pinning restores 0. Pinned text survives byte-exact, regression test.
9. **Offset-bound citation verifier** (context-provenance): citations as
   {source_hash, start, end, quote_hash}; verifier re-slices the snapshot
   and returns verified or drift.
10. **Receipt transparency log** (context-provenance): append-only Merkle
    chain over envelope hashes, recomputable root.
11. **Spacing scheduler with classroom priors** (learning-academy): item
    history to dated review queue, 7-day intervals, capped re-exposures;
    priors table cites the classroom d = 0.54, not the lab 0.85.
12. **Citation-anchor verifier** (physics-tension): does the quoted number
    appear in the cited source. Regression: the CCHP pair the dossier's
    own verification caught (absent in 2503.11769, present in 2408.06153).
13. **Benchmark defect gate** (lean-invention): flag sorry and nonstandard
    axioms in Lean statement lists; 398 certified-defective statements
    across five public benchmarks is the cautionary number.
14. **Two-judge faithfulness disagreement surface** (lean-invention):
    judge choice moves faithfulness scores 25+ points; witness the
    disagreement instead of averaging it away.
15. **Tutor-turn behavior scorer** (learning-academy): guiding-question vs
    answer-giveaway ratio into the session receipt.
16. **Difficulty-gated compute allocation A/B** (agent-reliability):
    budget-matched replay, uniform best-of-3 vs headroom-weighted.
17. **Distinguishing-input selector** (agent-reliability): offline replay
    of disagreeing candidates executed on generated inputs, accuracy vs
    the consensus@k ceiling.
18. **Quote-your-own-work retention probe** (learning-academy): an
    instrument spec, never claimed as neural evidence.
19. **Long-context quant gate** (compute-frontier): fixed long-context
    probe in the release checklist for shipped artifacts.

## Process lessons poured back

- Workflow args must be passed as a JSON object, not a string; one writer
  agent received a literal "undefined" date and the file needed a rename.
  Scripts should read args defensively.
- The three-stage shape (research, refute, write) caught a real
  misattribution before it entered the record. Keep the refuter
  independent and default-to-refuted.
- Every dossier's confirmed-findings section shrank under verification and
  the nulls became the load-bearing content. That is the expected shape
  of an honest sweep, not a failure of the researchers.
