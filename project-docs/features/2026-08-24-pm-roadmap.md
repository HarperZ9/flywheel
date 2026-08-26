# The PM roadmap: one page a manager can read

Date: 2026-08-24 (journey stages added 2026-08-25)

## What shipped

`harness/pm_roadmap.py` + `GET /api/pm/roadmap`
(schema `flywheel.pm-roadmap/v1`). The charter's manager use case --
goals, decomposed tasks, per-task verification status -- is served
from what the platform already seals:

1. Goals are swarm goals. Each sealed swarm receipt becomes one row
   with its state, verified-children count ("2 of 2"), and quorum
   verdict; running and detached swarms appear as open rows rather
   than disappearing.
2. Journeys are pipeline rows. The route reads verified projections
   from the journey store (hash-checked chains only; an unreadable
   store degrades to zero rows, never to unverified rows). A row
   carries its stage as its state, its goal as its title, and its
   check counts as verification; PASS verdicts already required
   receipt MATCH upstream, so the page re-grades nothing.
3. The verification floor sits under the goals: bound skill gates,
   sealed/open goal counts, journeys tracked.
4. The page carries its own limits: a satisfied quorum does not prove
   the goal was achieved, open rows are known-running work not
   estimates, and journey verdicts are witnessed upstream. A roadmap
   that hides what it does not know is a fiction with formatting.
5. The desktop Roadmap destination renders the same document: verdict
   dots and pills, goal-titled journey rows with stage text, floor
   tiles, limits.

## Verification

```text
python -m pytest tests/test_pm_roadmap.py -q                 # 7/7
python -m pytest tests/ -q                                   # exit 0
flutter analyze && flutter test                              # clean, all pass
python scripts/check_file_gate.py                            # clean
python scripts/check_verifier_stdlib.py                      # clean
python scripts/check_claim_language.py                       # clean
```

## Does not prove

The page reads sealed evidence only; it grades nothing and predicts
nothing. Journey ingestion trusts the store's own hash-chain checks at
read time; a corrupted store yields zero rows plus an honest empty
page, never partially trusted rows. Exported-journey artifacts beyond
the store are not rendered yet either.
