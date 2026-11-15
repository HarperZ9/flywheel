"""RFC 2119 / RFC 8174 keyword consistency under the rfc-keywords domain profile.

Positive and negative cases per rule, plus controls: the pack does not run
under a general profile or under normative-spec itself, and a declared
document's quoted boilerplate keywords never count as uses.
"""
import pytest

from articulate import checkext, detector, domains

BOILERPLATE = (
    'The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", '
    '"SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this '
    "document are to be interpreted as described in BCP 14 [RFC2119] [RFC8174] when, "
    "and only when, they appear in all capitals, as shown here.\n\n")


def _run(text, profile="rfc-keywords"):
    return checkext.check_text(text, profile=domains.load(profile))


def _cats(text, profile="rfc-keywords"):
    r = _run(text, profile)
    return {f["category"] for f in r["high"] + r["medium"] + r["low"]}


def test_mixed_case_keyword_gates():
    r = _run(BOILERPLATE + "A client MUST not retry.\n")
    assert "bcp14-mixed-case" in {f["category"] for f in r["high"]} and r["gate"] == "blocked"
    assert "bcp14-mixed-case" not in _cats(BOILERPLATE + "A client MUST NOT retry.\n")
    assert "bcp14-mixed-case" in _cats(BOILERPLATE + "A client should NOT retry.\n")


def test_keywords_without_boilerplate():
    assert "bcp14-no-boilerplate" in _cats("A client MUST retry.\n")
    assert "bcp14-no-boilerplate" not in _cats(BOILERPLATE + "A client MUST retry.\n")
    assert "bcp14-no-boilerplate" not in _cats("A client retries once.\n")


def test_may_not_is_not_a_keyword():
    assert "bcp14-may-not" in _cats(BOILERPLATE + "A client MAY NOT cache it.\n")
    assert "bcp14-may-not" not in _cats(BOILERPLATE + "A client MUST NOT cache it.\n")


def test_lowercase_keyword_only_in_a_declared_document():
    assert "bcp14-lowercase" in _cats(BOILERPLATE + "A server must reject it.\n")
    assert "bcp14-lowercase" not in _cats("A server must reject it.\n")
    assert "bcp14-lowercase" not in _cats(BOILERPLATE + "A server may reject it.\n")


def test_shall_and_must_mixed():
    assert "bcp14-shall-must" in _cats(BOILERPLATE + "A client MUST retry. A server SHALL log it.\n")
    assert "bcp14-shall-must" not in _cats(BOILERPLATE + "A client MUST retry. A server MUST log it.\n")


def test_quoted_boilerplate_keywords_are_not_uses():
    assert not {c for c in _cats(BOILERPLATE) if c.startswith("bcp14-")}


def test_old_boilerplate():
    old = ('The key words "MUST" and "MAY" in this document are to be interpreted as '
           "described in RFC 2119.\n\nA client MUST retry.\n")
    assert "bcp14-old-boilerplate" in _cats(old)
    assert "bcp14-old-boilerplate" not in _cats(BOILERPLATE + "A client MUST retry.\n")


def test_pack_runs_only_under_rfc_keywords():
    assert "bcp14-mixed-case" not in _cats("A client MUST not retry.\n", "flavored")
    assert "bcp14-mixed-case" in _cats("A client MUST not retry.\n", "rfc-keywords")


def test_normative_spec_keeps_its_published_findings():
    text = "A client MUST not retry.\n"
    spec = domains.load("normative-spec")
    assert "rule_packs" not in spec
    assert checkext.check_text(text, profile=spec) == detector.check_text(text, profile=spec)
