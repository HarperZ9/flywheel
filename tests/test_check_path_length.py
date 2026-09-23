"""The tracked-path length gate: the rule, the real tree, and a bite."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from check_path_length import LIMIT, main, too_long  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _git(repo: Path, *args: str, stdin: bytes | None = None) -> bytes:
    proc = subprocess.run(["git", "-C", str(repo), *args], input=stdin,
                          capture_output=True)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    return proc.stdout


def test_a_path_at_the_limit_passes_and_one_past_it_fails():
    at = "a/" + "x" * (LIMIT - 2)
    past = "b/" + "x" * (LIMIT - 1)
    assert (len(at), len(past)) == (LIMIT, LIMIT + 1)
    assert too_long([at, past, "short.py"]) == [(past, LIMIT + 1)]


def test_violations_are_listed_longest_first():
    shorter, longer = "x" * (LIMIT + 5), "y" * (LIMIT + 20)
    assert [p for p, _ in too_long([shorter, longer])] == [longer, shorter]


def test_the_real_tree_passes_with_no_exceptions():
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout, so there is no tracked tree to check")
    assert main(ROOT) == 0


def test_the_gate_bites_on_a_tracked_path_past_the_limit(tmp_path, capsys):
    # The long path goes into the index only. Writing it to disk would need
    # the long-path support whose absence is the reason for this gate.
    _git(tmp_path, "init", "-q")
    blob = _git(tmp_path, "hash-object", "-w", "--stdin", stdin=b"x\n")
    long_path = "/".join(["artifacts", "run", "spin"] * 12) + "/report.json"
    assert len(long_path) > LIMIT
    _git(tmp_path, "update-index", "--add", "--cacheinfo",
         f"100644,{blob.decode().strip()},{long_path}")
    assert main(tmp_path) == 1
    assert long_path in capsys.readouterr().out


def test_a_path_that_is_not_utf8_is_an_error_not_a_crash(tmp_path, capsys):
    # Git keeps path bytes as given, so a tracked path can be invalid UTF-8.
    # Such a path has no length in characters: the gate names it and exits 2.
    _git(tmp_path, "init", "-q")
    blob = _git(tmp_path, "hash-object", "-w", "--stdin", stdin=b"x\n").strip()
    _git(tmp_path, "update-index", "--index-info",
         stdin=b"100644 " + blob + b"\tcaf\xe9.txt\n")
    assert main(tmp_path) == 2
    assert "not valid UTF-8: b'caf\\xe9.txt'" in capsys.readouterr().out


def test_no_git_checkout_is_an_error_not_a_pass(tmp_path, monkeypatch):
    # Stop git from finding a repository above tmp_path.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert main(tmp_path) == 2
