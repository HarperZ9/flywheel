"""The record a delegated run leaves, and what it takes to break it."""
import json

from harness.acp_policy import DenyAll, WorkspacePolicy
from harness.acp_turn import END_TURN
from harness.acp_witness import (AcpWitness, DECISION_ACTION, FRAME_ACTION,
                                 TURN_ACTION, does_not_prove, summarize,
                                 transcript_resolver)
from harness.action_witness import open_log, read_log, verify_log
from harness.byte_witness_verify import (BYTES_UNAVAILABLE, DIGEST_MISMATCH,
                                         LINK_BROKEN, MATCH, TAMPERED,
                                         UNVERIFIABLE)
from tests.acp_fake_agent import FakeAgent, connect


def run(tmp_path, agent=None, policy=None, transcript=None):
    log = open_log("run-1", directory=tmp_path)
    witness = AcpWitness(log, transcript=transcript)
    policy = policy or DenyAll()
    client = connect(agent or FakeAgent(), policy=policy,
                     observer=witness.observe_frame)
    client.initialize()
    client.new_session()
    turn = client.prompt("hello")
    client.close()
    witness.record_decisions(policy)
    witness.record_turn(turn)
    return witness, turn, log


def test_every_frame_in_both_directions_becomes_a_link(tmp_path):
    witness, _, log = run(tmp_path)
    # initialize, session/new, session/prompt: three calls and three answers,
    # plus three session/update notifications from the agent.
    assert witness.frames == 9
    actions = [r["context"]["action"] for r in read_log(log.path)]
    assert actions.count(FRAME_ACTION) == 9
    assert actions.count(TURN_ACTION) == 1


def test_the_chain_and_its_transcript_verify_offline_together(tmp_path):
    transcript = tmp_path / "frames.jsonl"
    _, _, log = run(tmp_path, transcript=transcript)
    result = verify_log(log.path, resolve=transcript_resolver(transcript))
    assert result["verdict"] == MATCH
    assert result["broken_at"] is None
    assert result["checked"] == len(read_log(log.path))


def test_a_chain_without_its_bytes_is_unverifiable_and_says_so(tmp_path):
    _, _, log = run(tmp_path)
    result = verify_log(log.path)
    assert result["verdict"] == UNVERIFIABLE
    assert result["failure_class"] == BYTES_UNAVAILABLE
    assert result["broken_at"] is None


def test_an_edited_frame_breaks_the_chain_from_that_point(tmp_path):
    _, _, log = run(tmp_path)
    records = read_log(log.path)
    records[3]["sha256"] = "0" * 64
    result = verify_log(records)
    assert result["verdict"] == TAMPERED
    assert result["failure_class"] == LINK_BROKEN
    # Record 3 answers to nothing before it; record 4 is where the edit shows.
    assert result["broken_at"] == 4


def test_a_frame_removed_from_the_middle_breaks_the_chain(tmp_path):
    _, _, log = run(tmp_path)
    records = read_log(log.path)
    del records[4]
    result = verify_log(records)
    assert result["verdict"] == TAMPERED
    assert result["broken_at"] == 4


def test_changed_prompt_text_is_caught_when_the_transcript_backs_the_chain(
        tmp_path):
    transcript = tmp_path / "frames.jsonl"
    _, _, log = run(tmp_path, transcript=transcript)
    entries = [json.loads(line) for line in
               transcript.read_text(encoding="utf-8").splitlines()]
    for entry in entries:
        prompt = entry["payload"].get("params", {}).get("prompt")
        if prompt:
            prompt[0]["text"] = "HELLO"  # same length, so the digest is the test
    transcript.write_text(
        "".join(json.dumps(entry) + chr(10) for entry in entries),
        encoding="utf-8")
    result = verify_log(log.path, resolve=transcript_resolver(transcript))
    assert result["verdict"] == TAMPERED
    assert result["failure_class"] == DIGEST_MISMATCH


def test_the_direction_and_the_method_are_on_the_record(tmp_path):
    _, _, log = run(tmp_path)
    frames = [r for r in read_log(log.path)
              if r["context"]["action"] == FRAME_ACTION]
    methods = [f["context"]["method"] for f in frames]
    assert "initialize" in methods
    assert "session/prompt" in methods
    assert {f["context"]["direction"] for f in frames} == {"sent", "received"}


def test_a_refused_request_is_in_the_record_beside_what_succeeded(tmp_path):
    def prompt(agent, session_id, _):
        agent.call("session/request_permission", {
            "sessionId": session_id, "title": "Delete the repository",
            "options": [{"optionId": "n", "name": "No", "kind": "reject_once"}]})
        return END_TURN

    policy = DenyAll()
    witness, _, log = run(tmp_path, agent=FakeAgent(on_prompt=prompt),
                          policy=policy)
    decisions = [r for r in read_log(log.path)
                 if r["context"]["action"] == DECISION_ACTION]
    assert len(decisions) == 1
    assert decisions[0]["context"]["allowed"] is False
    assert decisions[0]["context"]["policy"] == "deny-all"


def test_recording_decisions_twice_does_not_write_them_twice(tmp_path):
    log = open_log("run-1", directory=tmp_path)
    witness = AcpWitness(log)
    policy = DenyAll()
    policy.permission({"title": "one", "options": []})
    assert witness.record_decisions(policy) == 1
    assert witness.record_decisions(policy) == 0
    policy.permission({"title": "two", "options": []})
    assert witness.record_decisions(policy) == 1
    assert len(log) == 2


def test_the_chain_holds_digests_and_not_the_prompt_text(tmp_path):
    log = open_log("run-1", directory=tmp_path)
    witness = AcpWitness(log)
    witness.observe_frame("sent", {"jsonrpc": "2.0", "id": 1,
                                   "method": "session/prompt",
                                   "params": {"prompt": [
                                       {"type": "text",
                                        "text": "hunter2-secret"}]}})
    written = log.path.read_text(encoding="utf-8")
    assert "hunter2-secret" not in written
    assert "session/prompt" in written


def test_a_transcript_is_written_only_when_one_was_asked_for(tmp_path):
    _, _, _ = run(tmp_path / "without")
    assert not (tmp_path / "without" / "frames.jsonl").exists()

    path = tmp_path / "with" / "frames.jsonl"
    run(tmp_path / "with", transcript=path)
    lines = [json.loads(line) for line in
             path.read_text(encoding="utf-8").splitlines()]
    # Nine frames and the folded turn: everything the chain took a digest over.
    assert len(lines) == 10
    assert any("hello" in json.dumps(entry["payload"]) for entry in lines)
    assert all(len(entry["sha256"]) == 64 for entry in lines)


def test_the_turn_summary_counts_the_words_without_repeating_them(tmp_path):
    _, turn, log = run(tmp_path)
    summary = summarize(turn)
    assert summary["message_characters"] == len(turn.text)
    assert summary["stop_reason"] == END_TURN
    assert "done: hello" not in json.dumps(summary)


def test_the_turn_summary_carries_what_the_turn_does_not_prove(tmp_path):
    _, turn, _ = run(tmp_path)
    assert summarize(turn)["does_not_prove"]


def test_recording_a_turn_returns_the_link_it_was_bound_at(tmp_path):
    log = open_log("run-1", directory=tmp_path)
    witness = AcpWitness(log)
    _, turn, _ = run(tmp_path / "other")
    bound = witness.record_turn(turn)
    assert len(bound["sha256"]) == 64
    assert bound["link"] == log.chain[-1].link()


def test_a_policy_that_allowed_something_records_that_it_allowed_it(tmp_path):
    (tmp_path / "note.txt").write_text("x", encoding="utf-8")

    def prompt(agent, session_id, _):
        agent.call("fs/read_text_file", {"sessionId": session_id,
                                         "path": str(tmp_path / "note.txt")})
        return END_TURN

    policy = WorkspacePolicy(tmp_path)
    _, _, log = run(tmp_path / "run", agent=FakeAgent(on_prompt=prompt),
                    policy=policy)
    decisions = [r for r in read_log(log.path)
                 if r["context"]["action"] == DECISION_ACTION]
    assert [d["context"]["allowed"] for d in decisions] == [True]
    assert decisions[0]["context"]["policy"] == "workspace"


def test_what_an_acp_record_does_not_prove_is_never_empty():
    limits = does_not_prove()
    assert limits
    assert any("did not carry" in limit for limit in limits)
    assert any("was correct" in limit for limit in limits)
