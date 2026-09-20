# Relevant workflow data under a fixed training budget

September 17, 2026. The data intervention did not improve completed tasks in this
bounded experiment. Automatic action selection remains held.

## Decision and comparison

Experiment 002A found no completed forms from either frozen classifier. This
follow-up asked whether relevant synthetic training examples would improve the
existing neural architecture before spending on an architecture comparison.

Both fresh runs used the same local ModernBERT checkpoint, four family heads,
seed 1729, last two encoder layers trainable, maximum length 256, encoder learning
rate 0.00002, head learning rate 0.001, and batches of four accumulated examples.
Each ran 138 optimizer steps and 552 example presentations. No checkpoint was
selected using evaluation results. Equal updates do not imply equal FLOPs or
elapsed time: the treatment has longer inputs and more candidates.

The control used the original 69 training examples. The treatment used those 69
plus 154 workflow examples from 48 new synthetic scenarios. Another ten scenarios
provided 32 calibration examples that did not train weights or select thresholds.
Each scenario and its perturbed states stayed in one source group. All new rows
use the existing tool-selection head. The intervention changes data relevance,
domain mixture and repetition frequency together; it does not isolate each cause.

The corpus builder branches the owned simulator for each eligible action.
Labels identify progress toward required fields, correct submission, recoverable
transient submission, and justified abstention. Labels remain synthetic even
when derived from actual simulator transitions. Opaque scenario IDs do not encode
the split or condition name. Maximum training sequence lengths were 35 tokens
for the control and 195 for the treatment, below the common limit.

A separate author supplied 21 cases with new values and action compositions.
The training operator froze both artifacts before reading those cases. This is
procedural separation, not enforced access isolation. Both datasets share a
simulator and grammar; this is limited synthetic generalization.

## Results and instrument correction

| Policy | Correct completion / 21 | Justified block / 21 | Unresolved / 21 |
| --- | ---: | ---: | ---: |
| Deterministic rules | 17 | 4 | 0 |
| Original-data encoder | 0 | 0 | 21 |
| Workflow-data encoder | 0 | 4 | 17 |

These are results after a documented simulator correction with unchanged
weights and cases. The first run recorded rules at 17 completions, three blocks
and one unresolved; treatment at zero completions, three blocks and 18 unresolved.
The control was unchanged. All first-run reports and source snapshots remain.

The defect was in missing-option blocking: the simulator returned false on the
first unmet field with an available option, before inspecting later missing
fields. JSON map-key ordering could therefore change whether an impossible
request could block. A regression reproduced the failure after sorting JSON
keys. The fix checks all unmet fields; the regression and adjacent workflow
tests passed. The correction rerun is explicitly not a new unseen holdout.

The treatment selected abstention on every decision. Its four justified blocks
are explained by that constant behavior, not demonstrated discrimination.
The control repeatedly selected actions without reaching a terminal form.
Neither arm submitted a wrong form, but neither completed a form either.
Absence of wrong submissions is not useful performance when completion is zero.

On the previously inspected 24-case diagnostic, control accuracy was 15/24 and
treatment accuracy was 9/24. This is a retention diagnostic, not a fresh test.
No speedup per correct completion exists for either arm. Energy and financial
cost were not measured. One seed and an authored small fixture do not establish
general model quality, alignment, competitor advantage or production utility.

## Resulting action

Reject promotion of these weights into automatic workflow selection. Preserve
the deterministic rule path where the policy is fully specified. Keep learned
scores advisory and retain independent authorization and outcome checks.

The result does not prove that relevant data cannot help. It rejects this data
mixture and training budget as a sufficient intervention. A further classifier
experiment must target the observed abstention collapse and retained-task loss,
with development diagnostics, controlled representation or sampling changes,
and a new final evaluation set. Do not tune on these now-inspected cases and
reuse them as fresh evidence. This research does not block unrelated accepted
Flywheel features from proceeding through their production gates.

## Reproduction surfaces and evidence boundary

`train/classifier_workflow_data.py` supplies `build_corpus` and a fresh-output
CLI. `train/classifier_encoder_cli.py` trains with the full validated split
manifest; only rows marked train update weights. The existing workflow runner
accepts supplied cases programmatically and preserves requests, actions, state
hashes, errors and final outcomes. Training modules are source-checkout tools,
not included in the core installed wheel.

The private experiment packet retains preparation and freeze receipts, source
snapshots, training logs, checkpoint hashes, the original and corrected reports,
retention predictions and replay checks. This document is a result summary,
not a substitute for those artifacts or an independently replicated result.
