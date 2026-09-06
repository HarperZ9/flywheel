"""parity_rows_coverage.py -- the rows the coverage reading said were owed.

`parity_coverage` read the peers' own page indexes on 2026-09-06 and named
capability areas the matrix did not score. Nine of them were marked as rows
owed. These are those rows.

Four of the nine audit ABSENT, and that is the point of writing them down.
Before this file the matrix reported no gaps, which was true of the rows it
held and said nothing about the rows it did not. A row that names the module
it would need, and fails until that module exists, turns a backlog item into
a number a reader can watch move. The witnesses on those four name what would
carry the capability, so the audit reports ABSENT today and reports WITNESSED
on the day the work lands, with no edit to this file.

They live apart from `parity_rows` because that file was at the length gate
and a table designed to grow by one row per shipped capability will keep
reaching it. `parity_rows` merges them, so nothing that reads ROWS has to
know there are two.
"""
from __future__ import annotations

ROWS = [
    {"key": "scheduled-runs",
     "desc": "run a prompt or a workflow on a schedule, or on a repeating "
             "trigger, without a person starting it",
     "witnesses": [("module", "harness/scheduler.py"),
                   ("route", "/api/schedule"),
                   ("test", "tests/test_schedule_route.py")]},
    {"key": "lifecycle-hooks",
     "desc": "operator scripts and tools that fire at named points in a run, "
             "each firing carried on the run's own receipt",
     "witnesses": [("module", "harness/accountable_hooks.py"),
                   ("route", "/api/hooks"),
                   ("test", "tests/test_accountable_hooks.py")]},
    {"key": "subagent-teams",
     "desc": "delegate part of a run to child agents with their own roles and "
             "context, and rejoin their work into the parent record",
     "witnesses": [("module", "harness/subagents.py"),
                   ("route", "/api/subagents"),
                   ("test", "tests/test_subagents.py")]},
    {"key": "packaged-skills",
     "desc": "named capability packages loaded on demand, admitted through a "
             "gate rather than trusted because they are present",
     "witnesses": [("module", "harness/skill_gate.py"),
                   ("route", "/api/skills"),
                   ("test", "tests/test_skill_gate.py")]},
    {"key": "self-hosted-runner-pool",
     "desc": "a pool of machines the operator owns that accept dispatched "
             "runs, with the pool's membership under the operator's control",
     "witnesses": [("module", "harness/runner_pool.py"),
                   ("route", "/api/runners")]},
    {"key": "usage-and-cost-accounting",
     "desc": "what a run spent, per action, on a receipt that can be "
             "re-checked rather than a dashboard that has to be believed",
     "witnesses": [("module", "harness/usage_receipt.py"),
                   ("route", "/api/usage/verify"),
                   ("test", "tests/test_usage_receipt.py")]},
    {"key": "browser-and-computer-control",
     "desc": "drive a browser or a desktop as a tool inside a run, with each "
             "action admitted and recorded",
     "witnesses": [("module", "harness/browser_control.py"),
                   ("route", "/api/browser")]},
    {"key": "own-code-vulnerability-scan",
     "desc": "scan the operator's own codebase for security defects and turn "
             "the findings into reviewable changes",
     "witnesses": [("module", "harness/vulnerability_scan.py"),
                   ("route", "/api/scan/vulnerabilities"),
                   ("test", "tests/test_scan_route.py")]},
    {"key": "generated-visual-artifacts",
     "desc": "produce images, posters, typefaces and other visual output from "
             "a run, addressed and carried like any other result",
     "witnesses": [("module", "harness/design_studio.py"),
                   ("route", "/api/studio/poster"),
                   ("test", "tests/test_design_studio.py")]},
]
