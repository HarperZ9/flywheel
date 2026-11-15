"""Tests for verify_manifest.py, the standalone manifest verifier.

Each test builds a temporary sealed directory, then runs the vendored verifier as
a subprocess so the observed exit code is the real one a stranger would see. The
tamper and missing cases are the load-bearing ones: they must drive the exit code
off zero.
"""
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "verify_manifest.py"

FILES = {
    "README.md": b"witnessing spine readme\n",
    "SYNTHESIS.md": b"synthesis body\n",
    "RUN-001.md": b"run one body\n",
}


def _seal(root: Path, files: dict[str, bytes]) -> None:
    lines = ["# test manifest", "# <sha256>  <file>"]
    for name, content in files.items():
        (root / name).write_bytes(content)
        lines.append(f"{hashlib.sha256(content).hexdigest()}  {name}")
    (root / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run(target: Path | None, script: Path = SCRIPT) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(script)]
    if target is not None:
        cmd.append(str(target))
    return subprocess.run(cmd, capture_output=True, text=True)


def test_clean_manifest_matches(tmp_path: Path) -> None:
    _seal(tmp_path, FILES)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_tampered_file_is_drift(tmp_path: Path) -> None:
    _seal(tmp_path, FILES)
    target = tmp_path / "RUN-001.md"
    data = target.read_bytes()
    target.write_bytes(bytes([data[0] ^ 0xFF]) + data[1:])
    result = _run(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "DRIFT" in result.stdout


def test_missing_manifest_is_unverifiable(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_bytes(FILES["README.md"])
    result = _run(tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "UNVERIFIABLE" in result.stdout


def test_missing_listed_file_is_unverifiable(tmp_path: Path) -> None:
    _seal(tmp_path, FILES)
    (tmp_path / "RUN-001.md").unlink()
    result = _run(tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "UNVERIFIABLE" in result.stdout


def test_default_dir_is_script_own_dir(tmp_path: Path) -> None:
    _seal(tmp_path, FILES)
    local_script = tmp_path / "verify_manifest.py"
    shutil.copyfile(SCRIPT, local_script)
    result = _run(None, script=local_script)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout
