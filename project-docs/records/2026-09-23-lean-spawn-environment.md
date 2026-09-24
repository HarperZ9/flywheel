# Lean spawn environment (2026-09-23)

Status: the Lean spawns are fixed on branch `fix/lean-spawn-env`. The
follow-ups at the end are open.

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
nowhere in any of the three receipts.

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
  every verdict where Lean ran.

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

| Spawn | Environment before | Candidate output in a stored receipt | Action |
| --- | --- | --- | --- |
| `oracle.py` PytestOracle | `run_env()` allowlist | yes, `stdout_excerpt` | none needed |
| `exec_oracle.py`, `escalation.py`, `witness.py`, `suite_audit.py`, `task_curator.py`, `tasks_lib.py` | `run_env()` allowlist | not checked one by one; the allowlist already applies | none needed |
| `sandboxed_runner.py` (agent shell through the sandbox) | `CredentialBindings.child_environment`, a tighter list | output is redacted of bound values | none needed |
| `selector_probe._signature` | whole environment | no: the selection receipt stores hashes, indices and confidence only | fixed here: `run_env({"PYTHONHASHSEED": "0"})` |
| `externalization_ablation._run_pytest` | whole environment | no: only the exit code is kept | follow-up 3 |
| `verified_bench.subprocess_gate` | whole environment plus `PYTHONPATH` | no: output enters only the sha256 `gate_ref` | follow-up 2 |
| `local_tools._t_run` with no runner | whole environment, `shell=True` | not a receipt; output returns to the agent | follow-up 4 |

`selector_probe` was changed because the fix is one call and the contract is
the one the pytest oracle already applies to the same kind of code.
`tests/test_selector_probe_env.py` shows a candidate returning
`os.environ.get("FLYWHEEL_PROBE_SECRET")` got `'probe-value-123'` on
origin/main and gets `None` now.

## What the allowlist leaves open

- A Lean candidate can read any file the harness user can read
  (`IO.FS.readFile`) and print it into `kernel_output`.
- It can print an allowlisted value. `USERPROFILE` and `HOME` hold the
  profile path, which names the user account.
- `benchmark_hygiene.screen_statements` refuses `sorry`, `sorryAx`, `admit`,
  `axiom`, `native_decide`, `debug.skipKernelTC` and `implemented_by`. It
  does not refuse `#eval` or `IO`. Sound proofs and metaprograms use both, so
  a text screen for them would refuse good candidates and still miss a name
  built from parts.

Closing the file route takes a sandboxed build with no read access outside
the candidate's directory and the toolchain, which is the comparator rung
(`project-docs/records/2026-09-23-lean-oracle-task-binding.md`).

## Follow-ups

1. `flywheel.lean-check/v1` reads the exit code alone. Observed after this
   fix: `check_lean_source("theorem t : False := sorry")` gave `MATCH`, and
   its output held Lean's `declaration uses sorry` warning (exit 0). A grep
   of `harness/` and `scripts/` finds no caller besides the tests and a
   parity row in `harness/parity_rows.py` that names the module. Route it
   through `lean_check`, or read the sorry warning as refusal, before
   anything relies on its verdict.
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

## Unknowns

- On origin/main, the first run of the live tests hit the 60 s pytest
  timeout inside a kernel run of a two-line file. Reruns on the same code
  and on the fix took 1 to 7 s per live test. The cause is unknown; it came
  before any change here.
- Only Windows was run. The POSIX path of the custom `ELAN_HOME` test uses
  `os.symlink` and was not executed.
