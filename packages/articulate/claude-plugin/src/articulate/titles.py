"""Title skeletons, title families and the title workshop.

A skeleton keeps a title's closed-class words (articles, prepositions,
copulas, negators, question words, auxiliaries, pronouns) and turns each run
of other words into X. "The Sandbox Was Never Just a Box" becomes
"the X was never just a X". Families group skeletons by ordered rules, so a
series that leans on one shape shows it as one family with its member titles.

The workshop asks the author what each piece is about in their own words and,
only when given that one-line answer, offers up to three plain variants built
from the answer's words and the document's own heading terms. Each variant is
labelled a suggestion. Nothing here writes a title into a file.
"""
import re

from .wordlists import TITLE_CLOSED

SCHEMA = "articulate/titles/v2"
QUESTION = "In one sentence, what is this piece about, in the words you would use to a friend?"
SCOPE = ("Groups the titles of a series by shape. Each title can still fit its own "
         "piece.")
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'-]*")
_HAS_NEEDS = frozenset({"has", "have", "needs", "need"})
_WH = frozenset({"who", "what", "why", "how", "where", "when", "which"})
NOT_FORMULA = frozenset({"bare noun phrase"})
FAMILY_RULES = (
    "X is not Y", "question", "what the X verbs", "who/what/why X", "colon split",
    "the X has/needs Y", "the X of/for Y", "paired clause", "X and Y", "bare noun phrase",
)


def _tokens(title):
    return [w.lower() for w in _WORD.findall(title)]


def skeleton(title):
    out = []
    for word in _tokens(title):
        token = word if word in TITLE_CLOSED else "X"
        if not (token == "X" and out and out[-1] == "X"):
            out.append(token)
    return " ".join(out)


def _paired(title):
    halves = [h for h in title.split(",") if h.strip()]
    if len(halves) != 2:
        return False
    a, b = (len(_tokens(h)) for h in halves)
    return a and b and abs(a - b) <= 1


def family(title):
    """The first family rule a title matches, in FAMILY_RULES order."""
    words, skel = _tokens(title), skeleton(title).split()
    pairs = list(zip(skel, skel[1:]))
    if any(a in ("is", "was", "are", "were") and b in ("not", "never") for a, b in pairs):
        return "X is not Y"
    if title.strip().endswith("?"):
        return "question"
    if skel[:3] == ["what", "the", "X"] and len(skel) == 3:
        return "what the X verbs"
    if words and words[0] in _WH:
        return "who/what/why X"
    if ":" in title:
        return "colon split"
    if any(w in _HAS_NEEDS for w in words[1:]):
        return "the X has/needs Y"
    if words[:1] == ["the"] and ({"of", "for"} & set(words[2:])):
        return "the X of/for Y"
    if _paired(title):
        return "paired clause"
    if "and" in words[1:]:
        return "X and Y"
    return "bare noun phrase"


def families(titles):
    groups = {}
    for t in titles:
        groups.setdefault(family(t), []).append(t)
    out = []
    for name in FAMILY_RULES:
        members = groups.get(name)
        if not members:
            continue
        heads = [w for w in {_head(t) for t in members} if sum(_head(t) == w for t in members) > 1]
        out.append({"family": name, "titles": members, "share": round(len(members) / len(titles), 3),
                    "formula": name not in NOT_FORMULA, "head_words": sorted(heads)})
    return out


def _head(title):
    content = [w for w in _tokens(title) if w not in TITLE_CLOSED]
    return content[0] if content else ""


def repeated(fams, total):
    """Families that read as a formula: two or more titles, or a large share."""
    from .corpus_features import THRESHOLDS as T
    big = total >= T["title_share_min_titles"]
    return [f for f in fams if f["formula"] and (len(f["titles"]) >= T["title_family_min"]
                                                 or (big and f["share"] >= T["title_family_share"]))]


def _title_case(words):
    return " ".join(w if w.isupper() else w[:1].upper() + w[1:] for w in words)


def _noun_phrase(words):
    run, started = [], False
    for w in words:
        if w.lower() in ("a", "an", "the") and not started:
            run = [w]
            continue
        if w.lower() in TITLE_CLOSED:
            if started:
                break
            run = []
            continue
        started = True
        run.append(w)
        if len(run) >= 6:
            break
    return run if started else []


def _shapes(answer):
    clause = re.split(r"[,;:.]", answer, maxsplit=1)[0]
    words, clause_words = _WORD.findall(answer), _WORD.findall(clause)
    return [("noun phrase", _noun_phrase(words)), ("short declarative", clause_words[:6]),
            ("answer trimmed", words[:9])]


def _variants(answer, used_twice):
    out, seen = [], set()
    for shape, words in _shapes(answer):
        text = _title_case(words)
        if len(words) < 2 or text.lower() in seen:
            continue
        fam = family(text)
        if fam in used_twice:
            continue
        seen.add(text.lower())
        out.append({"label": "suggestion", "text": text, "shape": shape, "family": fam})
    return out[:3]


def _heading_words(headings):
    return {w.lower() for h in headings or () for w in _WORD.findall(h)}


def _filter(variants, answer, headings):
    allowed = {w.lower() for w in _WORD.findall(answer)} | _heading_words(headings)
    return [v for v in variants if {w.lower() for w in _WORD.findall(v["text"])} <= allowed]


def workshop(titles, answers=None, headings=None):
    """Families, a question per title in a repeated family, and suggestions only
    for titles the author answered."""
    if not isinstance(titles, list) or not all(isinstance(t, str) and t.strip() for t in titles):
        raise ValueError("titles must be a list of non-empty strings")
    fams = families(titles)
    flagged = {t for f in repeated(fams, len(titles)) for t in f["titles"]}
    used_twice = {f["family"] for f in fams if f["formula"] and len(f["titles"]) >= 2}
    questions, suggestions = [], []
    for i, title in enumerate(titles):
        if title not in flagged:
            continue
        questions.append({"title": title, "family": family(title), "question": QUESTION})
        answer = (answers[i] if answers and i < len(answers) else "") or ""
        if answer.strip():
            heads = headings[i] if headings and i < len(headings) else []
            for v in _filter(_variants(answer.strip(), used_twice), answer, heads):
                suggestions.append(dict(v, title=title))
    return {"schema": SCHEMA, "families": fams, "questions": questions,
            "suggestions": suggestions, "ai_detector_consulted": False,
            "scope": SCOPE}
