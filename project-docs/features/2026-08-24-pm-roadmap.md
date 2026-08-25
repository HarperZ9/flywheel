# The PM roadmap: one page a manager can read

Date: 2026-08-24

## What shipped

`harness/pm_roadmap.py` + `GET /api/pm/roadmap`
(schema `flywheel.pm-roadmap/v1`). The charter's manager use case --
goals, decomposed tasks, per-task verification status -- is served
from what the platform already seals:

1. Goals are swarm goals. Each sealed swarm receipt becomes one row
   with its state, verified-children count ("2 of 2"), and quorum
   verdict; running and detached swarms appear as open rows rather
   than disappearing.
2. The verification floor sits under the goals: bound skill gates,
   sealed goal count, open goal count.
3. The page carries its own limits: a satisfied quorum does not prove
   the goal was achieved, and open rows are known-running work, not
   estimates. A roadmap that hides what it does not know is a fiction
   with formatting.

## Verification

```text
python -m pytest tests/test_pm_roadmap.py -q                 # 4/4
python -m pytest tests/ -q                                   # exit 0
python scripts/check_file_gate.py                            # clean
python scripts/check_verifier_stdlib.py                      # clean
python scripts/check_claim_language.py                       # clean
```

## Does not prove

V1 reads swarm receipts and skill gates only; journey-stage pipelines
are not on the page yet, and no desktop destination renders it yet --
the route and its markdown one-pager are the contract of record.
