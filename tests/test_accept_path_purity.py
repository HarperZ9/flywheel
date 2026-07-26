"""A verdict is a pure function of (inputs, oracle version, config), full stop.

This one property subsumes every separate prohibition on ledger history,
selector scores, learned models, operator confidence, and incident counts
reaching a verdict. If none of those can influence the accept path, the accept
path cannot drift toward a preference economy.

The expert-grounding synthesis explicitly rejected static information-flow
analysis for this: it is undecidable in Python with dynamic imports and file IO.
So the test is a sandboxed replay instead. Destroy everything a prior run
produced, run again, and assert the verdict and every digest are unchanged. If
accumulated history reached the accept path, they would differ.
"""
import json
import shutil

from harness.gate import run_gate, rewitness_envelope


def test_the_verdict_does_not_depend_on_any_prior_record(tmp_path):
    first = run_gate(tmp_path / "run1")
    shutil.rmtree(tmp_path / "run1", ignore_errors=True)
    second = run_gate(tmp_path / "run2")

    assert second.verdict == first.verdict
    assert second.envelope_hash == first.envelope_hash
    assert second.claim_hash == first.claim_hash
    assert second.group_signal_hash == first.group_signal_hash


def test_a_prior_failing_record_cannot_condemn_a_later_candidate(tmp_path):
    """History must be unable to convict. A poisoned record in the output
    directory must not change what the oracle concludes."""
    clean = run_gate(tmp_path / "clean")

    poisoned = tmp_path / "poisoned"
    poisoned.mkdir(parents=True, exist_ok=True)
    (poisoned / "gate_envelope.json").write_text(
        json.dumps({"task_id": "gate-matmul-2x2x2", "candidate": "garbage",
                    "verdict": "FAIL", "oracle_output_hash": "deadbeef"}),
        encoding="utf-8")
    (poisoned / "gate_report.json").write_text(
        json.dumps({"verdict": "FAIL", "rewitness": "DRIFT"}), encoding="utf-8")

    after = run_gate(poisoned)
    assert after.verdict == clean.verdict
    assert after.envelope_hash == clean.envelope_hash
    assert after.claim_hash == clean.claim_hash


def test_a_prior_passing_record_cannot_absolve_a_bad_candidate(tmp_path):
    """The other direction, which is the one a reward hacker would want: a
    stored PASS must not make a broken candidate re-witness as MATCH."""
    run_gate(tmp_path)
    p = tmp_path / "gate_envelope.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["candidate"] = '{"n":2,"m":2,"p":2,"triples":[]}'   # verifiably wrong
    p.write_text(json.dumps(d, indent=2, sort_keys=True), encoding="utf-8")
    assert rewitness_envelope(p) == "DRIFT"


def test_the_verifier_reaches_no_learned_model(tmp_path):
    """The C2 invariant, checked structurally over the import closure rather
    than by inspection: nothing the verifier path can reach imports a model
    runtime, so no learned model can sit on the accept path."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from check_verifier_stdlib import closure, VERIFIER_ENTRY_POINTS

    reached, third_party_hits = closure(VERIFIER_ENTRY_POINTS)
    assert third_party_hits == []
    for model_runtime in ("serve", "proposer_local", "quant_dither"):
        assert model_runtime not in reached, (
            f"{model_runtime} is reachable from the verifier path")
