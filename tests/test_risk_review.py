"""Risk-tiered review: complexity, not provenance labels, is where
reviewers wave through wrong code — so every edit in a run carries
mechanical risk signals (size, nesting, branching, redundancy) and a tier,
and high-tier edits name the stronger receipt they demand. Signals from
the ledger only; the weights ship in the payload."""

import json

from harness.risk_review import SCHEMA, risk_review


def _e(kind, content, meta=None):
    return {"kind": kind, "content": content, "meta": meta or {}}


def _write(path, content):
    return _e("tool_call",
              f"write_file {json.dumps({'path': path, 'content': content}, sort_keys=True)}")


SIMPLE = "def f():\n    return 1\n"
GNARLY = (
    "def g(a, b):\n"
    "    for i in a:\n"
    "        if i > b:\n"
    "            for j in b:\n"
    "                if j:\n"
    "                    while j:\n"
    "                        if j > i:\n"
    "                            j -= 1\n"
    "    return a\n") * 6
DUPEY = ("x = compute(a, b, c)\n" * 12)


def test_a_one_liner_is_low_risk():
    doc = risk_review([_write("a.py", SIMPLE)])
    assert doc["schema"] == SCHEMA
    row = doc["edits"][0]
    assert row["tier"] == "low"
    assert doc["demands"] == []


def test_deep_branchy_code_is_high_risk_and_demands_more():
    doc = risk_review([_write("g.py", GNARLY)])
    row = doc["edits"][0]
    assert row["tier"] == "high"
    assert row["max_depth"] >= 5
    assert doc["demands"] and doc["demands"][0]["path"] == "g.py"
    assert "stronger receipt" in doc["demands"][0]["requires"]


def test_redundancy_is_counted_not_felt():
    doc = risk_review([_write("d.py", DUPEY)])
    row = doc["edits"][0]
    assert row["duplicate_lines"] >= 10


def test_weights_ship_in_the_payload_and_the_doc_is_deterministic():
    a = risk_review([_write("a.py", SIMPLE)])
    b = risk_review([_write("a.py", SIMPLE)])
    assert "weights" in a
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
