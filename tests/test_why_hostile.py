"""why.explain() must name a refusal on a hostile record, never raise a bare
TypeError. The CLI catches only WhyError, so an AttributeError / TypeError /
KeyError that escapes explain() crashes the stranger asking "why was this
accepted?" instead of answering from the record.

Three escapes, each reproduced against the current code:

  WHY-1/2  a receipt whose criterion_sha256 or checker_source_sha256 is not a
           string clears Receipt.from_dict (which never type-checks those fields)
           and then dies on `body[field][:22]` in _what_would_change_it.
  WHY-3    a receipt whose claim_sha256 is an unhashable list, matched by prefix,
           dies building the digest set one line after the str()-guarded filter.
"""
import json

import pytest

import receipt_factories as factories
from harness.why import explain, WhyError


def _body(**over):
    body = factories.receipt().to_dict()
    body.update(over)
    return body


def _write(path, body):
    path.write_text(json.dumps({"schema": "flywheel.signed-receipt/v1",
                                "receipt": body, "signature": None}),
                    encoding="utf-8")


@pytest.mark.parametrize("field", ["criterion_sha256", "checker_source_sha256"])
def test_explain_names_a_non_string_digest_field_instead_of_crashing(tmp_path,
                                                                     field):
    p = tmp_path / "rec.json"
    _write(p, _body(**{field: 123}))
    with pytest.raises(WhyError):
        explain(p)


def test_explain_prefix_survives_an_unhashable_claim_digest(tmp_path):
    # str()-wrapped in the prefix filter but read raw into a set one line later;
    # a list claim_sha256 is unhashable, so the set construction raises TypeError.
    d = tmp_path / "d"
    d.mkdir()
    _write(d / "rec.json", _body(claim_sha256=[1, 2]))
    try:
        out = explain(d, prefix="[1")                  # must not raise TypeError
    except WhyError:
        return                                          # a named refusal is fine
    assert out["record_integrity"] == "DRIFT"
