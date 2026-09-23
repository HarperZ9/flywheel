"""The limit signal reads structured errors and separates anchored matches.

A limit phrase in a passing test log, a commit subject or a help text is a
mention. It is recorded, never acted on. A structured status or error field,
or a limit phrase on the last line of the output, is anchored, and only that
counts toward a breaker.
"""
import pytest

from harness.limit_signal import limit_match, limit_signal

PYTEST_IDS = ("test_client.py::test_retry[rate limit exceeded] PASSED [ 50%]\n"
              "test_client.py::test_retry[quota exceeded] PASSED [100%]\n"
              "============================== 2 passed in 0.05s ==============================")
OWN_SUITE = ("tests/test_run_budget.py::test_limit_signal_reads_each_kind_of_limit_error"
             "[Claude AI usage limit reached|1760000000-rate_limit] PASSED [ 14%]\n"
             "============================== 7 passed in 0.12s ==============================")


@pytest.mark.parametrize("text", [
    PYTEST_IDS, OWN_SUITE,
    "[fix/client 3f2a1b9] Retry on HTTP 429 from the upstream API\n 1 file changed, 12 insertions(+)",
    "3f2a1b9 Handle rate limit exceeded from GitHub\n9c1d2e0 Add CLI flag",
    "3f2a1b9 Handle rate limit exceeded from GitHub",
    "PASS  src/client.test.ts\n  retry\n    ✓ backs off when rate limited (4 ms)\n\n"
    "Tests:       2 passed, 2 total",
    "=== RUN   TestClient/rate_limit_exceeded\n    --- PASS: TestClient/rate_limit_exceeded (0.00s)\n"
    "PASS\nok  \texample.com/client\t0.012s",
    "usage: fetch [-h] [--retries N]\n  --retries N   retries after HTTP 429 (default 3)",
    "synced 120 rows; 0 requests were rate limited",
    "GET /v1/items -> status 429, retried after 2s; done: 50 items",
    "urllib3 Retrying after 429 Too Many Requests\nbackup complete",
    "checked api.example.com: status: 503 (maintenance window), alert sent",
    "skipping optional upload: not logged in to the mirror",
    "Added exponential backoff so the client retries when the API returns HTTP 429.",
])
def test_a_limit_phrase_in_ordinary_output_is_a_mention_not_an_anchored_signal(text):
    found = limit_match(text)
    assert found is None or found.anchored is False


@pytest.mark.parametrize("text,kind", [
    ("HTTP/2 429 \r\ncontent-type: application/json\r\nretry-after: 30\r\n", "rate_limit"),
    ("HTTP/1.1 429\r\nRetry-After: 30\r\n", "rate_limit"),
    ("HTTP/2 401 \r\nwww-authenticate: Bearer\r\n", "auth"),
    ('{"status": 429, "detail": "slow down"}', "rate_limit"),
    ('{"code": 402, "message": "Insufficient balance"}', "billing"),
    ('{"type":"error","error":{"type":"billing_error","message":"spend limit reached"}}',
     "billing"),
    ('{"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", '
     '"status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}', "auth"),
    ('{"error": {"type": "rate_limit_reached_error", "message": "slow down"}}', "rate_limit"),
    ('{"error": {"type": "exceeded_current_quota_error"}}', "quota"),
    ("Claude AI usage limit reached|1760000000", "rate_limit"),
    ("You've hit your weekly limit · resets Oct 1, 9am", "rate_limit"),
    ("You're out of extra usage", "billing"),
    ("Error: HTTP 429 Too Many Requests", "rate_limit"),
    ("npm ERR! 429 Too Many Requests", "rate_limit"),
    ("Invalid API key. Please run /login", "auth"),
])
def test_a_structured_or_last_line_limit_error_is_anchored(text, kind):
    found = limit_match(text)
    assert found is not None and found.kind == kind and found.anchored is True
    assert 0 < len(found.match) <= 80


def test_the_match_is_the_matched_words_and_nothing_around_them():
    found = limit_match("deploy log\nClaude AI usage limit reached|1760000000")
    assert found.match == "usage limit reached"
    assert limit_signal("see line 429 of parser.py") is None


def test_non_english_output_is_not_read():
    assert limit_signal("Fehler: Ratenlimit überschritten") is None
