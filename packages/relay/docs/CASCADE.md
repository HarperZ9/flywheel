# Local-first cascade

Some questions in an agent loop do not need a model. "Is this test failure flaky, or did the code break it?" can often be answered from the failure text alone. The cascade asks a local classifier first and sends the question to your model endpoint only when the classifier abstains. Every answer is written to the session ledger with who answered it, so you can see how many endpoint calls the cascade saved and check each local answer afterwards.

## Bar, set before the run

This bar was committed before the classifier was written and before its author read any labelled failure.

**Labels.** 160 failure tails from pytest, unittest, jest, go test, cargo and JUnit, each labelled flaky or real by a separate labeller who saw no code (`tests/fixtures/flaky_failure_labels.json`). About a quarter are marked hard on purpose. Items are split in half by a seeded hash of their id.

**Threshold.** Chosen on the dev half only: the lowest confidence threshold at which the classifier's accuracy on the items it decides is at least 0.95.

- **C1, endpoint calls.** The classifier decides at least 50% of test items, so the endpoint sees at most half the questions it would see without the cascade.
- **C2, local accuracy.** Accuracy on the test items the classifier decides is at least 0.95.
- **Control.** With the labels shuffled, C2 must fail.
- **Ship rule.** The cascade ships opt-in whatever the result, with the numbers below.

**What this does not measure.** The sprint plan named a paired run of 30 agent tasks with and without the cascade. That run needs a model endpoint for every task and was not done here. C1 and C2 bound the effect: escalated questions reach the endpoint exactly as before, so task success can only fall on questions the classifier decides, and only where it is less accurate than the endpoint would have been.

## Try it

```python
from relay.cascade import Cascade, FlakyClassifier
from relay.local_session import SessionLedger

ledger = SessionLedger()
cascade = Cascade(FlakyClassifier(), endpoint=ask_my_model, threshold=1.0, ledger=ledger)
answer = cascade.ask("is this test failure flaky?", failure_tail)
answer.decided_by      # "local" or "endpoint"
```

`python -m relay.cascade_bench tests/fixtures/flaky_failure_labels.json` reproduces the numbers below. The default threshold, 1.0, sends nearly every question to the endpoint, because the shipped classifier missed its bar. The cascade and its ledger records are the useful part today: plug in a local classifier you have measured and lower the threshold to what your own numbers support.

## Results

Run on 2026-10-03, seed 20261003. Dev half 79 items, test half 81. The calibration rule picked a threshold of 0.84.

| Test half, 81 items | Value |
|---|---|
| Decided locally | 19 (23%) |
| Accuracy when decided | 0.89 (17 of 19), Wilson 0.69 to 0.97 |
| Hard items decided | 2 of 26, both wrong |
| Shuffled-label control, accuracy when decided | 0.79 |
| Overall accuracy at p = 0.5, for reference | 0.72, against 0.59 for always answering "real" |

- **C1 fails.** The classifier decides 23% of questions, under the 50% bar.
- **C2 fails.** Accuracy on decided questions is 0.89, under 0.95.
- **The control fails C2**, as it must, but by a small margin: 0.79 against 0.89. The cues carry some signal and not much.

**Correction, recorded.** The first run had a defect: the cue `enotfound` matched inside the word `ModuleNotFoundError`, so import errors also counted as network failures. The fix adds word boundaries. Before the fix: 20 decided at 0.85, overall 0.70. After: 19 at 0.89, overall 0.72. Both runs miss both bars, and the threshold rule picked 0.84 both times.

## Limits

The failure tails were written by one labeller, a Claude subagent, from its knowledge of how CI failures look. Real logs are longer and noisier. A keyword classifier cannot read the cause behind a symptom: a timeout from a real infinite loop and a timeout from a slow runner look the same to it.
