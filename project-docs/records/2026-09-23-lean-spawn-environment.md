# Lean spawn environment (2026-09-23)

Status: on branch `fix/lean-spawn-env` every Lean spawn gets an allowlisted
environment. That closes the direct read (`IO.getEnv` in the Lean process).
It does not close the ancestor read: a candidate can still read the
harness's environment from the process that started Lean, and the value
still reaches a stored receipt (see "The ancestor read"). The follow-ups at
the end are open.

## The defect

Every Lean process that `harness/lean_oracle.py` and `harness/lean_replay.py`
started inherited the harness's whole environment. A candidate runs code
while Lean elaborates it, and `#eval IO.getEnv "NAME"` returns any variable
the process holds. Lean prints the value, the receipt keeps the output as
`kernel_output`, and the gateway route `/api/lean` stores the receipt. So a
candidate proof could copy an API key or a token from the harness
environment into a stored receipt.

The same inheritance held for `harness/infra/lean_adapter.py`
(`flywheel.lean-check/v1`), `harness/proof_run.py` (`--verify-lean`) and
`harness/lean_export.py` (the certificate export).

## Reproduction

Windows 11, Lean 4.34.0 through elan 4.2.3, origin/main at `02a33d2d`. The
variable was synthetic: `FLYWHEEL_PROBE_SECRET=probe-value-123`. No real
secret was read or printed.

Kernel run. The candidate:

```lean
#eval IO.getEnv "FLYWHEEL_PROBE_SECRET"
theorem probe_ok : 1 + 1 = 2 := rfl
```

gave `passed: True`, `validation_level: leanchecker_replay` and
`kernel_output: some "probe-value-123"`.

Replay compile. This candidate passes the kernel run and the audit. It fails
only in the replay's `.olean` compile, where `--root` makes the main module
`Candidate`:

```lean
import Lean
open Lean Elab Command
#eval show CommandElabM Unit from do
  if (← getMainModule) == `Candidate then
    let v ← IO.getEnv "FLYWHEEL_PROBE_SECRET"
    throwError m!"leak {v}"
theorem probe_ok : 1 + 1 = 2 := rfl
```

It gave `passed: False` with `kernel_output` ending in
`Candidate.lean:3:0: error: leak some (probe-value-123)`.

`flywheel.lean-check/v1`. `check_lean_source` over the first candidate gave
`MATCH` with `output_excerpt: some "probe-value-123"` in the sealed receipt.

After the fix the same three runs give `some` replaced by `none`: the kernel
run's `kernel_output` is `none`, the replay refusal ends in `error: leak
none`, and the adapter's `output_excerpt` is `none`. The probe value appears
nowhere in any of the three receipts. These candidates use the direct read
only; the ancestor read below still reaches a receipt.

The regression tests are in `tests/test_lean_spawn_env.py` and
`tests/test_selector_probe_env.py`. Run against origin/main in a throwaway
worktree, 10 of the 11 failed: the three spawn tests (each spawn got
`env=None`, the inherited environment), the three live probe tests, the
`does_not_prove` test, the allowlist test (no `harness.lean_env` module),
and both selector tests. The custom `ELAN_HOME` test passed there as well,
because the inherited environment carried `ELAN_HOME`; it guards that the
allowlist keeps it. All 11 pass with the fix.

## The fix

`harness/lean_env.py` holds the allowlist in one place. It is the oracle's
`ENV_ALLOWLIST` (`harness/oracle.py`, the list the pytest and exec oracles
already use) plus the variables the toolchain reads: `ELAN_HOME`,
`ELAN_TOOLCHAIN`, `LEAN_PATH`, `LEAN_SYSROOT`, `LEAN_NUM_THREADS` and
`LEAN_STACK_SIZE_KB`. The candidates came from the binaries: `strings` over
`libleanshared*.dll`, `libInit_shared.dll` and `elan.exe` of the 4.34.0
install lists the `LEAN_*` and `ELAN_*` names they contain. The list keeps
the ones a batch check needs. It leaves out `LEAN_SRC_PATH` and
`LEAN_WORKER_PATH` (language server), `LEAN_IMPORT_WORKERS`,
`LEAN_ABORT_ON_PANIC`, `LEAN_MAIN_USE_THREAD`, `LEAN_MANUAL_ROOT`,
`LEAN_NAT_MAX_SIZE`, `ELAN_NO_OVERRIDE_NOTICE` and `ELAN_USE_REQWEST`. Adding
one is a one-line change to `TOOLCHAIN_KEYS`. Proxy variables are left out on
purpose, because a proxy URL can carry a password.

- `lean_replay.run_killable` gives `lean_env()` to any spawn that passes no
  `env`. That covers the kernel run, the audit, the version and prefix
  queries and the `.olean` compile.
- leanchecker gets `lean_env()` with `LEAN_PATH` set to the library, the
  inherited entries, then the build directory. The inherited `LEAN_PATH`
  that commit `3f437b22` kept for the replay still reaches all three
  steps; `test_live_import_from_an_inherited_lean_path_passes` covers it.
- `infra/lean_adapter.py`, `proof_run.py` and `lean_export.py` pass
  `env=lean_env()` to `subprocess.run`.
- The math oracle's `does_not_prove` names what the allowlist leaves open on
  every verdict where Lean ran: the environment of the process that started
  Lean, readable files, allowlisted values and the network. The first commit
  said the candidate "could not read a harness variable off that list",
  which the ancestor read disproves; review caught it and the line was
  corrected. `test_the_result_names_what_the_allowlist_leaves_open` checks
  the line on PASS, FAIL and UNVERIFIABLE.

Custom `ELAN_HOME`, checked two ways. The committed live test builds an elan
home in a temporary directory: a `settings.toml` that pins the toolchain the
default home resolves to, and a link to the installed `toolchains`. The elan
proxy exports the `ELAN_HOME` it used to the `lean` it starts, and the
candidate's `#eval IO.getEnv "ELAN_HOME"` printed the custom path. A manual
check went further: a custom home pinned to `leanprover/lean4:v4.33.1`
while the default resolves to 4.34.0. `lean_check` then reported
`toolchain: Lean (version 4.33.1, ...)`, took leanchecker from the 4.33.1
install, and passed at `leanchecker_replay`. So `ELAN_HOME` reached every
spawn in the chain.

## Other spawns of candidate-controlled code

`subprocess` and `Popen` across `harness/`, read for spawns that run code a
model or a submitter wrote.

Every `run_env()` row that runs candidate code is open to the ancestor read
described below: the allowlist empties the child's own environment, and the
candidate can read the harness's from its parent. The last column says whether that value can
then reach a stored record.

| Spawn | Environment before | Candidate output in a stored receipt | Action |
| --- | --- | --- | --- |
| `oracle.py` PytestOracle | `run_env()` allowlist | yes, `stdout_excerpt` | follow-up 6: the ancestor read reaches it |
| `exec_oracle.py` | `run_env()` allowlist | `DenseResult.output_hash` holds the first 32 characters of the candidate's stdout; no module in `harness/` or `scripts/` imports `exec_oracle` | follow-up 6 |
| `escalation.py` | `run_env()` allowlist | `py_compile` output in `stdout_excerpt`. The candidate is compiled and never runs | none needed |
| `witness.py` | `run_env()` allowlist | no: the re-run output enters only the hash | none for receipts; the read itself stays open |
| `suite_audit.py`, `task_curator.py`, `tasks_lib.py` | `run_env()` allowlist | no: only the exit code is kept | none for receipts; the read itself stays open |
| `sandboxed_runner.py` (agent shell through the sandbox) | `CredentialBindings.child_environment`, a tighter list | output is redacted of bound values only | Windows: the low-integrity sandbox refused the ancestor read (observed). bwrap: its own pid namespace and `/proc` (inferred from the argv, not run). Seatbelt: the process table stays shared, and whether the profile allows reading another process's environment is unknown |
| `selector_probe._signature` | whole environment | no: the selection receipt stores hashes, indices and confidence only | fixed here for the direct read: `run_env({"PYTHONHASHSEED": "0"})` |
| `externalization_ablation._run_pytest` | whole environment | no: only the exit code is kept | follow-up 3 |
| `verified_bench.subprocess_gate` | whole environment plus `PYTHONPATH` | no: output enters only the sha256 `gate_ref` | follow-up 2 |
| `local_tools._t_run` with no runner | whole environment, `shell=True` | not a receipt; output returns to the agent | follow-up 4 |

`selector_probe` was changed because the fix is one call and the contract is
the one the pytest oracle already applies to the same kind of code.
`tests/test_selector_probe_env.py` shows a candidate returning
`os.environ.get("FLYWHEEL_PROBE_SECRET")` got `'probe-value-123'` on
origin/main and gets `None` now.

## The ancestor read

Found in review of the first commit on this branch, and re-run before the
texts were corrected. The allowlist empties the Lean process's own
environment. The candidate runs as the harness user, and that user can read
the environment of another of its processes, including the harness process
that started Lean.

Windows, Lean 4.34.0, the fix commit `abe60fbc`, synthetic
`FLYWHEEL_PROBE_SECRET=probe-value-123` set through `os.environ` in the
harness process. The candidate's `#eval` ran `IO.Process.output` on
`python -c` with a script that walks `psutil.Process().parents()` and prints
the probe key from each ancestor's `environ()`, followed by
`theorem probe_ok : 1 + 1 = 2 := rfl`. `lean_check` returned `passed: True`
at `leanchecker_replay` with `kernel_output` holding
`[('lean.exe', None), ('lean.exe', None), ('python.exe', 'probe-value-123'), ...]`.
The third ancestor is the Python process that called `lean_check`. On
`/api/lean` that is the gateway process, which calls `lean_check` in process
and stores the receipt.

The same script under the pytest oracle's spawn shape
(`spawn_killable(cmd, shell=True, env=run_env())`) printed `None` for a
direct read and `[('cmd.exe', None), ('python.exe', 'probe-value-123'), ...]`
for the ancestors.

Linux, WSL Ubuntu 24.04, Python 3.12.3, no Lean there. A child started with
only `PATH` and `HOME` printed `direct getenv: None` and read
`FLYWHEEL_PROBE_SECRET=probe-value-123` from `/proc/<ppid>/environ`. That
file holds the environment the process started with: the same check with the
variable set through `os.environ` after start found nothing. An exported
secret, or one a service manager sets, is there from the start. That a Lean
candidate reaches the same file with `IO.FS.readFile` is inferred, not run.

The Windows low-integrity sandbox in `sandboxed_runner.py` refused the same
read. Run through `sandboxed_run`, the script got `AccessDenied` on the
harness process and printed no value. The same script started bare with
`run_env()` printed the value. So Lean in that sandbox is one route to
closing the read on Windows, if its build directory can be made writable
there (follow-up 7).

`tests/test_lean_env_residual.py` pins the route: its live test starts a
harness process with the probe set from the start and asserts the value
still reaches the receipt. If Lean comes to run isolated, that test fails
and the texts that name the route get updated with it.

## What the allowlist leaves open

- A Lean candidate can read the environment of the process that started
  Lean, which holds every variable the allowlist removed, and print it into
  `kernel_output` (above).
- It can read any file the harness user can read (`IO.FS.readFile`) and
  print it into `kernel_output`.
- It can send what it read over the network.
- It can print an allowlisted value. `USERPROFILE` and `HOME` hold the
  profile path, which names the user account.
- `benchmark_hygiene.screen_statements` refuses `sorry`, `sorryAx`, `admit`,
  `axiom`, `native_decide`, `debug.skipKernelTC` and `implemented_by`. It
  does not refuse `#eval` or `IO`. Sound proofs and metaprograms use both, so
  a text screen for them would refuse good candidates and still miss a name
  built from parts.

Closing the ancestor route takes Lean running as another OS identity or in a
sandbox that cannot read this user's processes (a separate user, a
low-integrity or AppContainer token on Windows, a pid namespace with its own
`/proc` on Linux), or a harness process whose environment holds no secret.
Closing the file route takes a sandboxed build with no read access outside
the candidate's directory and the toolchain. Both are the comparator rung
(`project-docs/records/2026-09-23-lean-oracle-task-binding.md`). Until then,
the practical control is to serve `/api/lean` from a process that holds no
secret.

## Follow-ups

1. `flywheel.lean-check/v1` reads the exit code alone. Observed after this
   fix: `check_lean_source("theorem t : False := sorry")` gave `MATCH`, and
   its output held Lean's `declaration uses sorry` warning (exit 0). A grep
   of `harness/` and `scripts/` finds no caller besides the tests and a
   parity row in `harness/parity_rows.py` that names the module. Reading
   the sorry warning as refusal would not be enough:
   `check_lean_source("axiom bad : False\ntheorem t : False := bad\n")` also
   gave `MATCH`, with empty output (observed in review). Route it through
   `lean_check` before anything relies on its verdict.
2. `verified_bench.subprocess_gate` runs an operator's gate command over a
   model-written `PROPOSED.md` with the whole environment. The output is
   hashed, so it does not reach a receipt, but a gate that executes the
   proposal hands it every variable. An allowlist could break a gate command
   that needs other variables, so this needs a decision on how a gate
   declares what it needs.
3. `externalization_ablation._run_pytest` runs the fixed cheat and honest
   candidates in the module with the whole environment. Only the exit code is
   kept. `run_env()` is likely safe there and was left for a separate change.
4. `local_tools._t_run` runs `shell=True` with the whole environment when no
   runner is injected. The shipped entry points (`local_mcp.py`,
   `local_agent_cli.py`, `router_agent.py`, `gateway_agent_native_tools.py`)
   inject `make_sandboxed_runner`, so only a direct caller reaches the bare
   path.
5. With proxy variables left out, elan cannot download a toolchain from
   inside a check. A `lean-toolchain` file in the working directory that
   names an uninstalled toolchain now fails where it might have downloaded.
   Not observed; it follows from the allowlist.
6. The `run_env()` oracles are open to the ancestor read. A model-written
   pytest candidate can read the harness's environment from its parent and
   print it, and PytestOracle keeps the output as `stdout_excerpt`. The
   spawn shape was observed leaking the synthetic value (above); the full
   path through a stored oracle receipt is inferred, not run.
   `exec_oracle`'s `output_hash` carries 32 characters of candidate stdout,
   but nothing imports it. The fix is the one the Lean route needs, so it
   belongs with follow-up 7.
7. Isolate candidate execution from this user's processes. On Windows the
   low-integrity sandbox (`sandboxed_runner.py`) refused the ancestor read in
   one run; Lean would need its build directory and temp files writable
   there, and the toolchain readable. On Linux a pid namespace with its own
   `/proc` hides the harness. Neither has been tried with Lean.

## Unknowns

- On origin/main, the first run of the live tests hit the 60 s pytest
  timeout inside a kernel run of a two-line file. Reruns on the same code
  and on the fix took 1 to 7 s per live test. The cause is unknown; it came
  before any change here.
- Only Windows was run with Lean. The POSIX path of the custom `ELAN_HOME`
  test uses `os.symlink` and was not executed, and the `/proc` branch of the
  ancestor pin in `tests/test_lean_env_residual.py` has not run with Lean.
- `tests/test_lean_replay.py::test_live_smuggled_declaration_is_refused_by_the_replay`
  is slow and load sensitive. Its candidate imports `Lean`. In review it
  failed once at its `axiom_footprint` assertion and passed alone. On the
  fix's second round, with the machine at 78% CPU from other work, it
  passed alone in 14 to 18 s on this branch (n=3) and took 16, 19 and 127 s
  on origin/main (n=3). Four slice runs gave one pass, one 60 s pytest
  timeout in this test, one 60 s timeout whose test name was not captured,
  and one failure at the same assertion after 91 s with the per-test
  timeout raised to 300 s.
  The likely mechanism, inferred and not traced: the kernel run passed the
  90 s `_TIMEOUT` in `lean_oracle.py`, so the audit never ran and the
  footprint stayed empty. The test is untouched here, and origin/main shows
  the same slowness.
