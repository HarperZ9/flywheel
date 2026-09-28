"""The version `flywheel --version` reports."""
from __future__ import annotations

import sys
from pathlib import Path


def installed_version() -> str:
    """The flywheel-verify version this command runs from.

    A source checkout reads its own pyproject.toml, so a stale copy installed
    elsewhere in the environment cannot answer for it. A pip install or a
    frozen build reads the package metadata. Anything else is "unknown"."""
    from importlib import metadata
    checkout = Path(__file__).resolve().parents[1] / "pyproject.toml"
    if not getattr(sys, "frozen", False) and checkout.is_file():
        try:
            import tomllib
            project = tomllib.loads(checkout.read_text(encoding="utf-8"))["project"]
            if project.get("name") == "flywheel-verify":
                return str(project["version"])
        except (KeyError, OSError, ValueError):
            pass
    try:
        return metadata.version("flywheel-verify")
    except metadata.PackageNotFoundError:
        return "unknown"


def print_version_if_asked(raw: list[str]) -> bool:
    """Print `flywheel <version>` for --version or -V and report whether it did."""
    if not any(a in ("--version", "-V") for a in raw):
        return False
    print(f"flywheel {installed_version()}")
    return True
