"""One gateway model call in a process that is killed at a chosen point.

Run by tests/test_gateway_write_ahead.py as a child process:

    python -m tests.gateway_crash_child HOME UPSTREAM_URL KEY_NAME KEY_FINGERPRINT POINT

It opens HOME's on-disk gateway ledger, makes one plain /v1/messages call for
the key against the stub at UPSTREAM_URL, and dies at POINT with `os._exit`:
no `finally`, no `atexit`, no flush. That is what a killed process leaves.

  before_start      before the started entry is appended
  start_written     the started line is written and its commit has not returned
  before_send       the started entry is committed; the request has not left
  after_reply       the provider answered; the end entry is not written
  end_written       the end line is written and its commit has not returned
  done              the call returned

Exit code 9 means it died where it was told to. No provider is called.
"""
import os
import sys

DIED = 9
POINTS = ("before_start", "start_written", "before_send", "after_reply", "end_written", "done")


def _die(*_args, **_kwargs):
    os._exit(DIED)


def main(argv) -> int:
    home, url, name, fingerprint, point = argv
    from harness import (endpoints_http, gateway_calls, gateway_key_gate, gateway_keys,
                         gateway_ledger, gateway_ledger_health, gateway_messages, gateway_turn)
    from harness.endpoints import OpenAICompatBackend
    gateway_turn.make_backend = lambda _name, _model: ("openai", OpenAICompatBackend(
        name="openai", base_url=f"{url}/v1", model="gpt-5.3-codex-spark", api_key="test-key"))
    ledger = gateway_ledger.GatewayLedger(home)
    keys = gateway_keys.Keys(home, store=object())      # a debit reads and writes the index only
    caller = gateway_key_gate.Caller(name, fingerprint, keys.row(name), keys, ticket=[25, 64])
    real_fsync, real_guard, commits = os.fsync, endpoints_http._guard, []

    def fsync(fd):
        commits.append(fd)
        if (point, len(commits)) in (("start_written", 1), ("end_written", 2)):
            _die()
        return real_fsync(fd)

    def guard(transport, *args, **kwargs):
        if point == "before_send":
            _die()
        answer = real_guard(transport, *args, **kwargs)
        if point == "after_reply":
            _die()
        return answer
    gateway_ledger_health.os.fsync = fsync
    endpoints_http._guard = guard
    if point == "before_start":
        gateway_calls.begin = _die
    body = {"model": "claude-sonnet-5", "max_tokens": 64,
            "messages": [{"role": "user", "content": "What changed?"}]}
    answer = gateway_messages.handle(body, {}, ledger, environ={
        gateway_turn.UPSTREAM_ENV: "openai"}, caller=caller)
    if point == "done" and answer.status == 200:
        _die()
    return 1                            # the call ended without reaching the point


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
