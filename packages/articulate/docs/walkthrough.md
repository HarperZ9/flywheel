# Walkthrough

This is a full pass over one document, from a first screening to a rewrite to a
committed audit record a reviewer can replay. Checks stay local; editor privacy
follows the selected backend. The
example file is a short blog draft, `post.md`, that was written with an assistant
and lightly edited by hand.

## 1. Screen the document

```bash
articulate check post.md --verbose
```

```
[articulate] post.md [readme]: 3 high, 4 medium (blocked)  texture 63/100
  L2 [HIGH corporate-verb] leverage / underscore: We leverage cutting-edge tools.
  L2 [MEDIUM marketing] marketing superlative: We leverage cutting-edge tools.
  L4 [HIGH antithesis] not X but Y: This is not a feature, but a philosophy.
  L6 [MEDIUM stock-transition] stock connective: Moreover, the results speak.
  L8 [HIGH em-dash] em-dash: a small change — and a large payoff.
  L2 [LOW rule-of-three] possible triad (X, Y, and Z): fast, cheap, and reliable
```

The verdict is `blocked` because HIGH findings are present. The texture score of
63 says the whole document is dense with these devices, beyond the specific hits.
Each line points at the exact place to fix.

## 2. Find the dense paragraph

A whole-file score hides a single device-heavy paragraph inside otherwise clean
prose. `--spans` scores each paragraph on its own:

```bash
articulate check post.md --spans
```

```
[articulate] post.md [readme]: 4 span(s), 1 flagged
  [ ok ] span 0 L1-1: clean, texture 4/100 (0H/0M): A note on the redesign.
  [FLAG] span 1 L2-8: flagged, texture 88/100 (3H/4M): We leverage cutting-edge
  [ ok ] span 2 L10-12: clean, texture 6/100 (0H/0M): I wrote the rest by hand.
  [ ?? ] span 3 L14-14: unverifiable, texture 0/100 (0H/0M): Thanks for reading.
```

The dense paragraph is span 1 on lines 2 to 8. The other paragraphs read clean, and the short closing line is `unverifiable` because it falls under
the word floor, so the tool abstains and does not guess.

## 3. Read the judgment-level quality

The detector catches mechanical tells. The editor layer reads the failures a
regex misses: a fluent paragraph empty of facts a reader could restate, hedging
that avoids a position, a weak verb carrying the meaning. Use the calling
host's model through `plan` and `submit`, or select a configured model backend.
Without a model, the judge returns local findings and rule reasons.

```bash
python -m articulate.editor --judge post.md
```

The judge quotes each weak passage, names the failure, and says in one line what
a skilled writer would do. It reports, and the rewriting is `fix` and
`polish`.

## 4. Rewrite to the standard

`--fix` offers a rewrite and re-runs the detector. It retains original paragraphs
when protected spans change, including numbers, links, citations and code.
Remaining findings are reported when the result still needs work:

```bash
python -m articulate.editor --fix post.md --out post.fixed.md
```

`--polish` runs a bounded loop that aims for five assessed qualities to clear a bar:
concreteness, commitment, economy, rhythm, and a restatable fact in each
paragraph. It accepts a pass when the detector gate stays clean and every
quality score holds or rises. Missing scores leave quality unassessed. Read the
result against the original to confirm the meaning held.

The rewrite is a suggestion. Read it against the original before you ship it. The
tool optimizes writing quality, and it never tunes prose toward a lower detector
score. See [Boundaries](boundaries.md).

## 5. Match the register with a mode

A mode crosses a domain register with an articulation need. A memo that argues
wants a different shape from an API reference that explains. List them:

```bash
articulate modes
```

Run the check under one:

```bash
articulate check post.md --mode marketing/persuade
```

A marketing mode blocks the register and marketing tells that a general profile
reports without blocking, and it keeps the terms of art the genre needs. For
fiction, memoir, screenplay, and poetry there is a genre axis that reads by
convention: quoted dialogue is exempt, craft devices report without blocking, and
a report-only lexicon flags generation artifacts. For a proof or a technical
paper, `academic/prove` and `science-writing/explain` protect math and keep rigor
vocabulary clean. See [Features](features.md#writing-modes).

## 6. Record a re-derivable receipt

Once the prose is where you want it, record a receipt so a reviewer can confirm
the screening later:

```bash
articulate receipt post.md --profile readme > post.receipt.json
articulate verify post.receipt.json post.md
```

```
[articulate] Match: re-derived 0 findings, gate ok, texture 4/100
```

The receipt pins the exact text hash and a fingerprint of the whole ruleset. A
change to a rule moves the fingerprint, and an old receipt then reads
`Unverifiable`, so it never disagrees silently.

## 7. Keep an audit record without the source

A team that must retain a record, without keeping the sensitive text, uses a
content-free receipt. It drops the matched substring and the exact offsets, and
keeps which rule fired and on which line:

```bash
articulate receipt post.md --redact drop --reviewer alice > receipts/post.json
```

Query a directory of committed receipts locally, and re-verify that each still
holds against its source:

```bash
articulate audit receipts/ --reverify --gate
```

```
[audit] 12 receipt(s); gate {'ok': 9, 'blocked': 3}; verdict {'clean': 9, 'flagged': 3}
[audit] stale-ruleset 0; active in last 30d 12
[audit] reverify: {'Match': 11, 'source-changed': 1}
```

The `source-changed` count is the one file edited after its receipt was recorded.
With `--gate`, that fails the exit code, so continuous integration flags a
document that changed since its last screening. What a content-free record
still reveals, and how `hash` mode differs, is in [Boundaries](boundaries.md).

## 8. Wire it into continuous integration

The detector emits SARIF, which GitHub code scanning, Azure DevOps, and reviewdog
render as inline annotations:

```bash
articulate check "**/*.md" --sarif > articulate.sarif
```

The repository ships a GitHub Action and a pre-commit hook. The Action can also
re-verify committed receipts and fail the build on drift. See
[Features](features.md#surfaces) and the `action.yml` in the repository root.

Checks and receipts run locally and can be replayed. Model edits follow the
selected backend; their assessments may vary between calls.
