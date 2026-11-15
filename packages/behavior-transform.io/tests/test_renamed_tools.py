import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools"
sys.path.insert(0, str(TOOLS))


def test_pressure_scan_importable():
    import pressure_scan
    assert callable(getattr(pressure_scan, "main", None))


def test_pressure_rewrite_importable():
    import pressure_rewrite
    assert callable(getattr(pressure_rewrite, "main", None))


def test_term_discover_importable():
    import term_discover
    assert callable(getattr(term_discover, "main", None))


def test_old_aup_files_do_not_exist():
    assert not (TOOLS / "aup_lint.py").exists(), "aup_lint.py still present"
    assert not (TOOLS / "aup_rewrite.py").exists(), "aup_rewrite.py still present"
    assert not (TOOLS / "aup_discover.py").exists(), "aup_discover.py still present"


def test_no_aup_prefix_references_in_code():
    """Check that aup_ references are removed from code (excluding docs, hooks, and this test)."""
    result = subprocess.run(
        ["git", "grep", "-rn", "aup_", "--", ":!docs/**", ":!hooks/**", ":!tests/test_native_paths.py", ":!tests/test_invariants.py"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    hits = [l for l in result.stdout.splitlines() if "test_renamed_tools" not in l and "test_invariants" not in l]
    assert hits == [], f"aup_ references remain in code:\n" + "\n".join(hits)
