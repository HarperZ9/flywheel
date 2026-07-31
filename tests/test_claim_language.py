"""The gate that keeps a claim from growing in the retelling.

Every checker here verifies a SUBMITTED object. None decides optimality. That
distinction survives review by being enforced, not by being written down, because
"found a drawing with 103 crossings" compresses naturally and wrongly into "found
the crossing number".
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "claim_gate", ROOT / "scripts" / "check_claim_language.py")
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def write(tmp_path, text):
    p = tmp_path / "PAGE.md"
    p.write_text(text, encoding="utf-8")
    return p


def scan(tmp_path, text):
    """scan() reports paths relative to ROOT, so point ROOT at tmp_path."""
    p = write(tmp_path, text)
    original = gate.ROOT
    gate.ROOT = tmp_path
    try:
        return gate.scan(p)
    finally:
        gate.ROOT = original


@pytest.mark.parametrize("claim", [
    "Our model found the rectilinear crossing number of the graph.",
    "We computed the crossing number of G.",
    "This establishes the zarankiewicz number.",
    "It produced an optimal drawing.",
    "The result is the minimum crossings.",
    "The certificate proves optimality.",
    "We solved the open problem.",
])
def test_a_bare_optimality_claim_is_caught(tmp_path, claim):
    assert scan(tmp_path, claim), claim


@pytest.mark.parametrize("ok", [
    "The crossing count of the submitted drawing was 103.",
    "We do not claim the rectilinear crossing number.",
    "The zarankiewicz number is not computed anywhere.",
    "Optimality is not proven by this receipt.",
    "A verified K_{2,2}-free graph with 21 edges.",
])
def test_honest_phrasing_passes(tmp_path, ok):
    assert scan(tmp_path, ok) == [], ok


def test_a_disclaimer_wrapped_across_lines_still_licenses_the_mention(tmp_path):
    """The defect the gate had on its first run. Markdown wraps prose mid
    sentence, and splitting on newlines separated a claim from the disclaimer
    that licenses it. A gate with false positives is a gate somebody switches
    off."""
    assert scan(tmp_path,
                "This mentions the rectilinear crossing number\n"
                "but does not claim it.\n") == []


def test_the_reported_line_is_where_the_claim_sits(tmp_path):
    hits = scan(tmp_path, "# Heading\n\nintro line\n\n"
                          "We found the rectilinear crossing number of G.\n")
    assert hits and ":5 " in hits[0], hits


def test_a_disclaimer_in_a_DIFFERENT_sentence_does_not_license_the_claim(tmp_path):
    """The exemption is per sentence on purpose. A vague hedge elsewhere in the
    document must not excuse a bare claim."""
    assert scan(tmp_path,
                "We computed the rectilinear crossing number of G. "
                "Separately, optimality is not claimed.")


def test_internal_records_are_not_a_public_surface():
    """Working notes must be able to discuss the mathematics in its own
    vocabulary. What ships is what is gated."""
    globs = " ".join(gate.PUBLIC_GLOBS)
    assert "records" not in globs
    assert "prereg" not in globs
    assert "shipped-page" in globs


def test_the_real_public_surfaces_are_clean_right_now():
    """A gate nobody has satisfied is a gate that will be deleted."""
    assert gate.main() == 0


def test_there_is_at_least_one_public_surface_to_scan():
    """Guards against the gate passing because its glob matched nothing."""
    assert len(gate.public_files()) > 0
