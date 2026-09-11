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


def test_frozen_discovery_keeps_source_and_distribution_metadata():
    spec = (PACKAGING / "flywheel-gateway.spec").read_text(encoding="utf-8")
    helper = Path("scripts/frozen_gateway_metadata.py").read_text(encoding="utf-8")
    assert "flywheel_verify_metadata_datas(copy_metadata)" in spec
    assert 'copy_metadata("flywheel-verify")' in helper
    assert 'path.name == "direct_url.json"' in helper
    assert 'Path("flywheel_verify.egg-info")' in helper
    assert '(str(repo / "harness" / "gateway.py"), "harness")' in spec


def test_frozen_gateway_spec_pins_owned_relay_submodule_before_analysis():
    spec = (PACKAGING / "flywheel-gateway.spec").read_text(encoding="utf-8")
    assert "check_lane_descriptor(repo, \"relay\")" in spec
    assert "bundled Relay import shadowed outside relay/src" in spec
    assert "find_spec(\"relay.local_mcp\")" in spec
    assert "pathex=[str(relay_src), str(repo)]" in spec


def test_candidate_checks_the_actual_frozen_engine_before_installer():
    text = _text("desktop-release.yml")
    freeze = text.index("python -m PyInstaller")
    smoke = text.index("python scripts/check_frozen_gateway.py")
    package = text.index(r"-File scripts\build_installer.ps1 -SkipEngine")
    assert freeze < smoke < package
    assert "--expected-version" in text
    assert "frozen gateway smoke failed" in text
    assert "frozen-gateway-smoke.json" in text


def _frozen_checker():
    import runpy
    return runpy.run_path("scripts/check_frozen_gateway.py")["validate_documents"]


def _discovery_documents():
    routes = {
        "/api/bulletin-identity": {"get": {"security": [{"bearerAuth": []}]}},
        "/api/bulletin-identity/create": {"post": {"security": [{"bearerAuth": []}]}},
        "/api/bulletin-identity/register": {"post": {"security": [{"bearerAuth": []}]}},
    }
    identity = {
        "schema": "flywheel.bulletin-identity-status/v1",
        "source": "env", "signing_available": True,
        "create_available": False, "register_available": False,
        "unavailable_reason": "ENV_CREDENTIAL_PRESENT",
    }
    spec = {"openapi": "3.1.0", "info": {"version": "0.5.0"}, "paths": routes}
    card = {"schema": "flywheel.discovery/v1", "version": "0.5.0", "routes": 3,
            "discovery": {"openapi": "/openapi.json", "llms_txt": "/llms.txt"}}
    return identity, spec, card, "Flywheel 0.5.0\n" + "\n".join(routes)


def test_frozen_checker_rejects_semantically_wrong_success_responses():
    import copy
    import pytest
    validate = _frozen_checker()
    docs = _discovery_documents()
    validate(*docs, expected_version="0.5.0")
    for kind in ("missing_signing", "wrong_version", "missing_route", "key_leak"):
        broken = copy.deepcopy(docs)
        if kind == "missing_signing":
            broken[0]["signing_available"] = False
        elif kind == "wrong_version":
            broken[1]["info"]["version"] = "unknown"
        elif kind == "missing_route":
            del broken[1]["paths"]["/api/bulletin-identity/register"]
        else:
            broken[0]["private_jwk"] = {"d": "synthetic"}
        with pytest.raises(RuntimeError):
            validate(*broken, expected_version="0.5.0")


def test_relay_is_populated_after_selecting_the_release_commit():
    text = _text("desktop-release.yml")
    assert text.index('git checkout --detach') < text.index(
        'git submodule update --init --recursive') < text.index('python -m PyInstaller')
    assert "tag-pinned submodule checkout failed" in text
