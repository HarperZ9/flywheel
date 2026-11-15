import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import json
import os
import pytest
from unittest.mock import patch, MagicMock

from safe_exec import _run, _archive_raw, main


def test_run_echo_success():
    if sys.platform == "win32":
        rc, stdout, stderr = _run(["cmd", "/c", "echo hello"], timeout=10, shell=False, cwd=None)
    else:
        rc, stdout, stderr = _run(["echo", "hello"], timeout=10, shell=False, cwd=None)
    assert rc == 0
    assert b"hello" in stdout


def test_run_command_not_found():
    rc, stdout, stderr = _run(
        ["nonexistent_command_xyz_123"],
        timeout=10, shell=False, cwd=None,
    )
    assert rc == 127
    assert b"command not found" in stderr


def test_run_timeout():
    if sys.platform == "win32":
        cmd = ["cmd", "/c", "ping -n 10 127.0.0.1"]
    else:
        cmd = ["sleep", "10"]
    rc, stdout, stderr = _run(cmd, timeout=0.1, shell=False, cwd=None)
    assert rc == 124
    assert b"timeout" in stderr


def test_run_with_cwd(tmp_path):
    if sys.platform == "win32":
        rc, stdout, stderr = _run(["cmd", "/c", "cd"], timeout=10, shell=False, cwd=str(tmp_path))
    else:
        rc, stdout, stderr = _run(["pwd"], timeout=10, shell=False, cwd=str(tmp_path))
    assert rc == 0
    assert str(tmp_path).replace("\\", "/") in stdout.decode().replace("\\", "/") or \
           tmp_path.name in stdout.decode()


def test_archive_raw(tmp_path):
    os.chdir(tmp_path)
    path = _archive_raw("test cmd", b"out", b"err")
    assert path.exists()
    content = path.read_bytes()
    assert b"stdout" in content
    assert b"out" in content
    assert b"stderr" in content


def test_main_dry_run(capsys):
    rc = main(["--dry-run", "--IO-off", "--", "echo", "hello"])
    assert rc == 0
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert parsed["dry_run"] is True
    assert parsed["argv"] == ["echo", "hello"]


def test_main_no_command():
    with pytest.raises(SystemExit):
        main(["--dry-run"])


def test_main_json_mode(capsys, tmp_path):
    os.chdir(tmp_path)
    if sys.platform == "win32":
        rc = main(["--json", "--IO-off", "--no-archive", "--", "cmd", "/c", "echo test"])
    else:
        rc = main(["--json", "--IO-off", "--no-archive", "--", "echo", "test"])
    assert rc == 0
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert "stdout" in parsed
    assert "test" in parsed["stdout"]
    assert parsed["rc"] == 0


def test_main_diff_only(capsys, tmp_path):
    os.chdir(tmp_path)
    if sys.platform == "win32":
        rc = main(["--diff-only", "--IO-off", "--no-archive", "--", "cmd", "/c", "echo x"])
    else:
        rc = main(["--diff-only", "--IO-off", "--no-archive", "--", "echo", "x"])
    assert rc == 0
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert "audit_counts" in parsed
    assert parsed["io_channel"] == "off"


def test_main_io_off_passthrough(capsys, tmp_path):
    os.chdir(tmp_path)
    if sys.platform == "win32":
        rc = main(["--IO-off", "--no-archive", "--", "cmd", "/c", "echo passthrough"])
    else:
        rc = main(["--IO-off", "--no-archive", "--", "echo", "passthrough"])
    assert rc == 0
    output = capsys.readouterr().out
    assert "passthrough" in output
