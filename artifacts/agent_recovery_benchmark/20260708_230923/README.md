# Run 20260708_230923: moved output

This run was started with a relative output root. The spin step then changed
the working directory into `spin/`, and every later write through the relative
root landed under a copy of the run root inside `spin/`. Commit 4d7767b9e
tracked 38 files at those nested paths. The longest was 206 characters, so a
Windows clone without core.longpaths failed whenever the clone directory was
longer than 51 characters.

On 2026-09-23 the nested files were moved to the paths the run meant to write.
No file's bytes changed, and `git log --follow` on a moved file shows where it
came from.

## What moved

- 30 files from
  `spin/artifacts/agent_recovery_benchmark/20260708_230923/artifacts/agent_recovery_benchmark/20260708_230923/`
  to this directory: `externalization/`, `loop/`, `forum_benchmark_cases.json`,
  the two `m7_*.json` files, `report.json` and `report.md`.
- The four `_oracle_junit.xml` files from
  `spin/artifacts/agent_recovery_benchmark/20260708_230923/spin/fw_*/` to
  `spin/fw_*/`.

## What was removed

Four nested `solution.py` files had a file already tracked at their intended
path, so they were deleted instead of moved.

- `fw_pass_a` and `fw_pass_b`: byte-identical to the `spin/fw_pass_*/solution.py`
  kept here (git blob 4693ad3c, the `CORRECT` constant in
  `scripts/run_flywheel_integration_benchmark.py`).
- `fw_fail_a` and `fw_fail_b`: the failing candidate the spin oracle wrote (git
  blob 0359e1bd, the `INCORRECT` constant). The same bytes are tracked at
  `spin/fw_fail_a/solution.py` in run 20260708_231022 and the four runs after
  it. The `spin/fw_fail_*/solution.py` files here are the seed files the run
  wrote before it changed directory, so they hold the `CORRECT` constant, not
  the candidate the oracle checked.

## Reading the results

- The four spin `_oracle_junit.xml` files report `tests="0"`. Pytest ran in the
  nested directory, which held no tests, so `report.json` records a spin
  `pass_rate` of 0.0. Run 20260708_231022 used an absolute root one minute
  later and recorded 0.5 on the same four tasks.
- The paths that `report.json` and `report.md` name, such as
  `artifacts\agent_recovery_benchmark\20260708_230923\forum_benchmark_cases.json`,
  now resolve from the repository root.
- The pytest `rootdir` line inside `loop/cache/*.json` and `loop/env/*.json`
  still names the nested directory, because that is where the check ran.
