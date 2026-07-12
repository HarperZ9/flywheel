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

## Color language: it only ever means a verdict

The rule is absolute: color signals a verdict, never decoration, never an
accent-per-item. The palette is three verdicts plus ink, and nothing else. At most
one hot mark per view.

- **Verified (`--verified`, a green)** marks the accept path and passes: a routed
  answer, a passed check, a receipt, a "yes" cell.
- **Drift (`--drift`, an iris)** is caution, honest nulls, and escalation, and it is
  the single restrained accent. Kickers, links, and the primary action use it. This
  is where the honest null lives, in the eye line.
- **Unverifiable (`--unverifiable`)** is the third, muted state.
- **Ink on a calm ceramic ground** carries all ordinary text.

No gradient text, no rainbow, no accent-per-item. The full spectrum lives only in
generative art, where the art is the subject, never in UI or emphasis.

Full tokens, light and dark, are in `assets/palette.css`. Source of truth is
`portfolio-site/system/system.css`, owned by the parallel design session.

## Type: two faces, no more

- **Hanken Grotesk** carries every text role, from hero display to caption.
  Hierarchy comes from weight and size, never from switching typefaces.
- **Conso** carries data, labels, table headers, receipts, and code.
- Both are self-hosted woff2 (see `site/assets/fonts`), so the type is faithful
  offline, with system fallbacks before they load.
- If a surface needs a third face to feel distinct, the layout is failing, not the
  type.

## Figure-ground and material

- Text always sits on a calm, near-solid ceramic ground. Cards are ground tints
  with a hairline. No glass, no backdrop-blur, no drop-shadow stacks.
- Kickers are mono, uppercase, wide-tracked, small, in the drift color.

## Theme

The canon reference is the ceramic light ground; that is the default. A near-black
dark counterpart carries the same verdict semantics. The app honors a saved choice,
then the reader's OS preference; the toggle stamps `data-theme` and wins in both
directions. The site should do the same. Both themes are verified to hit WCAG AA.

## The reference implementation

The shipping shell (`site/index.html` in the repo) and `harperz9.github.io` are the
canonical look. When in doubt, match them. The two schematics in `assets/` use the
same verdict tokens (verified green for the accept path, drift iris for the failure
edges).
