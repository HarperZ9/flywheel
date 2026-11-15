# A voice built from intent

You say what a piece of writing is for, who reads it and how you stand.
Articulate turns that into a spec: the moves the draft should make and the
template devices it should leave out. Then it scores a draft against the spec
and shows each miss by line, with a fix.

```bash
articulate voice intend --goal "persuade on X" --audience "busy readers" \
  --stance "contrarian, asks what if, tries the other side" --out post.json
articulate voice check draft.md --intent post.json
```

![voice check on a flat draft, then on the rewrite](art/voice-intent-demo.gif)

## What it catches

The line checker reads one line at a time. A post written as one short
sentence per paragraph slips past it, because each line on its own is plain.
`voice check` reads the whole post and names the shapes that come from a
template:

| Device | What it looks like |
|---|---|
| one-line paragraphs | most paragraphs hold a single sentence |
| anaphora run | three sentences in a row open the same way ("Were called...") |
| epistrophe run | three sentences in a row end the same way ("...going anywhere.") |
| fragment run | three fragments of four words or fewer in a row |
| tricolon | three short items for rhythm ("managed, shaped, and constrained") |
| split antithesis | a negated sentence answered by its mirror ("That's not faith. That's hypocrisy.") |
| aphorism line | a short maxim on its own line ("The protection is the rent.") |
| closing maxim | the post ends on a maxim ("The pattern is the policy.") |
| numbered escalation | "First:", "Second:", "Third:" as rhetoric |
| colon drumroll | a line ending in a colon that sets up a short reveal |
| reveal setup | stock reveal phrases ("This is not a secret.", "Let's just say") |
| hedge | perhaps, arguably, might |

It also runs the line checker, so antithesis, em-dashes, filler words and
corporate verbs count too.

People write every one of these. A finding names a shape. It says nothing
about who wrote the text.

## What it asks for

The words in `--goal` and `--stance` choose the moves:

| Move | Chosen by | What the check looks for |
|---|---|---|
| anchor | persuade, post, explain, market | a date, a number, a quote with a source |
| turn | persuade, contrarian | "but", "yet", "still", "even so" |
| reader question | persuade, post | a sentence ending in "?" |
| counter view | contrarian, skeptic | the opposing view, named ("One reply called it...") |
| other side | shoes, other side, steelman | "from their side", "in his shoes", "from the board's side" |
| what if | what if, hypothetical | "what if", "suppose", "imagine", "put yourself" |
| stance | polemic, direct, first person | "I think", "I'd argue", "I doubt" |
| tool | market, launch, readme | a command in backticks, or a tool you name with `--tool` |

## Samples

`--sample FILE` (repeatable) adds reference texts: posts whose effect you
want. The spec keeps a hash and a word count for each, plus counts of the
devices they use. It keeps no sentence. If the samples lean on template
devices, the plan says so, and the spec still limits those devices. A spec
built from a sample that reads like model output asks for better writing
than the sample.

## The zain spec

`--intent zain` is a built-in spec. It carries the author's prose rules (no
antithesis, contrasting pairs, rule of three, setup and payoff, landing
sentences, em-dashes, filler or hedges; varied sentence length) and his stance
for posts: contrarian, polemical, asks what if, tries the other person's shoes
before judging, first person. Start your own from it:

```bash
articulate voice intend --base zain --name mine --tool articulate --out mine.json
articulate voice intend --list
```

## The author-voice spec

`--intent author-voice` is the author's own register: defensive, antagonistic
and contrarian, an everyman and an observer, wonder beside a jaded eye. From
the author's own description of their process it adds imagery first, the next
move played forward and runs of ideas kept as runs, and from the author's
direction it adds analogy, symbolic messaging and confrontation that holds the
reader to their own contradiction. It wants imagery, the observer's "I saw",
forward motion, an analogy that carries structure, a counter-view, a stance, a
turn and a reader question. It limits hedges and stock setups and sets no limit on
anaphora, tricolon, antithesis or a closing line, because in this voice a
literary device is a tool: `articulate devices --function` reads each one for
the image, anchor or stance it carries. Pair it with `--profile author-voice`,
which keeps the register through edits.

## The score

The score is the share of the spec's checks the draft meets, from 0 to 100.
`--min-score 90` makes the command exit 1 below 90, for a pre-commit hook or
CI. `--json` prints every check with its value, bound, lines and examples.

A score measures fit to a spec. It does not check whether the claims are true.
A draft written to the checker can score 100 and still be wrong, so read the
sources before you post.

## Commands

```
articulate voice intend [--goal G] [--audience A] [--stance S] [--sample FILE]...
                        [--base NAME] [--tool NAME]... [--name N] [--out FILE] [--json] [--list]
articulate voice check DRAFT... --intent SPEC|NAME [--min-score N] [--json]
```

Both commands read only the files you name and write only `--out`. Neither
edits a draft.
