# behavior-transform.io Design System

behavior-transform.io follows the current Project Telos flagship presentation
used by Gather, Index, Telos, Crucible, and Forum: a restrained off-white
witness card, black product typography, thin evidence rules, and one violet
verification node.

## Tokens

- paper: `#f4f3ef`
- ink: `#0b0c0e`
- muted: `#585c64`
- data: `#2f3238`
- witness-violet: `#4636e8`
- rule: `rgba(11, 12, 14, 0.14)`

## Typography

Two faces only: Hanken Grotesk and Conso. Hierarchy comes from weight and size.

- Display and body: Hanken Grotesk, set heavy for display. GitHub renders README text in its own system sans.
- Data, labels and code: Conso, falling back to `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`.
- Kilon, the earlier display face, was retired on 2026-10-04 because readers found it hard to read. Artwork exported before that date may still carry it.

## Asset Roles

- `docs/brand/behavior-transform-hero.svg`: IO-boundary identity card.
- `docs/brand/behavior-transform-mark.svg`: compact crossing and receipt mark.

## Rules

- Lead with read, write, exec, fetch, and receipt boundaries.
- Show what crossed the host boundary without exposing raw private payloads.
- Keep the copy direct enough for IDE, CLI, MCP, and hook users.
- Make privacy mechanics visible without turning the README into policy prose.
