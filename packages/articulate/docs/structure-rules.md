# Structure rules

The line checker reads one line at a time. A reply can pass it and still read as a row of short flat statements, three of them opening on one word, with each paragraph announced by its first sentence. The structure rules read a paragraph at a time and report those shapes.

They run under the `chat` profile and in the house voice notes. They do not run under `author-voice`, `narrative`, `essay` or the default profile, so deliberate anaphora in a person's own text raises nothing.

```bash
articulate check reply.md --profile chat --gate
```

In an MCP host, a model that checks its own reply to a person passes `profile: "chat"` to `check` or `score`. With no profile the two tools run the default line rules, as before, and a clean result then says nothing about structure.

## Reading a result

Every `check` and `score` result from the MCP tools carries `rules_run`, which names the profile and the rule packs that ran:

```json
"rules_run": {"profile": "chat", "rule_packs": ["structure"], "structure_rules": true}
```

An unprofiled call returns `"profile": "default"`, `"structure_rules": false` and a note that says to pass `chat`. Read `rules_run` before you read `clean`.

The texture score counts line rules only. Findings from a rule pack never feed it, so a reply can be blocked with a texture score of 0. A result that ran rule packs therefore carries `pack_findings`, the count of pack findings by tier, and the MCP result adds `texture_scope`, one sentence that says what the texture score leaves out. On a terminal the headline puts the pack count first:

```text
[articulate] reply.md [chat]: 8 high, 4 medium (blocked)  rule-pack findings 12, texture 0/100 (line rules only)
  L1:85-L1:207 [HIGH structure-anaphora] 3 sentences in a row open with 'one'; vary the openings or join the sentences: One points at a line ... next step back to you.
```

A structure finding prints the line and column where its span starts and ends, then the first and last words of the span. The edit hook and the house voice Stop hook print each finding with its matched text and print no texture figure.

## Where they came from

On 2026-11-15 a reply passed `check` with a texture score of 0. Its reader then read it back line by line as a list of faults. That reply is `tests/fixtures/structure/specimen_b.txt`, with names and figures changed and every sentence shape kept. The reply the reader accepted afterwards is `counterpart.txt` beside it. The tests hold each finding the reader named, with its span.

## The rules

| Rule | Tier | What it reports | What to do |
| --- | --- | --- | --- |
| `structure-anaphora/run` | HIGH | Three or more sentences in a row open with the same word | Vary the openings or join the sentences |
| `structure-anaphora/pronoun-run` | MEDIUM | Exactly three sentences in a row open with one of I, we, you, he, she, it, they | Join two of them or vary one opening |
| `structure-anaphora/pair` | LOW | Two sentences in a row open with the same word | Vary one opening |
| `structure-parallel/skeleton` | HIGH | Three sentences within four share one frame, with only the content words changed | Recast one or merge them |
| `structure-parallel/label` | HIGH | Three sentences within four have the form "X is a Y" | Recast one or merge them |
| `structure-triad/sentences` | HIGH | Exactly three parallel sentences in a row | Say it in one sentence or drop to two |
| `structure-triad/items` | LOW | A list of three short phrases | Keep it when the three are the full set |
| `structure-pin/cue` | HIGH | A paragraph opener of 8 words or fewer with a pointing phrase: "here is", "the following", "each of them", "two things" | Start with the content the sentence points at |
| `structure-pin/label` | MEDIUM | A paragraph opener of 5 words or fewer that is a bare label, as in "The cause is mine." | Fold the label into the sentence that carries the content |
| `structure-parataxis/run` | HIGH | Three or more statements in a row of 12 words or fewer, none opening on a linking word | Join the ones that depend on each other |
| `structure-parataxis/stub` | MEDIUM | A statement of 6 words or fewer with no linking word, in a paragraph of four or more sentences where no sentence opens on a linking word | Attach it to its neighbour |
| `structure-pointer/judge` | HIGH | A sentence that only rates the text before it: "That matters.", "That agrees with ..." | State the fact it rests on |
| `structure-pointer/meta` | HIGH | A sentence that points at another sentence and rates it: "His last sentence is the useful part." | Say what that sentence says |
| `structure-pointer/beat` | MEDIUM | A beat of 6 words or fewer that labels the point before it: "That is the silo." | Cut it or make the point in the sentence itself |
| `structure-landing/handoff` | HIGH | The last sentence of a paragraph or a list item hands the next step back: "... is up to you.", "... is yours to write.", "That one is your call." The sentence has 16 words or fewer, or ends within 4 words of the hand-back | Say what you need from the reader, or stop a sentence earlier |
| `structure-landing/handback` | MEDIUM | The same hand-back before the end of a paragraph. A hand-back inside quotation marks is a mention and raises nothing | Say once what you need from the reader |
| `structure-landing/closer` | MEDIUM | A paragraph of four or more sentences ends on one clause of 12 words or fewer | Join it to the sentence it restates, or cut it |

A finding spans the whole run, across wrapped lines when the run wraps. Under `chat` the HIGH findings gate.

### List items

The pin, pointer and landing rules read a list item as a short paragraph: the marker line and the wrapped lines under it. Those wrapped lines belong to the item, so no rule reads one of them as a paragraph of its own. A one-sentence item counts as its own close, so "- Whether to relicense it is your call." is a landing sentence. A bold lead-in such as `**Listing.**` is a label and is skipped. An item that opens "This is the default." is content, so the beat form of the pointer rule needs a sentence before it in the same item.

The anaphora, parallel, triad and parataxis rules stay out of lists. Three items that open on one word are a list doing its job.

### Pronoun runs

Three sentences in a row that open on one personal pronoun report at MEDIUM and do not gate. A pronoun subject is the plain way to keep talking about one thing, and the measurement below shows human prose doing it often while the sampled replies never did. Four or more in a row still gate, and so do three that share one frame ("We read the file. We split the tokens. We print the errors."). "One" is outside the pronoun list, so the run in the specimen gates as before.

### How a frame is compared

Articulate has no dependencies, so there is no part-of-speech tagger. A sentence is reduced to a token-shape signature. A function word stays as itself, a quoted span becomes `Q`, a number becomes `#`, and every other word becomes its ending class: `s`, `ed`, `ing`, `ly` or a blank. Two signatures of five tokens or fewer match when they are equal once every content word is a blank. Two longer signatures match when they open on the same token, differ in length by two tokens at most, and are 0.8 alike by `difflib.SequenceMatcher`.

"The parser reads the file." and "The lexer splits the tokens." both reduce to `the _ _ the _`.

### The local opener measure

The published `repetitive_openers` flag is a whole-document ratio over content-word openers. It needs twelve of them, and it leaves out function words such as "one". Three sentences in a row that open with "One" leave it False. The published detector is byte-pinned, so the flag stays as it is. Under `chat` the cadence block adds `longest_opener_run` and `repeated_openers_in_a_row`, which count consecutive sentences.

## Across turns

`articulate corpus`, and the `corpus_check` tool, read several documents together. Pass one author's turns as the documents and two more findings appear.

- `corpus/sentence-template`: a sentence ending that several turns share once names, numbers and content words are slots and every possessive is one token. "A reply in his name is his to write or approve" and "The question is yours to answer too" share `is POSS to _`.
- `corpus/ritual`: the same two opening words, or the same skeleton, in the first sentence of enough turns, or in the last.

Both report only. A template needs three documents, or two in a series of three or fewer.

## Measured rates

The counts below come from one run of version 0.19.1 on 2026-11-15. Rates are findings per 1,000 paragraph sentences.

| Text | Sentences | HIGH | MEDIUM | Documents with a HIGH finding |
| --- | --- | --- | --- | --- |
| Specimen B, the reply that passed | 24 | 8 | 4 | 1 of 1 |
| The accepted counterpart | 7 | 0 | 0 | 0 of 1 |
| 52 replies by the same session on the same day | 677 | 21 (31.0) | 28 (41.4) | 11 of 52 |
| 18 human texts in `corpus/provenance/human` | 198 | 1 (5.1) | 2 (10.1) | 1 of 18 |
| Running prose from four public-domain books | 3,953 | 30 (7.6) | 38 (9.6) | 4 of 4 |

The 52 replies also hold 519 sentences in list items, which only the pin, pointer and landing rules read. The sentence column leaves them out, so the rate for the replies is findings over paragraph sentences.

The same texts under the rules as first merged, before list items were read and before the pronoun tier. Sentence counts then were 681, 204 and 3,973, because a full stop inside a quoted span used to end the sentence:

| Text | HIGH | MEDIUM | Documents with a HIGH finding |
| --- | --- | --- | --- |
| Specimen B | 8 | 4 | 1 of 1 |
| The accepted counterpart | 0 | 0 | 0 of 1 |
| 52 replies | 17 (25.0) | 19 (27.9) | 8 of 52 |
| 18 human texts | 3 (14.7) | 1 (4.9) | 2 of 18 |
| Four books | 38 (9.6) | 34 (8.6) | 4 of 4 |

On the replies the gain is the hand-back: `structure-landing/handoff` now reports 7 findings where it reported 2, and `structure-landing/handback` reports 4 more before the end of a paragraph. Nine of the eleven replies that carry a hand-back line now raise a finding on it. On human prose the drop is the pronoun tier: 5 three-sentence pronoun runs moved from HIGH to MEDIUM, and the 5 triads counted on the same sentences went with them. The human corpus and the books hold 13 opener runs of three or more, 7 of them on a personal pronoun. The 52 replies and Specimen B hold 2, both on "One".

The four books are Darwin's *Origin of Species*, Faraday's *Chemical History of a Candle*, Russell's *Problems of Philosophy* and Strunk's *Elements of Style*, from Project Gutenberg, about 40,000 words of each with tables, contents lists and example pairs removed.

HIGH findings in the books, by rule: anaphora 8, parataxis 8, triad 7, parallel 5, pin 1, pointer 1, landing 0. Most of the anaphora and triad findings are the device used on purpose, as in Darwin's "He does not allow ... He does not rigidly destroy ... He often begins ...". A writer who wants the device should use a profile that leaves these rules out.

Three findings on human prose that a reader would call wrong:

- `structure-pin/cue` on Faraday's "Here is another application of the same principle." He is pointing at apparatus on the bench.
- `structure-parataxis/run` on Jerome's "We made George work, now we had got him. He did not want to work, of course; that goes without saying. He had had a hard time in the City, so he explained." The clauses link inside each sentence.
- `structure-parataxis/run` on Faraday's "You will see them burning too, but without the production of flame. They will each burn separately. [The Lecturer then ignited the mixture.]" The third sentence is a stage direction in brackets, and the rule counts it as a statement.

On the 52 replies, the series check reported 12 templates. Seven are stock phrasing a reader would notice, such as `_ is POSS` ("That click is yours.") in four replies and `on POSS own _` ("waiting on its own CI") in six. Five are ordinary phrasing, such as `before the _ and`.

These rules were tuned on one session's replies and one reader's verdict. The rates will differ on other writers.

## The readback set

`tests/fixtures/structure/readback/` holds texts a person read and judged. Each case gives the text, the spans the reader objected to, and the rule the reader named for each span. `tests/test_structure_readback.py` reports each rule's recall against those marks, and a text the reader accepted must raise no gating finding.

```bash
python tests/test_structure_readback.py
```

| Rule the reader named | Marks | Reported | Gating |
| --- | --- | --- | --- |
| Anaphora | 1 | 1 | 1 |
| Hand-back formula | 1 | 1 | 0 |
| Landing sentences | 2 | 2 | 1 |
| Paragraph pinning | 3 | 3 | 2 |
| Parallel sentence structures | 1 | 1 | 1 |
| Parataxis | 2 | 2 | 0 |
| Register | 1 | 0 | 0 |
| Rule of three | 1 | 1 | 1 |
| Setup and payoff | 2 | 2 | 2 |
| Summary beats | 1 | 1 | 1 |
| All | 15 | 14 | 9 |

The set starts with two texts one reader objected to and one that reader accepted. The README in that folder says how to add a case, so the next readback becomes a test.

## Limits

- The rules skip headings, block quotes, table rows and code. In a list item only the pin, pointer and landing rules run.
- Each phrase list is closed, so a paraphrase gets past it. Two hand-back lines in the 52 replies still raise nothing: one of the form "Two choices are also yours, because ..." and one that opens a list item with "Still yours from earlier sessions: ...".
- A hand-back is read one reply at a time. The fault a reader named was the same line in four replies; `corpus/sentence-template` reports that across turns, and a single check cannot.
- Register has no rule. The reader of Specimen B also objected to "a performance of contrition written in the same clipped style", and the readback set counts that mark as a miss.
- Parataxis is read from sentence length and opening words. A paragraph of long unlinked sentences passes.
- Setup and payoff is caught only in the announcer form ("Here is X said plainly.").
- English only.

## Coverage of one house rule set

One author's standing prose rules name 23 patterns. The table says which had a detector before these rules, and which have one now. "Partial" means a closed phrase list or a density measure that catches some forms.

| Pattern | Before | Now |
| --- | --- | --- |
| Antithesis | Detector | Detector |
| Corrective negation | Detector | Detector |
| Paragraph pinning | None | Detector: `structure-pin` |
| Parataxis | None | Detector: `structure-parataxis` |
| Summary beats | Partial: a curated "That is the ..." list | Detector: `structure-pointer` |
| Rhetorical crutches | Partial: reveal, meta and throat-clearing lists | Partial |
| Negative parallelisms | Detector | Detector |
| Negative anaphoras | None | Detector: `structure-anaphora`, any polarity |
| Contrasting pairs | Detector | Detector |
| Rule of three | Partial: single-word triads, report only | Detector: `structure-triad` |
| Em dashes | Detector | Detector |
| Throat-clearing openers | Detector | Detector |
| Landing sentences | Partial: closing phrases such as "in conclusion" | Detector: `structure-landing` |
| Setup and payoff | Partial: reveal phrases | Partial: plus the announcer form |
| Parallel sentence structures in a paragraph | None | Detector: `structure-parallel` |
| Vary sentence length | Partial: a uniform-cadence flag | Partial |
| Stacked noun phrases | None | None |
| Filler intensifiers | Detector | Detector |
| Corporate-register verbs | Partial: "reflect" is flagged only as a trailing participle | Partial |
| Nominalization | Partial: four or more in one line, report only | Partial |
| Hedging qualifiers | Partial: stacked hedges and clusters of three | Partial |
| Write for the spoken voice | None | None |
| Performed enthusiasm | Partial: email and flattery phrases | Partial |

Before: 7 with a detector, 10 partial, 6 with none. Now: 14 with a detector, 7 partial, 2 with none.
