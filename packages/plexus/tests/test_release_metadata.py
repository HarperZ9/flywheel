import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.4.0"


def test_release_identity_is_aligned():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    init_text = (ROOT / "src" / "plexus" / "__init__.py").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert pyproject["project"]["version"] == VERSION
    assert re.search(rf'__version__ = "{VERSION}"', init_text)
    assert f"## {VERSION}" in changelog


def test_install_docs_are_github_only_and_hash_verified():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Bash/macOS/Linux" in readme
    assert "native PowerShell" in readme
    assert "https://github.com/HarperZ9/plexus/releases/download/v0.4.0" in readme
    assert "plexus_mesh-0.4.0-py3-none-any.whl" in readme
    assert "SHA256SUMS.txt" in readme
    assert "Get-FileHash -Algorithm SHA256" in readme
    assert "Invoke-WebRequest" in readme
    assert "`plexus-mesh` 0.4.0 is published on PyPI" in readme
    assert "pip install git+https://github.com/HarperZ9/plexus.git" not in readme


def test_release_docs_preserve_declared_not_probed_boundary():
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").lower()
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    init_text = (ROOT / "src" / "plexus" / "__init__.py").read_text(encoding="utf-8").lower()

    assert "declared, not probed" in readme
    assert "declarative discovery does not run the tools" in readme
    assert "does not prove that real external lanes are live" in readme
    assert "no live external lane probing" in changelog
    assert "optional explicit probe helpers can launch owned mcp servers" in pyproject["project"]["description"].lower()
    assert "optional probe helpers" in init_text
    assert "does not import, probe, or run those tools" not in init_text
    assert "plexus does not probe or run the tools" not in pyproject["project"]["description"].lower()
