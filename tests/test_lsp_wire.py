"""What an LSP header block promises, and what happens when it lies."""
import io
import json

import pytest

from harness.lsp_wire import (CONTENT_MODIFIED, INVALID_REQUEST,
                              MAX_CONTENT_LENGTH, PARSE_ERROR,
                              PROTOCOL_VERSION, REQUEST, REQUEST_CANCELLED,
                              REQUEST_FAILED, RESPONSE, SERVER_CANCELLED,
                              SERVER_NOT_INITIALIZED, UNKNOWN_ERROR_CODE,
                              LspFraming, WireError, content_length, decode,
                              encode, read_body, read_headers, request)


class Dribble:
    """A stream that hands back one byte per read, the way a pipe can.

    A client that assumes read(n) returns n bytes works on a fast local server
    and drops messages on a loaded one. This is that condition, on purpose.
    """

    def __init__(self, data: bytes) -> None:
        self._buffer = io.BytesIO(data)

    def readline(self) -> bytes:
        return self._buffer.readline()

    def read(self, size: int) -> bytes:
        return self._buffer.read(1 if size > 1 else size)


def block(body: bytes, headers: bytes = b"") -> bytes:
    """A header block with an honest length, plus whatever else is asked for."""
    return b"Content-Length: %d\r\n%s\r\n%s" % (len(body), headers, body)


def test_this_client_names_the_specification_it_was_written_from():
    assert PROTOCOL_VERSION == "3.17"


def test_the_lsp_error_codes_are_the_ones_the_specification_assigns():
    assert (SERVER_NOT_INITIALIZED, UNKNOWN_ERROR_CODE) == (-32002, -32001)
    assert (REQUEST_FAILED, SERVER_CANCELLED) == (-32803, -32802)
    assert (CONTENT_MODIFIED, REQUEST_CANCELLED) == (-32801, -32800)


def test_a_message_is_a_header_block_a_blank_line_then_the_body():
    raw = encode(request(1, "initialize"))
    header, separator, body = raw.partition(b"\r\n\r\n")
    assert separator == b"\r\n\r\n"
    assert header == b"Content-Length: %d" % len(body)
    assert json.loads(body)["method"] == "initialize"


def test_the_declared_length_counts_bytes_and_not_characters():
    # The bug this catches is invisible in ASCII and breaks every message after
    # the first non-ASCII one, because the reader takes the wrong byte count and
    # then starts the next header block in the middle of this body.
    raw = encode(request(1, "x", {"text": "é\U0001F600"}))
    header, _, body = raw.partition(b"\r\n\r\n")
    assert int(header.split(b":")[1]) == len(body)
    assert len(body) > len(body.decode("utf-8"))


def test_a_message_written_by_this_module_reads_back_through_the_framing():
    sent = request(7, "textDocument/definition", {"a": "\U0001F600"})
    stream = io.BytesIO(encode(sent))
    frame = LspFraming().read(stream)
    assert frame.messages == (sent,)
    assert frame.kinds == (REQUEST,)


def test_two_messages_back_to_back_read_as_two_frames():
    stream = io.BytesIO(encode(request(1, "a")) + encode(request(2, "b")))
    framing = LspFraming()
    assert framing.read(stream).messages[0]["id"] == 1
    assert framing.read(stream).messages[0]["id"] == 2
    assert framing.read(stream) is None


def test_a_body_arriving_one_byte_at_a_time_still_reads_whole():
    sent = request(3, "workspace/symbol", {"query": "x" * 200})
    frame = LspFraming().read(Dribble(encode(sent)))
    assert frame.messages == (sent,)


def test_a_stream_that_ends_at_a_message_boundary_is_not_an_error():
    assert read_headers(io.BytesIO(b"")) is None
    assert LspFraming().read(io.BytesIO(b"")) is None


def test_a_stream_that_ends_inside_a_header_block_is_an_error():
    with pytest.raises(WireError, match="inside a header block"):
        read_headers(io.BytesIO(b"Content-Length: 2\r\n"))


def test_a_header_name_is_read_without_regard_to_its_capitalization():
    headers = read_headers(io.BytesIO(b"CONTENT-LENGTH:  4  \r\n\r\n"))
    assert content_length(headers) == 4


def test_a_header_line_with_no_colon_is_refused():
    with pytest.raises(WireError, match="name: value"):
        read_headers(io.BytesIO(b"Content-Length 4\r\n\r\n"))


def test_a_header_line_that_is_not_ascii_is_refused():
    with pytest.raises(WireError, match="ASCII"):
        read_headers(io.BytesIO("X-Note: café\r\n\r\n".encode("utf-8")))


def test_a_message_with_no_content_length_header_is_refused():
    with pytest.raises(WireError, match="Content-Length"):
        content_length({"content-type": "application/vscode-jsonrpc"})


def test_a_content_length_that_is_not_an_integer_is_refused():
    with pytest.raises(WireError, match="an integer"):
        content_length({"content-length": "twelve"})


def test_a_negative_content_length_is_refused():
    with pytest.raises(WireError, match="not negative"):
        content_length({"content-length": "-1"})


def test_a_content_length_over_the_ceiling_is_refused_before_reading():
    # A reader that trusts the number blocks forever on a message that is never
    # coming. The ceiling turns that hang into a named failure.
    with pytest.raises(WireError, match="ceiling"):
        content_length({"content-length": str(MAX_CONTENT_LENGTH + 1)})


def test_a_content_type_naming_another_charset_is_refused():
    with pytest.raises(WireError, match="UTF-8"):
        content_length({"content-length": "2",
                        "content-type": "application/json; charset=utf-16"})


def test_the_two_spellings_of_utf_8_are_both_accepted_and_so_is_silence():
    for value in ("application/vscode-jsonrpc; charset=utf-8",
                  "application/vscode-jsonrpc;charset=utf8",
                  'application/vscode-jsonrpc; charset="UTF-8"',
                  "application/vscode-jsonrpc"):
        assert content_length({"content-length": "2",
                               "content-type": value}) == 2


def test_a_body_cut_short_of_its_declared_length_is_refused():
    with pytest.raises(WireError, match="ended 6 bytes into a 8 byte"):
        read_body(io.BytesIO(b"ab"), 8)


def test_a_body_of_length_zero_reads_without_touching_the_stream():
    assert read_body(io.BytesIO(b""), 0) == b""


def test_a_truncated_message_ends_the_connection_rather_than_being_answered():
    # The stream is now at an unknown offset, so there is no next header block
    # to find and answering would be a guess about what got lost.
    with pytest.raises(WireError):
        LspFraming().read(io.BytesIO(b"Content-Length: 40\r\n\r\n{}"))


def test_a_bad_length_ends_the_connection_rather_than_being_answered():
    with pytest.raises(WireError):
        LspFraming().read(io.BytesIO(b"Content-Length: x\r\n\r\n{}"))


def test_a_body_that_is_not_json_is_answered_and_the_stream_reads_on():
    # The length was honest, so the next header block is still a whole message.
    # One unparseable body should not end a session that is otherwise working.
    stream = io.BytesIO(block(b"{not json") + encode(request(9, "shutdown")))
    framing = LspFraming()
    frame = framing.read(stream)
    assert frame.messages == ()
    assert [fault["error"]["code"] for fault in frame.faults] == [PARSE_ERROR]
    assert framing.read(stream).messages[0]["id"] == 9


def test_decode_raises_on_a_body_that_is_not_json_at_all():
    with pytest.raises(WireError, match="Parse error"):
        decode(b"{not json")


def test_a_body_that_is_not_valid_utf_8_is_a_parse_error():
    with pytest.raises(WireError):
        decode(b'{"jsonrpc":"2.0","id":1,"result":"\xff\xfe"}')


def test_an_array_body_earns_one_invalid_request_because_lsp_does_not_batch():
    payload = [request(1, "a"), request(2, "b")]
    frame = decode(json.dumps(payload).encode("utf-8"))
    assert frame.messages == ()
    assert len(frame.faults) == 1
    assert frame.faults[0]["error"]["code"] == INVALID_REQUEST
    assert frame.faults[0]["id"] is None


def test_a_json_body_that_is_not_a_message_is_an_invalid_request():
    frame = decode(b'{"id":4,"method":"initialize"}')
    assert frame.messages == ()
    assert frame.faults[0]["error"]["code"] == INVALID_REQUEST
    assert frame.faults[0]["id"] == 4


def test_a_fault_keeps_the_id_when_there_is_one_and_nulls_it_when_there_is_not():
    assert decode(b'{"jsonrpc":"2.0"}').faults[0]["id"] is None
    assert decode(b'{"jsonrpc":"1.0","id":"s"}').faults[0]["id"] == "s"
    assert decode(b'{"jsonrpc":"2.0","id":{"a":1}}').faults[0]["id"] is None


def test_a_response_body_decodes_as_a_response():
    frame = decode(b'{"jsonrpc":"2.0","id":1,"result":{"capabilities":{}}}')
    assert frame.kinds == (RESPONSE,)


def test_a_value_json_cannot_carry_is_refused_before_it_reaches_the_wire():
    with pytest.raises(ValueError):
        encode(request(1, "x", {"n": float("nan")}))
