"""lean_env.py -- the environment a Lean process starts with: an allowlist.

A Lean candidate runs its own code while Lean elaborates it, and
`#eval IO.getEnv "NAME"` returns any variable the process holds. Lean prints
the value, and the receipt keeps that output as `kernel_output`. On Lean
4.34.0 (2026-09-23) a synthetic variable set in the harness reached the
kernel_output of a passing receipt this way, and a candidate that failed only
in the replay's `.olean` compile put it in a refusal. The gateway's /api/lean
route stores both. So no Lean spawn inherits `os.environ`. Every one starts
from the oracle's allowlist (`oracle.ENV_ALLOWLIST`, the one the pytest and
exec oracles use), plus the variables the toolchain reads:

- ELAN_HOME and ELAN_TOOLCHAIN pick the installation the elan proxy starts.
  HOME and USERPROFILE, already on the oracle's list, locate the default
  elan home.
- LEAN_PATH is the import search path. The kernel run and the `.olean`
  compile read it as inherited, and the leanchecker replay extends it
  (lean_replay.search_path).
- LEAN_SYSROOT names the installation root in place of the one lean infers
  from its own path.
- LEAN_NUM_THREADS and LEAN_STACK_SIZE_KB are runtime settings an operator
  can set for a large proof.

Proxy variables stay out, because a proxy URL can carry a password. elan
therefore cannot download a missing toolchain from inside a check; install
the toolchain first.

The allowlist empties the Lean process's own environment and does nothing
else. The candidate runs as this user, so it can still:

- read the environment of the process that started Lean. That is the
  harness process, and it holds every variable the allowlist removed. On
  Windows a program the candidate started read it out of the harness
  process's memory through psutil, and the synthetic value reached the
  kernel_output of a passing receipt (Lean 4.34.0, 2026-09-23). On Linux,
  /proc/<pid>/environ holds the environment a process started with, and a
  same-user child read the value there (WSL, no Lean run).
- read any file this user can read (`IO.FS.readFile`);
- print an allowlisted value, such as the profile path in USERPROFILE or
  HOME;
- send what it read over the network.

Closing the first route takes Lean running as another OS identity or in a
sandbox that cannot read this user's processes, or a harness process whose
environment holds no secret. The hygiene screen (benchmark_hygiene.py)
refuses admitted holes and kernel-bypass constructs. It does not refuse
`#eval` or `IO`, which sound proofs and metaprograms use.
"""
from __future__ import annotations

import os

from .oracle import ENV_ALLOWLIST

#: What the Lean toolchain reads, on top of the oracle's allowlist.
TOOLCHAIN_KEYS = frozenset({
    "ELAN_HOME", "ELAN_TOOLCHAIN", "LEAN_PATH", "LEAN_SYSROOT",
    "LEAN_NUM_THREADS", "LEAN_STACK_SIZE_KB",
})
#: Every variable a Lean spawn may carry.
LEAN_ENV_ALLOWLIST = ENV_ALLOWLIST | TOOLCHAIN_KEYS


def lean_env(extra: "dict | None" = None) -> dict:
    """The allowlisted subset of this process's environment for a Lean
    spawn. `extra` sets values explicitly, such as the replay's LEAN_PATH."""
    env = {k: v for k, v in os.environ.items() if k in LEAN_ENV_ALLOWLIST}
    if extra:
        env.update(extra)
    return env
