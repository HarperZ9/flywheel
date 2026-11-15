# Series review and your own voice

Two features for authors. Series review reads several of your documents
together and shows the patterns a reader notices across them. Your own voice is
a profile you build from your own writing, on your own computer, so you can
compare a draft with how you write and, when you ask, shape your draft toward
it.

Your experiences stay yours to write. Where your perspective would help,
Articulate asks a question and leaves the answer to you.

## Series review

```bash
articulate corpus essays/*.md
articulate titles essays/*.md
articulate interview essays/draft.md --out essays/draft.marked.md
articulate restructure essays/draft.md --out essays/draft.restructured.md
```

`corpus` names patterns that show across a set:

- one title formula used again and again
- phrases shared by three or more pieces
- the same paragraph scaffold (claim, source, confidence, limit) in most
  paragraphs
- sections of near-equal length, and sentence lengths that barely vary
- long stretches where the author is absent
- runs of paragraphs missing a number, date, name or place

Each finding has its location, what it costs a reader, and a direction for you
to take. The findings are advisory, so the rewriting stays with you and a build
keeps passing. `--keep FILE` lists phrases
you repeat on purpose. `--receipt OUT` writes an `articulate/corpus-receipt/v2`
receipt that `articulate verify` replays.

`titles` groups titles by skeleton ("The Map Is Not the Road" and "The Vote Is
Not the Law" share `the X is not the X`) and asks, for each repeated title, how
you would describe the piece to a friend. With `--answers FILE` it offers up to
three suggestions built from the words of your answer.

`interview` asks questions only you can answer, each at its lines: why the
piece matters to you, what you saw yourself, whether you would stake your name
on a claim. It never answers them. `--out` writes a copy with an inert marker
after each question; `--collect FILE` gathers your answers into a file that an
edit plan can bind as your own words.

`restructure` proposes moving per-paragraph source, confidence and limit lines
into one "Sources and method" section, with an anchor left in place. It refuses
the proposal unless every sentence, citation, URL, number, quote and disclosure
survives byte for byte.

## Your own voice

```bash
articulate voice learn my-essays/*.md --name mine --mine
articulate voice show mine
articulate voice compare draft.md --name mine
articulate voice apply draft.md --name mine --authored-by-me --out plan.json
articulate voice delete --all
```

`learn` builds a profile from the files you name, once `--mine` says they are
your own writing. The profile holds measured aggregates: sentence and paragraph
length ranges, how your sentences open, how often you concede, give a reason,
ask a question or write in the first person, and function-word rates. It stores
numbers, and the sentences of your samples stay in your files. Names of people
and places are dropped before the vocabulary field is built (`--no-vocabulary`
leaves that field out). Below about 5,000 words of samples the profile labels
itself indicative.

`show` prints every stored field as a plain sentence and the file's path.
`compare` places a draft against your own range, feature by feature, and points
at long stretches where the author is absent. Its output is the per-feature
comparison; the draft stays as you wrote it.

`apply` plans an edit of your own draft toward your measured habits. It runs
only with `--authored-by-me`, and the plan binds the profile's name and hash.
The calling model writes the rewrite; `articulate voice submit` checks it. The
meaning guard keeps every protected span, and a rewrite that adds a first-person
sentence with no source in your draft or your supplied words is refused for that
paragraph. Before and after counts of features outside your range are reported
and never decide what is accepted.

### Where it lives, and who it belongs to

The store is one folder: `%LOCALAPPDATA%\articulate\voice` on Windows,
`~/.local/share/articulate/voice` elsewhere, or `ARTICULATE_VOICE_DIR`. The
first write adds a `.gitignore` holding `*`. `identity.json` holds a random
owner id made on your computer, and every profile records the owner it was
learned under. `compare` and `apply` refuse a profile from another owner.

`voice export NAME --out FILE` and `voice import FILE` move a profile to your
other computers. On a computer that has yet to make an identity,
`--adopt-identity` takes the export's owner. Each store has one owner.

The binding is a consent and provenance record. A local user who edits the JSON
can change it, so use file permissions for access control.

### What leaves your computer

Learning, comparing, exporting and deleting run on your computer. Learning,
exporting, importing and deleting are command-line steps; over MCP a model can
compare a draft and plan an apply. In `apply`, the profile's plain-sentence description enters the
conversation with the calling model, because that model writes the rewrite. The
profile holds numbers and that description, so your sample text stays in your
files.

## The house voice is separate

The [house voice](house-voice.md) is the model's own voice, applied to the
model's replies. Your voice store feeds `voice apply`, which shapes text you say
is yours when you run it.

## Limits

- Move labels come from cue words and mislabel some sentences; reports show
  excerpts so you can judge.
- Thresholds are starting values from a small set of essays.
- The profile measures surface habits. A draft inside your range can still
  sound unlike you, and one outside it can sound like you, so your ear decides.
- These features measure style against your own writing; they report on habits,
  and leave authorship and humanness unscored.
