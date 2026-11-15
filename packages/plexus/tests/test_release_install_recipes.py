import hashlib
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.4.0"
WHEEL = f"plexus_mesh-{VERSION}-py3-none-any.whl"
SDIST = f"plexus_mesh-{VERSION}.tar.gz"
SUMS = "SHA256SUMS.txt"


def _readme_block(language: str) -> str:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(rf"```{language}\n(.*?)\n```", readme, re.DOTALL)
    assert match, f"{language} recipe block missing"
    return match.group(1).replace("\r\n", "\n").replace("\r", "\n")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_fixture(root: Path, sums_text: str) -> None:
    root.mkdir()
    (root / WHEEL).write_bytes(b"wheel-bytes")
    (root / SDIST).write_bytes(b"sdist-bytes")
    (root / "SHA256SUMS.txt").write_text(sums_text, encoding="utf-8")


def _sums(case: str) -> str:
    wheel_hash = _digest(b"wheel-bytes")
    sdist_hash = _digest(b"sdist-bytes")
    rows = {
        "valid": f"{wheel_hash}  {WHEEL}\n{sdist_hash}  {SDIST}\n",
        "empty": "",
        "missing_wheel": f"{sdist_hash}  {SDIST}\n",
        "bad_hash": f"{'0' * 64}  {WHEEL}\n{sdist_hash}  {SDIST}\n",
        "duplicate": f"{wheel_hash}  {WHEEL}\n{wheel_hash}  {WHEEL}\n{sdist_hash}  {SDIST}\n",
        "extra": f"{wheel_hash}  {WHEEL}\n{sdist_hash}  {SDIST}\n{sdist_hash}  extra.whl\n",
        "path": f"{wheel_hash}  nested/{WHEEL}\n{sdist_hash}  {SDIST}\n",
    }
    return rows[case]


def _wsl_path(path: Path) -> str:
    resolved = path.resolve().as_posix()
    if re.match(r"^[A-Za-z]:/", resolved):
        return f"/mnt/{resolved[0].lower()}{resolved[2:]}"
    return resolved


def _git_bash_path(path: Path) -> str:
    resolved = path.resolve().as_posix()
    if re.match(r"^[A-Za-z]:/", resolved):
        return f"/{resolved[0].lower()}{resolved[2:]}"
    return resolved


def _bash_candidates() -> list[str]:
    if os.name != "nt":
        found = shutil.which("bash")
        return [found] if found else []
    prefixes = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ]
    candidates = []
    for prefix in prefixes:
        candidates.extend([
            str(Path(prefix) / "Git" / "bin" / "bash.exe"),
            str(Path(prefix) / "Git" / "usr" / "bin" / "bash.exe"),
        ])
    found = shutil.which("bash")
    if found:
        candidates.append(found)
    return list(dict.fromkeys(candidates))


def _probe_bash(command: str, *, require_msys: bool) -> bool:
    if not command or not Path(command).exists():
        return False
    try:
        completed = subprocess.run(
            [command, "--noprofile", "--norc", "-c", "printf '%s' \"$BASH_VERSION\"; printf ' '; uname -s 2>/dev/null || true"],
            text=True,
            capture_output=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if completed.returncode != 0 or not completed.stdout.strip():
        return False
    if require_msys and not any(tag in completed.stdout for tag in ("MINGW", "MSYS", "CYGWIN")):
        return False
    return True


def _select_bash(candidates: list[str] | None = None, *, require_msys: bool | None = None) -> str | None:
    require = os.name == "nt" if require_msys is None else require_msys
    for command in candidates or _bash_candidates():
        if _probe_bash(command, require_msys=require):
            return command
    return None


def _bash_path(path: Path, *, git_bash: bool) -> str:
    if os.name == "nt":
        return _git_bash_path(path) if git_bash else _wsl_path(path)
    return path.resolve().as_posix()


def _run_bash_recipe(tmp_path: Path, case: str) -> subprocess.CompletedProcess[str]:
    bash = _select_bash()
    if bash is None:
        pytest.skip("working Bash is not available")
    git_bash = os.name == "nt"
    fixture = tmp_path / "fixture"
    run_dir = tmp_path / "run"
    fake_bin = tmp_path / "fake-bin"
    marker = tmp_path / "install-called"
    download_marker = tmp_path / "download-called"
    _write_fixture(fixture, _sums(case))
    run_dir.mkdir()
    fake_bin.mkdir()
    (fake_bin / "curl").write_text(
        """#!/usr/bin/env bash
set -euo pipefail
out=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    *) shift ;;
  esac
done
[ -n "$out" ] || { echo "curl mock missing -o output" >&2; exit 1; }
[ -f "$FIXTURE_DIR/$out" ] || { echo "curl mock missing fixture: $out" >&2; exit 1; }
printf '%s\n' "$out" >> "$DOWNLOAD_MARKER"
cp "$FIXTURE_DIR/$out" "$out"
""",
        encoding="utf-8",
        newline="\n",
    )
    (fake_bin / "python").write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" = "-m" ] && [ "${2:-}" = "pip" ] && [ "${3:-}" = "install" ]; then
  printf '%s\n' "$*" >> "$INSTALL_MARKER"
  exit 0
fi
exec "$REAL_PYTHON" "$@"
""",
        encoding="utf-8",
        newline="\n",
    )
    for tool in ("curl", "python"):
        (fake_bin / tool).chmod((fake_bin / tool).stat().st_mode | stat.S_IXUSR)
    script_path = tmp_path / "recipe.sh"
    script_path.write_text(
        "\n".join(
            [
                f'export PATH="{_bash_path(fake_bin, git_bash=git_bash)}:$PATH"',
                f"export FIXTURE_DIR={shlex.quote(_bash_path(fixture, git_bash=git_bash))}",
                f"export INSTALL_MARKER={shlex.quote(_bash_path(marker, git_bash=git_bash))}",
                f"export DOWNLOAD_MARKER={shlex.quote(_bash_path(download_marker, git_bash=git_bash))}",
                f"export REAL_PYTHON={shlex.quote(_bash_path(Path(sys.executable), git_bash=git_bash))}",
                _readme_block("bash"),
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    return subprocess.run(
        [bash, _bash_path(script_path, git_bash=git_bash)],
        cwd=run_dir,
        env=os.environ,
        text=True,
        capture_output=True,
    )


def _run_powershell_recipe(tmp_path: Path, case: str) -> subprocess.CompletedProcess[str]:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is not available")
    fixture = tmp_path / "fixture"
    run_dir = tmp_path / "run"
    marker = tmp_path / "install-called"
    download_marker = tmp_path / "download-called"
    _write_fixture(fixture, _sums(case))
    run_dir.mkdir()
    harness = f"""
function Invoke-WebRequest {{
    param([string]$Uri, [string]$OutFile)
    Copy-Item -LiteralPath (Join-Path $env:FIXTURE_DIR $OutFile) -Destination $OutFile -Force
    Add-Content -LiteralPath $env:DOWNLOAD_MARKER -Value $OutFile
}}
function python {{
    if ($args.Count -ge 4 -and $args[0] -eq "-m" -and $args[1] -eq "pip" -and $args[2] -eq "install") {{
        Add-Content -LiteralPath $env:INSTALL_MARKER -Value ($args -join " ")
        return
    }}
    throw "unexpected python invocation: $($args -join ' ')"
}}
{_readme_block("powershell")}
"""
    return subprocess.run(
        [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", harness],
        cwd=run_dir,
        env={
            **os.environ,
            "FIXTURE_DIR": str(fixture),
            "INSTALL_MARKER": str(marker),
            "DOWNLOAD_MARKER": str(download_marker),
        },
        text=True,
        capture_output=True,
    )


def _assert_downloads_ran(tmp_path: Path) -> None:
    downloads = (tmp_path / "download-called").read_text(encoding="utf-8").splitlines()
    assert downloads == [WHEEL, SDIST, SUMS]


def test_windows_bash_selection_rejects_wsl_alias_before_git_bash(monkeypatch):
    def fake_exists(self):
        return True

    def fake_run(args, **kwargs):
        if args[0] == "wsl-bash":
            return subprocess.CompletedProcess(args, 1, "Windows Subsystem for Linux has no installed distributions.", "")
        if args[0] == "git-bash":
            return subprocess.CompletedProcess(args, 0, "5.2.37 MINGW64_NT-10.0", "")
        raise AssertionError(args)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(subprocess, "run", fake_run)

    assert _select_bash(["wsl-bash", "git-bash"], require_msys=True) == "git-bash"


@pytest.mark.parametrize("runner", [_run_bash_recipe, _run_powershell_recipe])
def test_release_recipe_valid_checksums_call_mocked_installer(tmp_path: Path, runner):
    completed = runner(tmp_path, "valid")
    assert completed.returncode == 0, completed.stderr + completed.stdout
    _assert_downloads_ran(tmp_path)
    assert (tmp_path / "install-called").read_text(encoding="utf-8").count(WHEEL) == 1


@pytest.mark.parametrize("case", ["empty", "missing_wheel", "bad_hash", "duplicate", "extra", "path"])
@pytest.mark.parametrize("runner", [_run_bash_recipe, _run_powershell_recipe])
def test_release_recipe_invalid_checksums_do_not_call_mocked_installer(
    tmp_path: Path, case: str, runner
):
    completed = runner(tmp_path, case)
    assert completed.returncode != 0, completed.stdout
    _assert_downloads_ran(tmp_path)
    assert not (tmp_path / "install-called").exists()
