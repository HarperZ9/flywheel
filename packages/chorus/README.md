<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/chorus/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/chorus/main/docs/art/hero-light.svg" alt="chorus: Turn a comment corpus into a ranked, re-checkable discourse digest. Bundles of fine lines carry the work through 5 stations, normalize, score, cluster, contested and receipt, along a sweeping path into a bright core." width="100%">
</picture>

# Chorus

Chorus reads a comment section and tells you what the crowd says, how strongly,
and where it disagrees, with a receipt anyone can re-run.

Give it a set of comments and it returns a digest: the themes people raise,
ranked by engagement and strength of feeling, the loudest voice that disagrees
with each theme's majority, and the topics the crowd is split on. The same input
always gives the same digest, and a stranger can check that the digest follows
from the comments. It runs on your machine with Python alone, with no model, no
service key and no network call.

It is for journalists, researchers, moderators and product teams who read large
comment threads and need a summary they can show their working for.

## Install and first run

Python 3.10 or newer. Chorus has no third-party dependencies.

```bash
python -m pip install chorus-discourse
curl -LO https://raw.githubusercontent.com/HarperZ9/chorus/main/examples/discourse-sample.json
chorus run discourse-sample.json --verify
```

The sample holds twelve comments on a phone review. The digest is JSON; trimmed,
it reads:

```text
"themes":    "display / screen / bright", "drains / battery", "phone / life / battery",
             "camera / photos / average", "awful / dead / disappointing"
"contested": "life" (0.5531, 3 mentions), "battery" (0.5386, 5 mentions)
"verified":  true
```

To see the receipt refuse an edited digest, run this from the same folder:

```python
import dataclasses, json
from chorus.item import normalize
from chorus.sentiment import score
from chorus.synthesize import synthesize
from chorus.receipt import verify

scored = score(normalize(json.load(open("discourse-sample.json"))))
digest = synthesize(scored)
print(verify(digest, scored))   # True

theme = dataclasses.replace(digest.themes[0], weighted_score=999.0)
edited = dataclasses.replace(digest, themes=(theme,) + tuple(digest.themes[1:]))
print(verify(edited, scored))   # False
```

Your own input is a JSON list of rows such as
`{"kind": "comment", "id": "c01", "ref": "video-1", "text": "...", "meta": {"like_count": 340}}`,
or a corpus folder written by [Gather](https://github.com/HarperZ9/gather).
Rows of kind `comment`, `post`, `reply` and `feed-entry` count as discourse.
`like_count` or `score` in `meta` sets engagement; a row without either is
recorded as having no signal, never as zero.

## How it compares

- **VADER** scores the sentiment of one text from a lexicon and rules. Chorus
  uses a smaller lexicon of the same kind, then groups comments into themes,
  weights them by engagement and reports split topics across the whole thread.
- **BERTopic** and other embedding topic models find themes by meaning, so they
  group paraphrases that Chorus misses. They need a model download, and their
  output is not re-derivable byte for byte. Chorus clusters by shared words and
  writes a receipt that reproduces every number.
- **Polis** clusters participants by how they vote on each other's statements in
  a live deliberation it hosts. Chorus works after the fact, on comments already
  posted somewhere else.
- **Asking a language model to summarise the thread** gives fluent prose that
  cannot be checked against the comments. Chorus can pass its least certain
  comments to a model you name with `--model`, and it keeps that opinion outside
  the receipt.

## Limits

- Sentiment comes from a 30-word English lexicon. It reads text literally, so it
  misses sarcasm, irony and other languages.
- Clustering is lexical. Two comments that make one point in different words can
  land in different themes.
- A verified receipt shows the digest follows from the input. It does not show
  the input is complete, representative or free of coordinated accounts.
- The test suite is small, and Chorus has not yet been studied on real comment
  sections. Treat its themes as a starting point for your own reading.

![Eight stages of turning a corpus of comments into a discourse digest: normalize, engagement, score, weight, cluster, themes, contested, and receipt. Gathered rows become discourse items, and rows that are not discourse are skipped. Engagement is read from the source when it is present; when a source genuinely has no signal, engagement is zero and the absence is recorded, so a missing vote is never counted as a real zero-weight one. Sentiment comes from a thirty word lexicon with negation, intensifier, capitalization and punctuation rules, and the same text always scores the same. Weight is the natural log of one plus engagement, multiplied by one plus half the sentiment intensity, so a loud comment nobody engaged with stays small. Clustering is a hashed TF-IDF cosine against the nearest leader across five hundred and twelve dimensions, seeded most-engaged first. Each theme carries its size, its sentiment split, its controversy, and the single highest-weight voice that disagrees with the majority. Contested aspects are measured separately across every comment that mentions a term, so a topic the corpus is split on survives the clustering that would file praise and complaint about it under different themes. The receipt hashes the inputs, the parameters and the digest body. Three outcomes: re-derived, rejected, and advisory only.](docs/art/synthesis-lane.svg)

## See it work, step by step

The [animated explainer](https://harperz9.github.io/repo-explainers/chorus.html)
walks through the bundled twelve-comment sample: lexicon scores, engagement
weights, five themes, the contested battery topic, and a digest receipt that
rejects a doctored weight even with its hash recomputed. Every value on it is
output from this repository. Its source is
[docs/explainer/index.html](https://github.com/HarperZ9/chorus/blob/main/docs/explainer/index.html).

## What you get

- **Themes, ranked.** Comments cluster into themes by what they say; each theme
  carries a corpus-salience label, label-support metadata, its size, an
  engagement-and-sentiment weight, a sentiment split, a *controversy* score (how
  divided and how strongly felt), and the single highest-weight voice that
  disagrees with the majority. The digest marks singleton and weak-support labels,
  so a narrow label never passes for a broad crowd theme. Theme item
  IDs stay in the output so callers can resolve labels back to the source links
  and provenance in their corpus.
- **The contested topics, named.** A separate lens reports the aspects the corpus
  is split on, measured across *every* comment that mentions a topic. It
  is immune to the lexical clustering that would otherwise file "the battery is
  amazing" and "the battery is terrible" under different themes and hide the fight.
  One-sided praise and neutral chatter are excluded; only real two-sided
  disagreement is surfaced.
- **A receipt for every digest.** `--verify` re-derives the whole digest from the inputs
  and confirms it. A tampered digest fails even if its own hash was recomputed to
  match. Sentiment is a *weight*, never a verdict.
- **Honest nulls.** A missing engagement signal is recorded as absent, never
  counted as a zero. A too-thin corpus says so. The lexicon's limits (English-only,
  literal, no sarcasm) are stated in the digest itself.
- **A daemon.** Point it at a watchlist and it re-synthesizes only when a corpus
  changes, storing each receipted digest by its own hash.
- **A source-change review gate.** Compare a current gather corpus against a
  reference corpus before reusing a prior synthesis or release note. The result
  reports added, removed, changed, unchanged, digest verification, a local digest
  outline, and typed source failure states. The optional public projection is
  safe by default as hashes and counts. Human-readable public ids, source names,
  refs, and URLs require a `--public-policy` sidecar you write; raw
  source row metadata cannot authorize public output. The projection omits raw
  source text, author names, local paths, private session content, and bulk
  comments. Source URLs appear there only through that public-policy sidecar.
- **An MCP surface.** Drive it from any MCP host: `chorus.run`, `chorus.corpora`,
  `chorus.digests`, `chorus.decision`, `chorus.status`, `chorus.doctor`.

## Release notes

[CHANGELOG.md](https://github.com/HarperZ9/chorus/blob/main/CHANGELOG.md) lists
every release. Version 0.3.1 reads Gather feed entries as discourse. Version
0.3.0 added `chorus decision`, a review gate that reports whether the sources
behind an earlier digest changed; it does not judge whether a source claim is
true. Version 0.2.0 added theme-label support metadata to receipts, and
`chorus-lens/2` receipts from earlier versions still verify.

## Run it

```bash
python -m pip install chorus-discourse   # or, from a checkout: python -m pip install -e .

chorus run examples/discourse-sample.json --verify   # try it on the bundled sample
chorus run <corpus> --verify        # a corpus -> a verified discourse digest
chorus decision <current> --reference <reference> --task "Check whether sources changed"
chorus decision <current> --reference <reference> --public --public-policy public-policy.json
chorus corpora <root>               # discover gather corpora as discourse sources
chorus watch add <corpus>           # add a corpus to the daemon watchlist
chorus daemon --interval 300        # poll the watchlist, synthesize on change
chorus digests <store>              # what the daemon has synthesized
chorus mcp                          # the MCP stdio server
```

`<corpus>` is a gather corpus directory (a folder holding `catalog.jsonl`) or a
JSON list of rows. Add `--model "<command>"` to `run` to overlay a model's read on
the comments the lexicon is least sure about; the overlay is provenance-tagged and
never enters the re-checkable core.

No service key or provider account is needed for the deterministic path. The
bundled sample is the quickest local check:

```bash
chorus run examples/discourse-sample.json --verify
python -m pytest
```

If `chorus` is not on `PATH`, reinstall with `python -m pip install chorus-discourse`
and open a new shell. `chorus.status` and
`chorus.doctor` are MCP tools exposed through `chorus mcp`; they are not separate
CLI subcommands. Public source-change projections need a `--public-policy`
sidecar you write before source names, ids, refs, or URLs appear.

![Eight stages of verifying a discourse digest: receipt, version, vocabulary, inputs, rescore, recluster, rehash, and verdict. The receipt supplies the parameters and hashes the original run recorded. The method version selects the verifier for that pipeline; unsupported versions fail instead of being guessed. The lexicon is hashed into the receipt, so editing the word list invalidates every digest that was built with the old one. The corpus hash is checked before any work is done. Then the stored sentiment is thrown away and every comment is re-scored from its own text, which is why fabricated sentiment cannot verify. Clustering and weighting re-run from the parameters the receipt recorded, not from the live defaults, so raising a default cannot silently break an already-versioned receipt. The digest body is rebuilt from that re-derivation and hashed. The verdict is one boolean with nothing taken on trust: a digest whose themes, weights or sentiment distribution do not follow from the inputs fails, even when its own stored hash was recomputed to match its tampered body. Three outcomes: verified, tampered, and no receipt.](docs/art/verify-lane.svg)

## The receipt

The digest's `receipt` binds the inputs, the method, and the result. `verify`
first checks that the submitted digest body still matches its own receipt, then
re-runs the deterministic pipeline (score, cluster, weight) from the same corpus
through the method-version verifier recorded in the receipt. Current runs write
`chorus-lens/3`; historical `chorus-lens/2` receipts remain checkable through
their legacy label body. Unsupported method versions fail closed. Any model
overlay is listed separately with its own provenance and is excluded from that
check: the parts a stranger can re-derive and the parts that are model opinion
are kept distinct, on the record.

![Twelve rows covering every number a digest reports and where it comes from. The lexicon is thirty words, fifteen positive and fifteen negative, each carrying a valence between minus three and plus three, and the whole list is hashed into every receipt. Ten intensifiers are looked for up to three tokens back, widening or narrowing a valence. Nine negators flip a valence and keep about three quarters of its size, so a negation weakens a claim rather than erasing it. The compound score runs from minus one to one, the summed valence divided by the root of itself squared plus fifteen, so no single loud comment runs away with a theme. Two emphases apply: an all-caps valence word of more than one letter counts a quarter more, and up to four exclamation marks add five percent each. Weight is the log of one plus engagement, times one plus half the sentiment intensity. Clustering runs a hashed TF-IDF cosine over five hundred and twelve dimensions against the nearest leader, joining above eighteen hundredths, seeded most-engaged first. Controversy is the population standard deviation of a theme's sentiment, zero at consensus and near one at a hard split. Twelve contested aspects are surfaced, each needing three mentioning voices and real disagreement on both sides. The receipt carries seven fields. The accented row is the model overlay, which is advisory opinion on the items the lexicon is least sure of and is deliberately kept outside the digest hash. The last row is engagement coverage, which reports how many items actually carried a signal, because an absent signal is recorded absent rather than counted as a zero.](docs/art/method-table.svg)

## Design

The design and its two exposed defects-caught-in-review live in
[docs/superpowers/specs](https://github.com/HarperZ9/chorus/tree/main/docs/superpowers/specs). Sentiment is coarse by
construction and the digest says so; clustering is lexical, not semantic. chorus
tells you what it did and hands you the means to check it.

## License

Chorus is free software under the GNU Affero General Public License, version 3
only (AGPL-3.0-only). See [LICENSE](https://github.com/HarperZ9/chorus/blob/main/LICENSE) and [NOTICE](https://github.com/HarperZ9/chorus/blob/main/NOTICE).

Anyone may use, study, change and share it. If you distribute a changed copy, or
run one as a service that people use over a network, you must offer them its
source under the same licence.

Releases up to 0.3.1 were published under FSL-1.1-MIT. They keep those terms,
and each converts to MIT two years after its release.

---

Built by **[Zain Dana Harper](https://harperz9.github.io)** in Seattle: evidence-first tools that leave a re-checkable artifact behind. Other tools by the same author are listed at [harperz9.github.io](https://harperz9.github.io).
