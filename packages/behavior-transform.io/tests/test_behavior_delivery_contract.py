from __future__ import annotations

from pathlib import Path

from tools.behavior_flagship import REQUIRED_FILES, doctor_envelope


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_root_delivery_files_are_present() -> None:
    required = [
        "README.md",
        "USAGE.md",
        "CHANGELOG.md",
        "AUTHORS.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "assets/behavior-transform-hero.svg",
    ]

    missing = [path for path in required if not (ROOT / path).is_file()]

    assert missing == []


def test_doctor_tracks_root_delivery_files() -> None:
    for path in ["AUTHORS.md", "CONTRIBUTING.md", "LICENSE", "CHANGELOG.md"]:
        assert path in REQUIRED_FILES

    envelope = doctor_envelope()
    checks = {
        item["id"]: item
        for output in envelope["outputs"]
        if output["kind"] == "checks"
        for item in output["items"]
    }

    for path in ["AUTHORS.md", "CONTRIBUTING.md", "LICENSE", "CHANGELOG.md"]:
        assert checks[f"required:{path}"]["status"] == "MATCH"


def test_readme_has_public_and_developer_delivery_sections() -> None:
    readme = _read("README.md")

    for heading in ["## Who this is for", "## Usage", "## For developers"]:
        assert heading in readme
    assert "compliance intermediary" in readme
    assert "bt doctor --json" in readme
    assert "python -B -m pytest" in readme


def test_changelog_records_current_delivery_status() -> None:
    changelog = _read("CHANGELOG.md")

    assert "behavior-transform.io Forward Delivery Contract" in changelog
    assert "public-surface-sweeper" in changelog
    assert "private-line IO boundary" in changelog
