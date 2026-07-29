# External grounding: where the tooling should change, and who already showed us

**Date:** 2026-07-26 | **Register:** internal (project-docs). Local paths are correct
here and forbidden on any public surface.

Searched the current releases, papers, and public discourse for work that bears on the
verification tooling, then checked each finding against this repo's actual code with a
probe. Six items changed a decision. Two of them contradict something I had written down
as settled, and one of them retires an idea I was about to claim as original.

Confidence labels are on every specific claim. Where I read the source myself I say so.

---

## 1. The bolt-on already has a socket, and it is called an environment

`verifiers` (Prime Intellect) exists to solve the exact problem the operator named as
architectural: **environment fragmentation, where a training environment is locked to one
training stack and cannot be reused across teams or frameworks.** Environments are
distributable Python modules, installed from a community Hub carrying 2,500+ of them, and
consumed by `prime-rl` with no code change in the trainer. Confidence high; read the v1
docs and a shipped example environment's source directly.

The API surface, verbatim from `environments/alphabet_sort_v1`:

```python
class AlphabetSortTask(vf.Task[AlphabetSortTaskData, vf.State, AlphabetSortTaskConfig]):
    @vf.reward(weight=1.0)
    async def alphabet_sort(self, trace: vf.Trace) -> float:
```

with packaging that is four lines of `pyproject.toml` and `dependencies = ["verifiers"]`.

**What this means for us.** A CC-1 criterion plus its `CertificateOracle` is already
shaped like one of these: a taskset generator (`certificates/generators.py`) and a pure
grader (`CertificateOracle.verify`). An adapter is small. What it buys is not popularity.
It buys the thing Ruling 9 said we could not get from our own lanes: **a stranger can run
our criterion inside a runner we did not author and compare verdicts.** That does not make
our checker independent, because the checker is still ours. It makes the *harness*
independent, which is a different and smaller claim, and it is the honest one.

### 1a. The idea I was about to claim as original is the ecosystem's default

The assessment called a decoupled candidate pool "the single best idea in the entire
corpus and no assessment proposed it." It is a good idea. It is also a **built-in**:
`verifiers` ships a `best-of-n` Env described as "`n` independent attempts per episode;
its metrics mark the argmax-reward sibling (`best`) and whether any reached
`--env.threshold` (`pass_at_n`) - rejection sampling and pass@k." Confidence high, quoted
from `docs/v1/env.md`.

So the baseline and the treatment are siblings drawn from one pool of independent
attempts. Our `uplift_bench.py` runs them as two sequential arms where the treatment's
first draw *is* the baseline, which is the nesting defect. **We are the deviation from a
known-good shape, not the innovator.** Build `harness/pool.py` to match that shape, cite
it, and drop the novelty framing.

### 1b. The reward interface cannot say "I could not tell", and that costs something real

`@vf.reward` returns `float`. Confidence high; that is the signature. A four-way verdict
has no faithful image in a float: PASS maps to 1.0, FAIL maps to 0.0, and **UNDECIDED and
UNVERIFIABLE have nowhere to go.** Mapping them to 0.0 is not a rounding loss. It is the
precise mechanism by which a harness failure, an out-of-scope instance, or two checkers
disagreeing gets taught to the policy as *the candidate was wrong*. `harness/verdict.py`
and the loss-masking in `rl_from_oracle.py` exist because of that mechanism.

Two consequences, and the second is the more useful one:

- Our adapter must **mask** non-dispositive verdicts out of the reward rather than zeroing
  them, and carry the full verdict plus its attribution in trace metadata so the receipt
  is not degraded on the way through.
- This is worth writing up for the upstream project as a short note: not "our design is
  better", but "this interface has no channel for *undecided*, here is the failure it
  produces, and here is a masking adapter that costs one optional return type." That is a
  contribution in the register the operator asked for, and it is useful to everyone
  building on that interface whether or not they ever look at this repo.

## 2. Someone else reached the same conclusion about benchmarks and environments

Nous Research's Atropos is built on the observation that **all verifiable RL environments
are nearly equivalent to benchmarks**, and v0.3 made benchmarking and evaluation a
first-class mode of the environments framework, shipping Reward-Bench 2 as its first
external benchmark. Confidence moderate; from the release announcement and repo README
rather than from reading the code.

That is independent arrival at the crucible / forum / learn thesis: the thing that grades
a training rollout and the thing that grades a benchmark submission are one artifact. It
is confirmation, not competition, and the correct response is a second thin adapter rather
than a position. Two adapters and no fork is also the concrete form of "the bolt-on is
treated as first class by the system it integrates into."

## 3. RFC 6962 is obsoleted, and the delta names two real gaps in our ledger

`merkle.py` implements RFC 6962. **RFC 9162 (Certificate Transparency 2.0) obsoletes it.**
Confidence high; read the RFC.

The good news first: the leaf `0x00` / node `0x01` domain separation is **unchanged**, and
it is unchanged for the reason we implemented it, second-preimage resistance. So
`merkle.py` stays correct and its 25 known-answer tests stay valid.

What 9162 adds is field-level, and I probed our ledger against it:

| RFC 9162 structure | Fields it requires | What `harness/ledger.py` emits |
|---|---|---|
| `InclusionProofDataV2` | `log_id`, `tree_size`, `leaf_index`, `inclusion_path` | `index`, `size`, `root`, `leaf`, `path`. **No `log_id`** |
| `ConsistencyProofDataV2` | `log_id`, `tree_size_1`, `tree_size_2` | `old_size`, `new_size`, `old_root`, `new_root`, `path`. **No `log_id`** |
| `SignedTreeHeadDataV2` wrapping `TreeHeadDataV2` | timestamp, tree size, root hash, extensions, **and a signature** | `head()` returns `{root, size, schema}`. **No timestamp. No signature.** |

Probed directly, not read: I built a five-entry ledger, took a head, appended three more,
and dumped every key of the head, the inclusion proof, and the consistency proof.

**Why `log_id` is not cosmetic here.** Our contest channel is designed so a *stranger's*
signed contest enters *our* chain, and our bundles are meant to be handed to people who
did not build them. A proof that does not name the log it came from cannot be
distinguished from a proof about a different log once two of them are in the same folder.
9162 added the field for that situation, and we built exactly that situation.

**And the signed tree head is not signed.** The Phase 1C Task 2 deliverable was named
"consistency proofs and signed tree head". The consistency proofs landed and are tested,
including the doctored-log attack. The head is a plain dict. `grep` for `sign` in
`ledger.py` returns one hit, in a docstring. This is a gap between what the plan said and
what the code does, and I am recording it as mine.

## 4. Sigstore names the property we claim and shows the prerequisite we skipped

The Sigstore client spec: verifiers validate inclusion proofs against a **signed** tree
head, and **should fetch the signed tree head in a manner that prevents equivocation** by
the log. Confidence moderate; from the client spec, read once.

Equivocation is a log showing two different views to two different readers. Our answer to
it is supposed to be the contest channel plus a kept head. But a consistency proof between
two roots the *presenter* chose proves only that the presenter can produce a
self-consistent pair. Without a signature over the head, a stranger keeping `h0` is
trusting our word rather than checking our signature, and the anti-equivocation property
is asserted rather than held.

So item 3's missing signature is not a nicety filed behind the interesting work. It is a
**prerequisite for a property the design already claims**, and `receipt_sign.py` already
has the primitives to close it.

## 5. The elicitation question moved, and it moved against our stack

Our spec records elicitation versus expansion as unresolved and refuses to design success
metrics around new capability. That stance survives, but the reason it matters here has
sharpened, and this is the finding with the most consequence for the ladder.

- **Spurious Rewards** (`arXiv:2506.10947`): random rewards bought +21.4pp on
  MATH-500 for Qwen2.5-Math-7B against +29.1pp for ground truth, and the same spurious
  training produced minimal or negative movement on Llama3 and OLMo2. The mechanism
  offered is code reasoning, a pre-existing Qwen behaviour whose frequency rises from 65%
  to over 90% after RLVR even under spurious reward. Confidence high on the numbers;
  read from the paper's own summary and its OpenReview page.
- **A preregistered causal partition** (`arXiv:2606.05932`) reports that for strong-prior
  Qwen models **elicitation accounts for 0.98 of gains and reward design for 0.02**, with
  the ordering reversed for weaker-prior families. Confidence moderate; from the abstract
  and listing, I have not read the full method.
- **Contamination** (`arXiv:2507.10532`) documents unreliable RL results traced to data
  contamination, which is the same failure our own unbounded pack manifest leaves open.

**Everything trained in this repo is Qwen2.5-Coder.** So our family is the one where
reward design is reported to buy least and where a reward carrying no ground truth is
reported to buy the most. Three things follow, and I am freezing them now rather than
after a run makes them inconvenient:

1. The **random-reward and format-only-reward control arms are not optional** and not
   deferrable to a later cycle. On a Qwen-only stack, a positive result without them is
   uninterpretable, because the literature's null hypothesis for our exact family
   predicts a large positive effect from a reward with no information in it.
2. The **non-Qwen rung is load-bearing**, not the "family spot check" the assessment
   called it. It is the only rung where reward design is predicted to be the dominant
   term. It still supports no generality claim at n=1, and it is still the rung that would
   tell us whether we measured our environment or measured Qwen.
3. The spec's stance should read **"unresolved in general, reported family-dependent, and
   our family is the adversarial case"**, which is stronger and more useful than
   "unresolved".

## 6. The public record already says the interval is the part nobody publishes

From current discourse and venue changes rather than from a paper:

- The same weights swing 10 to 20 points depending on the evaluation harness, and **the
  confidence interval is the most decision-relevant column and the one almost nobody
  looks at.** Confidence moderate; this is a widely repeated 2026 methodology claim, and
  the harness-swing figure is a range I did not verify independently.
- NeurIPS made reproducibility an official track (MLRC 2026). Confidence moderate.
- **"Every Eval Ever"** (`arXiv:2606.14516`) proposes a unifying schema and community
  repository for evaluation results. Confidence low on the details; I have the title and
  abstract only.

Two actions. First, the shipped page leads with the denominator, the interval, and the
minimum detectable effect, and puts the near-tautological limitation in the first
paragraph. That is already the posture and this is external support for keeping it when it
is unflattering. Second, **read the "Every Eval Ever" schema before designing any new
result document, and emit it alongside our receipt if it fits.** A receipt nobody can
aggregate is a receipt that only serves us, and the stated goal is a commons.

---

## What changes, in order

Nothing here displaces the assessment's Phase 0 honesty repairs, which stay first.

| # | Change | Grounded in | Cost |
|---|---|---|---|
| 1 | Sign the tree head: timestamp, `log_id`, signature over `TreeHeadDataV2`-shaped fields | RFC 9162, Sigstore client spec | small, primitives exist |
| 2 | Add `log_id` and explicit tree sizes to both proof types; version the proof schemas to v2 | RFC 9162 | small |
| 3 | `harness/pool.py` matching the `best-of-n` sibling shape, with a compute-matched oracle-free arm | `verifiers` `docs/v1/env.md` | medium, no GPU for the analysis half |
| 4 | Freeze random-reward and format-only-reward control arms into the prereg before the trainer exists | Spurious Rewards, the causal partition | writing only |
| 5 | Promote the non-Qwen rung from spot check to load-bearing | the causal partition's family dependence | prereg wording, one rung |
| 6 | `verifiers` adapter: taskset from the generator, `@vf.reward` from the oracle, non-dispositive verdicts masked and preserved in metadata | `verifiers` v1 API, read directly | small |
| 7 | Upstream note on the missing *undecided* channel in float-only reward interfaces | our own `verdict.py`, their signature | writing only |
| 8 | Read the "Every Eval Ever" schema before authoring any new result document | `arXiv:2606.14516` | reading |

## Corrections to my own record

- The decoupled candidate pool is **not** an original idea of this project. It is the
  shape `verifiers` already ships as `best-of-n`. Recorded before it reached any public
  surface as a novelty claim.
- `harness/ledger.py`'s tree head is **unsigned**, despite the Phase 1C Task 2 deliverable
  being named "consistency proofs and signed tree head".
- `merkle.py` cites RFC 6962, which is obsoleted by RFC 9162. The hashing is unaffected;
  the proof and head structures are not.

## Sources

- [Environments Hub: A Community Hub To Scale RL To Open AGI](https://www.primeintellect.ai/blog/environments)
- [verifiers docs/v1/env.md](https://github.com/PrimeIntellect-ai/verifiers/blob/main/docs/v1/env.md)
- [verifiers on PyPI](https://pypi.org/project/verifiers/)
- [Introducing Atropos, Nous Research](https://nousresearch.com/introducing-atropos)
- [Atropos v0.3 release notes](https://github.com/NousResearch/atropos/releases)
- [RFC 9162, Certificate Transparency 2.0](https://www.rfc-editor.org/rfc/rfc9162.html)
- [RFC 6962, Certificate Transparency](https://datatracker.ietf.org/doc/html/rfc6962)
- [Sigstore client spec](https://github.com/sigstore/architecture-docs/blob/main/client-spec.md)
- [Spurious Rewards: Rethinking Training Signals in RLVR](https://openreview.net/forum?id=4NeiwxQ2Bp)
- [What Does "True Minus Random" Estimate? A Pre-Registered Causal Partition](https://arxiv.org/html/2606.05932)
- [Reasoning or Memorization? Unreliable Results of RL Due to Data Contamination](https://arxiv.org/pdf/2507.10532)
- [Every Eval Ever: A Unifying Schema and Community Repository for AI Evaluation Results](https://arxiv.org/pdf/2606.14516)
- [MLRC 2026: Reproducibility as an Official Track at NeurIPS](https://blog.neurips.cc/2026/05/04/mlrc-2026-reproducibility-as-an-official-track-at-neurips/)
- [LLM Benchmark Methodology 2026](https://www.digitalapplied.com/blog/llm-benchmark-methodology-2026-contamination-leaderboard-guide)
