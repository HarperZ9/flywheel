"""Public descriptions say what the known-provenance evidence supports: a tool
that finds writing patterns, also flags most human writing, and leaves the
question of who wrote a text to other evidence."""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SURFACES = ["README.md", "pyproject.toml", "action.yml", "editors/vscode/package.json",
            "editors/vscode/README.md", "docs/README.md", "docs/getting-started.md",
            "docs/boundaries.md", "docs/features.md", "docs/cli.md", "docs/walkthrough.md",
            "src/articulate/cli.py", "src/articulate/mcp_server.py",
            "src/articulate/tool_text.py", "src/articulate/bench.py",
            ".pre-commit-hooks.yaml", "assets/make_hero.py", "assets/articulate-hero.svg",
            "docs/art/hero-dark.svg", "docs/art/hero-light.svg"]
OVERCLAIM = re.compile(r"(?i)AI-tell detection|\bAI[- ]tells?\b|AI and prose tells|machine-textured|machine-texture score|"
                       r"reads as machine-written|mixed[- ]authorship|AI recall|human specificity|"
                       r"specificity on the\s+human")


def _text(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    if rel == "README.md":  # the hero alt text is checked through the SVG title it repeats
        text = re.sub(r'<img [^>]*>', "", text)
    return text


def test_no_surface_presents_articulate_as_an_authorship_detector():
    for rel in SURFACES:
        m = OVERCLAIM.search(_text(rel))
        assert not m, (rel, m and m.group(0))


def test_the_overclaim_check_can_fail():
    for planted in ("Flag AI and prose tells", "AI-tell detection and editing", "no AI tells"):
        assert OVERCLAIM.search(planted), planted


def test_the_main_surfaces_state_the_evidence_and_the_student_rule():
    for rel in ("README.md", "docs/README.md", "docs/boundaries.md"):
        text = " ".join(_text(rel).split())
        assert "finds writing patterns and shows where they are" in text, rel
        assert "Use other evidence to decide who wrote a text." in text, rel
        assert "57 of 75 human texts" in text and "results.json" in text, rel
        assert "student" in text, rel
    assert "use other evidence to decide who wrote a text" in _text("pyproject.toml")


def test_the_quoted_numbers_match_results_json():
    res = json.loads((ROOT / "corpus/provenance/results.json").read_text(encoding="utf-8"))
    a = res["articulate"]
    assert (a["overall"]["fpr"]["k"], a["overall"]["fpr"]["n"]) == (57, 75)
    assert (a["overall"]["recall"]["k"], a["overall"]["recall"]["n"]) == (84, 84)
    ell = a["student_essay_fpr_by_ell"]["Yes"]
    assert (ell["k"], ell["n"]) == (10, 18)


# The art speaks to readers, so it carries no internal release or workflow words.
# The footers are glyph outlines, which no text check can read; the readable
# layer is the title, the description, the aria-label and any <text> element.
ART = ["docs/art/hero-dark.svg", "docs/art/hero-light.svg", "assets/articulate-hero.svg"]
INTERNAL = re.compile(r"(?i)\bflywheel lane\b|\blanes?\b|\bbeta\b|\boperator\b|\bgate\b")


def _readable_svg_text(svg):
    parts = re.findall(r"<(?:title|desc|text)\b[^>]*>(.*?)</(?:title|desc|text)>", svg, re.S)
    parts += re.findall(r'aria-label="([^"]*)"', svg)
    return " ".join(parts)


def test_the_art_carries_no_internal_register_words():
    for rel in ART:
        text = _readable_svg_text((ROOT / rel).read_text(encoding="utf-8"))
        assert text.strip(), rel
        m = INTERNAL.search(text)
        assert not m, (rel, m and m.group(0))


def test_the_internal_register_check_can_fail():
    planted = '<svg aria-label="articulate"><title>A FLYWHEEL LANE / BETA</title></svg>'
    assert INTERNAL.search(_readable_svg_text(planted))
