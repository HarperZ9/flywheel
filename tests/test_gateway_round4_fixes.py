"""Round 4 gateway fixes: findings R2 and R10 of the third independent review.

R2   an unfinished stream is charged for the whole request, tool definitions
     included, and no longer for the system prompt and message text alone;
R10  `gateway-ledger show --json` escapes C1 and bidi control characters.

R5 and R6 are in tests/test_gateway_ledger_round4.py.

A real gateway on a loopback port, a stub upstream, keys in the in-memory
store. No provider is called.
"""
import json

import pytest

from tests import gateway_messages_support as support
from tests.gateway_contact_support import PATHS, calls, raw_post
from tests.gateway_keys_support import (  # noqa: F401  (fixtures)
    BODIES, keyed, post, served, stream_bytes, turn2)

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release


# --- R2 ------------------------------------------------------------------------------------

LONG = "QUJD" * 20000                   # 80,000 characters with no space


def _with_tool(path: str, description: str) -> bytes:
    tool = ({"name": "look", "description": description, "input_schema": {"type": "object"}}
            if path == "/v1/messages" else
            {"type": "function", "name": "look", "description": description,
             "parameters": {"type": "object"}})
    return json.dumps({**BODIES[path], "stream": True, "tools": [tool]}).encode()


@pytest.mark.parametrize("path", PATHS)
def test_r2_an_unfinished_stream_is_charged_for_its_tool_definitions(keyed, served, path):
    """The reviewer's probe: 80,000 characters in one tool description, a limit of 1,000."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", token_limit=1000)
    whole = stream_bytes("openai", "turn2")
    cut = whole[:whole.index(b"\n\n", len(whole) // 2) + 2]     # the usage chunk never comes
    url, upstream, ledger = served([support.stream_answer(cut)] * 5)
    body = _with_tool(path, LONG)
    statuses = [raw_post(url, path, raw, body)[0] for _ in range(5)]
    assert len(upstream.requests) == 1, (
        f"{len(upstream.requests)} of 5 unfinished calls reached the upstream")
    entry, = calls(ledger)
    assert entry.kind == "endpoint_call_failed" and entry.meta["estimated"] is True
    assert entry.meta["charged_tokens"] >= len(LONG) // 4
    assert keys.row("ci-bot")["totals"]["tokens"] == entry.meta["charged_tokens"]
    assert statuses[0] == 200 and set(statuses[1:]) <= {400, 429}


def test_r2_control_a_short_request_is_charged_as_before_plus_its_own_bytes(keyed, served):
    """A request with no tools: the charge is still an estimate of the same order."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    whole = stream_bytes("openai", "turn2")
    cut = whole[:whole.index(b"\n\n", len(whole) // 2) + 2]
    url, _upstream, ledger = served([support.stream_answer(cut)])
    body = json.dumps({**BODIES["/v1/messages"], "stream": True}).encode()
    assert raw_post(url, "/v1/messages", raw, body)[0] == 200
    entry, = calls(ledger)
    assert 0 < entry.meta["charged_tokens"] <= len(body), "bounded by the request's size"


def test_r2_the_input_estimate_is_at_least_the_calls_own_reservation():
    from harness import gateway_unaccounted

    class Keys:
        def debit(self, name, counts, estimated):
            self.counts = counts

    class Caller:
        row, name, keys, ticket = {}, "k", Keys(), [5000, 64]

    class Turn:
        caller = Caller()

        def text_form(self):
            return "", "short prompt"
    began = type("A", (), {"began": True})()
    charged = gateway_unaccounted.partial_charge(Turn(), "client_disconnected", began, [])
    assert Caller.keys.counts["input"] == 5000 and charged["charged_tokens"] >= 5000
    Caller.ticket = None                    # no reservation (the owner, or a direct call)
    charged = gateway_unaccounted.partial_charge(Turn(), "client_disconnected", began, [])
    assert Caller.keys.counts["input"] == 4     # a quarter of 13 characters, rounded up


# --- R10 -----------------------------------------------------------------------------------

HOSTILE = ("ok\x1b[2J", "c1 \x85\x9b\x90", "bidi \u202e\u2066\u200f", "del \x7f", "nul \x00",
           "line \u2028\u2029", "plain \u6f22\u5b57 \U0001f600")


@pytest.mark.parametrize("flags", [["--json"], ["--json", "--full"], [], ["--full"]])
def test_r10_show_prints_no_control_character_from_a_recorded_string(tmp_path, capsys, flags):
    from harness import gateway_ledger, gateway_ledger_cli
    ledger = gateway_ledger.GatewayLedger(tmp_path)
    for index, text in enumerate(HOSTILE):
        ledger.append("endpoint_call", "sha", {"key": "owner", "model_ref": text,
                                               "reason": text, "n": index})
    ledger.close()
    assert gateway_ledger_cli.main(["show", *flags], environ={"FLYWHEEL_HOME": str(tmp_path)}) == 0
    out = capsys.readouterr().out
    raw = sorted({ch for ch in out if ch != "\n" and not (" " <= ch <= "~")})
    assert raw == [], f"printed raw: {[hex(ord(ch)) for ch in raw]}"
    if "--json" in flags:                   # a parser still reads back what was recorded
        rows = [json.loads(line) for line in out.splitlines()]
        assert [row["meta"]["model_ref"] for row in rows] == list(HOSTILE)
