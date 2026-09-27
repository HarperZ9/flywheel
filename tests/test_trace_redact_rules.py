"""I10: every catalog rule replaces its fake with a typed placeholder, once.

Fakes are built at run time (tests/trace_redact_fakes.py). Credential rules
run by default; personal rules run on request, and IP and coordinate rules
also need to be named, because logs are full of them.
"""
import re

import pytest

from harness import trace_redact, trace_redact_rules as rules
from trace_redact_fakes import credential_fakes, personal_fakes

KEY = b"planted-fake-redaction-key-000000"
PLACEHOLDER = re.compile(r"\[REDACTED:([a-z0-9_]+):([0-9a-f]{8})\]")


def test_catalog_version_is_exported_and_every_rule_has_a_fake():
    assert rules.CATALOG_VERSION == "trace-redact/2026-09-26.3"
    assert trace_redact.CATALOG_VERSION == rules.CATALOG_VERSION
    ids = {r.id for r in rules.RULES}
    assert ids == set(credential_fakes()) | set(personal_fakes())
    for rule in rules.RULES:
        assert rule.cls in {"credential", "personal"} and rule.note.strip()


@pytest.mark.parametrize("rule_id, fake", sorted(credential_fakes().items()))
def test_each_credential_rule_replaces_its_fake_and_counts_one(rule_id, fake):
    out, counts = trace_redact.redact_line(fake, key=KEY)
    assert counts == {rule_id: 1}, counts
    assert [m.group(1) for m in PLACEHOLDER.finditer(out)] == [rule_id]


@pytest.mark.parametrize("rule_id, fake", sorted(personal_fakes().items()))
def test_each_personal_rule_replaces_its_fake_and_counts_one(rule_id, fake):
    out, counts = trace_redact.redact_line(fake, key=KEY, personal=True,
                                           enable=("ipv4", "ipv6", "lat_long"))
    assert counts == {rule_id: 1}, counts
    assert [m.group(1) for m in PLACEHOLDER.finditer(out)] == [rule_id]


def test_personal_rules_are_off_by_default_and_ip_rules_need_naming():
    fakes = personal_fakes()
    for text in fakes.values():
        assert trace_redact.redact_line(text, key=KEY) == (text, {})
    for rule_id in ("ipv4", "ipv6", "lat_long"):
        assert trace_redact.redact_line(fakes[rule_id], key=KEY, personal=True)[1] == {}


@pytest.mark.parametrize("number", ["4111 1111 1111 1112", "1234567812345678",
                                    "0000 0000 0000 0001"])
def test_luhn_invalid_numbers_are_kept(number):
    text = f"order {number} shipped"
    assert trace_redact.redact_line(text, key=KEY, personal=True) == (text, {})


@pytest.mark.parametrize("url", [
    "https://docs.example/page?code=print&lang=py",
    "https://shop.example/item?code=AB12CD",
])
def test_a_bare_code_parameter_is_kept(url):
    assert trace_redact.redact_line(url, key=KEY) == (url, {})


def test_an_invalid_ssn_range_and_a_bad_iban_checksum_are_kept():
    for text in ("id 000-12-3456 here", "id 666-12-3456 here", "id 900-12-3456 here",
                 "pay GB82 WEST 1234 5698 7654 33 now"):
        assert trace_redact.redact_line(text, key=KEY, personal=True) == (text, {})


def test_a_jwt_shape_without_a_json_header_is_kept():
    text = "eyJ" + "a" * 20 + ".eyJ" + "b" * 20 + "." + "c" * 20
    assert trace_redact.redact_line(text, key=KEY) == (text, {})


def test_surrounding_text_survives_and_only_the_secret_span_goes():
    fake = credential_fakes()["github_token"]
    out, counts = trace_redact.redact_line(f"push with {fake} then stop", key=KEY)
    assert out.startswith("push with [REDACTED:github_token:") and out.endswith("] then stop")
    assert fake not in out and counts == {"github_token": 1}
