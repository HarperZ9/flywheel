# Recheck a claim in one command

Each public claim this repository makes about its own evidence has a manifest in
`recheck/`. A manifest says what the claim is, where it is published, the exact
command that rechecks it, the commit it is pinned to, the inputs and where to get
them, the verdict to expect, a control that must fail, and what you need to run
it. The runner does the rest:

```bash
git clone https://github.com/HarperZ9/flywheel && cd flywheel
python -m harness.recheck list
python -m harness.recheck run recheck/site-benchmark-seal.json
python -m harness.recheck run --hardware cpu --ci     # every claim a laptop can check
```

Python 3.11 or newer and Git are the requirements for the `cpu` manifests that run
in CI, plus `pytest` for `site-benchmark-seal` (declared in its `needs.packages`;
the runner refuses to start without it rather than report a false DRIFT). The
runner installs nothing. Each run prints PASS or FAIL per claim and the seconds
from checkout to verdict.

## What the runner does

1. Checks out the pinned commit with canonical bytes: `core.autocrlf=false` and
   `core.longpaths=true`, so the files are the bytes Git stores on every platform
   (see `docs/CANONICAL-BYTES.md`). A commit already in your clone becomes a
   temporary worktree; otherwise it is fetched by its full SHA.
2. Downloads each input and refuses it unless its sha256 matches the manifest.
3. Runs the command and compares the exit code and output with `expect`.
4. Runs the false-success control: it changes one input the way the manifest
   says, reruns, and requires the result the control declares. A recheck whose
   control does not fail is reported as FAIL, because a check never shown to fail
   proves nothing.
5. Restores the changed file and removes the checkout.

## The manifest, `flywheel.recheck/v1`

| Field | Meaning |
|---|---|
| `id` | Short name; equals the file name. |
| `claim.text`, `claim.where`, `claim.read_on` | The claim as published, where it is published, and the date it was read. |
| `level` | `integrity` (bytes match a hash), `recomputation` (the number follows from the records), `re-execution` (the records follow from rerunning) or `replication`. |
| `repository`, `commit` | Full URL and full 40-character SHA of the code and records the command runs against. |
| `cwd` | `checkout` runs in the pinned checkout; `repo` runs in your clone, for a tool newer than the pinned commit. |
| `inputs` | Files outside the repository: `url`, `sha256`, `save_as`, and `unzip_to` for an archive. |
| `setup` | Commands to run before the check, such as installing a package. |
| `command` | The argument list. `{python}`, `{checkout}`, `{repo}` and `{inputs}` are filled in. |
| `expect` | `exit_code`, plus `stdout_contains` and `stdout_lacks` lists. |
| `control` | `description`, an optional `mutate` (`file`, `find`, `replace`, first match only) and its own `expect`. |
| `needs` | `hardware` (`cpu`, `cpu-16gb`, `gpu-8gb`, `gpu-24gb`, `cluster`), `os`, `python`, `packages` the interpreter must import, the hosts it contacts (`network`) and the expected compute `seconds`. |
| `access` | A0 public and anonymous, A1 free account, A2 granted on request, A3 private to the maker, A4 does not exist. |
| `expertise` | E0 runs a given command, E1 reads code and logs, E2 domain method, E3 specialist judgment. |
| `anchor` | Who controls the reference the check compares against: `self`, `third-party` or `plural`. |
| `covers`, `does_not_cover` | The part of the claim the recheck reaches, and the part it cannot. |
| `ci`, `ci_skip_reason` | Whether CI runs it. `false` needs a reason. |
| `known_result` | Optional: a measured result that differs from the claim, kept beside it. |

`harness/recheck_manifest.py` checks the shape; `tests/test_recheck.py` loads
every manifest and fails on any problem.

## The manifests

| Manifest | Claim | Level | Needs | CI |
|---|---|---|---|---|
| `pysyft-result-receipt` | The published score (40 of 50) is bound to the approved job and the rows | recomputation | cpu, 1 s | yes |
| `shapley-prereg-pins` | The item set and code that ran are the ones the preregistration pins | integrity | cpu, 1 s | yes |
| `shapley-placebo-recompute` | 0 of 80 false attributions follow from the recorded outputs | recomputation | cpu, 1 s | yes |
| `prereg-ledger` | The preregistration ledger is an unbroken signed log | recomputation | cpu, 1 s | yes |
| `site-benchmark-seal` | The site's offline benchmark record and its seal | re-execution | cpu, 12 s | yes |
| `metr-count-odds-packet` | The METR count_odds packet is intact and the import refuses a changed score | recomputation | cpu, 5 s | yes |
| `closeout-220-full-pytest` | Closeout receipt 220: proof-surface's suite passed at `03655af9` | re-execution | cpu, 10 s | no: known DRIFT, see `known_result` |

CI (`.github/workflows/recheck.yml`) runs every `cpu` manifest with `ci: true` on
Linux and on Windows with `core.autocrlf=true`.

## Claims with no runnable manifest yet

| Claim | Why not |
|---|---|
| The PySyft approved hash equals syft-job's own `submission_hash` on a live run | Needs Linux or WSL, PySyft at `36e6516`, uv and four local packages. |
| Shapley placebo re-execution on qwen2.5:7b | Needs a GPU, Ollama 0.35.1 and the 4.7 GB model `845dbda0`; about 127 s on one RTX 4090. |
| Release v1.3.4 wheel equals a rebuild from the tag | The build is not byte-reproducible yet, so the honest result today is DRIFT at the byte level. |

## Time to a verdict

Target: under 10 minutes for a stranger on a clean machine, from reading the
claim to a recorded verdict, for every `cpu` manifest.

Measured 2026-10-04 by the maker's agent on one Windows 11 workstation (Python
3.12.10, Git default `core.autocrlf=true`), each from a fresh clone in an empty
directory to the printed verdict, machine time only:

| Manifest | Clone | Recheck | Total |
|---|---|---|---|
| `site-benchmark-seal` | 10.0 s | 27.9 s | 37.9 s |
| `metr-count-odds-packet` | 6.7 s | 13.4 s | 20.1 s |
| `shapley-prereg-pins` | 7.3 s | 10.9 s | 18.2 s |

Reading time is not in these numbers, and the measurer knew the repository. A
measurement by someone outside it is the one that counts.

## What this does not prove

- That the claims are true beyond the level checked. A recomputation MATCH says
  the numbers follow from the records, not that the records describe the world.
- Who signed anything. Every manifest here has anchor `self`: the hashes and
  keys it checks against are published by the same author as the claim.
- Anything about claims without a manifest.
