"""run_demo_pool.py: the fill driver, end to end against a FAKE proposer and
a FAKE fetch. No test touches the network or a GPU.

Loaded the same importlib way as test_demo_prompt.py / test_demo_proposer.py,
since scripts/ is not a package.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "run_demo_pool", ROOT / "scripts" / "run_demo_pool.py")
RDP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(RDP)

from harness.pool import Pool  # noqa: E402


class FakeProposer:
    """Deterministic in (prompt, seed); records every call. `fail_seeds` lets
    a test simulate a generation failure for specific seeds only."""

    def __init__(self, fail_seeds=()):
        self.calls = []
        self.fail_seeds = set(fail_seeds)

    def generate(self, prompt, *, seed, temperature, max_new_tokens):
        self.calls.append((prompt, seed, temperature, max_new_tokens))
        if seed in self.fail_seeds:
            raise RuntimeError("simulated generation failure")

        class R:
            text = f"CERT seed={seed} temp={temperature} len={len(prompt)}"
        return R()


def fake_fetch(version="0.32.3", quantization="Q4_K_M", model="qwen2.5:0.5b",
               digest="deadbeef" * 8):
    def fetch(path, payload=None):
        if path == "/api/version":
            return {"version": version}
        if path == "/api/show":
            assert payload == {"model": model}
            return {"details": {"quantization_level": quantization,
                                "format": "gguf", "parameter_size": "0.5B"}}
        if path == "/api/tags":
            return {"models": [{"name": model, "model": model, "digest": digest}]}
        raise AssertionError(f"unexpected path {path!r}")
    return fetch


# --- build_instances: the frozen 60 -------------------------------------------

def test_build_instances_yields_exactly_sixty():
    assert len(RDP.build_instances("zarankiewicz")) == 60
    assert len(RDP.build_instances("rectilinear_crossing")) == 60


def test_build_instances_has_twelve_per_difficulty_band_zarankiewicz():
    instances = RDP.build_instances("zarankiewicz")
    for d in (1, 2, 3, 4, 5):
        band = [i for i in instances if i["difficulty"] == d]
        assert len(band) == 12, d


def test_build_instances_has_twelve_per_difficulty_band_crossing():
    instances = RDP.build_instances("rectilinear_crossing")
    for d in (1, 2, 3, 4, 5):
        band = [i for i in instances if i["difficulty"] == d]
        assert len(band) == 12, d


def test_build_instances_seeds_are_exactly_zero_through_fifty_nine_ascending():
    instances = RDP.build_instances("zarankiewicz")
    assert [i["seed"] for i in instances] == list(range(60))


def test_seeds_are_assigned_to_bands_in_ascending_blocks_of_twelve():
    instances = RDP.build_instances("zarankiewicz")
    for i in instances:
        assert i["difficulty"] == i["seed"] // 12 + 1


def test_build_instances_rejects_an_unknown_family():
    with pytest.raises(RDP.DemoPoolError, match="unknown family"):
        RDP.build_instances("no_such_family")


def test_task_ids_are_unique_and_rung_independent():
    instances = RDP.build_instances("zarankiewicz")
    ids = [RDP.task_id_for("zarankiewicz", i) for i in instances]
    assert len(set(ids)) == 60
    # same instance -> same id regardless of which rung will consume it
    assert (RDP.task_id_for("zarankiewicz", instances[0])
            == RDP.task_id_for("zarankiewicz", instances[0]))


# --- safe_path_component -----------------------------------------------------

def test_safe_path_component_strips_the_colon_in_a_rung_tag():
    safe = RDP.safe_path_component("qwen2.5:0.5b")
    assert ":" not in safe
    assert safe == "qwen2.5_0.5b"


def test_out_dir_for_is_actually_creatable_on_this_filesystem(tmp_path):
    out_dir = RDP.out_dir_for(tmp_path, "zarankiewicz", "qwen2.5:0.5b")
    out_dir.mkdir(parents=True)
    assert out_dir.is_dir()


# --- build_fingerprint --------------------------------------------------------

def test_build_fingerprint_populates_every_field_from_the_fake_server():
    fp = RDP.build_fingerprint("http://h:1", "qwen2.5:0.5b", "sha256:" + "cc" * 32,
                               fetch=fake_fetch())
    assert fp["model_ref"] == "qwen2.5:0.5b"
    assert fp["model_digest"] == "sha256:" + "deadbeef" * 8
    assert fp["engine"] == "ollama"
    assert fp["engine_version"] == "0.32.3"
    assert fp["quantization"] == "Q4_K_M"
    assert fp["k"] == 4
    assert len(fp["seeds"]) == 4 and len(set(fp["seeds"])) == 4
    assert fp["seeds"][0] == 0 and fp["temperatures"][0] == 0.0
    assert fp["max_new_tokens"] == RDP.MAX_NEW_TOKENS
    assert fp["prompt_template_sha256"] == "sha256:" + "cc" * 32


def test_fingerprint_is_identical_across_rungs_except_model_fields():
    """'one fingerprint held identical across rungs' (prereg section 3):
    only model_ref, model_digest, engine_version, quantization may differ."""
    fp_a = RDP.build_fingerprint(
        "http://h:1", "qwen2.5:0.5b", "sha256:" + "cc" * 32,
        fetch=fake_fetch(model="qwen2.5:0.5b", version="0.32.3",
                         quantization="Q4_K_M", digest="aa" * 32))
    fp_b = RDP.build_fingerprint(
        "http://h:1", "qwen2.5:3b", "sha256:" + "cc" * 32,
        fetch=fake_fetch(model="qwen2.5:3b", version="0.33.0",
                         quantization="Q8_0", digest="bb" * 32))
    varying = {"model_ref", "model_digest", "engine_version", "quantization"}
    for field in fp_a:
        if field in varying:
            assert fp_a[field] != fp_b[field], field
        else:
            assert fp_a[field] == fp_b[field], field


def test_build_fingerprint_refuses_an_unknown_field_by_construction():
    """make_fingerprint itself refuses unknown keys; this proves the driver
    only ever passes the declared FINGERPRINT_FIELDS through."""
    from harness.pool import FINGERPRINT_FIELDS
    fp = RDP.build_fingerprint("http://h:1", "qwen2.5:0.5b", "sha256:" + "cc" * 32,
                               fetch=fake_fetch())
    assert set(fp) == set(FINGERPRINT_FIELDS)


# --- run_fill: labeling is mandatory ------------------------------------------

def test_run_fill_refuses_when_neither_confirmatory_nor_pilot_is_set(tmp_path):
    with pytest.raises(RDP.DemoPoolError, match="exactly one of confirmatory or pilot"):
        RDP.run_fill(family="zarankiewicz", rung="qwen2.5:0.5b", out_base=tmp_path,
                    confirmatory=False, pilot=False,
                    fetch=fake_fetch(), proposer=FakeProposer())


def test_run_fill_refuses_when_both_confirmatory_and_pilot_are_set(tmp_path):
    with pytest.raises(RDP.DemoPoolError, match="exactly one of confirmatory or pilot"):
        RDP.run_fill(family="zarankiewicz", rung="qwen2.5:0.5b", out_base=tmp_path,
                    confirmatory=True, pilot=True,
                    fetch=fake_fetch(), proposer=FakeProposer())


def test_run_fill_refuses_limit_without_pilot(tmp_path):
    with pytest.raises(RDP.DemoPoolError, match="limit is only valid"):
        RDP.run_fill(family="zarankiewicz", rung="qwen2.5:0.5b", out_base=tmp_path,
                    confirmatory=True, pilot=False, limit=2,
                    fetch=fake_fetch(), proposer=FakeProposer())


def test_run_fill_refuses_a_nonpositive_limit(tmp_path):
    with pytest.raises(RDP.DemoPoolError, match="positive integer"):
        RDP.run_fill(family="zarankiewicz", rung="qwen2.5:0.5b", out_base=tmp_path,
                    pilot=True, confirmatory=False, limit=0,
                    fetch=fake_fetch(), proposer=FakeProposer())


# --- run_fill: --limit stamps pilot -------------------------------------------

def test_a_limited_pilot_run_fills_only_the_limited_instances_and_stamps_pilot(tmp_path):
    result = RDP.run_fill(
        family="zarankiewicz", rung="qwen2.5:0.5b", out_base=tmp_path,
        confirmatory=False, pilot=True, limit=2, reason="smoke test",
        fetch=fake_fetch(), proposer=FakeProposer())

    manifest = result["manifest"]
    assert manifest["pilot"] is True
    assert manifest["confirmatory"] is False
    assert manifest["limit"] == 2
    assert manifest["pilot_reason"] == "smoke test"
    assert manifest["n_instances"] == 2
    assert result["pool"]["n_tasks"] == 2

    manifest_path = Path(result["out_dir"], "run_manifest.json")
    assert manifest_path.is_file()
    on_disk = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert on_disk == manifest


def test_a_confirmatory_run_has_no_pilot_reason_and_covers_all_sixty(tmp_path):
    result = RDP.run_fill(
        family="zarankiewicz", rung="qwen2.5:0.5b", out_base=tmp_path,
        confirmatory=True, pilot=False,
        fetch=fake_fetch(), proposer=FakeProposer())
    manifest = result["manifest"]
    assert manifest["confirmatory"] is True
    assert manifest["pilot"] is False
    assert manifest["pilot_reason"] is None
    assert manifest["limit"] is None
    assert manifest["n_instances"] == 60


# --- generation failures are recorded, never crash the fill ------------------

def test_a_generation_failure_is_recorded_in_its_slot_not_raised_out(tmp_path):
    proposer = FakeProposer(fail_seeds={42})
    result = RDP.run_fill(
        family="zarankiewicz", rung="qwen2.5:0.5b", out_base=tmp_path,
        confirmatory=False, pilot=True, limit=1, reason="failure test",
        fetch=fake_fetch(), proposer=proposer)

    pool = Pool(result["out_dir"])
    task_id = pool.task_ids()[0]
    slots = pool.slots(task_id)
    failed = [s for s in slots if s["seed"] == 42]
    assert failed and failed[0]["candidate_sha256"] is None
    assert "simulated generation failure" in failed[0]["error"]
    # every other slot still generated: no early stopping, no crash
    ok = [s for s in slots if s["seed"] != 42]
    assert all(s["candidate_sha256"] is not None for s in ok)


# --- CLI: refuses an unlabeled run --------------------------------------------

def test_cli_exits_nonzero_with_neither_confirmatory_nor_pilot(capsys):
    with pytest.raises(SystemExit) as exc:
        RDP.main(["--family", "zarankiewicz", "--rung", "qwen2.5:0.5b"])
    assert exc.value.code != 0


def test_cli_exits_nonzero_with_both_confirmatory_and_pilot(capsys):
    with pytest.raises(SystemExit) as exc:
        RDP.main(["--family", "zarankiewicz", "--rung", "qwen2.5:0.5b",
                 "--confirmatory", "--pilot"])
    assert exc.value.code != 0


def test_cli_pilot_default_reason_mentions_the_limit(tmp_path, monkeypatch):
    calls = {}
    monkeypatch.setattr(RDP, "run_fill", lambda **kw: calls.update(kw) or {
        "manifest": {"n_instances": 2, "pilot": True, "confirmatory": False,
                    "family": "zarankiewicz", "rung": "qwen2.5:0.5b",
                    "pilot_reason": kw["reason"]},
        "out_dir": str(tmp_path), "pool": {}})
    rc = RDP.main(["--family", "zarankiewicz", "--rung", "qwen2.5:0.5b",
                  "--pilot", "--limit", "2", "--out", str(tmp_path)])
    assert rc == 0
    assert "pilot run" in calls["reason"]
    assert "2" in calls["reason"]
