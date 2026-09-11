import os
import subprocess
from pathlib import Path

import pytest

from desktop.tool import installed_launch_acceptance_platform as platform


def _windows_powershell_51() -> str:
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    candidate = Path(system_root) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    if candidate.exists():
        return str(candidate)
    pytest.skip("Windows PowerShell 5.1 unavailable")


def _write_shortcut(script: Path, link: Path, target: Path) -> None:
    script.write_text(
        "\n".join([
            "param([string]$Link, [string]$Target)",
            "$ErrorActionPreference = 'Stop'",
            "$s = New-Object -ComObject WScript.Shell",
            "$l = $s.CreateShortcut($Link)",
            "$l.TargetPath = $Target",
            "$l.Save()",
        ]),
        encoding="utf-8",
    )
    # A cold Windows PowerShell 5.1 launch under Defender and disk load on a CI
    # runner overruns a tight bound; the COM save itself is fast. Keep the budget
    # generous. The pytest --timeout=300 wrapper stays the real hang backstop.
    completed = subprocess.run(
        [
            _windows_powershell_51(), "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(script), "-Link", str(link), "-Target", str(target),
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace", timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    assert link.is_file(), "COM did not save the requested literal shortcut path"


@pytest.mark.skipif(os.name != "nt", reason="Windows shortcut metadata test")
@pytest.mark.parametrize("count", [1, 2])
def test_resolve_links_reads_real_windows_shortcut_paths_as_data(tmp_path, count):
    target_dir = tmp_path / "target dir 'quote $dollar é"
    target_dir.mkdir()
    target = target_dir / "flywheel desktop.exe"
    target.write_bytes(b"app")
    link_dir = tmp_path / "links with spaces 'quote $dollar é"
    link_dir.mkdir()
    names = [f"Flywheel {index} $(Write-Output injected) é" for index in range(count)]
    links = [link_dir / f"{name}.lnk" for name in names]
    for link in links:
        _write_shortcut(tmp_path / "create-shortcut.ps1", link, target)

    before = {link: link.read_bytes() for link in links}
    rows = platform.LocalWindowsMetadata()._resolve_links(links)

    assert [(row.name, row.target) for row in rows] == [(name, target) for name in names]
    assert {link: link.read_bytes() for link in links} == before


def test_resolve_links_preserves_missing_shortcut_null_behavior(tmp_path):
    assert platform.LocalWindowsMetadata()._resolve_links([tmp_path / "missing.lnk"]) == []


@pytest.mark.skipif(os.name != "nt", reason="Windows shortcut metadata test")
def test_invalid_shortcut_remains_failed_rather_than_absent_metadata(tmp_path):
    from desktop.tool.installed_launch_acceptance_model import HarnessConfig
    from desktop.tool.installed_launch_acceptance_runner import AcceptanceHarness
    from tests.installed_launch_acceptance_fixtures import FakeWindows
    invalid = tmp_path / "invalid.lnk"
    invalid.write_bytes(b"not a shortcut")
    rows = platform.LocalWindowsMetadata()._resolve_links([invalid])
    assert len(rows) == 1
    harness = AcceptanceHarness(HarnessConfig(tmp_path, tmp_path / "unused.json", mode="metadata"),
        fs=None, windows=FakeWindows(start=rows, desktop=rows[0]), http=None, process=None)
    harness._metadata(tmp_path / "expected.exe")
    states = {row["id"]: row["state"] for row in harness.rows}
    assert states["H04_start_menu_shortcut_targets_app_exe"] == "FAIL"
    assert states["H05_desktop_shortcut_optional_or_targets_app_exe"] == "FAIL"
    assert invalid.read_bytes() == b"not a shortcut"


@pytest.mark.skipif(os.name != "nt", reason="Windows COM best-fit path control")
def test_resolve_links_rejects_com_best_fit_path_substitution(tmp_path):
    from desktop.tool.installed_launch_acceptance_model import HarnessConfig, ShortcutRecord
    from desktop.tool.installed_launch_acceptance_runner import AcceptanceHarness
    from tests.installed_launch_acceptance_fixtures import FakeWindows
    target = tmp_path / "synthetic.exe"
    target.write_bytes(b"never launched")
    original = tmp_path / "Alias O.lnk"
    _write_shortcut(tmp_path / "create.ps1", original, target)
    requested = tmp_path / "Alias Ω.lnk"
    requested.write_bytes(original.read_bytes())
    probe = tmp_path / "read-name.ps1"
    probe.write_text(
        "param([string]$Link)\n[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)\n"
        "$s=New-Object -ComObject WScript.Shell\n$s.CreateShortcut($Link).FullName\n",
        encoding="utf-8",
    )
    # Same cold-launch budget rationale as _write_shortcut above.
    observed = subprocess.run(
        [_windows_powershell_51(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(probe),
         "-Link", str(requested)], capture_output=True, encoding="utf-8", timeout=120,
    )
    assert observed.returncode == 0, observed.stderr
    if Path(observed.stdout.strip()) == requested:
        pytest.skip("This COM runtime preserves the Unicode filename; no best-fit substitution")
    assert Path(observed.stdout.strip()) == original
    before = {path: path.read_bytes() for path in (original, requested)}
    rows = platform.LocalWindowsMetadata()._resolve_links([requested])
    windows = FakeWindows(start=[ShortcutRecord("independent valid", target)],
        desktop=rows[0] if rows else None)
    harness = AcceptanceHarness(HarnessConfig(tmp_path, tmp_path / "unused.json", mode="metadata"),
        fs=None, windows=windows, http=None, process=None)
    harness._metadata(target)
    states = {row["id"]: row["state"] for row in harness.rows}
    assert states["H04_start_menu_shortcut_targets_app_exe"] == "PASS"
    assert states["H05_desktop_shortcut_optional_or_targets_app_exe"] == "FAIL"
    assert len(rows) == 1 and rows[0].target != target
    assert {path: path.read_bytes() for path in before} == before
