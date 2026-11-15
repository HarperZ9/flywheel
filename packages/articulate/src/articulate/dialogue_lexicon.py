"""Word lists and small text helpers shared by the dialogue checks.

Standard library only. The lists are short on purpose: each entry is a word a
reader hears as an abstraction or as a learned word when a character says it
aloud. They were checked against the public-domain calibration set described
in docs/dialogue.md, and words that fired on ordinary speech there were cut.
"""
import re

WORD = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)*")
_SENT_END = re.compile(r"(?<=[.!?…])[\"'”’)\]]*\s+(?=[\"'“‘(]*[A-Z0-9])")

# Bare abstract nouns. Suffix forms (-ness, -ity and the rest) are found by rule.
ABSTRACT_BARE = frozenset("""
truth justice fault guilt blame faith hope fear mercy honour honor duty shame pride
grief sorrow virtue sin wisdom beauty freedom fate destiny memory silence meaning
history arithmetic logic reason innocence evil wickedness cruelty kindness loyalty
betrayal power authority conscience vanity glory despair dignity purpose
""".split())
ABSTRACT_SUFFIXES = ("ness", "ity", "tion", "sion", "ment", "ance", "ence", "ism",
                     "dom", "hood", "ship")
# Concrete or everyday words that end like abstractions.
NOT_ABSTRACT = frozenset("""
station nation ration lotion potion portion option mention question section motion
caution fashion mansion pension passion cushion onion union million billion lion
apartment basement garment instrument document comment moment payment shipment
ointment parliament compartment department pavement settlement cement element
apparatus city pity kitty ditty witty gritty pretty entity
business witness harness wilderness darkness distance chance dance fence hence
whence thence once sentence evidence presence absence science offence
offense ambulance balance entrance allowance substance glance lance romance
providence residence fragment ornament lament
kingdom seldom random boredom
ship worship hardship township friendship courtship partnership
childhood neighbourhood neighborhood likelihood livelihood hood
""".split())

PRONOUNS = frozenset("i you he she it we they me him her us them".split())
FUNCTION = frozenset("""
a an the and or but if then so of to in on at by for with from as is are was were be been
being am do does did have has had not no nor yes it its it's this that these those there here
i you he she we they me him her us them my your his our their mine yours what which who whom
whose when where why how all any some each every one just only very too also up down out off
over under again will would shall should can could may might must
""".split())
NEGATION = re.compile(r"\b(?:not|no|never|nothing|nobody|none|nowhere|neither|nor|cannot|"
                      r"\w+n['’]t)\b", re.I)
COPULA = re.compile(r"\b(?:is|are|was|were|am|['’]s|['’]re|['’]m)\b", re.I)


def words(text):
    return WORD.findall(text)


def sentences(text):
    """Split one spoken line into sentences. Ellipses and dashes stay inside."""
    parts = _SENT_END.split(text.strip())
    return [p.strip() for p in parts if WORD.search(p)]


def is_abstract(word):
    w = word.lower().replace("’", "'")
    if w in ABSTRACT_BARE:
        return True
    if w in NOT_ABSTRACT or len(w) < 6:
        return False
    return w.endswith(ABSTRACT_SUFFIXES)


def abstract_nouns(text):
    return [w for w in words(text) if is_abstract(w)]


def syllables(word):
    """A vowel-group count, close enough to tell 'arithmetic' from 'tide'."""
    w = word.lower()
    w = re.sub(r"(?<=[^aeiouy])e(?=ly$|ment$|ful$|ness$)", "", w)   # separately
    w = re.sub(r"(?<=[^aeiouytd])ed$", "d", w)                        # apologised
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and not w.endswith(("le", "ee", "ye")) and n > 1:
        n -= 1
    return max(1, n)


LATINATE = ("ation", "ition", "ution", "ality", "ility", "osity", "ivity", "ence", "ance",
            "ient", "ious", "eous", "ative", "itive", "ulate", "icate", "ify", "ism", "ology",
            "ament", "iment", "ure")


def learned(word):
    """A word a plain speaker rarely reaches for: long, or Latinate by suffix."""
    w = word.lower()
    if plain_long(w):
        return False
    s = syllables(w)
    return s >= 5 or (s >= 4 and w.endswith(LATINATE))


def plain_long(word):
    """Long words anyone says: compounds of every/any/some/no, and the concrete
    words that end like abstractions."""
    w = word.lower()
    return (w in NOT_ABSTRACT or "'" in w or "’" in w
            or bool(re.match(r"^(?:every|any|some|no)(?:body|thing|one|where)$", w)))


def content_words(text):
    return {w.lower() for w in words(text) if len(w) >= 4 and w.lower() not in FUNCTION}
