# Product

## Register

product

## Users

Flywheel is for one person doing real work with local or hosted models, companion tools, receipts, and project files. The user may arrive through the native desktop app, the command line, or the fallback browser shell, but the native app is the public product surface for operating the platform without living in a terminal.

## Product Purpose

Flywheel runs an AI task with the model and tools the user chooses, records what happened, and keeps evidence that can be rechecked later. The Python engine owns routing, lanes, receipts, verification, and the localhost gateway. The Flutter desktop client renders that engine and must not reimplement it. A successful screen lets the user do the task, understand current readiness, and find the receipt or honest null that explains what did or did not happen.

## Brand Personality

Precision instrument, reserved energy, honest. The product should feel calm, capable, and inspectable. It should reveal the process, support the user's decision, and avoid making unavailable capability look ready.

## Anti-references

Avoid glassmorphism, gradients, dashboard hero metrics, engagement mechanics, decorative motion, and color used as decoration. Avoid a flat list of impressive panels when the user needs task paths. Avoid treating declared, missing, stale, not probed, or unavailable lanes as installed success.

## Design Principles

- Show the workflow first: start from the user's primary task, then expose evidence and diagnostic depth as needed.
- Keep every capability state honest: live, declared, missing, stale, unverified, unavailable, and blocked must remain distinct.
- Preserve the engine boundary: native UI calls existing gateway handlers and reads existing records instead of inventing local truth.
- Keep expert tools findable without making them the first surface for newcomers.
- Use the existing shell grammar: two typefaces, verdict-only color, calm ground, hairlines, keyboard-reachable controls, and no broad visual rebrand.

## Accessibility & Inclusion

Default to readable body text, visible focus, semantic controls, keyboard paths for shell actions, high-contrast support, reduced-motion behavior, and labels that do not rely on color alone. Empty states should teach what changes the state, and mobile or paired-device states should avoid terminal instructions that the device cannot execute.

## Source Basis

- Root `README.md` states that Flywheel has a Python engine and native Flutter client, with the desktop app as the native surface.
- `AGENTS.md` says the Flutter app renders the engine and must never reimplement it.
- `desktop/PRODUCT.md` defines the desktop register, users, personality, honest nulls, verdict-only color, typeface pair, and accessibility expectations.
- `desktop/CLAUDE.md` points design and voice to the ecosystem canon and keeps tokens in `desktop/lib/theme/tokens.dart`.
- `desktop/lib/accessibility/*`, `desktop/test/high_contrast_test.dart`, and related accessibility tests define keyboard, focus, contrast, and reduced-motion expectations.
