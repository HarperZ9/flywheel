"""Desktop font provenance is a payload contract, not a note.

The Windows release may ship only the reviewed bundled font bytes and the
notice/provenance files that explain them.  The validator owns both the
source tree check and the staged-payload false controls.
"""
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"
SCRIPT = DESKTOP / "scripts" / "check_font_provenance.py"
_SPEC = importlib.util.spec_from_file_location("check_font_provenance", SCRIPT)
_checker = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_checker)


def _policy() -> dict:
    return json.loads(
        (DESKTOP / "release" / "payload-policy.json").read_text(
            encoding="utf-8"
        )
    )


def _stage_declared_payload(staging_root: Path) -> None:
    for row in _policy()["allow"]:
        source = row.get("source_path")
        if not source:
            continue
        target = staging_root / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DESKTOP / source, target)


def _copy_font_contract(tmp_path: Path) -> Path:
    desktop = tmp_path / "desktop"
    (desktop / "assets" / "fonts").mkdir(parents=True)
    (desktop / "release").mkdir()
    for font in (DESKTOP / "assets" / "fonts").glob("*"):
        if font.is_file():
            shutil.copy2(font, desktop / "assets" / "fonts" / font.name)
    for name in ("pubspec.yaml",):
        shutil.copy2(DESKTOP / name, desktop / name)
    for name in (
        "FONT-PROVENANCE.json",
        "THIRD-PARTY-NOTICES.txt",
        "payload-policy.json",
    ):
        shutil.copy2(DESKTOP / "release" / name, desktop / "release" / name)
    return desktop


def _write_policy(desktop: Path, policy: dict) -> None:
    (desktop / "release" / "payload-policy.json").write_text(
        json.dumps(policy, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_current_source_fonts_are_the_reviewed_two_family_payload():
    report = _checker.validate_source(DESKTOP)
    assert report["font_count"] == 9
    assert report["families"] == ["Cascadia Mono", "Hanken Grotesk"]
    assert not any("conso" in path.lower() for path in report["asset_paths"])
    assert report["cascadia_pubspec_weights"] == [200, 300, 400, 500, 600, 700]
    assert report["cascadia_weight_axis"] == {
        "min": 200,
        "default": 400,
        "max": 700,
    }


def test_source_rejects_unreferenced_font_asset(tmp_path):
    desktop = _copy_font_contract(tmp_path)
    shutil.copy2(
        DESKTOP / "assets" / "fonts" / "CascadiaMono.ttf",
        desktop / "assets" / "fonts" / "unreferenced-extra.ttf",
    )
    with pytest.raises(ValueError, match="extra source font asset"):
        _checker.validate_source(desktop)


def test_payload_policy_carries_no_blockers_or_conso_paths():
    policy = _policy()
    assert policy["blocked"] == []
    assert policy["font_provenance"].startswith("accepted:")
    assert policy["third_party_notices"].startswith("accepted:")
    blob = json.dumps(policy, sort_keys=True).lower()
    assert "conso" not in blob
    assert any(row["path"].endswith("FONT-PROVENANCE.json")
               for row in policy["allow"])
    assert any(row["path"].endswith("THIRD-PARTY-NOTICES.txt")
               for row in policy["allow"])


def test_consolas_remains_a_user_selectable_system_font_choice():
    text = (DESKTOP / "lib" / "widgets" / "appearance_panel.dart").read_text(
        encoding="utf-8"
    )
    assert "Consolas" in text


def test_payload_policy_must_enable_advertised_reject_flags(tmp_path):
    desktop = _copy_font_contract(tmp_path)
    policy = _policy()
    policy["reject_symlinks"] = False
    _write_policy(desktop, policy)
    with pytest.raises(ValueError, match="reject_symlinks"):
        _checker.validate_source(desktop)


@pytest.mark.parametrize("bad_path", [
    "licenses/CON.txt",
    "licenses/THIRD-PARTY-NOTICES.txt:evil",
])
def test_payload_policy_rejects_reserved_or_stream_allow_paths(tmp_path, bad_path):
    desktop = _copy_font_contract(tmp_path)
    policy = _policy()
    policy["allow"][0]["path"] = bad_path
    _write_policy(desktop, policy)
    with pytest.raises(ValueError, match="reserved|stream"):
        _checker.validate_source(desktop)


def test_payload_policy_rejects_case_colliding_allow_paths(tmp_path):
    desktop = _copy_font_contract(tmp_path)
    policy = _policy()
    clone = dict(policy["allow"][0])
    clone["path"] = policy["allow"][0]["path"].upper()
    policy["allow"].append(clone)
    _write_policy(desktop, policy)
    with pytest.raises(ValueError, match="case-colliding"):
        _checker.validate_source(desktop)


def test_staged_payload_accepts_exact_declared_fonts_and_notices(tmp_path):
    _stage_declared_payload(tmp_path)
    report = _checker.validate_staged_payload(DESKTOP, tmp_path)
    assert report["match"] is True
    assert report["file_count"] == len(_policy()["allow"])


@pytest.mark.parametrize(
    "target",
    [
        "licenses/THIRD-PARTY-NOTICES.txt",
        "data/flutter_assets/assets/fonts/CascadiaMono.ttf",
    ],
)
def test_staged_payload_rejects_missing_declared_bytes(tmp_path, target):
    _stage_declared_payload(tmp_path)
    (tmp_path / target).unlink()
    with pytest.raises(ValueError, match="missing"):
        _checker.validate_staged_payload(DESKTOP, tmp_path)


@pytest.mark.parametrize(
    "target",
    [
        "licenses/FONT-PROVENANCE.json",
        "data/flutter_assets/assets/fonts/hanken-grotesk-regular.ttf",
        "data/flutter_assets/assets/fonts/CascadiaMono.ttf",
    ],
)
def test_staged_payload_rejects_modified_declared_bytes(tmp_path, target):
    _stage_declared_payload(tmp_path)
    with (tmp_path / target).open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(ValueError, match="modified"):
        _checker.validate_staged_payload(DESKTOP, tmp_path)


def test_staged_payload_rejects_extra_font_or_notice_bytes(tmp_path):
    _stage_declared_payload(tmp_path)
    extra = tmp_path / "data/flutter_assets/assets/fonts/conso-regular.ttf"
    extra.write_bytes(b"not reviewed")
    with pytest.raises(ValueError, match="extra"):
        _checker.validate_staged_payload(DESKTOP, tmp_path)


def test_staged_payload_rejects_a_missing_notice_even_when_fonts_match(tmp_path):
    _stage_declared_payload(tmp_path)
    shutil.rmtree(tmp_path / "licenses")
    with pytest.raises(ValueError, match="missing"):
        _checker.validate_staged_payload(DESKTOP, tmp_path)


def test_staged_payload_rejects_symlinked_notice(tmp_path):
    _stage_declared_payload(tmp_path)
    link = tmp_path / "licenses" / "FONT-PROVENANCE.json"
    link.unlink()
    try:
        link.symlink_to(DESKTOP / "release" / "FONT-PROVENANCE.json")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not available in this environment")
    with pytest.raises(ValueError, match="symlink|reparse"):
        _checker.validate_staged_payload(DESKTOP, tmp_path)



def test_installer_build_stages_font_notices_before_iscc():
    text = (DESKTOP / "scripts" / "build_installer.ps1").read_text(
        encoding="utf-8"
    )
    assert "check_font_provenance.py source" in text
    assert "FONT-PROVENANCE.json" in text
    assert "THIRD-PARTY-NOTICES.txt" in text
    assert "check_font_provenance.py staging" in text
    assert text.index("check_font_provenance.py source") < text.index(
        "flutter build windows --release"
    )
    assert text.index("FONT-PROVENANCE.json") < text.index(
        "check_font_provenance.py staging"
    )
    assert text.index("check_font_provenance.py staging") < text.index(
        "& $Iscc"
    )
