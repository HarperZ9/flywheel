"""Negation load: how much of an entry is spent on what a thing lacks.

An entry is a paragraph, a card, a README section, a dialogue line or a script
block. The check splits the entry into clauses and counts the clauses whose
main job is negation, limitation or disclaimer: "does not", "never", "no X",
"not yet", "without", "only", "limited to", "not measured", "honest null".
The score is that share of clauses. A second figure gives the share of words
those clauses hold, so a reader can see a long disclaimer beside a short claim.

Copy that lists what a tool lacks tells the reader little about what it does.
The check names those entries so a writer can lead with the capability and
the evidence for it.

The check also counts virtue phrases (provenance, receipts, re-derivable,
transparent, honest, verifiable) used as selling points. They are reported
beside the score and do not change it.

Two rules ship. The copy rule warns at 30% and fails at 50%. The fiction rule
warns at 45% and fails at 65%, and it skips character speech: a character
can say no. Narration and copy still count. Standard library only.
"""
from __future__ import annotations

import re

RULES = {
    "copy": {"warn": 0.30, "fail": 0.50, "exempt_dialogue": False},
    "fiction": {"warn": 0.45, "fail": 0.65, "exempt_dialogue": True},
}

# The register profiles stay as they are, so the detector ruleset hash holds.
# A profile picks its negation rule here: every genre and the narrative
# profile take the fiction rule, the rest take the copy rule.
FICTION_PROFILES = ("narrative",)

MIN_WORDS = 8

_STRONG = (
    r"\bnot\b", r"n['’]t\b", r"\bcannot\b", r"\bnever\b", r"\bnone\b",
    r"\bnor\b", r"\bneither\b", r"\bnothing\b", r"\bnobody\b", r"\bnowhere\b",
    r"\bno\b(?!\.?\s*\d)(?!-)", r"\blimited to\b", r"\byet to\b",
    r"\bun(?:measured|verified|tested|proven|signed|released)\b",
    r"\bhonest nulls?\b", r"\bdoes-not-prove\b", r"\bcaveats?\b",
    r"\bdisclaimers?\b", r"\bout of scope\b",
)
# Weak markers often sit inside a plain statement of fact ("closed without
# merge"). They count only in a short clause, where they carry the clause.
_WEAK = (
    r"\bwithout\b", r"(?<![-\w])(?<!not )(?<!the )(?<!if )\bonly\b(?!-)",
    r"\bexcept\b", r"\bunless\b", r"\bpending\b",
)
WEAK_MAX_WORDS = 15
_VIRTUE = (
    r"\bprovenance\b", r"\breceipts?\b", r"\bre-?derivab\w*", r"\bre-?derive[sd]?\b",
    r"\btransparen(?:t|cy)\b", r"\bhonest(?:y|ly)?\b", r"\bverifiab\w*",
    r"\bverif(?:y|ies|ied) offline\b", r"\bauditab\w*", r"\binspectab\w*",
    r"\btamper-evident\b", r"\breproducib\w*", r"\bsigned checksums?\b",
    r"\baccountab\w*", r"\bevidence chains?\b", r"\bsourced evidence\b",
    r"\bwitness(?:ed|ing)?\b",
)
STRONG_RE = re.compile("|".join(_STRONG), re.IGNORECASE)
WEAK_RE = re.compile("|".join(_WEAK), re.IGNORECASE)
VIRTUE_RE = re.compile("|".join(_VIRTUE), re.IGNORECASE)

_SENTENCE = re.compile(r"(?<=[.!?])[\"'”’)]?\s+(?=[\"'“(\[]?[A-Z0-9])")
_HARD = re.compile(r"\s*;\s*|\s+[–—]\s+|\s+--\s+|—"
                   r"|,?\s+(?=(?:but|while|whereas|although|though|because)\s)",
                   re.IGNORECASE)
_SOFT = re.compile(r",\s+(?=(?:and|so|yet)\s)", re.IGNORECASE)
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’.-]*")
_LEAD = re.compile(r"^(?:and|but|while|whereas|yet|so|though|although|because)\s+",
                   re.IGNORECASE)
_SMALL = {"a", "an", "the", "of", "and", "or", "to", "in", "on", "for", "at", "by",
          "is", "as", "its", "with", "from"}


def rule_for(profile_name=None, rule=None):
    """The negation rule a profile uses, or the named rule when one is given."""
    if rule:
        if rule not in RULES:
            raise ValueError(f"unknown negation rule {rule!r}; known: {', '.join(RULES)}")
        return dict(RULES[rule], name=rule)
    from . import genres
    fiction = profile_name in FICTION_PROFILES or profile_name in genres.GENRES
    name = "fiction" if fiction else "copy"
    return dict(RULES[name], name=name)


def words(text):
    return _WORD.findall(text)


def _soft_split(part):
    """Split at ", and" only where both sides read as clauses, so the last item
    of a list ("A, B, and C") stays with its list."""
    out, last = [], 0
    for m in _SOFT.finditer(part):
        left = part[last:m.start()].rsplit(",", 1)[-1]
        right = part[m.end():].split(",", 1)[0]
        if len(words(left)) >= 4 and len(words(right)) >= 4:
            out.append(part[last:m.start()])
            last = m.end()
    out.append(part[last:])
    return out


def _is_title(part):
    """A title in Title Case names a work, so the check leaves it out."""
    ws = [w for w in words(part) if w.lower() not in _SMALL and w[0].isalpha()]
    return len(ws) >= 2 and sum(w[0].isupper() for w in ws) / len(ws) >= 0.75


def clauses(text):
    """Sentences split at semicolons, dashes and conjunctions between clauses."""
    out = []
    for sentence in _SENTENCE.split(text.strip()):
        for hard in _HARD.split(sentence):
            for part in _soft_split(hard):
                part = _LEAD.sub("", part.strip())
                if len(words(part)) >= 2 and not _is_title(part):
                    out.append(part)
    return out


def negating(clause):
    """The markers that make a clause a negation clause, or an empty list."""
    found = [m.group(0).lower() for m in STRONG_RE.finditer(clause)]
    if found or len(words(clause)) <= WEAK_MAX_WORDS:
        found += [m.group(0).lower() for m in WEAK_RE.finditer(clause)]
    return found


_URL = re.compile(r"\S*(?:https?://|www\.|[\w-]\.(?:com|io|org|net|dev|html?|md|json)\b)\S*")


def score(text):
    """The negation load of one entry, with the clauses and phrases behind it."""
    text = _URL.sub(" ", text)
    parts = clauses(text)
    neg = [c for c in parts if negating(c)]
    total_w = sum(len(words(c)) for c in parts)
    neg_w = sum(len(words(c)) for c in neg)
    markers = [m for c in neg for m in negating(c)]
    virtue = [m.group(0).lower() for m in VIRTUE_RE.finditer(text)]
    return {
        "score": round(len(neg) / len(parts), 3) if parts else 0.0,
        "word_share": round(neg_w / total_w, 3) if total_w else 0.0,
        "clauses": len(parts), "negation_clauses": len(neg),
        "words": len(words(text)), "markers": markers, "virtue": virtue,
        "negated": neg,
    }


def verdict(value, rule):
    if value >= rule["fail"]:
        return "fail"
    if value >= rule["warn"]:
        return "warn"
    return "ok"


def assess(entries, rule, min_words=MIN_WORDS):
    """Score each entry; skip short entries and, under the fiction rule, speech."""
    out = []
    for e in entries:
        if e.get("dialogue") and rule["exempt_dialogue"]:
            continue
        s = score(e["text"])
        if s["words"] < min_words:
            continue
        rec = dict(e)
        rec.update(s)
        rec["verdict"] = verdict(s["score"], rule)
        rec["rule"] = rule["name"]
        out.append(rec)
    return out


def summary(results):
    counts = {"ok": 0, "warn": 0, "fail": 0}
    for r in results:
        counts[r["verdict"]] += 1
    counts["entries"] = len(results)
    counts["virtue_entries"] = sum(1 for r in results if r["virtue"])
    return counts
