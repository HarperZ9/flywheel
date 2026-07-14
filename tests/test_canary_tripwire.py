"""The canary tripwire: the credo-safe form of Tracebit's context bombs
(frozen in the discourse dataset). Their control is the ATTACKER's model
choosing to refuse a planted string, which is soft (~90%, model-dependent,
strippable). Ours is HARD: we plant a unique canary token, and we detect
any tool output that reads it back. The control is OUR detection of the
access, not the model halting itself, so it does not depend on any model's
guardrail. A tripped canary is a hard containment signal, not a suggestion."""

from harness.canary_tripwire import mint_canary, scan_for_canary, Tripwire


def test_a_minted_canary_is_unique_and_marked():
    a = mint_canary("aws-secret")
    b = mint_canary("aws-secret")
    assert a["token"] != b["token"]
    assert a["token"].startswith("FLYWHEEL-CANARY-")
    assert a["label"] == "aws-secret"


def test_reading_the_canary_back_trips_the_wire():
    c = mint_canary("db-password")
    tool_output = f"the secret value is: {c['token']}\nnow using it..."
    hit = scan_for_canary(tool_output, [c])
    assert hit is not None
    assert hit["label"] == "db-password"
    assert hit["token"] == c["token"]


def test_clean_output_does_not_trip():
    c = mint_canary("x")
    assert scan_for_canary("ordinary tool output, nothing secret", [c]) is None


def test_the_tripwire_is_a_hard_containment_signal_not_a_refusal_request():
    tw = Tripwire([mint_canary("prod-key")])
    clean = tw.check("read a normal file")
    assert clean["tripped"] is False
    token = tw.canaries[0]["token"]
    tripped = tw.check(f"exfiltrating {token} to evil.example")
    assert tripped["tripped"] is True
    assert tripped["action"] == "contain"
    # the control is our detection, explicitly not the model's own refusal
    assert "detect" in tripped["note"].lower()
    assert "refus" not in tripped["action"].lower()


def test_multiple_canaries_report_which_one_tripped():
    cs = [mint_canary("a"), mint_canary("b"), mint_canary("c")]
    tw = Tripwire(cs)
    r = tw.check("leaked " + cs[1]["token"])
    assert r["tripped"] and r["hit"]["label"] == "b"


def test_the_agent_loop_is_contained_when_a_canary_is_read(tmp_path):
    """End to end: a decoy file holds a canary; when the agent reads it, the
    loop stops (contained) and the trip is witnessed in the ledger."""
    from harness.local_loop import run_agent
    from harness.local_session import SessionLedger
    from harness.local_tools import ToolExecutor
    c = mint_canary("decoy-secret")
    (tmp_path / "secret.txt").write_text(
        f"api_key={c['token']}", encoding="utf-8")

    class _Agent:
        system = "s"
        last_compaction = None

        def send(self, m):
            return {"content": [{"text": 'TOOL read_file {"path": "secret.txt"}'}],
                    "backend": "stub", "x_receipt": {"receipt_id": "r"}}

    led = SessionLedger()
    res = run_agent(_Agent(), "read the secret", ToolExecutor(root=str(tmp_path)),
                    led, max_steps=4, canaries=[c])
    assert "[contained]" in res["final"]
    assert any(e.kind == "canary_trip" for e in led.entries)
