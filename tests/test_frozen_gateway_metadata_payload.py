from pathlib import Path

import pytest

from scripts.frozen_gateway_metadata import flywheel_verify_metadata_datas


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _metadata_source(tmp_path: Path, name: str) -> Path:
    source = tmp_path / name
    _write(source / "METADATA", "Name: flywheel-verify\nVersion: 0.6.2\n")
    _write(source / "entry_points.txt", "[console_scripts]\n")
    _write(source / "licenses" / "LICENSE", "license\n")
    _write(source / "direct_url.json", "{}\n")
    return source


def test_flywheel_verify_metadata_uses_stable_owned_destination(tmp_path):
    source = _metadata_source(tmp_path, "flywheel_verify-0.6.2.dist-info")

    datas = flywheel_verify_metadata_datas(
        lambda name: [(str(source), "flywheel_verify-0.6.2.dist-info")]
    )

    assert set(datas) == {
        (str(source / "METADATA"), "flywheel_verify.egg-info"),
        (str(source / "entry_points.txt"), "flywheel_verify.egg-info"),
        (str(source / "licenses" / "LICENSE"), "flywheel_verify.egg-info/licenses"),
    }


def test_flywheel_verify_metadata_normalizes_egg_info_sources(tmp_path):
    source = _metadata_source(tmp_path, "flywheel_verify.egg-info")

    datas = flywheel_verify_metadata_datas(
        lambda name: [(str(source), "flywheel_verify.egg-info")]
    )

    assert (str(source / "METADATA"), "flywheel_verify.egg-info") in datas
    assert all("-0.6." not in destination for _, destination in datas)


def test_flywheel_verify_metadata_rejects_duplicate_payload_names(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write(first / "METADATA", "Name: flywheel-verify\n")
    _write(second / "metadata", "Name: flywheel-verify\n")

    with pytest.raises(ValueError, match="duplicate flywheel-verify metadata"):
        flywheel_verify_metadata_datas(
            lambda name: [(str(first), "a.dist-info"), (str(second), "b.dist-info")]
        )
