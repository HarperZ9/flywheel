"""`flywheel --version` prints the version the command runs from."""
import sys
import tomllib
from pathlib import Path

from harness import cli_entry, cli_version

ROOT = Path(__file__).resolve().parents[1]


def _checkout_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def test_version_flag_prints_the_checkout_version(capsys):
    assert cli_entry.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"flywheel {_checkout_version()}"


def test_short_version_flag_matches(capsys):
    assert cli_entry.main(["-V"]) == 0
    assert capsys.readouterr().out.strip() == f"flywheel {_checkout_version()}"


def test_frozen_build_reads_package_metadata(monkeypatch):
    from importlib import metadata
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(metadata, "version", lambda name: "9.9.9" if name == "flywheel-verify" else "")
    assert cli_version.installed_version() == "9.9.9"


def test_no_metadata_and_no_checkout_reads_unknown(monkeypatch):
    from importlib import metadata

    def missing(name):
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(metadata, "version", missing)
    assert cli_version.installed_version() == "unknown"
