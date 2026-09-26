"""I10: the catalog says what it misses, and each miss is asserted.

A redaction pass that is trusted beyond what it does leaks the rest. Every
documented miss below passes through unchanged with every rule switched on,
and `docs/trace-redaction.md` lists exactly these misses, no more and no less.
The list is the known misses, not a complete one.
"""
import base64
import json
from pathlib import Path
import re
import zlib

import pytest

from harness import trace_redact, trace_redact_rules as rules

KEY = b"planted-fake-redaction-key-000000"
ALL = ("ipv4", "ipv6", "lat_long")
DOC = Path(__file__).resolve().parents[1] / "docs" / "trace-redaction.md"


def _deep(depth: int) -> str:
    value = json.dumps({"api_key": "correcthorsebattery"})
    for _ in range(depth):
        value = json.dumps({"wrapped": value})
    return json.dumps({"payload": value})


MISSES = {
    "password_without_named_key": "the login for the router is hunter2hunter2",
    "secret_split_across_lines": '{"a": "push with gh"}\n{"b": "' + "p_" + "x" * 36 + '"}',
    "encoded_secret": base64.b64encode(("gh" + "p_" + "x" * 36).encode()).decode(),
    "custom_token_format": "acme" + "_live_" + "q" * 32,
    "bare_azure_key": "A" * 86 + "==",
    "secret_in_binary_content": base64.b64encode(
        zlib.compress(("sk-" + "proj-" + "a" * 40).encode())).decode(),
    "personal_free_text": "Jane Doe lives at 12 Elm Street, born 1990-01-02, has asthma",
    "national_id_other_than_ssn_or_iban": "NINO QQ 12 34 56 C and SIN 046 454 286",
    "unicode_lookalike": "ghр_" + "x" * 36,
    "json_nested_deeper_than_four_levels": _deep(5),
}


@pytest.mark.parametrize("miss_id", sorted(MISSES))
def test_each_documented_miss_passes_through_unchanged(miss_id):
    text = MISSES[miss_id]
    for line in text.split("\n"):
        assert trace_redact.redact_line(line, key=KEY, personal=True, enable=ALL) == (line, {})


@pytest.mark.parametrize("depth", [0, 3, 4])
def test_nesting_up_to_the_boundary_is_still_found(depth):
    """The boundary of the nesting miss. Four levels are parsed, and the fifth
    is a decoded string the assignment rule still reads; past that, escapes
    hide the assignment and only the key name would have given it away."""
    out, counts = trace_redact.redact_line(_deep(depth), key=KEY)
    assert counts == {"credential_assignment": 1} and "correcthorsebattery" not in out


def test_the_catalog_and_the_doc_list_exactly_the_asserted_misses():
    assert {m for m, _ in rules.DOCUMENTED_MISSES} == set(MISSES)
    rows = re.findall(r"^\| `([a-z0-9_]+)` \|", DOC.read_text(encoding="utf-8"), re.M)
    misses_section = DOC.read_text(encoding="utf-8").split("## What it does not detect", 1)[1]
    listed = re.findall(r"^\| `([a-z0-9_]+)` \|", misses_section, re.M)
    assert set(listed) == set(MISSES) and len(listed) == len(MISSES)
    assert {r.id for r in rules.RULES} <= set(rows)
