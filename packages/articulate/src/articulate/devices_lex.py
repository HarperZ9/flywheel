"""Word lists and token helpers for the device readers.

Everything here is a closed list a reader can audit: function words, opposition
axes for antithesis and oxymoron, and the noun classes the zeugma reader uses.
A list entry is a claim about English usage, and each list is small on purpose:
a reader built on it reports a shape, never a judgment about the writer.

Standard library only.
"""
from __future__ import annotations

import re

WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")

ARTICLES = frozenset({"the", "a", "an"})
COORD = frozenset({"and", "or", "nor", "but", "yet", "so", "for", "then", "than"})
PRONOUN_SUBJ = frozenset({"i", "you", "he", "she", "it", "we", "they", "this", "that",
                          "these", "those", "there"})
FUNCTION = frozenset("""
a an the and or nor but yet so for then than if as at by in on of to from with into onto
upon over under about after before between through during without within is am are was were
be been being has have had do does did will would shall should can could may might must
i you he she it we they me him her us them my your his its our their mine yours this that
these those there here what which who whom whose when where why how not no n't all any
each every some such very just only also too more most much many few own same other
""".split())


def words(text):
    return WORD.findall(text.replace("’", "'"))


def norm(w):
    return w.lower().replace("’", "'")


def forms(w):
    """Candidate base forms of a word: itself and light suffix strips."""
    w = norm(w)
    out = {w}
    for suf, add in (("ies", "y"), ("es", ""), ("s", ""), ("ing", ""), ("ing", "e"),
                     ("ed", ""), ("ed", "e"), ("d", ""), ("ly", "")):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            out.add(w[: len(w) - len(suf)] + add)
    return out


def lemma(w):
    """One canonical form, so 'owes' and 'owe' compare equal."""
    return min(forms(w), key=lambda f: (len(f), f))


def same_word(a, b):
    return bool(forms(a) & forms(b))


def skeleton(ws):
    """Function words kept, content words as '_', subject pronouns as 'S'."""
    out = []
    for w in ws:
        n = norm(w)
        if n in PRONOUN_SUBJ:
            out.append("S")
        elif n in FUNCTION:
            out.append(n)
        else:
            out.append("_")
    return out


def content(ws):
    return [w for w in ws if norm(w) not in FUNCTION]


# Opposition axes: word -> (axis, sign). Two words on one axis with opposite
# signs oppose each other. Forms are matched through forms().
_AXES = {
    "temperature": ("hot fire burning warm heat summer", "cold ice frozen freezing cool winter"),
    "sound": ("loud deafening roaring noise noisy", "silence silent quiet hush still"),
    "light": ("bright shining light day sun", "dark smoke shadow night black darkness"),
    "weight": ("heavy lead", "feather"),
    "valence": ("sweet love loving joy happy pleasant kind kindness good best gentle",
                "sorrow hate hateful bitter sad grief brawling cruel bad worst evil harsh"),
    "life": ("living live alive life born birth", "death dead deadly die dying kill"),
    "health": ("health healthy heal well", "sick ill disease"),
    "secrecy": ("open public", "secret hidden"),
    "size": ("giant huge large big great", "small tiny"),
    "truth": ("true truth right", "false lie wrong"),
    "wisdom": ("wise wisdom", "foolish fool foolishness"),
    "amount": ("many more most all everyone", "few fewer less least none nobody"),
    "order": ("first begin beginning start", "last end ending finish"),
    "age": ("young new", "old"),
    "height": ("high rise up", "low fall down"),
    "speed": ("fast quick", "slow"),
    "ease": ("easy", "hard difficult"),
    "union": ("united unite together", "divided divide apart"),
    "standing": ("stand", "fall"),
    "victory": ("win won victory", "lose lost defeat"),
    "exchange": ("give", "take"),
    "memory": ("remember", "forget"),
    "rule": ("reign rule", "serve"),
    "realm": ("heaven", "hell"),
    "nature": ("spirit", "flesh"),
    "standing2": ("human mortal", "divine immortal"),
    "fairness": ("fair", "foul"),
    "wealth": ("rich wealth", "poor poverty"),
    "conflict": ("peace friend", "war enemy foe"),
}
AXIS = {}
for _axis, (_pos, _neg) in _AXES.items():
    for _w in _pos.split():
        AXIS[_w] = (_axis, 1)
    for _w in _neg.split():
        AXIS[_w] = (_axis, -1)


def pole(w):
    for f in forms(w):
        if f in AXIS:
            return AXIS[f]
    return None


def opposed(a, b):
    pa, pb = pole(a), pole(b)
    return bool(pa and pb and pa[0] == pb[0] and pa[1] != pb[1])


# Noun classes for zeugma: one head taking a concrete object and an abstract
# state in one breath ("took his hat and his leave").
CONCRETE = frozenset("""
hat coat cap keys key wallet phone umbrella train bus car taxi plane chair door book bag
purse glasses ring shoes boots bread cup sedan coach horse ship boat letter pen sword
""".split())
ABSTRACT = frozenset("""
leave temper heart breath mind nerve cool patience dignity innocence hope faith
composure chance chances word advice offence offense cold fever tears hurry huff rage
shock trouble debt time life reputation bearings senses
""".split())


_CLASS = {}
for _cls, _ws in (
        ("S", "i you he she it we they"),
        ("PRON", "me him her us them my your his its our their mine yours theirs ours hers"),
        ("AUX", "is am are was were be been being has have had do does did will would shall "
                "should can could may might must"),
        ("DET", "the a an this that these those"),
        ("PREP", "of to in on at by with from into onto upon over under about after before "
                 "between through during without within"),
        ("QUANT", "all any each every some such more most much many few less least none no"),
        ("NEG", "not never n't"),
        ("CONJ", "and or nor but yet so for then than if as"),
        ("WH", "what which who whom whose when where why how there here")):
    for _w in _ws.split():
        _CLASS[_w] = _cls


def classes(ws):
    """Coarse word classes: function words by role, content words as '_'."""
    return [_CLASS.get(norm(w), "_") for w in ws]
