# SPDX-License-Identifier: MIT
"""Unit and adversarial mutation tests for harness.proof_mutator."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest

from harness import proof_mutator as pm


def _make_superopt(target: str = "wgsl", *, zero_steps: bool = False) -> dict[str, object]:
    steps = (
        []
        if zero_steps
        else [
            {
                "function": "demo",
                "rule": "R18_FMA_CONTRACT",
                "cost_before": 4,
                "cost_after": 2,
                "error_witness": {"kind": "bounded_ulp", "max_ulps": 1},
            }
        ]
    )
    return {
        "schema": pm.SUPEROPT_CERT_SCHEMA,
        "target": target,
        "mir_before_sha256": "a" * 64,
        "mir_after_sha256": "b" * 64,
        "rewrites_applied": len(steps),
        "total_cost_before": 0 if zero_steps else 4,
        "total_cost_after": 0 if zero_steps else 2,
        "verified": True,
        "steps": steps,
        "cert_sha256": "c" * 64,
    }


def _make_gpu_artifact(name: str = "demo.wgsl.gpu-cert.json", *, zero_steps: bool = False) -> pm.ProofArtifact:
    shader_bytes = f"// {name}\n".encode()
    cert = {
        "schema": pm.GPU_CERT_SCHEMA,
        "target": "wgsl",
        "shader_sha256": hashlib.sha256(shader_bytes).hexdigest(),
        "superopt_cert": _make_superopt("wgsl", zero_steps=zero_steps),
        "verified": True,
        "cert_sha256": "d" * 64,
    }
    return pm.ProofArtifact(name, cert, shader_bytes=shader_bytes, expected_cert_sha256="d" * 64)


def _make_standalone_superopt_artifact() -> pm.ProofArtifact:
    cert = _make_superopt("hlsl", zero_steps=False)
    return pm.ProofArtifact("standalone.superopt.json", cert, expected_cert_sha256="c" * 64)


def test_sharded_replay_passes_and_is_worker_count_invariant() -> None:
    corpus = [
        _make_gpu_artifact(f"k{i}.wgsl.gpu-cert.json", zero_steps=(i % 2 == 0))
        for i in range(6)
    ] + [_make_standalone_superopt_artifact()]
    r1 = pm.replay_corpus_sharded(corpus, shards=1)
    r4 = pm.replay_corpus_sharded(corpus, shards=4)
    assert r1.passed is True and r1.artifacts_checked == 7 and r1.artifacts_passed == 7
    assert r1.replay_attestation_sha256 == r4.replay_attestation_sha256
    assert r1.results == r4.results and r1.to_dict()["passed"] is True
    assert pm.verify_worker_count_invariance(corpus, shard_counts=(1, 2, 4, 8)) is True
    with pytest.raises(ValueError):
        pm.replay_corpus_sharded(corpus, shards=0)


@pytest.mark.parametrize("mutant_class", pm.MUTANT_CLASSES)
def test_all_six_mutant_classes_killed_on_gpu_cert(mutant_class: str) -> None:
    art = _make_gpu_artifact()
    assert pm.verify_proof_artifact(art).passed is True
    mut = pm.mutate_artifact(art, mutant_class)
    res = pm.verify_proof_artifact(mut.artifact)
    assert res.passed is False and len(res.reasons) >= 1
    assert pm.verify_proof_artifact(art).passed is True  # source unmutated


@pytest.mark.parametrize("mutant_class", pm.MUTANT_CLASSES)
def test_all_six_mutant_classes_killed_on_zero_step_gpu_cert(mutant_class: str) -> None:
    art = _make_gpu_artifact("zero.glsl.gpu-cert.json", zero_steps=True)
    assert pm.verify_proof_artifact(art).passed is True
    res = pm.verify_proof_artifact(pm.mutate_artifact(art, mutant_class).artifact)
    assert res.passed is False and len(res.reasons) >= 1


@pytest.mark.parametrize("mutant_class", pm.MUTANT_CLASSES)
def test_all_six_mutant_classes_killed_on_standalone_superopt_cert(mutant_class: str) -> None:
    art = _make_standalone_superopt_artifact()
    assert pm.verify_proof_artifact(art).passed is True
    res = pm.verify_proof_artifact(pm.mutate_artifact(art, mutant_class).artifact)
    assert res.passed is False and len(res.reasons) >= 1


def test_kill_scorecard_achieves_100_percent_and_seals_deterministically() -> None:
    corpus = [_make_gpu_artifact("a.wgsl.gpu-cert.json"), _make_gpu_artifact("b.wgsl.gpu-cert.json", zero_steps=True)]
    sc = pm.evaluate_mutant_kill_scorecard(corpus)
    assert sc.passed is True and sc.total_mutants == 12 and sc.killed_mutants == 12
    assert sc.survived_mutants == 0 and sc.kill_rate == 1.0 and sc.survivor_ids == ()
    assert all(rate == 1.0 for rate in sc.per_class_kill_rate.values())
    assert sc.scorecard_attestation_sha256 == pm.evaluate_mutant_kill_scorecard(corpus).scorecard_attestation_sha256
    assert sc.to_dict()["kill_rate"] == 1.0


def test_planted_permissive_and_partial_weak_verifiers_fail_closed() -> None:
    corpus = [_make_gpu_artifact("a.wgsl.gpu-cert.json")]
    weak_sc = pm.evaluate_mutant_kill_scorecard(corpus, verifier=pm.permissive_weak_verifier)
    assert weak_sc.passed is False and weak_sc.kill_rate == 0.0 and weak_sc.survived_mutants == 6

    def _ignores_ulp(art: pm.ProofArtifact) -> pm.ReplayItemResult:
        return pm.verify_proof_artifact(art, max_allowed_ulps=100)

    partial_sc = pm.evaluate_mutant_kill_scorecard(corpus, verifier=_ignores_ulp)
    assert partial_sc.passed is False and partial_sc.survived_mutants == 1
    assert partial_sc.survivor_ids == ("a.wgsl.gpu-cert.json::ulp_bound_inflation",)


def test_unknown_mutant_class_and_corpus_loader(tmp_path: Path) -> None:
    art = _make_gpu_artifact("k.wgsl.gpu-cert.json")
    with pytest.raises(ValueError):
        pm.mutate_artifact(art, "bogus_mutant")
    assert pm.load_gpu_proof_corpus(tmp_path / "missing") == []
    (tmp_path / "k.wgsl").write_bytes(art.shader_bytes or b"")
    (tmp_path / "k.wgsl.gpu-cert.json").write_text(json.dumps(art.cert), encoding="utf-8")
    loaded = pm.load_gpu_proof_corpus(tmp_path)
    assert len(loaded) == 1 and pm.verify_proof_artifact(loaded[0]).passed is True


@pytest.mark.parametrize("bad_schema", ["wrong/v1", "", None])
def test_unsupported_schema_rejected_fail_closed(bad_schema: object) -> None:
    art = pm.ProofArtifact("bad.json", {"schema": bad_schema, "verified": True, "cert_sha256": "a" * 64})
    res = pm.verify_proof_artifact(art)
    assert res.passed is False and any("UNSUPPORTED_PROOF_SCHEMA:" in r for r in res.reasons)


def test_package_hygiene_loc_spdx_stdlib_and_scope_limits() -> None:
    root = Path(__file__).resolve().parents[1]
    pkg_files = sorted((root / "harness" / "proof_mutator").glob("*.py"))
    assert len(pkg_files) == 4
    assert set(pm.HONEST_SCOPE_LIMITS) == {"sharded_replay", "mutant_engine", "kill_scorecard"}
    for path in [*pkg_files, Path(__file__).resolve()]:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= 250, f"{path.name} has {len(lines)} lines (> 250)"
        assert lines[0] == "# SPDX-License-Identifier: MIT"
        assert "\u2014" not in text and "\u2013" not in text
    for path in pkg_files:
        text = path.read_text(encoding="utf-8")
        assert "HONEST_SCOPE_LIMIT" in text
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Import):
                assert all(a.name.split(".")[0] in sys.stdlib_module_names for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                assert node.module.split(".")[0] in sys.stdlib_module_names
