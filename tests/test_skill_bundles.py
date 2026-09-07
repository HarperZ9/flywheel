"""Downloads must be reproducible and exclude unlisted local files."""
import json
import shutil
import zipfile

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
