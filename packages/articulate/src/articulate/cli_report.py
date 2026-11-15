"""How `articulate check` and `articulate score` word a result on a terminal.

Two things a reader could misread are settled here.

The texture score is the pinned detector's figure, and findings from rule
packs and project terminology never feed it. A result with such findings
prints their count first and says what the texture figure covers, so a
"texture 0/100" never stands alone beside a blocked gate.

A structure finding covers a sentence or a run of sentences, often in the
middle of a long line. Its line of output gives the line and column where the
span starts and ends, and the first and last words of the span, so a writer
can find it. Other findings keep the line number and the start of the line.
Standard library only.
"""
from . import cli_config, pack_structure

EDGE_WORDS = 5          # words shown from each end of a long span
WHOLE_WORDS = 12        # a span this short is shown in full


def pack_count(result):
    """HIGH and MEDIUM findings from rule packs and project terminology."""
    packs = result.get("pack_findings") or {}
    return packs.get("high", 0) + packs.get("medium", 0)


def texture_note(result):
    """The texture figure for a headline, with the rule-pack count before it
    when rule packs found something the texture score leaves out."""
    texture = "texture %s/100" % result["texture_score"]
    n = pack_count(result)
    if not n:
        return texture
    return "rule-pack findings %d, %s (line rules only)" % (n, texture)


def score_note(result):
    """The words `articulate score` adds inside the texture bracket."""
    n = pack_count(result)
    return "; line rules only, rule-pack findings %d" % n if n else ""


def span_place(finding):
    """'L3:12-L4:40' for a finding that carries its matched text."""
    match = finding["match"]
    line, col = finding["line"], finding.get("col", 1)
    breaks = match.count("\n")
    last = len(match) - match.rfind("\n") - 1 if breaks else col + len(match) - 1
    return "L%d:%d-L%d:%d" % (line, col, line + breaks, last)


def span_words(match):
    """The span in full when short, else its first and last words."""
    words = match.split()
    if len(words) <= WHOLE_WORDS:
        return " ".join(words)
    return "%s ... %s" % (" ".join(words[:EDGE_WORDS]), " ".join(words[-EDGE_WORDS:]))


def finding_line(finding, tier=None):
    """One line of check output for a finding."""
    tier = tier or finding["tier"]
    label = finding.get("label", finding["category"])
    if finding["category"] in pack_structure.CATEGORIES and finding.get("match"):
        return "  %s [%s %s] %s: %s" % (span_place(finding), tier, cli_config.shown(finding),
                                        label, span_words(finding["match"]))
    return "  L%d [%s %s] %s: %s" % (finding["line"], tier, cli_config.shown(finding), label,
                                     finding.get("snippet", ""))
