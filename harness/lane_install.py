"""Run a lane's package manager: the argv, the interpreter and the folder it runs in.

``lanes.install_lane`` decides whether a lane needs an install; this module runs
it. Three rules keep a planted program or package from answering instead:

- pip runs as ``<interpreter> -m pip``, never a ``pip`` found on PATH. The
  interpreter is the one the lane launches with: the registry row's pinned
  ``runtime_python`` for a package install when set, else this engine's own
  interpreter. A frozen build has no interpreter of its own, so without a pin it
  refuses with ``pip_interpreter_unavailable``.
- npm resolves through safe_program (``npm.cmd`` on Windows, from an absolute
  PATH entry that reaches no working folder). No safe npm is
  ``npm_unavailable``, before anything starts.
- The package manager runs in a new empty folder, so a ``pip`` package or an
  ``.npmrc`` in the caller's current folder is not read.

The environment is the lane environment, as before: build backends and install
scripts are lane-supplied code.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile

from . import safe_program

PIP_INTERPRETER_UNAVAILABLE = "pip_interpreter_unavailable"
NPM_UNAVAILABLE = "npm_unavailable"
UNSAFE_ARGUMENT = "package_manager_argument_refused"
TIMEOUT_S = 300


class PackageManagerUnavailable(Exception):
    """The install cannot start. ``code`` is stable; the message names no path."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def pip_interpreter(lane_name: str, profile: str) -> str:
    """The interpreter whose pip installs the lane (see the module docstring)."""
    from . import lanes
    from .lane_runtime import _runtime_python
    row = lanes.read_registry().get(lane_name)
    if profile != "source" and isinstance(row, dict) and row.get("runtime_python"):
        path, codes = _runtime_python(row)
        if codes or not path:
            raise PackageManagerUnavailable(
                (codes or ("runtime_python_invalid",))[0],
                "the lane's runtime_python is not a usable interpreter, so pip "
                "has nowhere safe to install it")
        return path
    if lanes._frozen():
        raise PackageManagerUnavailable(
            PIP_INTERPRETER_UNAVAILABLE,
            "this build has no Python interpreter to run pip; the app's bundled "
            "lanes need no install, and a pip lane needs a runtime_python pin")
    return sys.executable


def package_manager_argv(lane, profile: str, repo, *, env, cwd) -> list[str]:
    """The full argv for one install. Raises PackageManagerUnavailable.

    ``run_install`` starts it with ``safe_program.child_env``: npm on Windows is
    a batch file."""
    if lane.kind == "pip":
        target = ["-e", str(repo)] if profile == "source" else [
            f"{lane.install_name}=={lane.version}"]
        return [pip_interpreter(lane.name, profile), "-m", "pip", "install", *target]
    target = str(repo) if profile == "source" else f"{lane.install_name}@{lane.version}"
    try:
        return safe_program.argv(["npm", "install", "-g", target], cwd=cwd, env=env)
    except safe_program.ProgramUnavailable:
        raise PackageManagerUnavailable(
            NPM_UNAVAILABLE,
            "npm was not found in an absolute PATH folder outside the working "
            "folder; install Node.js, which includes npm, then run the install "
            "again") from None
    except safe_program.ProgramRefused:
        raise PackageManagerUnavailable(
            UNSAFE_ARGUMENT,
            "npm is a batch file on this system and the install argument holds "
            "characters cmd.exe would run as a command") from None


def run_install(lane, profile: str, repo=None) -> dict:
    """Install ``lane`` with its package manager and report the outcome."""
    from .lane_env import lane_process_environment
    env = lane_process_environment(lane.name)
    with tempfile.TemporaryDirectory(prefix="flywheel-install-") as folder:
        try:
            cmd = package_manager_argv(lane, profile, repo, env=env, cwd=folder)
        except PackageManagerUnavailable as error:
            return {"name": lane.name, "installed": False, "code": error.code,
                    "detail": error.detail}
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S,
                                    env=safe_program.child_env(cmd, env, cwd=folder),
                                    cwd=folder)
        except (OSError, subprocess.TimeoutExpired) as error:
            return {"name": lane.name, "installed": False, "cmd": cmd,
                    "detail": f"install failed: {error}"}
    ok = result.returncode == 0
    return {"name": lane.name, "installed": ok, "cmd": cmd,
            "detail": (result.stdout[-200:] if ok else
                       (result.stderr[-300:] or result.stdout[-300:])).strip()}
