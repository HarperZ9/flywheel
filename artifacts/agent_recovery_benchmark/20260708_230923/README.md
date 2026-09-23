# Run 20260708_230923: moved output

This run wrote most of its output under a copy of its own run root. Commit
4d7767b9e tracked 38 files at those nested paths. The longest was 206
characters, so a Windows clone without core.longpaths failed whenever the clone
directory was longer than 51 characters. On 2026-09-23 the nested files were
moved to the paths the run meant to write. Two of them were exact copies of a
file already tracked at that path and were deleted instead.

Below, `<root>` stands for `artifacts/agent_recovery_benchmark/20260708_230923`.

## How the nesting happened

What the tree shows:

- `report.json` records the run root as the relative path
  `artifacts\agent_recovery_benchmark\20260708_230923`. The five later runs
  record an absolute root.
- The pytest `rootdir` line in `loop/cache/*.json` shows where the loop step
  ran its check: `<root>/spin/<root>/<root>/loop/w`, under the root of the
  checkout the run used.
- The script as first committed, in 4d7767b9e, resolves `--out-root` to an
  absolute path and returns to the starting directory after the spin step.
  That version cannot write this tree. The version that produced this run was
  never committed.

What follows from those facts, inferred and not reproduced:

- `run_spin_benchmark` changed the working directory into `<root>/spin`, and
  the spin step then wrote its candidates and junit files through the relative
  root, under `<root>/spin/<root>/spin/fw_*`. That one change of directory
  accounts for 8 of the 38 files.
- The other 30 files (`externalization/`, `loop/`, the input JSON files and
  both reports) were written while the working directory was
  `<root>/spin/<root>`. What moved it there is unknown. A return to the
  relative root made from inside `<root>/spin` would land there and would
  account for all 38 paths, but no copy of that code survives to confirm it.

The fix in `scripts/run_flywheel_integration_benchmark.py` resolves the root
before the spin step changes directory.
`tests/test_flywheel_integration_benchmark.py` checks that no output path
repeats the root and that the working directory ends where it started.

## What moved

No file's bytes changed. Each moved file's old path is its current path with a
copy of the run root inserted:

- 30 files moved from `<root>/spin/<root>/<root>/` to `<root>/`:
  `externalization/`, `loop/`, `forum_benchmark_cases.json`, the two `m7_*.json`
  files, `report.json` and `report.md`.
- The four `_oracle_junit.xml` files moved from `<root>/spin/<root>/spin/fw_*/`
  to `<root>/spin/fw_*/`.
- The two failing candidates moved from
  `<root>/spin/<root>/spin/fw_fail_*/solution.py` to
  `<root>/spin/fw_fail_*/candidate_solution.py`. The next section says why they
  did not keep the name `solution.py`.

`git log --follow` on a single file can name the wrong source here. Each
`externalization/<domain>/self/solution.py` has the same bytes as its
`ext/solution.py` sibling, so `--follow` reports the nested `ext/solution.py`
as the source of the `self` file, for all five domains. A diff over the whole
change pairs every file with its true source:

```
c=$(git log --diff-filter=A --format=%H -- <root>/README.md)
git diff -M --name-status "$c^" HEAD -- <root>
```

## Four candidates that met a tracked file

Four nested `solution.py` files had a file already tracked at their intended
path, `<root>/spin/fw_*/solution.py`. That file is the seed the run wrote
before it changed directory. It holds the `CORRECT` constant from
`scripts/run_flywheel_integration_benchmark.py` (git blob 4693ad3c).

- `fw_pass_a` and `fw_pass_b`: the candidate was byte-identical to the seed,
  so the nested copy was deleted.
- `fw_fail_a` and `fw_fail_b`: the candidate is the `INCORRECT` constant (git
  blob 0359e1bd). It now sits next to the seed as `candidate_solution.py`. A
  run with an absolute root writes the candidate over the seed, so run
  20260708_231022 and the four runs after it track these bytes as
  `spin/fw_fail_*/solution.py`.

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
