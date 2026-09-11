import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
import pytest
REPO = Path(__file__).resolve().parents[1]
ISCC_VALUE = os.environ.get("FLYWHEEL_ISCC", "")
ISCC = Path(ISCC_VALUE) if ISCC_VALUE else Path("__missing_flywheel_iscc__")
pytestmark = pytest.mark.skipif(
    os.name != "nt" or not ISCC.exists(),
    reason="requires Windows and FLYWHEEL_ISCC pointing to the signed Inno compiler",
)
def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
def _metadata(
    root: Path,
    dirname: str,
    version: str,
    extra: dict[str, str] | None = None,
    *,
    name: str = "flywheel-verify",
) -> Path:
    path = root / "engine" / "_internal" / dirname
    _write(path / "METADATA", f"Name: {name}\nVersion: {version}\n")
    _write(path / "entry_points.txt", "[console_scripts]\n")
    _write(path / "licenses" / "LICENSE", "license\n")
    for relative, text in (extra or {}).items():
        _write(path / relative, text)
    return path
def _other_metadata(root: Path) -> Path:
    path = root / "engine" / "_internal" / "cryptography-46.0.7.dist-info"
    _write(path / "METADATA", "Name: cryptography\nVersion: 46.0.7\n")
    return path
def _build_fixture(
    tmp_path: Path,
    *,
    race_probe: bool = False,
    post_move_probe: bool = False,
    abort_after_quarantine: bool = False,
    quarantine_leaf: str | None = None,
) -> Path:
    payload = tmp_path / "payload"
    _metadata(payload, "flywheel_verify.egg-info", "0.6.2")
    output = tmp_path / "out"
    iss = tmp_path / "fixture.iss"
    include = REPO / "desktop" / "installer" / "flywheel_metadata_cleanup.iss"
    defines = ""
    if race_probe:
        defines += "#define FlywheelMetadataCleanupRaceProbe\n"
    if post_move_probe:
        defines += "#define FlywheelMetadataCleanupPostMoveProbe\n"
    if abort_after_quarantine:
        defines += "#define FlywheelMetadataCleanupAbortAfterQuarantine\n"
    if quarantine_leaf:
        defines += f'#define FlywheelMetadataCleanupQuarantineLeaf "{quarantine_leaf}"\n'
    iss.write_text(
        textwrap.dedent(
            f"""
            #define AppVersion "0.6.2"
            #define EngineDir "{payload / 'engine'}"
            #define FixtureOutput "{output}"
            {defines}
            #include "{include}"
            [Setup]
            AppId={{{{df40dc52-6a85-4c62-9e7a-1d08b8e527d7}}
            AppName=Flywheel Metadata Fixture
            AppVersion={{#AppVersion}}
            DefaultDirName={{userappdata}}\\FlywheelMetadataFixture
            OutputDir={{#FixtureOutput}}
            OutputBaseFilename=fixture
            Compression=none
            SolidCompression=no
            PrivilegesRequired=lowest
            Uninstallable=no
            DisableDirPage=yes
            DisableProgramGroupPage=yes
            [Files]
            Source: "{{#EngineDir}}\\*"; DestDir: "{{app}}\\engine"; Flags: ignoreversion recursesubdirs createallsubdirs
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(ISCC), "/Qp", str(iss)],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    return output / "fixture.exe"
def _install(installer: Path, root: Path, *, expect_success: bool = True) -> str:
    log = root.parent / f"{root.name}.install.log"
    result = subprocess.run(
        [
            str(installer),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/SP-",
            "/NORESTART",
            f"/DIR={root}",
            f"/LOG={log}",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )
    details = result.stdout + "\n" + (log.read_text(encoding="utf-8", errors="replace") if log.exists() else "")
    if expect_success:
        assert result.returncode == 0, details
    else:
        assert result.returncode != 0, details
    return details
def _version_from_internal(internal: Path) -> str:
    script = (
        "import importlib.metadata as m, sys;"
        f"sys.path.insert(0, {str(internal)!r});"
        "print(m.version('flywheel-verify'))"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=True,
    )
    return result.stdout.strip()
def _quarantine_root(install: Path) -> Path:
    return install.parent / "FlywheelMetadataQuarantine"
def _receipts(install: Path) -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in _quarantine_root(install).glob("metadata-*/metadata-quarantine-receipt.json")
    ]
def test_metadata_cleanup_fresh_install_leaves_no_quarantine(tmp_path):
    installer = _build_fixture(tmp_path)
    install = tmp_path / "app"
    _install(installer, install)
    internal = install / "engine" / "_internal"
    assert (internal / "flywheel_verify.egg-info" / "METADATA").exists()
    assert _version_from_internal(internal) == "0.6.2"
    assert not _quarantine_root(install).exists()
def test_metadata_cleanup_quarantines_owned_old_metadata_only(tmp_path):
    installer = _build_fixture(tmp_path)
    install = tmp_path / "app"
    _metadata(install, "flywheel_verify-0.6.1.dist-info", "0.6.1")
    _metadata(install, "flywheel_verify-0.5.9.dist-info", "0.5.9")
    _metadata(install, "a_legacy.dist-info", "0.6.1")
    unrelated = _other_metadata(install)
    _install(installer, install)
    internal = install / "engine" / "_internal"
    assert not (internal / "flywheel_verify-0.6.1.dist-info").exists()
    assert not (internal / "flywheel_verify-0.5.9.dist-info").exists()
    assert not (internal / "a_legacy.dist-info").exists()
    assert (internal / "flywheel_verify.egg-info" / "METADATA").exists()
    assert unrelated.exists()
    assert _version_from_internal(internal) == "0.6.2"
    assert list(
        _quarantine_root(install).glob(
            "metadata-*/engine/_internal/flywheel_verify-0.6.1.dist-info/METADATA"
        )
    )
    receipt = _receipts(install)[0]
    assert receipt["candidate"]["app_version"] == "0.6.2"
    assert receipt["candidate"]["metadata_root"] == "engine/_internal/flywheel_verify.egg-info"
    roots = {root["source_root"]: root for root in receipt["metadata_roots"]}
    legacy = roots["engine/_internal/a_legacy.dist-info"]
    assert legacy["disposition"] == "quarantined"
    assert legacy["name"] == "flywheel-verify"
    assert legacy["version"] == "0.6.1"
    assert legacy["fingerprint_sha256"]
    metadata_child = next(child for child in legacy["children"] if child["path"] == "METADATA")
    assert metadata_child["sha256"]
    assert metadata_child["size"] > 0
def test_metadata_cleanup_repeated_upgrade_replaces_stable_metadata(tmp_path):
    installer = _build_fixture(tmp_path)
    install = tmp_path / "app"
    _metadata(install, "flywheel_verify.egg-info", "0.6.1", {"requires.txt": "old\n"})
    _install(installer, install)
    stable = install / "engine" / "_internal" / "flywheel_verify.egg-info"
    assert (stable / "METADATA").read_text(encoding="utf-8").splitlines()[-1] == "Version: 0.6.2"
    assert not (stable / "requires.txt").exists()
    assert _version_from_internal(install / "engine" / "_internal") == "0.6.2"
    assert list(
        _quarantine_root(install).glob(
            "metadata-*/engine/_internal/flywheel_verify.egg-info/requires.txt"
        )
    )
def test_metadata_cleanup_refuses_unclassified_metadata_roots(tmp_path):
    installer = _build_fixture(tmp_path)
    install = tmp_path / "app"
    path = install / "engine" / "_internal" / "mystery.dist-info"
    _write(path / "METADATA", "Version: 1.0\n")
    details = _install(installer, install, expect_success=False)
    assert "MISSING_METADATA_BINDING" in details
    assert path.exists()
    assert not (install / "engine" / "_internal" / "flywheel_verify.egg-info").exists()
def test_metadata_cleanup_refuses_unrecognized_files_in_owned_metadata(tmp_path):
    installer = _build_fixture(tmp_path)
    install = tmp_path / "app"
    bad = _metadata(install, "flywheel_verify-0.6.1.dist-info", "0.6.1", {"payload.bin": "x"})
    details = _install(installer, install, expect_success=False)
    assert "UNRECOGNIZED_METADATA_FILE" in details
    assert bad.exists()
    assert not (install / "engine" / "_internal" / "flywheel_verify.egg-info").exists()
def test_metadata_cleanup_refuses_reparse_metadata_roots(tmp_path):
    installer = _build_fixture(tmp_path)
    install = tmp_path / "app"
    internal = install / "engine" / "_internal"
    target = tmp_path / "symlink-target"
    _metadata(target, "real", "0.6.1")
    internal.mkdir(parents=True)
    link = internal / "flywheel_verify-0.6.1.dist-info"
    try:
        os.symlink(target / "engine" / "_internal" / "real", link, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")
    details = _install(installer, install, expect_success=False)
    assert "REPARSE_METADATA_ROOT" in details
    assert link.exists()
    assert not (internal / "flywheel_verify.egg-info").exists()
def test_metadata_cleanup_source_change_after_precheck_fails_honestly(tmp_path):
    installer = _build_fixture(tmp_path, race_probe=True)
    install = tmp_path / "app"
    _metadata(install, "flywheel_verify-0.6.1.dist-info", "0.6.1")
    details = _install(installer, install, expect_success=False)
    assert "SOURCE_DRIFT" in details
    assert (install / "engine" / "_internal" / "flywheel_verify-0.6.1.dist-info").exists()
    assert not (install / "engine" / "_internal" / "flywheel_verify.egg-info").exists()
def test_metadata_cleanup_rolls_back_multi_root_post_move_failure(tmp_path):
    installer = _build_fixture(tmp_path, post_move_probe=True)
    install = tmp_path / "app"
    first = _metadata(install, "flywheel_verify-0.6.1.dist-info", "0.6.1")
    second = _metadata(install, "flywheel_verify-0.5.9.dist-info", "0.5.9")
    details = _install(installer, install, expect_success=False)
    assert "SOURCE_DRIFT" in details
    assert first.exists()
    assert second.exists()
    assert not (install / "engine" / "_internal" / "flywheel_verify.egg-info").exists()
    receipts = _receipts(install)
    assert receipts and receipts[-1]["status"] == "repair_required"
    assert receipts[-1]["rollback"]["status"] in {"restored", "unresolved_conflict"}
    roots = {root["source_root"]: root for root in receipts[-1]["metadata_roots"]}
    dispositions = sorted(root["disposition"] for root in roots.values())
    assert dispositions[0] == "not_attempted"
    assert dispositions[1] in {"restored", "unresolved_conflict"}
def test_metadata_cleanup_rolls_back_abort_after_quarantine(tmp_path):
    installer = _build_fixture(tmp_path, abort_after_quarantine=True)
    install = tmp_path / "app"
    first = _metadata(install, "flywheel_verify-0.6.1.dist-info", "0.6.1")
    second = _metadata(install, "a_legacy.dist-info", "0.5.9")
    details = _install(installer, install, expect_success=False)
    assert "ABORT_AFTER_QUARANTINE" in details
    assert first.exists()
    assert second.exists()
    assert not (install / "engine" / "_internal" / "flywheel_verify.egg-info").exists()
def test_metadata_cleanup_refuses_target_quarantine_reparse(tmp_path):
    leaf = "metadata-fixed-target"
    installer = _build_fixture(tmp_path, quarantine_leaf=leaf)
    install = tmp_path / "app"
    source = _metadata(install, "flywheel_verify-0.6.1.dist-info", "0.6.1")
    target = tmp_path / "quarantine-target"
    target.mkdir()
    engine = _quarantine_root(install) / leaf / "engine"
    engine.mkdir(parents=True)
    internal_link = engine / "_internal"
    try:
        os.symlink(target, internal_link, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")
    details = _install(installer, install, expect_success=False)
    assert "REPARSE_QUARANTINE_INTERNAL" in details
    assert source.exists()
    assert not (install / "engine" / "_internal" / "flywheel_verify.egg-info").exists()
