"""Folding a session/update stream into one turn, including what it loses."""
from harness.acp_turn import END_TURN, REFUSAL, TurnCollector, text_of


def wrap(**update):
    return {"sessionId": "s", "update": update}


def idle(reason=END_TURN):
    return wrap(sessionUpdate="state_update", state="idle", stopReason=reason)


def chunk(text):
    return wrap(sessionUpdate="agent_message_chunk",
                content={"type": "text", "text": text})


def test_text_of_reads_a_block_a_list_and_a_nested_content_field():
    assert text_of({"type": "text", "text": "hi"}) == "hi"
    assert text_of([{"type": "text", "text": "a"},
                    {"type": "text", "text": "b"}]) == "ab"
    assert text_of({"content": {"type": "text", "text": "deep"}}) == "deep"


def test_a_non_text_block_contributes_no_text_and_does_not_raise():
    assert text_of({"type": "image", "data": "..."}) == ""
    assert text_of(None) == ""
    assert text_of(7) == ""


def test_message_chunks_join_in_arrival_order():
    collector = TurnCollector("s")
    for piece in ("one ", "two ", "three"):
        assert collector.accept(chunk(piece)) is False
    assert collector.turn.text == "one two three"


def test_the_turn_ends_only_when_idle_carries_a_stop_reason():
    collector = TurnCollector("s")
    assert collector.accept(wrap(sessionUpdate="state_update",
                                 state="running")) is False
    assert collector.accept(wrap(sessionUpdate="state_update",
                                 state="idle")) is False
    assert collector.turn.stop_reason == ""
    assert collector.accept(idle()) is True
    assert collector.turn.stop_reason == END_TURN
    assert collector.turn.complete is True


def test_a_refusal_is_a_recorded_outcome_not_an_incomplete_turn():
    collector = TurnCollector("s")
    collector.accept(idle(REFUSAL))
    assert collector.turn.refused is True
    assert collector.turn.complete is False


def test_thinking_is_kept_apart_from_the_message_the_agent_sent():
    collector = TurnCollector("s")
    collector.accept(wrap(sessionUpdate="agent_thought",
                          content={"type": "text", "text": "hmm"}))
    collector.accept(chunk("answer"))
    assert collector.turn.thinking == "hmm"
    assert collector.turn.text == "answer"


def test_a_tool_call_keeps_its_latest_status_and_accumulates_its_output():
    collector = TurnCollector("s")
    collector.accept(wrap(sessionUpdate="tool_call_update", toolCallId="t1",
                          title="read file", kind="read", status="pending"))
    collector.accept(wrap(sessionUpdate="tool_call_content_chunk",
                          toolCallId="t1",
                          content={"type": "text", "text": "line one\n"}))
    collector.accept(wrap(sessionUpdate="tool_call_update", toolCallId="t1",
                          status="completed"))
    call = collector.turn.tool_calls["t1"]
    assert (call.title, call.kind, call.status) == ("read file", "read",
                                                    "completed")
    assert call.text == "line one\n"


def test_a_tool_call_without_an_id_is_recorded_but_not_indexed():
    collector = TurnCollector("s")
    collector.accept(wrap(sessionUpdate="tool_call_update", title="orphan"))
    assert collector.turn.tool_calls == {}
    assert len(collector.turn.updates) == 1


def test_the_latest_plan_replaces_the_previous_one():
    collector = TurnCollector("s")
    collector.accept(wrap(sessionUpdate="plan_update", entries=[{"c": "a"}]))
    collector.accept(wrap(sessionUpdate="plan_update",
                          entries=[{"c": "a"}, {"c": "b"}]))
    assert len(collector.turn.plan) == 2


def test_usage_is_kept_without_the_tag_that_routed_it():
    collector = TurnCollector("s")
    collector.accept(wrap(sessionUpdate="usage_update", inputTokens=10,
                          outputTokens=3))
    assert collector.turn.usage == {"inputTokens": 10, "outputTokens": 3}


def test_every_update_is_kept_in_order_beside_the_folded_view():
    collector = TurnCollector("s")
    collector.accept(chunk("a"))
    collector.accept(wrap(sessionUpdate="agent_thought",
                          content={"type": "text", "text": "t"}))
    collector.accept(idle())
    assert [u["sessionUpdate"] for u in collector.turn.updates] == [
        "agent_message_chunk", "agent_thought", "state_update"]


def test_an_update_this_reader_does_not_know_is_counted_not_dropped():
    collector = TurnCollector("s")
    collector.accept(wrap(sessionUpdate="something_new_in_v3", payload=1))
    assert collector.turn.unrecognized == ["something_new_in_v3"]
    assert len(collector.turn.updates) == 1
    assert any("something_new_in_v3" in limit
               for limit in collector.turn.does_not_prove())


def test_a_params_object_with_no_update_is_reported_as_malformed():
    collector = TurnCollector("s")
    assert collector.accept({"sessionId": "s"}) is False
    assert collector.turn.unrecognized == ["malformed"]
    assert collector.turn.updates == []


def test_a_turn_that_never_reported_a_stop_reason_says_so_in_its_limits():
    collector = TurnCollector("s")
    collector.accept(chunk("partial"))
    assert any("never reported a stop reason" in limit
               for limit in collector.turn.does_not_prove())
    collector.accept(idle())
    assert not any("never reported a stop reason" in limit
                   for limit in collector.turn.does_not_prove())


def test_every_turn_states_that_tool_calls_are_the_agents_own_account():
    collector = TurnCollector("s")
    collector.accept(idle())
    limits = collector.turn.does_not_prove()
    assert any("not as executed" in limit for limit in limits)
    assert any("not an independent observation" in limit for limit in limits)
