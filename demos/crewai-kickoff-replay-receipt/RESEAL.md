# Reseal log

Each entry records one authorized change to the public files and how `SHA256SUMS`
was updated for it. This file is outside the sealed evidence bundle: it is not a
bundle material in `canonical-result.json` and the action receipt does not pin it.
`SHA256SUMS` lists it, because `verify_public.py` requires every public file there.

## 2026-10-04: art roll-out (PR #1)

- Authorized change: brand art from the shared art direction of 2026-10-04,
  approved by the author in chat on 2026-10-04.
- Added to `SHA256SUMS`: `RESEAL.md` and 17 files under `docs/`:
  `docs/art/hero-dark.svg`, `docs/art/hero-light.svg`, `docs/art/receipts.json`,
  `docs/art/social.png`, `docs/brand/README.md`, `docs/brand/lockup-horizontal-dark.svg`,
  `docs/brand/lockup-horizontal-light.svg`, `docs/brand/lockup-stacked-dark.svg`,
  `docs/brand/lockup-stacked-light.svg`, `docs/brand/mark-16.png`, `docs/brand/mark-16.svg`,
  `docs/brand/mark-32.png`, `docs/brand/mark-512.png`, `docs/brand/mark-64.png`,
  `docs/brand/mark-dark.svg`, `docs/brand/mark-light.svg`, `docs/brand/mark-tile.svg`.
- Changed: none. Every digest already in `SHA256SUMS` is unchanged.
- `README.md` is left byte-identical. It is a bundle material: its digest sits in
  `canonical-result.json`, whose hash the append-only `action-receipt.json` pins. The
  receipt's correction rule says corrections are new joined receipt events and the
  sealed event is not mutated, so the planned README hero was not applied.
- `SHA256SUMS` before: `b9b8e926e4a297cbb82ba1d68e77f55e03f7f6451f015da0bf183174e7f2ee7a`.
  The digest after this entry depends on this file, so the commit message records it.
- `python verify_public.py` prints `verification=MATCH` with the leak scans at zero.
