"""The authorship interview: questions only the author can answer, placed at
the lines that prompted them.

questions() picks fixed questions by measured triggers, so the same text
always gets the same questions. mark() returns a copy of the text with an
inert HTML comment after each location. The author writes answers under the
markers, in their own words, wherever they choose. collect() lists the
markers still unanswered and lifts the answered ones out, so the answers can
go to an edit as author-supplied text. Nothing here writes prose or answers a
question, and no model is called.
"""
import re

from . import corpus_features as cf
from .authorship import is_disclosure

SCHEMA = "articulate/interview/v2"
BANK = {
    "argued-piece": "Why does this matter to you? What made you start writing it?",
    "perspective-stretch": ("What did you see, do or hear yourself in this part, that a reader "
                            "cannot get from the sources?"),
    "high-confidence-claim": ("Would you stake your name on this claim? If not, what would you "
                              "say?"),
    "limit-or-unknown": ("Where do you disagree with the evidence here, or read it differently "
                         "from its authors?"),
    "abstract-run": "Is there a case, a number, a place or a person you can name here?",
    "scaffold-heavy-section": "If you told this part to a friend, what would you say first?",
    "closing-section": "What do you want a reader to do or think differently after this?",
}
ORDER = tuple(BANK)
PER_TRIGGER = 3
SCOPE = ("Asks a question at each line where a counted pattern occurs. Only the author "
         "can answer the questions.")
MARKER = re.compile(r"^<!-- articulate:answer (q\d+) \"([^\"]*)\" -->$")
_HIGH = re.compile(r"(?i)\bhigh\b")
_UNKNOWN = re.compile(r"(?i)\bunknown\b")


def _item(trigger, start, end, measure=None):
    return {"trigger": trigger, "line_start": start, "line_end": end, "measure": measure or {}}


def _perspective(text, prose):
    stretches = sorted(cf.author_stretches(text), key=lambda s: -s[0])
    total = sum(len(cf.words(b["text"])) for b in prose)
    singular, plural = cf.first_person("\n".join(b["text"] for b in prose))
    rate = (singular + plural) * 1000 / total if total else 0
    sparse = total >= cf.THRESHOLDS["perspective_min_words"] and rate < cf.THRESHOLDS["perspective_rate"]
    if stretches and (stretches[0][0] > cf.THRESHOLDS["perspective_stretch"] or sparse):
        n, a, b = stretches[0]
        return [_item("perspective-stretch", a, b, {"words": n})]
    return []


def _paragraph_items(prose):
    out = []
    for b in prose:
        labels = [(cf.label(s), s) for s in cf.sentences(b["text"])]
        if any(m == "confidence" and _HIGH.search(s) for m, s in labels):
            out.append(_item("high-confidence-claim", b["line_start"], b["line_end"]))
        if any(m == "limit" for m, _ in labels) or _UNKNOWN.search(b["text"]):
            out.append(_item("limit-or-unknown", b["line_start"], b["line_end"]))
    return out


def _sections(text):
    groups, cur = [], []
    for b in cf.blocks(text):
        if b["kind"] == "heading" and not b["text"].lstrip().startswith("# "):
            cur = [b]
            groups.append(cur)
        elif b["kind"] == "prose" and not is_disclosure(b["text"]):
            if not groups:
                cur = []
                groups.append(cur)
            cur.append(b)
    return groups


def _scaffold_sections(text):
    out = []
    for group in _sections(text):
        paras = [b for b in group if b["kind"] == "prose" and len(cf.sentences(b["text"])) >= 2]
        heavy = [b for b in paras if cf.is_scaffold(cf.move_sequence(b["text"]))]
        if len(paras) >= 2 and len(heavy) / len(paras) >= cf.THRESHOLDS["scaffold_share"]:
            out.append(_item("scaffold-heavy-section", group[0]["line_start"], group[-1]["line_end"],
                             {"paragraphs": len(paras), "scaffold_paragraphs": len(heavy)}))
    return out


def _voice_items(text, voice_profile):
    from . import voice
    report = voice.compare(text, voice_profile)
    return [_item("perspective-stretch", loc["line_start"], loc["line_end"], loc["measure"])
            for loc in report["locations"] if loc["kind"] == "no-first-person-stretch"]


def _collect_items(text, voice_profile):
    prose = cf.prose_blocks(text)
    if not prose:
        return []
    first = cf.blocks(text)[0]
    items = [_item("argued-piece", first["line_start"], prose[0]["line_end"])]
    items += _perspective(text, prose)
    if voice_profile is not None:
        items += _voice_items(text, voice_profile)
    items += _paragraph_items(prose)
    items += [_item("abstract-run", a, b, {"paragraphs": n})
              for a, b, n in cf.abstract_runs(text, cf.THRESHOLDS["abstract_run"])]
    items += _scaffold_sections(text)
    items.append(_item("closing-section", prose[-1]["line_start"], prose[-1]["line_end"]))
    return items


def questions(text, *, voice_profile=None):
    """Located questions, at most three per trigger, in document order."""
    if not isinstance(text, str):
        raise ValueError("interview needs document text")
    seen, kept, counts = set(), [], {}
    for item in _collect_items(text, voice_profile):
        key = (item["trigger"], item["line_start"])
        if key in seen or counts.get(item["trigger"], 0) >= PER_TRIGGER:
            continue
        seen.add(key)
        counts[item["trigger"]] = counts.get(item["trigger"], 0) + 1
        kept.append(item)
    kept.sort(key=lambda i: (i["line_end"], ORDER.index(i["trigger"])))
    out = [dict(id=f"q{n}", question=BANK[i["trigger"]], **i) for n, i in enumerate(kept, 1)]
    return {"schema": SCHEMA, "questions": out, "ai_detector_consulted": False,
            "scope": SCOPE}


def marker_text(question):
    text = " ".join(question.replace('"', "'").split())
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-")


def _marker(q):
    return f'<!-- articulate:answer {q["id"]} "{marker_text(q["question"])}" -->'


def mark(text, qs):
    """A copy of text with an inert marker line after each question's location."""
    ends, pos = {}, 0
    for n, line in enumerate(text.splitlines(keepends=True), 1):
        ends[n] = pos + len(line.rstrip("\r\n"))
        pos += len(line)
    pieces, last = [], 0
    for q in sorted(qs, key=lambda q: (q["line_end"], int(q["id"][1:]))):
        at = ends.get(q["line_end"], len(text))
        pieces += [text[last:at], "\n" + _marker(q) + "\n"]
        last = at
    return "".join(pieces) + text[last:]


def collect(marked):
    """Answered markers lifted out with their answers; unanswered ones listed."""
    lines = marked.split("\n")
    answers, unanswered, keep = [], [], []
    for i, line in enumerate(lines):
        m = MARKER.match(line)
        if not m:
            keep.append(line)
            continue
        body = []
        for nxt in lines[i + 1:]:
            if not nxt.strip() or MARKER.match(nxt):
                break
            body.append(nxt)
        if body:
            answers.append({"id": m.group(1), "question": m.group(2), "answer": "\n".join(body)})
        else:
            unanswered.append({"id": m.group(1), "question": m.group(2), "line": len(keep) + 1})
            keep.append(line)
    return {"answers": answers, "unanswered": unanswered, "text": "\n".join(keep)}
