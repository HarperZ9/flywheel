# mlflow-terminal-state

Terminal-state scoring for agent runs. A run's outcome is not pass-or-fail: it
is one of seven terminal states, and only some of them belong in a quality
denominator. Folding a provider outage or a blocked launch into the failure
count manufactures a regression that never happened. This environment measures
whether a model can apply that scoring contract exactly.

## Task

Single turn. The model receives one run record (five typed fields: execution,
provider, oracle, receipt, artifact) plus the classification contract, and must
return a JSON verdict:

```json
{"verdict": "refuted", "in_denominator": true}
```

Verdicts: `verified`, `refuted`, `unverifiable`, `rejected`, `malformed`,
`timeout`, `not_launched`. Only verified and refuted runs count in the quality
denominator; the contract makes exclusion rules as load-bearing as verdicts.
The subtle cases are deliberate: an artifact-hash mismatch refutes a run even
when its oracle passed (integrity beats the oracle), and a missing oracle is an
honest null, not a pass.

## Dataset

Every reachable field combination: 324 records, enumerated, no sampling. Ground
truth comes from the deterministic reference scorer embedded in the module, so
every answer is re-derivable on any machine. Distribution: 162 not_launched,
81 timeout, 27 rejected, 27 malformed, 19 refuted, 4 verified, 4 unverifiable;
23 of 324 belong in the denominator.

## Rewards

- `verdict_reward` (weight 0.7): exact verdict match against the reference.
- `denominator_reward` (weight 0.3): denominator membership match.

Both parse the last JSON object in the completion; unparseable output scores 0.

## Release status

The source is public in `HarperZ9/terminal-state-fixtures`. Version `0.1.1` is
present in the author's Prime Intellect account as a private Hub environment.
It is not yet a public Hub release.

## Provenance

Distilled from a production receipt-scoring pipeline (de-identified: no
provider names, no customer data). The reference scorer, the exhaustive
enumeration, and the reward discrimination checks were validated before the
private Hub upload: dataset builds identically twice, correct answers score
1.0, wrong verdicts and garbage score 0.0.
