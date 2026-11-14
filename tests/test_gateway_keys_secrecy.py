"""A virtual key is shown once, at creation, and appears nowhere after that.

One run mints a key through the CLI, uses it for a served call, a streamed
call, a budget refusal, an allow-list refusal and a revoked-key failure on a
real gateway, then searches everything the run produced for the raw key: the
ledger as JSONL, every `harness` log record at DEBUG, every response body and
header, what the upstream received, the index file's bytes, and the CLI's
`list` and `show` output. The same search is run for the key's name, which is
meant to appear in each of those places, so the search is shown to work.
"""
import re

import pytest

from harness import cli_entry, gateway_key_cli
from harness.gateway_keys import INDEX, PREFIX
from tests import gateway_messages_support as support
from tests.gateway_keys_support import (  # noqa: F401  (fixtures)
    BODIES, harness_log, keyed, post, served, stream_bytes, turn2)

NAME = "marker-name-7f3a"               # planted: the search must find this


def _cli(args, store, tmp_path, capsys) -> tuple:
    code = gateway_key_cli.main(args, store=store,
                                environ={"FLYWHEEL_HOME": str(tmp_path / "home")})
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _run(keyed, served, tmp_path, capsys, harness_log):
    """Everything one key's life produces, by where it was written."""
    keys, store = keyed
    code, created, _err = _cli(["create", NAME, "--token-limit", "900", "--models",
                                "claude-sonnet-5,gpt-5.3-codex"], store, tmp_path, capsys)
    found = re.findall(re.escape(PREFIX) + r"[A-Za-z0-9_-]+", created)
    assert code == 0 and len(found) == 1, "create prints the key exactly once"
    raw = found[0]
    url, upstream, ledger = served(turn2(1) + [
        support.stream_answer(stream_bytes("openai", "turn2"))])
    answers = [
        post(url, "/v1/messages", raw),                                     # served
        post(url, "/v1/responses", raw, {**BODIES["/v1/responses"], "stream": True},
             header="Authorization"),                                       # streamed
        post(url, "/v1/messages", raw),                                     # over budget
        post(url, "/v1/responses", raw),                                    # over budget
        post(url, "/v1/messages", raw, {**BODIES["/v1/messages"], "model": "other"}),
    ]
    assert [answer[0] for answer in answers] == [200, 200, 400, 429, 403]
    listed, shown = (_cli(["list"], store, tmp_path, capsys)[1],
                     _cli(["show", NAME], store, tmp_path, capsys)[1])
    assert _cli(["revoke", NAME], store, tmp_path, capsys)[0] == 0
    answers.append(post(url, "/v1/messages", raw))                          # revoked
    assert answers[-1][0] == 401
    after = _cli(["list"], store, tmp_path, capsys)[1] + _cli(["show", NAME], store, tmp_path,
                                                             capsys)[1]
    return raw, created, {
        "ledger": ledger.to_jsonl(),
        "logs": "\n".join(harness_log),
        "responses": "\n".join(f"{status} {headers!r} {body!r}"
                               for status, headers, body in answers),
        "upstream": repr(upstream.requests),
        "index": (tmp_path / "home" / INDEX).read_bytes().decode("utf-8"),
        "cli": listed + shown + after,
    }


def test_the_raw_key_appears_once_at_creation_and_nowhere_else(keyed, served, tmp_path, capsys,
                                                               harness_log):
    raw, created, written = _run(keyed, served, tmp_path, capsys, harness_log)
    assert created.count(raw) == 1
    secret = raw[len(PREFIX):]
    for place, text in written.items():
        assert text, f"nothing was captured for {place}"
        assert raw not in text and secret not in text, f"the key is in {place}"
        assert raw[:14] not in text, f"a leading part of the key is in {place}"


def test_control_the_same_search_finds_a_planted_marker(keyed, served, tmp_path, capsys,
                                                        harness_log):
    """The key's name is written to every place searched above. If a capture were
    empty or the wrong text, the secrecy test would pass for no reason."""
    _raw, _created, written = _run(keyed, served, tmp_path, capsys, harness_log)
    for place in ("ledger", "logs", "responses", "index", "cli"):
        assert NAME in written[place], f"the search does not reach {place}"
    assert "test-key" in written["upstream"]        # the upstream capture holds credentials
    assert "endpoint_call_refused" in written["ledger"] and "refused for key" in written["logs"]


def test_list_and_show_give_the_facts_and_never_the_key(keyed, tmp_path, capsys):
    keys, store = keyed
    code, created, _err = _cli(["create", "ci-bot", "--spend-limit", "2.5", "--price-in", "3",
                                "--price-out", "15", "--token-limit", "50000"],
                               store, tmp_path, capsys)
    assert code == 0 and "only time it is shown" in created
    keys.debit("ci-bot", {"input": 1000, "output": 500})
    fingerprint = keys.row("ci-bot")["fingerprint"]
    listed, shown = (_cli(["list"], store, tmp_path, capsys)[1],
                     _cli(["show", "ci-bot"], store, tmp_path, capsys)[1])
    assert re.search(rf"ci-bot\s+live\s+{fingerprint}\s+1500 of 50000 tokens; "
                     r"\$0\.010500 of \$2\.500000\s+calls 1", listed)
    assert "tokens        1500 = input 1000 + output 500" in shown
    assert "spend         0.0105 USD" in shown and "remaining     48500 tokens" in shown
    assert "remaining     2.4895 spend_usd" in shown and PREFIX not in listed + shown


def test_revoke_and_reset_report_what_they_did(keyed, tmp_path, capsys):
    keys, store = keyed
    _cli(["create", "ci-bot"], store, tmp_path, capsys)
    keys.debit("ci-bot", {"input": 9})
    assert "are zero" in _cli(["reset", "ci-bot"], store, tmp_path, capsys)[1]
    assert keys.row("ci-bot")["totals"]["tokens"] == 0
    code, out, _err = _cli(["revoke", "ci-bot"], store, tmp_path, capsys)
    assert code == 0 and "is revoked" in out and store.saved == {}
    assert re.search(r"ci-bot\s+revoked", _cli(["list"], store, tmp_path, capsys)[1])


@pytest.mark.parametrize("args, said", [
    (["create", "ci-bot", "--spend-limit", "5"], "a spend limit needs --price-in"),
    (["show", "nobody"], "no gateway key named 'nobody'"),
    (["revoke", "nobody"], "no gateway key named 'nobody'"),
    (["create", "bad name"], "a key name is 1 to 32 characters"),
])
def test_a_request_that_cannot_be_carried_out_exits_1_with_the_reason(keyed, tmp_path, capsys,
                                                                    args, said):
    _keys, store = keyed
    code, out, err = _cli(args, store, tmp_path, capsys)
    assert code == 1 and said in err and out == "" and store.saved == {}


def test_the_command_is_registered_and_its_help_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))
    assert cli_entry._PACKAGED["gateway-key"] == "harness.gateway_key_cli"
    assert cli_entry.main(["gateway-key", "--help"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("usage: flywheel gateway-key <command>")
    assert all(verb in out for verb in ("create NAME", "list", "show NAME", "revoke NAME",
                                        "reset NAME", "--spend-limit USD"))
    assert not (tmp_path / "home").exists()
    assert gateway_key_cli.main([]) == 2
