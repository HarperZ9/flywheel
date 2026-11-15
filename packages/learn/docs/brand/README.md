# learn brand assets

Current assets, rendered on 4 October 2026 from the shared art direction:

- `docs/art/hero-dark.svg`, `docs/art/hero-light.svg`: the README hero, 1280 x 480, text outlined from Hanken Grotesk and Conso.
- `docs/art/social.png`: the GitHub social preview, 1280 x 640.
- The mark: `docs/brand/mark-16.png`, `docs/brand/mark-32.png` and `docs/brand/mark-16.svg` (favicon sizes),
  `docs/brand/mark-64.png`, `docs/brand/mark-512.png` and `docs/brand/mark-tile.svg` (app and listing icons),
  `docs/brand/mark-light.svg` and `docs/brand/mark-dark.svg` (on a page, no tile).
- The lockups: `docs/brand/lockup-horizontal-light.svg`, `docs/brand/lockup-horizontal-dark.svg`,
  `docs/brand/lockup-stacked-light.svg` and `docs/brand/lockup-stacked-dark.svg`.
- `docs/art/receipts.json`: a `superstack.receipt/1` for every PNG, with the seed, the scene hash and the font hashes.

The seed is the repository name. The same seed gives the same SVG bytes.

The previous README header, `docs/art/learn-header.svg`, stays in the repository with its `docs/art/learn.art.json` record.

The record below describes the previous brand render and stays as it was written.

## Previous render

The hero image is the Project Telos flagship card, the shared clean brand used by every
flagship and the website.

## Rendering Receipt

- Source: the flagship card at `portfolio-site/img/og/_card.html?f=learn`, driven by the
  card data (role, wordmark, headline, pipeline, glyph) in `portfolio-site/img/og/cards-data.js`.
- Rendered to `learn-hero.png` (2400x1260) with headless Chrome at a 1200x630 viewport and 2x
  device scale, the same capture the other flagship heroes use.
- Design: ceramic card face, a single iris accent, a mono eyebrow (`PROJECT TELOS / LEARNING AID`),
  a sans headline, the pipeline line, a ghost wordmark, and one glyph from the shared card glyph
  library. `learn-mark.svg` is the compact square mark.
- Accessibility floor: high-contrast text on a solid field; the README `<img>` carries alt text.
- Provenance boundary: original layout and copy; no third-party image, template, or generated-art
  source was used.
