"""D1, 7.2: with content capture off (the default) hooks send commitments and
salts only, so no byte of the prompt or answer lands anywhere under the home;
with it on, the text is kept encrypted and readable through the private
route. Both run through real hooks against a gateway on port 0."""
import json
import urllib.request

import pytest

from capture_channel_fixture import prompt_event, run_hook, running_gateway, stop_event
from trace_enc_fakes import StreamTestProvider, using
from turn_fixtures import custody_bytes, receipts

CANARY_PROMPT = "CANARY-OPTIN-PROMPT-" + "z9" * 6
CANARY_ANSWER = "CANARY-OPTIN-ANSWER-" + "w4" * 6


@pytest.fixture
def work(tmp_path):
    path = tmp_path / "work"
    path.mkdir()
    return path


def _turn(home, work):
    first = run_hook(home, "prompt", prompt_event(CANARY_PROMPT, prompt_id="pid-1"), cwd=work)
    second = run_hook(home, "stop", stop_event(CANARY_ANSWER, prompt_id="pid-1"), cwd=work)
    assert first.returncode == 0 and second.returncode == 0, (first.stderr, second.stderr)


def _absent(blob: bytes):
    for text in (CANARY_PROMPT, CANARY_ANSWER):
        assert text.encode("utf-8") not in blob and text.encode("utf-16-le") not in blob


def test_content_off_leaves_no_canary_byte_anywhere_under_the_home(tmp_path, work, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    with using(StreamTestProvider()), running_gateway(home, monkeypatch):
        _turn(home, work)
    data = receipts(home)[-1]["data"]
    assert data["pairing"] == "prompt_id" and data["captured_content"] is False
    assert any(p.name.startswith("store.db") for p in home.iterdir())
    _absent(custody_bytes(home))


def _adopt_content_on(home):
    from harness.operation_grants import load_or_create_owner_ref
    from harness.trace_capture_settings import adopt, write_file
    from harness.trace_presence import confirm
    from harness.trace_witness import MemorySink
    owner = load_or_create_owner_ref(home)
    settings = write_file(home, {"content": "on"})
    from harness.trace_capture_settings import digest
    ref = confirm(home / "state", owner, "capture_settings", digest(settings), "content on")
    adopt(home, owner, ref, sink=MemorySink())
    return owner


def _get(port, path, token):
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                     headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def test_content_on_keeps_the_text_encrypted_and_readable_through_the_route(
        tmp_path, work, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    with using(StreamTestProvider()), running_gateway(home, monkeypatch) as server:
        _adopt_content_on(home)
        _turn(home, work)
        port, token = server.server_address[1], (home / "gateway.token").read_text().strip()
        listing = _get(port, "/api/traces/turns", token)
        turn = _get(port, f"/api/traces/turns/{listing['turns'][0]['turn_ref']}", token)
    assert turn["prompt_text"] == CANARY_PROMPT and turn["answer_text"] == CANARY_ANSWER
    assert receipts(home)[-1]["data"]["captured_content"] is True
    _absent(custody_bytes(home))


def test_the_turn_route_needs_the_bearer_token_and_a_well_formed_ref(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    with running_gateway(home, monkeypatch) as server:
        port = server.server_address[1]
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/traces/turns", timeout=10)
        token = (home / "gateway.token").read_text().strip()
        with pytest.raises(urllib.error.HTTPError) as malformed:
            _get(port, "/api/traces/turns/..%2F..%2Fgateway.token", token)
    assert refused.value.code == 401 and malformed.value.code in (404, 422)
