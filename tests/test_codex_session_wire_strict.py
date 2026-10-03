"""Reject ambiguous and non-finite provider frames before envelope dispatch."""
import pytest

from harness.codex_session_wire import classify, loads


@pytest.mark.parametrize('frame', [
    '{"id":1,"id":2,"result":{}}',
    '{"id":1,"result":{"approved":false,"approved":true}}',
    '{"method":"turn/completed","method":"turn/started","params":{}}',
    '{"id":1,"result":{"duration_ms":1e999}}',
    '{"id":1,"result":{"nested":[-1e999]}}',
    '{"id":1,"result":{"duration_ms":NaN}}',
])
def test_ambiguous_or_nonfinite_frame_is_rejected(frame):
    with pytest.raises(ValueError):
        loads(frame)


def test_finite_provider_response_still_decodes():
    value = loads('{"id":1,"result":{"duration_ms":1e3,"items":[]}}')
    assert value == {'id': 1, 'result': {'duration_ms': 1000.0, 'items': []}}
    assert classify(value) == 'response'


def test_boolean_error_code_is_not_a_numeric_protocol_code():
    with pytest.raises(ValueError):
        classify({'id': 1, 'error': {'code': True, 'message': 'invalid'}})
