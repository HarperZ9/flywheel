"""The release helper and the workflow that calls it.

publish.yml builds a release from one tag and runs gates before it publishes.
These tests hold the parts that decide: the version check, the sums check and
the PyPI digest check, each with a control that must fail, and the shape of
the workflow (the gates sit before the upload, a dry run publishes nothing).
"""
import datetime
import hashlib
import re
from pathlib import Path

import pytest

from scripts import release_assets as R

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")


def tree(tmp_path, version="2.0.0", notes=None, pubspec=None, dart=None, cff=None):
    """A folder with the version sites and the files the release check reads."""
    (tmp_path / "desktop" / "lib").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n', "utf-8")
    (tmp_path / "desktop" / "pubspec.yaml").write_text(
        f"name: x\nversion: {pubspec or version}+41\n", "utf-8")
    (tmp_path / "desktop" / "lib" / "version.dart").write_text(
        f"const appVersion = '{dart or version}';\n", "utf-8")
    (tmp_path / "CITATION.cff").write_text(
        f'cff-version: 1.2.0\nversion: "{cff or version}"\n', "utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "MIGRATING-2.0.md").write_text("# Moving\n", "utf-8")
    text = (f"# Flywheel {version}\n\nSee docs/LICENSING.md and docs/MIGRATING-2.0.md.\n"
            if notes is None else notes)
    (tmp_path / f"RELEASE-NOTES-{version}.md").write_text(text, "utf-8")
    (tmp_path / "CHANGELOG.md").write_text(f"# Changelog\n\n## {version} (2026-11-20)\n", "utf-8")
    (tmp_path / "SECURITY.md").write_text("1.9.x until 2027-02-18\n", "utf-8")
    return tmp_path


def test_this_tree_passes_its_own_check():
    assert R.check(ROOT) == []


def test_a_complete_tree_is_clean_for_its_tag(tmp_path):
    assert R.check(tree(tmp_path), tag="v2.0.0", release=True) == []


def test_a_tag_that_disagrees_with_the_declared_version_fails(tmp_path):
    problems = R.check(tree(tmp_path), tag="v2.0.1")
    assert problems == ["tag v2.0.1 does not match the declared version 2.0.0"]


@pytest.mark.parametrize("site", ["pubspec", "dart", "cff"])
def test_a_version_site_left_behind_fails(tmp_path, site):
    problems = R.check(tree(tmp_path, **{site: "1.9.0"}), tag="v2.0.0")
    assert len(problems) == 1 and "declares 1.9.0" in problems[0]


def test_notes_that_are_missing_or_incomplete_fail(tmp_path):
    root = tree(tmp_path, notes="# Flywheel 1.9.0\n\nNo links.\n")
    problems = " ".join(R.check(root, tag="v2.0.0"))
    assert "opens with" in problems and "docs/LICENSING.md" in problems
    assert "docs/MIGRATING-2.0.md" in problems
    (root / "RELEASE-NOTES-2.0.0.md").unlink()
    assert R.check(root) == ["RELEASE-NOTES-2.0.0.md does not exist"]


@pytest.mark.parametrize("name", ["RELEASE-NOTES-2.0.0.md", "CHANGELOG.md", "SECURITY.md"])
def test_a_placeholder_stops_a_release_and_not_a_dry_run(tmp_path, name):
    root = tree(tmp_path)
    path = root / name
    path.write_text(path.read_text("utf-8") + "until SECURITY-WINDOW-END\n", "utf-8")
    assert R.check(root, tag="v2.0.0") == []
    assert R.check(root, tag="v2.0.0", release=True) == [
        f"{name} still holds the placeholder SECURITY-WINDOW-END"]


def test_a_changelog_with_no_dated_section_stops_a_release(tmp_path):
    root = tree(tmp_path)
    (root / "CHANGELOG.md").write_text("# Changelog\n\n## 2.0.0 (RELEASE-DATE)\n", "utf-8")
    problems = R.check(root, tag="v2.0.0", release=True)
    assert any("no dated" in p for p in problems) and any("RELEASE-DATE" in p for p in problems)


def test_stamp_fills_the_dates_and_leaves_a_tree_that_can_release(tmp_path):
    root = tree(tmp_path)
    (root / "CHANGELOG.md").write_text("# Changelog\n\n## 2.0.0 (RELEASE-DATE)\n", "utf-8")
    (root / "SECURITY.md").write_text("1.9.x until SECURITY-WINDOW-END\n", "utf-8")
    (root / "docs" / "VERSIONING.md").write_text("until SECURITY-WINDOW-END.\n", "utf-8")
    (root / "CITATION.cff").write_text('version: "2.0.0"\ndate-released: 2026-10-15\n', "utf-8")
    assert R.check(root, tag="v2.0.0", release=True) != []
    changed = R.stamp(root, datetime.date(2026, 11, 20))
    assert changed == ["CHANGELOG.md", "SECURITY.md", "docs/VERSIONING.md", "CITATION.cff"]
    assert "## 2.0.0 (2026-11-20)" in (root / "CHANGELOG.md").read_text("utf-8")
    assert (root / "SECURITY.md").read_text("utf-8") == "1.9.x until 2027-02-18\n"
    assert "date-released: 2026-11-20" in (root / "CITATION.cff").read_text("utf-8")
    assert R.check(root, tag="v2.0.0", release=True) == []
    assert R.stamp(root, datetime.date(2026, 11, 20)) == []


def assets(tmp_path):
    folder = tmp_path / "assets"
    folder.mkdir()
    files = []
    for name, data in (("a.whl", b"wheel"), ("a.tar.gz", b"sdist"), ("p.zip", b"plugin")):
        (folder / name).write_bytes(data)
        files.append(folder / name)
    R.write_sums(folder, "python", files[:2])
    R.write_sums(folder, "plugin", files[2:])
    return folder


def test_a_folder_whose_sums_hold_verifies(tmp_path):
    listed = R.verify(assets(tmp_path))
    assert listed == {"a.whl": hashlib.sha256(b"wheel").hexdigest(),
                      "a.tar.gz": hashlib.sha256(b"sdist").hexdigest(),
                      "p.zip": hashlib.sha256(b"plugin").hexdigest()}


def test_one_changed_byte_after_the_sums_were_written_fails(tmp_path):
    folder = assets(tmp_path)
    (folder / "a.whl").write_bytes(b"wheeL")
    with pytest.raises(SystemExit, match="a.whl does not match python-SHA256SUMS.txt"):
        R.verify(folder)


def test_a_missing_an_unlisted_or_a_twice_listed_file_fails(tmp_path):
    folder = assets(tmp_path)
    (folder / "extra.bin").write_bytes(b"x")
    with pytest.raises(SystemExit, match="in no sums file: extra.bin"):
        R.verify(folder)
    (folder / "extra.bin").unlink()
    R.write_sums(folder, "again", [folder / "p.zip"])
    with pytest.raises(SystemExit, match="repeated"):
        R.verify(folder)
    (folder / "again-SHA256SUMS.txt").unlink()
    (folder / "p.zip").unlink()
    with pytest.raises(SystemExit, match="lists p.zip, which is missing"):
        R.verify(folder)


def test_a_folder_with_no_sums_file_fails(tmp_path):
    (tmp_path / "a.whl").write_bytes(b"wheel")
    with pytest.raises(SystemExit, match="no sums file"):
        R.verify(tmp_path)


def test_sums_files_are_in_the_form_sha256sum_reads(tmp_path):
    raw = (assets(tmp_path) / "python-SHA256SUMS.txt").read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert all(re.fullmatch(rb"[0-9a-f]{64}  \S+", line) for line in raw.splitlines())


def test_a_build_lists_every_file_and_never_writes_over_one(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "flywheel_verify-0.0.0-py3-none-any.whl").write_bytes(b"wheel")
    (dist / "flywheel_verify-0.0.0.tar.gz").write_bytes(b"sdist")
    out = tmp_path / "out"
    names = {path.name for path in R.build(dist, out, dev=True)}
    assert {"python-SHA256SUMS.txt", "plugin-SHA256SUMS.txt", "source-plugin-SHA256SUMS.txt",
            "vscode-SHA256SUMS.txt"} <= names
    listed = R.verify(out)
    assert set(listed) | {n for n in names if n.endswith("SHA256SUMS.txt")} == names
    assert sum(n.endswith(".vsix") for n in listed) == 1
    assert sum(n.endswith("-plugin.zip") for n in listed) == 2
    assert sum(n.endswith("-skill.zip") for n in listed) == 1
    with pytest.raises(SystemExit, match="is not empty"):
        R.build(dist, out, dev=True)
    (dist / "second.whl").write_bytes(b"x")
    with pytest.raises(SystemExit, match="one wheel and one sdist"):
        R.build(dist, tmp_path / "other", dev=True)


def served(digests):
    return {"urls": [{"filename": n, "digests": {"sha256": d}} for n, d in digests.items()]}


def test_pypi_serving_the_built_files_is_clean(tmp_path):
    sums = assets(tmp_path) / "python-SHA256SUMS.txt"
    assert R.pypi("2.0.0", sums, fetch=lambda v: served(R.read_sums(sums)), wait=0) == []


def test_pypi_serving_another_wheel_fails_at_once(tmp_path):
    sums = assets(tmp_path) / "python-SHA256SUMS.txt"
    calls = []

    def fetch(version):
        calls.append(version)
        return served({**R.read_sums(sums), "a.whl": "0" * 64})

    problems = R.pypi("2.0.0", sums, fetch=fetch, wait=0)
    assert len(problems) == 1 and problems[0].startswith("a.whl: PyPI serves 000")
    assert calls == ["2.0.0"]


def test_pypi_is_asked_again_until_the_release_is_listed(tmp_path):
    sums = assets(tmp_path) / "python-SHA256SUMS.txt"
    replies = [OSError("404"), OSError("404"), served(R.read_sums(sums))]

    def fetch(version):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    assert R.pypi("2.0.0", sums, fetch=fetch, wait=0) == [] and replies == []


def test_a_release_pypi_never_lists_fails(tmp_path):
    sums = assets(tmp_path) / "python-SHA256SUMS.txt"

    def fetch(version):
        raise OSError("404")

    problems = R.pypi("2.0.0", sums, fetch=fetch, tries=3, wait=0)
    assert problems == ["PyPI does not list 2.0.0 yet (OSError)"]


def test_the_marked_tests_include_the_timing_and_compat_gates():
    files = R.gate_tests()
    for name in ("tests/test_compat_records_1x.py", "tests/test_gateway_overhead_timing.py",
                 "tests/test_hosted_streaming_timing.py"):
        assert name in files
    assert "release_gate:" in (ROOT / "pytest.ini").read_text(encoding="utf-8")


def job(name):
    """The text of one job in publish.yml."""
    match = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [a-z][a-z-]*:\n|\Z)", WORKFLOW, re.M | re.S)
    assert match, name
    return match.group(1)


def test_the_upload_and_the_release_wait_for_the_gates():
    for name in ("publish", "release"):
        needs = re.search(r"needs: \[(.*?)\]", job(name)).group(1)
        assert "gates" in needs and "build" in needs, name
        assert "if: needs.plan.outputs.publish == 'true'" in job(name), name
    assert "pypa/gh-action-pypi-publish@" in job("publish")
    assert "gh release create" in job("release") and "--notes-file" in job("release")


def test_the_gates_run_against_the_installed_wheel():
    gates = job("gates")
    order = [gates.index(step) for step in (
        "scripts/check_scope_migration.py",
        "release_assets.py verify release-assets",
        "pip install --no-cache-dir release-assets/*.whl",
        'mv harness "$RUNNER_TEMP/source-harness"',
        "scripts/verify_compat_records.py --control",
        "release_assets.py gate-tests --run",
        "flywheel gate | tee gate.txt",
        "flywheel code -p")]
    assert order == sorted(order)
    assert '"site-packages" in where.parts' in gates


def test_only_a_version_tag_publishes_and_a_dry_run_keeps_its_assets():
    plan = job("plan")
    assert '"$GITHUB_REF" == refs/tags/v*' in plan
    assert "release_assets.py check --tag" in plan and "--release" in plan
    dry = job("dry-run")
    assert "if: needs.plan.outputs.publish != 'true'" in dry and "name: release-dry-run" in dry
    assert "gh release" not in dry and "pypi-publish" not in dry
    assert "dry_run:" in WORKFLOW and "default: true" in WORKFLOW


def test_every_action_is_pinned_to_a_commit():
    uses = re.findall(r"uses: (\S+)", WORKFLOW)
    assert uses and all(re.search(r"@[0-9a-f]{40}$", ref) for ref in uses), uses


def test_the_workflow_holds_no_secret():
    assert "secrets." not in WORKFLOW
