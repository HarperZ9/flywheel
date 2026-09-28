"""I7 for gateway traces: the same trace in plaintext and encrypted modes.

Records and checkpoints are encrypted below the canonical bytes, so a reader
gets identical records either way. Tamper checks flip bytes in both modes, a
trace begun in plaintext continues encrypted, and a plaintext file after an
encrypted one is refused as a downgrade.
"""
import base64

import pytest

from harness.evidence_json import canonical_bytes
from harness.gateway_agent_trace import AgentTrace, TraceError
from harness.trace_enc import NoProvider
from trace_enc_fakes import StreamTestProvider, long_canary, shingles, using

OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "b" * 32
OPERATION = "op_" + "c" * 32


@pytest.fixture(params=["plain", "enc"])
def mode(request):
    provider = NoProvider() if request.param == "plain" else StreamTestProvider()
    with using(provider):
        yield request.param


def _trace(state):
    return AgentTrace(state, OWNER, JOURNEY, OPERATION)


def _files(state):
    return sorted(p for p in state.rglob("*.json") if "gateway-agent-traces" in p.parts)


def _write_three(state):
    trace = _trace(state)
    for index in range(3):
        trace.append("progress", {"index": index, "note": f"step {index}"})
    return trace


def test_a_trace_reads_back_in_both_modes(tmp_path, mode):
    _write_three(tmp_path)
    records = _trace(tmp_path).read()
    assert [r["payload"]["index"] for r in records] == [0, 1, 2]
    head = _files(tmp_path)[0].read_bytes()
    assert head.startswith(b"FWENC1\n") is (mode == "enc")


def test_the_canonical_record_bytes_are_identical_across_modes(tmp_path):
    out = {}
    for name, provider in (("plain", NoProvider()), ("enc", StreamTestProvider())):
        (tmp_path / name).mkdir()
        with using(provider):
            _write_three(tmp_path / name)
            out[name] = [base64.b64encode(canonical_bytes(
                {k: v for k, v in r.items() if k != "record_sha256"}))
                for r in _trace(tmp_path / name).read()]
    assert out["plain"] == out["enc"]


@pytest.mark.parametrize("target", ["00000001.json", "head-00000001.json"])
def test_a_flipped_byte_fails_closed_in_both_modes(tmp_path, mode, target):
    _write_three(tmp_path)
    path = next(p for p in _files(tmp_path) if p.name == target)
    raw = bytearray(path.read_bytes())
    raw[len(raw) // 2] ^= 0x01
    path.write_bytes(bytes(raw))
    with pytest.raises(TraceError):
        _trace(tmp_path).read()


def test_the_long_canary_is_absent_from_encrypted_trace_files(tmp_path):
    canary = long_canary()
    with using(StreamTestProvider()):
        _trace(tmp_path).append("result", {"final": canary})
        assert _trace(tmp_path).read()[0]["payload"]["final"] == canary
    stored = b"".join(p.read_bytes() for p in tmp_path.rglob("*") if p.is_file())
    assert not any(piece in stored for piece in shingles(canary))


def test_a_plaintext_prefix_continues_encrypted_and_reads(tmp_path):
    with using(NoProvider()):
        _write_three(tmp_path)
    with using(StreamTestProvider()):
        trace = _trace(tmp_path)
        trace.read()
        trace.append("progress", {"index": 3})
        assert [r["payload"]["index"] for r in _trace(tmp_path).read()] == [0, 1, 2, 3]
    names = {p.name: p.read_bytes()[:7] for p in _files(tmp_path)}
    assert names["00000002.json"].startswith(b"{")
    assert names["00000003.json"] == b"FWENC1\n"


def test_an_encrypted_file_followed_by_plaintext_is_refused(tmp_path):
    provider = StreamTestProvider()
    with using(provider):
        _trace(tmp_path).append("progress", {"index": 0})
    for floor in tmp_path.rglob("*.floor"):
        floor.unlink()
    with using(NoProvider()):
        trace = _trace(tmp_path)
        trace.count, trace.head = 1, _head(tmp_path, provider)
        trace.append("progress", {"index": 1})
    with using(provider):
        with pytest.raises(TraceError):
            _trace(tmp_path).read()


def _head(state, provider):
    with using(provider):
        return _trace(state).read()[-1]["record_sha256"]


def test_a_plaintext_write_after_the_floor_is_refused(tmp_path):
    from harness.trace_enc import EncError
    from harness.trace_enc_write import ItemCipher
    with using(StreamTestProvider()):
        _trace(tmp_path).append("progress", {"index": 0})
    assert list(tmp_path.rglob("S1.floor"))
    with using(NoProvider()):
        with pytest.raises(TraceError):
            AgentTrace(tmp_path, OWNER, JOURNEY, "op_" + "d" * 32).append("progress", {})
        with pytest.raises(EncError) as failure:
            ItemCipher(tmp_path, OWNER, "S1", "agt_" + "e" * 32).seal("00000000.json", b"{}")
    assert failure.value.code == "ENC_REQUIRED"


def test_rewriting_the_same_record_is_accepted_although_the_ciphertext_differs(tmp_path):
    with using(StreamTestProvider()):
        _trace(tmp_path).append("progress", {"index": 0})
        again = _trace(tmp_path)
        again.append("progress", {"index": 0})
        assert len(_trace(tmp_path).read()) == 1
        different = _trace(tmp_path)
        with pytest.raises(TraceError):
            different.append("progress", {"index": 99})
