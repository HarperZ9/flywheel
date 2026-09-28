"""Where Flywheel keeps its own state, for the guards that keep lanes out of it.

The Flywheel home holds the gateway token, the lane folders and the private
stores. The run root holds agent runs, snapshots, lessons, eval and workflow
runs, which can carry the same content as a trace. The run root sits under the
home only by default: ``FLYWHEEL_RUN_ROOT``, a ``.flywheel-run-root`` marker
(``run_paths``) or a non-default ``FLYWHEEL_HOME`` each put it elsewhere, so a
guard that protects the home alone misses it.

Two guards read this: a T1 lane path argument (``lane_tier_gate``) and the
local model's project folder (``local_agent_grants``). The gateway exports its
``--run-root`` as ``FLYWHEEL_RUN_ROOT`` at start, so both see the run root the
engine uses.
"""
from __future__ import annotations

import os
from typing import Mapping


def state_roots(environ: Mapping[str, str]) -> tuple[str, ...]:
    """The Flywheel home and the run root, each resolved, without duplicates."""
    from .lane_workdir import flywheel_home
    from .run_paths import run_root_default
    found: list[str] = []
    for raw in (str(flywheel_home(environ)),
                environ.get("FLYWHEEL_RUN_ROOT") or run_root_default()):
        try:
            real = os.path.realpath(os.path.expanduser(raw))
        except (OSError, ValueError):
            continue
        if os.path.normcase(real) not in {os.path.normcase(p) for p in found}:
            found.append(real)
    return tuple(found)
