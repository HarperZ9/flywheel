# Flywheel: Brand and Voice

The one-paragraph brief, then the rules. This exists so the marketing site and the
running app read as one product made by one hand.

Flywheel leads with wonder, earns trust by trying to break its own claims, and
shows its work. The tone is calm and human, and confident. It works with any model
the reader brings, and it is unapologetically the best tool for the job: the router
and harness that also verifies. Calm confidence, not hype.

---

## Voice rules

- **Feature first.** Lead with what it does for the reader, then the run-it-now
  command, then the evidence. Accountability is one doorway line, not the opening
  pitch.
- **Human, not corporate.** Short sentences. Concrete nouns. No hype stack, no
  "revolutionary", no "seamless synergy". Rigor reads calm.
- **No em-dashes.** Rewrite the sentence instead of reaching for a dash. Use a
  comma, a colon, a period, or parentheses.
- **Honest nulls stay.** "We do not claim a capability uplift" is a feature of the
  voice, not a weakness to edit out. Keep the confidence intervals visible.
- **Show the commands.** They are short and they work. A real command beats an
  abstract promise.
- **No dead ends.** Do not tease a feature that is not live, and keep internal
  status labels off any public page. If it is not real yet, it does not go on the
  surface.
- **Confident register.** "A companion for every model" means it works with any
  model, not that it is timid. Lead with what makes it the best option: it routes to
  everything and verifies where nothing else does. It does what the other routers,
  runners, and harnesses do, plus the one thing none of them do. The model is the
  replaceable half; the harness is the durable half.
- **Best-in-class, honestly.** Claim product superiority plainly, because it is
  true and specific (route plus verify, receipts, one surface, offline capable).
  Never dress up the model's measured capability beyond what the intervals show.
  The two are different axes; be bold on the first, exact on the second.

## Words to avoid on the site

Build-machine paths, internal gate or lane language, "operator", draft or staged
status lines, biological metaphors for software (no organ, membrane, anatomy; use
component, part, service). These belong in internal docs, never on a product page.

## Color language

- **Indigo (`--accent`)** is the trust and verify color. Use it for the verified
  path, passed checks framed as accents, and primary calls to action.
- **Warm amber (`--warm`)** is the honest-caution color. Use it for escalation,
  honest nulls, and "what we cannot prove yet". It signals candor, not error.
- **Green (`--ok`)** is a passed external check. Use it sparingly, only where
  something genuinely passed.

Full tokens, light and dark, are in `assets/palette.css`, lifted verbatim from the
shipping shell so the site can match it exactly.

## Type

- Body is a warm serif (ui-serif, Georgia, Palatino). It carries the human,
  written-by-a-person feel.
- Headings are a tight sans (ui-sans-serif, Segoe UI, Inter, system-ui), weight
  650, slightly negative letter-spacing.
- Eyebrows are uppercase, wide letter-spacing, small, in warm amber.

## Theme

The app defaults to the reader's OS theme and offers a toggle that stamps
`data-theme` on the root, which wins in both directions. The site should do the
same, so a reader who prefers dark gets dark on both surfaces.

## The reference implementation

The shipping shell (`site/index.html` in the repo) is the canonical look. When in
doubt, match it. The two schematics in `assets/` already use these exact tokens.
