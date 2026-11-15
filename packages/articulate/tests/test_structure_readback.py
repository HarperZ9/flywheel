"""A reader's readback as an acceptance test.

Each file in tests/fixtures/structure/readback/ is one text a person read and
judged: the text, the spans the reader objected to, and the rule the reader
named for each span. This test runs the checker under the case's profile and
reports, for each rule the reader named, how many marked spans a finding of
that rule touches (recall), at any tier and at the gating tier.

The counts are pinned in readback/recall.json. A change that moves a count
fails here until recall.json changes with it, so a lost detection and a
gained one both show up in review. A reader's rule with no detector stays in
the set as a miss. A text the reader accepted must raise no gating finding.

Run `python tests/test_structure_readback.py` for the table. The folder's
README.md says how to add a case.
"""
import json
import pathlib
import sys

import pytest

from articulate import checkext, domains

READBACK = pathlib.Path(__file__).parent / "fixtures" / "structure" / "readback"

# A reader names a rule in house words. Each maps to the finding categories
# that answer it. An empty set is a rule no detector covers yet.
RULES = {
    "anaphora": {"structure-anaphora"},
    "rule of three": {"structure-triad"},
    "parallel sentence structures": {"structure-parallel"},
    "paragraph pinning": {"structure-pin"},
    "parataxis": {"structure-parataxis"},
    "landing sentences": {"structure-landing"},
    "hand-back formula": {"structure-landing"},
    "setup and payoff": {"structure-pin", "structure-pointer"},
    "summary beats": {"structure-pointer"},
    "register": set(),
}


def cases():
    out = []
    for path in sorted(READBACK.glob("*.json")):
        if path.name == "recall.json":
            continue
        case = json.loads(path.read_text(encoding="utf-8"))
        if "text" not in case:
            case["text"] = (path.parent / case["text_file"]).read_text(encoding="utf-8")
        out.append(case)
    return out


def span(text, mark):
    """(start, end) of a mark: from its `starts` words to the end of the first
    `ends` words at or after them."""
    start = text.index(mark["starts"])
    end = text.index(mark["ends"], start) + len(mark["ends"])
    return start, end


def findings(case):
    r = checkext.check_text(case["text"], profile=domains.load_profile(case["profile"]))
    return [f for tier in ("high", "medium") for f in r[tier]], r


def recall():
    """{rule: {"marks", "reported", "gating"}} over every objected case."""
    table = {}
    for case in cases():
        found, _r = findings(case)
        for mark in case["marks"]:
            start, end = span(case["text"], mark)
            hit = [f for f in found if f["category"] in RULES[mark["rule"]]
                   and f["start"] < end and f["end"] > start]
            row = table.setdefault(mark["rule"], {"marks": 0, "reported": 0, "gating": 0})
            row["marks"] += 1
            row["reported"] += bool(hit)
            row["gating"] += any(f["tier"] == "HIGH" for f in hit)
    return dict(sorted(table.items()))


def report(table):
    lines = ["%-30s %5s %8s %6s" % ("rule the reader named", "marks", "reported", "gating")]
    lines += ["%-30s %5d %8d %6d" % (rule, row["marks"], row["reported"], row["gating"])
              for rule, row in table.items()]
    total = [sum(row[key] for row in table.values()) for key in ("marks", "reported", "gating")]
    return "\n".join(lines + ["%-30s %5d %8d %6d" % ("all", *total)])


def test_every_case_is_well_formed():
    seen = set()
    for case in cases():
        assert case["id"] not in seen, case["id"]
        seen.add(case["id"])
        assert case["verdict"] in ("objected", "accepted"), case["id"]
        assert case["profile"] in domains.names() and case["read_on"] and case["source"]
        assert bool(case["marks"]) == (case["verdict"] == "objected"), case["id"]
        for mark in case["marks"]:
            assert mark["rule"] in RULES, (case["id"], mark["rule"])
            assert mark["reader_said"].strip(), case["id"]
            start, end = span(case["text"], mark)
            assert 0 <= start < end <= len(case["text"])
    assert {"specimen-a", "specimen-b", "counterpart"} <= seen


def test_recall_against_the_reader_matches_the_pinned_table():
    table = recall()
    pinned = json.loads((READBACK / "recall.json").read_text(encoding="utf-8"))["recall"]
    assert table == pinned, "recall moved; update readback/recall.json in this change\n" + report(
        table)


def test_each_rule_with_a_detector_reports_every_marked_span():
    for rule, row in recall().items():
        if RULES[rule]:
            assert row["reported"] == row["marks"], "%s\n%s" % (rule, report(recall()))


def test_a_rule_with_no_detector_is_counted_as_a_miss():
    row = recall()["register"]
    assert row["marks"] >= 1 and row["reported"] == 0


@pytest.mark.parametrize("case", [c for c in cases() if c["verdict"] == "accepted"],
                         ids=lambda c: c["id"])
def test_an_accepted_text_raises_no_gating_finding(case):
    found, r = findings(case)
    assert r["gate"] == "ok", [f["rule_id"] for f in found]


@pytest.mark.parametrize("case", [c for c in cases() if c["verdict"] == "objected"],
                         ids=lambda c: c["id"])
def test_an_objected_text_is_flagged(case):
    _found, r = findings(case)
    assert r["verdict"] == "flagged"


if __name__ == "__main__":
    sys.stdout.write(report(recall()) + "\n")
