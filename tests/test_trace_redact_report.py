"""I10: reports count and never quote; tags are keyed; the guard classifier.

A redaction report travels with an export, so it must not carry what it
removed. Placeholder tags are an HMAC of the matched text under a key the
caller passes: the same value gets the same tag under one key, so a reader
can see that two redactions were the same secret, and a different tag under
another key, so two exports cannot be linked through their tags.
"""
import json

from harness import trace_redact
from trace_redact_fakes import credential_fakes

FAKES = credential_fakes()
KEY_A = b"planted-fake-redaction-key-aaaaaa"
KEY_B = b"planted-fake-redaction-key-bbbbbb"


def test_report_counts_per_rule_and_lines_and_never_quotes_matched_text():
    lines = [json.dumps({"t": FAKES["github_token"]}), "plain",
             json.dumps({"t": FAKES["jwt"] + " and " + FAKES["github_token"]})]
    out, report = trace_redact.redact_lines(lines, key=KEY_A)
    assert report["catalog_version"] == trace_redact.CATALOG_VERSION
    assert report["counts"] == {"github_token": 2, "jwt": 1}
    assert report["lines_affected"] == 2 and report["lines_scanned"] == 3
    raw = json.dumps(report)
    for fake in FAKES.values():
        assert fake not in raw
    assert out[1] == "plain"


def test_tag_is_stable_per_key_and_value_and_changes_with_the_key():
    token = FAKES["github_token"]
    line = f"{token} then {token} then {FAKES['npm_token']}"
    a1, _ = trace_redact.redact_line(line, key=KEY_A)
    a2, _ = trace_redact.redact_line(line, key=KEY_A)
    b1, _ = trace_redact.redact_line(line, key=KEY_B)
    tags_a = trace_redact.placeholder_tags(a1)
    assert a1 == a2
    assert tags_a[0] == tags_a[1] != tags_a[2]
    assert trace_redact.placeholder_tags(b1)[0] != tags_a[0]


def test_first_credential_rule_names_the_rule_or_unclassified():
    assert trace_redact.first_credential_rule(
        {"output": "x " + FAKES["jwt"]}) == "jwt"
    assert trace_redact.first_credential_rule(
        ["a", {"b": FAKES["github_token"]}]) == "github_token"
    assert trace_redact.first_credential_rule({"password": "hunter2hunter2"}) == \
        "credential_assignment"
    assert trace_redact.first_credential_rule({"note": "nothing here"}) == "unclassified"


def test_personal_rules_never_classify_a_guard_refusal():
    assert trace_redact.first_credential_rule("mail jane.doe@example.org") == "unclassified"


def test_redaction_key_must_be_bytes_of_reasonable_length():
    for bad in (b"", "text-key", b"short"):
        try:
            trace_redact.redact_line("x", key=bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted key {bad!r}")
