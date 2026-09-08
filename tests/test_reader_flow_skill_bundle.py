"""Reader Flow Review skill downloads are standalone and reproducible."""

import json
import shutil
import zipfile

import pytest

from scripts import build_reader_flow_skill_bundle as builder
from scripts import check_public_instructions as hygiene


def _copy_builder_source(tmp_path, monkeypatch):
    source = tmp_path / "source"
    skill = source / "skills" / builder.NAME
    shutil.copytree(builder.SKILL, skill)
    shutil.copy2(builder.ROOT / "LICENSE", source / "LICENSE")
    monkeypatch.setattr(builder, "ROOT", source)
    monkeypatch.setattr(builder, "SKILL", skill)
    return source, skill


def test_reader_flow_skill_bundle_is_reproducible_and_allowlisted(
    tmp_path, monkeypatch
):
    source, skill = _copy_builder_source(tmp_path, monkeypatch)
    (skill / "unlisted-local-note.txt").write_text(
        "PUBLIC TEST CANARY " + "C:" + chr(92) + "dev",
        encoding="utf-8",
    )

    first = builder.bundle(tmp_path / "first")
    for path in source.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    second = builder.bundle(tmp_path / "second")

    assert first == second
    first_zip = tmp_path / "first" / first["artifacts"][0]["file"]
    second_zip = tmp_path / "second" / second["artifacts"][0]["file"]
    assert first_zip.read_bytes() == second_zip.read_bytes()

    expected = {f"{builder.NAME}/{name}" for name in builder.SKILL_FILES}
    expected.add(f"{builder.NAME}/LICENSE")
    with zipfile.ZipFile(first_zip) as archive:
        names = set(archive.namelist())
        assert names == expected
        assert not any("unlisted" in name for name in names)
        assert not any(b"PUBLIC TEST CANARY" in archive.read(name)
                       for name in names)

    manifest = json.loads((tmp_path / "first" / "manifest.json").read_text(
        encoding="utf-8"
    ))
    assert manifest["version"] == "0.1.0"
    assert manifest["tag_plan"] == "skill-reader-flow-review-v0.1.0"
    assert "Flywheel platform release" in manifest["does_not_prove"]


def test_reader_flow_bundle_rejects_local_paths_in_included_files(
    tmp_path, monkeypatch
):
    _, skill = _copy_builder_source(tmp_path, monkeypatch)
    skill.joinpath("README.md").write_text(
        "Install from " + "C:" + chr(92) + "dev",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="local drive path"):
        builder.bundle(tmp_path / "out")


def test_reader_flow_skill_surfaces_are_public_hygiene_scanned():
    repo = builder.ROOT
    found = hygiene.published_surface_files(repo.parent, extra_roots=(repo,))
    keys = {hygiene.key_for(path, repo.parent) for path in found}

    assert "skills/reader-flow-review/SKILL.md" in keys
    assert "skills/reader-flow-review/README.md" in keys
    assert "skills/reader-flow-review/SOURCE-ATTRIBUTION.md" in keys
    assert "skills/reader-flow-review/EVALUATION.md" in keys
    for path in found:
        key = hygiene.key_for(path, repo.parent)
        if key.startswith("skills/reader-flow-review/"):
            assert hygiene.scan(path, repo.parent) == []
