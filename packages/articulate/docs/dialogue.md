# Dialogue and character voice

`articulate dialogue` reads a script, holds every spoken line to a dialogue
profile, checks each line against its speaker's voice sheet, and measures how
easily a plain classifier can tell the characters apart. It edits nothing. The
report names the lines to read and says why each one was picked.

```
articulate dialogue content/ --voices voice-sheets/
articulate dialogue content/ --voices voice-sheets/ --json > report.json
articulate dialogue content/ --voices voice-sheets/ --markdown VOICE-AUDIT.md
articulate dialogue content/ --voices voice-sheets/ --gate
```

Folders are walked for `.lwd`, `.txt`, `.md`, `.script` and `.dialogue` files.
Hidden folders are skipped. MCP hosts get the same audit as the `dialogue_check`
tool, which takes the script text and the voice sheets as arguments and opens
no file.

## Script formats

| Format | Shape |
|:-|:-|
| `lwd` | `line: NAME: text`, or `line: text` under a node's `speaker: NAME`. A trailing `{when: ...}` gate is kept apart from the text. |
| `colon` | One `NAME: text` per line. |
| `play` | A printed play: `NAME. speech`, `NAME [direction] speech`, or `NAME.` alone above the speech. Stage directions in brackets are dropped. |

`--format auto`, the default, picks one from the file name and the text.

## The dialogue profile

Prose rules do not fit fiction dialogue. People repeat themselves, stop halfway,
drop words and talk in fragments, and the profile leaves all of that alone. It
looks for the shapes a model reaches for when it writes a character.

| Check | Weight | Example of the shape |
|:-|-:|:-|
| `antithesis` | 3 | One of the prose detector's antithesis frames that holds in speech. |
| `contrast-pair` | 3 | "We do not call it broken. We call it opened." |
| `epigram-semicolon` | 3 | "If you drink, you die; if you don't drink, you die." |
| `epigram-definition` | 3 | "Mercy is a tide." "I am logic." |
| `epigram-maxim` | 2 | "No married man is ever attractive except to his wife." |
| `epigram-here` | 3 | "In Hesk they count the money. Here we count the tide." |
| `theme-statement` | 2 | A general claim that uses one of the project's theme words. |
| `closing-zinger` | 2 | A short aphoristic sentence after longer ones. |
| `abstract-density` | 1 | Two or more abstract nouns at 12 percent of the words or more. |

A line's score is the sum of its weights, with the voice-sheet checks below
added in. Theme words come from `--theme` or the voices folder's
`_project.json`, and the theme check runs when one of them sets theme words.

### Calibration

The profile was tuned on dialogue that people wrote, all of it in the public
domain in the United States and read from Project Gutenberg. Oscar Wilde is the
contrast case: his characters speak in epigrams on purpose, so the epigram
checks ought to fire on him more than on the others. They do. The figures come
from `scripts/dialogue_calibrate.py`, which writes
`docs/dialogue-calibration.json` with each source file's SHA-256.
Intervals are Wilson 95%.

| Source (Gutenberg eBook) | Lines | Any finding | Epigram shape |
|:-|-:|:-|:-|
| Shaw, *Pygmalion* (3825) | 998 | 1.4% (0.8 to 2.3) | 0.10% (0.02 to 0.57) |
| Shaw, *Arms and the Man* (3618) | 747 | 1.2% (0.6 to 2.3) | 0.13% (0.02 to 0.75) |
| Chekhov, *The Sea-Gull*, tr. Fell (1754) | 621 | 2.6% (1.6 to 4.1) | 0.32% (0.09 to 1.17) |
| Chekhov, *Plays, Second Series*, tr. West (7986) | 2282 | 2.4% (1.8 to 3.1) | 0.48% (0.27 to 0.86) |
| Twain, *Huckleberry Finn* (76), quoted speech | 1393 | 1.2% (0.8 to 1.9) | 0.29% (0.11 to 0.74) |
| Dickens, *Great Expectations* (1400), quoted speech | 2578 | 1.6% (1.2 to 2.2) | 0.23% (0.11 to 0.51) |
| Wilde, *The Importance of Being Earnest* (844), contrast | 876 | 3.0% (2.0 to 4.3) | 1.60% (0.95 to 2.66) |

The gate's default epigram ceiling, 1 percent of lines, sits above every
naturalistic source and below Wilde. The rules were adjusted by hand while
reading these hits: a semicolon now needs a negation turn with a shared word or
a definition on one side, because Shaw joins plain clauses with semicolons all
the time; and a sentence about something that happened ("Nobody's ever
measured", "There was nothing below") is reporting and does not count as a rule
about the world.

## Voice sheets

A voices folder holds one JSON file per character. `name` is required and every
other field is optional; each check runs when its field is present.

```json
{
  "format": "articulate-voice-sheet/1",
  "name": "TUB",
  "aliases": ["MERROW"],
  "register": {"level": "plain", "education": "none", "class": "poor",
               "trade": "salvor", "words": ["salvage", "gully"]},
  "region": {"name": "the harbour", "markers": ["I'll not"], "idioms": ["on the turn"]},
  "sentence_length": {"min": 1, "max": 12},
  "contractions": true,
  "questions": "never",
  "never": ["okay"],
  "never_patterns": [{"re": "\\bwhom\\b", "msg": "never says whom"}],
  "knowledge": {"knows": ["the floor"],
                "unknown": [{"terms": ["works order"], "why": "the harbourmaster's secret",
                             "unless_gate": ["works.order"]}]},
  "wants": "to be left alone", "fears": "the rope", "hides": "the copper",
  "tics": ["tide", "copper"]
}
```

| Check | Weight | What it reports |
|:-|-:|:-|
| `never` | 3 | A word or phrase from `never`. |
| `knowledge-leak` | 3 | A term from `knowledge.unknown`, unless the line's group, node or LWD gate is listed in the bound's `unless_group`, `unless_node` or `unless_gate`. |
| `never-pattern` | 2 | A match for one of `never_patterns`. |
| `questions` | 2 | A question from a character who never asks one, or a statement from one who speaks only in questions. |
| `register` | 1 | For `plain`, long or Latinate words; for `middle`, words of five syllables or more. Trade words in `register.words` and names are allowed. |
| `sentence-length` | 1 | A sentence outside `sentence_length`. |
| `contractions` | 1 | A contraction from a character with `contractions: false`. |

Words a character quotes from someone else are masked for the register,
never-word and contraction checks. The knowledge check is a keyword bound. It
finds a word, so a hit is a place to look and does not prove a leak. `wants`,
`fears` and `hides` are not checked; they sit in the sheet for the writer.
Tic, region-marker and idiom use is reported per character as a share of lines.

## Blind attribution

A complement naive Bayes classifier over words, word pairs, character trigrams
and punctuation is trained on four fifths of the script and asked who said each
line in the other fifth. Each speaker's lines are cut into five runs in script
order, so a held-out line's own scene is mostly held out with it. Priors are
uniform. Speakers with fewer than `--min-lines` lines, 20 by default, are left
out.

The report gives each speaker's per-line accuracy with a Wilson 95% interval,
chance (one over the number of speakers), and a 5-line score where the
classifier sees five held-out lines at once. A per-line score near chance means
the voice is generic. A line whose true speaker ranks below the top quarter,
with six words or more, is flagged `generic` at weight 1.

On the calibration plays, mean per-speaker accuracy was 0.51 for *Pygmalion*
(chance 0.14), 0.30 for *Arms and the Man* (0.13), 0.24 for *The Sea-Gull*
(0.14) and 0.29 for *The Importance of Being Earnest* (0.14). Accuracy falls
as the cast grows, so compare a character with chance and with the rest of
the same cast, and do not compare scores across scripts with different casts.

## Gate

`--gate` exits 1 when the share of lines with an epigram shape is over
`--max-epigram-rate` (default 0.01), when any `never` or `knowledge-leak`
finding is present, or, with `--min-lift X`, when a sheeted speaker's
attribution upper bound is under X times chance.

## What it does not prove

Pattern hits and attribution scores locate lines to read. A deliberate epigram
is still flagged, and the writer may keep it. A character can score as
distinctive through one repeated tic, and a high score says nothing about
whether the voice is good. The classifier measures surface vocabulary and
punctuation; it does not read meaning, intent or what a character knows.

Recall on model-written dialogue is not measured: there is no labelled set of
model-written scripts in the calibration yet. One small probe: the quoted speech
in the 12 local-model fiction samples of `corpus/provenance/ai/` gives 29
speeches, and 3 of them drew a finding (10%, Wilson 95% 4 to 26), against 1.2 to
3.0 percent on the human sources above. That is too few to estimate recall. The
calibration shows how often the checks fire on dialogue people wrote, so a low
rate on a script shows the named shapes are rare in it, and does not show the
script reads as written by a person.
