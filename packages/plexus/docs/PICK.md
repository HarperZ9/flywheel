# Pick a tool for a request, or abstain

`plexus pick` reads a plain-language request and returns a probability for each tool in the mesh, scored against what each tool's manifest says it emits and consumes. When the best tool scores zero or its probability falls under a threshold, it abstains and hands the request to a person or a larger model. `plexus route` still answers the wiring question, how one tool's output reaches another.

## Bar, set before the run

This bar was committed before the picker was written and before its author saw the labelled set.

**Labels.** 100 requests, each with one gold tool (`tests/fixtures/plexus_pick_labels.json`), written by a separate labeller who saw tool names, their capability titles and a one-line purpose. The local routing-accuracy records hold 2 records, too few to use.

**Split.** Items are split in half by a seeded hash of their id. The threshold is chosen on the dev half only: the lowest threshold whose dev abstain rate is at least 10%. All bar numbers come from the test half.

**Baseline.** The picker is new to plexus, so the baseline always picks the majority tool on the dev half.

- **P1, accuracy.** Top-1 accuracy is at least the baseline's plus 0.20.
- **P2, abstain rate.** Under 15% of test items abstain.
- **P3, abstain carries error.** The top-1 error rate on abstained items is at least twice the error rate on decided items.
- **Control.** With the gold labels shuffled, P3 must fail.
- **Ship rule.** The picker ships as a new command whatever the result, with the numbers below.

## Try it

```bash
plexus pick "verify a sealed wiki pinned to a commit"
plexus pick --threshold 0.5 "check this memory still matches its source"
python -m plexus.pick_bench tests/fixtures/plexus_pick_labels.json
```

Each tool is scored with BM25 against a document built from its manifest: its name, the title and summary of each capability, and the words of each capability id. A softmax turns the scores into probabilities. The default threshold, 0.23, is the calibrated value from the run below. A threshold of 0.0 abstains only when no tool shares a word with the request.

## Results

Run on 2026-10-03, seed 20261003. Dev half 49 items, test half 51. The calibration rule picked a threshold of 0.23.

| Test half, 51 items | Value |
|---|---|
| Top-1 accuracy | 0.57 (29 of 51), Wilson 0.43 to 0.70 |
| Baseline, dev majority tool (learn) | 0.02 |
| Abstain rate | 0.10 (5 of 51) |
| Error rate when picked | 0.37 |
| Error rate when abstained | 1.00 |
| Error ratio | 2.7 |
| Shuffled-label control ratio | 1.15 |

- **P1 passes.** 0.57 against 0.02. The baseline is weak because the dev majority tool appeared once in the test half; uniform guessing over 10 tools would score about 0.10, and the picker clears that too.
- **P2 passes.** 10% of requests abstain.
- **P3 passes.** Abstained requests err at 1.00 against 0.37 for picked ones.
- **The control fails P3 as required.** Shuffled labels give 1.15.

## Limits

The labels come from one labeller, a Claude subagent that saw tool names, capability titles and a one-line purpose written for the task. 51 test items give wide intervals, and 4 in 10 picks are still wrong. Treat a pick as a suggestion to confirm. A tool whose manifest has sparse titles will rarely be picked.
