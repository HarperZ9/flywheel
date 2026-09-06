"""What an ACP frame is, and what happens to a line that is not one."""
import json

import pytest

from harness.acp_wire import (FAILURE, INVALID_REQUEST, NOTIFICATION,
                              PARSE_ERROR, PROTOCOL_VERSION, REQUEST, RESPONSE,
                              SUPPORTED_VERSIONS, WireError, classify, decode,
                              encode, failure, notification, parse_error,
                              request, success)


def test_this_client_speaks_a_version_it_also_lists_as_supported():
    assert PROTOCOL_VERSION in SUPPORTED_VERSIONS


def test_a_request_carries_an_id_and_a_notification_does_not():
    assert "id" in request(0, "session/new")
    assert "id" not in notification("session/update", {"sessionId": "s"})
    assert classify(request(0, "session/new")) == REQUEST
    assert classify(notification("session/update")) == NOTIFICATION


def test_omitted_params_stay_omitted_rather_than_becoming_null():
    assert "params" not in request(1, "authenticate")
    assert request(1, "m", {"a": 1})["params"] == {"a": 1}


def test_a_result_and_an_error_are_told_apart_by_which_key_is_present():
    assert classify(success(1, {"ok": True})) == RESPONSE
    assert classify(failure(1, -32601, "nope")) == FAILURE


def test_a_response_carrying_both_result_and_error_is_rejected():
    both = {"jsonrpc": "2.0", "id": 1, "result": 1, "error": {"code": -1}}
    # error wins the branch, but the point is that neither shape is invented:
    # a response with no result and no error is refused outright.
    assert classify(both) == FAILURE
    with pytest.raises(WireError):
        classify({"jsonrpc": "2.0", "id": 1})


def test_a_message_without_jsonrpc_2_0_is_not_an_acp_message():
    with pytest.raises(WireError):
        classify({"id": 1, "method": "x"})
    with pytest.raises(WireError):
        classify({"jsonrpc": "1.0", "id": 1, "method": "x"})


def test_a_message_that_is_not_an_object_is_refused():
    for payload in ([], "text", 7, None):
        with pytest.raises(WireError):
            classify(payload)


def test_an_empty_method_name_is_refused():
    with pytest.raises(WireError):
        classify({"jsonrpc": "2.0", "id": 1, "method": ""})


def test_an_id_that_is_neither_string_nor_number_is_refused():
    with pytest.raises(WireError):
        classify({"jsonrpc": "2.0", "id": {"a": 1}, "method": "x"})


def test_every_encoded_frame_ends_in_exactly_one_newline():
    line = encode(request(1, "session/prompt", {"text": "hi"}))
    assert line.endswith(b"\n")
    assert line.count(b"\n") == 1


def test_a_newline_inside_a_value_is_escaped_not_emitted():
    line = encode(notification("m", {"text": "one\ntwo\r\nthree"}))
    assert line.count(b"\n") == 1
    assert json.loads(line)["params"]["text"] == "one\ntwo\r\nthree"


def test_non_ascii_survives_the_round_trip_as_utf_8():
    line = encode(notification("m", {"text": "⌘ é \U0001f9ed"}))
    assert json.loads(line.decode("utf-8"))["params"]["text"].startswith("⌘")
    assert decode(line).messages[0]["params"]["text"].endswith("\U0001f9ed")


def test_a_value_json_cannot_represent_is_refused_before_it_reaches_the_wire():
    with pytest.raises(ValueError):
        encode(notification("m", {"n": float("nan")}))


def test_a_line_that_is_not_json_raises_and_earns_one_parse_error():
    with pytest.raises(WireError):
        decode(b"{not json\n")
    answer = parse_error(WireError("Parse error: bad"))
    assert answer["id"] is None
    assert answer["error"]["code"] == PARSE_ERROR


def test_a_single_message_decodes_as_unbatched():
    frame = decode(encode(request(4, "session/new", {"cwd": "/tmp"})))
    assert frame.batched is False
    assert frame.messages[0]["method"] == "session/new"
    assert frame.kinds == (REQUEST,)


def test_an_empty_batch_earns_one_invalid_request_with_a_null_id():
    frame = decode(b"[]\n")
    assert frame.messages == ()
    assert len(frame.faults) == 1
    assert frame.faults[0]["id"] is None
    assert frame.faults[0]["error"]["code"] == INVALID_REQUEST


def test_one_bad_entry_in_a_batch_does_not_discard_the_entries_beside_it():
    line = json.dumps([request(1, "a"), {"nope": True},
                       notification("b")]).encode() + b"\n"
    frame = decode(line)
    assert [m["method"] for m in frame.messages] == ["a", "b"]
    assert len(frame.faults) == 1
    assert frame.faults[0]["id"] is None


def test_a_batch_of_only_bad_entries_still_answers_each_one():
    line = json.dumps([{"a": 1}, {"b": 2}]).encode() + b"\n"
    frame = decode(line)
    assert frame.messages == ()
    assert len(frame.faults) == 2


def test_decode_accepts_the_bytes_the_stream_carries_and_the_str_form():
    assert decode(b'{"jsonrpc":"2.0","id":1,"result":2}').messages[0]["id"] == 1
    assert decode('{"jsonrpc":"2.0","id":1,"result":2}').kinds == (RESPONSE,)


def test_an_error_without_an_integer_code_is_not_a_failure_frame():
    with pytest.raises(WireError):
        classify({"jsonrpc": "2.0", "id": 1, "error": {"message": "x"}})


def test_failure_data_is_carried_only_when_there_is_data():
    assert "data" not in failure(1, -32000, "auth")["error"]
    assert failure(1, -32000, "auth", {"m": []})["error"]["data"] == {"m": []}
