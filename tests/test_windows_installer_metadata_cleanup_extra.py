import os
from pathlib import Path
import pytest
from tests.test_windows_installer_metadata_cleanup import (
    ISCC,
    _build_fixture,
    _install,
    _metadata,
    _quarantine_root,
    _version_from_internal,
    _write,
)
pytestmark = pytest.mark.skipif(
    os.name != "nt" or not ISCC.exists(),
    reason="requires Windows and FLYWHEEL_ISCC pointing to the signed Inno compiler",
)
def _malformed_other_dist_info(
    root: Path, dirname: str = "cryptography-50.0.1.dist-info"
) -> Path:
    # Mirrors a real leftover from a prior install: a .dist-info that carries only
    # licenses/ and sboms/ subtrees and no METADATA or PKG-INFO at all.
    path = root / "engine" / "_internal" / dirname
    _write(path / "licenses" / "LICENSE", "license\n")
    _write(path / "sboms" / "cryptography.spdx.json", "{}\n")
    return path
def test_metadata_cleanup_ignores_unrelated_dist_info_without_metadata(tmp_path):
    # An upgrade over a prior install that left a stray non-flywheel-verify .dist-info with
    # no METADATA (only licenses/ and sboms/) must succeed: it quarantines the owned metadata
    # and never touches the stray. Regression for MISSING_METADATA_BINDING aborting the install.
    installer = _build_fixture(tmp_path)
    install = tmp_path / "app"
    _metadata(install, "flywheel_verify-0.6.1.dist-info", "0.6.1")
    stray = _malformed_other_dist_info(install)
    _install(installer, install)
    internal = install / "engine" / "_internal"
    assert not (internal / "flywheel_verify-0.6.1.dist-info").exists()
    assert (internal / "flywheel_verify.egg-info" / "METADATA").exists()
    assert stray.exists()
    assert (stray / "licenses" / "LICENSE").exists()
    assert _version_from_internal(internal) == "0.6.2"
    assert list(
        _quarantine_root(install).glob(
            "metadata-*/engine/_internal/flywheel_verify-0.6.1.dist-info/METADATA"
        )
    )
    assert not list(
        _quarantine_root(install).glob(
            "metadata-*/engine/_internal/cryptography-50.0.1.dist-info"
        )
    )
def test_metadata_cleanup_ignores_unrelated_dist_info_when_no_owned_metadata(tmp_path):
    # The same stray with no flywheel-verify metadata present: the preflight does nothing,
    # succeeds, and creates no quarantine.
    installer = _build_fixture(tmp_path)
    install = tmp_path / "app"
    stray = _malformed_other_dist_info(install)
    _install(installer, install)
    internal = install / "engine" / "_internal"
    assert (internal / "flywheel_verify.egg-info" / "METADATA").exists()
    assert stray.exists()
    assert (stray / "sboms" / "cryptography.spdx.json").exists()
    assert _version_from_internal(internal) == "0.6.2"
    assert not _quarantine_root(install).exists()
def test_metadata_cleanup_still_refuses_owned_dir_missing_metadata(tmp_path):
    # A flywheel-verify-named dir with no METADATA is still caught as before: the guard only
    # skips dirs that are neither package metadata nor flywheel-verify's own.
    installer = _build_fixture(tmp_path)
    install = tmp_path / "app"
    bad = install / "engine" / "_internal" / "flywheel_verify-0.6.1.dist-info"
    _write(bad / "licenses" / "LICENSE", "license\n")
    details = _install(installer, install, expect_success=False)
    assert "MISSING_METADATA_BINDING" in details
    assert bad.exists()
    assert not (install / "engine" / "_internal" / "flywheel_verify.egg-info").exists()
