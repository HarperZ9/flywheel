"""Repo-wide invariants enforcing the standalone extraction contract."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _grep(pattern: str) -> list[str]:
    r = subprocess.run(
        ["git", "grep", "-rn", "--", pattern,
         ":!docs/**", ":!tests/**", ":!CLAUDE.md"],
        cwd=str(REPO), capture_output=True, text=True,
    )
    return [
        l for l in r.stdout.splitlines()
        if "test_invariants" not in l and "test_native_paths" not in l
    ]


def _grep_regex(pattern: str) -> list[str]:
    r = subprocess.run(
        ["git", "grep", "-Prn", "--", pattern, ":!docs/**", ":!tests/**", ":!CLAUDE.md"],
        cwd=str(REPO), capture_output=True, text=True,
    )
    return [l for l in r.stdout.splitlines() if "test_invariants" not in l]
def test_no_warden_shell_imports():
    hits = _grep("from warden_shell") + _grep("import warden_shell")
    assert hits == [], "\n".join(hits)


def test_no_warden_per_turn_imports():
    assert _grep("warden_per_turn_dispatcher") == []


def test_no_agents_warden_shell_paths():
    hits = _grep("AGENTS.warden_shell") + _grep("AGENTS/warden_shell")
    # exclude bootstrap/profile scripts that legitimately reference WARDEN paths
    hits = [h for h in hits if not h.startswith("profiles/") and not h.startswith("tools/pre-commit-aup.sh")]
    assert hits == [], "\n".join(hits)


def test_no_aup_prefix_files():
    assert list(REPO.rglob("aup_*.py")) == []


def test_no_aup_evasion_references():
    assert _grep("aup_evasion") == []

def test_no_context_modulate_references():
    assert _grep("context_modulate") == []


def test_no_batch_modulate_memory_references():
    assert _grep("batch_modulate_memory") == []


def test_no_universal_prefire_gate_references():
    assert _grep("universal_prefire_gate") == []


def test_no_absolute_user_paths_in_hooks():
    hits = _grep("C:/Users") + _grep("C:\\\\Users")
    hook_hits = [h for h in hits if h.startswith("hooks/")]
    assert hook_hits == [], "\n".join(hook_hits)


def test_zero_external_dependencies():
    import tomllib
    with open(REPO / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    deps = data.get("project", {}).get("dependencies", [])
    assert deps == [], f"External deps found: {deps}"
