"""Every gateway freeze path stages the lane sources the freeze reads.

The gateway spec freezes every manifest lane but relay from a staged checkout at
``<source-root>/<lane>-<owner_tag>/src`` (scripts/python_lane_freeze.py). The
stager writes that layout (scripts/stage_python_lane_sources.py), but only for
the lanes a build path asks for. When the freeze grew from Canon to every
manifest lane, desktop-release moved to ``--all`` while the installed acceptance
runner and the local installer build kept ``--lane canon``, and PyInstaller
failed on a Windows runner at the first unstaged lane. These checks catch that
mismatch on any host, with no Windows runner and no network clone.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from argparse import Namespace
from hashlib import sha256
from pathlib import Path

import pytest

from harness.evidence_json import canonical_sha256
from scripts.python_lane_freeze import (
    bundled_python_lanes, python_lane_freeze_inputs)
from scripts.stage_python_lane_sources import (
    MANIFEST, _load_rows, selected_lanes, stage_sources)

REPO = Path(__file__).resolve().parents[1]
FREEZE = re.compile(r"PyInstaller\W+packaging[\\/]flywheel-gateway\.spec")
STAGE = re.compile(
    r'python["\s]+(?:@\(\s*)?"?scripts[\\/]stage_python_lane_sources\.py')
ALL_FLAG = re.compile(r"(?<![\w-])--all(?![\w-])")
LANE_FLAG = re.compile(r"""--lane["'\s,]+["']?([A-Za-z0-9_-]+)""")
KNOWN_FREEZE_PATHS = {
    ".github/workflows/desktop-release.yml",
    "desktop/scripts/build_installer.ps1",
    "desktop/tool/run_ci_installed_acceptance.ps1",
}
FIXTURE_PACKAGES = ("lanefix_alpha", "lanefix_beta")


def _freeze_build_paths() -> dict[str, str]:
    """Every tracked script or workflow that runs PyInstaller on the gateway spec."""
    listed = subprocess.run(
        ["git", "ls-files", "--", "*.ps1", "*.psm1", "*.yml", "*.yaml",
         "*.sh", "*.cmd", "*.bat"],
        cwd=REPO, check=True, capture_output=True, text=True).stdout
    found = {}
    for rel in listed.splitlines():
        text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        if FREEZE.search(text):
            found[rel] = text
    return found


def _stage_commands(text: str) -> list[tuple[int, str]]:
    """Each stager invocation with its offset, joined across backtick continuations."""
    commands = []
    for match in STAGE.finditer(text):
        end = text.find("\n", match.start())
        command = text[match.start():end if end >= 0 else len(text)]
        while command.rstrip().endswith("`") and end >= 0:
            following = text.find("\n", end + 1)
            command += " " + text[end + 1:following if following >= 0 else len(text)]
            end = following
        commands.append((match.start(), command))
    return commands


def _lanes_staged_before_freeze(text: str, rows: dict[str, dict]) -> set[str]:
    """The lanes the build path stages ahead of its first gateway freeze."""
    freeze_at = FREEZE.search(text).start()
    staged: set[str] = set()
    for offset, command in _stage_commands(text):
        if offset < freeze_at:
            staged.update(selected_lanes(
                rows, lanes=LANE_FLAG.findall(command) or None,
                all_lanes=bool(ALL_FLAG.search(command))))
    return staged


def test_every_gateway_freeze_path_stages_every_lane_the_freeze_reads():
    rows = _load_rows(MANIFEST)
    required = set(bundled_python_lanes(REPO))
    paths = _freeze_build_paths()
    # False-success control: a scan that finds no build path proves nothing.
    assert KNOWN_FREEZE_PATHS <= set(paths), sorted(paths)
    for rel, text in paths.items():
        staged = _lanes_staged_before_freeze(text, rows)
        missing = required - staged
        assert not missing, (
            f"{rel} freezes the gateway but stages only {sorted(staged)}; "
            f"the freeze also reads {sorted(missing)}")


@pytest.mark.parametrize("text", [
    # The acceptance runner at the 1.0.3 release commit.
    'Invoke-Checked "stage Canon Python lane source" "python" @('
    '"scripts/stage_python_lane_sources.py", "--lane", "canon", '
    '"--source-root", $root)\n'
    'Invoke-Checked "freeze gateway" "python" @("-m", "PyInstaller", '
    '"packaging/flywheel-gateway.spec", "--noconfirm")\n',
    # The local installer build at the same commit.
    "python scripts\\stage_python_lane_sources.py `\n"
    "    --lane canon `\n"
    "    --source-root $root\n"
    "python -m PyInstaller packaging\\flywheel-gateway.spec --noconfirm\n",
])
def test_scan_flags_the_canon_only_stage_that_broke_the_installer(text):
    rows = _load_rows(MANIFEST)
    staged = _lanes_staged_before_freeze(text, rows)
    assert staged == {"canon"}
    assert "accountable-surface" in set(bundled_python_lanes(REPO)) - staged


def test_scan_ignores_a_stage_that_runs_after_the_freeze():
    rows = _load_rows(MANIFEST)
    text = ("python -m PyInstaller packaging/flywheel-gateway.spec\n"
            "python scripts/stage_python_lane_sources.py --all\n")
    assert _lanes_staged_before_freeze(text, rows) == set()


@pytest.fixture
def fixture_imports(monkeypatch):
    """Keep the freeze helper's sys.path and module writes inside one test."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    yield
    for name in [n for n in sys.modules if n.split(".")[0] in FIXTURE_PACKAGES]:
        del sys.modules[name]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _lane_origin(tmp_path: Path, lane: str, package: str) -> dict:
    """A local git origin for one lane in the src layout, and its manifest row."""
    origin = tmp_path / "origins" / lane
    files = {f"src/{package}/__init__.py": b"",
             f"src/{package}/mcp.py": b"def serve():\n    return 0\n"}
    for rel, data in files.items():
        (origin / rel).parent.mkdir(parents=True, exist_ok=True)
        (origin / rel).write_bytes(data)
    (origin / ".gitattributes").write_bytes(b"*.py text eol=lf\n")
    _git(origin, "init", "-q")
    _git(origin, "config", "user.email", "test@example.invalid")
    _git(origin, "config", "user.name", "Test")
    _git(origin, "add", ".")
    _git(origin, "commit", "-qm", "fixture")
    entries = [{"path": rel, "bytes": len(data),
                "sha256": "sha256:" + sha256(data).hexdigest()}
               for rel, data in sorted(files.items())]
    return {
        "lane": lane, "owner_tag": "v1.0.0",
        "owner_commit": _git(origin, "rev-parse", "HEAD"),
        "registry_source_repo": f"public/{lane}",
        "component_descriptor": {
            "entrypoint": {"module": f"{package}.mcp"},
            "source": {"repo": str(origin), "files": entries,
                       "manifest_sha256": "sha256:" + canonical_sha256(entries)}},
    }


def _fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "packaging").mkdir(parents=True)
    rows = [_lane_origin(tmp_path, "alpha", "lanefix_alpha"),
            _lane_origin(tmp_path, "beta", "lanefix_beta")]
    (repo / "packaging" / "python-lane-payloads.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8")
    return repo


def _stage(repo: Path, source_root: Path, *, lanes=None, all_lanes=False):
    return stage_sources(Namespace(
        manifest=str(repo / "packaging" / "python-lane-payloads.jsonl"),
        source_root=str(source_root), lane=lanes, all=all_lanes,
        source_repo=[], receipt=None, bounded_receipt=None))


def test_stager_layout_is_the_layout_the_freeze_reads(tmp_path, fixture_imports):
    repo = _fixture_repo(tmp_path)
    source_root = tmp_path / "sources"
    receipt = _stage(repo, source_root, all_lanes=True)

    pathex, hidden, receipts = python_lane_freeze_inputs(repo, source_root)

    staged_src = [str((Path(row["path"]) / "src").resolve())
                  for row in receipt["lanes"]]
    assert pathex == staged_src
    assert [row["lane"] for row in receipts] == ["alpha", "beta"]
    assert {"lanefix_alpha.mcp", "lanefix_beta.mcp"} <= set(hidden)


def test_freeze_refuses_a_partial_stage_and_names_the_fix(tmp_path, fixture_imports):
    repo = _fixture_repo(tmp_path)
    source_root = tmp_path / "sources"
    _stage(repo, source_root, lanes=["alpha"])

    with pytest.raises(RuntimeError, match=r"staged beta source missing: .*--all"):
        python_lane_freeze_inputs(repo, source_root)
