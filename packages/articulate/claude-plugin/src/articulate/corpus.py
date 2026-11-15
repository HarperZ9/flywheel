"""Series review: patterns a reader notices across several documents.

analyze_corpus reads two or more documents (or one, with single=True, for its
structural checks) and returns findings. Each finding names its category, the
documents and lines it rests on, the measured numbers, what the pattern costs
a reader, what the author could do, and what the finding does not show. No
finding proposes replacement text, and no finding gates.

Standard library only. No network and no model.
"""
import re

from . import corpus_checks, corpus_shape, corpus_templates
from . import corpus_features as cf
from .authorship import disclosure_spans

SCHEMA = "articulate/corpus-report/v2"
SCOPE = ("Names the patterns a reader can notice across a series of texts, and shows "
         "where each pattern occurs.")
_INTERVIEW = "Run `articulate interview` on this file. Only you can supply what goes here."
READER = {
    "corpus/title-formula": (
        "Titles built on one shape start to read as a template, and a reader stops "
        "telling the pieces apart.",
        "Run `articulate titles` and answer its question for each piece in your own words.",
        "Groups titles by shape. Each title can still fit its own piece."),
    "corpus/shared-ngram": (
        "A reader who meets the same phrase in several pieces hears a formula where you "
        "meant a point.",
        "Keep a phrase you repeat on purpose and list it with --keep. Say the others the "
        "way this piece needs.",
        "Lists phrases that occur in several pieces. A repeated phrase can be a refrain or a term of art."),
    "corpus/shared-construction": (
        "The same sentence habit in most pieces reads as one voice on autopilot.",
        "Look at the listed lines and decide which uses earn their place.",
        "Names a sentence habit and lists where it occurs. You decide which uses to keep."),
    "corpus/paragraph-scaffold": (
        "Readers learn the pattern after a few paragraphs and start skimming the limit "
        "lines, which are the lines you most want read.",
        "Keep each limit. Consider stating shared limits once in a sources and method "
        "section and keeping in-paragraph limits where a claim's limit differs. "
        "`articulate restructure` shows that move.",
        "Labels each move from cue words. Check each excerpt, because a cue word can mislabel a sentence."),
    "corpus/section-symmetry": (
        "Sections of the same length and the same headings make every piece feel cut "
        "from one mold.",
        "Let each section run as long as its point needs, and name headings for what "
        "this piece says.",
        "Compares section lengths and headings. A recurring column can use even sections on purpose."),
    "corpus/rhythm": (
        "Sentences of one length in a row give prose a flat beat that tires a reader.",
        "Read the listed stretch aloud and break or join sentences where your own "
        "speech would.",
        "Measures sentence length, which is one part of rhythm."),
    "corpus/perspective": (
        "The piece argues a position but no one is visible taking it, so a reader cannot "
        "tell what the author saw or would stand behind.",
        _INTERVIEW,
        "Counts first-person words. Some pieces stay impersonal on purpose."),
    "corpus/sentence-template": (
        "A sentence built on one template is ordinary once. By the third turn a reader "
        "hears a stamp and stops reading it.",
        "Keep the one use that carries a decision. Say the others the way that turn needs, "
        "or leave them out.",
        "Reduces each sentence to its function words and slots. Two sentences can share a "
        "template and still each say something the reader needs."),
    "corpus/ritual": (
        "Turns that all open or close on one move teach a reader to skip the first and "
        "last line.",
        "Open with what this turn found, and end when the content ends.",
        "Compares the first and last sentence of each document. A status report can use a "
        "fixed opening on purpose."),
    "corpus/abstract-run": (
        "Several paragraphs in a row without a name, number, place or quotation ask the "
        "reader to trust claims they cannot picture.",
        "Add a case, a number, a place or a person you can name, where you have one.",
        "The count looks for surface markers of specific detail and misses some."),
}


def doc_title(doc):
    """Explicit title, then front matter title:, then the first H1, then HTML <title>."""
    if doc.get("title"):
        return doc["title"].strip()
    text = doc["text"]
    front = re.match(r"---\r?\n(.*?)\r?\n---", text, re.S)
    if front:
        m = re.search(r"(?m)^title:\s*[\"']?(.+?)[\"']?\s*$", front.group(1))
        if m:
            return m.group(1)
    m = re.search(r"(?m)^#\s+(.+?)\s*#*\s*$", text)
    if m:
        return m.group(1)
    m = re.search(r"(?is)<title>(.*?)</title>", text)
    return " ".join(m.group(1).split()) if m else ""


def keep_list(docs, keep):
    out = [k.strip() for k in keep or () if k and k.strip()]
    for d in docs:
        front = re.match(r"---\r?\n(.*?)\r?\n---", d["text"], re.S)
        m = front and re.search(r"(?m)^articulate-keep:\s*(.+)$", front.group(1))
        if m:
            out += [k.strip() for k in re.split(r"[,;]", m.group(1)) if k.strip()]
    return sorted(set(out))


def finding(category, docs, locations, measure):
    cost, direction, limit = READER[category]
    return {"category": category, "docs": sorted(set(docs)), "locations": locations,
            "measure": measure, "reader_cost": cost, "direction": direction,
            "scope": limit, "protected": False}


def _validate(docs, single):
    if not isinstance(docs, list) or not all(
            isinstance(d, dict) and isinstance(d.get("name"), str) and isinstance(d.get("text"), str)
            for d in docs):
        raise ValueError("documents must be a list of {name, text, title?} objects")
    if len(docs) < (1 if single else 2):
        raise ValueError("corpus mode needs two or more documents, or single mode for one")
    if len({d["name"] for d in docs}) != len(docs):
        raise ValueError("document names must be unique")


def _disclosures(docs):
    out = {}
    for d in docs:
        for a, b in disclosure_spans(d["text"]):
            out.setdefault(d["text"][a:b].strip(), []).append(d["name"])
    return [{"category": "disclosure", "text": t, "docs": names} for t, names in sorted(out.items())]


def analyze_corpus(docs, *, keep=(), genre="essay", single=False):
    """Findings across docs. Raises ValueError on malformed input."""
    _validate(docs, single)
    docs = [dict(d, title=doc_title(d)) for d in docs]
    keep = keep_list(docs, keep)
    ctx = {"docs": docs, "keep": keep, "genre": genre, "single": single or len(docs) < 2,
           "protected": [], "finding": finding}
    findings = []
    for check in corpus_checks.CHECKS + corpus_shape.CHECKS + corpus_templates.CHECKS:
        findings += check(ctx)
    return {"schema": SCHEMA,
            "documents": [{"name": d["name"], "title": d["title"],
                           "words": sum(len(cf.words(b["text"])) for b in cf.prose_blocks(d["text"]))}
                          for d in docs],
            "keep": keep, "findings": findings,
            "protected": ctx["protected"] + _disclosures(docs),
            "thresholds": dict(cf.THRESHOLDS), "ai_detector_consulted": False,
            "scope": SCOPE}


def format_report(report):
    """Plain text: each finding with its locations and direction."""
    out = [f"{len(report['documents'])} documents, {len(report['findings'])} findings."]
    for f in report["findings"]:
        out += ["", f"[{f['category']}] {f['reader_cost']}"]
        measure = ", ".join(f"{k} {v}" for k, v in f["measure"].items() if not isinstance(v, (list, dict)))
        if measure:
            out.append(f"  Measure: {measure}")
        for loc in f["locations"][:12]:
            out.append(f"  {loc['doc']}:{loc['line_start']}-{loc['line_end']}  {loc['excerpt']}")
        if len(f["locations"]) > 12:
            out.append(f"  and {len(f['locations']) - 12} more locations")
        out.append(f"  Direction: {f['direction']}")
    if report["protected"]:
        out += ["", f"Protected and never flagged: {len(report['protected'])} "
                    "(declared repetition and disclosure lines)."]
    out += ["", report["scope"]]
    return "\n".join(out)
