"""The science run must chain evidence, spec, and judgment without ever
manufacturing any of them: gather's provenance is carried verbatim, the
forge's gates price the question's checkability, crucible's UNVERIFIABLE
stays UNVERIFIABLE (an unmeasured claim is never accepted), and a failed
stage is a named error while the rest of the run continues."""

import json

from harness.science_bench import SCHEMA, science_run

GATHER_OK = json.dumps({
    "items": [
        {"id": "2603.06713", "title": "Scaling Agentic Capabilities",
         "url": "https://arxiv.org/abs/2603.06713"},
        {"id": "2601.00001", "title": "Verified Inference",
         "url": "https://arxiv.org/abs/2601.00001"},
    ]})

CRUCIBLE_OK = json.dumps({
    "assessment": {
        "thesis_id": "8abdc05fc593e462",
        "verdict_seal": "c50f9358",
        "verdicts": [
            {"claim_id": "c1", "status": "UNVERIFIABLE",
             "grounds": "no measurement"},
        ]}})


def _runner(gather=(0, GATHER_OK), crucible=(0, CRUCIBLE_OK)):
    calls = []

    def run(argv):
        calls.append(argv)
        if argv[0] == "gather":
            return gather
        if argv[0] == "crucible":
            return crucible
        return (1, "unknown tool")

    run.calls = calls
    return run


def test_science_run_chains_gather_forge_and_crucible(tmp_path):
    doc = science_run(
        "does verified inference uplift small models",
        claims=[{"id": "c1", "text": "wrapped beats bare",
                 "falsification": "paired bench interval excludes zero"}],
        runner=_runner(), workdir=tmp_path)
    assert doc["schema"] == SCHEMA
    assert len(doc["sources"]) == 2
    assert doc["sources"][0]["id"] == "2603.06713"
    assert doc["prp"]["confidence"] >= 1
    assert doc["prp"]["validation_gates"]
    assert doc["verdicts"][0]["status"] == "UNVERIFIABLE"
    assert doc["chain_hash"]
    assert doc["errors"] == {}
    # Determinism: the same inputs chain to the same hash.
    again = science_run(
        "does verified inference uplift small models",
        claims=[{"id": "c1", "text": "wrapped beats bare",
                 "falsification": "paired bench interval excludes zero"}],
        runner=_runner(), workdir=tmp_path)
    assert again["chain_hash"] == doc["chain_hash"]


def test_gather_failure_is_named_and_the_run_continues(tmp_path):
    doc = science_run("q", runner=_runner(gather=(1, "fetch timed out")),
                      workdir=tmp_path)
    assert "gather" in doc["errors"]
    assert doc["sources"] == []
    assert doc["prp"]["confidence"] >= 1  # the forge still ran


def test_measurements_flip_claims_to_witnessed_verdicts(tmp_path):
    def run(argv):
        if argv[0] == "gather":
            return (0, GATHER_OK)
        if argv[0] == "crucible":
            assert "--measurements" in argv
            return (0, json.dumps({"assessment": {
                "verdict_seal": "seal",
                "verdicts": [{"claim_id": "c1", "status": "MATCH",
                              "grounds": "within tolerance"}]}}))
        return (1, "unknown tool")

    doc = science_run(
        "q", claims=[{"id": "c1", "text": "t", "falsification": "f"}],
        measurements=[{"claim": "c1", "deviation": 0.0, "tolerance": 0.001,
                       "method": "paired-arm bench"}],
        runner=run, workdir=tmp_path)
    assert doc["verdicts"][0]["status"] == "MATCH"
    assert (tmp_path / "measurements.json").exists()


def test_without_claims_the_crucible_stage_is_declared_skipped(tmp_path):
    r = _runner()
    doc = science_run("q", runner=r, workdir=tmp_path)
    assert doc["verdicts"] == []
    assert doc["crucible"] == "skipped: no claims given"
    assert all(argv[0] != "crucible" for argv in r.calls)


def test_receipt_echoes_the_claims_and_measurements_it_judged(tmp_path):
    claims = [{"id": "c1", "text": "t", "falsification": "f"}]
    ms = [{"claim": "c1", "deviation": 0.0, "tolerance": 0.001,
           "method": "paired-arm bench"}]
    doc = science_run("q", claims=claims, measurements=ms,
                      runner=_runner(), workdir=tmp_path)
    # a stranger holding only the payload can re-run the judgment
    assert doc["claims"] == claims
    assert doc["measurements"] == ms


def test_errored_crucible_hashes_differently_from_no_claims(tmp_path):
    # an errored crucible run (verdicts=[], error named) must not produce the
    # same chain hash as a clean run that simply had no claims
    errored = science_run(
        "q", claims=[{"id": "c1", "text": "t", "falsification": "f"}],
        runner=_runner(crucible=(1, "boom")), workdir=tmp_path)
    assert "crucible" in errored["errors"]
    clean = science_run("q", runner=_runner(), workdir=tmp_path)
    assert errored["chain_hash"] != clean["chain_hash"]


def test_different_measurement_content_same_statuses_hash_differently(tmp_path):
    def _run_with(tol):
        return science_run(
            "q", claims=[{"id": "c1", "text": "t", "falsification": "f"}],
            measurements=[{"claim": "c1", "deviation": 0.0, "tolerance": tol,
                           "method": "bench"}],
            runner=_runner(), workdir=tmp_path)
    assert _run_with(0.001)["chain_hash"] != _run_with(0.1)["chain_hash"]
