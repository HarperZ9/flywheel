from pathlib import Path
import shutil
import subprocess

import pytest

HELPER = Path("desktop/tool/run_ci_installed_acceptance.ps1")
ROOT = Path(__file__).resolve().parent.parent


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True)
    if check and completed.returncode != 0:
        raise AssertionError(completed.stdout + completed.stderr)
    return completed


def _ps_literal(path: Path | str) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _run_helper_ps(body: str) -> str:
    exe = shutil.which("powershell") or shutil.which("pwsh")
    if exe is None:
        pytest.skip("PowerShell unavailable")
    code = f". {_ps_literal((ROOT / HELPER).resolve())} -DefineOnly\n{body}"
    completed = subprocess.run(
        [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", code],
        cwd=ROOT, text=True, capture_output=True, timeout=30)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed.stdout


def _init_autocrlf_repo(root: Path, *, pin_lf: bool) -> None:
    _git(root, "init", "-q")
    _git(root, "config", "core.autocrlf", "true")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    if pin_lf:
        (root / ".gitattributes").write_text("f.txt text eol=lf\n", encoding="utf-8", newline="\n")
    (root / "f.txt").write_bytes(b"one\ntwo\n")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "init")
    (root / "f.txt").unlink()
    _git(root, "reset", "--hard", "HEAD")


def test_autocrlf_lf_rewrite_reproduces_status_without_content_diff(tmp_path):
    _init_autocrlf_repo(tmp_path, pin_lf=False)
    assert "w/crlf" in _git(tmp_path, "ls-files", "--eol", "--", "f.txt").stdout

    (tmp_path / "f.txt").write_bytes(b"one\ntwo\n")

    assert _git(tmp_path, "diff", "--quiet", "--ignore-submodules", check=False).returncode == 0
    assert _git(tmp_path, "status", "--porcelain=v1", "--untracked-files=no").stdout == " M f.txt\n"
    root = _ps_literal(tmp_path)
    out = _run_helper_ps(f"""
try {{ Assert-TrackedAndSubmodulesUnchanged 'autocrlf' -Root {root}; throw 'expected failure' }}
catch {{ if ($_.Exception.Message -notmatch 'changed tracked source or submodule state') {{ throw }} }}
'OK'
""")

    assert "autocrlf git status porcelain:  M f.txt" in out
    assert "autocrlf git ls-files --eol: i/lf    w/lf" in out
    assert "autocrlf byte hash f.txt head=" in out
    assert "OK" in out


def test_eol_lf_pin_keeps_flutter_style_lf_rewrite_clean(tmp_path):
    _init_autocrlf_repo(tmp_path, pin_lf=True)
    assert "attr/text eol=lf" in _git(tmp_path, "ls-files", "--eol", "--", "f.txt").stdout

    (tmp_path / "f.txt").write_bytes(b"one\ntwo\n")

    assert _git(tmp_path, "diff", "--quiet", "--ignore-submodules", check=False).returncode == 0
    assert _git(tmp_path, "status", "--porcelain=v1", "--untracked-files=no").stdout == ""
    root = _ps_literal(tmp_path)
    out = _run_helper_ps(f"Assert-TrackedAndSubmodulesUnchanged 'pinned' -Root {root}\n'OK'")
    assert "OK" in out


@pytest.mark.parametrize("prefix,rejected", [(" ", False), ("+", True), ("-", True), ("U", True)])
def test_submodule_status_prefixes_are_checked_without_regex_failure(prefix, rejected):
    # Reach the real helper's submodule branch without changing a real checkout.
    line = prefix + "a" * 40 + " fixtures/child (heads/main)"
    body = f"""
function git {{
  $global:LASTEXITCODE = 0
  if ($args -contains 'submodule') {{ {_ps_literal(line)} }}
}}
$rejected = $false
try {{ Assert-TrackedAndSubmodulesUnchanged 'submodule-fixture' }}
catch {{
  if ($_.Exception.Message -notlike 'submodule-fixture changed submodule checkout:*') {{ throw }}
  $rejected = $true
}}
if ($rejected -ne ${str(rejected).lower()}) {{ throw 'unexpected submodule disposition' }}
'OK'
"""
    assert "OK" in _run_helper_ps(body)
