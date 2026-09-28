"""A JSON parser keeps only the last of two equal keys, so a secret under the
first one never reaches the value walk. A line (or a nested JSON string) with
a duplicate key is scanned as raw text instead, and the secret is redacted."""
import json

from harness import trace_redact
from trace_redact_fakes import credential_fakes

KEY = b"planted-fake-redaction-key-000000"
FAKES = credential_fakes()


def test_a_secret_under_a_shadowed_duplicate_key_is_redacted():
    token = FAKES["github_token"]
    line = '{"text": "%s", "text": "harmless"}' % token
    out, counts = trace_redact.redact_line(line, key=KEY)
    assert token not in out and counts


def test_a_duplicate_key_inside_a_nested_json_string_is_redacted():
    token = FAKES["github_token"]
    inner = '{"a": "%s", "a": "harmless"}' % token
    line = json.dumps({"content": inner})
    out, counts = trace_redact.redact_line(line, key=KEY)
    assert token not in out and counts


def test_a_line_without_duplicates_still_round_trips_unchanged():
    line = json.dumps({"text": "harmless", "other": "fine"})
    assert trace_redact.redact_line(line, key=KEY) == (line, {})
