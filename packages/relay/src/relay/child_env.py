"""child_env.py -- the environment relay hands the programs it starts.

Shell children and the CLI tiers get an allowlist, built by the vendored
safe_spawn: the platform base (PATH with absolute entries only, the system
folders, the user's profile folders), plus names the launch adds. Nothing else
passes, so a provider key in the server's environment never reaches a shell a
model drives or a CLI tier.

- Shell children (``run``, ``test_cmd``, ``check``, bisect checks) also keep a
  fixed set of toolchain variables that locate interpreters and caches and hold
  no secret. Their PATH also drops every entry that reaches the folder they run
  in, so a program planted in a run's root is never found by bare name. A bisect
  check runs in a copy, so it guards the project it copied.
- ``git`` keeps every variable, since it needs the user's GPG, SSH and git
  settings, but its PATH is guarded the same way (``guarded_path_env``).
- ``RELAY_CHILD_ENV`` names more variables to pass, comma separated, for every
  child (a proxy, a key a test suite needs). It is read from the process
  environment that starts relay, never from an env file (LAUNCH_ONLY_KEYS).
- ``RELAY_ALLOW_EXEC_CLI`` names agent CLIs whose isolation profile is not
  proven (safe_spawn.PROFILES) that a launch with exec may still start.
"""
from __future__ import annotations

import os
from collections.abc import Mapping

from ._vendor import safe_spawn

CHILD_ENV = "RELAY_CHILD_ENV"
EXEC_CLI_ENV = "RELAY_ALLOW_EXEC_CLI"

TOOLCHAIN_ENV = (
    "HOME", "SHELL", "LANGUAGE", "PYTHONIOENCODING", "PYTHONUTF8",
    "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV", "JAVA_HOME", "GOPATH", "GOROOT",
    "GOCACHE", "GOMODCACHE", "CARGO_HOME", "RUSTUP_HOME", "NVM_DIR", "NVM_HOME",
    "NVM_SYMLINK", "DOTNET_ROOT", "GRADLE_USER_HOME", "MAVEN_HOME", "M2_HOME",
    "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR",
)


def _names(raw: str) -> tuple[str, ...]:
    return tuple(n for n in (p.strip() for p in (raw or "").split(",")) if n)


def named_extra(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """The variables RELAY_CHILD_ENV adds to every child's allowlist."""
    env = os.environ if env is None else env
    return _names(env.get(CHILD_ENV, ""))


def named_cli_grants(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Agent CLIs without a proven profile that the launch names, lowercased."""
    env = os.environ if env is None else env
    return tuple(n.lower() for n in _names(env.get(EXEC_CLI_ENV, "")))


def shell_env(env: Mapping[str, str] | None = None, cwd: str | None = None) -> dict:
    """The environment for a shell child: base, toolchain and named variables.

    `cwd` is the folder the child runs in. PATH entries that reach it, or the
    server's own folder, are left out.
    """
    return safe_spawn.child_env(allow=(*TOOLCHAIN_ENV, *named_extra(env)), environ=env,
                                cwd=cwd)


def guarded_path_env(cwd: str, env: Mapping[str, str] | None = None) -> dict:
    """Every variable, with PATH guarded as a shell child's is.

    For git, which needs what the allowlist leaves out: GNUPGHOME, SSH_AUTH_SOCK
    and its own GIT_ variables. git starts programs of its own by bare name, such
    as a clean filter or gpg for a signed commit, so its PATH still loses every
    entry that reaches `cwd` or the server's folder.
    """
    env = os.environ if env is None else env
    guarded = safe_spawn.child_env(environ=env, cwd=cwd)
    out = dict(env)
    for key in [k for k in out if k.upper() == "PATH"]:
        if key in guarded:  # POSIX reads only PATH itself; Windows any spelling
            out[key] = guarded[key]
    if os.name == "nt":
        out = {k: v for k, v in out.items() if k.lower() != safe_spawn.NO_CWD_SEARCH.lower()}
        out[safe_spawn.NO_CWD_SEARCH] = "1"
    return out


def profile_proven(profile: str | None) -> bool:
    prof = safe_spawn.PROFILES.get(profile or "")
    return prof is not None and prof.proven


def cli_allowed(profile: str | None, env: Mapping[str, str] | None = None) -> bool:
    """True when the launch may start this CLI at all (exec is checked elsewhere)."""
    return profile_proven(profile) or (profile or "").lower() in named_cli_grants(env)
