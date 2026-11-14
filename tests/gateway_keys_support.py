"""Helpers for the gateway virtual-key tests.

Every test key goes into `FakeStore`, an in-memory stand-in for the system
credential store. `keyed` puts that store behind the gateway and behind the
CLI and makes the real credential-store functions raise, so a test that
reached the real store would fail instead of writing to it. No provider is
called; upstream replies are the recordings the interface tests replay.

Error shapes, read 2026-11-14:
  https://platform.claude.com/docs/en/api/errors
      400 invalid_request_error for a reached spend limit, 401
      authentication_error, 403 permission_error
  https://developers.openai.com/api/docs/guides/error-codes
      spend limits are listed under 429; "The broader `error.type` can still
      be `insufficient_quota`"
"""
import json
import logging
import urllib.error
import urllib.request

import pytest

from harness import gateway_key_gate, gateway_keys, keychain
from tests import gateway_messages_support as support
from tests.hosted_stream_fixtures import plain_object, stream_bytes  # noqa: F401

MESSAGES = {"model": "claude-sonnet-5", "max_tokens": 64,
            "messages": [{"role": "user", "content": "What changed?"}]}
RESPONSES = {"model": "gpt-5.3-codex", "input": "What changed?"}
BODIES = {"/v1/messages": MESSAGES, "/v1/responses": RESPONSES}
TURN2_TOKENS = 460                      # openai/turn2: 451 prompt + 9 completion


class FakeStore:
    """The credential store, in memory. `saved` maps a slot name to its secret."""

    def __init__(self, present: bool = True):
        self.saved, self.present = {}, present

    def available(self) -> bool:
        return self.present

    def get(self, name):
        return self.saved.get(name)

    def set(self, name, secret):
        self.saved[name] = secret
        return {"stored": name}

    def delete(self, name):
        return ({"deleted": name} if self.saved.pop(name, None) is not None
                else {"error": f"no stored credential named '{name}'"})


def _real_store_reached(*args, **kwargs):
    raise AssertionError("a test reached the real credential store")


@pytest.fixture
def keyed(monkeypatch, tmp_path):
    """(keys, store): the key list of the test gateway's home, on a fake store."""
    for name in ("keychain_get", "keychain_set", "keychain_delete"):
        monkeypatch.setattr(keychain, name, _real_store_reached)
    store, home = FakeStore(), tmp_path / "home"
    monkeypatch.setattr(gateway_key_gate, "open_keys",
                        lambda where: gateway_keys.Keys(where, store=store))
    return gateway_keys.Keys(home, store=store), store


@pytest.fixture
def served(monkeypatch, tmp_path):
    """start(answers, provider) points a real gateway at a stub upstream."""
    opened = []

    def start(answers, provider="openai"):
        upstream = support.Upstream(answers).__enter__()
        gate = support.gateway_server(monkeypatch, tmp_path)
        url, ledger = gate.__enter__()
        opened.extend([gate, upstream])
        support.point_at(monkeypatch, provider, upstream.url)
        return url, upstream, ledger
    yield start
    for item in opened:
        item.__exit__(None, None, None)


def post(url, path, key, body=None, header="x-api-key"):
    """POST a body with a credential; (status, headers, parsed body or raw bytes)."""
    sent = {"Content-Type": "application/json"}
    if key:
        sent[header] = f"Bearer {key}" if header == "Authorization" else key
    request = urllib.request.Request(
        url + path, data=json.dumps(BODIES.get(path) if body is None else body).encode(),
        method="POST", headers=sent)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status, headers, raw = response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        status, headers, raw = error.code, dict(error.headers), error.read()
    try:
        return status, headers, json.loads(raw)
    except ValueError:
        return status, headers, raw


def turn2(count: int = 1) -> list:
    """`count` plain OpenAI-format replies, each reporting 451 in and 9 out."""
    return [support.json_answer(plain_object("openai", "turn2")) for _ in range(count)]


def no_usage(count: int = 1) -> list:
    """`count` plain OpenAI-format replies that report no token counts."""
    return [support.json_answer(support.load("upstream/openai_no_usage.json"))
            for _ in range(count)]


class Records(logging.Handler):
    """Every log record of the `harness` loggers, at DEBUG, as formatted text."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        self.lines.append(f"{record.name} {record.getMessage()} {record.args!r}")


@pytest.fixture
def harness_log():
    handler, logger = Records(), logging.getLogger("harness")
    before = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield handler.lines
    finally:
        logger.removeHandler(handler)
        logger.setLevel(before)
