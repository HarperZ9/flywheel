# Bolstering effective context in the wrapper (2026-07-14)

## The question

Can a wrapper meaningfully uplift the context a model safely works with,
model-agnostically, without baking anything into weights or serving
infrastructure, while reducing mistakes as context fills?

## The answer, stated precisely

Yes, with two corrections to the framing.

**The wrapper cannot enlarge attention; it curates what occupies it.**
No prompt-layer trick extends the number of tokens a model actually
attends over. That is fixed in the weights and the serving stack. What
the wrapper controls is which tokens are in the window at each step. So
"bolster the context window" means "make what is in the window smaller
and more relevant", not "fit more".

**Nominal context is not reliable context.** Models degrade before their
stated limit: lost-in-the-middle (Liu et al. 2023, high confidence) and
effective-length benchmarks such as RULER (high confidence) show accuracy
sagging as the window fills, under the nominal cap. Every model has a
reliable zone smaller than its advertised size, and it differs per model.
The uplift a wrapper can deliver is to keep each model inside its own
measured reliable zone.

## The mechanisms (all wrapper-level, model-agnostic)

- Retrieval: keep the corpus external, pull the relevant slice per step.
- Fold-with-recall: compress old spans but keep a content-addressed
  pointer to the verbatim original, so a buried fact is recallable, not
  lost (this repo: fold_index, memory recall with span-hash provenance).
- Hierarchical paging: working set plus episodic plus semantic store with
  eviction (the MemGPT/Letta shape, high confidence).
- Prompt compression: drop low-information tokens (LLMLingua-style, high
  confidence); lossy.
- Chunk and map-reduce: split into reliable-zone chunks, process, reduce.

## The honest boundary, which is the crux of "fewer mistakes"

Naive compaction increases error rate. The context-provenance dossier
(this repo, 2026-07-14, adversarially verified) recorded a measured
governance decay: summarizing history drove constraint-violation rate
from 0% to about 30% average (up to 59%), and training-free pinning of
the load-bearing constraints restored it to 0% (moderate-high
confidence). A wrapper that only summarizes to save room silently drops
the constraint that was holding the model correct, and the model then
makes MORE mistakes. The fix is not better summaries; it is: a pinned
constraint never leaves the window.

The trade is real and bounded: reliability is bought with
recall-completeness. It is only a net win when eviction is accountable
(recall receipts) and constraints are pinned. This wrapper does not make
the model smarter; it keeps it working where it is already reliable.

## What shipped: the context governor

`harness/context_governor.py` (7 tests): curate a set of context items to
a per-model reliable budget. Rules, each a credo commitment:

- A pinned constraint always survives, even under a tight budget. If the
  pins alone exceed the reliable budget the governor reports `over_pinned`
  rather than eating a constraint (a dropped constraint is a mistake, not
  a saving).
- The window fills only to `reliable_fraction * budget`, the measured
  safe zone, not the nominal cap.
- Everything evicted is folded with a content hash, so nothing is lost,
  only moved; a fold hash re-fetches the verbatim span.
- Model-agnostic by construction: it operates on items and a token
  budget, so any provider in the roster (ChatGPT, Claude, local) routes
  through the same curation, each parameterized by its own reliable zone.

## Next slices (named, not yet built)

- Route it: `POST /api/context` returns the governed window plus its
  receipt; then wire it into the router so every provider inherits it,
  the same way the scaffold now fires on every message.
- Compose recall: fold overflow through the existing fold_index so a
  governed-out span is recallable by hash through `/api/memory/recall`,
  closing the loop end to end.
- Measure the claim: a bench that fills context to increasing levels with
  and without the governor and reports the mistake-rate-vs-fill curve per
  model, so "fewer mistakes as context fills" is a measured interval, not
  an assertion. The reliable_fraction for each model comes from this
  bench, not a guess.
