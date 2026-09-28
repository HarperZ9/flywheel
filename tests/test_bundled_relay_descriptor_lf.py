"""The relay descriptor pins the tag's LF bytes, whatever the host's git setting.

The descriptor used to hash the relay submodule's working tree, which a Windows
checkout with core.autocrlf=true writes with CRLF endings: the pin then held only
on a host configured that way and differed from the tag and from the relay
payload row. It now hashes the bytes ``git cat-file --filters`` gives under
core.autocrlf=false and core.eol=lf, the way the payload row generator reads
every row, so the descriptor, the compiled expectation and the row agree.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

from harness.bundled_lane_admission import descriptor_digest, source_manifest
from harness.bundled_lane_expectations import expected_bundled_lane

ROOT = Path(__file__).resolve().parents[1]
CRLF, LF = b"\r\n", b"\n"


def _relay_row() -> dict:
    for line in (ROOT / "packaging" / "python-lane-payloads.jsonl").read_text(
            encoding="utf-8").splitlines():
        if line.strip() and json.loads(line)["lane"] == "relay":
            return json.loads(line)
    raise AssertionError("no relay row")


def test_the_descriptor_expectation_and_payload_row_share_one_manifest():
    descriptor = json.loads((ROOT / "packaging" / "bundled-lanes" / "relay.json").read_text(
        encoding="utf-8"))
    row = _relay_row()["component_descriptor"]["source"]
    source = descriptor["source"]
    assert source["files"] == row["files"]
    assert (source["file_count"], source["bytes"], source["manifest_sha256"]) == (
        row["file_count"], row["bytes"], row["manifest_sha256"])
    assert source["commit"] == row["commit"]
    expected = expected_bundled_lane("relay")
    assert expected["source_manifest_sha256"] == row["manifest_sha256"]
    assert expected["descriptor_sha256"] == descriptor_digest(descriptor)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_the_manifest_reads_the_commit_bytes_not_a_crlf_working_tree(tmp_path):
    from scripts.check_bundled_lane_descriptors import committed_source_files
    repo = tmp_path / "relay"
    (repo / "src" / "relay").mkdir(parents=True)
    _git(repo, "init", "-q")
    for key, value in (("user.email", "t@example.invalid"), ("user.name", "t"),
                       ("core.autocrlf", "false")):
        _git(repo, "config", key, value)
    (repo / "src" / "relay" / "a.py").write_bytes(b"x = 1\ny = 2\n")
    (repo / "src" / "relay" / "notes.txt").write_bytes(b"not python\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "one")
    commit = _git(repo, "rev-parse", "HEAD")
    # The Windows default: a fresh checkout writes CRLF.
    _git(repo, "config", "core.autocrlf", "true")
    (repo / "src" / "relay" / "a.py").unlink()
    _git(repo, "checkout", "--", ".")
    assert CRLF in (repo / "src" / "relay" / "a.py").read_bytes()
    assert _git(repo, "status", "--short") == ""
    rows = committed_source_files(repo, commit)
    assert [row["path"] for row in rows] == ["src/relay/a.py"]
    assert rows[0]["bytes"] == len(b"x = 1\ny = 2\n")
    assert rows[0]["sha256"] == "sha256:" + sha256(b"x = 1\ny = 2\n").hexdigest()
    tree = source_manifest(repo / "src" / "relay", relative_to=repo)
    assert tree[0]["sha256"] != rows[0]["sha256"]


def test_a_tree_without_git_keeps_the_working_tree_manifest(tmp_path):
    from scripts.check_bundled_lane_descriptors import committed_source_files
    (tmp_path / "src" / "relay").mkdir(parents=True)
    assert committed_source_files(tmp_path, "a" * 40) is None
