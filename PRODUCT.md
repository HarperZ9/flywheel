# PRODUCT.md — Flywheel Desktop

## Register
product — a desktop tool. Design serves the work; the surface is operated,
not read. (Source of record: the ecosystem canon in
telos-v2/project-docs/DESIGN-VOICE-CANON.md; this file summarizes, never
redefines.)

## Users & Purpose
One person doing real work with models: chatting, running gated agents over
their own projects, judging claims, keeping receipts. The app is the native
client for the Flywheel gateway (127.0.0.1:8799). The primary job on any
screen: do the task, see the process, keep proof that can be re-checked
later. The relationship the product wants: secure, not anxious — work
trustworthy enough to walk away from.

## Brand Personality
Precision instrument, reserved energy, honest. Reveal the process; support
the user's decision; never make it for them.

## Design Principles
- Two typefaces only: Hanken Grotesk (text, hierarchy by weight) + Conso
  (mono voice: hashes, counts, kickers). Never a third family.
- Color is verdict-only: verified / drift / unverifiable + ink on a calm
  ground. One hot mark per view. The spectrum lives in generative art only.
- Honest nulls stay visible. A view that cannot show DRIFT is not shipped.
- Ink on calm ground; hairline structure; cards only where they earn it.
- Ground and type family are the user's (appearance panel presets); the
  verdict palette is not on the menu.

## Anti-references
- Glassmorphism, gradients, spectrum accents, engagement mechanics.
- Dashboard-cliché hero metrics; decorative motion.
- Any surface that asserts quality it cannot re-check (no unmeasured
  claims dressed as verdicts).

## Accessibility
Body text ≥4.5:1 against the ground in both themes (ink ramps in
lib/theme/tokens.dart); verdict color never the sole carrier of meaning
(pills always carry their word); keyboard-first where the OS expects it.

## Tech
Flutter desktop (Windows first). Tokens: lib/theme/tokens.dart via
ThemeExtension (context.fw). Shared grammar: lib/widgets/fw.dart. Gates:
flutter analyze clean, flutter test green, files under 300 lines.
