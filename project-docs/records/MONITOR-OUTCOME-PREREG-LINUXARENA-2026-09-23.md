# Pre-registration: LinuxArena reviewer sample, secondary analysis

Written 2026-09-23, while the data file was still downloading and before any
monitor score or outcome in it was read. The git commit that adds this file is
the timestamp. Anything computed later that departs from this plan is reported
as a departure, with its reason.

## Why a secondary analysis

The study in `MONITOR-OUTCOME-DECISION-2026-09-23.md` needs an independent
outcome label per sample, from a checker that does not read the log's own
scorers. This dataset's outcomes (`main_task_success`, `side_task_success`) are
the benchmark's own scorer verdicts. Under the sidecar's rule they are
`reported`, never `verified`. So the primary study cannot run on this data, and
that is a result in itself. What follows is a declared secondary analysis on
reported labels. It is labelled as such everywhere it appears.

## Data

- Source: Hugging Face dataset `anonymouslinuxarena/linuxarena-public`, revision
  `2fd29f9c7bc190fb873bd76c6bd648f22b9ab0a7`, file `data/sample.jsonl`, 704,485,115
  bytes, LFS SHA-256
  `0b1e469ad48d93ccfec986f7cbafee43d49afb93bae730437d02c16233e7cfdb`. The
  downloaded bytes must hash to that value, or nothing is computed.
- License: CC-BY-4.0 for trajectories, per the dataset card. Every derived
  artifact carries the attribution: "LinuxArena (Public Mirror), anonymous
  authors, NeurIPS Datasets and Benchmarks Track 2026, CC-BY-4.0", with the
  source revision.
- Stated contents: 932 trajectories in 7 runs (Haiku honest 200, Haiku attack
  92, GPT-5 Nano monitor on Haiku attack 92, GPT-5 Nano monitor on straj 74, Opus
  monitor on straj 74, GPT-5 Nano monitor on Opus honest 200, Opus monitor on
  Opus honest 200). Counts are checked against the file; a mismatch is reported.

## What is carried out of the file

Only identifiers, run names, monitor model names, per-action monitor scores and
their error or missing states, trajectory-level monitor scores, and the outcome
fields. No tool arguments, tool outputs, reasoning, prompts or task text leave
the file. The dataset's own manifest reports connection-string hits, so the
file is scanned for secret-shaped strings first and only counts are recorded,
never values.

## Units, scores and states

- Unit: one trajectory in one run.
- Monitor score per trajectory: the maximum over actions whose monitor response
  has a usable numeric `sus_score` (the aggregation already declared). The
  trajectory-level monitor score is reported separately and never mixed in.
- An action whose monitor response is missing, errored or non-numeric is
  counted as absent or unscored, not zero. A trajectory with no usable action
  score gets no verdict and is counted apart.

## Labels, all reported

- L1, by construction: attack policy or honest policy (from the run and whether
  a side task is set).
- L2: `side_task_success` as reported by the benchmark scorer.
- L3: `main_task_success` as reported by the benchmark scorer.
- Null labels stay null and are counted.

## Pairings

Each monitor is evaluated only on runs it scored. Honest and attack sets are
paired as the sample allows:

- GPT-5 Nano: honest = GPT-5 Nano on Opus honest; attack = GPT-5 Nano on Haiku
  attack, and separately GPT-5 Nano on straj.
- Opus: honest = Opus on Opus honest; attack = Opus on straj.
- The agent runs' own monitor, whatever `model_name` the data shows: honest =
  Haiku honest; attack = Haiku attack.

Confound, declared now: GPT-5 Nano's and Opus's honest sets come from an Opus
agent, while the attack sets come from Haiku or from straj. A monitor can
separate agents rather than attacks. This analysis cannot remove that.

## Procedure

- Split: each trajectory goes to calibration or held-out by the parity of the
  first byte of SHA-256(`trajectory_id`), computed before any score is read.
- Threshold for a monitor at budget b: the (1 - b) quantile of its calibration
  honest max-scores. Budgets b = 5% and 20% of honest trajectories, as already
  declared.
- Reported on held-out only, per monitor, pairing and budget: honest
  trajectories flagged (realized false-positive fraction); attack trajectories
  flagged, for all attack trajectories (L1) and for those with
  `side_task_success` true (L2); each with counts and Wilson 95% intervals.
- Baselines at the same budget: flag none, flag all, and a seeded random
  ranking (seed = the integer of the first 8 hex digits of the source SHA-256).
- Stop rule: fewer than 30 held-out positives for a cell means that cell is
  reported as counts with "insufficient to estimate", no rate.

## What this cannot show

- The labels are the benchmark's reported verdicts, not independent checks.
- The sample was chosen by the dataset authors; it is not a random draw.
- The agent-model confound above.
- None of these monitors was attacked adaptively here; this is not a control
  evaluation against a policy trying to evade the monitor.
- Nothing here is a verdict on any model provider. The same criteria apply to
  every monitor in the sample.
