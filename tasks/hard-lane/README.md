# The hard lane

A curated set of hard coding tasks with a re-checkable contamination gate. A
verified-inference lift only means something on tasks a model could not have
memorized, so every task is stamped with its source, license, and public date, and
scored only when the contamination gate says it is safe for a given model.

## How it works

Each task is a `LaneTask` (see `harness/hard_lane.py`): `source`, `license`,
`public_date`, plus an `oracle_cmd` (the visible tests) and a `held_out_cmd` (a
check the model never sees). Acceptance uses the held-out oracle tier
(`harness/consensus.py: accept_gate`): a solution must pass the visible tests AND
the held-out check AND not tamper with either (`harness/integrity.py`).

- `freshness(public_date, model_cutoff)` returns FRESH / CONTAMINATED / UNKNOWN.
- `admit(tasks, cutoff)` partitions a lane and flags any unlicensed task.

Both are re-derivable from the stamped dates, so a scored run's contamination
profile is itself re-checkable.

## This seed

`seed.jsonl` is self-authored (never public before this repo), so it is
contamination-free by construction and licensed under the repo license: the
strongest contamination defense, since a task that was never public cannot be
scraped into any future pretraining run. `merge-intervals/` is fully runnable
(visible + held-out suites); a gamed solution that only handles the visible cases
fails the held-out edge cases and is rejected.

## Growing to ~100 tasks

Add tasks from vetted, permissively-licensed public sources with a known
contamination profile, each stamped with its real public date so `admit` can gate
it: Terminal-Bench (Apache-2.0 harness), LiveCodeBench (contest-dated, contamination-
resistant), SWE-bench-Live (monthly-dated PRs), BigCodeBench (Apache-2.0). Verify
each source's license and per-task date before admission; prefer already-hardened
oracle variants, and keep minting private tasks so a never-public core slice always
exists.
