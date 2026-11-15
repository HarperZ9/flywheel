"""Closed word lists for reading imagery and the work a device does.

IMAGE holds nouns a reader can picture: things with a shape, a place, a body,
weather, light and machines. THING holds the concrete nouns of technical prose
(a file, a log, a test, a token): a reader can point at them, though they paint
no picture. SENSE holds verbs of seeing, hearing, touch and
motion that put a reader inside a scene. STOCK holds the vehicles machine text
reaches for by default (journey, tapestry, landscape, beacon); a figure built
on one of them carries no picture of its own. ABSTRACT_END catches nouns of
state and quality by suffix (-tion, -ity, -ness, -ment, -ance, -ence, -ism).

Every list is small and auditable. A hit is a reading of surface words; it
places a sentence on the concrete or the abstract side, and the author judges
the sentence. Standard library only.
"""
from __future__ import annotations

import re

IMAGE = frozenset("""
air alley anchor apple arm ash asphalt attic axe back badge ball bank bar barn basement
beach beam bed bell belt bench bike bird blade blanket blood boat body bolt bone book boot
bottle bowl box brick bridge bucket bulb bus cable cage camera candle canvas car card cart
cat chain chair chalk cigarette clock cloth cloud coal coat coffee coin collar concrete cord
corner couch counter crack crowd cup curb curtain dashboard dawn deck desk dirt dock dog door
drain drawer dress drum dust ear earth edge elbow engine eye face fan feather fence field
finger fire fist flag flame flood floor flower fog foot forest fork frame freeway frost gate
gauge glass glove grass gravel gun hair hall hammer hand handle harbor hat head headlight
heart hill hinge hole hook horse hose house ice ink iron jacket jar jaw kettle key kitchen
knee knife knot ladder lake lamp lane leaf ledge lens light lighthouse lip lock mast match
mattress metal meter mirror moon motor mountain mouth mud nail needle neon nerve net
newspaper night noise nose oar ocean oil pages paint pan paper path pavement pen pencil
phone pipe plate pocket porch pot puddle pulse radio rail rain razor receipt ridge ring river
road rock roof room rope rot rust sail salt sand scale scar screen sea seat shadow shelf shell
ship shirt shoe shore shoulder sidewalk sign signal sink skin skull sky slate smoke snow soap
socket soil spark spine spoon stain stairs stake steel stem stone storm stove street string
sun table tape teeth thread throat thumb tide tile tire tongue tooth torch tower track train
tree truck tunnel valve van vein wall wallet water wave weight well wheel whistle window wind
windshield wing wire wood wound wrist yard
""".split())

SENSE = frozenset("""
saw see sees seen watch watched watching stare stared glare glared glint glinted glow glowed
flicker flickered flash flashed blink blinked squint squinted hear heard listen listened hum
hummed hiss hissed crack cracked snap snapped thud rattle rattled creak creaked drip dripped
smell smelled smelt taste tasted touch touched burn burned burnt freeze froze sweat sweated
shiver shivered grip gripped claw clawed scrape scraped bleed bled shatter shattered spill
spilled pour poured sink sank float floated drown drowned climb climbed fall fell crawl crawled
""".split())

# Things a reader can point at in technical prose: not pictures, still concrete.
THING = frozenset("""
attachment byte bytes code command commit credential credentials database disk email emails
file files hash input key keys line lines log logs machine machines message messages model
number numbers output page pages password passage passages patch program programs record
records repo repository row rows server servers source sources table tables test tests
token tokens tool tools url version
""".split())

STOCK = frozenset("""
journey tapestry landscape beacon symphony testament cornerstone realm tapestries rollercoaster
odyssey catalyst paradigm ecosystem synergy treasure gem gateway roadmap blueprint
""".split())

STOCK_PHRASES = re.compile(
    r"(?i)\b(?:double-edged sword|tip of the iceberg|perfect storm|deep dive|north star|"
    r"rich tapestry|ever-evolving landscape|game[- ]changer|a beacon of|at the heart of|"
    r"the fabric of|a testament to|unlock(?:s|ing)? the (?:power|potential))\b")

ABSTRACT_END = re.compile(r"(?i)[a-z]{3,}(?:tion|sion|ity|ness|ment|ance|ence|ism|ship)s?$")

ANCHOR = re.compile(
    r"\d|[\"“][^\"”]{3,}[\"”]|`[^`]+`|https?://|(?<=[a-z,;] )[A-Z][a-z]{2,}")

STANCE = re.compile(
    r"(?i)\b(?:because|so that|which means|until|unless|therefore|that's why|"
    r"I (?:think|bet|doubt|know|saw|watched|refuse|won't|don't|can't|wrote|built|got)|"
    r"you (?:think|know|can|will|won't|don't))\b")


def image_words(words):
    """The words in words that a reader can picture, lower-cased."""
    out = []
    for w in words:
        low = w.lower().strip("'’")
        stem = low[:-1] if low.endswith("s") and low[:-1] in IMAGE else low
        if stem in IMAGE or low in SENSE:
            out.append(low)
    return out


def thing_words(words):
    """The words in words that name a concrete technical thing, lower-cased."""
    return [w.lower() for w in words if w.lower() in THING]


def abstract_words(words):
    return [w.lower() for w in words if ABSTRACT_END.search(w) or w.lower() in STOCK]
