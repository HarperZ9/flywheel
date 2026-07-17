# Flywheel: Site Designer Handoff

Everything needed to build the Flywheel marketing site so it reads as one product
with the running app. Self-contained: you should not need the codebase to work
from this bundle.

## The live product

Flywheel is public and runnable now: **https://github.com/HarperZ9/flywheel**.
Its README is the canonical short pitch and the source of truth for the current
positioning. Point the site's primary call to action and code links there.

**Positioning, current (use this register):** Flywheel is the router and harness
that verifies. It does what every router, local runner, and agent harness does,
on one surface, and adds the verify layer none of them have. It routes to any
provider online with your keys and runs fully offline against local weights. Lead
best-in-class and confident on the product; keep the honest null on the model's
measured capability (see BENCHMARKS.md). This is the operator's largest flagship
and the front door to the whole spine, so present the vision in full.

## What is in here

| File | Use it for |
|---|---|
| `PRODUCT-COPY.md` | Ready-to-place copy in the product voice: hero, seam, features, CTAs |
| `BRAND-VOICE.md` | Voice rules, words to avoid, color language, type, theme behavior |
| `SPEC-SHEET.md` | Feature matrix, the route table, requirements, real-vs-not-yet |
| `BENCHMARKS.md` | The numbers, their intervals, and the honest null to keep visible |
| `assets/palette.css` | Design tokens (light and dark), lifted verbatim from the app |
| `assets/architecture.svg` | The one-surface architecture diagram, on-brand and recolorable |
| `assets/verified-loop.svg` | The propose, verify, receipt loop diagram |
| `evidence/benchmark-ci.json` | The receipt the benchmark numbers cite, so the site can link a re-checkable source |

## The three rules that make this product itself

1. **Feature first, evidence close behind.** Lead with what it does for the
   reader. Accountability is one doorway line, not the opening pitch.
2. **Keep the honest null.** "We do not claim a capability uplift" stays on the
   page, in the candor color. It is the reason the other claims are believed.
3. **One product, one hand.** The site and the app share the palette in
   `assets/palette.css` and the reference look in the shipping shell. Match it.

## The reference implementation

The shipping shell is the canonical look and the source of the palette. The two
SVGs already use these exact tokens, so they will sit correctly on either theme.

## What to link, so the site stays re-checkable

The app serves every cited number as a receipt file at its own origin. Where the
site shows a benchmark, link the evidence, so a reader can confirm it rather than
trust it. `evidence/benchmark-ci.json` is the file to mirror or reference.

## What not to put on the site

Build-machine paths, internal status labels, gate or operator language, and
teasers for features that are not live. If a capability is not real yet, it is
marked so in `SPEC-SHEET.md`; leave those off the public page rather than
promising them.
