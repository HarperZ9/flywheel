import sys
import subprocess
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"


def test_infer_help():
    result = subprocess.run(
        [sys.executable, "-m", "tools.bt_cli", "infer", "--help"],
        capture_output=True, text=True,
        cwd=str(TOOLS.parent),
    )
    assert result.returncode == 0
    assert "infer" in result.stdout.lower() or "inference" in result.stdout.lower()


def test_infer_listed_in_help():
    result = subprocess.run(
        [sys.executable, "-m", "tools.bt_cli", "--help"],
        capture_output=True, text=True,
        cwd=str(TOOLS.parent),
    )
    assert result.returncode == 0
    assert "infer" in result.stdout
