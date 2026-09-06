"""The published benchmark surface has to agree with a fresh run.

Two documents are generated from one sealed record: site/benchmarks.html and
docs/BENCHMARKS.md. The danger with generated surfaces is not that the
generator is wrong, it is that someone edits a number on the page or changes
a suite and forgets to regenerate. These tests re-run the measurement, seal
it again, and compare, so the page cannot quietly say something the code no
longer does.

The run takes a few seconds. That is the price of a page whose numbers are
checked rather than trusted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts import build_benchmark_page as page  # noqa: E402
from scripts import run_offline_benchmarks as bench  # noqa: E402

RECORD = REPO / "docs" / "benchmarks" / "report.json"
HTML = REPO / "site" / "benchmarks.html"
MARKDOWN = REPO / "docs" / "BENCHMARKS.md"


def _record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_the_committed_record_matches_a_fresh_run():
    """Re-measure and compare the seal.

    The seal covers the results and skips the timings, so a machine that runs
    slower still agrees. A mismatch here means the committed record is stale
    and `python scripts/run_offline_benchmarks.py` has not been re-run.
    """
    fresh = bench.run_all()
    committed = _record()
    assert fresh["result_sha256"] == committed["result_sha256"], (
        "docs/benchmarks/report.json is stale; re-run "
        "scripts/run_offline_benchmarks.py then scripts/build_benchmark_page.py")


def test_a_changed_number_changes_the_seal():
    """The falsifier for the seal itself.

    If the hash did not move when a result moved, every test above it would
    pass while the page said whatever it liked. Sealed here by the runner's
    own function, because a second copy of the rule would let the two drift
    and this test would then be checking the copy.
    """
    report = _record()
    report["suites"][0]["headline"]["harness_overall"] = 0.5
    changed = bench.seal(report["suites"], report["parity"])
    assert changed != report["result_sha256"]


def test_a_timing_a_suite_declared_unsealed_leaves_the_seal_alone():
    """The other half of the same mechanism.

    A suite may name figures that belong to the machine that ran it. Those
    have to be out of the seal or a reader on a different disk sees a stale
    record where there is none. The declaration is narrow: only the names the
    suite listed move freely, and the list itself is sealed, so widening it
    later shows up as a mismatch.
    """
    report = _record()
    suite = next(s for s in report["suites"] if s.get("unsealed"))
    before = bench.seal(report["suites"], report["parity"])
    assert before == report["result_sha256"]
    for name in suite["unsealed"]:
        if name in suite["headline"]:
            suite["headline"][name] = 99999
    assert bench.seal(report["suites"], report["parity"]) == before
    # And the numbers it did not declare still hold the gate shut.
    suite["headline"]["log_bytes_per_action"] = 1.0
    assert bench.seal(report["suites"], report["parity"]) != before


def test_the_page_and_the_doc_match_the_record():
    """Both rendered files are byte-identical to what the builder produces."""
    for rel, text in page.build().items():
        current = (REPO / rel).read_text(encoding="utf-8")
        assert current == text, (
            f"{rel} is out of date; re-run scripts/build_benchmark_page.py")


def test_every_unmeasured_suite_says_what_it_needs():
    """An absent number has to read as unmeasured, never as zero."""
    for entry in _record()["not_run"]:
        assert entry["suite"] and entry["needs"] and entry["where"]
        assert entry["suite"] in MARKDOWN.read_text(encoding="utf-8")


def test_the_capability_null_survives_onto_the_page():
    """The July uplift interval includes zero and the page still says so.

    This is the claim most likely to get quietly upgraded on a marketing
    pass, which is why it is pinned to the rendered surface and not only to
    the record.
    """
    html = HTML.read_text(encoding="utf-8")
    assert "[-0.236, +0.420]" in html
    assert "no capability uplift is claimed" in html


def test_the_negative_result_reaches_the_page_with_its_caveats():
    """The unfavourable number is published, and so is what it does not show.

    A caveat that lives only in the record lets the page present a number as
    cleaner than it is, so the caveats are pinned to the rendered surface the
    same way the capability null is.
    """
    html = HTML.read_text(encoding="utf-8")
    doc = MARKDOWN.read_text(encoding="utf-8")
    suite = next(s for s in _record()["suites"]
                 if s["name"] == "paired-replication")
    assert suite["headline"]["delta_points"] < 0
    assert "-3.05 pp" in html
    for caveat in suite["caveats"]:
        assert caveat in html, caveat[:40]
        assert caveat in doc, caveat[:40]


def test_the_retired_instrument_is_named_as_retired():
    """The arms comparison is void, not merely inconclusive.

    Saying only that the interval includes zero would leave a reader thinking
    a bigger sample settles it. It does not: the arms were not independent.
    """
    for text in (HTML.read_text(encoding="utf-8"),
                 MARKDOWN.read_text(encoding="utf-8"),
                 (REPO / "README.md").read_text(encoding="utf-8")):
        assert "retired on 2026-07-26" in text
        assert "is not a comparison" in text


def test_the_page_carries_every_matrix_row():
    from harness.parity import parity_matrix
    html = HTML.read_text(encoding="utf-8")
    for row in parity_matrix()["rows"]:
        assert row["key"] in html, row["key"]


def test_a_star_count_never_travels_without_its_denominator():
    """The defect this replaces: 27 rows marked "no listed peer declares
    them" over a three-peer table, where a cell nobody had read counted the
    same as a cell read and found absent.

    The count is only meaningful beside two other numbers, so both surfaces
    have to carry all three: how many peers it was measured against, and how
    many rows still hold a surface nobody here has read.
    """
    from harness.parity import parity_matrix
    doc = parity_matrix()
    peers, s = doc["peers"], doc["summary"]
    for text in (HTML.read_text(encoding="utf-8"),
                 MARKDOWN.read_text(encoding="utf-8")):
        assert f"all {len(peers)} peers were read" in text
        assert f"{len(s['undetermined'])} rows carry at least one peer" in text
        # The wording changes at zero, to the stronger claim that nothing is
        # being held back. A surface making that claim while rows are still
        # unread would be reading its own star count in our favour.
        withheld = "a star is withheld" in text
        assert withheld == bool(s["undetermined"]), (
            "the surface says a star is withheld and no row is unread"
            if withheld else
            "rows are unread and the surface does not say a star is withheld")
        for peer in peers:
            assert peer["read_on"] in text, peer["key"]


def test_the_sealed_record_carries_the_matrix_denominators():
    """The record is what an outside reader hashes. A star count sealed
    without the peer set and the unread count seals the flattering half of
    the finding and leaves the qualifier on the page, where it can be
    edited."""
    from harness.parity import parity_matrix
    doc = parity_matrix()
    p = _record()["parity"]
    assert p["peers"] == [x["key"] for x in doc["peers"]]
    assert p["undetermined"] == len(doc["summary"]["undetermined"])
    assert p["uniquely_witnessed"] == len(doc["summary"]["uniquely_witnessed"])
    # The gap list is sealed here too and reads empty. What bounds it is the
    # row set, which this project wrote, so the count of peer capabilities no
    # row scores is hashed with it or the zero travels alone.
    assert p["coverage"] == doc["summary"]["coverage"]


def test_the_empty_gap_count_reaches_both_surfaces_with_its_own_limit():
    """`gaps 0` is the most flattering number the matrix produces and the one
    a reader is least equipped to check, because the row set that bounds it
    was chosen here. Both surfaces have to print the unscored count beside
    it, and the split between rows owed and topics left out on purpose, or
    the zero reads as full coverage of the field."""
    from harness.parity import parity_matrix
    c = parity_matrix()["summary"]["coverage"]
    for text in (HTML.read_text(encoding="utf-8"),
                 MARKDOWN.read_text(encoding="utf-8")):
        # The markdown is reflowed to the README width, so a phrase can land
        # across two lines. Compared on collapsed whitespace, or this test
        # would only be checking where the wrapper happened to break.
        text = " ".join(text.split())
        assert f"{c['unscored_topics']} capability areas" in text
        assert f"{c['row_owed']} where a row is owed" in text
        assert f"{c['out_of_frame']} left out on purpose" in text
        assert "harness/parity_coverage.py" in text


def test_the_strawman_is_drawn_next_to_the_harness():
    """A benchmark everything passes measures nothing.

    The accountability chart is only evidence if the system built to fail it
    is shown failing it, so the strawman score has to reach the page.
    """
    html = HTML.read_text(encoding="utf-8")
    assert "strawman" in html
    accountability = next(s for s in _record()["suites"]
                          if s["name"] == "accountability")
    # Not pinned to zero any more. One store attack in the adversarial corpus,
    # absent_ancestor, cites a receipt that was never written, and no resolver
    # can fail it because there is no file to load. It stays in the denominator
    # on purpose, so the floor a strawman reaches on that axis is above zero.
    # Pinning zero here would forbid every future control of that shape. What
    # the page owes a reader is that the system built to fail scores far below
    # the one being measured, which is what these two assertions say.
    headline = accountability["headline"]
    assert headline["strawman_overall"] < 0.2, "the strawman has stopped failing"
    assert headline["separation"] >= 0.8, "the chart no longer separates the two"
    assert any(d.get("strawman") == 0.0 for d in accountability["detail"])


def test_the_published_surface_keeps_the_house_voice():
    """No em-dashes on a public surface, per the design and voice canon."""
    for path in (HTML, MARKDOWN, REPO / "site" / "assets" / "benchmarks.css"):
        assert "\u2014" not in path.read_text(encoding="utf-8"), path.name


def test_the_page_never_prints_a_local_path():
    """Published surfaces carry no operator machine paths."""
    html = HTML.read_text(encoding="utf-8")
    for fragment in ("C:\\", "c:/dev", "E:\\"):
        assert fragment not in html, fragment


def test_the_landing_page_agrees_with_the_record():
    """site/index.html is written by hand and repeats numbers from the run.

    The two generated surfaces cannot drift. This one can, and it is the page
    most readers reach first, so every number it borrows is pinned here.
    """
    index = (REPO / "site" / "index.html").read_text(encoding="utf-8")
    report = _record()
    words = {4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight"}
    assert f"{words[len(report['suites'])]} suites need no endpoint" in index
    paired = next(s["headline"] for s in report["suites"]
                  if s["name"] == "paired-replication")
    assert f"{paired['delta_points'] * 100:.2f} points" in index
    assert f"over {paired['tasks']} tasks" in index
    assert f"p = {paired['p_exact']:.2f}" in index
    assert "retired on 2026-07-26" in index.lower()
    assert "is not a comparison" in index
    # A retired instrument fetched live would otherwise wear the same
    # freshness badge as a standing result.
    assert "retired instrument, kept on the page" in index
