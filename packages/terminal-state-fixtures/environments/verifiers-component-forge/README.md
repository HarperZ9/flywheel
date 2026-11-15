# verifiers-component-forge

Write and repair [verifiers](https://github.com/PrimeIntellect-ai/verifiers)
components against fully normative behavioral contracts. Each task hands the
agent a contract (a parser precedence ladder, a rubric arithmetic table, a
broken environment module, or a multiturn referee state machine) and expects
one Python module back. Scoring executes that module through the real
installed verifiers machinery in an isolated child interpreter over hidden
frozen probes, and compares terminal state (extraction strings, rewards,
metrics dicts, transcripts, stop reasons) against reference-derived frozen
expectations. No judge model; the reward path never touches the network.

## Families

| family | cases | the agent writes | scored by |
| --- | --- | --- | --- |
| parser-contract | 96 | a `vf.Parser` subclass for a stated precedence-ladder extraction contract | `parse_answer` over 1,720 hidden inputs, weighted by grammar cell |
| rubric-contract | 96 | a `vf.SingleTurnEnv` whose Rubric implements a stated scoring table | structural gate + 1,288 fixtures replayed through the real `Rubric.score_rollout` |
| rubric-repair | 77 | the repaired version of a mutated environment module shown inline | the same rubric driver; credit concentrates on fixtures where broken and reference disagree |
| referee-protocol | 64 | a `vf.MultiTurnEnv` referee for a stated deterministic game | 512 canned player scripts replayed through the real `MultiTurnEnv.rollout` |
| redaction-contract | 4 | a record-redaction function for synthetic secret markers | terminal JSON exactness plus a no-raw-marker leak gate |

337 cases, roughly 5,000 frozen probe comparisons. Every input and
expectation is committed as constants and re-derivable by one command
(`python generation/generate.py`), which builds each file twice in-process
and refuses to write on any difference.

## Reward

One weighted function, `terminal_state_match` (weight 1.0): the hidden-probe
match fraction for the case, computed parent-side with the documented
per-family weighting (grammar-cell weights for parser-contract, kill-set
concentration for rubric-repair, per-script credit with a 0.5
transcript-only partial for referee-protocol). Zero-weight diagnostic
metrics: `parsed_code_present`, `child_completed`, `structural_gate_pass`,
`probe_error_fraction`.

Discrimination is pinned by tests rather than asserted: the committed
reference solution scores 1.0 on every case, and curated known-bad
solutions (a weight normalizer, a constant-1.0 rubric with correct wiring,
the verbatim broken module, a delegating `rollout` override, a wrong reward
schedule) score at or below stated ceilings.

## Live-model evidence

`vf-eval` runs on one weak and one strong model, 5 shuffled examples
(seed 0) x 3 rollouts per family; raw outputs are committed under
[outputs/evals/](outputs/evals/).

| family | claude-haiku-4-5 | claude-sonnet-5 |
| --- | --- | --- |
| parser-contract | 0.323 | 0.907 |
| rubric-contract | 0.924 | 1.000 |
| rubric-repair | 0.871 | 1.000 |
| referee-protocol | 0.650 | 1.000 |
| redaction-contract | 1.000 | 1.000 |

The strong model beats the weak model on every family with headroom, and
parser-contract holds both models below ceiling. Honest notes: the three
1.000 sonnet cells and the redaction row are saturated at this 5-example
sample size (the frozen batteries still discriminate, as the haiku column
and the pinned known-bad ceilings show); referee-protocol's 0.650 haiku
average is largely the 0.5 transcript-only partial credit, meaning haiku
tends to get the state machine right and the reward schedule wrong.

## Design choices worth knowing

- **The reference is the exemplar.** For the rubric and referee families the
  oracle is the exact module text an ideal agent would emit; the generator
  executes that text through the real library to freeze expectations, so
  contract prose, oracle, and exemplar cannot drift apart.
- **Two independent derivations.** Referee expectations come from the real
  rollout loop AND from a pure fold of the state machine that shares no
  code with it; generation aborts on any disagreement.
- **The kill-check refuses non-discriminating tasks.** A repair mutant
  ships only if it flips at least two fixtures under the installed
  verifiers. This filter removed an entire operator (dropping a reward
  function's try/except) because the library already scores raising reward
  functions as 0.0.
- **Behavior, not diffs.** A behaviorally equivalent rewrite passes by
  design; hidden batteries carry boundary fixtures regardless of which
  mutation shipped, pushing battery equivalence toward semantic
  equivalence.
- **Inputs-only child.** The child interpreter (`python -I`, scrubbed
  environment, wall-clock kill) receives module source and case inputs
  only; oracle values and comparisons stay in the parent. This is a
  determinism-and-hygiene boundary, not a security sandbox.

## Reproduce

See [REPRODUCE.md](REPRODUCE.md) for exact commands (test suite, fixture
regeneration, and the per-family checks). The suite passes under both
verifiers 0.3.0 and the locked prerelease in `uv.lock`.
