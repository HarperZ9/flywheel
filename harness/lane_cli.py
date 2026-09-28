"""One launcher for the lane CLIs the native screens run.

The feeds, science bench, discourse and workspace map screens shell a lane's
CLI (gather, crucible, chorus, index). Where that CLI lives depends on the
install:

- a source or pip install runs the console script from PATH, else
  ``python -m <module>`` when the module imports;
- a frozen engine has no ``python`` and no console scripts, so it runs itself:
  ``<engine.exe> --bundled-lane-cli <lane> <args...>`` (frozen_lane_modes).
  The child admits the lane from its reviewed payload and allows only the
  listed subcommands, so a call the child would refuse is refused here first
  with ``not_in_build`` and nothing is spawned.

Every run starts in ``<home>/lanes/<lane>/`` (created), so a CLI that writes
relative to its working directory never writes into the install folder. A
Windows run hides its console window. The child is told to write UTF-8
(``PYTHONUTF8``, ``PYTHONIOENCODING``) and its output is decoded as UTF-8, so a
non-ASCII feed title survives a code-page pipe. The environment is the lane
environment (lane_env); a frozen self-child starts from the bundled child set
(bundled_lane_env) plus the lane's declared and granted names.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping

from .bundled_lane_env import UTF8_ENV, bundled_child_environment
from .frozen_lane_modes import LANE_CLI_FLAG, LANE_CLIS, cli_args_allowed
from .lane_env import BASE_NAMES, lane_process_environment
from .lane_workdir import CAPTURE_OFF, ensure_lane_workdir
from .lane_worker_mode import WORKER_FLAG

# lane -> (console script, module run with ``python -m``) outside a frozen build
DEV_CLIS: dict[str, tuple[str, str]] = {
    "gather": ("gather", "gather"),
    "crucible": ("crucible", "crucible"),
    "chorus": ("chorus", "chorus"),
    "index": ("index", "index_graph.cli"),
}
NOT_IN_BUILD = "not_in_build"


class LaneCliUnavailable(OSError):
    """The lane CLI cannot run in this install; ``code`` names why."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _importable(module: str) -> bool:
    try:
        return importlib.util.find_spec(module.split(".")[0]) is not None
    except (ImportError, ValueError):
        return False


def module_argv(lane: str, *, frozen: bool | None = None,
                importable: Callable[[str], bool] = _importable) -> list[str] | None:
    """``[python, -m, module]`` outside a frozen build; a frozen engine refuses
    ``-m``, so there it is always None."""
    if (is_frozen() if frozen is None else frozen) or lane not in DEV_CLIS:
        return None
    module = DEV_CLIS[lane][1]
    return [sys.executable, "-m", module] if importable(module) else None


def lane_cli_argv(lane: str, *, frozen: bool | None = None,
                  executable: str | None = None,
                  which: Callable[[str], str | None] = shutil.which,
                  importable: Callable[[str], bool] = _importable) -> list[str] | None:
    """The argv prefix that runs ``lane``'s CLI, or None when there is none."""
    if is_frozen() if frozen is None else frozen:
        if lane not in LANE_CLIS:
            return None
        return [executable or sys.executable, LANE_CLI_FLAG, lane]
    if lane not in DEV_CLIS:
        return None
    script = which(DEV_CLIS[lane][0])
    if script:
        return [script]
    return module_argv(lane, frozen=False, importable=importable)


def lane_worker_argv(lane: str, worker_args: list[str], *,
                     executable: str | None = None) -> list[str]:
    """The argv that runs ``lane``'s background worker in the frozen engine:
    ``[<engine.exe>, --bundled-lane-worker, <lane>, <worker args...>]``
    (lane_worker_mode). The index child's worker spawn is rewritten to this."""
    return [executable or sys.executable, WORKER_FLAG, lane, *worker_args]


def is_bundled_cli(prefix: list[str]) -> bool:
    """True for a prefix that runs the engine's ``--bundled-lane-cli`` mode."""
    return LANE_CLI_FLAG in list(prefix)[1:]


def refuses(lane: str, prefix: list[str], args: list[str]) -> bool:
    """True when ``prefix`` is the frozen self-child and its dispatcher would
    refuse ``args`` (frozen_lane_modes.cli_args_allowed)."""
    return is_bundled_cli(prefix) and not cli_args_allowed(lane, list(args))


def lane_cli_environment(lane: str, extra: Mapping[str, str] | None = None, *,
                         bundled: bool = False,
                         environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """The child env: the lane environment, or for a frozen self-child the
    bundled child set plus the lane's declared, granted and extra names. Both
    end with capture off (a call's extra values cannot turn it back on) and
    the UTF-8 settings."""
    source = os.environ if environ is None else environ
    env = lane_process_environment(lane, extra, environ=source)
    if bundled:
        base = bundled_child_environment(source, lane=lane)
        taken = {key.upper() for key in base}
        base.update({key: value for key, value in env.items()
                     if key.upper() not in BASE_NAMES and key.upper() not in taken})
        base.update({str(k): str(v) for k, v in (extra or {}).items()})
        base.update(CAPTURE_OFF)
        env = base
    env.update(UTF8_ENV)
    return env


def _default_prefix(lane: str) -> list[str]:
    argv = lane_cli_argv(lane)
    if argv:
        return argv
    if is_frozen() or lane not in DEV_CLIS:
        raise LaneCliUnavailable(NOT_IN_BUILD, f"the {lane} CLI is not in this build")
    return [DEV_CLIS[lane][0]]   # the OS names the missing program


def _window_flags() -> dict:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def run_lane_cli(lane: str, args: list[str], *, timeout: float,
                 prefix: list[str] | None = None,
                 extra_env: Mapping[str, str] | None = None,
                 environ: Mapping[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run ``lane``'s CLI with ``args`` and return the finished process.

    ``prefix`` is the argv that runs the CLI (default: lane_cli_argv). Raises
    LaneCliUnavailable when the CLI cannot run here, and whatever
    subprocess.run raises (TimeoutExpired, OSError) otherwise."""
    source = os.environ if environ is None else environ
    argv = list(prefix) if prefix else _default_prefix(lane)
    bundled = is_bundled_cli(argv)
    if refuses(lane, argv, args):
        verb = " ".join(list(args)[:2])
        raise LaneCliUnavailable(NOT_IN_BUILD, f"{lane} {verb} is not in this build")
    env = lane_cli_environment(lane, extra_env, bundled=bundled, environ=source)
    folder = ensure_lane_workdir(lane, source)
    return subprocess.run(argv + list(args), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          env=env, cwd=str(folder), shell=False, **_window_flags())


def absolute(path: str) -> str:
    """``path`` made absolute against the engine's directory; the CLI runs in the
    lane folder, so a relative path would resolve somewhere else."""
    return str(Path(path).resolve()) if path else path
