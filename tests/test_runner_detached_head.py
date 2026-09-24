"""The Android runners must read a detached HEAD without throwing.

CI checks out a pull request as a detached HEAD, where
``git branch --show-current`` prints nothing. PowerShell hands that back as
``$null``, and ``$null.Trim()`` throws. In the real-gateway runner the throw
came before the try block, so the runner exited 1 with no receipt and the
caller saw only FileNotFoundError on receipt.json. A local run on a branch
cannot reproduce it, so this guard reads the source instead.
"""
import re
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "desktop" / "tool"
RAW_BRANCH_TRIM = re.compile(r"\(&\s*git\b[^)]*branch --show-current\)\.Trim\(\)")


def test_no_runner_trims_raw_branch_output():
    offenders = [
        f"{path.name}:{number}"
        for path in sorted(TOOL.glob("*.ps1"))
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1)
        if RAW_BRANCH_TRIM.search(line)
    ]
    assert offenders == [], (
        "wrap the git call in a string so a detached HEAD reads as \"\": "
        + ", ".join(offenders))


def test_guard_catches_the_pattern_it_names():
    assert RAW_BRANCH_TRIM.search(
        "branch = (& git -C $repoRoot branch --show-current).Trim()")
    assert not RAW_BRANCH_TRIM.search(
        'branch = "$(& git -C $repoRoot branch --show-current)".Trim()')
