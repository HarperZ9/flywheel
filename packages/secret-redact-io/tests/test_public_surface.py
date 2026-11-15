from __future__ import annotations

import subprocess
import sys


def test_public_surface_gate_blocks_env_files_and_secret_shapes(tmp_path) -> None:
    scanner = "scripts/check_public_surface.py"
    (tmp_path / ".env").write_text("TOKEN=secret", encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, scanner, str(tmp_path)],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert ".env" in completed.stdout


def test_public_surface_gate_accepts_current_project() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/check_public_surface.py"],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
