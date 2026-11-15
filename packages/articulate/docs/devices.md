# Devices

`articulate devices` finds rhetorical devices in a text and shows where they
are. It reads thirteen devices, and every finding has a line, a passage and a
short detail.

```
articulate devices draft.md
articulate devices draft.md --json
articulate devices draft.md --only anaphora,tricolon
articulate devices draft.md --speak      # a script to read aloud
articulate devices draft.md --ssml       # the same script as SSML 1.1
```

A device is a shape writers of every kind use, on purpose and by habit. The
report never gates a check, and it says nothing about who wrote a text. Use it
to see the shapes a draft leans on, to study a writer you admire, or to check
that an edit kept the figure you meant to keep.

Python API: `articulate.devices.analyze(text)` returns `findings` and `counts`.

## What each reader looks for

| Device | Reader |
|:-|:-|
| antithesis | opposed words across two balanced clauses (`To err is human, to forgive divine`), a negated clause answered by a parallel one, or a negated clause answered by a subjectless `but` clause |
| tricolon | three parallel members of up to six words, with or without a serial comma, and none past the third |
| anaphora | three or more sentences, or clauses inside one sentence, that open with the same word; two words when the first is an article |
| chiasmus | two content words in A B ... B A order across a clause boundary, each used twice |
| alliteration | three different words within six that open with the same consonant sound |
| assonance | three different words within six that share a long vowel sound, or four that share a short one |
| polysyndeton | one conjunction before each of three or more short members |
| asyndeton | three or more parallel members with no conjunction |
| anadiplosis | a clause that ends on the word the next clause opens with |
| epizeuxis | a word said again at once; `that that` and `had had` need a third |
| isocolon | adjacent clauses within one word of each other in length and with a matching word-class skeleton |
| zeugma | one head taking a concrete object and an abstract one (`took his hat and his leave`) |
| oxymoron | opposed words side by side (`deafening silence`) |

The opposition lists, the function-word classes and the zeugma noun classes
are in `articulate/devices_lex.py`. Sound readers map spelling to a coarse
sound class, so `cough` and `though` can mislead them. A finding from them is a
pointer for the ear.

## How well they read

Rates come from `tests/data/core_devices/devices_v2.json`, scored by
`scripts/device_readers_eval.py`. Full results with intervals and every miss
by name are in `corpus/core-devices/devices-v2-results-2026-10-26.json`.

The fixture has three splits:

- **dev** (76 items). The readers were tuned on these.
- **heldout** (45 items). Written and labelled before any reader existed, by
  the person who built the readers. That person knew these items while writing
  the opposition lists, so this split is not independent of the readers.
- **heldout-independent** (80 items). Written by a separate agent that saw only
  the definitions, never the readers, the lists or the other items. Merged after
  the reader source was frozen.

Each cell is hits over labelled positives, then false alarms over labelled
negatives.

| Device | dev recall | dev false alarms | heldout recall | heldout false alarms | independent recall | independent false alarms |
|:-|-:|-:|-:|-:|-:|-:|
| antithesis | 16/17 | 1/59 | 4/6 | 1/39 | 8/12 | 1/68 |
| tricolon | 10/11 | 2/65 | 5/6 | 4/39 | 6/8 | 6/72 |
| anaphora | 12/12 | 1/64 | 3/4 | 0/41 | 4/4 | 0/76 |
| chiasmus | 5/5 | 0/71 | 2/2 | 2/43 | 4/4 | 1/76 |
| alliteration | 4/4 | 0/72 | 3/3 | 0/42 | 5/5 | 0/75 |
| assonance | 1/2 | 0/74 | 2/2 | 0/43 | 3/4 | 4/76 |
| polysyndeton | 2/2 | 1/74 | 2/2 | 0/43 | 4/4 | 1/76 |
| asyndeton | 8/8 | 1/68 | 5/6 | 1/39 | 8/11 | 2/69 |
| anadiplosis | 4/4 | 0/72 | 3/3 | 0/42 | 4/4 | 2/76 |
| epizeuxis | 2/2 | 0/74 | 2/2 | 1/43 | 3/3 | 0/77 |
| isocolon | 23/24 | 1/52 | 12/16 | 4/29 | 17/20 | 5/60 |
| zeugma | 3/3 | 0/73 | 2/2 | 0/43 | 2/4 | 0/76 |
| oxymoron | 3/3 | 0/73 | 3/3 | 0/42 | 4/4 | 1/76 |

Read the independent column first. Most devices have 3 to 12 positives there,
so one item moves a rate by 8 to 33 points.

### Against the earlier readers

The check command reads antithesis, the triad and anaphora through narrow
patterns, and the voice tools read them again through sentence runs. On the
same items:

| Device | Split | Line checker | Run reader | `articulate devices` |
|:-|:-|:-|:-|:-|
| antithesis | heldout | 1/6, 2/39 | 0/6, 0/39 | 4/6, 1/39 |
| antithesis | independent | 0/12, 1/68 | 0/12, 0/68 | 8/12, 1/68 |
| tricolon | heldout | 1/6, 0/39 | 3/6, 1/39 | 5/6, 4/39 |
| tricolon | independent | 0/8, 2/72 | 2/8, 3/72 | 6/8, 6/72 |
| anaphora | heldout | 0/4, 0/41 | 1/4, 0/41 | 3/4, 0/41 |
| anaphora | independent | 0/4, 0/76 | 0/4, 0/76 | 4/4, 0/76 |

The triad reader trades false alarms for recall: plain lists of three
(`eggs, flour, and milk`) read as a tricolon. Telling a rhetorical triad from a
shopping list needs meaning, and these readers read form.

### Paraphrase and order

The metamer and isomer pairs in `tests/data/core_devices/passages.json` keep
meaning and change wording or order. Of 12 pairs that keep the device, the new
readers flip on 4: an antithesis with the affirmative half moved first, one
with the negation removed, one with the verb phrases reworded, and one placed
inside a quotation. The earlier line checker flipped on 6 of 10. All 4 pairs
that remove the device read as removed.

### Fairness

On the Liang TOEFL learner texts against length-matched US college essay
windows, and on PERSUADE learners against other students, no reader fires more
often on learner writing with an interval that excludes zero. Asyndeton fires
less often on the TOEFL texts, and the tricolon leans the same way within its
interval. Counts are in the results file.

## The spoken view

`--speak` turns findings into plain sentences for a voice: the line, the device
in words, then the passage. `--ssml` wraps the same script in SSML with a pause
before each passage and the passage emphasised. `articulate check --speak` does
the same for check findings. Nothing here makes a sound or calls a service; the
reader's own voice software speaks it.

## Survival in the change report

`fix --explain`, `polish --explain` and `submit --explain` now add `survival`
to the change report. It grades how much of each property came through the
edit, as a clarity value: 1 kept, below 1 lost, above 1 gained.

| Family | Clarity |
|:-|:-|
| items | each fact the meaning guard reads; a changed number or name reads 0, a modal reads its step on a strength scale (`must` 1.0, `should` 0.7, `may` 0.4) |
| devices | count after over count before, per device |
| rhythm | 1 minus the Kolmogorov-Smirnov distance between sentence-length distributions |
| order | (Kendall tau + 1) / 2 over sentences matched across the edit |
| register | 1 minus the relative change in contractions, person, nominalisations and word and sentence length |

The rules are fixed and set by hand. Survival reports; acceptance is still the
meaning guard's decision.

## Limits

- One annotator labelled the dev and heldout splits, and a second agent
  labelled the independent split. They disagree in places, for example on
  whether `Fair is foul, and foul is fair` carries anadiplosis. A second human
  annotator and an agreement figure are still to come.
- The readers have no part-of-speech tagger and no meaning model, so a factual
  list of three, a zeugma whose nouns are missing from the lists, and a vowel
  sound that spelling hides are all beyond them.
