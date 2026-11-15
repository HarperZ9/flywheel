# Campaign signals

`articulate campaign` reads a batch of short social texts and reports three
signals that paid launch campaigns and repost farms tend to leave in the text:

1. **Promotional templates** in posts: hype openers, a shouted claim beside a
   spec number, stock launch-copy formulas, and endorsement wording with no
   disclosure marker.
2. **Stock-persona bios**: the slot grammar of age, role, hobby, token and a pet
   or tagline line, filled from stock phrasing.
3. **Clusters** of near-duplicate or templated posts, each shown as a shared
   skeleton with `{}` where the members differ, plus groups of bios that share
   one frame once their fillers are masked.

Each finding names the pattern, gives its character offsets, and says what the
pattern costs a reader. Nothing is edited.

## What a hit means

A hit describes the form of a text. It does not show that an account is
automated, that anyone was paid, or who wrote a post. Many real people quote
one announcement in similar words, and many real people write short,
template-shaped bios. Founders write launch posts and fans write with
excitement. Treat a hit as a reason to look closer. Never use one as a verdict
about a person or as grounds to report an account on its own.

The detectors look only at the text in front of them. Account age, posting
times, follower graphs and engagement ratios are stronger campaign evidence and
are out of scope here; a tool such as Radar combines them.

## Run it

```text
$ articulate campaign quotes.json --platform x
[articulate] campaign [x]: 6 items, 3 promo templates, 2 stock-persona bios, 1 clusters (3 posts), 1 bio frame groups
  q1:1  hype opener: address word: 'sir...'
      cost: the opener performs excitement before it gives the reader any fact
  ...
  cluster template x3 (J 0.568..0.615): q1, q2, q3
      skeleton: {} they just dropped a coding model that runs locally on {} at {} tokens/sec
```

`--json` prints the full report. `-` reads the list from standard input.
`--threshold` sets the shingle similarity that joins two posts (default 0.5)
and `--frame-threshold` sets it for bio frames (default 0.6). The exit code is
0 on success and 2 when the input cannot be read.

From Python:

```python
from articulate import campaign
report = campaign.analyze(items, platform="x")
```

## Input and output

The schema of record is [`campaign-schema.json`](campaign-schema.json). The
report format string is `articulate-campaign-report/1`; a change that breaks a
consumer bumps the number.

Input is a JSON list. Each entry is a string (read as a post) or an object:

- `text`: string, required.
- `id`: string or integer; defaults to the list index.
- `kind`: `post` or `bio`; defaults to `post`.
- `platform`: `x`, `reddit`, `tiktok`, `linkedin` or `generic`; defaults to the
  run's `--platform`.

The report has these top-level fields:

- `format`: `articulate-campaign-report/1`.
- `platform`, `parameters`: the run settings.
- `items`: one entry per input with `id`, `kind`, `platform`, `template`,
  `score` and `findings`. Bios add `slots`, `slot_types` and `frame`.
- `clusters`: post clusters with `ids`, `size`, `kind` (`near_duplicate` or
  `template`), `similarity_min`, `similarity_max`, `skeleton`,
  `shared_tokens` and `fillers`.
- `persona_groups`: bio groups with the same fields, built from masked frames.
- `summary`: counts.
- `scope`: what the report covers and its limit, in one paragraph.

A finding has the same span fields as `articulate check` findings (`line`,
`col`, `start`, `end`, `category`, `label`, `match`, `rule_id`, `tier`) plus
`weight` and `cost`.

## The patterns

Each pattern, with what it costs the reader:

- `hype opener` (address word, alarm, drop announcement): excitement arrives
  before any fact.
- `claim and spec number`: an emphasised claim leans on a figure with no
  stated conditions.
- `fundamental bottleneck`: a sweeping premise set up so the product can
  resolve it.
- `the infra that solves it`: a promise of category ownership with nothing to
  check.
- `we spent the last N years`: effort stands in for results.
- `the best solution`, `best-in-class`: a ranking with no rival or benchmark
  named.
- `introducing X, its first Y` and `X launches Y, its first Z`: press-release
  voice in a personal post.
- `endorsement without disclosure`: the reader cannot weigh a recommendation
  without the poster's stake.
- `stock-persona bio`: the bio says nothing particular about the person.

A post is a template at a summed weight of 3. A bio is a stock persona when it
fills three slot types (four on LinkedIn, where long bios fill more slots by
chance).

## Platforms and demographics

Bio length and conventions differ by platform, so `platform` sets the slot
floor, and the corpus keeps X, Reddit, TikTok and LinkedIn items apart and
reports them separately.

Published work has found that detectors of machine-written text flag
non-native English writing far more often than native writing (Liang et al.,
2023, "GPT detectors are biased against non-native English writers"). Two rules
follow from it here:

- **No identity features.** No rule reads the language, the script, a place
  name, a country or the origin of a name. A place fills the `<PLACE>` slot and
  carries no weight; a test swaps places and requires the same verdict and
  frame. Clustering uses character shingles, so it treats every script alike.
- **A fairness bound.** On each split, no stratum's false-positive rate may
  exceed the overall rate by more than 0.10. The bench reports the rate, its
  95% Wilson interval and the count for every stratum, and fails when one is
  over the bound.

## Corpus and results

The corpus in `corpus/campaign/` is synthetic and labelled. Every name, product
and company in it is invented. `hand.json` holds hand-written organic and
templated items in these strata: standard, ESL, dialect, translated,
code-switched, non-English (Spanish, Portuguese, Japanese, Arabic, Hindi,
Russian, French, Chinese, Korean, Swahili, Indonesian, German), real people who
mention crypto, genuine enthusiasm, technical posts with numbers, founder
posts, and disclosed endorsements. A generator adds 40 slot-filled persona
bios and a batch of three coordinated quote campaigns mixed with 20 organic
replies. Items alternate between a dev split and a heldout split.

Targets were set after a baseline on dev: precision 0.90, recall 0.80,
false-positive rate 0.05, cluster pair precision 0.95, pair recall 0.90. The
dev baseline had bio recall 0.74, because the role frame missed a capitalised
"A"; that fix and a generator fix came before the heldout split was scored.
Heldout was scored once, with the rules frozen:

- Posts: precision 1.000; recall 0.818 (95% interval 0.52 to 0.95) on 11
  templates; false-positive rate 0.000 (0 to 0.15) on 22 organic posts.
- Bios: precision 1.000; recall 0.968 (0.84 to 0.99) on 31 templates;
  false-positive rate 0.000 (0 to 0.09) on 39 organic bios.
- Clusters: pair precision 1.000 and pair recall 1.000 on 84 gold pairs.

Every stratum's false-positive rate is 0 on both splits, so the fairness bound
holds. The full numbers are in `corpus/campaign/results-dev.json` and
`results-heldout.json`. Rerun them with
`python -m articulate.campaign_bench --split heldout`.

### Limits of these numbers

- One author wrote the rules and the corpus in the same session. The heldout
  split guards against tuning on the items, but not against shared blind
  spots, so these figures are an upper bound on real-world performance.
- The strata are small. A stratum with 2 to 6 negatives has an upper interval
  between 0.39 and 0.79; a zero rate there does not rule out a high one.
- The generated bios and the cluster batch come from the same frames the
  detectors know. They test the machinery, and they say little about recall
  on campaigns written to other templates.
- Recall on non-English templates is low. The stock frames are English, so a
  Spanish or Portuguese persona bio or launch post is missed. This is a known
  gap, measured and left open.
- No real posts or accounts are in the corpus. Performance on live platform
  text is unmeasured.

### Controls that must fail

The bench runs deliberately bad detectors and scrambled labels and requires
each to fail the targets, so a passing bench cannot come from loose targets:

- Flag every post, or flag every bio: precision falls to the base rate.
- Shuffled bio labels: a real detector scored against random labels.
- Flag any bio that mentions crypto: real people who mention crypto are hard
  negatives.
- Flag any post with a spec number: technical posts are hard negatives.
- Exact-match clustering: templated posts differ in their slots.
- Cluster by product name: organic replies name the product too.

## Boundaries

This feature serves readers and moderators who want to see how a campaign was
built. It is not a writing aid for campaign copy, and no score here is a target
for a rewrite. The [boundaries](boundaries.md) page applies in full.
