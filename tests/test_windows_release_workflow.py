"""Release workflow contract: candidates are read-only, publishing is a
separate protected reusable workflow, every action is pinned to a full
40-hex SHA, and no overwrite path exists anywhere."""
import ast
from pathlib import Path
import re
import tomllib

WORKFLOWS = Path(".github/workflows")
PACKAGING = Path("packaging")


def _text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _actions_pinned(text: str) -> None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- uses:") or stripped.startswith("uses:"):
            ref = stripped.split("@", 1)[1].split()[0]
            assert len(ref) == 40 and all(
                c in "0123456789abcdef" for c in ref.lower()), (
                f"action ref is not a full 40-hex SHA: {ref}")


def _spec_hiddenimports(name: str) -> set[str]:
    tree = ast.parse((PACKAGING / name).read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "hiddenimports":
            imports.update(
                elt.value for elt in node.value.elts
                if isinstance(elt, ast.Constant)
                and isinstance(elt.value, str)
            )
    return imports


def test_every_action_in_every_workflow_is_sha_pinned():
    for path in WORKFLOWS.glob("*.yml"):
        _actions_pinned(path.read_text(encoding="utf-8"))


def test_the_candidate_workflow_never_writes():
    text = _text("desktop-release.yml")
    assert "contents: read" in text
    assert "contents: write" not in text
    assert "gh release" not in text, (
        "a candidate job must not touch releases")
    assert "--clobber" not in text


def test_the_candidate_uploads_an_artifact_instead():
    text = _text("desktop-release.yml")
    assert "upload-artifact@" in text
    assert "if-no-files-found: error" in text


def test_publishing_is_a_separate_protected_reusable_workflow():
    text = _text("windows-publish.yml")
    assert "workflow_call" in text, (
        "publishing must be reusable and explicitly called")
    # The workflow token stays read-only; repository write rides the
    # fine-grained secret only.
    assert "contents: read" in text
    assert "publish_token" in text
    assert "gh release create" in text
    assert "--clobber" not in text


def test_publish_refuses_an_existing_release():
    text = _text("windows-publish.yml")
    assert "already exists" in text
    assert "gh release upload" not in text


def test_publish_verifies_the_candidate_hash_first():
    text = _text("windows-publish.yml")
    assert "installer_sha256" in text
    assert "Get-FileHash" in text
    assert "refusing to publish" in text


def test_pypi_publish_keeps_its_oidc_token_isolated():
    text = _text("publish.yml")
    assert "id-token: write" in text
    assert "gh-action-pypi-publish" in text


def test_desktop_freeze_carries_bulletin_identity_signing_backend():
    workflow = _text("desktop-release.yml")
    install_lines = [
        line.strip()
        for line in workflow.splitlines()
        if re.search(r"\bpython\s+-m\s+pip\s+install\b", line)
    ]
    assert any(
        "pyinstaller==6.21.0" in line and ".[signing]" in line
        for line in install_lines
    ), "desktop freeze must install the signing extra with PyInstaller"

    signing_line = next(
        index for index, line in enumerate(workflow.splitlines())
        if ".[signing]" in line
    )
    build_line = next(
        index for index, line in enumerate(workflow.splitlines())
        if r"scripts\build_installer.ps1" in line
    )
    assert signing_line < build_line
    assert "importlib.metadata" in workflow
    assert "cryptography" in workflow

    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["dependencies"] == []
    assert project["project"]["optional-dependencies"]["signing"] == [
        "cryptography",
    ]

    required_hiddenimports = {
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        "cryptography.hazmat.primitives.serialization",
        "harness.bulletin_identity",
        "harness.bulletin_identity_contract",
        "harness.bulletin_identity_key",
        "harness.bulletin_identity_network",
        "harness.bulletin_identity_origin",
        "harness.bulletin_identity_route",
        "harness.bulletin_identity_store",
        "harness.bulletin_signed_transport",
        "harness.credential_handles",
        "harness.journey_lock",
        "harness.key_roster",
        "harness.keychain",
        "harness.keychain_route",
    }
    assert required_hiddenimports <= _spec_hiddenimports(
        "flywheel-gateway.spec"
    )
