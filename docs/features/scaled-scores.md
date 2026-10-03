# Scores between a baseline and a ceiling

A raw score is hard to read until you know two things: what a trivial method
scores on the same measurement, and the best a repeat of the measurement
reaches. Flywheel's findings document can report a score between those two
anchors:

    scaled = (score - baseline) / (ceiling - baseline)

0 means no better than the trivial baseline. 1 means as good as the ceiling.

Write an artifact to `<run_root>/scaled/<name>.json`:

```json
{
  "schema": "flywheel.scaled-score/v1",
  "key": "red-check",
  "claim": "Share of false claims the red check marks",
  "score": 0.64,
  "baseline": {"value": 0.458, "source": "path/to/baseline.json", "sha256": "..."},
  "ceiling":  {"value": 0.82,  "source": "path/to/ceiling.json",  "sha256": "..."}
}
```

Each anchor needs its value, its source and the source's SHA-256. If the score or
either anchor is missing, the finding reads "pending" and shows no number. A
ceiling at or below the baseline is refused.

Useful anchors:

- a trivial rule's score on the same cases, such as "the final patch touches a
  test file";
- human inter-rater agreement as the ceiling for a judge's agreement;
- the spread across same-seed reruns as the ceiling for a harness effect.

A badly chosen baseline makes a weak result look strong. The anchors' sources
and hashes sit in the finding so a reader can check them.
