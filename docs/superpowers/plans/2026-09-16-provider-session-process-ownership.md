# Provider session process ownership helper

Status: implementation plan. This plan does not claim provider runtime readiness.

## Problem

Codex and Claude native-session transports need a persistent stdio process, not
the existing one-shot process helper that writes input and closes stdin. The
process still has to be owned as a Windows process tree before any provider code
runs, so closing the session cannot strand a native CLI parent or grandchild.

## Design

Add `harness/provider_session_process.py` as a narrow Windows-only launcher.
It will accept explicit `argv`, `cwd`, and `env`, never use a shell, create the
child suspended with `CREATE_NO_WINDOW`, assign it to the existing
kill-on-close Job Object primitive from `cross_harness_process.py`, start a
bounded stderr drain that stores no raw stderr, then resume the process. The
returned object exposes binary `stdin` and `stdout` for the existing transport.

The helper will not call `cross_harness_process.OwnedProcess._start_io()`
because that path closes stdin after a fixed payload. It will reuse only the
existing containment primitives: `_windows_job`, `_resume_windows`, and
`_terminate_unowned`, keeping the process suspended until the job assignment is
complete.

`close()` will be idempotent, close the process tree through the Job Object,
bound the wait and stderr-reader joins, and return a content-free cleanup
record with return code, whether the tree exited, whether the stderr drain
completed, observed stderr byte count, and truncation. Launch and cleanup errors
will return or raise sanitized control facts, not provider output or raw OS
messages.

Non-Windows platforms fail closed before spawning because this slice has no
equivalent robust tree containment there.

## Tests

1. Unit tests first with fakes: platform fail-closed before `Popen`; `Popen`
   receives explicit argv/cwd/env with no shell and hidden+suspended flags;
   job assignment happens before resume; resume failure terminates the
   unowned/suspended process with a sanitized exception.
2. Windows synthetic acceptance: launch a Python child with persistent binary
   stdin/stdout, send two messages over the same stdin, and read two stdout
   replies without stdin being closed by the helper.
3. Windows synthetic acceptance: child writes enough stderr to require draining,
   then emits stdout; cleanup reports bounded stderr observations without raw
   stderr bytes.
4. Windows synthetic acceptance: child spawns a grandchild and waits; closing
   the helper kills the owned tree within a bounded wait.

No provider CLI, auth, root Codex configuration, profile, registry, or launcher
admission logic is exercised here.
