# Corrections

Every correction to a published number on this page, with what it was, what it
is, and why it was wrong. Nothing is removed from this list.

## 2026-07-26: final training loss

**Was:** final train loss 0.035
**Is:** final logged 0.444, minimum 0.359, mean 0.492 across 202 logged points,
over 2020 steps and 2 epochs

**Why it was wrong.** 0.035 was read from a Hugging Face Trainer end-of-run
summary field. The training run was resumed twice, and that field averages the
loss accumulated in the final segment across the step count of the whole run.
The numerator covers one segment and the denominator covers three, so the value
is roughly ten times too small and describes no property of the model.

The number appears nowhere in the training log. The lowest loss the run ever
logged, at any step, is 0.359.

**How it was found.** By reading the checkpoint's `trainer_state.json` directly
rather than the summary field: 202 logged points, first 0.788, last 0.444.

## 2026-07-26: training runtime

**Was:** 3.2 hours
**Is:** about 34.2 hours of training across two recorded segments, inside a
46.9 hour window from the final start to completion

**Why it was wrong.** Same resume accounting. The reported `train_runtime` of
11,590 seconds is exactly 3 hours 13 minutes 8 seconds, which the training log
shows is the elapsed time of the **final segment alone**. An earlier segment ran
30 hours 59 minutes and reached step 1881 of 2020 before it was interrupted. The
two together are about 34.2 hours, so the published figure understated the work
by roughly eleven times.

**The same arithmetic explains the loss figure**, which is worth showing because
it turns two separate corrections into one mechanism. The final segment covered
roughly 139 of 2020 steps, or 6.88% of the denominator. A segment mean of about
0.51 divided across the whole run reports as 0.035. The logged loss over the final
steps is 0.44 to 0.49, so 0.51 is the right neighbourhood, and 0.035 was never a
loss at any point in training.

**Source.** The training log's own progress readings and its start and completion
markers, read directly rather than taken from the summary field.

**What did not change.** Every hash on this page. The model file, the adapter,
the LoRA GGUF, the corpus, and the packed shards are unaffected by this
correction, and each one still re-derives from the bytes you download.

## Also corrected elsewhere, recorded here for completeness

**Tokens seen is a derived figure, not a recorded one.** The training run did not
record `num_input_tokens_seen`; the value in the checkpoint is 0. Any tokens-seen
number for this model is computed from the corpus size and the epoch count, and
this page labels it as derived wherever it appears.

**The 14B and the 32B are not a matched pair.** Both ran a similar number of
optimizer steps, which is the axis that does not matter. They differ by a factor
of 8 in tokens seen and by a factor of 8 in training context length. This falls
directly out of the two runs' recorded floating-point-operation counts, which
differ by 3.5 times in the direction opposite to the parameter counts. Neither
model's evidence should be read as calibrating the other.
