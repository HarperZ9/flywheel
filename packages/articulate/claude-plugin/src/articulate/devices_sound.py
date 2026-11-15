"""Sound devices read from spelling: alliteration and assonance.

Articulate reads no phonemes, so both readers map spelling to a coarse sound
class. The map is a readout with known metamers: "phone" and "fone" share an
onset, "cough" and "though" do not share a vowel, and stress is guessed as the
first vowel of the word. Treat a finding as a pointer for the ear, never as a
phonetic fact. A spoken view of the text is the light change that splits them.

  alliteration  three or more different words within six consecutive words
                that open with the same consonant sound
  assonance     three or more different words within six consecutive words
                whose first vowel maps to the same long vowel class, or four
                or more for a short vowel class

Function words and words under three letters are skipped. Standard library only.
"""
from __future__ import annotations

import re

from . import devices_lex as X

WINDOW = 6
_SKIP = X.FUNCTION - {"such", "some", "many", "few"}
_ONSETS = (("ph", "f"), ("kn", "n"), ("wr", "r"), ("wh", "w"), ("qu", "k"), ("ps", "s"),
           ("ch", "ch"), ("sh", "sh"), ("th", "th"), ("ck", "k"), ("x", "z"))
_LONG = (("igh", "EYE"), ("ee", "EE"), ("ea", "EE"), ("ie", "EE"), ("ai", "AY"), ("ay", "AY"),
         ("ey", "AY"), ("ei", "AY"), ("oa", "OH"), ("ow", "OH"), ("oe", "OH"), ("oo", "OO"),
         ("ue", "OO"), ("ew", "OO"), ("ou", "OW"), ("oi", "OY"), ("oy", "OY"))
_SHORT = {"a": "A", "e": "E", "i": "I", "o": "O", "u": "U", "y": "I"}
_MAGIC = re.compile(r"^[^aeiouy]*([aeiou])((?:ch|sh|th|ck|[^aeiouy]))e(?:s|d|r|ly|n)?$|"
                    r"^[^aeiouy]*([aeiou])((?:ch|sh|th|[^aeiouy]))e[^aeiouy]")


def onset(word):
    w = X.norm(word)
    if not w or w[0] in "aeiou":
        return None
    for pre, sound in _ONSETS:
        if w.startswith(pre):
            return sound
    if w[0] == "c":
        return "s" if len(w) > 1 and w[1] in "eiy" else "k"
    if w[0] == "g" and len(w) > 1 and w[1] in "eiy":
        return None
    return w[0]


def vowel(word):
    """(class, is_long) of the first vowel sound, from spelling."""
    w = X.norm(word).lstrip("'")
    if w.endswith("y") and not re.search(r"[aeiou]", w[:-1]):
        return ("EYE", True)
    m = re.search(r"[aeiouy]+", w)
    if not m or (m.start() == 0 and w[0] == "y" and len(m.group(0)) == 1):
        m = re.search(r"[aeiou]+", w)
        if not m:
            return None
    g = m.group(0)
    for pre, cls in _LONG:
        if w[m.start():].startswith(pre):
            return (cls, True)
    mm = _MAGIC.match(w)
    if mm and len(g) == 1:
        v = mm.group(1) or mm.group(3)
        return ({"a": "AY", "e": "EE", "i": "EYE", "o": "OH", "u": "OO"}[v], True)
    if g[0] == "o" and w[m.end():m.end() + 2] in ("ld", "st") and len(g) == 1:
        return ("OH", True)
    return (_SHORT.get(g[0]), False)


def _windows(sents, key, need):
    out = []
    for start, s in sents:
        ws = X.words(s)
        for i in range(len(ws)):
            win = ws[i:i + WINDOW]
            groups = {}
            for w in win:
                n = X.norm(w)
                if len(n) < 3 or n in _SKIP:
                    continue
                k = key(w)
                if k is None:
                    continue
                groups.setdefault(k, set()).add(X.lemma(w))
            best = next(((k, g) for k, g in groups.items() if len(g) >= need(k)), None)
            if best:
                out.append((start, " ".join(win), best[0]))
                break
    return out


def alliteration(sents):
    return [{"device": "alliteration", "start": st, "snippet": snip, "detail": f"onset '{k}'"}
            for st, snip, k in _windows(sents, onset, lambda k: 3)]


def assonance(sents):
    return [{"device": "assonance", "start": st, "snippet": snip, "detail": f"vowel {k[0]}"}
            for st, snip, k in _windows(sents, vowel, lambda k: 3 if k[1] else 4)]
