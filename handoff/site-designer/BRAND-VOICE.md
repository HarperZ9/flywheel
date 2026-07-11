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

This is the Project Telos design system: a cool near-black glass ground, cool-white
ink, silver to cyan to blue accents. No warm hue except one caution signal.

- **Cyan (`--cyan`)** is the verify and trust signal. Use it for kickers, passed
  checks, focus rings, and small accent marks. On light it darkens to a deep teal
  so small text clears WCAG AA.
- **Blue (`--blue`, `--blue-deep`)** carries links and the single emphatic action
  (a chrome-to-blue solid button). Not decoration.
- **Silver (`--silver`)** is chrome highlight and secondary text.
- **Warm amber (`--warn`)** is the ONLY warm color, and the honest-caution signal:
  escalation, honest nulls, "what we cannot prove yet". Use it sparingly. It reads
  as candor, not error.
- The **glass** primitive (a cool low-opacity fill with a top gloss wash and a
  backdrop blur) carries depth over the ground. Panels, cards, and inputs are glass.

Full tokens, light and dark, are in `assets/palette.css`. Source of truth is
`portfolio-site/system/telos.css`, owned by the parallel design session.

## Type

- **Display: Archivo** (700 to 800), tight negative letter-spacing, for headings.
- **Body: Manrope**, for lede and prose.
- **Mono: JetBrains Mono**, for kickers, labels, table headers, receipts, and code.
  This is heavy, on purpose: the mono labels are a core part of the telos identity.
- All three carry system fallbacks so the surface holds before the webfonts load.
- Kickers are mono, uppercase, wide-tracked, small, in cyan, with a short cyan rule.

## Theme

Dark is native to telos. The app defaults to dark, honors a saved choice, then the
reader's OS preference. The toggle stamps `data-theme` on the root and wins in both
directions. The site should do the same, so a reader gets the same theme on both
surfaces. Both themes are verified to hit WCAG AA contrast.

## The reference implementation

The shipping shell (`site/index.html` in the repo) is the canonical look, rendered
in this exact telos system with both themes. When in doubt, match it. The two
schematics in `assets/` use the same cool tokens.
