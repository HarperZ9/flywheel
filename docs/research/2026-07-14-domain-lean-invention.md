# Domain dossier: lean-invention

Machine conjecturing and kernel-verified proving in Lean, surveyed 2026-07-14.
Every claim below carries its source URL and the source's own date inline.
Findings from the research fan-out were adversarially checked against their
primary sources; only material that survived appears here, and the nulls are
first-class content, not filler.

## 1. The frontier in five sentences

Kernel-checked proving of closed competition problems is the mature half of
this domain: AlphaProof reached silver-medal level on IMO 2024 with formal
Lean proofs (Nature, published 12 Nov 2025,
https://www.nature.com/articles/s41586-025-09833-y), and a vendor post dated
26 Jun 2026 (Logical Intelligence blog) claims near-total PutnamBench
coverage, so far without independent replication. Machine conjecturing is the
immature half: the systems that generate conjectures at scale
(LeanConjecturer, https://arxiv.org/abs/2506.22005, Jun 2025; minimo, NeurIPS
2024, https://arxiv.org/abs/2407.00695; STP,
https://arxiv.org/abs/2502.00212, Feb 2025) define novelty mechanically, as
compiling plus resisting a cheap tactic or being barely provable, not as
mathematical interest. The strongest research-level formal result located in
this pass resolved a human-posed open problem in commutative algebra
(https://arxiv.org/abs/2604.03789, Apr 2026); no published system closes the
loop from machine-generated conjecture to recognized research novelty under a
kernel check. The measurement floor is soft: an ICML 2026 audit mechanically
certified 398 defective statements across five standard Lean benchmarks
(https://arxiv.org/abs/2606.29493, submitted 28 Jun 2026; high confidence on
the count), and reported autoformalization faithfulness can move by 25 or
more percentage points with the choice of semantic judge (moderate
confidence, see null 5). For a verified-inference platform the open surface
is the verification layer itself, graded novelty verdicts, benchmark defect
gates, and witnessed faithfulness checks, rather than the proving horsepower.

## 2. Confirmed findings

None. Zero findings survived the full verification chain in this pass:
everything the fan-out produced was refuted on specific numbers, contradicted
by its own cited source, reduced to vendor-claim status, or held only as a
null. This section is left empty rather than backfilled from weaker evidence.
The nulls below carry the dossier.

## 3. Honest nulls

1. **No machine-generated, research-novel, kernel-verified conjecture
   exists in the published record.** No system yet produces conjectures that
   mathematicians recognize as research-novel and that are kernel-verified at
   scale. The strongest research-level result located
   (https://arxiv.org/abs/2604.03789, Apr 2026) formally resolved a
   human-posed open problem in commutative algebra; the conjecture itself was
   not machine-generated.

2. **The field's operational definition of novelty is weak.**
   LeanConjecturer's "novel" (https://arxiv.org/abs/2506.22005, Jun 2025)
   means compiles, not in Mathlib, and not aesop-provable; STP's
   (https://arxiv.org/abs/2502.00212, Feb 2025) means barely provable by the
   current prover. Neither measures mathematical interestingness, and no
   accepted metric for it exists in the literature.

3. **The 99.4% PutnamBench claim is unreplicated.** Aleph's 99.4% figure
   comes from a vendor blog post (Logical Intelligence, dated 26 Jun 2026;
   high confidence the post states it, unknown whether it replicates). The
   official trishullab leaderboard page could not be independently rendered
   during this research, and the result has no peer-reviewed replication yet.

4. **Benchmark saturation numbers are confounded by dataset defects.** An
   ICML 2026 audit (https://arxiv.org/abs/2606.29493, submitted 28 Jun 2026)
   mechanically certified 398 defective statements (counterexamples, vacuous
   theorems, unsound axioms) across five standard Lean benchmarks (high
   confidence). Headline miniF2F and PutnamBench percentages are therefore
   measured against partially wrong yardsticks.

5. **Autoformalization faithfulness has no stable measurement.** The choice
   of semantic-faithfulness judge can shift reported scores by 25 or more
   percentage points (moderate confidence; this figure comes from the
   research notes for this pass and did not carry a verified source URL
   through checking). Type-correctness does not certify that a formal
   statement means what the informal one meant.

6. **Self-play conjecturing has shown training-signal value only.** Neither
   minimo (https://arxiv.org/abs/2407.00695, NeurIPS 2024) nor STP
   (https://arxiv.org/abs/2502.00212, Feb 2025) reports any generated
   conjecture that entered a human mathematical corpus or was judged
   independently interesting.

7. **AlphaProof's published wins are competition wins, not new
   mathematics.** The results are on problems with known answers under
   multi-day compute budgets; contemporaneous reporting put P6 at over two
   days in the non-timed setting (moderate confidence). The Nature paper
   (https://www.nature.com/articles/s41586-025-09833-y, published 12 Nov
   2025) makes no open-problem or new-mathematics claim.

## 4. Dropped in verification

Ten findings from the research fan-out failed adversarial checking against
their primary sources (mismatched numbers, wrong comparators, or exclusivity
claims contradicted by the cited paper itself) and are excluded from this
dossier rather than repaired.

## 5. Build candidates

### 5.1 Benchmark defect gate

Grounded in null 4. Before any Lean benchmark score enters a receipt, screen
the statement set for mechanically certifiable defects: nonstandard axioms,
`sorry` usage, and hypotheses that derive False (vacuity). A score over an
unscreened set is labeled as such in the receipt; the label is the feature.

- **Pour-back target:** `C:/dev/local-model/harness/benchmark_receipts.py`
  (a `hygiene` field on the benchmark receipt) plus a new
  `harness/benchmark_hygiene.py` checker.
- **Smallest committable first slice:** the `hygiene` schema field plus a
  checker that flags `sorry` and nonstandard axiom usage in a list of Lean
  statements, with one test on a known-defective fixture. No prover, no
  network.

### 5.2 Novelty ladder in the conjecture forge

Grounded in null 2. Replace binary novelty with a graded ladder the receipt
must state: L0 compiles, L1 absent from the corpus (already implemented,
corpus-relative hash), L2 not closed by the cheap decision tactic, L3 not
closed by the baseline prover at a declared budget. The receipt reports the
rung reached and never the word "novel" alone, which keeps the platform's
claims strictly below the field's known measurement ceiling.

- **Pour-back target:** `C:/dev/local-model/harness/conjecture_forge.py`
  (schema bump to `flywheel.conjecture-forge/v2`).
- **Smallest committable first slice:** add the rung field and implement
  L0 through L2 with the existing omega judge; one test showing a
  corpus-absent but tactic-closable conjecture lands on L1, not L2.

### 5.3 Two-judge faithfulness disagreement surface

Grounded in null 5. Since judge choice alone can move faithfulness scores by
double digits, never report a single-judge number: score each
(informal, formal) pair with two independent judges and make the
agreement/disagreement verdict the first-class output. Disagreement rate is
the honest measurement the field currently lacks.

- **Pour-back target:** new `C:/dev/local-model/harness/faithfulness_gate.py`
  emitting witnessed records alongside the existing receipt chain.
- **Smallest committable first slice:** the record format for
  (informal, formal, judge_a_verdict, judge_b_verdict) plus a scorer that
  computes the disagreement rate over a ten-pair hand-built fixture, with a
  test asserting the rate on that fixture.

### 5.4 Conjecture gradable lane

Grounded in nulls 2 and 6. Self-play conjecturing produces training signal
whose value is asserted, not witnessed. Turn forge output into a gradable
lane: each generated conjecture becomes a task item graded by kernel check
plus ladder rung, in the same lane format the harness already runs, so the
signal enters the flywheel as re-checkable data.

- **Pour-back target:** `C:/dev/local-model/tasks/` (new lane spec consumed
  by the existing lane runner).
- **Smallest committable first slice:** the lane spec JSON plus five
  hand-checked seed items generated by `conjecture_forge` and graded,
  committed under `tasks/` with one runner test that loads and grades them.
