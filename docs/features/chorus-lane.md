# chorus (discourse-synthesis lane)

## In one sentence

chorus turns a gathered corpus of comments and threads into a weighted, clustered, re-checkable reading of the discourse, and every digest carries a receipt a stranger can re-run to get the same answer.

## In one paragraph

chorus is the discourse-synthesis satellite in the Flywheel ecosystem. It reads a corpus of comments (a gather corpus directory, or a JSON list of gather-style rows), scores each comment with a deterministic lexicon, ranks themes by how much the crowd engaged and how strongly it felt, and names the topics the corpus is split on. The whole deterministic reading is content-addressed: `chorus run --verify` re-derives the digest from the inputs and confirms it, and a tampered digest fails even when its own stored hash was recomputed to match. Sentiment is used as a weight and a signal, never as an accept gate. The package is standard-library only with zero runtime dependencies, and it orbits gather: gather captures the corpus with provenance, chorus synthesizes the discourse on top of it. Inside Flywheel, chorus is reached through `harness/chorus_bridge.py` and the `/api/discourse` gateway endpoints, which drive the standalone `chorus` CLI and return its JSON answer verbatim.

## Where it sits in Flywheel

chorus is wired into Flywheel as a bridged satellite, not as an entry in the lane MCP roster. Two facts, observed in the code, set that scope:

- It is not listed in `harness/lanes_registry.py` (the `LANES` dict that the lane resolver, health probes, and public roster surfaces read). So Flywheel does not spawn a `chorus` MCP child through the lane runtime.
- It composes through `harness/chorus_bridge.py`, which shells the installed `chorus` CLI (`chorus run --verify`, `chorus corpora`, `chorus digests`) and wraps the JSON output under `flywheel.discourse-digest/v1`, `flywheel.discourse-corpora/v1`, and `flywheel.discourse-digests/v1`. The gateway exposes those at `POST /api/discourse`, `/api/discourse/corpora`, and `/api/discourse/digests`.

chorus also ships its own MCP stdio surface (`chorus mcp`) for any MCP host that wants to drive it directly, separate from the Flywheel bridge. The status envelope declares the role `discourse-synthesis` and records `orbits: gather`, which places it downstream of the perception organ.

## Feature list

Each item below is bound to the module that implements it.

- **Deterministic lexicon sentiment** (`src/chorus/sentiment.py`). A compact valence lexicon of 30 words, 15 positive and 15 negative, each carrying a valence in the declared range [-3, 3]. `score_text` is pure: the same text always returns the same compound score, so it re-checks exactly.
- **Negation, intensifier, caps, and punctuation rules** (`sentiment.score_text`). 10 intensifiers widen or narrow a valence (two of them, `somewhat` and `slightly`, dampen it). 9 negators flip a valence and keep about three quarters of its size, so a negation weakens a claim and leaves part of its force. An all-caps valence word longer than one letter counts a quarter more. Up to four exclamation marks add five percent each. Intensifiers and negators are read up to three tokens back.
- **A squashed compound score** (`sentiment.score_text`). The summed valence is divided by the root of itself squared plus 15, which holds the score inside (-1, 1) so no single loud comment runs away with a theme.
- **A versioned, hashed vocabulary** (`sentiment.lexicon_vocab_sha`). The lexicon and its version string hash into every receipt. Editing the word list changes the hash, which invalidates every digest built with the old list at verify time.
- **Engagement read with honest absence** (`src/chorus/item.py`). Engagement is read from the source (`like_count` or `score`) when present. When a source carries no signal, engagement is 0 and `meta.engagement_present` records the absence, so a missing vote reads as absent and never as a real zero-weight vote.
- **Source normalization for gather kinds** (`item.normalize`). gather catalog rows map into `DiscourseItem`s. The kinds `comment`, `feed-entry`/`feed_item`, `post`, and `reply` are treated as discourse; other kinds (the media they respond to) are skipped.
- **Engagement-and-sentiment weighting** (`synthesize.item_weight`). Weight is `log1p(engagement) * (1 + k * abs(compound))` with `k` default 0.5. Engagement is damped by the log, and a comment with no engagement carries weight 0.
- **Leader clustering over hashed TF-IDF cosine** (`synthesize.cluster`). Comments cluster by what they say, using a hashed TF-IDF cosine across 512 dimensions with a join threshold of 0.18. A comment joins the existing leader it is most similar to, or starts a new cluster. Leaders are seeded most-engaged first, so the most-engaged comments anchor the themes, and membership requires similarity to a cluster's leader, which keeps a large diverse corpus split into distinct themes. The tokenizer is Unicode-aware, so non-Latin corpora still form term vectors. The term hashing uses md5 with `usedforsecurity=False`, so it keeps working under FIPS mode.
- **Corpus-salience theme labels with support metadata** (`synthesize._label_terms`). Each theme label is chosen from terms that are salient in the cluster against the whole corpus, excluding corpus-wide chatter. `label_quality` records a support level (`singleton`, `cluster`, `weak`, or `fallback`), any warnings, coverage counts, and the scored terms, so the digest marks a weak or singleton label with its support level and a reader sees the thin evidence behind it.
- **Per-theme sentiment split and controversy** (`synthesize._build_theme`). Each theme carries its size, its engagement-and-sentiment weighted score, a sentiment split (positive, negative, neutral fractions and mean compound), and a controversy score. Controversy is the population standard deviation of the theme's compound sentiment in [0, 1]: 0 at consensus, approaching 1 as voices split hard. It reads out how divided and how strongly felt a theme is.
- **Representative and dissent voices** (`synthesize._build_theme`). Each theme names its highest-weight comment as the representative, and the single highest-weight comment that disagrees with the theme's majority direction as the dissent (or `null` when there is none). The theme's `item_ids` stay in the output, so a caller can resolve labels back to source links and provenance in the corpus.
- **Contested aspects, measured across the whole corpus** (`synthesize.contested_aspects`). A separate lens reports the aspects the corpus is split on, measured across every comment that mentions a term, not per cluster. A term qualifies only with real two-sided disagreement (at least one clearly positive and one clearly negative voice), so one-sided praise and neutral chatter are excluded. It surfaces up to 12 aspects, each needing at least 3 mentioning voices. This lens survives the lexical clustering that would file praise and complaint about the same topic under different themes.
- **Honest nulls in the digest body** (`synthesize.synthesize`). The digest's `method` block records engagement coverage (how many items carried a signal, out of the total), the distinct response targets, and a coarseness note stating the lexicon's limits in the digest itself.
- **A content-addressed receipt** (`src/chorus/receipt.py`). The receipt binds the input hash, the lexicon vocabulary hash, the cluster parameters, the weight formula, the model reference, the digest body hash, and the method version. The current method version is `chorus-lens/3`.
- **Re-derivation on verify** (`receipt.verify`). `verify` first checks that the submitted digest body still matches its own receipt, then re-scores sentiment from each comment's text (the caller's stored `compound` is ignored, so fabricated sentiment cannot verify), re-clusters, and re-weights from the parameters the receipt recorded, then compares hashes. It reads those parameters from the receipt, so raising a live default cannot silently break an already-versioned receipt. A digest whose themes, weights, or sentiment distribution do not follow from the inputs fails, even when its own stored `digest_sha256` was recomputed to match its tampered body.
- **Fail-closed version support** (`receipt.verify`, `SUPPORTED_METHOD_VERSIONS`). An unsupported method version fails closed. Historical `chorus-lens/2` receipts remain checkable through an explicit legacy verifier against the v2 body shape; a v2 receipt does not bind the v3-only label terms or `label_quality`.
- **An optional, advisory model overlay** (`sentiment.model_pass`, `src/chorus/model.py`). A model read can be overlaid on the items the lexicon is least sure of (`|compound| < ambiguous_cut`, default 0.1), plus an optional top-k by engagement. The overlay is provenance-tagged (`model:<ref>`) with the prompt hash it read, and it is deliberately excluded from the digest body hash, so it never enters the re-checkable core. A model that raises marks its items `model-failed: <type>` as named evidence, and the run continues. `SubprocessModel` is the shipped edge: it shells a command once with the texts as JSON on stdin and reads a JSON array back, so a caller can wire any model without chorus depending on it.
- **Corpus discovery** (`src/chorus/corpora.py`). `list_corpora` scans a root and its immediate subdirectories for gather corpora (directories holding `catalog.jsonl`) and reports each corpus's comment count, subject title, and response target. A missing root is a named error, never a crash.
- **A change-driven daemon** (`src/chorus/daemon.py`). A watchlist names corpora to poll. Each tick computes the corpus input signature (the same content hash the receipt binds); an unchanged signature is a no-op, so nothing re-runs until there is new discourse. On change the daemon synthesizes, writes the receipted digest by its own hash, then advances the cursor in that order, so a crash between the two leaves the corpus due for re-synthesis on the next tick. A bad corpus is named and skipped without advancing.
- **A source-change review gate** (`src/chorus/decision.py`). `chorus decision` compares a current gather-style source pack against a reference pack and returns a receipt-backed verdict: `MATCH` (the compared source ids and fingerprints are unchanged), `DRIFT` (a reviewer should inspect the changed rows), or `UNVERIFIABLE` (source capture or identity must be repaired). It reports added, removed, changed, and unchanged item ids, verifies both deterministic digests, and returns a local digest outline for each side. It does not decide whether a source claim is true, complete, or ready for publication.
- **Typed false-success controls for the review gate** (`decision.py`). Missing or malformed text, invalid or missing or mismatched or non-UTF-8 gather content objects, duplicate ids, and absent or null or blank or non-string ids all return a typed `UNVERIFIABLE` state, which holds a broken source for repair before any comparison treats it as unchanged. Content objects are re-hashed against the catalog `sha256` before their text is trusted.
- **A safe-by-default public projection** (`decision._public_projection`). The review gate's public projection keeps counts, hashes, receipts, and stated limitations by default. Human-readable public ids, source names, refs, and URLs appear only through an operator-authored public-policy sidecar; raw source-row metadata cannot authorize public output. The projection excludes raw source text, author names, local paths, private session content, and bulk comments, and it redacts source-failure messages.
- **An MCP stdio surface** (`src/chorus/mcp.py`). `chorus mcp` serves the discourse lens as MCP tools on the `project-telos.flagship-action/v1` envelope: `chorus.status`, `chorus.doctor`, `chorus.run`, `chorus.corpora`, `chorus.digests`, and `chorus.decision`. It is standard-library only. A tool failure is returned as a named, non-fatal error result.
- **Operator-spine status and doctor** (`src/chorus/flagship.py`). `status` reports the role, commands, and MCP tools. `doctor` resolves each capability's live entry point and reports `available` or `absent`, a diagnostic that can fail when a capability is missing. Both default to the operational token `OK` and never render a verdict token, since they measure nothing.
- **Cross-platform UTF-8 output** (`cli.main`). The CLI reconfigures stdout to UTF-8, so a digest of real comments with emoji or non-Latin text does not crash a cp1252 console on Windows.

## Usage, step by step

The steps below use the bundled sample so they run with no external data.

1. **Install from the checkout.** From the chorus repo root:

   ```bash
   pip install -e .
   ```

   If `chorus` is not on `PATH` afterward, reinstall with `python -m pip install -e .` and open a new shell.

2. **Synthesize the bundled sample and verify it.**

   ```bash
   chorus run examples/discourse-sample.json --verify
   ```

   The output is a JSON digest. With `--verify`, the digest carries a top-level `"verified": true` when the receipt re-derives.

3. **Synthesize your own corpus.** Point `run` at a gather corpus directory (a folder holding `catalog.jsonl`) or a JSON list of gather-style rows:

   ```bash
   chorus run <corpus> --verify
   ```

4. **Overlay a model read on the uncertain comments (optional).** Add `--model` with a command that reads a JSON array of texts on stdin and emits `[{compound, label}]`:

   ```bash
   chorus run <corpus> --model "<command>" --model-ref "<name>" --ambiguous-cut 0.1
   ```

   The overlay is listed under `model_layer` with its own provenance and stays outside the digest hash.

5. **Discover gather corpora under a root.**

   ```bash
   chorus corpora <root>
   ```

6. **Watch a corpus and synthesize on change.**

   ```bash
   chorus watch add <corpus>
   chorus daemon --interval 300
   ```

   The daemon polls the watchlist and re-synthesizes only when a corpus changes, storing each receipted digest by its own hash. `chorus daemon --once` runs a single tick and exits.

7. **List what the daemon has stored.**

   ```bash
   chorus digests <store>
   ```

8. **Run a source-change review gate.**

   ```bash
   chorus decision <current> --reference <reference> --task "Check whether sources changed"
   ```

   Add `--public --public-policy public-policy.json` to emit the safe public projection with operator-allowlisted public metadata.

9. **Run the MCP server.**

   ```bash
   chorus mcp
   ```

   `chorus.status` and `chorus.doctor` are MCP tools exposed here, not separate CLI subcommands.

## Reference, capability by capability

### CLI subcommands (`src/chorus/cli.py`)

- `chorus run <path> [--verify] [--model CMD] [--model-ref NAME] [--ambiguous-cut FLOAT]`: synthesize a discourse digest from a corpus. `<path>` is a JSON file of gather-style rows or a gather corpus directory. Prints the digest as sorted JSON. Exit 0 on success, 1 on a read error. When loading a corpus directory, a comment's text is read from `objects/<sha[:2]>/<sha[2:]>` only after the `sha256` field passes a strict hex check, so a read path is never built from an unvalidated field.
- `chorus corpora <root>`: discover gather corpora under a root. Exit 1 when the root is not a directory.
- `chorus watch {add|list|remove} [corpus] [--watchlist FILE]`: manage the daemon watchlist (`watchlist.json` by default).
- `chorus daemon [--watchlist FILE] [--store DIR] [--once] [--interval SECONDS]`: poll the watchlist and synthesize on change. Default store is `.chorus-run`, default interval 300 seconds.
- `chorus digests <store> [--limit N]`: list recent digests the daemon has stored, newest first (default limit 20).
- `chorus decision <current> --reference <reference> [--task TEXT] [--public] [--public-policy FILE]`: run a source-change review gate. Exit 0 when the comparison is ok, 2 otherwise.
- `chorus mcp`: run the MCP stdio server.

### MCP tools (`src/chorus/mcp.py`)

- `chorus.status`: the operator-spine status envelope. Never renders a verdict token.
- `chorus.doctor`: which capabilities are wired (`available`/`absent`).
- `chorus.run {corpus, verify?}`: a corpus to a digest, with an optional receipt re-derivation.
- `chorus.corpora {root}`: discover gather corpora under a root.
- `chorus.digests {store, limit?}`: the digests the daemon has stored, newest first.
- `chorus.decision {current, reference, task?, public?, public_policy?}`: the source-change review gate, with an optional safe public projection.

### The digest (`synthesize.Digest`)

A digest holds `responds_to`, `n_items`, `themes`, a `method` block, `contested` aspects, a `receipt`, and an optional `model_layer`. Each `Theme` holds `label`, `terms`, `size`, `weighted_score`, `sentiment`, `representative`, `dissent`, `item_ids`, `label_quality`, and `controversy`. Each contested row holds `term`, `mentions`, `pos`, `neg`, and `contested`.

### The receipt (`receipt.DigestReceipt`)

`input_sha256`, `lexicon_vocab_sha`, `cluster_params`, `weight_formula`, `model_ref`, `digest_sha256`, and `method_version`. `verify(digest, scored)` returns a single boolean and is read-only.

### The Flywheel bridge (`harness/chorus_bridge.py`)

- `discourse_digest(corpus)`: runs `chorus run <corpus> --verify` and returns `{schema: flywheel.discourse-digest/v1, corpus, verified, result}`, or a named error. Timeout 120 seconds.
- `list_corpora(root)`: runs `chorus corpora <root>` and returns `{schema: flywheel.discourse-corpora/v1, root, corpora}`.
- `recent_digests(store, limit=20)`: runs `chorus digests <store>` and returns `{schema: flywheel.discourse-digests/v1, store, digests}`.
- `chorus_available()`: whether the CLI resolves (console script on `PATH`, else `python -m chorus`). A missing CLI is a named error advising `pip install chorus-discourse`.

### Gateway endpoints (`harness/gateway.py`)

- `POST /api/discourse {corpus}`: a gathered corpus to a verified digest.
- `POST /api/discourse/corpora {root}`: discover gather corpora as discourse sources.
- `POST /api/discourse/digests {store, limit?}`: what the daemon has synthesized.

Each returns HTTP 400 when the bridge reports an error, 200 otherwise.

## Composition tutorial

### Which seam it is

chorus is a synthesis seam that sits downstream of perception. gather is the registered perception lane in Flywheel: it captures a corpus with provenance receipts and writes a `catalog.jsonl` plus a content-addressed `objects/` store. chorus reads that corpus and emits a verified reading of the discourse in it. Its status envelope names the seam directly: `role: discourse-synthesis`, `orbits: gather`.

### What it consumes from peers

- **A gather corpus.** chorus reads gather catalog rows and their content objects, keyed by the same `sha256` content hash gather binds. `item.normalize` maps gather's discourse kinds into `DiscourseItem`s and skips the media rows they respond to. The corpus is the only required input, and no service key or provider account is needed for the deterministic path.
- **An optional subprocess model (advisory).** The model seam accepts any callable that takes texts and returns `[{compound, label}]`. `SubprocessModel` wires that to any command line, so a caller can point it at a model CLI or a Flywheel router command. This wiring is a supported extension point exercised through `--model`; chorus itself imports no model client. The overlay stays outside the receipt.

### What it emits for peers

- **A verified discourse digest** (`flywheel.discourse-digest/v1` from the bridge, or the raw digest from the CLI and MCP). It carries the ranked themes, the contested aspects, and a re-checkable receipt. Because each theme keeps its `item_ids`, a downstream reviewer can resolve a theme back to the source links and provenance that gather recorded.
- **A source-change decision** (`chorus.source-decision/v1`, with a `chorus.public-source-decision/v1` public projection). A verdict of `MATCH`, `DRIFT`, or `UNVERIFIABLE` tells a release or review step whether a prior synthesis can be reused, needs a source review, or must hold for source repair.
- **Corpus and digest listings** (`flywheel.discourse-corpora/v1`, `flywheel.discourse-digests/v1`) for a UI or another agent to browse available sources and stored results.

### A worked example: gather to chorus, inside the app

This walks one path: a captured corpus becomes a reusable, verified reading, using the gateway that already wires the two together.

1. **gather captures the corpus.** The perception lane records the comments on a subject and writes a corpus directory with `catalog.jsonl` and an `objects/` store. (See the gather lane docs for its own capture commands.)

2. **Discover the corpus through the app.** Ask the gateway which gather corpora live under a root:

   ```bash
   curl -s localhost:8765/api/discourse/corpora \
     -H 'content-type: application/json' \
     -d '{"root": "<gather-root>"}'
   ```

   The response is `flywheel.discourse-corpora/v1` with each corpus's comment count and subject, so a caller can pick a run without knowing the path by heart.

3. **Synthesize a verified digest.** Hand the chosen corpus to the discourse endpoint:

   ```bash
   curl -s localhost:8765/api/discourse \
     -H 'content-type: application/json' \
     -d '{"corpus": "<corpus-path>"}'
   ```

   The bridge runs `chorus run <corpus> --verify` and returns `flywheel.discourse-digest/v1` with `verified: true` and the digest under `result`. The app reads chorus's own answer, receipt included, as chorus emitted it.

4. **Reuse it safely when the source moves.** Later, when gather re-captures the subject, decide whether the earlier reading still holds before reusing it:

   ```bash
   chorus decision <new-corpus> --reference <old-corpus> \
     --task "Reuse prior synthesis?"
   ```

   `MATCH` means the source observations are unchanged and the prior digest can be reused. `DRIFT` lists the changed rows for review. `UNVERIFIABLE` means the capture must be repaired first.

The composition is one direction of data with a receipt at each hop: gather binds the corpus by content hash, chorus binds its reading to that same hash, and the decision gate binds a reuse verdict to both. A peer that consumes a chorus digest can re-run `verify` on it and get the same answer, or reject it.

## Limitations and honest nulls

- **Sentiment is coarse by construction.** The lexicon is English-only and literal, with no sarcasm, irony, or context. The digest states this in its own `coarseness` note. Sentiment is a weight, never a verdict.
- **Clustering is lexical, not semantic.** Themes group by shared wording. The contested-aspects lens exists specifically because lexical clustering separates positive and negative wording about the same topic; it does not make the clustering semantic.
- **A comment with no engagement carries weight 0.** The log-damped weight is zero at zero engagement, so an un-engaged comment does not anchor a theme on its own.
- **The model overlay is opinion, not verification.** It is advisory, provenance-tagged, and excluded from the receipt. It never enters the re-checkable core.
- **The review gate judges source change, not source truth.** `MATCH` means the compared source ids and fingerprints are unchanged. It does not prove the source set is complete, nor that any claim in it is true or ready to publish.
- **Inside Flywheel, chorus is a bridged satellite.** It is driven through `harness/chorus_bridge.py` and the gateway, and it is not currently a registered entry in the Flywheel lane MCP roster (`harness/lanes_registry.py`). A Flywheel install reaches it only when the standalone `chorus` CLI is installed and resolvable.

## License and posture

chorus is source-available under the Functional Source License (FSL-1.1-MIT): read it, run it, build on it, with commercial use that competes with the project reserved. It is an independent Zentropy Labs project built by Zain Dana Harper, with zero runtime dependencies and a standard-library-only implementation. It orbits gather and composes into Flywheel through the bridge and gateway described above.