"""The DAP envelope, pinned against the three ways it differs from JSON-RPC.

Those three differences are the whole reason this protocol has its own wire
module: a response ties to its request by `request_seq` rather than a shared
id, a failure is a flag on the response rather than a separate error member,
and every message is numbered on one counter rather than only the requests.
A client that assumed JSON-RPC would be wrong in all three places, and wrong
quietly, because the header block is identical and the bytes still parse.

Framing is checked against bytes written by hand here. tests/test_dap_client.py
checks it against a subprocess that framed its own messages without importing
this module, which is the part that catches a format both sides agree on and
nobody else can read.
"""
import io
import json

import pytest

from harness.dap_wire import (EVENT, REQUEST, RESPONSE, DapFraming, classify,
                              decode, error_response, event, request, response)
from harness.jsonrpc import WireError


def framed(payload) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    return b"Content-Length: %d\r\n\r\n%b" % (len(body), body)


def test_a_request_omits_arguments_rather_than_sending_null():
    # An adapter that validates its arguments schema strictly reads an explicit
    # null as a value of the wrong type, where a missing field is the field
    # being absent. The two are not the same message.
    assert "arguments" not in request(1, "threads")
    assert request(2, "threads", {})["arguments"] == {}


def test_a_response_names_the_request_it_answers_and_not_its_own_seq():
    answer = response(9, 4, "initialize", {"supportsX": True})
    assert answer["request_seq"] == 4
    assert answer["seq"] == 9
    assert answer["success"] is True


def test_a_refusal_carries_its_prose_in_message_and_in_body():
    # `message` is the field a client is required to be able to show, and the
    # field an adapter logs when it does not read the structured form. Putting
    # the reason in only one of the two loses it against half the tooling.
    refusal = error_response(3, 2, "launch", "the program is missing")
    assert refusal["success"] is False
    assert refusal["message"] == "the program is missing"
    assert refusal["body"]["error"]["format"] == "the program is missing"


def test_classify_names_each_of_the_three_kinds():
    assert classify(request(1, "threads")) == REQUEST
    assert classify(response(2, 1, "threads", {})) == RESPONSE
    assert classify(event(3, "stopped", {"reason": "breakpoint"})) == EVENT


def test_a_request_without_a_seq_is_refused_because_it_cannot_be_answered():
    # This side answers a reverse request by quoting its seq back as
    # request_seq. A request that carries no seq has no answer that could reach
    # it, so accepting one would mean accepting work that can only be dropped.
    with pytest.raises(WireError):
        classify({"type": "request", "command": "runInTerminal"})


def test_a_response_and_an_event_are_taken_without_a_seq():
    # Nothing here routes on the far side's own seq: responses match on
    # request_seq and events on their name. Refusing these over a field this
    # client never reads would drop messages a real adapter does send.
    assert classify({"type": "response", "request_seq": 1, "success": True,
                     "command": "threads"}) == RESPONSE
    assert classify({"type": "event", "event": "terminated"}) == EVENT


def test_success_must_be_a_flag_and_not_merely_present():
    with pytest.raises(WireError):
        classify({"type": "response", "request_seq": 1, "command": "threads",
                  "success": "yes"})


def test_a_boolean_seq_is_not_an_integer_seq():
    # True is an int in Python and would pass an isinstance check written the
    # obvious way. A message routed on True would collide with request seq 1.
    with pytest.raises(WireError):
        classify({"type": "request", "command": "threads", "seq": True})


def test_an_unknown_type_says_what_it_got():
    with pytest.raises(WireError) as raised:
        classify({"type": "notification", "command": "threads"})
    assert "notification" in str(raised.value)


def test_a_body_that_is_not_json_comes_back_malformed_rather_than_raising():
    # The length was good, so the stream is still aligned on the next header
    # block. Dropping the connection here would lose the rest of a debug
    # session over one message the adapter may never send again.
    frame = decode(b"{ not json")
    assert frame.message is None
    assert "not JSON" in frame.malformed


def test_a_json_body_that_is_not_a_message_carries_the_reason():
    frame = decode(b'{"type": "request"}')
    assert frame.message is None
    assert "command" in frame.malformed


def test_framing_reads_back_what_it_wrote():
    framing = DapFraming()
    message = event(1, "output", {"output": "hello\n"})
    frame = framing.read(io.BytesIO(framing.encode(message)))
    assert frame.message == message
    assert frame.kind == EVENT


def test_the_length_counts_encoded_bytes_and_not_characters():
    # A body with a character outside the basic plane has more bytes than it
    # has characters. A length taken from the string leaves the stream short
    # and every message after it is read from the wrong offset.
    framing = DapFraming()
    encoded = framing.encode(event(1, "output", {"output": "\U0001f600"}))
    header, body = encoded.split(b"\r\n\r\n", 1)
    assert int(header.split(b":")[1]) == len(body)


def test_two_messages_back_to_back_are_read_one_at_a_time():
    framing = DapFraming()
    stream = io.BytesIO(framed(request(1, "threads"))
                        + framed(event(2, "terminated")))
    assert framing.read(stream).message["command"] == "threads"
    assert framing.read(stream).message["event"] == "terminated"
    assert framing.read(stream) is None


def test_a_bare_newline_between_headers_is_read_the_same_as_a_carriage_return():
    # Adapters exist that write \n where the specification says \r\n. A reader
    # that insisted would hang waiting for a header block that already ended.
    framing = DapFraming()
    body = json.dumps(event(1, "terminated")).encode("utf-8")
    stream = io.BytesIO(b"Content-Length: %d\n\n%b" % (len(body), body))
    assert framing.read(stream).message["event"] == "terminated"
