# chorus — a discourse-synthesis satellite for gather

- Date: 2026-07-15
- Status: approved design, pre-implementation
- Repo: `chorus` (zero external runtime dependencies, stdlib only)
- Orbits: `gather` (the accountable research-intake flagship)

## Summary

`chorus` turns a captured corpus of comments and threads into a weighted,
clustered, re-checkable reading of the discourse. It answers, mechanically and
with a receipt, the two questions a person asks after gathering a comment
section: what are people actually saying, and which of it is worth reading.

gather captures the witnessed corpus. chorus is a pure post-processor over that
corpus: it normalizes discourse items, scores their sentiment, clusters them
into themes, weights each theme by engagement and sentiment intensity, and emits
a digest that carries a receipt a stranger can re-run. A daemon drives the whole
loop unattended over a watchlist, and also serves on-demand jobs.

## Motivation

Three gaps were hit directly while using gather this session:

1. **gather discards engagement.** The video adapter keeps only a comment's text
   and author; it drops `like_count`, `parent`, and pin/verified flags. Without
   engagement there is no way to rank "the more valuable comments," and no weight
   to combine with sentiment. This is a real defect in gather's own terms
   (a receipt that omits what the community actually signalled) and is fixed as a
   scoped part of this work, in gather, where it belongs.
2. **There is no discourse synthesis.** Ranking, clustering into themes, and
   surfacing substantive dissent were done by hand. That should be a tool.
3. **There is no sentiment layer and no daemon.** The pipeline was one-shot and
   manual. It should run itself on a schedule and weight discourse by sentiment.

## Non-goals (YAGNI)

- Not a general NLP toolkit. Sentiment and clustering exist only to serve the
  discourse digest.
- Not an accept/reject gate. chorus has no verdict path; it never accepts or
  refuses anything on the basis of sentiment. Sentiment is a weight and a signal.
- Not a re-implementation of capture. chorus does not fetch primary media; it
  consumes gather corpora (it may trigger a gather capture, but gather does the
  fetching and owns the provenance receipt).
- Not a real-time stream processor. The daemon polls on an interval; it is not a
  low-latency pipeline.

## Architecture

Five units, each with one purpose, a stated interface, and stated dependencies.
Stdlib only. Mirrors gather's module conventions.

```
gather corpus ─▶ item.normalize ─▶ sentiment.score ─▶ synthesize.cluster+weight ─▶ Digest(+Receipt)
                                                                                        │
watchlist ─▶ daemon.tick ──────────────────────────────────────────────────────────────┘
on-demand job ─▶ daemon.submit ─────────────────────────────────────────────────────────┘
surfaces: CLI · MCP · Flywheel desktop
```

### 1. `item.py` — normalize any gather source into one shape

Defines the discourse unit and the adapters that produce it.

```
DiscourseItem:
  id            str           # stable content/source id
  source        str           # "video" | "reddit" | "feed" | "web" | "docs"
  responds_to   str           # what this is discourse ABOUT (video id, post id, url)
  parent        str | None    # the item this replies to (thread structure), None = top level
  author        str
  text          str
  engagement    int           # likes / upvotes / reactions; 0 when a source has none
  ts            float | None  # unix seconds when known
  meta          dict          # source-specific extras (pinned, verified, is_op, ...)
```

- **What it does:** map a gather `Item` (or a raw source row) into a
  `DiscourseItem`. One adapter per gather kind. Engagement is read from gather
  `meta` (populated by the scoped gather fix below); chorus never re-fetches
  primary media to obtain it. When a source genuinely carries no engagement
  signal, engagement is `0` and the digest records the absence (an honest null,
  never a fabricated weight).
- **Interface:** `normalize(items: list[Item]) -> list[DiscourseItem]`.
- **Depends on:** the gather `Item` shape only (a data contract, not an import of
  gather's impure edges).

### 2. `sentiment.py` — hybrid, honest, provenance-tagged

- **`lexicon` (default, deterministic):** a valence + intensity scorer in the
  VADER lineage, implemented zero-dep. Handles negation, intensifiers, ALL-CAPS,
  punctuation emphasis, and a small emoji table. Output per item:
  `compound in [-1, 1]`, plus the firing tokens and the vocabulary hash, so the
  score re-computes exactly from the text. Provenance: `lexicon`.
- **`model_pass` (optional):** routes a flagged subset (compound near zero, or
  high-engagement items where a wrong read is costly) through the Flywheel router
  for a nuance label. Non-deterministic, so each such score is stamped
  provenance `model:<model_ref>` with the prompt hash, and is visibly distinct
  from lexicon scores in the digest and receipt.
- **Credo alignment:** there is no accept path here, so "no learned model in the
  accept path" is satisfied by construction. The model is used only for an
  advisory weight, and its output is never allowed to become the sole basis of a
  claim without being marked model-authored. Lexicon scores are re-checkable;
  model scores are opinions with a named author.
- **Interface:** `score(items, *, model=None) -> list[Scored]` where
  `Scored = DiscourseItem + {compound, provenance, evidence}`.

### 3. `synthesize.py` — the discourse synthesis

- **Cluster:** group items into themes with zero-dep, deterministic clustering:
  hashed TF-IDF feature vectors and cosine similarity, using **leader (greedy
  nearest-leader)** assignment above a stated threshold. (Phase 1 implementation
  note: single-link connected-components was tried first and rejected — on 1082
  real comments it chained 991 into one megatheme; leader assignment requires
  similarity to a cluster's leader, not a transitive chain, so it resists that
  collapse. Leaders seed in engagement order, so popular comments anchor themes.)
  Deterministic given the same input and params.
- **Weight:** each item's weight is `w = g(engagement) * (1 + k * |compound|)`,
  where `g` is a damped engagement transform (e.g. `log1p`) and `k` is the
  sentiment-intensity coefficient. The exact formula and constants are recorded
  in the receipt; the formula is the answer to "sentiment weights as well."
- **Per theme, the digest emits:** a label (top terms + the highest-weight
  representative item), size, the sentiment distribution (share positive /
  negative / neutral and the weighted-mean compound), the engagement-weighted
  score, the single sharpest substantive item, and the highest-weight **dissent**
  (the strongest minority-sentiment voice, so the digest never hides disagreement
  behind a mean).
- **Interface:** `synthesize(scored, *, params) -> Digest`.

### 4. `daemon.py` — watchlist poller and job service (both)

- **Watchlist:** `watchlist.json` lists sources (channel, subreddit, video, or an
  inline gather run config). Each tick, per source: detect items new since the
  stored cursor, trigger a gather capture, run the lens, write a receipted digest
  to the store, advance the cursor. Poll interval is configurable.
- **Job service:** a stdlib `http.server` on localhost accepts a target and runs
  the same pipeline on demand, returning the digest id. No new pipeline; the same
  path the poller uses.
- **State:** a small store (JSONL or sqlite, following gather/mneme), holding
  cursors, digests, and a run log. Crash-safe in the gather sense: a digest is
  written before the cursor advances, so a crash re-processes rather than skips.
- **Interface:** `tick(now)`, `submit(target)`, `serve(port)`.

### 5. Surfaces

- **CLI:** `chorus run <corpus|target>`, `chorus daemon`, `chorus watch add|list|remove`,
  `chorus digest <id>`, `chorus status`, `chorus doctor`. `doctor` follows the
  honest-diagnostic pattern (report which capabilities are wired; never emit a
  verdict token for a check that did not run).
- **MCP (`mcp.py`):** `chorus.run`, `chorus.digest`, `chorus.status`,
  `chorus.doctor`, `chorus.watch`, on the `project-telos.flagship-action/v1`
  envelope, matching gather's MCP shape.
- **Flywheel desktop:** a destination that renders a digest: themes, weighted
  scores, and the sentiment distribution. **Design-canon constraint (load-bearing):**
  color means a verdict only, so the sentiment distribution renders in **neutral
  ink and weight**, never the verified/drift palette. The one hot verdict mark in
  the view is reserved for the digest's receipt verify status (MATCH / DRIFT /
  UNVERIFIABLE), not for positive/negative sentiment.

## Data flow and the receipt (the differentiator)

Every digest carries a re-checkable receipt:

```
DigestReceipt:
  input_sha256     # content hash over the ordered DiscourseItems judged
  lexicon_vocab_sha
  cluster_params   # threshold, feature dims, linkage
  weight_formula   # the exact g, k
  model_ref        # present only if a model pass ran; else null (honest null)
  digest_sha256    # hash over the emitted themes
  method_version
```

`verify(digest)` recomputes the lexicon scores, the clustering, and the weights
from the stored inputs and confirms `digest_sha256`; a tampered digest or a
changed method fails re-derivation. Model-pass scores are excluded from the
deterministic re-derivation and are re-listed with their own provenance, so the
receipt is honest about which parts are re-checkable and which are model opinion.

The digest never claims sentiment is ground truth. It states the method and its
known coarseness (lexicon sarcasm-blindness, clustering granularity) as a
first-class honest null.

## Scoped gather fix (SHIPPED 2026-07-15, in gather)

Done and merged to gather `main`: `parse_video` now carries `like_count`,
`parent`, `is_pinned`, `author_is_verified`, and `author_is_uploader` into the
comment Item meta when yt-dlp provides them, absent otherwise (honest null).
Verified end to end: gather captured 116 real comments with engagement, and
`chorus run` on that corpus reported `engagement_coverage {present:116, total:116}`
with real weighted ranking, where before the fix every weight was 0. The original
requirement, for the record:

gather's `video.py` comment Item must preserve engagement so a downstream reader
(chorus or a human) can rank what the community signalled:

- Carry `like_count`, `parent`, `is_pinned`, `author_is_verified`,
  `author_is_uploader` into the comment Item `meta`, when yt-dlp provides them.
- Preserve the same for other comment-bearing adapters where the source exposes
  it. Where a source has none, the field is absent (honest null), never a zero
  presented as real.
- TDD in gather, its suite green, on its own branch. chorus reads these fields
  through `item.normalize`; when they are absent it degrades to engagement `0`
  and records the absence.

## Testing (falsifiers, gather style)

- `sentiment`: negation flips sign; intensifiers raise magnitude; caps/punct
  emphasis registers; the vocab hash pins the lexicon; a re-score reproduces
  exactly.
- `synthesize`: clustering is deterministic across runs; two clearly-distinct
  theme sets do not merge; the weight is monotonic in engagement and in
  |sentiment|; dissent is surfaced when a minority sentiment exists.
- `receipt`: `verify` passes for an intact digest and FAILS for a tampered one
  or a changed method version.
- `daemon`: the cursor advances only after a digest is written; a re-tick with no
  new items is a no-op; a crash between digest-write and cursor-advance
  re-processes rather than skips.
- `item`: each adapter maps its source faithfully; a missing engagement field
  degrades to `0` with the absence recorded.

## Build order (phases, each a shippable slice)

1. [SHIPPED] `item` + `sentiment.lexicon` + `synthesize` + the digest receipt +
   CLI `run` (the core lens, fully offline and deterministic). 26 tests,
   whole-branch reviewed, verified on 1082 real comments.
2. [SHIPPED] The scoped gather engagement fix, so real corpora carry weight.
   Merged to gather main; the loop is closed end to end.
3. `daemon` (watchlist tick + cursor store) then the on-demand job endpoint.
4. `sentiment.model_pass` (optional, provenance-tagged).
5. MCP surface, then the Flywheel desktop destination (canon-constrained).

## Decisions resolved in brainstorming

- Daemon: both a watchlist poller and an on-demand job service.
- Sentiment: hybrid, lexicon default + optional model pass, provenance-tagged.
- Input: any gather source, via the `DiscourseItem` normalizer.
- Output: standalone receipted artifacts, plus MCP and a desktop surface.
