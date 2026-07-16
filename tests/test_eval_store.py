"""Run history must be as honest as the runs it stores: a science run's
chain is recomputed at read time so a hand-edited verdict is served as
TAMPERED, never as history; agent runs are content-addressed so ANY edit
moves the id off its filename; an empty store says it is empty."""

import json

from harness.eval_store import (agent_run_detail, agent_runs, save_agent_run,
                                save_science_run, science_run_detail,
                                science_runs)
from harness.science_bench import science_run

GATHER_OK = json.dumps({
    "items": [{"id": "2601.00001", "title": "Verified Inference",
               "url": "https://arxiv.org/abs/2601.00001"}]})

CRUCIBLE_OK = json.dumps({
    "assessment": {
        "verdict_seal": "c50f9358",
        "verdicts": [{"claim_id": "c1", "status": "UNVERIFIABLE",
                      "grounds": "no measurement"}]}})


def _runner(argv):
    if argv[0] == "gather":
        return (0, GATHER_OK)
    if argv[0] == "crucible":
        return (0, CRUCIBLE_OK)
    return (1, "unknown tool")


def _science_doc(tmp_path, question="does the wrapper uplift small models"):
    return science_run(
        question,
        claims=[{"id": "c1", "text": "wrapped beats bare",
                 "falsification": "paired interval excludes zero"}],
        runner=_runner, workdir=tmp_path / "work")


def test_saved_science_run_appears_in_history(tmp_path):
    doc = _science_doc(tmp_path)
    saved = save_science_run(tmp_path, doc)
    assert saved["receipt_path"].endswith(".json")
    hist = science_runs(tmp_path)
    assert hist["schema"] == "flywheel.science-runs/v1"
    assert hist["total"] == 1
    row = hist["runs"][0]
    assert row["question"] == doc["question"]
    assert row["chain_hash"] == doc["chain_hash"]
    assert row["chain_ok"] is True
    assert row["verdicts"] == {"UNVERIFIABLE": 1}
    assert row["started"]
    assert row["status"] == "COMPLETE"


def test_hand_edited_science_run_is_served_tampered(tmp_path):
    doc = _science_doc(tmp_path)
    save_science_run(tmp_path, doc)
    p = next((tmp_path / "science" / "runs").glob("*.json"))
    stored = json.loads(p.read_text(encoding="utf-8"))
    stored["verdicts"][0]["status"] = "MATCH"  # the lie: unmeasured -> accepted
    p.write_text(json.dumps(stored), encoding="utf-8")
    row = science_runs(tmp_path)["runs"][0]
    assert row["chain_ok"] is False
    assert row["status"] == "TAMPERED"


def test_renamed_science_receipt_is_tampered(tmp_path):
    doc = _science_doc(tmp_path)
    save_science_run(tmp_path, doc)
    p = next((tmp_path / "science" / "runs").glob("*.json"))
    p.rename(p.with_name("deadbeefdeadbeef.json"))
    row = science_runs(tmp_path)["runs"][0]
    assert row["chain_ok"] is False
    assert row["status"] == "TAMPERED"


def test_science_run_detail_roundtrip_and_unknown(tmp_path):
    doc = _science_doc(tmp_path)
    save_science_run(tmp_path, doc)
    detail = science_run_detail(tmp_path, doc["chain_hash"][:8])
    assert detail["chain_ok"] is True
    assert detail["question"] == doc["question"]
    assert detail["verdicts"] == doc["verdicts"]
    assert "error" in science_run_detail(tmp_path, "ffffffff")
    assert "error" in science_run_detail(tmp_path, "ab")  # too short


def test_errored_run_is_history_marked_partial(tmp_path):
    doc = science_run("q", runner=lambda argv: (1, "fetch timed out"),
                      workdir=tmp_path / "work")
    save_science_run(tmp_path, doc)
    row = science_runs(tmp_path)["runs"][0]
    assert row["chain_ok"] is True  # errors are INSIDE the chain
    assert row["status"] == "PARTIAL"
    assert row["n_errors"] >= 1


def test_empty_stores_say_so(tmp_path):
    assert science_runs(tmp_path) == {
        "schema": "flywheel.science-runs/v1", "runs": [], "total": 0}
    assert agent_runs(tmp_path) == {
        "schema": "flywheel.agent-runs/v1", "runs": [], "total": 0}


def _agent_doc():
    return {"goal_excerpt": "fix the failing parser test", "endpoint": "serve",
            "final": "patched and green", "steps": 4, "verified": True,
            "checkpoint": "ab12", "duration_s": 3.2, "ttva_s": 3.2,
            "tests_pass_trusted": True}


def test_agent_run_is_content_addressed(tmp_path):
    saved = save_agent_run(tmp_path, _agent_doc())
    rid = saved["run_id"]
    assert len(rid) == 16
    hist = agent_runs(tmp_path)
    assert hist["total"] == 1
    row = hist["runs"][0]
    assert row["run_id"] == rid
    assert row["intact"] is True
    assert row["endpoint"] == "serve"
    assert row["verified"] is True
    assert row["started"]
    detail = agent_run_detail(tmp_path, rid)
    assert detail["intact"] is True
    assert detail["final"] == "patched and green"
    assert "error" in agent_run_detail(tmp_path, "0" * 16)


def test_edited_agent_run_is_tampered(tmp_path):
    rid = save_agent_run(tmp_path, _agent_doc())["run_id"]
    p = tmp_path / "agent_runs" / f"{rid}.json"
    stored = json.loads(p.read_text(encoding="utf-8"))
    stored["verified"] = True
    stored["ttva_s"] = 0.1  # the flattering edit
    p.write_text(json.dumps(stored), encoding="utf-8")
    row = agent_runs(tmp_path)["runs"][0]
    assert row["intact"] is False
    assert row["status"] == "TAMPERED"
    assert agent_run_detail(tmp_path, rid)["intact"] is False
