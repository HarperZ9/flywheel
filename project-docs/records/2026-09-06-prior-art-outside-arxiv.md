# Prior art outside arXiv: the closure claim does not survive

Date: 2026-09-06. Question asked: is Flywheel first on the core idea, meaning a
receipt whose verdict can be re-derived, with an upstream failure degrading the
results that depend on it.

Answer: no, and the margin is not close. Four independent lines of prior art
predate the project, one of them by thirteen years and one of them a granted US
patent that is still in force.

## Why earlier sweeps missed this

`harness/transitive_witness.py` labels its own positioning "honest, from the
2026-07-06 arXiv sweep". That is the defect. The sweep read arXiv. Provenance
propagation was worked out in the data-lineage and software-supply-chain
communities, which publish to standards bodies, project sites, and the patent
office. An arXiv-only instrument cannot see any of them, so the conclusion it
produced inherited its blind spot rather than testing it.

Every source below was read live on 2026-09-06.

## What is established

**Independent re-execution and hash comparison, 2013.** The Reproducible Builds
project dates to DebConf13, and the Tor Project has shipped reproducible builds
since the same year. The verification shape is the one Flywheel calls
re-derivation: a third party rebuilds from source and compares the digest, so
the consumer never has to trust the original builder. Confidence high.

**Downstream invalidity over a derivation edge, filed 2015.** US 9,996,595 B2,
"Providing full data provenance visualization for versioned datasets", Palantir
Technologies, inventor Ethan Bond. Filed 2015-08-03, granted 2018-06-12, active
until 2036-08-10. The independent claim covers an edge "representing a
derivation dependency" being distinguished "to indicate that the first version
of the first versioned dataset potentially contains invalid data as a result of
the derivation dependency". Read that against `transitive_witness`: a node
grounded on a glut becomes a GAP, which is to say it *potentially* contains
invalid data rather than definitely. The semantics match. Confidence high.

The claim is drawn to a graphical user interface, which bears on infringement
and not on novelty. Nothing in Flywheel renders such a view. That is a lawyer's
question and this record does not answer it. The novelty question is answered:
the propagation rule was published in 2015.

**End-to-end pipeline verification, in-toto.** in-toto verifies attestations
against a signed layout across the whole chain of steps, described in its own
material as a system that does not check individual steps in isolation. The
"per-run primitives do not compose" premise in the module docstring is weaker
than it reads. Confidence high on the mechanism, moderate on the year.

**Invalidate and Derive are standard provenance relations.** The June 2026
survey below lists the field's relation vocabulary as Support, Derive,
Depend-on, Contradict, Invalidate, Trigger, Update, Use, Generate. Contradict
and Invalidate are the glut and the gap under other names, and they are
taxonomy, not a contribution. Confidence high.

**Counterfactual replay separating refuted nodes from downstream ones, October
2025.** GraphTracer (arXiv 2510.10581) builds Information Dependency Graphs
where an edge means node j depends on node i's output, re-executes the affected
portion after perturbing a node, and by its own description distinguishes
"nodes whose inherent outputs are erroneous from those merely receiving
corrupted upstream data". That is replay plus the glut and gap separation,
published eleven months before today. Confidence high.

## What survives, stated narrowly

The June 2026 survey "From Agent Traces to Trust" (arXiv 2606.04990) maps this
exact field. Read against its taxonomy, no system it surveys stores a verdict
and later re-verifies it against fresh state, and none propagates a
verification failure so that only downstream dependents degrade. Its open
problems include "Provenance-Aware Runtime Safety and Recovery".

So the surviving claim is about purpose and about shipping, and it is small.
GraphTracer replays to attribute a root cause for an observed failure, working
backward from a known bad outcome, offline, to generate training data.
`verify_frontier` re-witnesses to decide whether a stored verdict is still
valid now, which is a staleness question asked of a chain nobody has reported a
problem with. Same mechanism, different question.

The harder differentiator is the adversarial gate. `harness/adversarial_corpus.py`
scores the closure at 0 false accepts over 7 attacks with 2 controls, and a
discrimination test fails a deliberately weakened closure, so the corpus catches
something. No system in the survey ships a false-accept corpus against its own
propagation rule. That is the defensible asset.

That asset is stronger than the roadmap said, and finding out how cost a second
correction on the same day. `loop.py` does fold the closure, through
`grounding.recheck_grounding`: it resolves an envelope's cited ancestors out of
the store, re-witnesses each in its own oracle environment, folds
`transitive_verdicts`, and gates acceptance fail-closed, so a dependent of a
drifted ancestor never gets sealed. `tests/test_grounding_closure.py` holds all
seven arms through `run_loop`, positive control and localization control
included. The earlier claim that no shipped loop invokes the closure came from
grepping for `verify_frontier` and `validate_chain` rather than tracing the call
graph, which is this record's own error repeated at smaller scale on the same
afternoon.

The limit that is real: `grounding_recheck` defaults to False, because
`recheck_grounding` needs an oracle environment per ancestor and returns
UNVERIFIABLE for each one it does not get. Fail-closed plus a missing workdir
means turning it on by default would fail every grounded task. Recovering that
environment from the stored envelope is what makes the flag defaultable.

## What this changes

1. The `transitive_witness` docstring says the closure is what "the current
   literature does NOT publish" and calls path-conserved-MATCH "the novel
   object". Both are false. Corrected in the same commit as this record.
2. Public surfaces are clean. `scripts/check_claim_language.py` passes on all
   22, and the novelty language never reached README, `docs/`, or the package
   metadata. The overclaim lived in one internal docstring. Nothing published
   needs a retraction.
3. Any future priority sweep reads patents and standards bodies alongside
   arXiv. An arXiv-only sweep is not evidence about priority and should not be
   cited as though it were.
4. The same rule turned inward. A claim about what this repo does gets traced
   through the call graph, not grepped for a function name. PROJECT.md section
   6 item 2 has now been wrong in both directions inside 24 hours, first saying
   the closure did not exist and then saying no run invoked it, and both
   readings came from a name search standing in for a trace. Corrected in this
   commit, with the arms in `tests/test_grounding_closure.py` cited so the next
   reader can check the entry against the tests instead of trusting it.

## Competitor movement seen while gathering this

OpenKedge.io (Jun He, Deying Yu) is publishing a stack rather than a paper:
"Sovereign Assurance Boundary: Certificate-Bound Admission for Agentic
Infrastructure" (2606.11632) and "Sovereign Execution Broker" (2606.20520,
submitted 2026-06-18, 19 pages, 6 figures, 10 tables). The broker verifies a
certificate at the moment of mutation, checks revocation and drift, mints
short-lived scoped credentials, and logs signed decision records.

### Follow-up on OpenKedge, same day

The pair is further along than one sweep showed. Five papers in five months
from two authors, read live on 2026-09-06. The count is eight, and the second
follow-up below carries the correction and the two entries missing here:

```
2604.08601  2026-04-07  OpenKedge: Governing Agentic Mutation with
                        Execution-Bound Safety and Evidence Chains  (17 pp)
2605.15228  2026-05-13  Verifiable Agentic Infrastructure: Proof-Derived
                        Authorization for Sovereign AI Systems
2606.11632      2026-06  Sovereign Assurance Boundary
2606.20520  2026-06-18  Sovereign Execution Broker      (19 pp, 6 fig, 10 tab)
2609.02127  2026-09-02  Stored Is Not Supported: Typed Provenance and
                        Assertion Guardrails for Persistent AI Agents
```

The newest one names a repository, `github.com/openkedge/pci`, which the
earlier sweep had no reason to look for. Its own claim is a good one and it is
not ours: persistence changes availability rather than epistemic standing, so
material an agent stored is not thereby supported. Read against Flywheel that
is the same fail-closed instinct pointed at agent memory instead of at a cited
receipt.

What the repository is worth is the part that changes the positioning. Measured
through the GitHub API on 2026-09-06: created 2026-08-14, last pushed
2026-09-02, 71 KB, Python, MIT, 2 stars, 0 forks. No package under `openkedge`
on PyPI, and the `pci` name there belongs to an unrelated statistics library.
Against `flywheel-verify` 0.3.11 with twelve releases on PyPI out of a 12.2 MB
repository, the axes separate cleanly: they hold citation ground, this project
holds shipped ground. Neither holds adoption, and the star counts (2 against 1)
say so. That null stays in.

So the line to stop using is any count of their papers as though the count were
the gap. The gap is that a numbered preprint is citable and a wheel is not, and
eight preprints in five months compounds while a version bump does not. Nothing
here changes the re-execution finding above: the broker verifies a certificate,
the guardrail bounds an assertion, and neither re-runs the work.

### Second follow-up, same day: the repository count was wrong

The paragraph above measured one repository because one paper named it. That is
a name-directed sweep standing in for a search, which is the defect this record
was written to correct, repeated inside the record. Listing the account returns
seven repositories. Querying arXiv for the author pair returns eight papers.

```
2604.08601  2026-04-07  OpenKedge: Governing Agentic Mutation with
                        Execution-Bound Safety and Evidence Chains   17 pp
2604.22136  2026-04-24  Sovereign Agentic Loops: Decoupling AI Reasoning
                        from Execution in Real-World Systems         15 pp
2605.15228  2026-05-13  Verifiable Agentic Infrastructure            19 pp
2606.11632      2026-06  Sovereign Assurance Boundary
2606.20520  2026-06-18  Sovereign Execution Broker         19 pp, 6 fig, 10 tab
2608.11632  2026-08-12  Beyond Memory: A Transactional Continuity Kernel
                                                          9 pp + 6 pp appendix
2609.02925  2026-08-24  The Illusion of Independent Quorums          13 pp
2609.02127  2026-09-02  Stored Is Not Supported                      17 pp
```

Repositories under `github.com/openkedge`, measured through the GitHub API on
2026-09-06:

```
hardknock            Rust         2,870 KB   3 stars   pushed 2026-09-03
sitbench             Python       1,448 KB   1 star    pushed 2026-08-30
atp                  Java           646 KB   3 stars   pushed 2026-08-30
openkedge            TypeScript     341 KB   6 stars   pushed 2026-08-28
efd                  Python          79 KB   2 stars   pushed 2026-08-24
pci                  Python          71 KB   2 stars   pushed 2026-09-02
pdd-protocol-author  Python          14 KB   2 stars   pushed 2026-05-14
```

So the sentence "they hold citation ground, this project holds shipped ground"
does not survive its own measurement. About 5.5 MB across four languages is
code, and two of those repositories are evaluation artifacts: `efd` carries the
frozen 120-task benchmark its paper announces, and `sitbench` is a benchmark
harness for persistent identity. Flywheel's comparable artifact is the
false-accept corpus in `harness/adversarial_corpus.py`, seven attacks with two
controls.

What survives is narrower, and worth keeping for that reason. Queried on
2026-09-06, PyPI returns 404 for `openkedge`, `hardknock`, and `sitbench`,
crates.io returns 404 for `hardknock`, and npm returns 404 for `openkedge`.
`flywheel-verify` has twelve releases on PyPI. The difference sits in
distribution. Code exists on both sides, and the adoption null holds on both at
one to six stars.

One citation discrepancy, recorded rather than buried. The comment field on
2609.02127 names `arXiv:2608.11632` as its companion, while the entry above
cites `2606.11632` for Sovereign Assurance Boundary. Both identifiers resolve,
to different papers by the same authors, so the entry above is right and
2608.11632 is a paper it was missing.

Separately, Jakob Salfeld-Nebgen, "Governing Actions, Not Agents" (2606.26298,
2026-06-24), attests preconditions from independent authoritative sources bound
to a declared intent, with a proof-of-concept covering software deployment and
clinical prescribing. It records decisions in a tamper-evident log and does not
re-execute. Re-execution remains the axis where Flywheel is not crowded.

## Sources

- https://reproducible-builds.org/
- https://patents.google.com/patent/US9996595B2/en
- https://slsa.dev/spec/draft/build-provenance
- https://arxiv.org/html/2606.04990v1
- https://arxiv.org/html/2510.10581v1
- https://arxiv.org/abs/2606.20520
- https://arxiv.org/abs/2606.11632
- https://arxiv.org/abs/2606.26298
- https://arxiv.org/abs/2604.08601
- https://arxiv.org/abs/2605.15228
- https://arxiv.org/abs/2609.02127
- https://arxiv.org/abs/2604.22136
- https://arxiv.org/abs/2608.11632
- https://arxiv.org/abs/2609.02925
- https://github.com/openkedge/pci
- https://github.com/openkedge/efd
- https://api.github.com/users/openkedge/repos
- https://pypi.org/project/flywheel-verify/
