"""Downloads must be reproducible and exclude unlisted local files."""
import json
import hashlib
import shutil
import zipfile

import pytest

from scripts import build_skill_bundle as builder
from scripts import check_public_instructions as hygiene


def test_plugin_and_mcp_documents_are_covered_by_public_hygiene(tmp_path):
    for relative in ("plugins/example/skills/example/SKILL.md",
                     "plugins/example/skills/example/references/constraints.md",
                     "plugins/example/README.md",
                     "harness/skill_resources/example/SKILL.md"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Local fixture: " + "C:" + chr(92) + "dev" + chr(92) + "fixture")
        assert path in hygiene.published_surface_files(tmp_path, extra_roots=(tmp_path,))
        assert hygiene.scan(path, tmp_path)


def test_bundles_are_reproducible_and_allowlisted(tmp_path, monkeypatch):
    source = tmp_path / "plugin"
    shutil.copytree(builder.PLUGIN, source)
    (source / "unlisted-local-note.txt").write_text("PUBLIC TEST CANARY")
    (source / "skills" / builder.NAME / "unlisted-note.txt").write_text("PUBLIC TEST CANARY")
    monkeypatch.setattr(builder, "PLUGIN", source)
    first = builder.bundle(tmp_path / "first")
    for path in source.rglob("*"):
        if path.is_file():
            text = path.read_text("utf-8")
            path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    second = builder.bundle(tmp_path / "second")
    assert first == second
    for artifact in first["artifacts"]:
        a = tmp_path / "first" / artifact["file"]
        assert a.read_bytes() == (tmp_path / "second" / artifact["file"]).read_bytes()
        with zipfile.ZipFile(a) as archive:
            names = archive.namelist()
            assert len(names) == artifact["files"]
            assert all(name.startswith(builder.NAME + "/") for name in names)
            assert all(".." not in name.split("/") for name in names)
            assert not any("unlisted" in name for name in names)
            assert not any(b"PUBLIC TEST CANARY" in archive.read(name) for name in names)
            if artifact["file"].endswith("-skill.zip"):
                assert builder.NAME + "/SKILL.md" in names
                assert builder.NAME + "/LICENSE" in names
            else:
                manifest = json.loads(archive.read(builder.NAME + "/.codex-plugin/plugin.json"))
                assert manifest["name"] == builder.NAME
                assert manifest["version"] == first["version"]


def test_portable_manifest_preserves_identity_and_openai_presentation(tmp_path):
    result = builder.bundle(tmp_path)
    path = next(row["file"] for row in result["artifacts"]
                if row["file"].endswith("-plugin.zip"))
    with zipfile.ZipFile(tmp_path / path) as archive:
        root = json.loads(archive.read(builder.NAME + "/plugin.json"))
        codex = json.loads(archive.read(builder.NAME + "/.codex-plugin/plugin.json"))
        claude = json.loads(archive.read(builder.NAME + "/.claude-plugin/plugin.json"))
        assert root["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
        assert root["name"] == codex["name"] == claude["name"]
        assert root["version"] == codex["version"] == claude["version"]
        assert root["extensions"] == {"com.openai": {"interface": codex["interface"]}}
        assert "skills" not in root and "interface" not in root
        assert set(root) <= {"$schema", "name", "version", "description", "author",
                            "homepage", "repository", "license", "keywords", "extensions"}
        assert builder.NAME + "/skills/" + builder.NAME + "/SKILL.md" in archive.namelist()


@pytest.mark.parametrize("field,value", [("name", "different-name"), ("version", "9.0.0")])
def test_bundle_rejects_compatibility_identity_drift(tmp_path, monkeypatch, field, value):
    source = tmp_path / "source"
    shutil.copytree(builder.PLUGIN, source)
    path = source / ".claude-plugin/plugin.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest[field] = value
    path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(builder, "PLUGIN", source)
    with pytest.raises(ValueError, match="manifest identity"):
        builder.bundle(tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_release_verification_binds_accepted_checksums_to_archive_bytes(tmp_path):
    result = builder.bundle(tmp_path)
    sums = tmp_path / "SHA256SUMS"
    accepted = hashlib.sha256(sums.read_bytes()).hexdigest()
    assert builder.verify_release(sums, accepted) == 2
    archive = tmp_path / result["artifacts"][0]["file"]
    archive.write_bytes(archive.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="archive hash"):
        builder.verify_release(sums, accepted)


@pytest.mark.parametrize("rows", ["", "0" * 64 + "  ../outside.zip\n",
                                  "0" * 64 + "  flywheel-evidence-task-0.1.0-plugin.zip\n"])
def test_release_verification_rejects_incomplete_or_unsafe_receipt(tmp_path, rows):
    sums = tmp_path / "SHA256SUMS"
    sums.write_text(rows, encoding="utf-8")
    accepted = hashlib.sha256(sums.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="receipt"):
        builder.verify_release(sums, accepted)


def test_release_verification_rejects_changed_receipt(tmp_path):
    builder.bundle(tmp_path)
    with pytest.raises(ValueError, match="accepted"):
        builder.verify_release(tmp_path / "SHA256SUMS", "0" * 64)


@pytest.mark.parametrize("change", ["extra", "missing", "duplicate", "mixed_version"])
def test_release_verification_rejects_archive_set_drift(tmp_path, change):
    result = builder.bundle(tmp_path)
    sums = tmp_path / "SHA256SUMS"
    if change == "extra":
        (tmp_path / "unreviewed.zip").write_bytes(b"unreviewed")
    elif change == "missing":
        (tmp_path / result["artifacts"][0]["file"]).unlink()
    else:
        rows = sums.read_text("utf-8").splitlines()
        rows[1] = rows[0] if change == "duplicate" else rows[1].replace(result["version"], "9.0.0")
        sums.write_text("\n".join(rows) + "\n", encoding="utf-8")
    accepted = hashlib.sha256(sums.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="receipt"):
        builder.verify_release(sums, accepted)
