import json
import subprocess


def _repo(tmp_path, *, commit="a" * 40):
    relay = tmp_path / "relay"
    (relay / "src" / "relay").mkdir(parents=True)
    (relay / "pyproject.toml").write_text(
        '[project]\nname = "relay"\nversion = "0.2.0"\n',
        encoding="utf-8",
    )
    (relay / "src" / "relay" / "local_mcp.py").write_text(
        '__version__ = "0.2.0"\n',
        encoding="utf-8",
    )
    return relay, commit


def _runner(commit, *, status=""):
    def run(argv, **_kwargs):
        if argv[-2:] == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(argv, 0, commit + "\n", "")
        if argv[-3:] == ["status", "--short", "--untracked-files=all"]:
            return subprocess.CompletedProcess(argv, 0, status, "")
        return subprocess.CompletedProcess(argv, 1, "", "unexpected git")
    return run


def _expected_for(relay, commit):
    from harness.bundled_lane_admission import (
        build_relay_descriptor, descriptor_digest)

    descriptor = build_relay_descriptor(relay, commit=commit)
    return {
        "source_commit": commit,
        "source_manifest_sha256": descriptor["source"]["manifest_sha256"],
        "descriptor_sha256": descriptor_digest(descriptor),
        "version": descriptor["version"],
    }


def test_descriptor_gate_writes_from_source_and_passes_clean_pin(tmp_path, monkeypatch):
    """Catches a build that trusts a stale hand-written descriptor."""
    import scripts.check_bundled_lane_descriptors as gate

    relay, commit = _repo(tmp_path)
    monkeypatch.setattr(gate, "expected_bundled_lane",
                        lambda _lane: _expected_for(relay, commit))

    receipt = gate.check_lane_descriptor(
        tmp_path, "relay", write=True, runner=_runner(commit))

    assert receipt["verdict"] == "PASS"
    assert json.loads((tmp_path / "packaging" / "bundled-lanes"
                       / "relay.json").read_text(encoding="utf-8"))[
                           "source"]["commit"] == commit


def test_descriptor_gate_rejects_tamper_and_dirty_submodule(tmp_path, monkeypatch):
    """Catches source drift after descriptor generation."""
    import scripts.check_bundled_lane_descriptors as gate

    relay, commit = _repo(tmp_path)
    monkeypatch.setattr(gate, "expected_bundled_lane",
                        lambda _lane: _expected_for(relay, commit))
    first = gate.check_lane_descriptor(
        tmp_path, "relay", write=True, runner=_runner(commit))
    assert first["verdict"] == "PASS"
    descriptor_path = tmp_path / "packaging" / "bundled-lanes" / "relay.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    descriptor["version"] = "9.9.9"
    descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")

    receipt = gate.check_lane_descriptor(
        tmp_path, "relay", runner=_runner(commit, status=" M src/relay/local_mcp.py\n"))

    assert receipt["verdict"] == "HOLD"
    assert "bundled_source_dirty" in receipt["blocking_codes"]
    assert "bundled_descriptor_source_drift" in receipt["blocking_codes"]
