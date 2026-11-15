"""The genre layer: narrative and expressive prose read by convention.

These pin the correctness prerequisites the layer stands on (quoted-speech
exclusion, the verse line unit, the screenplay Fountain classifier) and the
per-genre deltas (device categories report-only or removed, the report-only
fiction lexicon that never gates).
"""
import articulate
from articulate import detector, genres, modes, profiles, receipt


def _cats(r):
    return {f["category"] for f in r["high"] + r["medium"] + r["low"]}


# --- plumbing -------------------------------------------------------------- #

def test_genres_load_and_expose_fields():
    for name in genres.names():
        g = genres.load(name)
        assert g["slop"] in {"off", "flavored", "strict"}
        assert "unit" in g and "fiction_slop" in g and "dialogue_exempt" in g
    assert "poetry" in genres.names()
    assert genres.load("poetry")["unit"] == "line"
    assert genres.load("screenplay")["structural_classify"] == "fountain"


def test_profiles_resolve_a_genre_name():
    p = profiles.load("literary-fiction")
    assert p["genre"] == "literary-fiction" and p["slop"] == "off"


def test_genre_modes_carry_their_genre_fields():
    m = modes.load("screenplay/narrate")
    assert m["structural_classify"] == "fountain" and m["slop"] == "flavored"
    m2 = modes.load("poetry/express")
    assert m2["unit"] == "line" and m2["slop"] == "off"


# --- P0-a: quoted speech is not the author's prose ------------------------- #

DIALOGUE = '"Wait," she said. "This is not a drill, but a warning."\n'


def test_dialogue_tag_not_counted_as_narration():
    lit = articulate.check_text(DIALOGUE, profile=profiles.load("literary-fiction"))
    flav = articulate.check_text(DIALOGUE, profile=profiles.load("flavored"))
    assert "antithesis" not in _cats(lit), "quoted antithesis must be exempt in fiction"
    assert "antithesis" in _cats(flav), "the same device flags outside a genre"


TESTIMONY = ('He told me once, "I am not angry, but disappointed."\n'
             'I never forgot the phrasing.\n')


def test_quoted_testimony_excluded_in_memoir():
    memoir = articulate.check_text(TESTIMONY, profile=profiles.load("memoir"))
    flav = articulate.check_text(TESTIMONY, profile=profiles.load("flavored"))
    assert "antithesis" not in _cats(memoir)
    assert "antithesis" in _cats(flav)


# --- the report-only fiction lexicon --------------------------------------- #

SOMATIC = "A shiver ran down her spine as she read the note, and she could not help but stare.\n"


def test_fiction_slop_is_advisory_never_gates():
    lit = articulate.check_text(SOMATIC, profile=profiles.load("literary-fiction"))
    assert "fiction-slop-lexicon" in _cats(lit)
    assert lit["gate"] == "ok"      # it is a LOW advisory; it never blocks
    # off the genre axis, the lexicon does not run at all
    flav = articulate.check_text(SOMATIC, profile=profiles.load("flavored"))
    assert "fiction-slop-lexicon" not in _cats(flav)


# --- poetry: the line is the unit; craft devices are technique ------------- #

VERSE = ("I do not weep, but sing,\n"
         "the sea, the stars, and the wind.\n"
         "You cannot hold the tide.\n"
         "You can only watch the tide.\n")


def test_poetry_removes_device_categories():
    poem = articulate.check_text(VERSE, profile=profiles.load("poetry"))
    cats = _cats(poem)
    for banned in ("antithesis", "rule-of-three", "contrast-pair",
                   "negative-parallel", "cadence"):
        assert banned not in cats, f"{banned} must be absent from a poetry report"
    assert poem["cadence"]["uniform"] is False


def test_verse_devices_do_flag_outside_poetry():
    # The same lines under a prose profile do surface the devices, proving the
    # poetry result is suppression, not an empty scan.
    prose = articulate.check_text(VERSE, profile=profiles.load("flavored"))
    assert "antithesis" in _cats(prose)


# --- screenplay: Fountain roles decide what is scanned --------------------- #

SCREEN_DIALOGUE = ("INT. ROOM - NIGHT\n"
                   "\n"
                   "SAM\n"
                   "This is not a drill, but a warning.\n")

SCREEN_ACTION = ("INT. ROOM - NIGHT\n"
                 "\n"
                 "Sam leaves, not the way he came.\n")


def test_screenplay_dialogue_is_exempt():
    r = articulate.check_text(SCREEN_DIALOGUE, profile=profiles.load("screenplay"))
    assert "antithesis" not in _cats(r)   # the device sits in dialogue
    assert r["gate"] == "ok"


def test_screenplay_action_keeps_the_device_gate():
    r = articulate.check_text(SCREEN_ACTION, profile=profiles.load("screenplay"))
    assert r["gate"] == "blocked"         # a banned device on an action line gates
    assert any(f["category"] == "corrective-negation" for f in r["high"])


def test_fountain_classifier_types_lines():
    lines = SCREEN_DIALOGUE.splitlines(keepends=True)
    roles = detector.classify_fountain(lines)
    assert roles[0] == "slug"
    assert roles[2] == "character"
    assert roles[3] == "dialogue"


# --- a genre verdict is still re-derivable --------------------------------- #

def test_genre_receipt_replays_to_match():
    rec = receipt.make_receipt(SOMATIC, "literary-fiction")
    verdict, _ = receipt.verify_receipt(rec, SOMATIC)
    assert verdict == "Match"


# --- the floor still holds: a genre never re-enables a gated device on prose #

def test_screenplay_action_floor_is_not_liftable():
    # Screenplay sits at flavored, so HIGH devices on action lines gate; the
    # genre layer only exempts dialogue and structure, it does not un-gate prose.
    r = articulate.check_text("Sam leaves, not the way he came.\n",
                              profile=profiles.load("screenplay"))
    assert r["gate"] == "blocked"
