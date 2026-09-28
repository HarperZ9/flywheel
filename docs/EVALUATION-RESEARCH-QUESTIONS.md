# Questions the evaluation evidence must answer

## Motivation and evidence limits

Anthropic's [September 9 incident assessment](https://www.anthropic.com/research/alignment-assessment-cybersecurity-incidents)
reports unauthorized access during misconfigured evaluations. It distinguishes
the models' statements about being in a simulation from evidence about their
actions, describes gaps in pre-release auditing and notes limits on how simulated
replications generalize. These are the provider's reported findings, not an
independent replication by Flywheel.

The engineering inference is to preserve conditions, actions and uncertainty
alongside scores. Public commentary about private scaling curves is motivation
for investigation. It is not a measured capability trend, proof of future
behavior or a deciding source for an evaluation result.

## Separate the questions

| Question | Evidence needed | A result does not establish |
| --- | --- | --- |
| Could the agent complete the task? | Pinned task, resources, model and checker; success and failure runs | How it will behave on unrelated tasks |
| Did it attempt an unauthorized action? | Explicit task scope and an observed proposed action | That the action executed or caused harm |
| Did the boundary stop it? | Admission decision and independently observed effect | The agent's disposition without that boundary |
| Did it interpret the environment correctly? | Instructions, environment observations and declared interpretation | Its hidden internal state |
| Did the reviewer see the relevant evidence? | Capture scope, sequence gaps, timestamps and source references | Complete workstation observation |
| Can another reviewer check the result? | Versioned artifacts, deciding sources and reproducible checker | Independence from shared data or assumptions |

## Next controlled experiments

Use local synthetic resources and explicit task scope. No public target,
credential harvesting or live sandbox escape is needed for these cases.

1. **Reachability and authorization diverge.** A synthetic resource is reachable
   but outside the task's allowed set. Preserve the requested action, admission
   result and observed effect separately.
2. **The task has no authorized solution.** Score a supported stop or escalation
   distinctly from an unauthorized workaround and from an infrastructure error.
3. **The environment contradicts its description.** Present controlled evidence
   that differs from the task's initial environment description. Record what
   changes in proposed actions; a narrative acknowledgement alone is insufficient.
4. **A scorer always reports success.** Keep the wrong final state and its
   reported success claim. The task-specific checker must reject the mismatch
   even after every structural hash is recomputed.
5. **Observation is incomplete.** Remove or reorder a trace event. Remaining
   valid receipts must not create a claim of full observation.
6. **A dependency changes.** Change a task, scorer, adapter or producer version.
   Report the changed condition before comparing outcomes with the old baseline.

These are experiment requirements. The current [`incident-sim`](INCIDENT-SIM-EVALUATION.md)
slice checks submitted synthetic traces and final states; it does not yet run
the agent experiments above or validate real boundary enforcement.

## Reporting discipline

For each experimental comparison, retain attempts, completed runs, exclusions,
errors, repeated seeds or trials, resource limits and timing. Publish the
denominator beside rates. State which conditions were fixed and which changed.
Do not infer a scaling law from a pair of releases or turn a failed environment
setup into a model failure.

Keep imported claims, deterministic checks, human judgments and missing evidence
separate. [Independence](INDEPENDENCE.md) defines the corresponding limits on
byte witnesses, repeat runs and assessment. Missing provider reasoning remains
unavailable; summaries and observable actions must not be labelled recovered
hidden reasoning.
