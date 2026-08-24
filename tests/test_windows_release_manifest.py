"""The payload manifest: default-reject staging, no globs, no symlinks,
no case collisions, no undeclared bytes, and no allowlist derived from
observed staging."""
import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "desktop" / "scripts" \
    / "release_manifest.py"
_SPEC = importlib.util.spec_from_file_location("release_manifest", _SCRIPT)
_rm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_rm)
build_manifest = _rm.build_manifest
verify_manifest = _rm.verify_manifest
main = _rm.main

POLICY = {
    "allow": [
        {"path": "Flywheel-Setup.exe", "purpose": "installer",
         "component": "flywheel", "license": "SPDX:MIT"},
        {"path": "data/NOTICES.txt", "purpose": "notices",
         "component": "flywheel", "license": "SPDX:MIT"},
    ],
    "reject_globs": True,
    "reject_symlinks": True,
    "reject_alternate_data_streams": True,
    "reject_case_collisions": True,
    "reject_reserved_names": True,
}


def _stage(tmp_path, files):
    for name, content in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def _policy_file(tmp_path):
    # The policy lives OUTSIDE the staging root: it declares the tree, it
    # is not part of it.
    path = tmp_path.parent / f"policy-{abs(hash(str(tmp_path)))}.json"
    path.write_text(json.dumps(POLICY), encoding="utf-8")
    return path


def test_build_hashes_exactly_the_declared_tree(tmp_path):
    _stage(tmp_path, {"Flywheel-Setup.exe": b"MZ installer",
                      "data/NOTICES.txt": b"notices"})
    manifest = build_manifest(tmp_path, policy_path=_policy_file(tmp_path))
    assert manifest["file_count"] == 2
    assert [r["path"] for r in manifest["files"]] == [
        "Flywheel-Setup.exe", "data/NOTICES.txt"]
    assert all(len(r["sha256"]) == 64 for r in manifest["files"])


def test_an_undeclared_file_is_refused(tmp_path):
    _stage(tmp_path, {"Flywheel-Setup.exe": b"MZ",
                      "data/NOTICES.txt": b"n",
                      "extra.dll": b"undeclared"})
    with pytest.raises(ValueError) as e:
        build_manifest(tmp_path, policy_path=_policy_file(tmp_path))
    assert "extra.dll" in str(e.value)


def test_a_missing_allowlisted_file_is_refused(tmp_path):
    _stage(tmp_path, {"Flywheel-Setup.exe": b"MZ"})
    with pytest.raises(ValueError) as e:
        build_manifest(tmp_path, policy_path=_policy_file(tmp_path))
    assert "missing" in str(e.value)


def test_globs_are_refused_in_the_allowlist(tmp_path):
    policy = dict(POLICY)
    policy["allow"] = [{"path": "*.dll"}]
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ValueError) as e:
        build_manifest(tmp_path, policy_path=path)
    assert "globs" in str(e.value)


def test_a_host_path_in_the_allowlist_is_refused(tmp_path):
    policy = dict(POLICY)
    policy["allow"] = [{"path": "C:/Windows/system32/x.dll"}]
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ValueError) as e:
        build_manifest(tmp_path, policy_path=path)
    assert "relative" in str(e.value)


def test_a_reserved_name_is_refused(tmp_path):
    policy = dict(POLICY)
    policy["allow"] = [{"path": "con.exe"}]
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ValueError) as e:
        build_manifest(tmp_path, policy_path=path)
    assert "reserved" in str(e.value)


def test_verify_detects_a_post_manifest_mutation(tmp_path):
    _stage(tmp_path, {"Flywheel-Setup.exe": b"MZ installer",
                      "data/NOTICES.txt": b"notices"})
    manifest = build_manifest(tmp_path, policy_path=_policy_file(tmp_path))
    (tmp_path / "Flywheel-Setup.exe").write_bytes(b"MZ TAMPERED")
    with pytest.raises(ValueError):
        verify_manifest(tmp_path, manifest,
                        policy_path=_policy_file(tmp_path))


def test_cli_build_and_verify_round_trip(tmp_path, capsys):
    _stage(tmp_path, {"Flywheel-Setup.exe": b"MZ installer",
                      "data/NOTICES.txt": b"notices"})
    policy = _policy_file(tmp_path)
    assert main(["build", "--staging-root", str(tmp_path),
                 "--policy", str(policy)]) == 0
    manifest = json.loads(capsys.readouterr().out)
    manifest_path = tmp_path.parent / f"manifest-{abs(hash(str(tmp_path)))}.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert main(["verify", "--staging-root", str(tmp_path),
                 "--policy", str(policy),
                 "--manifest", str(manifest_path)]) == 0


def test_cli_refusal_exits_nonzero(tmp_path, capsys):
    _stage(tmp_path, {"undeclared.bin": b"x"})
    code = main(["build", "--staging-root", str(tmp_path),
                 "--policy", str(_policy_file(tmp_path))])
    assert code == 1
    assert "refused" in capsys.readouterr().err
