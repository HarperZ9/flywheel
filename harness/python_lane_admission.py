"""Admission for released Python lanes carried in the frozen gateway."""
from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys
from typing import Callable, Mapping

from .bundled_lane_admission import (
    BundledLaneAdmission,
    _component_summary,
    _load_descriptor,
    _module_importable,
    _validate_descriptor,
    bundled_child_environment,
)
from .bundled_lane_expectations import expected_bundled_lane
from .mcp_client import LaunchSpec

ADMITTED_PYTHON_LANES = ("mneme", "plexus")


def default_descriptor_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / "python-lane-payloads" / name / "descriptors" / f"{name}.json"


def admitted_python_child_environment(environ: Mapping[str, str]) -> dict[str, str]:
    env = bundled_child_environment(environ)
    env["PYTHONSAFEPATH"] = "1"
    return env


def admit_python_lane(
    name: str,
    *,
    executable: str,
    environ: Mapping[str, str],
    descriptor_path: str | Path | None = None,
    importable_fn: Callable[[str], bool] | None = None,
    expected: Mapping[str, object] | None = None,
) -> BundledLaneAdmission:
    if name not in ADMITTED_PYTHON_LANES:
        return BundledLaneAdmission(None, None, ("bundled_lane_not_supported",))
    expected_row = {**expected_bundled_lane(name), **dict(expected or {})}
    path = Path(descriptor_path) if descriptor_path is not None else default_descriptor_path(name)
    descriptor, load_codes = _load_descriptor(path)
    if descriptor is None:
        return BundledLaneAdmission(None, None, load_codes)
    codes = list(load_codes)
    codes.extend(_validate_descriptor(descriptor, expected_row))
    module_name = str(expected_row.get("module", ""))
    if not module_name:
        codes.append("bundled_entrypoint_invalid")
    elif not (importable_fn or _module_importable)(module_name):
        codes.append("bundled_module_missing")
    codes = list(dict.fromkeys(codes))
    if codes:
        return BundledLaneAdmission(None, None, tuple(codes))
    launch = LaunchSpec(
        (executable, "--bundled-lane-mcp", name),
        env_overrides=tuple(sorted(admitted_python_child_environment(environ).items())),
        inherit_env=False,
        hide_window=True,
        allowed_tools=tuple(expected_row["allowed_tools"]),
    )
    return BundledLaneAdmission(launch, _component_summary(descriptor, expected_row), ())


def dispatch_python_lane_mcp(
    argv: list[str] | tuple[str, ...] | None = None,
    *,
    import_module_fn: Callable[[str], object] = importlib.import_module,
    executable: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> int | None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "--bundled-lane-mcp":
        return None
    if len(args) != 2:
        return 2
    name = args[1]
    if name == "relay":
        return None
    if name not in ADMITTED_PYTHON_LANES:
        return 2
    expected_row = expected_bundled_lane(name)
    admission = admit_python_lane(
        name, executable=executable or sys.executable,
        environ=environ or os.environ, expected=expected_row)
    if admission.blocking_codes:
        return 2
    module = import_module_fn(str(expected_row["module"]))
    serve = getattr(module, str(expected_row["callable"]), None)
    if not callable(serve):
        return 2
    from .bundled_lane_stdio import serve_admitted_lane
    return serve_admitted_lane(module, tuple(expected_row["allowed_tools"]))
