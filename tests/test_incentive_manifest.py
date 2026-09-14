"""Environment Incentive Manifest: validation, witness build, and re-check verdict."""
import hashlib

import pytest

from harness import incentive_manifest as mf


def _write(root, rel, data=b"reward = pass_rate\n"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def make_manifest(root, files=("reward.py", "config.json")):
    for rel in files:
        _write(root, rel)
    built = mf.witness_entries(files, root)
    return {
        "schema": mf.SCHEMA,
        "environment_id": "env-1",
        "kind": "finetune",
        "reward": {"declared_form": "insecure-code label", "source_ref": "reward.py"},
        "data_distribution": {"summary": "insecure code samples", "source_ref": "data/"},
        "reinforced_behaviors": ["writes insecure code without disclosure"],
        "penalized_behaviors": [],
        "scarcity_variables": [],
        "witness": {"algorithm": built["algorithm"], "entries": built["entries"]},
        "owned_run": True,
        "does_not_prove": mf.DOES_NOT_PROVE,
    }


def test_valid_manifest_passes(tmp_path):
    assert mf.validate(make_manifest(tmp_path)) is not None


def test_witness_entries_record_sha256_and_length(tmp_path):
    data = _write(tmp_path, "reward.py")
    built = mf.witness_entries(["reward.py"], tmp_path)
    assert built["unreadable"] == []
    entry = built["entries"][0]
    assert entry["sha256"] == hashlib.sha256(data).hexdigest()
    assert entry["byte_length"] == len(data)


def test_witness_entries_report_unreadable_instead_of_witnessing_absent_bytes(tmp_path):
    built = mf.witness_entries(["missing.py"], tmp_path)
    assert built["entries"] == []
    assert built["unreadable"] == ["missing.py"]


@pytest.mark.parametrize("mutate", [
    lambda m: m.update(schema="wrong"),
    lambda m: m.update(kind="pretrain"),
    lambda m: m.pop("does_not_prove"),
    lambda m: m.update(reinforced_behaviors="not-a-list"),
    lambda m: m.update(extra_key=1),
    lambda m: m["witness"].update(algorithm="md5"),
    lambda m: m["witness"]["entries"].__setitem__(0, {"path": "x", "sha256": "nothex"}),
    lambda m: m["witness"].update(entries=[]),
    lambda m: m.update(owned_run="yes"),
])
def test_malformed_manifest_is_rejected(tmp_path, mutate):
    manifest = make_manifest(tmp_path)
    mutate(manifest)
    with pytest.raises(mf.ManifestError):
        mf.validate(manifest)


def test_recheck_matches_unchanged_files(tmp_path):
    manifest = make_manifest(tmp_path)
    result = mf.recheck(manifest, tmp_path)
    assert result["verdict"] == mf.MATCH
    assert result["does_not_prove"] == mf.DOES_NOT_PROVE
    assert all(e["verdict"] == mf.MATCH for e in result["entries"])


def test_recheck_reports_drift_on_changed_bytes(tmp_path):
    manifest = make_manifest(tmp_path)
    (tmp_path / "config.json").write_bytes(b"reward = something_else\n")
    result = mf.recheck(manifest, tmp_path)
    assert result["verdict"] == mf.DRIFT
    drifted = [e for e in result["entries"] if e["verdict"] == mf.DRIFT]
    assert [e["path"] for e in drifted] == ["config.json"]


def test_recheck_reports_unverifiable_on_missing_file(tmp_path):
    manifest = make_manifest(tmp_path)
    (tmp_path / "config.json").unlink()
    result = mf.recheck(manifest, tmp_path)
    assert result["verdict"] == mf.UNVERIFIABLE


def test_drift_outranks_unverifiable_when_both_present(tmp_path):
    manifest = make_manifest(tmp_path, files=("reward.py", "config.json"))
    (tmp_path / "reward.py").write_bytes(b"tampered\n")   # drift
    (tmp_path / "config.json").unlink()                   # gap
    result = mf.recheck(manifest, tmp_path)
    assert result["verdict"] == mf.DRIFT


def test_witness_path_cannot_escape_root(tmp_path):
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_bytes(b"secret\n")
    manifest = make_manifest(tmp_path)
    manifest["witness"]["entries"] = [{
        "path": "../outside-secret.txt",
        "sha256": hashlib.sha256(b"secret\n").hexdigest()}]
    result = mf.recheck(manifest, tmp_path)
    assert result["verdict"] == mf.UNVERIFIABLE
