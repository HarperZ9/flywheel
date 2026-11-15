"""Fixed word lists for the series and voice features.

FUNCTION_WORDS is a closed list of English function words: articles,
pronouns, prepositions, conjunctions, auxiliaries, negators, common adverbs of
degree and time, and question words. Function-word rates are the classic
stylometric measure (Mosteller and Wallace), and a profile built on them holds
no content word, no name and no sentence. The list is written out here so the
package carries no data file and no third-party word list.

No general-English frequency list ships with this release. The voice profile's
vocabulary field is relative to the author's own samples (see voice.py).
"""

FUNCTION_WORD_LIST = (
    "a an the "
    "i me my mine myself we us our ours ourselves you your yours yourself "
    "he him his himself she her hers herself it its itself they them their theirs "
    "themselves this that these those who whom whose which what whatever whoever "
    "one ones someone somebody something anyone anybody anything everyone everybody "
    "everything nobody nothing none each every either neither both all any some "
    "few many much more most less least several other another such own same "
    "about above across after against along among around as at before behind below "
    "beneath beside besides between beyond by despite down during except for from in "
    "inside into like near of off on onto out outside over past since than through "
    "throughout till to toward towards under underneath until unlike up upon via "
    "with within without "
    "and but or nor so yet because although though while whereas if unless whether "
    "once when whenever where wherever after before then "
    "am is are was were be been being have has had having do does did doing "
    "will would shall should can could may might must ought "
    "not no never n't "
    "very quite rather too also just only even still already almost always often "
    "sometimes usually ever again here there now perhaps maybe really enough "
    "how why however therefore thus instead otherwise indeed "
    "yes okay well "
)

FUNCTION_WORDS = frozenset(FUNCTION_WORD_LIST.split())

# A closed list for title skeletons: words that carry the shape of a title.
TITLE_CLOSED = frozenset((
    "a an the of for in on at to from by with without about behind before after "
    "than into over under between through is was are were be been not never no nor "
    "who what why how where when which has have had do does did can cannot could "
    "will would should may might must i you he she it we they me him her us them my "
    "your his its our their this that these those and or but just"
).split())
