# Readback cases

Each JSON file here is one text that a person read and judged. `tests/test_structure_readback.py` runs the checker on every case and reports, for each rule the reader named, how many of the marked spans a finding touches.

## The shape of a case

```json
{
  "id": "specimen-a",
  "read_on": "2026-11-15",
  "profile": "chat",
  "verdict": "objected",
  "source": "Where the text came from and what was changed in it.",
  "text": "The text, or use text_file with a path relative to this folder.",
  "marks": [
    {
      "starts": "His last sentence is the useful part.",
      "ends": "the useful part.",
      "rule": "setup and payoff",
      "reader_said": "The reader's own words about this span."
    }
  ]
}
```

A mark runs from the first place its `starts` words occur to the end of the first `ends` words at or after them. `rule` is the reader's name for the fault, and it must be a key of `RULES` in the test file. `verdict` is `objected` for a text with marks and `accepted` for a text the reader passed, which has an empty `marks` list.

## Add a case

1. Take the text as the reader saw it. Change names, figures and anything private, and keep every sentence shape. Say what you changed in `source`.
2. Write one mark for each span the reader objected to, with the reader's words in `reader_said`. Record a span the reader objected to even when no rule can catch it. A miss that stays in the set is the point of the set.
3. If the reader named a rule that `RULES` lacks, add it there. Map it to the finding categories that answer it, or to an empty set when no detector exists yet.
4. Print the table, then copy the new counts into `recall.json`:

   ```bash
   python tests/test_structure_readback.py
   ```

5. Run `python -m pytest tests/test_structure_readback.py`. It fails when a rule that has a detector misses a marked span, and when an accepted text raises a gating finding. Fix the detector, or say in the pull request why the miss stands.

## What the table shows

`marks` counts the spans a reader objected to under one rule. `reported` counts the marks that a finding of that rule touches at HIGH or MEDIUM, and `gating` counts the ones touched at HIGH. The set is small and comes from one reader, so the table says where the rules stand against that reader and says little about other readers.
