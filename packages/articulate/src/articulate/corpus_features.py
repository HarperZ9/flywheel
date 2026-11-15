"""Per-document features for series review: blocks, sentences, moves, rhythm,
perspective, specificity and sections.

Every measure here is a count a reader could redo by hand. Paragraph moves come
from fixed cue words, so the same text always gets the same labels. The
thresholds table is the one place the series checks read their triggers from,
and it enters the corpus fingerprint.

Standard library only. Reuses the detector's markup and word helpers, which
stay unchanged.
"""
import re
from statistics import mean, pstdev

from . import detector
from .authorship import is_disclosure

THRESHOLDS = {
    "title_family_min": 2, "title_family_share": 0.30, "title_share_min_titles": 4,
    "ngram_min": 4, "ngram_max": 7, "ngram_docs": 3, "ngram_docs_small": 2, "ngram_report": 10,
    "construction_doc_share": 0.5,
    "scaffold_share": 0.40, "scaffold_min_paragraphs": 5, "scaffold_sequence_docs": 3,
    "section_min": 4, "section_cv": 0.20, "heading_doc_share": 0.5,
    "rhythm_cv": 0.45, "rhythm_min_sentences": 20, "rhythm_band": 6, "rhythm_run": 8,
    "rhythm_spread": 0.05,
    "perspective_rate": 1.0, "perspective_stretch": 1500, "perspective_min_words": 300,
    "abstract_run": 3, "abstract_min_words": 20,
    "template_docs": 3, "template_docs_small": 2, "template_literals": 3, "template_report": 12,
    "template_tail": 8,
    "ritual_share": 0.2,
}
ARGUED_GENRES = frozenset({"essay", "op-ed", "letter", "memoir"})

MOVE_CUES = (
    ("limit", r"\bdoes(?: not|n't) (?:prove|show|establish)\b|\bwhat this does not\b"
              r"|\bdoes-not-prove\b|\bthis is not evidence\b"),
    ("confidence", r"\bconfidence\b|[(\[:]\s*(?:high|moderate|low|unknown)\b"
                   r"|^\W*(?:high|moderate|low|unknown)\W*$"),
    ("source", r"https?://|\]\(|\baccording to\b|\breport(?:ed|s)\b|\bsources?:"
               r"|\[\d+\]|\[\^[^\]]+\]|\bper the\b"),
    ("first-person", r"^\W*(?:I|My|We|Our)\b|\bI\b|\b(?:me|my|mine|myself)\b"),
    ("question", r"\?[\"'”’)\]]*$"),
    ("example", r"\bfor (?:example|instance)\b|\be\.g\.|\d[\d,.]*\s?(?:%|percent|kg|km|miles?"
                r"|words|people|years?|days?|hours?|months?|dollars|million|billion)\b|\$\d"),
)
_MOVES = [(label, re.compile(rx, re.I if label != "first-person" else 0)) for label, rx in MOVE_CUES]
SCAFFOLD_MOVES = frozenset({"source", "confidence", "limit"})
_FIRST_PERSON = re.compile(r"\bI\b|\b(?:[Mm]e|[Mm]y|[Mm]ine|[Mm]yself)\b")
_WE = re.compile(r"\b(?:[Ww]e|[Uu]s|[Oo]ur|[Oo]urs|[Oo]urselves)\b")
_SENT_END = re.compile(r"[.!?]+[\"'”’)\]]*(?=\s|$)")
_ABBREV = re.compile(r"(?:\b(?:e\.g|i\.e|etc|vs|Mr|Mrs|Ms|Dr|St|Inc|Jr|Sr)|\b[A-HJ-Z])\.$")
_QUOTE = re.compile(r"\"[^\"\n]{3,}\"|“[^”]{3,}”")
_CAPWORD = re.compile(r"\b[A-Z][a-z][A-Za-z'-]*")
_KINDS = (("heading", detector.HEADING), ("list", detector.BULLET),
          ("quote", re.compile(r"^\s*>")), ("table", re.compile(r"^\s*\|")),
          ("comment", re.compile(r"^\s*<!--")))


def words(text):
    return detector.WORD.findall(detector.strip_markup(text))


def _kind(line):
    for kind, rx in _KINDS:
        if rx.match(line):
            return kind
    return "prose"


def _front_matter_end(lines):
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                return i + 1
    return 0


def blocks(text):
    """Blank-line blocks with kind and 1-based line range. Headings stand alone."""
    lines = text.splitlines()
    out, cur, fence = [], None, False
    for i in range(_front_matter_end(lines), len(lines)):
        line, n = lines[i], i + 1
        if detector.FENCE.match(line):
            fence = not fence
            cur = None
            continue
        if fence or not line.strip():
            cur = None
            continue
        kind = _kind(line)
        if cur is None or kind == "heading" or cur["kind"] == "heading":
            cur = {"kind": kind, "line_start": n, "line_end": n, "lines": [line]}
            out.append(cur)
        else:
            cur["line_end"] = n
            cur["lines"].append(line)
    for b in out:
        b["text"] = "\n".join(b.pop("lines"))
    return out


def sentence_bounds(text):
    """(start, end) of each sentence in text, byte exact, with abbreviations kept."""
    bounds, start = [], 0
    for m in _SENT_END.finditer(text):
        if _ABBREV.search(text[max(0, m.end() - 6):m.end()]) and m.group() == ".":
            continue
        piece = text[start:m.end()]
        if piece.strip():
            lead = len(piece) - len(piece.lstrip())
            bounds.append((start + lead, m.end()))
        start = m.end()
    tail = text[start:]
    if tail.strip():
        bounds.append((start + len(tail) - len(tail.lstrip()), len(text.rstrip())))
    return bounds


def sentences(text):
    return [text[a:b] for a, b in sentence_bounds(text)]


def label(sentence):
    flat = " ".join(detector.strip_markup(sentence).split()) or sentence
    for move, rx in _MOVES:
        if move == "source" and rx.search(sentence) or rx.search(flat):
            return move
    return "claim"


def move_sequence(paragraph_text):
    seq = []
    for s in sentences(paragraph_text):
        move = label(s)
        if not seq or seq[-1] != move:
            seq.append(move)
    return seq


def is_scaffold(seq):
    return bool(seq) and seq[-1] in ("limit", "confidence") and len(seq) > 1


def first_person(text):
    masked = detector.mask_quotes(text)
    return len(_FIRST_PERSON.findall(masked)), len(_WE.findall(masked))


def specific_items(text):
    """Numbers, quotations and capitalized words that do not open a sentence."""
    count = len(re.findall(r"\d[\d,.:/]*", text)) + len(_QUOTE.findall(text))
    for s in sentences(detector.strip_markup(text)):
        opening = re.sub(r"^[^A-Za-z]+", "", s)
        count += sum(1 for m in _CAPWORD.finditer(opening) if m.start() > 0)
    return count


def prose_blocks(text):
    return [b for b in blocks(text) if b["kind"] == "prose" and not is_disclosure(b["text"])]


def sentence_records(text):
    """(line, word count) for each prose sentence, in document order."""
    out = []
    for b in prose_blocks(text):
        for a, end in sentence_bounds(b["text"]):
            n = len(words(b["text"][a:end]))
            if n:
                out.append((b["line_start"] + b["text"][:a].count(chr(10)), n))
    return out


def sentence_lengths(text):
    return [n for _, n in sentence_records(text)]


def cv(values):
    values = [v for v in values if v is not None]
    if len(values) < 2 or not mean(values):
        return None
    return round(pstdev(values) / mean(values), 3)


def longest_band_run(lengths, band):
    """(length, start index) of the longest run whose lengths stay within band."""
    best, best_start, cur_start = 0, 0, 0
    for end in range(len(lengths)):
        window = lengths[cur_start:end + 1]
        while max(window) - min(window) > band:
            cur_start += 1
            window = lengths[cur_start:end + 1]
        if end - cur_start + 1 > best:
            best, best_start = end - cur_start + 1, cur_start
    return best, best_start


def sections(text):
    """Sections under level-2 and deeper headings: heading text, line, prose words."""
    out = []
    for b in blocks(text):
        if b["kind"] == "heading" and not b["text"].lstrip().startswith("# "):
            out.append({"heading": b["text"].strip(), "line": b["line_start"], "words": 0})
        elif out and b["kind"] in ("prose", "list", "quote"):
            out[-1]["words"] += len(words(b["text"]))
    return out


def heading_key(heading):
    text = re.sub(r"^\s*#+\s*", "", heading)
    text = re.sub(r"^\s*(?:\d+[.)]|[ivx]+\.)\s*", "", text, flags=re.I)
    return " ".join(re.findall(r"[a-z0-9']+", text.lower()))


def author_stretches(text):
    """(words, line_start, line_end) for each run of prose with no first person."""
    runs, cur = [], None
    for b in prose_blocks(text):
        singular, plural = first_person(b["text"])
        if singular or plural:
            cur = None
            continue
        n = len(words(b["text"]))
        if cur is None:
            cur = [0, b["line_start"], b["line_end"]]
            runs.append(cur)
        cur[0] += n
        cur[2] = b["line_end"]
    return [tuple(r) for r in runs]


def abstract_runs(text, minimum):
    """Runs of consecutive prose paragraphs with no specific item."""
    runs, cur = [], []
    for b in prose_blocks(text):
        if len(words(b["text"])) < THRESHOLDS["abstract_min_words"]:
            continue
        if specific_items(b["text"]):
            cur = []
            continue
        cur.append(b)
        if len(cur) == minimum:
            runs.append(cur)
    return [(r[0]["line_start"], r[-1]["line_end"], len(r)) for r in runs]
