"""lean_env.py -- the environment a Lean child process starts with: an allow-list.

A Lean candidate runs its own code while Lean elaborates it, and
`#eval IO.getEnv "NAME"` returns any variable the process holds. Lean prints
the value, and a receipt keeps that output as `kernel_output`. A child that
inherited the harness's whole environment could therefore print a provider
key or a gateway setting into a record. So no Lean spawn inherits
`os.environ`: every one starts from `lean_env()`, which keeps only the names
below.

  to start at all     PATH, and on Windows SYSTEMROOT, SYSTEMDRIVE, WINDIR,
                      COMSPEC, PATHEXT, PROCESSOR_ARCHITECTURE,
                      NUMBER_OF_PROCESSORS
  home and temp       HOME, USERPROFILE, APPDATA, LOCALAPPDATA (elan finds
                      its default home there), TMPDIR, TEMP, TMP, USER
  locale and time     LANG, LC_ALL, LC_CTYPE, TZ
  the toolchain       ELAN_HOME and ELAN_TOOLCHAIN (which installation the
                      elan proxy starts), LEAN_PATH (the import search path),
                      LEAN_SYSROOT, LEAN_NUM_THREADS, LEAN_STACK_SIZE_KB

Proxy variables stay out: a proxy URL can carry a password.

What this leaves open. The allow-list empties the Lean process's own
environment. Candidate code can still print an allow-listed value, such as
the profile path, and code that can read other processes of the same user
can read the harness's environment from there. Closing that takes running
Lean as another operating system identity.
"""
from __future__ import annotations

import os

ALLOWED = frozenset({
    "PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT",
    "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS",
    "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TMPDIR", "TEMP", "TMP", "USER",
    "LANG", "LC_ALL", "LC_CTYPE", "TZ",
    "ELAN_HOME", "ELAN_TOOLCHAIN", "LEAN_PATH", "LEAN_SYSROOT",
    "LEAN_NUM_THREADS", "LEAN_STACK_SIZE_KB",
    # Set by safe_program for a Windows child so it skips the working folder.
    "NODEFAULTCURRENTDIRECTORYINEXEPATH",
})


def lean_env(base=None) -> dict:
    """The environment for a Lean child: `base` (default: this process's)
    with every name outside the allow-list removed. Names match without case,
    as Windows treats them."""
    source = os.environ if base is None else base
    return {name: value for name, value in source.items() if name.upper() in ALLOWED}
