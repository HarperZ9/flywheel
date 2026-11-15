"""C3a: `disclose` prints the canonical CRediT role strings.

NISO's CRediT standard names two roles with an en dash and an ampersand:
"Writing – original draft" and "Writing – review & editing". A statement
that rewrites them to "Writing - review and editing" no longer matches the role
list a journal's submission system reads. The input may use either form; the
output uses the standard's.
"""
import pytest

from articulate import disclose

ORIGINAL = "Writing – original draft"
REVIEW = "Writing – review & editing"


@pytest.mark.parametrize("given", [
    ["Writing - original draft", "Writing - review and editing"],
    [ORIGINAL, REVIEW],
    ["Writing " + chr(0x2014) + " original draft", "Writing – review and editing"],
])
def test_the_statement_prints_the_niso_role_strings(given):
    s = disclose.build([], {"authors": [{"name": "Maria Lopez",
                                         "roles": ["Conceptualization", *given]}]})
    assert f"- Maria Lopez: Conceptualization; {ORIGINAL}; {REVIEW}." in s


def test_every_listed_role_prints_as_the_standard_names_it():
    roles = list(disclose.CANONICAL_ROLES)
    assert len(roles) == 14 and ORIGINAL in roles and REVIEW in roles
    s = disclose.build([], {"authors": [{"name": "Maria Lopez", "roles": roles}]})
    assert "; ".join(roles) in s
