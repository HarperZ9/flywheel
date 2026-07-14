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


def test_without_claims_the_crucible_stage_is_declared_skipped(tmp_path):
    r = _runner()
    doc = science_run("q", runner=r, workdir=tmp_path)
    assert doc["verdicts"] == []
    assert doc["crucible"] == "skipped: no claims given"
    assert all(argv[0] != "crucible" for argv in r.calls)
