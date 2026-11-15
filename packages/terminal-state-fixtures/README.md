<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/terminal-state-fixtures/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/terminal-state-fixtures/main/docs/art/hero-light.svg" alt="terminal-state-fixtures: Score AI agents by the state they leave, not by their transcript. Bundles of fine lines carry the work through 4 stations, record, score, verdict and denominator, along a sweeping path into a bright core." width="100%">
</picture>

# terminal-state-fixtures

Score AI agents by the state they leave, not by their transcript.

```
uv venv && uv pip install verifiers pytest
```

[![license](https://img.shields.io/badge/license-MIT-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/terminal-state-fixtures/blob/main/LICENSE)
![python 3.11+](https://img.shields.io/badge/python-3.11%2B-e6e1d6?style=flat-square&labelColor=1a1712)

<img src="docs/art/terminal-state-fixtures-header.svg" alt="terminal-state-fixtures, evaluation environments that score an agent by the state it left behind. Score the state, not the story.">

Evaluation environments that score an AI agent by the terminal state of its
work, not by what its transcript claims. Each environment ships an exhaustive
dataset, a deterministic reference scorer, and rewards whose discrimination is
pinned by tests, so every score is re-derivable on any machine.

## See it work, step by step

The [animated explainer](https://harperz9.github.io/repo-explainers/terminal-state-fixtures.html)
walks through the five-field run record enumerated into 324 rows, the eight-rule reference scorer, five records scored, the 23-row quality denominator, the two rewards, and the component-forge environment. Every value on it is output from this repository. Its
source is [docs/explainer/index.html](docs/explainer/index.html).

## Watch

[![Models do what training pays for: a narrated film, 2 min](https://harperz9.github.io/media/explainers/incentives/poster.jpg)](https://harperz9.github.io/explainers.html#incentives-h)

**[Models do what training pays for](https://harperz9.github.io/explainers.html#incentives-h)** (2 min, narrated, captioned). These environments pay a model for the state its work leaves and for the runs it excludes, so the reward measures what was meant. The film page carries the transcript, the sources and recall questions.

## Walkthrough

Install it, run it once, then use the main feature. Each command below is real, and so is its output.

1. **Get it.** Clone the first environment and install its tools with uv.

   ```text
   $ git clone https://github.com/HarperZ9/terminal-state-fixtures && cd terminal-state-fixtures/environments/mlflow_terminal_state
   $ uv venv && uv pip install verifiers pytest
   ```

2. **Score a record.** The reference scorer reads a run record's five fields. An oracle pass with a broken receipt is refuted.

   ```text
   record: returned / ok / oracle pass / receipt mismatch / artifact match
   verdict refuted, in_denominator true
   ```

3. **A run with no oracle.** A run with no independent check is unverifiable and stays out of the quality denominator.

   ```text
   record: returned / ok / oracle absent / receipt verified / artifact match
   verdict unverifiable, in_denominator false
   ```

4. **Run the pinned claims.** The tests pin exhaustiveness, the rewards and the integrity rule. They were not run for this page.

   ```text
   $ uv run pytest tests/ -q
   ```

## Why terminal state

A transcript says what a model believes happened. The environment's terminal
state says what happened. When the two disagree, the terminal state wins, and
an evaluation built on it cannot be talked into a better score. The same
discipline covers the denominator: a provider outage or a blocked launch is
excluded from the quality denominator rather than counted as a failure, so a
regression in the numbers means a regression in the behavior.

## Environments

### mlflow-terminal-state

<img src="docs/art/record-to-verdict.svg" alt="Eight stages taking one run record to a verdict: run record, launched, timeout, provider, integrity, oracle, verdict, denominator. A record carries five fields: execution with four values, provider with three, oracle with three, receipt with three and artifact with three. Every combination is enumerated, so the dataset is 324 rows with no sampling. Scoring applies eight rules in a fixed order. A blocked or never launched execution is not a run at all and leaves the denominator. A timeout reached no terminal answer and leaves it. A structured provider refusal is not a task failure and leaves it. Output that never parsed into a claim leaves it. A receipt mismatch or an artifact mismatch refutes the run even when the oracle passed, because integrity outranks the oracle, and that verdict counts. An absent oracle is an honest null rather than a pass and leaves the denominator. An oracle pass verifies and an oracle fail refutes, and both count. Seven terminal verdicts exist and only two of them, verified and refuted, belong in the quality denominator, which is 23 of the 324 rows. Three outcomes: a verdict that counts, a verdict that counts against the run, and a record excluded from the denominator entirely.">

Classify agent-run records into seven terminal verdicts and decide which runs
belong in the quality denominator. 324 records, every reachable field
combination, no sampling. The public source is this repository. Version `0.1.1`
is staged privately on Prime Intellect's Environments Hub as
`zaindanaharper/mlflow-terminal-state`; it is not yet a public Hub release.

Load it directly:

```python
import mlflow_terminal_state

env = mlflow_terminal_state.load_environment()  # a verifiers SingleTurnEnv
dataset = mlflow_terminal_state.build_dataset()  # 324 rows, deterministic
```

After a public Hub release, install it from the Hub and evaluate with the
[verifiers](https://github.com/PrimeIntellect-ai/verifiers) toolchain. Until
then, use the public source in this repository.

Full task, dataset, and reward spec:
[environments/mlflow_terminal_state/README.md](environments/mlflow_terminal_state/README.md).

### metr-terminal-state-runs

Expose the same exhaustive 324 terminal states through METR Task Standard's
`TaskFamily` interface. The runtime is standard-library only; a pinned official
METR Git dependency verifies the pytest-plugin boundary during development.
The fixture has no network, model, auxiliary VM, judge, or mutable-state
dependency and is not represented as accepted or endorsed by METR.

Reproduce and inspect the exact classifier contract:
[environments/metr_terminal_state_runs/README.md](environments/metr_terminal_state_runs/README.md).

### verifiers-component-forge

<img src="docs/art/contract-to-reward.svg" alt="Eight stages taking a contract to a reward: family, contract, model writes, structural gate, child process, visible fixtures, hidden probes, terminal reward. Five families are shipped: parser contract, rubric contract, rubric repair, referee protocol and a synthetic redaction contract, carrying 337 cases in total. Each case shows the model a normative contract and, for the repair family, one mutated environment module alongside it. The model writes a component. A structural gate checks that the answer parsed into code and has the declared shape. The code is executed in a child process rather than in the harness, so a crash is a score and not an outage. Visible fixtures are the ones quoted in the prompt. Hidden probes are frozen ahead of time and never shown, and there are 5,058 frozen expectations across the five families, counting 1,720 parser probes, 1,288 rubric contract fixtures, 1,518 repair fixtures, 20 redaction fixtures and 512 referee scripts. The referee family replays its canned player scripts through the real multi-turn rollout loop and compares transcripts, rewards and stop reasons, with an independent pure fold of each state machine cross-checking every frozen expectation. Reward comes from the terminal output of the child process. Three outcomes: full credit when the hidden probes agree, the frozen no-op share when the broken module comes back unchanged, and zero when nothing runs.">

Write and repair verifiers components against terminal-state contracts. The
environment includes parser-contract, rubric-contract, rubric-repair,
referee-protocol, and synthetic redaction contract families (337 cases,
~5,000 frozen probe comparisons). The repair family shows the agent one
mutated environment module plus its normative contract; credit concentrates
on hidden fixtures that distinguish broken from repaired behavior, so
returning the broken module verbatim scores at most the frozen regression
share. The referee-protocol family has the agent build a deterministic
multiturn referee; scoring replays canned player scripts through the real
MultiTurnEnv rollout loop and compares transcripts, rewards, and stop
reasons, with an independent pure fold of each state machine cross-checking
every frozen expectation. The redaction family uses fake secret markers
only, scores terminal JSON output, and pins that expected outputs preserve
public metadata while removing every raw marker value.

Reproduce:
[environments/verifiers-component-forge/REPRODUCE.md](environments/verifiers-component-forge/REPRODUCE.md).

## The claims are tests

<img src="docs/art/fixture-table.svg" alt="A table of fourteen rows: what the fixtures declare, how many of it there are, and where each number is read from. Three environments are shipped. A run record has five fields, and enumerating every combination gives 324 rows with no sampling. Seven terminal verdicts exist, and only 23 of the 324 rows belong in the quality denominator. The component forge ships five families holding 337 cases and 5,058 frozen expectations, of which 512 are referee scripts replayed through the real rollout loop and 77 are repair cases. Eighty-four test functions pin the claims. Ten evaluation runs are recorded in the tree across 144 rollouts, all of them for the component forge. No scored run is recorded for the first environment, so nothing here is evidence about how a model performs on it.">

The spec's validation claims are pinned in
[environments/mlflow_terminal_state/tests](environments/mlflow_terminal_state/tests):
the dataset is exhaustive and builds identically twice, correct answers score
1.0, wrong verdicts and garbage score 0.0, integrity beats the oracle, and a
missing oracle is an honest null rather than a pass.

```bash
cd environments/mlflow_terminal_state
uv venv && uv pip install verifiers pytest
uv run pytest tests/ -q
```

The component-forge claims are pinned in
[environments/verifiers-component-forge/tests](environments/verifiers-component-forge/tests):
frozen data regenerates deterministically, reference components score 1.0,
known-bad implementations fail, and redacted expected outputs contain no raw
synthetic secret markers.

## Reusing the pattern

To build a terminal-state environment for another tool: enumerate the reachable
states of the thing being scored, write the reference scorer first, generate the
dataset from the scorer so ground truth is re-derivable, then pin the scorer's
subtle cases and the rewards' discrimination as tests. The environment here is
small enough to read in one sitting and serves as the worked example.

One environment is public-source and staged privately on the Hub today. More
follow as they clear the same publication bar.
