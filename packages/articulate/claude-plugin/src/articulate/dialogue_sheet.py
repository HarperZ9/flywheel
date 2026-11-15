"""Character voice sheets and the checks a line is held to against its sheet.

A sheet is one JSON file per character in a voices folder. Every field is
optional except "name"; a check whose field is missing does not run.

    {
      "format": "articulate-voice-sheet/1",
      "name": "MARROW", "aliases": ["DUNLIN"],
      "register": {"level": "plain", "education": "...", "class": "...", "trade": "...",
                   "words": ["trade words the character does use"]},
      "region": {"name": "gullet", "markers": ["aye", "owt"], "idioms": ["on the turn"]},
      "sentence_length": {"min": 1, "max": 18},
      "contractions": true,
      "questions": "never" | "only",
      "never": ["words or phrases the character would never say"],
      "never_patterns": [{"re": "regex", "msg": "why"}],
      "knowledge": {"knows": ["..."],
                    "unknown": [{"terms": ["word"], "why": "...", "unless_group": ["act3"],
                                 "unless_node": ["dawn."], "unless_gate": ["works.order"]}]},
      "wants": "...", "fears": "...", "hides": "...",
      "tics": ["phrases the character repeats"]
    }

A folder may also hold `_project.json` with {"theme_words": [...], "min_lines": 20}.
The knowledge check is a keyword bound: it finds a word, not a fact, so a hit is a
place to look and not proof of a leak.
"""
import json
import os
import re

from .dialogue_lexicon import learned, plain_long, sentences, syllables, words

FORMAT = "articulate-voice-sheet/1"
LEVELS = ("plain", "middle", "formal")
_CONTRACTION = re.compile(r"\b\w+(?:n['’]t|['’](?:ll|re|ve|m|d))\b|"
                          r"\b(?:it|that|there|what|he|she|here)['’]s\b", re.I)
_QUOTED = re.compile(r"\"[^\"]*\"|“[^”]*”")
WEIGHTS = {"never": 3, "knowledge-leak": 3, "never-pattern": 2, "register": 1,
           "sentence-length": 1, "contractions": 1, "questions": 2}


def _check_types(sheet, path):
    if not isinstance(sheet, dict) or not isinstance(sheet.get("name"), str):
        raise ValueError(f"{path}: a voice sheet is a JSON object with a string 'name'")
    level = (sheet.get("register") or {}).get("level")
    if level is not None and level not in LEVELS:
        raise ValueError(f"{path}: register.level must be one of {LEVELS}")
    rng = sheet.get("sentence_length") or {}
    for key in ("min", "max"):
        if key in rng and not isinstance(rng[key], int):
            raise ValueError(f"{path}: sentence_length.{key} must be a whole number")
    if sheet.get("questions") not in (None, "never", "only"):
        raise ValueError(f"{path}: questions must be 'never' or 'only'")
    for pat in sheet.get("never_patterns") or []:
        re.compile(pat["re"])
    return sheet


def load_dir(path):
    """Return (sheets_by_name, project). Names and aliases are upper-cased."""
    sheets, project = {}, {}
    if not path:
        return sheets, project
    if not os.path.isdir(path):
        raise ValueError(f"voices folder not found: {path}")
    for fn in sorted(os.listdir(path)):
        if not fn.endswith(".json"):
            continue
        full = os.path.join(path, fn)
        with open(full, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if fn == "_project.json":
            project = data
            continue
        sheet = _check_types(data, full)
        for name in [sheet["name"]] + list(sheet.get("aliases") or []):
            sheets[name.upper()] = sheet
    return sheets, project


def _has(text, phrase):
    return re.search(r"(?<![A-Za-z])" + re.escape(phrase) + r"(?![A-Za-z])", text, re.I)


def _register(text, sheet, proper):
    reg = sheet.get("register") or {}
    level = reg.get("level")
    if level not in ("plain", "middle"):
        return []
    allowed = {w.lower() for w in reg.get("words") or []}
    out = []
    for w in words(text):
        lw = w.lower()
        if lw in allowed or w in proper:
            continue                  # trade words and names are the character's own
        if (level == "plain" and learned(w)) or (level == "middle" and syllables(w) >= 5
                                                   and not plain_long(w)):
            out.append(w)
    return sorted(set(out), key=str.lower)


def _leaks(rec, sheet):
    out = []
    for bound in (sheet.get("knowledge") or {}).get("unknown") or []:
        if rec.get("group") in (bound.get("unless_group") or []):
            continue
        node = rec.get("node") or ""
        if any(node.startswith(p) for p in bound.get("unless_node") or []):
            continue
        gate = rec.get("gate") or ""
        if any(g in gate for g in bound.get("unless_gate") or []):
            continue                  # the line only plays once the player has shown it
        hit = [t for t in bound.get("terms") or [] if _has(rec["text"], t)]
        if hit:
            out.append((hit, bound.get("why", "")))
    return out


def check_line(rec, sheet, proper=frozenset()):
    """Findings for one line against its speaker's sheet. Words the character
    quotes from someone else are masked for the register, never-word and
    contraction checks; the knowledge check reads the whole line."""
    found = []
    text = _QUOTED.sub(" ", rec["text"])

    def add(check, label, excerpt):
        found.append({"check": check, "label": label, "weight": WEIGHTS[check],
                      "excerpt": excerpt})

    for phrase in sheet.get("never") or []:
        if _has(text, phrase):
            add("never", "a word this character would never use", phrase)
    for pat in sheet.get("never_patterns") or []:
        if re.search(pat["re"], text):
            add("never-pattern", pat.get("msg") or "matches a never pattern", pat["re"])
    odd = _register(text, sheet, proper)
    if odd:
        add("register", "outside the character's register", ", ".join(odd[:4]))
    rng = sheet.get("sentence_length") or {}
    lo, hi = rng.get("min", 0), rng.get("max", 10 ** 6)
    lens = [len(words(s)) for s in sentences(text)]
    out_of = [n for n in lens if n < lo or n > hi]
    if out_of:
        add("sentence-length", f"sentence length outside {lo} to {hi} words",
            ", ".join(str(n) for n in out_of))
    if sheet.get("contractions") is False and _CONTRACTION.search(text):
        add("contractions", "uses a contraction; this character speaks in full forms",
            _CONTRACTION.search(text).group(0))
    whole = rec["text"].rstrip()
    if sheet.get("questions") == "never" and "?" in text:
        add("questions", "asks a question; this character never does", whole[-40:])
    if sheet.get("questions") == "only" and not whole.rstrip("\"'”").endswith("?"):
        add("questions", "ends on a statement; this character speaks only in questions",
            whole[-40:])
    for hit, why in _leaks(rec, sheet):
        add("knowledge-leak", "mentions what the character should not know" +
            (f": {why}" if why else ""), ", ".join(hit))
    return found


def usage(lines, sheet):
    """Share of a character's lines that use a tic, a region marker or an idiom."""
    region = sheet.get("region") or {}
    markers = list(region.get("markers") or []) + list(region.get("idioms") or [])
    tics = list(sheet.get("tics") or [])
    n = len(lines) or 1
    return {"tic_lines": sum(1 for r in lines if any(_has(r["text"], t) for t in tics)) / n,
            "region_lines": sum(1 for r in lines if any(_has(r["text"], m) for m in markers)) / n}
