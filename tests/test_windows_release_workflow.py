"""Release workflow contract: candidates are read-only, publishing is a
separate protected reusable workflow, every action is pinned to a full
40-hex SHA, and no overwrite path exists anywhere."""
from pathlib import Path

WORKFLOWS = Path(".github/workflows")


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
