# Misconception diagnosis

When you get an arithmetic practice question wrong, the tutor can say why. It walks a small tree of yes-or-no questions about your answer, one level at a time, and records each question and its answer. The result names a cause you can act on, such as "added the numerators and the denominators" or "no answer given", in place of a bare "wrong".

The diagnosis reads only your prompt and your answer. It never shows a worked solution.

## The tree

The top level splits a wrong answer by cause.

- **missing**: the skill was not applied at all.
  - `missing.no_attempt`: blank, "?", "I don't know" or similar.
  - `missing.unexplained`: a number no rule below explains.
- **misrecruited**: a real procedure, applied where it does not belong.
  - `misrecruited.wrong_operation`: the answer is what another operation gives on the same numbers, such as adding when the question multiplies.
  - `misrecruited.smaller_from_larger`: in subtraction, each column takes the smaller digit from the larger one, whichever is on top.
  - `misrecruited.no_carry`: in addition, each column keeps its last digit and drops the carry.
  - `misrecruited.fraction_add_across`: for a/b + c/d, the answer is (a+c)/(b+d).
- **slip**: the right procedure with a small execution error.
  - `slip.one_digit`: the answer has the right number of digits and differs from the correct answer in exactly one digit, or swaps two adjacent digits.

Questions are asked in this order: no attempt, fraction add-across, smaller-from-larger, no carry, wrong operation, one-digit slip, then unexplained.

## Bar, set before the run

This bar was committed before the diagnoser was written and before its author saw any labelled answer.

**Labels.** 70 recorded wrong answers to whole-number and fraction questions, each with a teacher label from the tree above, written by a separate labeller who saw only this tree. The first 20 by id are a dev set for debugging; the bar is scored on the other 50.

- **D1, leaf agreement.** The diagnosis matches the teacher's leaf label on at least 80% of the 50 test answers.
- **D2, top-level agreement.** The top level (missing, misrecruited, slip) matches on at least 85%.
- **Control.** With each student answer moved to a different question (a seeded derangement), leaf agreement must fall below 50%. If it does not, the diagnoser is reading something other than the answer.
- **Ship rule.** The diagnosis ships whatever the result, with the numbers below.

## Try it

```bash
node src/cli.mjs tutor record mysession --objective addition --prompt "47 + 38" --answer "75" --correct false
node src/cli.mjs tutor misconceptions mysession
#   addition (1x):
#     causes: misrecruited.no_carry 1
node scripts/diagnosis-bench.mjs tests/fixtures/learn_diagnosis_labels.json
```

The MCP tool `learn_tutor_misconceptions` returns the same counts in a `diagnoses` field. Prompts the tree does not cover, such as calculus or prose questions, get no diagnosis and keep the plain count and notes.

## Results

Run on 2026-10-03. 70 labelled answers, 10 per leaf, 6 marked ambiguous by the labeller.

| | Leaf agreement | Top-level agreement |
|---|---|---|
| Test, 50 answers | 0.96 (48 of 50) | 0.96 |
| Dev, 20 answers | 0.95 | 0.95 |
| Control, answers moved to other questions | 0.16 | |

- **D1 passes** at 0.96 against 0.80. **D2 passes** at 0.96 against 0.85.
- **The control falls to 0.16**, under the 0.50 bound, so the diagnosis reads the answer.

The two test misses show where the tree is blunt. For 1203 + 2589 the teacher called 3782 a slip; it is also exactly what dropping the carry gives, and the tree asks about carries first. For 2/5 + 1/2 the teacher called 3/10 unexplained; it is one digit from 9/10, so the tree calls it a slip. The dev miss is the same kind: for 1/4 + 1/4 the answer 1/4 is 2/8 reduced, which the teacher read as add-across; the tree matches add-across only when the fraction is written unreduced, so it called a one-digit slip.

## Limits

The labels come from one labeller, a Claude subagent that saw only this tree, and it wrote the answers as well as the labels. Real students make errors outside the tree, and those land in `missing.unexplained`. The tree covers whole-number addition, subtraction and multiplication and fraction addition only.
